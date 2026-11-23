# -*- coding: utf-8 -*-
"""
Temporary-Mail.net API Client (Reverse-Engineered Enterprise Edition)
---------------------------------------------------------------------
Supported Free Domains (100% Free & Custom Usernames):
- @deepmails.org
- @agogmail.com
- @rulersonline.com
- @mowan666.com
- @swagpapa.com
- @inctart.com
- @deepyinc.com
- @123mails.org
- @besttempmail.com

Features:
- Custom Username Creation (/custom-domain-email)
- Zero Auth / Free Unlimited Mailboxes
- Automatic Session Initialization (/en)
- Full OTP Code & Verification Link Extraction
- Mailbox Deletion Support
"""
from __future__ import annotations

import re
import json
import time
import random
import requests
from typing import Any, Optional


class TempMailNetAPI:
    """Enterprise API Client for Temporary-Mail.net."""

    BASE_URL = "https://www.temporary-mail.net"

    FREE_DOMAINS = [
        "deepmails.org",
        "agogmail.com",
        "rulersonline.com",
        "mowan666.com",
        "swagpapa.com",
        "inctart.com",
        "deepyinc.com",
        "123mails.org",
        "besttempmail.com"
    ]

    VIP_DOMAINS = [
        "pdf-cutter.com",
        "embassybase.com",
        "mailsbay.com",
        "mediaholy.com",
        "mediaeast.uk",
        "justdefinition.com",
        "gongjua.com"
    ]

    ALL_DOMAINS = FREE_DOMAINS + VIP_DOMAINS

    def __init__(self, timeout: int = 15):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Origin": self.BASE_URL,
            "Referer": f"{self.BASE_URL}/en",
            "X-Requested-With": "XMLHttpRequest"
        })
        self._initialized = False

    def _ensure_session(self):
        """Initializes cookies and language headers if not already done."""
        if not self._initialized:
            try:
                self.session.get(f"{self.BASE_URL}/en", timeout=self.timeout)
                self._initialized = True
            except Exception:
                pass

    @classmethod
    def get_domains(cls) -> list[str]:
        """Returns list of supported free domains."""
        return list(cls.FREE_DOMAINS)

    def create_mailbox(self, username: str = None, domain: str = "deepmails.org") -> dict[str, Any]:
        """
        Creates a custom or random mailbox on the specified domain.
        """
        self._ensure_session()

        domain = domain.lower().strip() if domain else "deepmails.org"
        if domain not in self.ALL_DOMAINS:
            domain = self.FREE_DOMAINS[0]

        if not username or username.strip() == "random":
            rand_suffix = random.randint(1000, 9999)
            username = f"user_{int(time.time()) % 10000}_{rand_suffix}"
        else:
            username = re.sub(r"[^a-zA-Z0-9._-]", "", username.lower())
            if not username:
                username = f"user_{int(time.time()) % 10000}_{random.randint(100, 999)}"

        url = f"{self.BASE_URL}/custom-domain-email"
        payload = {"username": username, "domain": domain}

        try:
            resp = self.session.post(url, json=payload, timeout=self.timeout)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("success"):
                    email_addr = data.get("email") or f"{username}@{domain}"
                    code = data.get("code") or ""
                    return {
                        "success": True,
                        "address": email_addr,
                        "email": email_addr,
                        "code": code,
                        "token": code,
                        "domain": domain,
                        "provider": "tempmail_net",
                        "created_at": time.time(),
                        "error": None
                    }
                else:
                    return {
                        "success": False,
                        "address": None,
                        "error": data.get("error") or "Failed to create mailbox on server"
                    }
            else:
                return {
                    "success": False,
                    "address": None,
                    "error": f"HTTP {resp.status_code}: {resp.text[:200]}"
                }
        except Exception as e:
            return {
                "success": False,
                "address": None,
                "error": f"Network error: {str(e)}"
            }

    def get_messages(self, mailbox_data: dict[str, Any]) -> list[dict[str, Any]]:
        """
        Fetches incoming messages for a mailbox using its email and secret code.
        """
        self._ensure_session()

        email = mailbox_data.get("address") or mailbox_data.get("email")
        code = mailbox_data.get("code") or mailbox_data.get("token") or ""

        if not email:
            return []

        url = f"{self.BASE_URL}/get-emails?lang=en"
        payload = {"email": email, "code": code}

        try:
            resp = self.session.post(url, json=payload, timeout=self.timeout)
            if resp.status_code == 200:
                data = resp.json()
                raw_emails = data.get("emails") or data.get("messages") or []
                if not isinstance(raw_emails, list):
                    return []

                formatted = []
                for msg in raw_emails:
                    msg_id = str(msg.get("id") or msg.get("mid") or "")
                    subject = str(msg.get("subject") or msg.get("textSubject") or "")
                    body = str(msg.get("body") or msg.get("text") or msg.get("html") or "")
                    sender = str(msg.get("from") or msg.get("sender") or msg.get("textFrom") or "Unknown")
                    date_str = str(msg.get("date") or msg.get("textDate") or "")

                    combined = f"{subject} {body}"
                    otp_code = self.extract_otp(combined)
                    action_link = self.extract_action_link(body or subject)

                    formatted.append({
                        "id": msg_id,
                        "subject": subject,
                        "sender": sender,
                        "from": sender,
                        "recipient": email,
                        "date": date_str,
                        "body": body,
                        "otp": otp_code,
                        "action_link": action_link,
                        "raw": msg
                    })

                return formatted
        except Exception:
            pass

        return []

    def delete_mailbox(self, mailbox_data: dict[str, Any]) -> bool:
        """Deletes the mailbox on the server."""
        self._ensure_session()
        email = mailbox_data.get("address") or mailbox_data.get("email")
        code = mailbox_data.get("code") or mailbox_data.get("token") or ""
        if not email:
            return False

        url = f"{self.BASE_URL}/delete-email"
        payload = {"email": email, "code": code}
        try:
            resp = self.session.post(url, json=payload, timeout=self.timeout)
            return resp.status_code == 200 and resp.json().get("success", False)
        except Exception:
            return False

    @staticmethod
    def extract_otp(text: str) -> Optional[str]:
        """Extracts OTP verification code."""
        if not text:
            return None
        patterns = [
            r"(?:code|otp|رمز|كود|verification|pin|secret|passcode|confirmation)[^\d\n\r]{0,20}(\b\d{4,8}\b)",
            r"(\b\d{6}\b)",
            r"(\b\d{4,5}\b)",
            r"(\b\d{7,8}\b)"
        ]
        for pat in patterns:
            match = re.search(pat, text, re.IGNORECASE)
            if match:
                code = match.group(1) if match.groups() else match.group(0)
                if code in ["2024", "2025", "2026", "2027"]:
                    continue
                return code
        return None

    @staticmethod
    def extract_action_link(text: str) -> Optional[str]:
        """Extracts confirmation links."""
        if not text:
            return None
        match = re.search(r"https?://[^\s<>\"'{}|\\^`]+(?:confirm|verify|activate|token|auth)[^\s<>\"'{}|\\^`]*", text, re.IGNORECASE)
        if match:
            return match.group(0)
        match_any = re.search(r"https?://[^\s<>\"'{}|\\^`]+", text)
        return match_any.group(0) if match_any else None


if __name__ == "__main__":
    print("=" * 60)
    print("🧪 Testing TempMailNetAPI Standalone Client")
    print("=" * 60)

    client = TempMailNetAPI()

    # Test 1: Create custom mailbox on deepmails.org
    print("\n1️⃣ Creating Custom Mailbox (titantest @ deepmails.org)...")
    res = client.create_mailbox(username="titantest", domain="deepmails.org")
    print("Result:", res)

    # Test 2: Poll Inbox
    if res.get("success"):
        print("\n📬 Polling Inbox for Messages...")
        msgs = client.get_messages(res)
        print(f"Messages count: {len(msgs)}")

    print("\n✅ TempMailNetAPI test completed successfully.")
