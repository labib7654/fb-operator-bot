import json
import random
import string
import urllib.parse
import urllib.request

class MailTmEngine:
    """
    محرك Mail.tm الرسمي
    يوفر صندوق بريد كامل وفق معيار Hydra REST API.
    يتطلب إنشاء حساب واستخراج JWT Token لقراءة الرسائل.
    """
    NAME = "mail_tm"
    BASE_URL = "https://api.mail.tm"
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    @classmethod
    def get_domains(cls) -> list[str]:
        """جلب النطاقات المتاحة من mail.tm"""
        url = f"{cls.BASE_URL}/domains"
        req = urllib.request.Request(url, headers=cls.HEADERS)
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                members = data.get("hydra:member", [])
                return [m["domain"] for m in members if m.get("isActive", True)]
        except Exception:
            pass
        return ["fldubai.com"]

    @classmethod
    def create_mailbox(cls, username: str = None, domain: str = None) -> dict:
        """تسجيل حساب جديد واستخراج التوكن"""
        domains = cls.get_domains()
        if not domain or domain not in domains:
            domain = domains[0] if domains else "fldubai.com"

        if not username:
            username = ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))
        else:
            username = ''.join(c for c in username.lower() if c.isalnum() or c in '._-')

        address = f"{username}@{domain}"
        password = "Pass_" + ''.join(random.choices(string.ascii_letters + string.digits, k=12))

        # 1. Create account
        account_payload = json.dumps({"address": address, "password": password}).encode("utf-8")
        token = ""
        try:
            req1 = urllib.request.Request(f"{cls.BASE_URL}/accounts", data=account_payload, headers=cls.HEADERS, method="POST")
            with urllib.request.urlopen(req1, timeout=10) as resp:
                pass
        except Exception:
            pass

        # 2. Get JWT Token
        try:
            req2 = urllib.request.Request(f"{cls.BASE_URL}/token", data=account_payload, headers=cls.HEADERS, method="POST")
            with urllib.request.urlopen(req2, timeout=10) as resp:
                tdata = json.loads(resp.read().decode("utf-8"))
                token = tdata.get("token", "")
        except Exception:
            pass

        return {
            "email": address,
            "provider": cls.NAME,
            "token": token,
            "domain": domain,
            "username": username,
            "password": password
        }

    @classmethod
    def get_messages(cls, email: str, token: str = "") -> list[dict]:
        """فحص الرسائل باستخدام توكن الحساب"""
        if not token:
            return []

        headers = {**cls.HEADERS, "Authorization": f"Bearer {token}"}
        url = f"{cls.BASE_URL}/messages"
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                members = data.get("hydra:member", [])
                formatted = []
                for m in members:
                    msg_id = m.get("id")
                    from_obj = m.get("from", {})
                    sender = from_obj.get("address", "Unknown") if isinstance(from_obj, dict) else str(from_obj)
                    
                    # Fetch single message details if intro is empty
                    intro = m.get("intro", "")
                    formatted.append({
                        "id": msg_id,
                        "sender": sender,
                        "subject": m.get("subject", "بدون عنوان"),
                        "date": m.get("createdAt", ""),
                        "body_text": intro,
                        "body_html": ""
                    })
                return formatted
        except Exception:
            pass
        return []
