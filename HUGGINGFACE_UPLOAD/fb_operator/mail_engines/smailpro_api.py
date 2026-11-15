# -*- coding: utf-8 -*-
"""
SmailPro & Sonjj API Client (Reverse-Engineered Enterprise Edition)
------------------------------------------------------------------
Supported Services:
- Real Google Gmail (@gmail.com)
- Real Microsoft Outlook & Hotmail (@outlook.com, @hotmail.com)
- University & Student Domains (@singapore.edu.pl, @paris.edu.pl, @france.edu.pl)
- 16 Managed Long-Lived Domains (@devpoet.com, @magim.be, etc.)

Features:
- Self-Healing Auto-Refresh JWT Token on HTTP 401
- Intelligent Sonjj Endpoint Routing (temp_gmail vs temp_outlook vs temp_email)
- Two-Step Deep Message & Body Extraction (/app/message -> /v1/.../message)
- Built-in DNS Resilience (Cloudflare edge IPv4 fallback to prevent Windows getaddrinfo 11002)
- Automated OTP & Verification Link Extraction
"""
from __future__ import annotations

import re
import json
import time
import socket
import requests
from typing import Any, Optional

try:
    from fb_operator.mail_engines.smailpro_credentials import get_smailpro_cookie
except ImportError:
    try:
        from api.smailpro_credentials import get_smailpro_cookie
    except ImportError:
        try:
            from smailpro_credentials import get_smailpro_cookie
        except ImportError:
            def get_smailpro_cookie(custom_path=None):
                return ""

# DNS resilience for api.sonjj.com (Cloudflare edge IPs)
SONJJ_IPS = ["104.26.10.66", "104.26.11.66", "172.67.68.39"]
_orig_getaddrinfo = socket.getaddrinfo

def _resilient_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    try:
        return _orig_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)
    except Exception:
        if host == "api.sonjj.com":
            return _orig_getaddrinfo(SONJJ_IPS[0], port, socket.AF_INET, type, proto, flags)
        raise

socket.getaddrinfo = _resilient_getaddrinfo


