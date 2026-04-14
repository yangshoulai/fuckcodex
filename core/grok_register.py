import asyncio
import argparse
import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from pydoll.browser import Chrome
from pydoll.browser.options import ChromiumOptions
from pydoll.browser.tab import Tab

from service.base_mail_service import BaseMailService, Mail, MailBox
from service.config_service import GrokRegisterConfig, ConfigService
from service.http_service import HttpService
from service.mail import mail_factory
from util import pydoll_util, account_util
from util.account_util import Account
from util.logger import get_logger

LOGGER = get_logger("Grok Register")


class GrokRegister:
    def __init__(self, config: GrokRegisterConfig, mail_provider: BaseMailService, http_service: HttpService):
        self._config = config
        self._mail_provider = mail_provider
        self._http_service = http_service

    @classmethod
    def from_config_file(cls, config_file: str | Path = "config.toml") -> "GrokRegister":
        """通过配置文件实例化注册机。"""
        app_config = ConfigService.load(config_file)
        http_service = HttpService(app_config.http)
        mail_provider = mail_factory.create_mail_service(app_config, app_config.grok_register.mail_provider, http_service=http_service)

        return cls(
            config=app_config.grok_register,
            mail_provider=mail_provider,
            http_service=http_service
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

    async def _wait_for_verify_code(self, mail_box: MailBox, received_after: str, timeout_sec: int = 60) -> str:
        """轮询 MailService 获取验证码。"""
        deadline = time.time() + timeout_sec + 5
        LOGGER.info(f"开始轮询验证码 => 5s 间隔，{timeout_sec}s 超时")

        def mail_filter(mail: Mail) -> bool:
            if (not mail.receive_at) or mail.receive_at < received_after:
                return False
            if not mail.subject or "xAI confirmation code" not in mail.subject:
                return False
            return True

        last_error: Exception | None = None
        while time.time() < deadline:
            try:
                code = self._mail_provider.get_latest_verification_code(mail_box, mail_filter=mail_filter,
                                                                        verification_code_regex=re.compile(r"(?<![A-Z0-9])[A-Z0-9]{3}-[A-Z0-9]{3}(?![A-Z0-9])"))
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

    async def _start_register(self, tab: Tab) -> Account:
        """注册 Grok 账号"""

        await tab.go_to("https://accounts.x.ai/sign-up", timeout=self._config.default_timeout_seconds)
        mailbox = self._mail_provider.generate_mail_box()
        account = account_util.create_new_account(mailbox)
        if self._config.default_account_password:
            account.password = self._config.default_account_password
        LOGGER.info(
            f"生成账号 => email={account.email}, username={account.username}, password={account.password}, birthday={'-'.join(account.birthday)}"
        )
        sign_up_with_email_btn = await tab.query(
            "//button[contains(., 'Sign up with email') or contains(., '使用邮箱注册')]", timeout=self._config.default_timeout_seconds)
        await sign_up_with_email_btn.wait_until(is_visible=True, is_interactable=True, timeout=10)
        LOGGER.info("点击 Sign up with email")
        await sign_up_with_email_btn.click(humanize=True)

        email_input = await tab.query("//input[@name='email']", timeout=self._config.default_timeout_seconds)
        await email_input.wait_until(is_visible=True, is_interactable=True, timeout=10)
        LOGGER.info(f"输入邮箱: {account.email}")
        await pydoll_util.ensure_input(tab, "//input[@name='email']", account.email)

        sign_up_btn = await tab.query("//button[@type='submit']", timeout=self._config.default_timeout_seconds)
        await sign_up_btn.wait_until(is_visible=True, is_interactable=True, timeout=2)
        LOGGER.info("点击 Sign up")
        received_after = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        await sign_up_btn.click(humanize=True)

        code_input = await tab.query("//input[@autocomplete='one-time-code']", timeout=self._config.default_timeout_seconds)
        LOGGER.info("等待 xAI 验证码")
        verify_code = await self._wait_for_verify_code(mailbox, received_after, self._config.email_timeout_seconds)
        if not verify_code:
            raise RuntimeError("Unable to obtain xAI verification code")
        LOGGER.info(f"输入验证码: {verify_code}")

        await tab.enable_auto_solve_cloudflare_captcha()
        await code_input.type_text(verify_code)

        given_name_input = await tab.query("//input[@name='givenName']", timeout=self._config.default_timeout_seconds)
        family_name_input = await tab.query("//input[@name='familyName']", timeout=self._config.default_timeout_seconds)
        password_input = await tab.query("//input[@name='password']", timeout=self._config.default_timeout_seconds)

        LOGGER.info(f"输入名: {account.first_name}")
        await given_name_input.wait_until(is_visible=True, is_interactable=True, timeout=10)
        await pydoll_util.ensure_input(tab, "//input[@name='givenName']", account.first_name)

        LOGGER.info(f"输入姓: {account.last_name}")
        await family_name_input.wait_until(is_visible=True, is_interactable=True, timeout=10)
        await pydoll_util.ensure_input(tab, "//input[@name='familyName']", account.last_name)

        LOGGER.info(f"输入密码: {account.password}")
        await password_input.wait_until(is_visible=True, is_interactable=True, timeout=10)

        await tab.enable_auto_solve_cloudflare_captcha()
        await pydoll_util.ensure_input(tab, "//input[@name='password']", account.password)
        await tab.disable_auto_solve_cloudflare_captcha()

        complete_btn = await tab.query("//button[contains(., 'Complete sign up') or contains(., '完成注册')]", timeout=self._config.default_timeout_seconds)
        await complete_btn.wait_until(is_visible=True, is_interactable=True, timeout=10)
        LOGGER.info("点击 Complete sign up")
        await complete_btn.click(humanize=True)
        await tab.disable_auto_solve_cloudflare_captcha()

        await tab.query("//h1[contains(., '接受服务条款')]", timeout=self._config.default_timeout_seconds)
        checkbox_buttons = await tab.query("//button[@role='checkbox' and @type='button']", find_all=True, timeout=self._config.default_timeout_seconds)
        LOGGER.info("同意条款")
        for btn in checkbox_buttons[:2]:
            await btn.wait_until(is_visible=True, is_interactable=True, timeout=10)
            LOGGER.info("勾选协议")
            await btn.click(humanize=True)

        LOGGER.info("点击 Continue")
        continue_btn = await tab.query("//button[contains(., 'Continue') or contains(., '继续')]", timeout=self._config.default_timeout_seconds)
        await continue_btn.wait_until(is_visible=True, is_interactable=True, timeout=10)
        await continue_btn.click(humanize=True)

        LOGGER.info("等待账号管理页")
        await pydoll_util.wait_url(tab, ["/accounts"])
        return account

    @staticmethod
    async def _start_get_sso(tab: Tab, account: Account) -> str:
        sso = await pydoll_util.get_cookie(tab, "sso")
        if not sso:
            raise Exception("Unable to obtain sso cookie")
        return sso

    def _save_auth_file_to_local(self, file_name: str, raw_json: str) -> Path:
        """先将授权文件保存到本地目录。"""

        account_file_dir = self._config.account_file_dir
        account_file_dir.mkdir(parents=True, exist_ok=True)

        file_path = account_file_dir / file_name
        file_path.write_text(f"{raw_json}\n", encoding="utf-8")
        return file_path

    async def start(self, register_num: int = 1):
        sso_list = []
        for i in range(register_num):
            LOGGER.info(f"{'*' * 50} 开始第 {i + 1} / {register_num} 个注册流程 {'*' * 50}")
            async with Chrome(options=self._build_chrome_options()) as browser:
                account: Account | None = None
                tab: Tab | None = None
                try:
                    tab = await browser.start()
                    account = await self._start_register(tab)
                    sso = await self._start_get_sso(tab, account)
                    sso_list.append(sso)
                    account_payload: dict[str, Any] = {
                        "email": account.email,
                        "username": account.username,
                        "password": account.password,
                        "sso": sso,
                        "birthday": "-".join(account.birthday),
                    }
                    raw_auth_file = json.dumps(account_payload, indent=2, ensure_ascii=False)
                    LOGGER.success(f"注册成功\n{raw_auth_file}")
                    file_name = f"{account.email}.json"
                    local_file = self._save_auth_file_to_local(file_name, raw_auth_file)
                    LOGGER.success(f"账号已保存到本地：{local_file}")
                except Exception as exc:
                    LOGGER.error(f"注册失败：{exc}")
                    if not self._config.save_screenshot_on_error:
                        LOGGER.info("配置已关闭异常截图，跳过浏览器截图")
                        continue
                    if tab is None:
                        LOGGER.warning("浏览器标签页尚未初始化，无法截图")
                        continue
                    try:
                        self._config.account_file_dir.mkdir(parents=True, exist_ok=True)
                        screenshot_name = account.email if account else datetime.now().strftime('%Y%m%d%H%M%S')
                        screenshot_file = self._config.account_file_dir / f"screenshot_{screenshot_name}.png"
                        await tab.take_screenshot(screenshot_file, quality=100)
                        LOGGER.info(f"异常截图已保存：{screenshot_file}")
                    except Exception as ex:
                        LOGGER.error(f"截图异常：{ex}")
        if sso_list:
            LOGGER.success(f"已获取 {len(sso_list)} 个 sso，复制下面内容即可导入 Grok2Api\n{'\n'.join(sso_list)}")

    def start_sync(self, register_num: int = 1):
        """同步入口。"""

        return asyncio.run(self.start(register_num))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Grok 注册脚本")
    parser.add_argument("--config", default="config.toml", help="配置文件路径")
    parser.add_argument("--count", type=int, default=2, help="注册数量")
    args = parser.parse_args()

    GrokRegister.from_config_file(args.config).start_sync(args.count)
