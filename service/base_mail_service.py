from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Dict, Any


@dataclass
class MailBox:
    email: str
    extras: Dict[str, Any] | None = None


@dataclass
class Mail:
    sender: str | None
    subject: str | None
    receive_at: str | None
    content: str | None
    verification_code: str | None = None


MailFilter = Callable[[Mail], bool]


_OTP_PATTERN = re.compile(r"(?<!\d)\d{4,8}(?!\d)")


class BaseMailService:

    def generate_mail_box(self) -> MailBox:
        """生成新的临时邮箱。"""
        raise NotImplementedError

    def get_latest_verification_code(self, mail_box: MailBox, mail_filter: MailFilter | None = None, verification_code_regex: re.Pattern | None = None) -> str:
        """通过 Token 获取最新验证码。"""
        messages = self.get_latest_emails(mail_box=mail_box, mail_filter=mail_filter, verification_code_regex=verification_code_regex)
        if messages:
            for mail in messages:
                if mail.verification_code:
                    return mail.verification_code
        return ""

    def get_latest_emails(self, mail_box: MailBox, mail_filter: MailFilter | None = None, verification_code_regex: re.Pattern | None = None) -> list[Mail]:
        """获取最新邮件。"""
        raise NotImplementedError

    @staticmethod
    def extract_verification_code(texts: list[str], pattern: re.Pattern | None = None) -> str | None:
        """从邮件内容中提取验证码。"""
        for text in texts:
            matched = (pattern or _OTP_PATTERN).search(text or "")
            if matched:
                return matched.group(0)
        return None
