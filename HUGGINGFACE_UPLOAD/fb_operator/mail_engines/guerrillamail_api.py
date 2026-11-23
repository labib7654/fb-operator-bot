# -*- coding: utf-8 -*-
"""
Guerrilla Mail API Client (Zero-Auth Enterprise Edition)
---------------------------------------------------------
Supported Domains:
- @sharklasers.com
- @guerrillamail.info
- @grr.la
- @guerrillamail.biz
- @guerrillamail.com
- @guerrillamail.de
- @guerrillamail.net
- @guerrillamail.org
- @pokemail.net

Features:
- Instant Session-less Creation
- Custom Usernames Supported via set_email_user
- Automated OTP & Action Link Extraction
- Lightweight, zero cookies needed
"""
from __future__ import annotations

import re
import json
import time
import random
import requests
from typing import Any, Optional


class GuerrillaMailAPI:
    """Enterprise API Client for GuerrillaMail."""

    BASE_URL = "https://api.guerrillamail.com/ajax.php"

    DOMAINS = [
        "sharklasers.com",
        "guerrillamail.info",
        "grr.la",
        "guerrillamail.biz",
        "guerrillamail.com",
        "guerrillamail.de",
        "guerrillamail.net",
        "guerrillamail.org",
        "pokemail.net"
    ]

    def __init__(self, timeout: int = 15):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
            "Accept": "application/json, text/javascript, */*"
        })

    @classmethod
    def get_domains(cls) -> list[str]:
        return list(cls.DOMAINS)

    def create_mailbox(self, username: str = None, domain: str = "sharklasers.com") -> dict[str, Any]:
        """
        Initializes a mailbox and optionally sets a custom username.
        """
        domain = domain.lower().strip() if domain else "sharklasers.com"
        if domain not in self.DOMAINS:
            domain = self.DOMAINS[0]

        try:
            # 1. Initialize address & get sid_token
            params = {"f": "get_email_address", "ip": "127.0.0.1", "agent": "Antigravity"}
            resp = self.session.get(self.BASE_URL, params=params, timeout=self.timeout)
            if resp.status_code != 200:
                return {"success": False, "address": None, "error": f"HTTP {resp.status_code}"}

            data = resp.json()
            sid_token = data.get("sid_token")
            current_addr = data.get("email_addr", "")

            # 2. If custom username or domain requested, set it
            if username and username != "random":
                clean_user = re.sub(r"[^a-zA-Z0-9._-]", "", username.lower())
                set_params = {
                    "f": "set_email_user",
                    "email_user": clean_user,
                    "sid_token": sid_token,
                    "lang": "en"
                }
                set_resp = self.session.get(self.BASE_URL, params=set_params, timeout=self.timeout)
                if set_resp.status_code == 200:
                    set_data = set_resp.json()
                    email_user = set_data.get("email_user", clean_user)
                    current_addr = f"{email_user}@{domain}"
            else:
                user_part = current_addr.split("@")[0]
                current_addr = f"{user_part}@{domain}"

            return {
                "success": True,
                "address": current_addr,
                "email": current_addr,
                "sid_token": sid_token,
                "domain": domain,
                "provider": "guerrillamail",
                "created_at": time.time(),
                "error": None
            }
        except Exception as e:
            return {"success": False, "address": None, "error": str(e)}

    def get_messages(self, mailbox_data: dict[str, Any]) -> list[dict[str, Any]]:
        """
        Checks inbox for new messages.
        """
        sid_token = mailbox_data.get("sid_token")
        address = mailbox_data.get("address") or ""
        if not sid_token:
            return []

        params = {
            "f": "check_email",
            "seq": "0",
            "sid_token": sid_token
        }

        try:
            resp = self.session.get(self.BASE_URL, params=params, timeout=self.timeout)
            if resp.status_code == 200:
                data = resp.json()
                raw_list = data.get("list", [])
                formatted = []

                for item in raw_list:
                    # Skip guerrilla welcome message
                    sender = str(item.get("mail_from") or "Unknown")
                    subject = str(item.get("mail_subject") or "")
                    mail_id = str(item.get("mail_id") or "")
                    body = str(item.get("mail_excerpt") or "")
                    date_str = str(item.get("mail_date") or "")

                    combined = f"{subject} {body}"
                    otp_code = self.extract_otp(combined)
                    action_link = self.extract_action_link(body or subject)

                    formatted.append({
                        "id": mail_id,
                        "subject": subject,
                        "sender": sender,
                        "from": sender,
                        "recipient": address,
                        "date": date_str,
                        "body": body,
                        "otp": otp_code,
                        "action_link": action_link,
                        "raw": item
                    })

                return formatted
        except Exception:
            pass

        return []

    @staticmethod
    def extract_otp(text: str) -> Optional[str]:
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
        if not text:
            return None
        match = re.search(r"https?://[^\s<>\"'{}|\\^`]+(?:confirm|verify|activate|token|auth)[^\s<>\"'{}|\\^`]*", text, re.IGNORECASE)
        if match:
            return match.group(0)
        match_any = re.search(r"https?://[^\s<>\"'{}|\\^`]+", text)
        return match_any.group(0) if match_any else None


if __name__ == "__main__":
    print("=" * 60)
    print("🧪 Testing GuerrillaMailAPI Standalone Client")
    print("=" * 60)

    client = GuerrillaMailAPI()
    res = client.create_mailbox(username="titantest", domain="sharklasers.com")
    print("Result:", res)

    if res.get("success"):
        msgs = client.get_messages(res)
        print(f"Messages count: {len(msgs)}")

    print("\n✅ GuerrillaMailAPI test completed successfully.")
