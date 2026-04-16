import argparse
import asyncio
import errno
import json
import os
import shlex
import signal
import subprocess
import time
import urllib.parse
from datetime import date, datetime
from pathlib import Path
from typing import Any

from pydoll.browser import Chrome
from pydoll.browser.options import ChromiumOptions
from pydoll.browser.tab import Tab
from pydoll.constants import Key

from service.base_mail_service import Mail, MailBox, BaseMailService
from service.base_sms_service import BaseSmsService
from service.config_service import ConfigService, OpenAIRegisterConfig
from service.cpa_service import CpaService
from service.http_service import HttpService
from service.mail.mail_factory import create_mail_service
from service.sms.sms_factory import create_sms_service
from util import openai_register_util, pydoll_util
from util.account_util import Account, create_new_account
from util.logger import get_logger
from util.openai_register_util import OAuthStart

LOGGER = get_logger("OpenAI Register", level="DEBUG")


class CallbackServer:
    """本地 OAuth 回调服务。"""

    def __init__(self, host: str = "127.0.0.1", port: int = 1455):
        self.host = host
        self.port = port
        self._server: asyncio.base_events.Server | None = None
        self._clients: set[asyncio.StreamWriter] = set()

    @staticmethod
    def _pids_listening_on_port(port: int) -> set[int]:
        """查找当前占用端口的进程。"""

        cmd = ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        except FileNotFoundError:
            return set()

        if result.returncode not in (0, 1):
            return set()

        pids: set[int] = set()
        for line in result.stdout.splitlines():
            candidate = line.strip()
            if candidate.isdigit():
                pids.add(int(candidate))
        return pids

    @staticmethod
    def _kill_pids(pids: set[int], timeout: float = 3.0) -> None:
        """尝试释放端口占用进程。"""

        current_pid = os.getpid()
        targets = [pid for pid in pids if pid != current_pid]

        for pid in targets:
            try:
                os.kill(pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                pass

        deadline = time.time() + timeout
        alive = set(targets)
        while time.time() < deadline and alive:
            for pid in list(alive):
                try:
                    os.kill(pid, 0)
                except ProcessLookupError:
                    alive.discard(pid)
                except PermissionError:
                    pass
            time.sleep(0.1)

        for pid in alive:
            try:
                os.kill(pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass

    async def _try_free_port(self) -> None:
        pids = self._pids_listening_on_port(self.port)
        if not pids:
            return
        LOGGER.info(f"端口 {self.port} 被占用，准备释放进程: {sorted(pids)}")
        self._kill_pids(pids)
        await asyncio.sleep(0.2)

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self._clients.add(writer)
        try:
            data = b""
            while b"\r\n\r\n" not in data:
                chunk = await reader.read(1024)
                if not chunk:
                    break
                data += chunk
                if len(data) > 64 * 1024:
                    break

            response = (
                b"HTTP/1.1 200 OK\r\n"
                b"Content-Type: text/plain; charset=utf-8\r\n"
                b"Content-Length: 2\r\n"
                b"Connection: close\r\n"
                b"\r\nOK"
            )
            writer.write(response)
            await writer.drain()
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
            self._clients.discard(writer)

    async def start(self) -> None:
        try:
            self._server = await asyncio.start_server(self._handle_client, self.host, self.port)
        except OSError as exc:
            if exc.errno != errno.EADDRINUSE:
                raise
            await self._try_free_port()
            self._server = await asyncio.start_server(self._handle_client, self.host, self.port)

        LOGGER.info(f"Callback server started at http://{self.host}:{self.port}")

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

        for writer in list(self._clients):
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
        self._clients.clear()
        LOGGER.info("Callback server stopped")


class OpenAIRegister:
    """OpenAI 注册机。"""

    def __init__(
            self,
            config: OpenAIRegisterConfig,
            mail_provider: BaseMailService,
            sms_provider: BaseSmsService | None,
            cpa_service: CpaService | None,
            http_service: HttpService
    ):
        self._config = config
        self._mail_provider = mail_provider
        self._cpa_service = cpa_service
        self._http_service = http_service
        self._sms_provider = sms_provider

    @classmethod
    def from_config_file(cls, config_file: str | Path = "config.toml") -> "OpenAIRegister":
        """通过配置文件实例化注册机。"""
        app_config = ConfigService.load(config_file)
        http_service = HttpService(app_config.http)
        mail_provider = create_mail_service(app_config, app_config.openai_register.mail_provider, http_service=http_service)
        cpa_service = CpaService(app_config.cpa, http_service) if app_config.openai_register.upload_cpa_auth_file else None

        sms_provider = create_sms_service(app_config, app_config.openai_register.sms_provider,
                                          register_sms_config=app_config.openai_register.sms_config,
                                          http_service=http_service) if app_config.openai_register.sms_provider else None

        return cls(
            config=app_config.openai_register,
            mail_provider=mail_provider,
            cpa_service=cpa_service,
            http_service=http_service,
            sms_provider=sms_provider
        )

    def _build_chrome_options(self) -> ChromiumOptions:
        options = ChromiumOptions()
        options.headless = self._config.headless
        options.set_accept_languages("zh-CN")

        options.add_argument("--window-size=1920,1080")
        options.add_argument("--lang=zh-CN")
        options.set_accept_languages("zh-CN,zh;q=0.9")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-setuid-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")

        options.add_argument(f"--user-agent={self._config.user_agent}")

        if self._config.chrome_binary_path:
            options.binary_location = self._config.chrome_binary_path
        if self._config.chrome_proxy:
            options.add_argument(f"--proxy-server={self._config.chrome_proxy}")
        return options

    async def _prepare_browser_env(self, tab: Tab):
        oauth = openai_register_util.generate_oauth_url(self._config.oauth_client_id, self._config.callback_server_port)
        LOGGER.info("探测 Cloudflare Turnstile 环境")
        async with tab.expect_and_bypass_cloudflare_captcha(time_to_wait_captcha=5):
            await tab.go_to(oauth.auth_url)

    @staticmethod
    async def _ensure_input(tab: Tab, expression: str, value: str, timeout: int = 10, try_times: int = 3):
        success = await pydoll_util.ensure_input(tab, expression, value, timeout, try_times)
        if success:
            return
        current_value = await pydoll_util.get_live_value(expression, tab)
        raise RuntimeError(f"输入 {expression} 失败，当前值={current_value}，目标值={value}")

    async def _wait_for_sms_code(self, phone_number: dict[str, Any], timeout_sec: int = 60) -> str:
        deadline = time.time() + timeout_sec + 5
        LOGGER.info(f"开始轮询短信验证码 => 5s 间隔，{timeout_sec}s 超时")
        while time.time() < deadline:
            try:
                code = self._sms_provider.get_activation_code(phone_number)
                if code:
                    LOGGER.info(f"获取短信验证码成功: {code}")
                    return code
                LOGGER.debug(f"未获取短信验证码")
            except Exception as exc:
                LOGGER.warning(f"获取短信验证码失败: {str(exc)[:200]}")
            await asyncio.sleep(5)
        return ""

    async def _wait_for_sms_code_resend_if_needed(self, tab: Tab, phone_number: dict[str, Any]) -> str:
        btn_resend = await tab.query("//button[@value='resend']", timeout=10, raise_exc=False)
        if btn_resend:
            await btn_resend.wait_until(is_visible=True, is_interactable=True, timeout=10)
            await btn_resend.click(humanize=True)
        code = await self._wait_for_sms_code(phone_number, self._config.sms_timeout_seconds)
        if not code:
            for i in range(self._config.sms_retries):
                btn_resend = await tab.query("//button[@value='resend']", timeout=10, raise_exc=False)
                if btn_resend:
                    await btn_resend.wait_until(is_visible=True, is_interactable=True, timeout=10)
                    LOGGER.info(f"等待短信验证码超时，将尝试第 {i + 1} 次重新获取验证码")
                    LOGGER.info("点击重新发送短信验证码")
                    await btn_resend.click(humanize=True)
                    code = await self._wait_for_sms_code(phone_number, self._config.sms_timeout_seconds)
                    if code:
                        break
        return code

    async def _wait_for_verify_code(self, mail_box: MailBox, received_after: str, timeout_sec: int = 60) -> str:
        """轮询 MailService 获取验证码。"""
        deadline = time.time() + timeout_sec + 5
        LOGGER.info(f"开始轮询验证码 => 5s 间隔，{timeout_sec}s 超时")

        def mail_filter(mail: Mail) -> bool:
            if not mail.sender or "openai.com" not in mail.sender:
                return False
            if (not mail.receive_at) or mail.receive_at < received_after:
                return False
            if (not mail.subject) or (("ChatGPT" not in mail.subject) and ("OpenAI" not in mail.subject)):
                return False
            return True

        last_error: Exception | None = None
        while time.time() < deadline:
            try:
                code = self._mail_provider.get_latest_verification_code(mail_box, mail_filter=mail_filter)
                if code:
                    LOGGER.info(f"获取验证码成功: {code}")
                    return code
                LOGGER.debug(f"未获取验证码")
            except Exception as exc:
                LOGGER.warning(f"获取验证码失败: {str(exc)[:200]}")
                last_error = exc
            await asyncio.sleep(5)

        if last_error is not None:
            LOGGER.warning(f"等待验证码超时，最后一次错误: {last_error}")
        return ""

    async def _wait_for_verify_code_resend_if_needed(self, tab: Tab, mail_box: MailBox, received_after: str) -> str:
        btn_resend = await tab.query("//button[@value='resend']", timeout=10, raise_exc=False)
        if btn_resend:
            await btn_resend.wait_until(is_visible=True, is_interactable=True, timeout=10)
            await btn_resend.click(humanize=True)
        code = await self._wait_for_verify_code(mail_box, received_after, self._config.email_timeout_seconds)
        if not code:
            for i in range(self._config.email_retries):
                btn_resend = await tab.query("//button[@value='resend']", timeout=10, raise_exc=False)
                if btn_resend:
                    await btn_resend.wait_until(is_visible=True, is_interactable=True, timeout=10)
                    LOGGER.info(f"等待验证码超时，将尝试第 {i + 1} 次重新获取验证码")
                    LOGGER.info("点击重新发送验证码")
                    await btn_resend.click(humanize=True)
                    code = await self._wait_for_verify_code(mail_box, received_after, self._config.email_timeout_seconds)
                    if code:
                        break
        return code

    async def _try_input_password_and_submit(self, tab: Tab, password: str, *, password_expression: str, try_times: int = 8) -> None:
        """输入密码并提交。"""

        for index in range(try_times):
            input_password = await tab.query(password_expression, timeout=self._config.default_timeout_seconds)
            await input_password.wait_until(is_visible=True, is_interactable=False, timeout=10)
            LOGGER.info(f"输入密码：{password}")
            # await input_password.type_text(password, humanize=True)
            await self._ensure_input(tab, password_expression, password)

            btn_continue = await tab.query("//button[@data-dd-action-name='Continue']", timeout=10)
            await btn_continue.wait_until(is_visible=True, is_interactable=True, timeout=10)
            LOGGER.info(f"点击继续按钮")
            await btn_continue.click(humanize=True)

            next_element = await tab.query(
                "//button[@data-dd-action-name='Try again'] | //input[@name='code']",
                timeout=self._config.default_timeout_seconds,
            )
            if next_element.tag_name == "button":
                LOGGER.warning(f"密码提交失败，点击重试")
                await next_element.click(humanize=True)
                continue

            LOGGER.info(f"提交密码成功")
            return

        raise RuntimeError("提交密码失败")

    async def _start_register(self, tab: Tab) -> Account:
        """执行 ChatGPT 账号注册。"""
        await tab.go_to("https://chatgpt.com", timeout=self._config.default_timeout_seconds)
        LOGGER.info("访问 https://chatgpt.com")
        btn_login = await tab.query("//button[@data-testid='login-button']", timeout=10)
        await btn_login.wait_until(is_visible=True, is_interactable=True, timeout=10)
        LOGGER.info("点击登录按钮")
        await btn_login.click(humanize=True)

        input_email = await tab.query("//input[@id='email']", raise_exc=False, timeout=5)
        if not input_email:
            LOGGER.warning("未找到邮箱输入框，刷新页面重试")
            await tab.refresh()
            btn_login = await tab.query("//button[@data-testid='login-button']", timeout=10)
            await btn_login.wait_until(is_visible=True, is_interactable=True, timeout=10)
            await btn_login.click(humanize=True)
            input_email = await tab.query("//input[@id='email']", raise_exc=False, timeout=5)
        if not input_email:
            raise RuntimeError("未找到邮箱输入框")

        account = create_new_account(self._mail_provider.generate_mail_box())
        if self._config.default_account_password:
            account.password = self._config.default_account_password
        birthday_text = "-".join(account.birthday)
        LOGGER.info(
            f"生成账号 => email={account.email}, username={account.username}, password={account.password}, birthday={birthday_text}"
        )

        await input_email.wait_until(is_visible=True, is_interactable=False, timeout=10)
        LOGGER.info(f"输入邮箱：{account.email}")
        await self._ensure_input(tab, "//input[@id='email']", account.email)
        # await input_email.type_text(account.email, humanize=True)

        btn_submit = await tab.query("//button[@type='submit']", timeout=10)
        await btn_submit.wait_until(is_visible=True, is_interactable=True, timeout=10)
        LOGGER.info("点击提交按钮")
        received_after = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        await btn_submit.click(humanize=True)

        input_password_or_code = await tab.query("//input[@name='new-password' or @name='code']", timeout=self._config.default_timeout_seconds)
        if input_password_or_code.get_attribute("name") == "new-password":
            await self._try_input_password_and_submit(tab, account.password, password_expression="//input[@name='new-password']")

        input_code = await tab.query("//input[@name='code']", timeout=self._config.default_timeout_seconds)
        await input_code.wait_until(is_visible=True, is_interactable=False, timeout=10)
        LOGGER.info("等待验证码")

        code = await self._wait_for_verify_code_resend_if_needed(tab, account.mail_box, received_after=received_after)
        if not code:
            raise RuntimeError("获取验证码失败")

        LOGGER.info(f"输入验证码：{code}")
        # await input_code.type_text(code, humanize=False)
        await self._ensure_input(tab, "//input[@name='code']", code)

        btn_continue = await tab.query("//button[@data-dd-action-name='Continue']", timeout=10)
        await btn_continue.wait_until(is_visible=True, is_interactable=True, timeout=10)
        LOGGER.info("点击继续按钮")
        await btn_continue.click(humanize=True)

        url, input_username = await pydoll_util.wait_url_or_element(tab, url_flags=["https://chatgpt.com"], ele_selectors=["//input[@name='name']"],
                                                                    raise_exc=False, timeout_sec=self._config.default_timeout_seconds)
        # 直接注册成功，不出现用户名输入框
        if input_username:
            await input_username.wait_until(is_visible=True, is_interactable=False, timeout=10)
            LOGGER.info(f"输入用户名：{account.username}")
            # await input_username.type_text(account.username, humanize=True)
            await self._ensure_input(tab, "//input[@name='name']", account.username)

            input_age = await tab.query("//input[@name='age' or @name='birthday']", timeout=2, raise_exc=False)
            if input_age.get_attribute("name") == "age":
                await input_age.wait_until(is_visible=True, is_interactable=False, timeout=5)
                age = str(date.today().year - int(account.birthday[0]))
                LOGGER.info(f"输入年龄：{age}")
                # await input_age.type_text(age, humanize=True)
                await self._ensure_input(tab, "//input[@name='age']", age)
            else:
                birthday_compact = "".join(account.birthday)
                LOGGER.info(f"输入生日：{birthday_text}")
                await tab.keyboard.press(Key.TAB)
                await tab.keyboard.type_text(birthday_compact)

            btn_finish = await tab.query("//button[@data-dd-action-name='Continue']", timeout=10)
            await btn_finish.wait_until(is_visible=True, is_interactable=True, timeout=10)
            LOGGER.info("点击完成账户创建按钮")
            await btn_finish.click(humanize=True)

        await pydoll_util.wait_url(tab, url_flags=["https://chatgpt.com"], timeout_sec=self._config.default_timeout_seconds)
        await asyncio.sleep(1)
        LOGGER.info("账号注册成功")
        return account

    async def _try_get_consent_url(self, tab: Tab, account: Account, oauth: OAuthStart, try_times: int = 2) -> bool:
        """执行 OAuth 授权页登录流程。"""

        last_url = ""
        for index in range(try_times):
            try:
                LOGGER.info(f"访问授权链接页面")
                await tab.go_to(oauth.auth_url, timeout=self._config.default_timeout_seconds)
                await asyncio.sleep(2)

                input_email = await tab.query("//input[@name='email']", timeout=10)
                await input_email.wait_until(is_visible=True, is_interactable=False, timeout=10)
                LOGGER.info(f"输入邮箱：{account.email}")
                # await input_email.type_text(account.email, humanize=True)
                await self._ensure_input(tab, "//input[@name='email']", account.email)

                btn_submit = await tab.query("//button[@type='submit']", timeout=10)
                await btn_submit.wait_until(is_visible=True, is_interactable=True, timeout=10)
                LOGGER.info(f"点击提交按钮")

                received_after = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                await btn_submit.click(humanize=True)

                input_password_or_code = await tab.query(
                    "//input[@name='current-password' or @name='code']",
                    timeout=self._config.default_timeout_seconds,
                )
                if input_password_or_code.get_attribute("name") == "current-password":
                    await self._try_input_password_and_submit(
                        tab,
                        account.password,
                        password_expression="//input[@name='current-password']",
                    )

                input_code = await tab.query("//input[@name='code']", timeout=self._config.default_timeout_seconds)
                await input_code.wait_until(is_visible=True, is_interactable=False, timeout=10)
                LOGGER.info(f"等待验证码")

                code = await self._wait_for_verify_code_resend_if_needed(tab, mail_box=account.mail_box, received_after=received_after)
                if not code:
                    raise RuntimeError("无法获取验证码")

                LOGGER.info(f"输入验证码：{code}")
                # await input_code.type_text(code, humanize=False)
                await self._ensure_input(tab, "//input[@name='code']", code)

                btn_continue = await tab.query("//button[@data-dd-action-name='Continue']", timeout=10)
                await btn_continue.wait_until(is_visible=True, is_interactable=True, timeout=10)
                LOGGER.info(f"点击继续按钮")
                await btn_continue.click(humanize=True)

                last_url = await pydoll_util.wait_url(tab, url_flags=["/codex/consent", "/add-phone"], timeout_sec=self._config.default_timeout_seconds)
                if "/add-phone" not in last_url:
                    return False
                else:
                    LOGGER.info(f"需要验证手机")
                    if index < try_times - 1:
                        LOGGER.info(f"尝试重新获取授权链接")
            except Exception as exc:
                LOGGER.warning(f"获取授权链接失败： {exc}")
                raise exc
        if "/add-phone" in last_url and self._sms_provider:
            # 尝试使用 SMS 验证码
            phone_input = await tab.query("//input[@type='tel']", timeout=10)
            await phone_input.wait_until(is_visible=True, is_interactable=False, timeout=10)
            number = self._sms_provider.generate_phone_number()
            if number and "phoneNumber" in number:
                LOGGER.info(f"输入手机号：{number["phoneNumber"]}")
                await phone_input.type_text("+" + number["phoneNumber"])

                await tab.keyboard.press(Key.TAB)
                btn_continue = await tab.query("//button[@data-dd-action-name='Continue']", timeout=10)
                await btn_continue.wait_until(is_visible=True, is_interactable=True, timeout=10)
                LOGGER.info(f"点击继续按钮")
                await btn_continue.click(humanize=True)

                input_code_or_error = await tab.query("//input[@name='code'] | //*[contains(@class, 'error')]", timeout=self._config.default_timeout_seconds)
                await input_code_or_error.wait_until(is_visible=True, is_interactable=False, timeout=10)
                if input_code_or_error.get_attribute("name") == "code":
                    LOGGER.info(f"等待验证码")
                    code = await self._wait_for_sms_code_resend_if_needed(tab, number)
                    if code:
                        LOGGER.info(f"输入短信验证码：{code}")
                        await self._ensure_input(tab, "//input[@name='code']", code)
                        btn_continue = await tab.query("//button[@data-dd-action-name='Continue']", timeout=10)
                        await btn_continue.wait_until(is_visible=True, is_interactable=True, timeout=10)
                        LOGGER.info(f"点击继续按钮")
                        await btn_continue.click(humanize=True)
                        last_url, e = await pydoll_util.wait_url_or_element(tab, url_flags=["/codex/consent"], ele_selectors=["//*[contains(@class, 'error')]"],
                                                                            timeout_sec=self._config.default_timeout_seconds)
                        if last_url and "/codex/consent" in last_url:
                            return True
                        else:
                            self._sms_provider.cancel_activation(number)
                            if e:
                                LOGGER.warning(f"短信验证失败，未进入同意授权页面，异常: {e.inner_html}")
                            else:
                                LOGGER.warning(f"短信验证失败，未进入同意授权页面，最后访问 URL: {last_url}")
                    else:
                        LOGGER.warning(f"获取短信验证码失败")
                        self._sms_provider.cancel_activation(number)
                else:
                    self._sms_provider.cancel_activation(number)
                    LOGGER.warning(f"无法获取验证码: {input_code_or_error.inner_html}")

        raise RuntimeError("需要手机号" if "/add-phone" in last_url else "无法获取授权链接")

    async def _start_oauth(self, tab: Tab, account: Account) -> tuple[OAuthStart, str, bool]:
        """执行 Codex OAuth 流程。"""

        oauth = openai_register_util.generate_oauth_url(self._config.oauth_client_id, self._config.callback_server_port)
        LOGGER.info(f"生成 OAuth 授权链接：{oauth.auth_url}")
        phone_bypass = await self._try_get_consent_url(tab, account=account, oauth=oauth)

        btn_continue = await tab.query("//button[@data-dd-action-name='Continue']", timeout=10)
        await btn_continue.wait_until(is_visible=True, is_interactable=True, timeout=10)
        LOGGER.info("点击继续按钮")
        await btn_continue.click(humanize=True)

        callback_host = f"localhost:{self._config.callback_server_port}"
        LOGGER.info("等待回调链接")
        callback_url = await pydoll_util.wait_url(tab, url_flags=[callback_host], timeout_sec=self._config.default_timeout_seconds)
        LOGGER.info(f"成功获取回调链接：{callback_url}")
        return oauth, callback_url, phone_bypass

    @staticmethod
    async def _submit_callback_url(tab: Tab, oauth: OAuthStart, callback_url: str) -> dict[str, Any]:
        """提交 OAuth 回调地址并生成 CPA 授权文件。"""

        parsed = urllib.parse.urlparse(callback_url)
        query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)

        code = (query.get("code", [""])[0] or "").strip()
        state = (query.get("state", [""])[0] or "").strip()
        error = (query.get("error", [""])[0] or "").strip()
        error_description = (query.get("error_description", [""])[0] or "").strip()

        if error:
            raise RuntimeError(f"codex oauth error: {error}: {error_description}".strip())
        if not code:
            raise ValueError("callback url missing ?code=")
        if not state:
            raise ValueError("callback url missing ?state=")
        if state != oauth.state:
            raise ValueError("state mismatch")
        data = {
            "grant_type": "authorization_code",
            "client_id": oauth.client_id,
            "code": code,
            "redirect_uri": oauth.redirect_uri,
            "code_verifier": oauth.code_verifier,
        }
        headers = [
            {
                "name": "Content-Type",
                "value": "application/x-www-form-urlencoded",
            },
            {
                "name": "Accept",
                "value": "application/json",
            },
        ]
        url = "https://auth.openai.com/oauth/token"
        try:
            response = await tab.request.post(url, data=data, headers=headers)
            if response.status_code != 200:
                raise RuntimeError(f"token exchange failed: {response.status_code}: {response.text}")
            return openai_register_util.create_cpa_auth_file_payload(response.json())
        except Exception as exc:
            # 打印完整的 curl 请求报文，方便人工处理
            curl_parts: list[str] = ["curl", "-i", "-sS", "-X", "POST", url]
            for header in headers:
                curl_parts.extend(["-H", f"{header['name']}: {header['value']}"])
            curl_parts.extend(["--data-raw", urllib.parse.urlencode(data)])
            curl_command = " ".join(shlex.quote(part) for part in curl_parts)
            LOGGER.error("可复现 curl 请求报文：\n%s", curl_command)
            raise exc

    def _save_auth_file_to_local(self, file_name: str, raw_json: str) -> Path:
        """先将授权文件保存到本地目录。"""

        auth_file_dir = self._config.auth_file_dir
        auth_file_dir.mkdir(parents=True, exist_ok=True)

        file_path = auth_file_dir / file_name
        file_path.write_text(f"{raw_json}\n", encoding="utf-8")
        return file_path

    async def start(self, register_num: int = 1):
        """启动完整注册流程。"""
        server = CallbackServer(port=self._config.callback_server_port)
        await server.start()
        for i in range(register_num):
            LOGGER.info(f"{'*' * 50} 开始第 {i + 1} / {register_num} 个注册流程 {'*' * 50}")
            async with Chrome(options=self._build_chrome_options()) as browser:
                account: Account | None = None
                tab: Tab | None = None
                try:
                    tab = await browser.start()
                    await self._prepare_browser_env(tab)
                    account = await self._start_register(tab)
                    oauth, callback_url, phone_bypass = await self._start_oauth(tab, account)
                    LOGGER.info("开始提交回调链接")
                    auth_file = await self._submit_callback_url(tab, oauth, callback_url)
                    raw_auth_file = json.dumps(auth_file, indent=2, ensure_ascii=False)
                    LOGGER.info(f"获取授权文件成功\n{raw_auth_file}")
                    file_name = f"codex{'-phone-bypass' if phone_bypass else ''}-{account.email}.json"
                    local_file = self._save_auth_file_to_local(file_name, raw_auth_file)
                    LOGGER.success(f"授权文件已保存到本地：{local_file}")
                    if self._config.upload_cpa_auth_file:
                        if self._cpa_service is None:
                            raise RuntimeError("未初始化 CPA 服务，无法上传授权文件")
                        ok = self._cpa_service.upload_auth_file(file_name, raw_auth_file)
                        if not ok:
                            raise RuntimeError("上传授权文件失败")
                        LOGGER.success(f"授权文件[{file_name}]上传成功")
                    else:
                        LOGGER.info("配置已关闭上传 CPA，跳过授权文件上传")
                except Exception as exc:
                    LOGGER.error(f"注册失败：{exc}")
                    if not self._config.save_screenshot_on_error:
                        LOGGER.info("配置已关闭异常截图，跳过浏览器截图")
                        continue
                    if tab is None:
                        LOGGER.warning("浏览器标签页尚未初始化，无法截图")
                        continue
                    try:
                        self._config.auth_file_dir.mkdir(parents=True, exist_ok=True)
                        screenshot_name = account.email if account else datetime.now().strftime('%Y%m%d%H%M%S')
                        screenshot_file = self._config.auth_file_dir / f"screenshot_codex-{screenshot_name}.png"
                        await tab.take_screenshot(screenshot_file, quality=100)
                        LOGGER.info(f"异常截图已保存：{screenshot_file}")
                    except Exception as ex:
                        LOGGER.error(f"截图异常：{ex}")
        await server.stop()

    def start_sync(self, register_num: int = 1):
        """同步入口。"""

        return asyncio.run(self.start(register_num))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="OpenAI 注册脚本")
    parser.add_argument("--config", default="config.toml", help="配置文件路径")
    parser.add_argument("--count", type=int, default=2, help="注册数量")
    args = parser.parse_args()

    OpenAIRegister.from_config_file(args.config).start_sync(args.count)
