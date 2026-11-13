import json
import random
import urllib.parse
import urllib.request

class GuerrillaMailEngine:
    """
    محرك Guerrilla Mail الكلاسيكي المجاني
    يعتمد على Session ID (sid_token) لجلب الإيميل والرسائل دون تسجيل.
    """
    NAME = "guerrillamail"
    BASE_URL = "https://api.guerrillamail.com/ajax.php"
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Accept": "application/json"
    }

    @classmethod
    def get_domains(cls) -> list[str]:
        return [
            "guerrillamail.com",
            "guerrillamailblock.com",
            "sharklasers.com",
            "guerrillamail.net",
            "guerrillamail.org"
        ]

    @classmethod
    def create_mailbox(cls, username: str = None, domain: str = None) -> dict:
        """جلب بريد جديد مع sid_token"""
        url = f"{cls.BASE_URL}?f=get_email_address"
        req = urllib.request.Request(url, headers=cls.HEADERS)
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                email = data.get("email_addr", "")
                sid_token = data.get("sid_token", "")
                
                # إذا طلب المستخدم اسم مخصص
                if username and sid_token:
                    set_url = f"{cls.BASE_URL}?f=set_email_user&email_user={urllib.parse.quote(username)}&sid_token={sid_token}"
                    req_set = urllib.request.Request(set_url, headers=cls.HEADERS)
                    with urllib.request.urlopen(req_set, timeout=10) as set_resp:
                        set_data = json.loads(set_resp.read().decode("utf-8"))
                        email = set_data.get("email_addr", email)

                return {
                    "email": email,
                    "provider": cls.NAME,
                    "token": sid_token,
                    "domain": email.split("@")[-1] if "@" in email else "guerrillamail.com",
                    "username": email.split("@")[0] if "@" in email else ""
                }
        except Exception:
            pass

        return {
            "email": f"user{random.randint(1000,9999)}@sharklasers.com",
            "provider": cls.NAME,
            "token": "",
            "domain": "sharklasers.com",
            "username": ""
        }

    @classmethod
    def get_messages(cls, email: str, token: str = "") -> list[dict]:
        """فحص الرسائل الواردة لـ GuerrillaMail"""
        if not token:
            return []
        url = f"{cls.BASE_URL}?f=check_email&seq=0&sid_token={token}"
        req = urllib.request.Request(url, headers=cls.HEADERS)
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                msg_list = data.get("list", [])
                formatted = []
                for m in msg_list:
                    # استبعاد الرسالة الترحيبية الافتراضية الخاصة بـ Guerrilla
                    if "welcome" in m.get("mail_subject", "").lower() or m.get("mail_from") == "no-reply@guerrillamail.com":
                        continue
                    mid = str(m.get("mail_id", ""))
                    body_text = m.get("mail_excerpt", "") or ""
                    body_html = ""

                    # Fetch full message body via fetch_email
                    if mid:
                        try:
                            f_url = f"{cls.BASE_URL}?f=fetch_email&email_id={mid}&sid_token={token}"
                            f_req = urllib.request.Request(f_url, headers=cls.HEADERS)
                            with urllib.request.urlopen(f_req, timeout=8) as f_resp:
                                f_data = json.loads(f_resp.read().decode("utf-8"))
                                full_body = f_data.get("mail_body", "")
                                if full_body:
                                    if "<html" in full_body.lower() or "<div" in full_body.lower() or "<p" in full_body.lower():
                                        body_html = full_body
                                        import re, html as py_html
                                        no_style = re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', body_html, flags=re.DOTALL | re.IGNORECASE)
                                        clean = re.sub(r'<[^<]+?>', ' ', no_style)
                                        body_text = ' '.join(py_html.unescape(clean).split())
                                    else:
                                        body_text = full_body
                        except Exception:
                            pass

                    formatted.append({
                        "id": mid,
                        "sender": m.get("mail_from", "Unknown"),
                        "subject": m.get("mail_subject", "بدون عنوان"),
                        "date": m.get("mail_date", ""),
                        "body_text": body_text,
                        "body_html": body_html
                    })
                return formatted
        except Exception:
            pass
        return []
