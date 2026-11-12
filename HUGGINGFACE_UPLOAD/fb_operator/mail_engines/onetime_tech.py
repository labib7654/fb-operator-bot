import base64
import json
import random
import string
import urllib.parse
import urllib.request

class OneTimeTechEngine:
    """
    محرك Instant Mail (1timetech) المستخرج من تطبيق Instant Mail الأندرويد.
    يدعم النطاقات: gmail10p.com, voewo.com, rommiui.com, oletters.com, oemails.com, suiemail.com, إلخ.
    لا يتطلب مفتاح API أو تسجيل دخول.
    """
    NAME = "1timetech"
    BASE_URLS = [
        "https://mail-server.1timetech.com/api",
        "https://mail-server-2.1timetech.com/api"
    ]
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Android; Mobile; rv:120.0) Gecko/120.0 Firefox/120.0",
        "Accept": "application/json"
    }

    @staticmethod
    def _decode_reversed_payload(raw_text: str):
        """فك تشفير استجابة الخادم (Reverse + Base64 Decoding مع إصلاح الـ Padding)"""
        try:
            data_obj = json.loads(raw_text)
            encoded_str = data_obj.get("data", raw_text)
            
            # عكس السلسلة
            reversed_str = encoded_str[::-1]
            
            # تصحيح الـ Base64 Padding
            missing_padding = len(reversed_str) % 4
            if missing_padding:
                reversed_str += '=' * (4 - missing_padding)
                
            decoded_bytes = base64.b64decode(reversed_str)
            return json.loads(decoded_bytes.decode("utf-8"))
        except Exception:
            return None

    @classmethod
    def _request(cls, endpoint: str):
        for base in cls.BASE_URLS:
            try:
                url = f"{base}{endpoint}"
                req = urllib.request.Request(url, headers=cls.HEADERS)
                with urllib.request.urlopen(req, timeout=12) as response:
                    if response.status == 200:
                        content = response.read().decode("utf-8")
                        return cls._decode_reversed_payload(content)
            except Exception:
                continue
        return None

    @classmethod
    def get_domains(cls) -> list[str]:
        """جلب قائمة النطاقات النشطة الحالية"""
        data = cls._request("/domains")
        if data and isinstance(data, dict) and "domains" in data:
            return data["domains"]
        return [
            "gmail10p.com", "voewo.com", "rommiui.com", 
            "oletters.com", "oemails.com", "suiemail.com", 
            "yanemail.com", "mail1time.com"
        ]

    @classmethod
    def create_mailbox(cls, username: str = None, domain: str = None) -> dict:
        """إنشاء صندوق بريد عشوائي أو مخصص"""
        domains = cls.get_domains()
        if not domain or domain not in domains:
            domain = random.choice(domains)
        
        if not username:
            username = ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))
        else:
            username = re_clean = ''.join(c for c in username.lower() if c.isalnum() or c in '._-')
            if not re_clean:
                username = "user" + str(random.randint(1000, 9999))

        email = f"{username}@{domain}"
        return {
            "email": email,
            "provider": cls.NAME,
            "token": "",
            "domain": domain,
            "username": username
        }

    @classmethod
    def get_messages(cls, email: str, token: str = "") -> list[dict]:
        """فحص الرسائل الواردة لبريد معين"""
        clean_email = urllib.parse.quote(email.strip().lower())
        res = cls._request(f"/email/{clean_email}/messages")
        if isinstance(res, list):
            formatted = []
            for m in res:
                formatted.append({
                    "id": m.get("id", str(random.random())),
                    "sender": m.get("from", "Unknown"),
                    "subject": m.get("subject", "بدون عنوان"),
                    "date": m.get("date", ""),
                    "body_text": m.get("text", "") or m.get("intro", "") or "",
                    "body_html": m.get("html", "") or ""
                })
            return formatted
        return []
