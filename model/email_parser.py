import re
from typing import Optional
import asyncio
from loguru import logger
from imap_tools import MailBox
from datetime import datetime, timedelta
import pytz
import time


class SyncEmailChecker:
    def __init__(self, email: str, password: str):
        self.email = email
        self.password = password
        self.imap_server = self._get_imap_server(email)
        self.search_start_time = datetime.now(pytz.UTC)

    def _get_imap_server(self, email: str) -> str:
        """Returns the IMAP server based on the email domain."""
        if email.endswith("@rambler.ru"):
            return "imap.rambler.ru"
        elif email.endswith("@gmail.com"):
            return "imap.gmail.com"
        elif "@gmx." in email:
            return "imap.gmx.com"
        elif "outlook" in email:
            return "imap-mail.outlook.com"
        elif email.endswith("@mail.ru"):
            return "imap.mail.ru"
        else:
            return "imap.firstmail.ltd"

    def print_all_messages(self) -> None:
        """Prints all messages in the mailbox"""
        logger.info(f"Account: {self.email} | Printing all messages...")
        try:
            with MailBox(self.imap_server).login(self.email, self.password) as mailbox:
                for msg in mailbox.fetch():
                    print("\n" + "=" * 50)
                    print(f"From: {msg.from_}")
                    print(f"To: {msg.to}")
                    print(f"Subject: {msg.subject}")
                    print(f"Date: {msg.date}")
                    print("\nBody:")
                    print(msg.text or msg.html)
        except Exception as error:
            logger.error(f"Account: {self.email} | Failed to fetch messages: {error}")

    def check_if_email_valid(self) -> bool:
        try:
            with MailBox(self.imap_server).login(self.email, self.password):
                return True
        except Exception as error:
            logger.error(f"Account: {self.email} | Email is invalid (IMAP): {error}")
            return False

    def _search_for_code(self, mailbox: MailBox) -> Optional[str]:
        """Searches for verification code in mailbox"""
        time_threshold = self.search_start_time - timedelta(seconds=60)

        messages = sorted(
            mailbox.fetch(),
            key=lambda x: (
                x.date.replace(tzinfo=pytz.UTC) if x.date.tzinfo is None else x.date
            ),
            reverse=True,
        )

        for msg in messages:
            msg_date = (
                msg.date.replace(tzinfo=pytz.UTC)
                if msg.date.tzinfo is None
                else msg.date
            )

            if msg_date < time_threshold:
                continue

            body = msg.text or msg.html
            if not body:
                continue

            matches = re.findall(r"\b\d{6}\b", body)
            if matches:
                return matches[0]

        return None

    def _search_for_code_in_spam(
        self, mailbox: MailBox, spam_folder: str
    ) -> Optional[str]:
        """Searches for verification code in spam folder"""
        if mailbox.folder.exists(spam_folder):
            mailbox.folder.set(spam_folder)
            return self._search_for_code(mailbox)
        return None

    def check_email_for_code(
        self, max_attempts: int = 20, delay_seconds: int = 3
    ) -> Optional[str]:
        try:
            # Check inbox
            for attempt in range(max_attempts):
                with MailBox(self.imap_server).login(
                    self.email, self.password
                ) as mailbox:
                    code = self._search_for_code(mailbox)
                    if code:
                        return code
                if attempt < max_attempts - 1:
                    time.sleep(delay_seconds)

            # Check spam folders
            logger.warning(
                f"Account: {self.email} | Code not found after {max_attempts} attempts, searching in spam folder..."
            )
            spam_folders = ("SPAM", "Spam", "spam", "Junk", "junk", "Spamverdacht")

            with MailBox(self.imap_server).login(self.email, self.password) as mailbox:
                for spam_folder in spam_folders:
                    code = self._search_for_code_in_spam(mailbox, spam_folder)
                    if code:
                        logger.success(
                            f"Account: {self.email} | Found code in spam: {code}"
                        )
                        return code

            logger.error(f"Account: {self.email} | Code not found in any folder")
            return None

        except Exception as error:
            logger.error(
                f"Account: {self.email} | Failed to check email for code: {error}"
            )
            return None
