# -*- coding: utf-8 -*-
"""
محرك البريد المميز (SmailPro VIP Engine - Gmail & Outlook)
--------------------------------------------------------
يدعم توليد عناوين بريد إلكتروني حقيقية بنطاقات:
- @gmail.com
- @outlook.com
مع فحص كود التحقق (OTP) من خوادم api.sonjj.com وحذف البريد لتحرير الخانة.
"""
from __future__ import annotations

import json
import os
import time
import requests
from typing import Any

class SmailProEngine:
    NAME = "smailpro"
    BASE_URL = "https://smailpro.com"
    SONJJ_URL = "https://api.sonjj.com"

    DEFAULT_HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Content-Type": "application/json",
        "Referer": "https://smailpro.com/temporary-email"
    }

    @classmethod
    def _get_cookie(cls, session_cookie: str | None = None) -> str | None:
        if session_cookie and session_cookie.strip():
            return session_cookie.strip()
        return os.environ.get("SMAILPRO_COOKIE", "").strip() or None

    @classmethod
    def _get_headers(cls, session_cookie: str | None = None) -> dict[str, str]:
        headers = dict(cls.DEFAULT_HEADERS)
        cookie = cls._get_cookie(session_cookie)
        if cookie:
            headers["Cookie"] = cookie
        return headers

    @classmethod
    def get_domains(cls) -> list[str]:
        """النطاقات المدعومة في المحرك المميز"""
        return ["gmail.com", "outlook.com"]

    @classmethod
    def create_mailbox(cls, domain: str = "gmail.com", session_cookie: str | None = None, server: int = 1) -> dict[str, Any]:
        """
        إنشاء بريد جديد بنطاق gmail.com أو outlook.com
        يُرجع قاموس الحساب متضمناً:
        email, key, timestamp, token, provider, expires_at
        """
        domain_clean = "gmail.com" if "gmail" in domain.lower() else "outlook.com"
        url = f"{cls.BASE_URL}/app/create?username=random&type=alias&domain={domain_clean}&server={server}"
        headers = cls._get_headers(session_cookie)

        try:
            res = requests.get(url, headers=headers, timeout=15)
            if res.status_code == 200:
                data = res.json()
                address = data.get("address")
                key = data.get("key")
                timestamp = data.get("timestamp")

                if address and key and timestamp:
                    # حفظ التوكن كـ JSON لسهولة استرجاع المفتاح والوقت لاحقاً
                    token_payload = json.dumps({"key": key, "timestamp": timestamp})
                    return {
                        "email": address,
                        "provider": cls.NAME,
                        "token": token_payload,
                        "domain": domain_clean,
                        "username": address.split("@")[0],
                        "key": key,
                        "timestamp": timestamp,
                        "created_at": time.time(),
                        "expires_at": time.time() + 300,  # 5 دقائق صلاحية افتراضية
                        "is_vip": True
                    }
                raise RuntimeError(f"بيانات الاستجابة غير مكتملة: {data}")
            elif res.status_code == 403:
                err_data = res.json() if "application/json" in res.headers.get("Content-Type", "") else {}
                msg = err_data.get("msg", "")
                if "Captcha is invalid" in msg:
                    raise RuntimeError("يتطلب SmailPro كوكيز جلسة صالحة (يرجى إضافة كوكيز SmailPro من إعدادات المشرف).")
                raise RuntimeError(f"تم رفض الطلب من مزود SmailPro (403): {msg or res.text[:100]}")
            else:
                raise RuntimeError(f"خطأ خادم SmailPro ({res.status_code}): {res.text[:120]}")
        except Exception as e:
            raise RuntimeError(f"تعذر إنشاء البريد المميز ({domain_clean}): {e}")

    @classmethod
    def get_messages(cls, email: str, token: str = "", session_cookie: str | None = None) -> list[dict[str, Any]]:
        """
        فحص البريد الوارد وجلب كافة الرسائل لبريد SmailPro
        """
        key = None
        timestamp = None

        if token:
            try:
                t_obj = json.loads(token)
                key = t_obj.get("key")
                timestamp = t_obj.get("timestamp")
            except Exception:
                pass

        if not key or not timestamp:
            return []

        mail_type = "gmail" if "gmail" in email.lower() else "outlook"
        endpoint = "temp_gmail" if mail_type == "gmail" else "temp_outlook"
        headers = cls._get_headers(session_cookie)

        payload_body = [{
            "address": email,
            "timestamp": timestamp,
            "key": key
        }]

        try:
            inbox_res = requests.post(f"{cls.BASE_URL}/app/inbox", headers=headers, json=payload_body, timeout=15)
            if inbox_res.status_code != 200:
                return []
            
            inbox_data = inbox_res.json()
            if not isinstance(inbox_data, list) or len(inbox_data) == 0:
                return []

            jwt_payload = inbox_data[0].get("payload")
            if not jwt_payload:
                return []

            check_url = f"{cls.SONJJ_URL}/v1/{endpoint}/inbox?payload={jwt_payload}"
            messages_res = requests.get(check_url, headers=headers, timeout=15)
            if messages_res.status_code != 200:
                return []

            messages_data = messages_res.json()
            raw_messages = messages_data.get("messages", [])
            formatted = []

            for m in raw_messages:
                mid = m.get("mid") or m.get("id") or str(time.time())
                sender = m.get("textFrom") or m.get("from") or "Unknown"
                subject = m.get("textSubject") or m.get("subject") or "بدون عنوان"
                date_str = m.get("textDate") or m.get("date") or ""

                # جلب محتوى الرسالة الكامل إذا وجد رابط message
                body_text = subject
                body_html = ""
                if mid and jwt_payload:
                    try:
                        msg_detail_url = f"{cls.SONJJ_URL}/v1/{endpoint}/message?mid={mid}&payload={jwt_payload}"
                        det_res = requests.get(msg_detail_url, headers=headers, timeout=10)
                        if det_res.status_code == 200:
                            det_data = det_res.json()
                            body_html = det_data.get("html", "") or det_data.get("body", "") or ""
                            body_text = det_data.get("text", "") or body_html or body_text
                    except Exception:
                        pass

                formatted.append({
                    "id": str(mid),
                    "sender": sender,
                    "subject": subject,
                    "date": date_str,
                    "body_text": body_text,
                    "body_html": body_html
                })

            return formatted
        except Exception:
            return []

    @classmethod
    def delete_email(cls, address: str, session_cookie: str | None = None) -> bool:
        """
        حذف البريد فور الانتهاء أو بعد انتهاء مهلة الـ 5 دقائق لتحرير الخانة للعامة
        """
        url = f"{cls.BASE_URL}/app/delete"
        headers = cls._get_headers(session_cookie)
        try:
            res = requests.post(url, headers=headers, json={"address": address}, timeout=10)
            return res.status_code in (200, 204)
        except Exception:
            return False
