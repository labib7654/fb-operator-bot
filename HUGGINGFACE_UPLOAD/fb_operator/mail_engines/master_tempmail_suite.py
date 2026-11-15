"""
====================================================================================================
🚀 المنظومة الشاملة الموحدة للبريد المؤقت (Master TempMail Suite - 24+ Domains & Real Gmail/Outlook)
====================================================================================================
تجمع كافة المحركات والـ APIs التي قمنا بهندستها بالكامل في كود بايثون واحد جاهز للنسخ المباشر:
1. محرك Temporary-Mail.net:
   - 9 نطاقات مجانية 100% مفتوحة للعامة (Custom Username + Custom Domain).
   - 7 نطاقات VIP بريميوم (قيمة 20 دولار).
   - مولد إيميلات Gmail حقيقية مبنية على النقاط (Gmail Dot Aliases).
2. محرك SmailPro & Sonjj:
   - إيميلات Gmail حقيقية 100% (@gmail.com) واستقبال أكواد ChatGPT.
   - إيميلات Outlook حقيقية (@outlook.com).
   - توليد توكنات JWT وفحص صناديق sonjj.com المشفرة.
3. محرك GuerrillaMail & Sharklasers:
   - نطاقات إضافية مجانية وسريعة جداً.
====================================================================================================
"""

import requests
import re
import os
import time
import random
import json
import logging
from typing import Dict, List, Optional, Tuple, Any

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("MasterTempMailSuite")

# ==================================================================================================
# 🌐 1. دليل كافة النطاقات المتاحة (24+ نطاق بالكامل)
# ==================================================================================================

DOMAINS_CATALOG = {
    # 🌟 النطاقات العالمية الكبرى (سيرفرات حقيقية Gmail & Outlook)
    "major": [
        "gmail.com",
        "outlook.com",
        "hotmail.com"
    ],
    # 🎓 نطاقات SmailPro التعليمية والجامعية المجانية (Edu Domains - مفتوحة 100%)
    "smailpro_edu": [
        "singapore.edu.pl",
        "paris.edu.pl",
        "france.edu.pl"
    ],
    # 🌐 نطاقات SmailPro المجانية المُدارة (16 نطاق نشط)
    "smailpro_managed": [
        "devpoet.com",
        "hastana.com",
        "fenfax.com",
        "jewby.com",
        "bogchi.com",
        "devmant.com",
        "appbott.com",
        "animoby.com",
        "fordemy.com",
        "meltcoo.com",
        "brajraj.org",
        "comproa.org",
        "damphen.org",
        "momroad.org",
        "bussaco.com",
        "storegmail.net"
    ],
    # 🆓 نطاقات Temporary-Mail.net المجانية المفتوحة للعامة 100% (بدون كوكيز وبدون حظر)
    "tempmail_free": [
        "agogmail.com",
        "mowan666.com",
        "rulersonline.com",
        "swagpapa.com",
        "inctart.com",
        "deepyinc.com",
        "deepmails.org",
        "123mails.org",
        "besttempmail.com"
    ],
    # 💎 نطاقات الـ VIP البريميوم (بقيمة 20 دولار في الموقع - مفتوحة بالكامل)
    "tempmail_vip": [
        "pdf-cutter.com",
        "embassybase.com",
        "mailsbay.com",
        "mediaholy.com",
        "mediaeast.uk",
        "justdefinition.com",
        "gongjua.com"
    ],
    # ⚡ نطاقات GuerrillaMail السريعة
    "guerrilla": [
        "guerrillamail.com",
        "guerrillamailblock.com",
        "sharklasers.com",
        "guerrillamail.net",
        "guerrillamail.org"
    ]
}

# ==================================================================================================
# ⚡ 2. محرك Temporary-Mail.net (لا يتطلب كوكيز أو تسجيل - مفتوح 100%)
# ==================================================================================================