class SmailProAPI:
    """Enterprise API Client for SmailPro & Sonjj Temporary Email Service."""

    BASE_URL = "https://smailpro.com"
    API_SONJJ_URL = "https://api.sonjj.com"

    DOMAINS_GMAIL = ["gmail.com", "googlemail.com"]
    DOMAINS_MICROSOFT = ["outlook.com", "hotmail.com"]
    DOMAINS_EDU = [
        "singapore.edu.pl",
        "paris.edu.pl",
        "france.edu.pl"
    ]
    DOMAINS_MANAGED = [
        "devpoet.com",
        "fordemy.com",
        "appbott.com",
        "animoby.com",
        "meltcoo.com",
        "bussaco.com",
        "hastana.com",
        "fenfax.com",
        "jewby.com",
        "bogchi.com",
        "devmant.com",
        "brajraj.org",
        "comproa.org",
        "damphen.org",
        "momroad.org",
        "magim.be"
    ]

    ALL_DOMAINS = DOMAINS_GMAIL + DOMAINS_MICROSOFT + DOMAINS_EDU + DOMAINS_MANAGED

    def __init__(self, cookie: str = None, timeout: int = 15):
        self.cookie = cookie or get_smailpro_cookie()
        self.timeout = timeout
        self.session = requests.Session()
        self._update_session_headers()

    def _update_session_headers(self):
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
            "Referer": f"{self.BASE_URL}/temporary-email",
            "Cookie": self.cookie,
            "Accept": "application/json, text/plain, */*"
        })

    def set_cookie(self, cookie: str):
        """Update cookie at runtime."""
        self.cookie = cookie.strip()
        self._update_session_headers()

    @classmethod
    def get_domains_catalog(cls) -> dict[str, list[str]]:
        """Returns all supported domain categories."""
        return {
            "gmail": list(cls.DOMAINS_GMAIL),
            "microsoft": list(cls.DOMAINS_MICROSOFT),
            "edu": list(cls.DOMAINS_EDU),
            "managed": list(cls.DOMAINS_MANAGED),
            "all": list(cls.ALL_DOMAINS)
        }

    def create_mailbox(self, domain: str = "gmail.com", username: str = "random") -> dict[str, Any]:
        """
        Creates a new temporary mailbox.
        - For gmail.com and outlook.com/hotmail.com: Free tier requires username='random'.
        - For .edu.pl and managed domains: Custom usernames are supported!
        """
        domain = domain.lower().strip()
        if domain not in self.ALL_DOMAINS:
            domain = "gmail.com"

        if domain in self.DOMAINS_GMAIL or domain in self.DOMAINS_MICROSOFT:
            username = "random"
        else:
            if not username or username == "random":
                username = "random"
            else:
                username = re.sub(r"[^a-zA-Z0-9._-]", "", username.lower())
                if not username:
                    username = "random"

        url = f"{self.BASE_URL}/app/create"
        params = {
            "username": username,
            "type": "alias",
            "domain": domain,
            "server": 1
        }

        try:
            resp = self.session.get(url, params=params, timeout=self.timeout)
            if resp.status_code == 200:
                data = resp.json()
                address = data.get("address")
                timestamp = data.get("timestamp")
                key = data.get("key")

                if address and key:
                    jwt_payload = self.get_inbox_payload(address, timestamp, key)
                    return {
                        "success": True,
                        "address": address,
                        "domain": domain,
                        "timestamp": timestamp,
                        "key": key,
                        "jwt_payload": jwt_payload or "",
                        "provider": "smailpro",
                        "created_at": time.time(),
                        "error": None
                    }
                else:
                    return {
                        "success": False,
                        "address": None,
                        "domain": domain,
                        "error": f"Invalid server response: {data}"
                    }
            elif resp.status_code in [401, 403]:
                return {
                    "success": False,
                    "address": None,
                    "domain": domain,
                    "error": "SmailPro cookie/session expired. Please update smailpro_cookie.txt."
                }
            else:
                return {
                    "success": False,
                    "address": None,
                    "domain": domain,
                    "error": f"HTTP {resp.status_code}: {resp.text[:200]}"
                }
        except Exception as e:
            return {
                "success": False,
                "address": None,
                "domain": domain,
                "error": f"Network exception: {str(e)}"
            }

    def get_inbox_payload(self, address: str, timestamp: int, key: str) -> Optional[str]:
        """
        Calls /app/inbox to exchange address/timestamp/key for the Sonjj JWT payload.
        """
        url = f"{self.BASE_URL}/app/inbox"
        payload = [{
            "address": address,
            "timestamp": timestamp,
            "key": key
        }]

        headers = {"Content-Type": "application/json"}
        try:
            resp = self.session.post(url, json=payload, headers=headers, timeout=self.timeout)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list) and len(data) > 0:
                    return data[0].get("payload")
        except Exception:
            pass
        return None

    def get_messages(self, mailbox_data: dict[str, Any]) -> list[dict[str, Any]]:
        """
        Fetches incoming messages for a mailbox.
        Auto-refreshes JWT payload if expired (HTTP 401).
        """
        address = mailbox_data.get("address") or ""
        domain = mailbox_data.get("domain") or (address.split("@")[-1] if "@" in address else "gmail.com")
        jwt_payload = mailbox_data.get("jwt_payload")
        timestamp = mailbox_data.get("timestamp", int(time.time()))
        key = mailbox_data.get("key")

        if not jwt_payload and address and key:
            jwt_payload = self.get_inbox_payload(address, timestamp, key)
            mailbox_data["jwt_payload"] = jwt_payload

        if not jwt_payload:
            return []

        if domain in self.DOMAINS_GMAIL:
            endpoint_name = "temp_gmail"
        elif domain in self.DOMAINS_MICROSOFT:
            endpoint_name = "temp_outlook"
        else:
            endpoint_name = "temp_email"

        url = f"{self.API_SONJJ_URL}/v1/{endpoint_name}/inbox"
        sonjj_headers = {
            "referer": f"{self.BASE_URL}/",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
        }

        try:
            resp = requests.get(url, params={"payload": jwt_payload}, headers=sonjj_headers, timeout=self.timeout)

            # Auto-refresh JWT payload if expired
            if resp.status_code == 401 and address and key:
                fresh_payload = self.get_inbox_payload(address, timestamp, key)
                if fresh_payload and fresh_payload != jwt_payload:
                    jwt_payload = fresh_payload
                    mailbox_data["jwt_payload"] = fresh_payload
                    resp = requests.get(url, params={"payload": jwt_payload}, headers=sonjj_headers, timeout=self.timeout)

            if resp.status_code == 200:
                data = resp.json()
                raw_messages = data.get("messages", [])
                formatted_messages = []

                for msg in raw_messages:
                    mid = str(msg.get("mid") or msg.get("id") or "")
                    subject = str(msg.get("textSubject") or msg.get("subject") or "")
                    sender = str(msg.get("textFrom") or msg.get("from") or "Unknown")
                    recipient = str(msg.get("textTo") or msg.get("to") or address)
                    date_str = str(msg.get("textDate") or msg.get("date") or "")
                    body = str(msg.get("body") or msg.get("text") or msg.get("html") or "")

                    # Two-step retrieval if body is empty
                    if not body and mid and address:
                        body = self.fetch_message_body(address, mid, endpoint_name)

                    combined_text = f"{subject} {body}"
                    otp_code = self.extract_otp(combined_text)
                    action_link = self.extract_action_link(body or subject)

                    formatted_messages.append({
                        "id": mid,
                        "mid": mid,
                        "subject": subject,
                        "sender": sender,
                        "from": sender,
                        "recipient": recipient,
                        "to": recipient,
                        "date": date_str,
                        "body": body,
                        "otp": otp_code,
                        "action_link": action_link,
                        "raw": msg
                    })

                return formatted_messages
        except Exception:
            pass

        return []

    def fetch_message_body(self, address: str, mid: str, endpoint_name: str) -> str:
        """
        Executes the two-step message body retrieval with automatic retries:
        1. /app/message?email=...&mid=... -> returns message payload JWT
        2. api.sonjj.com/v1/{endpoint_name}/message?payload=... -> returns body JSON
        """
        for attempt in range(3):
            try:
                r1 = self.session.get(f"{self.BASE_URL}/app/message", params={"email": address, "mid": mid}, timeout=self.timeout)
                if r1.status_code == 200:
                    msg_payload = r1.text.strip().strip('"')
                    if msg_payload and not msg_payload.startswith("{"):
                        sonjj_headers = {
                            "referer": f"{self.BASE_URL}/",
                            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                        }
                        r2 = requests.get(f"{self.API_SONJJ_URL}/v1/{endpoint_name}/message", params={"payload": msg_payload}, headers=sonjj_headers, timeout=self.timeout)
                        if r2.status_code == 200:
                            data = r2.json()
                            body = data.get("body") or data.get("text") or data.get("html") or ""
                            if body:
                                return body
                time.sleep(1)
            except Exception:
                time.sleep(1)
        return ""

    @staticmethod
    def extract_otp(text: str) -> Optional[str]:
        if not text:
            return None
        clean_text = re.sub(r"<style\b[^>]*>.*?</style>", "", text, flags=re.DOTALL)
        clean_text = re.sub(r"<script\b[^>]*>.*?</script>", "", clean_text, flags=re.DOTALL)
        clean_text = re.sub(r"<[^>]+>", " ", clean_text)

        patterns = [
            r"(?:code|otp|رمز|كود|verification|pin|secret|passcode|confirmation|المصادقة)[^\d\n\r]{0,30}(\b\d{4,8}\b)",
            r"(\b\d{6}\b)",
            r"(\b\d{4,5}\b)",
            r"(\b\d{7,8}\b)"
        ]
        for pat in patterns:
            match = re.search(pat, clean_text, re.IGNORECASE)
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
