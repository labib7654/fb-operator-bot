# -*- coding: utf-8 -*-
"""
محرك البريد المؤقت (Temporary-Mail.net Engine)
-----------------------------------------------
يدعم النطاقات الـ 9 المجانية:
- @deepmails.org
- @agogmail.com
- @rulersonline.com
- @mowan666.com
- @swagpapa.com
- @inctart.com
- @deepyinc.com
- @123mails.org
- @besttempmail.com

مع استخراج رموز التحقق (OTP) وروابط التأكيد فوراً.
"""
from __future__ import annotations

import re
import time
import random
import requests
from typing import Any

class TempMailNetEngine:
    NAME = "tempmail_net"
    BASE_URL = "https://www.temporary-mail.net"

    DOMAINS = [
        # 🆓 النطاقات المجانية المفتوحة 100%
        "deepmails.org",
        "agogmail.com",
        "rulersonline.com",
        "mowan666.com",
        "swagpapa.com",
        "inctart.com",
        "deepyinc.com",
        "123mails.org",
        "besttempmail.com",
        # 💎 نطاقات الـ VIP البريميوم (بقيمة 20 دولار في الموقع - مفتوحة بالكامل)
        "pdf-cutter.com",
        "embassybase.com",
        "mailsbay.com",
        "mediaholy.com",
        "mediaeast.uk",
        "justdefinition.com",
        "gongjua.com"
    ]

    @classmethod
    def get_domains(cls) -> list[str]:
        return list(cls.DOMAINS)

    @classmethod
    def create_mailbox(cls, username: str = None, domain: str = None) -> dict[str, Any]:
        """إنشاء بريد مخصص على النطاق المطلوب"""
        if not domain or domain not in cls.DOMAINS:
            domain = cls.DOMAINS[0]

        if not username:
            username = f"user_{int(time.time()) % 10000}_{random.randint(1000, 9999)}"
        else:
            username = "".join(c for c in username.lower() if c.isalnum() or c in "._-")

        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "en-US,en;q=0.9,ar;q=0.8",
            "Origin": cls.BASE_URL,
            "Referer": f"{cls.BASE_URL}/change",
            "X-Requested-With": "XMLHttpRequest"
        })

        try:
            session.get(f"{cls.BASE_URL}/en", timeout=10)
        except Exception:
            pass

        url = f"{cls.BASE_URL}/custom-domain-email"
        payload = {"username": username, "domain": domain}

        try:
            resp = session.post(url, json=payload, timeout=12)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("success"):
                    email_addr = data.get("email") or f"{username}@{domain}"
                    code = data.get("code") or ""
                    return {
                        "email": email_addr,
                        "engine": cls.NAME,
                        "token": code,
                        "code": code,
                        "domain": domain,
                        "address": email_addr
                    }
        except Exception:
            pass

        # في حالة وجود ضغط أو تأخر السيرفر
        fallback_email = f"{username}@{domain}"
        return {
            "email": fallback_email,
            "engine": cls.NAME,
            "token": "",
            "code": "",
            "domain": domain,
            "address": fallback_email
        }

    @classmethod
    def get_messages(cls, email: str, token: str = "") -> list[dict[str, Any]]:
        """فحص الوارد وجلب الرسائل واستخراج أكواد OTP"""
        if not email:
            return []

        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Origin": cls.BASE_URL,
            "Referer": f"{cls.BASE_URL}/en",
            "X-Requested-With": "XMLHttpRequest"
        })

        url = f"{cls.BASE_URL}/get-emails?lang=en"
        payload = {"email": email, "code": token}

        try:
            resp = session.post(url, json=payload, timeout=12)
            if resp.status_code == 200:
                data = resp.json()
                raw_emails = data.get("emails") or data.get("messages") or []
                formatted = []
                for i, msg in enumerate(raw_emails):
                    subj = str(msg.get("subject") or msg.get("textSubject") or "")
                    body = str(msg.get("body") or msg.get("text") or msg.get("html") or "")
                    sender = str(msg.get("from") or msg.get("textFrom") or "مجهول")
                    date = str(msg.get("date") or msg.get("textDate") or "")

                    # استخراج رمز التحقق التلقائي
                    otp_m = re.search(r'\b([0-9]{4,8})\b', f"{subj} {body}")
                    otp = otp_m.group(1) if otp_m else None

                    formatted.append({
                        "id": str(msg.get("mid") or msg.get("id") or i),
                        "from": sender,
                        "sender": sender,
                        "subject": subj,
                        "date": date,
                        "body": body,
                        "body_text": body,
                        "body_html": str(msg.get("html") or ""),
                        "otp_code": otp,
                        "otp": otp
                    })
                return formatted
        except Exception:
            pass

        return []
