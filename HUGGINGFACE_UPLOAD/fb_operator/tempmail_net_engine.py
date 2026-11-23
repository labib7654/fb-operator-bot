"""
========================================================================================
🚀 Temporary-Mail.net Ultimate Automation Engine (Multi-Domain & Gmail Aliases)
========================================================================================
- الهندسة العكسية الكاملة لخدمة Temporary-Mail.net
- يدعم كافة النطاقات الـ 16 (9 نطاقات مجانية 100% مفتوحة للعامة + 7 نطاقات VIP)
- ميزة تخصيص اسم الإيميل (Custom Username) وتخصيص النطاق (Custom Domain)
- ميزة توليد إيميلات Gmail حقيقية مبنية على النقاط (Gmail Dot Aliases)
- استقبال الرسائل واستخراج رموز التحقق (OTP) تلقائياً (ChatGPT, Telegram, etc.)
========================================================================================
"""

import requests
import re
import time
import random
import logging
from typing import Dict, List, Optional, Tuple, Any

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("TempMailNetEngine")

class TempMailNetEngine:
    BASE_URL = "https://www.temporary-mail.net"
    
    # قائمة النطاقات الكاملة المستخرجة من سورس المنصة
    DOMAINS_FREE = [
        "agogmail.com",
        "mowan666.com",
        "rulersonline.com",
        "swagpapa.com",
        "inctart.com",
        "deepyinc.com",
        "deepmails.org",
        "123mails.org",
        "besttempmail.com"
    ]
    
    DOMAINS_VIP = [
        "pdf-cutter.com",
        "embassybase.com",
        "mailsbay.com",
        "mediaholy.com",
        "mediaeast.uk",
        "justdefinition.com",
        "gongjua.com"
    ]
    
    def __init__(self, proxy: Optional[str] = None):
        self.session = requests.Session()
        if proxy:
            self.session.proxies = {"http": proxy, "https": proxy}
            
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "en-US,en;q=0.9,ar;q=0.8",
            "Origin": self.BASE_URL,
            "Referer": f"{self.BASE_URL}/change",
            "X-Requested-With": "XMLHttpRequest"
        })
        
        self.current_email: Optional[str] = None
        self.current_code: Optional[str] = None
        self._session_initialized = False

    def init_session(self) -> bool:
        """تهيئة الجلسة والتقاط ملفات تعريف الارتباط الأساسية من الصفحة الرئيسية"""
        try:
            resp = self.session.get(f"{self.BASE_URL}/en", timeout=15)
            if resp.status_code == 200:
                self._session_initialized = True
                logger.info("تمت تهيئة الجلسة بنجاح مع خادم temporary-mail.net")
                return True
            logger.warning(f"فشلت تهيئة الجلسة، كود الحالة: {resp.status_code}")
            return False
        except Exception as e:
            logger.error(f"خطأ أثناء تهيئة الجلسة: {e}")
            return False

    def get_available_domains(self, include_vip: bool = False) -> List[str]:
        """إرجاع قائمة النطاقات المتاحة للمستخدم"""
        if include_vip:
            return self.DOMAINS_FREE + self.DOMAINS_VIP
        return self.DOMAINS_FREE

    def create_custom_email(self, username: Optional[str] = None, domain: Optional[str] = None) -> Tuple[bool, Dict[str, Any]]:
        """
        إنشاء إيميل مخصص على أي نطاق مجاني متاح
        :param username: اسم المستخدم المطلوب (مثلاً: labib_test)
        :param domain: النطاق المطلوب (من قائمة النطاقات المجانية)
        """
        if not self._session_initialized:
            self.init_session()
            
        # اختيار النطاق
        if not domain or domain not in self.DOMAINS_FREE:
            domain = random.choice(self.DOMAINS_FREE)
            
        # إنشاء اسم عشوائي إذا لم يحدده المستخدم
        if not username:
            random_num = random.randint(10000, 99999)
            username = f"user_{int(time.time()) % 10000}_{random_num}"
            
        url = f"{self.BASE_URL}/custom-domain-email"
        payload = {
            "username": username,
            "domain": domain
        }
        
        self.session.headers["Referer"] = f"{self.BASE_URL}/change"
        
        try:
            resp = self.session.post(url, json=payload, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("success"):
                    self.current_email = data.get("email")
                    self.current_code = data.get("code")
                    logger.info(f"تم إنشاء الإيميل المخصص بنجاح: {self.current_email}")
                    return True, {
                        "email": self.current_email,
                        "code": self.current_code,
                        "domain": domain,
                        "type": "custom_domain"
                    }
                else:
                    logger.warning(f"رفض الخادم إنشاء الإيميل: {data.get('error')}")
                    return False, {"error": data.get("error", "Failed to create email")}
            elif resp.status_code == 429:
                return False, {"error": "Rate limit exceeded (429). Please wait a few seconds."}
            else:
                return False, {"error": f"Server returned status {resp.status_code}"}
        except Exception as e:
            logger.error(f"خطأ أثناء إنشاء الإيميل: {e}")
            return False, {"error": str(e)}

    def create_custom_gmail(self, gmail_alias: Optional[str] = None) -> Tuple[bool, Dict[str, Any]]:
        """
        إنشاء إيميل Gmail مبني على نظام النقاط (Gmail Dot Alias)
        """
        if not self._session_initialized:
            self.init_session()
            
        if not gmail_alias:
            base_names = ["alexander", "robert", "michael", "william", "david", "richard"]
            base = random.choice(base_names)
            rand_suffix = random.randint(100, 999)
            # إضافة نقاط عشوائية
            gmail_alias = f"{base}.{rand_suffix}.v{random.randint(1,9)}@gmail.com"
        elif not gmail_alias.endswith("@gmail.com"):
            gmail_alias = f"{gmail_alias}@gmail.com"
            
        url = f"{self.BASE_URL}/custom-gmail-email"
        payload = {
            "gmailAlias": gmail_alias
        }
        
        self.session.headers["Referer"] = f"{self.BASE_URL}/change"
        
        try:
            resp = self.session.post(url, json=payload, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("success"):
                    self.current_email = data.get("email")
                    self.current_code = data.get("code")
                    logger.info(f"تم إنشاء إيميل Gmail بنجاح: {self.current_email}")
                    return True, {
                        "email": self.current_email,
                        "code": self.current_code,
                        "type": "gmail_alias"
                    }
                else:
                    return False, {"error": data.get("error", "Failed to create Gmail alias")}
            elif resp.status_code == 429:
                return False, {"error": "Rate limit exceeded (429). Please wait a few seconds."}
            else:
                return False, {"error": f"Server status {resp.status_code}"}
        except Exception as e:
            logger.error(f"خطأ أثناء إنشاء Gmail: {e}")
            return False, {"error": str(e)}

    def get_inbox_messages(self, email: Optional[str] = None, code: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        فحص صندوق الوارد وجلب الرسائل
        """
        email = email or self.current_email
        code = code or self.current_code
        
        if not email or not code:
            logger.error("لا يمكن فحص الوارد بدون وجود email و code مسجلين بالجلسة.")
            return []
            
        url = f"{self.BASE_URL}/get-emails?lang=en"
        payload = {
            "email": email,
            "code": code
        }
        
        self.session.headers["Referer"] = f"{self.BASE_URL}/en"
        
        try:
            resp = self.session.post(url, json=payload, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("success"):
                    emails = data.get("emails") or []
                    # بعض الخوادم ترجعها تحت اسم messages
                    if not emails and "messages" in data:
                        emails = data.get("messages") or []
                    return emails
            return []
        except Exception as e:
            logger.error(f"خطأ أثناء فحص الوارد: {e}")
            return []

    def wait_for_otp(self, email: Optional[str] = None, code: Optional[str] = None, timeout: int = 60, interval: int = 5) -> Optional[str]:
        """
        انتظار كود التحقق (OTP) من أي رسالة واردة تلقائياً
        """
        email = email or self.current_email
        code = code or self.current_code
        
        start_time = time.time()
        logger.info(f"بدء مراقبة الرسائل لاستخراج كود التحقق للإيميل: {email} (المهلة: {timeout} ثانية)...")
        
        while time.time() - start_time < timeout:
            messages = self.get_inbox_messages(email, code)
            if messages:
                for msg in messages:
                    subject = msg.get("textSubject") or msg.get("subject") or ""
                    body = msg.get("body") or msg.get("text") or msg.get("html") or ""
                    sender = msg.get("textFrom") or msg.get("from") or ""
                    full_text = f"{subject} {body}"
                    
                    # استخراج كود التحقق بواسطة regex
                    otp_match = re.search(r'\b([0-9]{4,8})\b', full_text)
                    if otp_match:
                        otp = otp_match.group(1)
                        logger.info(f"🎯 تم صيد كود التحقق بنجاح! الكود: {otp} | المرسل: {sender} | الموضوع: {subject}")
                        return otp
                        
            time.sleep(interval)
            
        logger.warning("انتهت المهلة ولم يتم استقبال أي كود تحقق.")
        return None

# ========================================================================================
# تشغيل تجريبي مباشر
# ========================================================================================
if __name__ == "__main__":
    print("=" * 70)
    print("🚀 فحص واختبار محرك Temporary-Mail.net لجميع النطاقات")
    print("=" * 70)
    
    engine = TempMailNetEngine()
    domains = engine.get_available_domains()
    print(f"✔️ عدد النطاقات المجانية المفتوحة: {len(domains)}")
    for i, d in enumerate(domains, 1):
        print(f"  [{i}] @{d}")
        
    print("\n--- [تجربة 1]: إنشاء إيميل بنطاق مخصص @deepmails.org ---")
    success, res = engine.create_custom_email(username="labib_hero_2026", domain="deepmails.org")
    if success:
        print(f"🎉 تم الإنشاء بنجاح: {res['email']}")
        print(f"🔑 كود الجلسة (Mailbox Code): {res['code']}")
        
        print("\n--- [تجربة 2]: فحص صندوق الوارد المباشر ---")
        msgs = engine.get_inbox_messages()
        print(f"📬 الرسائل الحالية في الصندوق: {len(msgs)}")
    else:
        print(f"❌ فشل الإنشاء: {res.get('error')}")
