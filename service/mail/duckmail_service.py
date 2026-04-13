import re

from service.base_mail_service import Mail, MailFilter, BaseMailService, MailBox
from service.config_service import DuckMailConfig
from service.http_service import HttpService
from service.mail.gmail_service import GmailService


class DuckMailService(BaseMailService):
    """DuckMail 服务封装。"""

    def __init__(self, config: DuckMailConfig, http_service: HttpService, gmail_service: GmailService):
        self._config = config
        self._gmail_service = gmail_service
        self._http_service = http_service
        self._headers = {
            "authorization": f"Bearer {self._config.authorization_token}",
            "referer": "https://duckduckgo.com/"
        }

    def generate_mail_box(self) -> MailBox:
        """生成新的临时邮箱。"""
        resp = self._http_service.post(url=f"{self._config.base_url}/api/email/addresses", headers=self._headers)
        if resp.status_code != 201:
            raise RuntimeError(f"获取 DuckMail 私有邮箱失败: {resp.status_code}")
        email_addr = resp.json().get("address", "")
        if not email_addr:
            raise RuntimeError(f"获取 DuckMail 私有邮箱失败: {resp.text}")
        return MailBox(email=f"{email_addr}@duck.com")

    # def get_latest_verification_code(self, mail_box: MailBox, mail_filter: MailFilter | None = None, verification_code_regex: re.Pattern | None = None) -> str:
    #     return self._gmail_service.get_target_mailbox_latest_verification_code(self._config.forward_gmail, mail_box, mail_filter=mail_filter,
    #                                                                            verification_code_regex=verification_code_regex)

    def get_latest_emails(self, mail_box: MailBox, mail_filter: MailFilter | None = None, verification_code_regex: re.Pattern | None = None) -> list[Mail]:
        """获取最新邮件。"""
        return self._gmail_service.get_target_mailbox_latest_emails(self._config.forward_gmail, mail_box, mail_filter=mail_filter,
                                                                    verification_code_regex=verification_code_regex)
