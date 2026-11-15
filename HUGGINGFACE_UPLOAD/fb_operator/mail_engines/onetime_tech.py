import base64
import hashlib
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
        """فحص الرسائل الواردة لبريد معين مع جلب التفاصيل الكاملة لكل رسالة"""
        clean_email = urllib.parse.quote(email.strip().lower())
        res = cls._request(f"/email/{clean_email}/messages")
        if isinstance(res, list):
            formatted = []
            for m in res:
                mid = m.get("id")
                body_text = m.get("text", "") or m.get("intro", "") or ""
                body_html = m.get("html", "") or ""
                subject = m.get("subject", "بدون عنوان")
                sender = m.get("from", "Unknown")
                date = m.get("date", "")

                # Fetch full message details if mid is present to get full body and HTML
                if mid:
                    try:
                        details = cls._request(f"/email/{clean_email}/messages/{mid}")
                        if isinstance(details, dict):
                            body_html = details.get("html", "") or body_html
                            body_text = details.get("text", "") or body_text
                            subject = details.get("subject", "") or subject
                            sender = details.get("from", "") or details.get("fromText", "") or sender
                            date = details.get("createdAt", "") or date
                    except Exception:
                        pass

                # If body_html is present, extract clean text; prefer it if it's richer than truncated body_text
                if body_html:
                    import re, html as py_html
                    no_style = re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', body_html, flags=re.DOTALL | re.IGNORECASE)
                    clean = re.sub(r'<[^<]+?>', ' ', no_style)
                    extracted_text = ' '.join(py_html.unescape(clean).split())
                    if len(extracted_text) > len(body_text) or not body_text.strip():
                        body_text = extracted_text

                if mid:
                    stable_id = str(mid)
                else:
                    seed = f"{clean_email}_{sender}_{subject}_{date}_{body_text[:50]}"
                    stable_id = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:16]

                formatted.append({
                    "id": stable_id,
                    "sender": sender,
                    "subject": subject,
                    "date": date,
                    "body_text": body_text,
                    "body_html": body_html
                })
            return formatted
        return []
