import json
import random
import string
import urllib.parse
import urllib.request

class TempMailIoEngine:
    """
    محرك Temp-Mail.io
    API خفيفة وسريعة توفر 7+ نطاقات شغالة، تدعم تحديد اسم المستخدم يدوياً دون الحاجة لكلمة سر.
    """
    NAME = "tempmail_io"
    BASE_URL = "https://api.internal.temp-mail.io/api/v3"
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    @classmethod
    def get_domains(cls) -> list[str]:
        """جلب النطاقات المتاحة"""
        url = f"{cls.BASE_URL}/domains"
        req = urllib.request.Request(url, headers=cls.HEADERS)
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if "domains" in data and isinstance(data["domains"], list):
                    return [d["name"] for d in data["domains"] if "name" in d]
        except Exception:
            pass
        return ["bwmyga.com", "lnovic.com", "ruutukf.com", "gmeenramy.com", "olipii.com", "ooynib.com", "tanpony.com"]

    @classmethod
    def create_mailbox(cls, username: str = None, domain: str = None) -> dict:
        """إنشاء بريد جديد عشوائي أو مخصص"""
        domains = cls.get_domains()
        if not domain or domain not in domains:
            domain = random.choice(domains)

        if not username:
            username = ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))
        else:
            username = ''.join(c for c in username.lower() if c.isalnum() or c in '._-')

        payload = {
            "name": username,
            "domain": domain
        }
        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(f"{cls.BASE_URL}/email/new", data=data_bytes, headers=cls.HEADERS, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                res = json.loads(resp.read().decode("utf-8"))
                return {
                    "email": res.get("email", f"{username}@{domain}"),
                    "provider": cls.NAME,
                    "token": res.get("token", ""),
                    "domain": domain,
                    "username": username
                }
        except Exception:
            # Fallback local definition
            return {
                "email": f"{username}@{domain}",
                "provider": cls.NAME,
                "token": "",
                "domain": domain,
                "username": username
            }

    @classmethod
    def get_messages(cls, email: str, token: str = "") -> list[dict]:
        """فحص الرسائل الواردة"""
        clean_email = urllib.parse.quote(email.strip().lower())
        url = f"{cls.BASE_URL}/email/{clean_email}/messages"
        req = urllib.request.Request(url, headers=cls.HEADERS)
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if isinstance(data, list):
                    formatted = []
                    for m in data:
                        formatted.append({
                            "id": m.get("id", str(random.random())),
                            "sender": m.get("from", "Unknown"),
                            "subject": m.get("subject", "بدون عنوان"),
                            "date": m.get("created_at", ""),
                            "body_text": m.get("body_text", "") or "",
                            "body_html": m.get("body_html", "") or ""
                        })
                    return formatted
        except Exception:
            pass
        return []
