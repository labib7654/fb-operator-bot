import re
import json
import urllib.request
import urllib.parse
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("YemenCallerID")

class YemenCallerIDAPI:
    """
    محرك كاشف الأرقام اليمنية المستخرج من تطبيق كاشف الأرقام 967 (com.yemen.y967)
    يدعم البحث بالرقم لجلب اسم المتصل وشبكة الاتصال التابع لها.
    """

    # قائمة السيرفرات النشطة المستخرجة من سورس Flutter المترجم (libapp.so)
    SERVERS = [
        "https://rfhhgdggehhh6.cloudfelre.com",
        "https://u209.cloudfelre.com",
        "https://namer1.studioyemenha.site",
        "https://30.studioyemenha.site",
        "https://31.studioyemenha.site"
    ]

    HEADERS = {
        "User-Agent": "Dart/3.0 (dart:io)",
        "Accept": "application/json",
        "Content-Type": "application/json"
    }

    @staticmethod
    def sanitize_number(raw_phone: str) -> str:
        """
        تنظيف رقم الهاتف وتوحيد صيغته:
        تحويل +967771234567 أو 00967771234567 أو 0771234567 إلى 771234567
        """
        if not raw_phone:
            return ""
        digits = re.sub(r'\D', '', str(raw_phone))
        if digits.startswith("00967"):
            digits = digits[5:]
        elif digits.startswith("967"):
            digits = digits[3:]
        elif digits.startswith("0") and len(digits) >= 9:
            digits = digits[1:]
        return digits

    @staticmethod
    def detect_carrier(number: str) -> str:
        """تحديد شركة الاتصالات التابع لها الرقم اليمني"""
        if not number or len(number) < 2:
            return "غير معروف"
        prefix = number[:2]
        carriers = {
            "77": "يمن موبايل (Yemen Mobile)",
            "78": "يمن موبايل (Yemen Mobile 4G)",
            "73": "يو (YOU - MTN سابقاً)",
            "71": "سبأفون (Sabafon)",
            "70": "واي (Y Telecom)",
            "01": "الهاتف الثابت - صنعاء",
            "02": "الهاتف الثابت - عدن",
            "03": "الهاتف الثابت - الحديدة",
            "04": "الهاتف الثابت - تعز / إب"
        }
        return carriers.get(prefix, "شبكة يمنية أخرى")

    @classmethod
    def lookup_number(cls, raw_phone: str) -> dict:
        """
        البحث عن اسم صاحب الرقم عبر السيرفرات المستخرجة
        مسار الـ API: /api/arkamalyemenphone/2025/getname/{number}
        """
        phone = cls.sanitize_number(raw_phone)
        if not phone or len(phone) < 6:
            return {"success": False, "error": "الرقم غير صالح. يرجى إدخال رقم يمني صحيح (مثال: 777123456)."}

        carrier = cls.detect_carrier(phone)
        endpoint = f"/api/arkamalyemenphone/2025/getname/{phone}"

        # تجربة السيرفرات بالتدوير عند تعثر أي سيرفر (Automatic Failover)
        for base in cls.SERVERS:
            url = f"{base}{endpoint}"
            try:
                req = urllib.request.Request(url, headers=cls.HEADERS)
                with urllib.request.urlopen(req, timeout=5) as response:
                    if response.status == 200:
                        content = response.read().decode("utf-8", errors="ignore")
                        data = json.loads(content)
                        
                        # تحليل النتيجة واستخراج الأسماء
                        names = []
                        if isinstance(data, list):
                            for item in data:
                                if isinstance(item, dict):
                                    name = item.get("name") or item.get("Name")
                                    if name and name not in names:
                                        names.append(name)
                                elif isinstance(item, str):
                                    names.append(item)
                        elif isinstance(data, dict):
                            res_names = data.get("names") or data.get("data") or data.get("name")
                            if isinstance(res_names, list):
                                names = res_names
                            elif isinstance(res_names, str):
                                names = [res_names]

                        return {
                            "success": True,
                            "phone": phone,
                            "carrier": carrier,
                            "names": names if names else ["لم يتم العثور على اسم مسجل لهذا الرقم"],
                            "server": base
                        }
            except Exception as e:
                logger.warning(f"السيرفر [{base}] تعثر: {e}، تجربة السيرفر البديل...")
                continue

        return {
            "success": False,
            "phone": phone,
            "carrier": carrier,
            "error": "تعذر الاتصال بقاعدة بيانات كاشف الأرقام حالياً. يرجى إعادة المحاولة لاحقاً."
        }


# ==============================================================================
# كود الاستخدام المباشر داخل بوت التلجرام (Telebot Example)
# ==============================================================================
"""
# انسخ هذا الجزء وضعه داخل ملف البوت الخاص بك:

@bot.message_handler(commands=['num', 'number', 'kashf'])
def handle_number_search(message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        bot.reply_to(message, "📌 **طريقة الاستخدام:**\nأرسل الأمر مع الرقم هكذا:\n`/num 777123456`", parse_mode="Markdown")
        return
        
    phone_query = args[1].strip()
    bot.send_chat_action(message.chat.id, "typing")
    
    result = YemenCallerIDAPI.lookup_number(phone_query)
    if not result.get("success"):
        bot.reply_to(message, f"❌ {result.get('error')}")
        return
        
    names_text = "\n".join([f"👤 {n}" for n in result['names'][:10]])
    response_msg = (
        f"📱 **نتيجة كاشف الأرقام اليمنية:**\n"
        f"🔢 الرقم: `{result['phone']}`\n"
        f"🌐 الشبكة: `{result['carrier']}`\n\n"
        f"📋 **الأسماء المسجلة:**\n{names_text}"
    )
    bot.reply_to(message, response_msg, parse_mode="Markdown")
"""

if __name__ == "__main__":
    print("=" * 60)
    print("🔍 تجربة استعلام كاشف الأرقام اليمنية (967)")
    print("=" * 60)
    res = YemenCallerIDAPI.lookup_number("777000000")
    print("النتيجة:", json.dumps(res, ensure_ascii=False, indent=2))