class TempMailNetEngine:
    BASE_URL = "https://www.temporary-mail.net"
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Origin": self.BASE_URL,
            "Referer": f"{self.BASE_URL}/change",
            "X-Requested-With": "XMLHttpRequest"
        })
        self._init_session()

    def _init_session(self):
        try:
            self.session.get(f"{self.BASE_URL}/en", timeout=12)
        except Exception:
            pass

    def create_custom_email(self, username: Optional[str] = None, domain: str = "deepmails.org") -> Dict[str, Any]:
        """إنشاء بريد مخصص على أي من النطاقات المجانية أو الـ VIP"""
        if not username:
            username = f"user_{int(time.time()) % 10000}_{random.randint(100, 999)}"
            
        url = f"{self.BASE_URL}/custom-domain-email"
        self.session.headers["Referer"] = f"{self.BASE_URL}/change"
        payload = {"username": username, "domain": domain}
        
        try:
            resp = self.session.post(url, json=payload, timeout=15)
            data = resp.json()
            if resp.status_code == 200 and data.get("success"):
                return {
                    "success": True,
                    "email": data.get("email"),
                    "code": data.get("code"),
                    "domain": domain,
                    "engine": "tempmail_net"
                }
            return {"success": False, "error": data.get("error", "Failed to create email")}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def create_gmail_alias(self, gmail_address: Optional[str] = None) -> Dict[str, Any]:
        """توليد إيميل Gmail حقيقي مبني على نظام النقاط"""
        if not gmail_address:
            base_names = ["alexander", "robert", "william", "david", "richard", "thomas"]
            base = random.choice(base_names)
            rand_id = random.randint(100, 999)
            gmail_address = f"{base}.{rand_id}.v{random.randint(1,9)}@gmail.com"
        elif not gmail_address.endswith("@gmail.com"):
            gmail_address = f"{gmail_address}@gmail.com"

        url = f"{self.BASE_URL}/custom-gmail-email"
        self.session.headers["Referer"] = f"{self.BASE_URL}/change"
        try:
            resp = self.session.post(url, json={"gmailAlias": gmail_address}, timeout=15)
            data = resp.json()
            if resp.status_code == 200 and data.get("success"):
                return {
                    "success": True,
                    "email": data.get("email"),
                    "code": data.get("code"),
                    "domain": "gmail.com",
                    "engine": "tempmail_net"
                }
            return {"success": False, "error": data.get("error", "Failed to create Gmail")}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_messages(self, email: str, code: str) -> List[Dict[str, Any]]:
        """فحص الوارد وجلب الرسائل"""
        url = f"{self.BASE_URL}/get-emails?lang=en"
        self.session.headers["Referer"] = f"{self.BASE_URL}/en"
        try:
            resp = self.session.post(url, json={"email": email, "code": code}, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("success"):
                    msgs = data.get("emails") or data.get("messages") or []
                    return msgs
            return []
        except Exception:
            return []

# ==================================================================================================
# 🔥 3. محرك SmailPro & Sonjj API (Gmail و Outlook الأصلي مع فك تشفير JWT)
# ==================================================================================================

class SmailProEngine:
    BASE_URL = "https://smailpro.com"
    API_SONJJ = "https://api.sonjj.com/v1"
    
    def __init__(self, cookies: Optional[str] = None):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            "Referer": "https://smailpro.com/temporary-email",
            "Accept": "application/json, text/plain, */*"
        })
        self.has_cookies = False
        if cookies:
            self.set_cookies(cookies)
        else:
            self.auto_load_cookies()

    def auto_load_cookies(self):
        """تحميل الكوكيز تلقائياً من البيئة أو الملفات المحلية"""
        # 1. متغير البيئة
        c_env = os.environ.get("SMAILPRO_COOKIE", "").strip()
        if c_env:
            self.set_cookies(c_env)
            return

        # 2. ملفات smailpro_cookie.txt
        from pathlib import Path
        for d in [Path(__file__).parent, Path(__file__).parent.parent, Path(".")]:
            cf = d / "smailpro_cookie.txt"
            if cf.exists():
                try:
                    c = cf.read_text(encoding="utf-8").strip()
                    if c:
                        self.set_cookies(c)
                        return
                except Exception:
                    pass

        # 3. من مدير البريد
        try:
            import fb_operator.tempmail_manager as tm_m
            c_mgr = tm_m.get_vip_cookie()
            if c_mgr:
                self.set_cookies(c_mgr)
        except Exception:
            pass

    def set_cookies(self, raw_cookies: str):
        """تعيين كوكيز الجلسة لتجاوز حظر الكابتشا في SmailPro"""
        for item in raw_cookies.split(";"):
            if "=" in item:
                k, v = item.strip().split("=", 1)
                self.session.cookies.set(k, v, domain="smailpro.com")
        self.has_cookies = True

    def create_mailbox(self, domain: str = "gmail.com", username: str = "random") -> Dict[str, Any]:
        """
        إنشاء بريد رسمي عبر SmailPro
        :param domain: النطاق المطلوب (gmail.com, outlook.com, singapore.edu.pl, devpoet.com, إلخ)
        :param username: اسم المستخدم أو 'random' لتوليده تلقائياً
        """
        dom_clean = domain.strip().lower()
        if "gmail" in dom_clean:
            dom_target = "gmail.com"
            mail_type = "gmail"
        elif "outlook" in dom_clean or "hotmail" in dom_clean:
            dom_target = "outlook.com"
            mail_type = "outlook"
        else:
            dom_target = dom_clean
            mail_type = "gmail"

        url = f"{self.BASE_URL}/app/create?username={username}&type=alias&domain={dom_target}&server=1"
        try:
            resp = self.session.get(url, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                address = data.get("address")
                timestamp = data.get("timestamp")
                if address and timestamp:
                    # طلب مفتاح الـ JWT للصندوق (إرسال الصندوق المفرد فقط لتخطي حد الـ 5 المفتوحة معاً)
                    inbox_req = [{"address": address, "timestamp": timestamp}]
                    inbox_resp = self.session.post(f"{self.BASE_URL}/app/inbox", json=inbox_req, timeout=15)
                    key = None
                    if inbox_resp.status_code == 200:
                        inbox_data = inbox_resp.json()
                        if isinstance(inbox_data, list) and len(inbox_data) > 0:
                            key = inbox_data[0].get("key")
                            
                    return {
                        "success": True,
                        "email": address,
                        "timestamp": timestamp,
                        "jwt_key": key,
                        "domain": dom_target,
                        "mail_type": mail_type,
                        "engine": "smailpro"
                    }
            elif resp.status_code == 403:
                return {"success": False, "error": "يتطلب كوكيز جلسة صالحة (Cloudflare / Session Expiry)"}
            return {"success": False, "error": f"Status {resp.status_code}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_messages(self, jwt_key: str, mail_type: str = "gmail") -> List[Dict[str, Any]]:
        """جلب الرسائل المشفرة عبر API sonjj المباشر"""
        endpoint = "temp_gmail" if mail_type == "gmail" else "temp_outlook"
        url = f"{self.API_SONJJ}/{endpoint}/inbox?payload={jwt_key}"
        try:
            resp = requests.get(url, headers={"user-agent": self.session.headers["User-Agent"]}, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, dict) and "messages" in data:
                    return data.get("messages", [])
                elif isinstance(data, list):
                    return data
            return []
        except Exception:
            return []

# ==================================================================================================
# 🚀 4. المحرك الشامل الموحد المربوط بكافة الخدمات (Universal Multi-Engine Suite)
# ==================================================================================================

class MasterTempMailSuite:
    def __init__(self, smailpro_cookies: Optional[str] = None):
        self.tempmail_net = TempMailNetEngine()
        self.smailpro = SmailProEngine(cookies=smailpro_cookies)

    def list_all_domains(self) -> Dict[str, List[str]]:
        """إرجاع كافة النطاقات المتاحة بالكامل (24+ نطاق)"""
        return DOMAINS_CATALOG

    def generate_email(self, domain_or_type: str = "deepmails.org", username: Optional[str] = None) -> Dict[str, Any]:
        """
        واجهة موحدة ذكية: تفحص النطاق وتستدعي المحرك الأنسب فوراً!
        """
        dom = domain_or_type.lower().replace("@", "").strip()

        # 1. طلب Gmail
        if dom in ["gmail", "gmail.com"]:
            res = self.smailpro.create_mailbox("gmail.com")
            if res.get("success"):
                return res
            # محاولة أخيرة عبر Temporary-Mail.net
            res_alias = self.tempmail_net.create_gmail_alias()
            if res_alias.get("success"):
                return res_alias
            return res

        # 2. طلب Outlook أو Hotmail
        elif dom in ["outlook", "outlook.com", "hotmail", "hotmail.com"]:
            dom_target = "outlook.com" if "outlook" in dom else "hotmail.com"
            res = self.smailpro.create_mailbox(dom_target)
            return res

        # 3. طلب نطاقات SmailPro التعليمية (Edu) أو النطاقات المدارة
        elif dom in DOMAINS_CATALOG.get("smailpro_edu", []) or dom in DOMAINS_CATALOG.get("smailpro_managed", []):
            res = self.smailpro.create_mailbox(dom)
            return res

        # 4. النطاقات المخصصة والمجانية والـ VIP لـ Temporary-Mail.net (16 نطاقاً)
        else:
            return self.tempmail_net.create_custom_email(username=username, domain=dom)

    def fetch_inbox(self, mail_obj: Dict[str, Any]) -> List[Dict[str, Any]]:
        """جلب الرسائل تلقائياً اعتماداً على المحرك المستخدم"""
        engine = mail_obj.get("engine")
        if engine == "tempmail_net":
            return self.tempmail_net.get_messages(mail_obj["email"], mail_obj.get("code", ""))
        elif engine == "smailpro":
            mail_type = mail_obj.get("mail_type")
            if not mail_type:
                dom = mail_obj.get("domain", "") or mail_obj.get("email", "")
                mail_type = "outlook" if ("outlook" in dom or "hotmail" in dom) else "gmail"
            return self.smailpro.get_messages(mail_obj.get("jwt_key", ""), mail_type)
        return []

    def extract_otp(self, messages: List[Dict[str, Any]]) -> Optional[str]:
        """استخراج كود التحقق (OTP) من الرسائل الواردة بـ Regex تلقائي"""
        if not messages:
            return None
        for msg in messages:
            subject = msg.get("textSubject") or msg.get("subject") or ""
            body = msg.get("body") or msg.get("text") or msg.get("html") or ""
            full_text = f"{subject} {body}"
            match = re.search(r'\b([0-9]{4,8})\b', full_text)
            if match:
                return match.group(1)
        return None

# ==================================================================================================
# 🌟 الكائن الموحد الجاهز للاستيراد في كافة أجزاء المشروع
# ==================================================================================================
master_suite = MasterTempMailSuite()

# ==================================================================================================
# تشغيل تجريبي وفحص شامل
# ==================================================================================================
if __name__ == "__main__":
    print("=" * 80)
    print("🚀 اختبار المحرك الموحد الشامل (Master TempMail Suite)")
    print("=" * 80)
    
    suite = MasterTempMailSuite()
    catalog = suite.list_all_domains()
    
    total = sum(len(v) for v in catalog.values())
    print(f"📊 إجمالي النطاقات المكتشفة والمدعومة: {total} نطاقاً")
    for category, doms in catalog.items():
        print(f"  • قسم [{category}]: {', '.join(['@' + d for d in doms])}")

    print("\n--- [تجربة 1]: توليد إيميل بنطاق مجاني @deepmails.org ---")
    m1 = suite.generate_email("deepmails.org", username="hero_bot_user")
    print(f"✔️ النتيجة: {m1}")

    print("\n--- [تجربة 2]: توليد إيميل Gmail حقيقي بنقاط ---")
    m2 = suite.generate_email("gmail.com")
    print(f"✔️ النتيجة: {m2}")
