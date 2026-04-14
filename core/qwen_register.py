import asyncio
import argparse
import base64
import hashlib
import html
import json
import re
import secrets
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from pydoll.browser import Chrome
from pydoll.browser.options import ChromiumOptions
from pydoll.browser.tab import Tab

from service.base_mail_service import BaseMailService, Mail, MailBox
from service.config_service import ConfigService, QwenRegisterConfig
from service.cpa_service import CpaService
from service.http_service import HttpService
from service.mail import mail_factory
from util import pydoll_util, account_util
from util.account_util import Account
from util.logger import get_logger

LOGGER = get_logger("Qwen Register")

_VERIFY_LINK_REGEX = re.compile(r'href\s*=\s*["\'](https://chat\.qwen\.ai/api/v1/auths/activate[^"\']*)["\']')


class QwenRegister:
    def __init__(self, config: QwenRegisterConfig, mail_provider: BaseMailService, http_service: HttpService, cpa_service: CpaService):
        self._config = config
        self._mail_provider = mail_provider
        self._http_service = http_service
        self._cpa_service = cpa_service

    @classmethod
    def from_config_file(cls, config_file: str | Path = "config.toml") -> "QwenRegister":
        """通过配置文件实例化注册机。"""
        app_config = ConfigService.load(config_file)
        http_service = HttpService(app_config.http)
        mail_provider = mail_factory.create_mail_service(app_config, app_config.qwen_register.mail_provider, http_service=http_service)
        cpa_service = CpaService(app_config.cpa, http_service) if app_config.qwen_register.upload_cpa_auth_file else None

        return cls(
            config=app_config.qwen_register,
            mail_provider=mail_provider,
            http_service=http_service,
            cpa_service=cpa_service
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

    async def _wait_for_verify_link(self, mail_box: MailBox, received_after: str, timeout_sec: int = 60) -> str:
        """轮询 MailService 获取验证链接。"""
        deadline = time.time() + timeout_sec + 5
        LOGGER.info(f"开始轮询验证链接 => 5s 间隔，{timeout_sec}s 超时")

        def mail_filter(mail: Mail) -> bool:
            if not mail.sender or "qwen" not in mail.sender:
                return False
            if (not mail.receive_at) or mail.receive_at < received_after:
                return False
            if not mail.subject or "qwen" not in mail.subject:
                return False
            return True

        last_error: Exception | None = None
        while time.time() < deadline:
            try:
                mails = self._mail_provider.get_latest_emails(mail_box, mail_filter=mail_filter)
                if mails:
                    for mail in mails:
                        if mail.content:
                            match = _VERIFY_LINK_REGEX.search(mail.content)
                            if match:
                                verify_link = match.group(1)
                                return html.unescape(verify_link)
                LOGGER.debug(f"未获取验证链接")
            except Exception as exc:
                LOGGER.warning(f"获取验证链接失败: {str(exc)[:200]}")
                last_error = exc
            await asyncio.sleep(5)

        if last_error is not None:
            LOGGER.warning(f"等待验证链接超时，最后一次错误: {last_error}")
        return ""

    async def _wait_for_verify_link_resend_if_needed(self, tab: Tab, mail_box: MailBox, received_after: str) -> str:
        btn_resend = await tab.query("//button[contains(., '重新发送邮件')]", timeout=10, raise_exc=False)
        if btn_resend:
            await btn_resend.wait_until(is_visible=True, is_interactable=True, timeout=65)
            await btn_resend.click(humanize=True)
        verify_link = await self._wait_for_verify_link(mail_box, received_after, self._config.email_timeout_seconds)
        if not verify_link:
            for i in range(self._config.email_retries):
                btn_resend = await tab.query("//button[contains(., '重新发送邮件')]", timeout=10, raise_exc=False)
                if btn_resend:
                    await btn_resend.wait_until(is_visible=True, is_interactable=True, timeout=65)
                    LOGGER.info(f"等待验证链接超时，将尝试第 {i + 1} 次重新获取验证链接")
                    LOGGER.info("点击重新发送验证链接")
                    await btn_resend.click(humanize=True)
                    verify_link = await self._wait_for_verify_link(mail_box, received_after, self._config.email_timeout_seconds)
                    if verify_link:
                        break
        return verify_link

    async def _start_register(self, tab: Tab) -> Account:
        """注册 QwenAI 账号"""
        LOGGER.info("访问注册页面 https://chat.qwen.ai/auth?mode=register")
        await tab.go_to("https://chat.qwen.ai/auth?mode=register", timeout=self._config.default_timeout_seconds)

        username_input = await tab.query("//input[@name='username']", timeout=self._config.default_timeout_seconds)
        await username_input.wait_until(is_visible=True, is_interactable=True, timeout=10)
        email_input = await tab.query("//input[@name='email']", timeout=self._config.default_timeout_seconds)
        await email_input.wait_until(is_visible=True, is_interactable=True, timeout=10)
        password_input = await tab.query("//input[@name='password']", timeout=self._config.default_timeout_seconds)
        await password_input.wait_until(is_visible=True, is_interactable=True, timeout=10)
        check_password_input = await tab.query("//input[@name='checkPassword']", timeout=self._config.default_timeout_seconds)
        await check_password_input.wait_until(is_visible=True, is_interactable=True, timeout=10)
        agree_checkbox = await tab.query("//input[@type='checkbox']", timeout=self._config.default_timeout_seconds)
        await agree_checkbox.wait_until(is_visible=True, is_interactable=True, timeout=10)

        submit_button = await tab.query("//button[@type='submit']", timeout=self._config.default_timeout_seconds)

        mailbox = self._mail_provider.generate_mail_box()
        account = account_util.create_new_account(mailbox)
        if self._config.default_account_password:
            account.password = self._config.default_account_password
        LOGGER.info(
            f"生成账号 => email={account.email}, username={account.username}, password={account.password}, birthday={'-'.join(account.birthday)}"
        )
        LOGGER.info(f"输入用户名：{account.username}")
        await pydoll_util.ensure_input(tab, "//input[@name='username']", account.username)
        LOGGER.info(f"输入邮箱：{account.email}")
        await pydoll_util.ensure_input(tab, "//input[@name='email']", account.email)
        LOGGER.info(f"输入密码：{account.password}")
        await pydoll_util.ensure_input(tab, "//input[@name='password']", account.password)
        LOGGER.info(f"输入确认密码：{account.password}")
        await pydoll_util.ensure_input(tab, "//input[@name='checkPassword']", account.password)
        LOGGER.info(f"勾选同意条款")
        await agree_checkbox.click(humanize=True)

        await submit_button.wait_until(is_visible=True, is_interactable=True, timeout=10)
        LOGGER.info("点击注册按钮")
        received_after = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        await submit_button.click(humanize=True)

        btn_logout = await tab.query("//button[@class='account-pending-desktop-button-cancel']", timeout=self._config.default_timeout_seconds)
        await btn_logout.wait_until(is_visible=True, is_interactable=True, timeout=10)

        LOGGER.info("等待验证链接")
        verify_link = await self._wait_for_verify_link_resend_if_needed(tab, mailbox, received_after)
        if not verify_link:
            raise RuntimeError("Unable to obtain QwenAI verification link")
        LOGGER.info(f"访问验证链接 {verify_link}")
        await tab.go_to(verify_link, self._config.default_timeout_seconds)
        await tab.query(f"//div[contains(., '{account.username}')]", timeout=self._config.default_timeout_seconds)
        LOGGER.info("账号注册成功")
        return account

    async def _get_device_code(self, tab: Tab, challenge: str) -> dict[str, str]:
        data = {
            "client_id": self._config.oauth_client_id,
            "scope": "openid profile email model.completion",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
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
        response = await tab.request.post("https://chat.qwen.ai/api/v1/oauth2/device/code", data=data, headers=headers)
        response.raise_for_status()
        return response.json()

    @staticmethod
    async def _do_authorize(tab: Tab, user_code: str, verification_uri_complete: str):
        data = {
            "approved": True,
            "user_code": user_code
        }
        headers = [
            {
                "name": "Content-Type",
                "value": "application/json",
            },
            {
                "name": "Referer",
                "value": verification_uri_complete,
            },
        ]
        response = await tab.request.post("https://chat.qwen.ai/api/v2/oauth2/authorize", json=data, headers=headers)
        response.raise_for_status()
        return response.json()

    async def _get_oauth_token(self, tab: Tab, device_code: str, verifier: str) -> dict[str, Any]:
        data = {
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            "client_id": self._config.oauth_client_id,
            "device_code": device_code,
            "code_verifier": verifier,
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
        response = await tab.request.post("https://chat.qwen.ai/api/v1/oauth2/token", data=data, headers=headers)
        response.raise_for_status()
        return response.json()

    async def _start_oauth(self, tab: Tab, account: Account) -> dict[str, Any] | None:
        LOGGER.info("开始 OAuth 登录流程")
        verifier = secrets.token_urlsafe(64)
        sha256_raw = hashlib.sha256(verifier.encode("ascii")).digest()
        challenge = base64.urlsafe_b64encode(sha256_raw).decode("ascii").rstrip("=")
        LOGGER.info("获取设备授权信息")
        device_resp = await self._get_device_code(tab, challenge)
        LOGGER.info(f"设备授权信息: \n{json.dumps(device_resp, indent=2, ensure_ascii=False)}")
        LOGGER.info("等待授权")
        await self._do_authorize(tab, device_resp["user_code"], device_resp["verification_uri_complete"])
        LOGGER.info("获取授权令牌")
        token = await self._get_oauth_token(tab, device_resp["device_code"], verifier)
        return token if token and "access_token" in token else None

    def _save_auth_file_to_local(self, file_name: str, raw_json: str) -> Path:
        """先将授权文件保存到本地目录。"""

        account_file_dir = self._config.auth_file_dir
        account_file_dir.mkdir(parents=True, exist_ok=True)

        file_path = account_file_dir / file_name
        file_path.write_text(f"{raw_json}\n", encoding="utf-8")
        return file_path

    async def start(self, register_num: int = 1):
        for i in range(register_num):
            LOGGER.info(f"{'*' * 50} 开始第 {i + 1} / {register_num} 个注册流程 {'*' * 50}")
            async with Chrome(options=self._build_chrome_options()) as browser:
                account: Account | None = None
                tab: Tab | None = None
                try:
                    tab = await browser.start()
                    account = await self._start_register(tab)
                    token = await self._start_oauth(tab, account)
                    if not token:
                        raise RuntimeError("Unable to obtain QwenAI OAuth token")

                    now = int(time.time())
                    expires_in = int(token["expires_in"])
                    auth_file_body: dict[str, Any] = {
                        "type": "qwen",
                        "email": account.email,
                        "access_token": token["access_token"],
                        "refresh_token": token["refresh_token"],
                        "last_refresh": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
                        "resource_url": token["resource_url"],
                        "expired": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now + max(expires_in, 0)))
                    }
                    raw_auth_file = json.dumps(auth_file_body, indent=2, ensure_ascii=False)
                    LOGGER.success(f"注册成功\n{raw_auth_file}")
                    file_name = f"qwen-{account.email}.json"
                    local_file = self._save_auth_file_to_local(file_name, raw_auth_file)
                    LOGGER.success(f"账号已保存到本地：{local_file}")
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

    def start_sync(self, register_num: int = 1):
        """同步入口。"""

        return asyncio.run(self.start(register_num))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Qwen 注册脚本")
    parser.add_argument("--config", default="config.toml", help="配置文件路径")
    parser.add_argument("--count", type=int, default=9, help="注册数量")
    args = parser.parse_args()

    QwenRegister.from_config_file(args.config).start_sync(args.count)
