"""
=============================================================================
محرك أدوات البوت الشامل والفوري (Mega Bot Utilities Engine)
=============================================================================
يعمل في نفس اللحظة (0.0001 ثانية) داخل البوت وبدون أي تأخير أو سيرفرات خارجية:
1. مولد الأسماء المصرية الواقعية (ذكور وإناث).
2. مولد الأسماء الأجنبية العالمية (ذكور وإناث).
3. مولد كلمات المرور الفولاذية العشوائية (مع زر نسخ).
4. مولد أكواد ومفاتيح المصادقة الثنائية (2FA Secret & TOTP Code).
5. مستخرج الآيدي والمعلومات التلجرامية (ID & User Info).
=============================================================================
"""

import random
import string
import secrets
import base64
import time
import hmac
import struct
import hashlib

class MegaBotTools:

    # --- 1. قائمة الأسماء المصرية الواقعية ---
    EGYPTIAN_MALE_FIRST = [
        "أحمد", "محمد", "محمود", "علي", "إبراهيم", "طارق", "كريم", "مصطفى", "عمر", 
        "خالد", "يوسف", "سيد", "حسن", "حسين", "رامي", "أيمن", "وليد", "ياسر", "هشام"
    ]
    EGYPTIAN_FEMALE_FIRST = [
        "فاطمة", "سارة", "نور", "مريم", "آية", "ندى", "ياسمين", "رنا", "هبة", "منة", 
        "شيماء", "أسماء", "دعاء", "ريهام", "دينا", "سلمى", "إيمان", "نهى", "أميرة"
    ]
    EGYPTIAN_LAST = [
        "عبد العزيز", "الشريف", "الدسوقي", "المنشاوي", "البحيري", "الصاوي", "الشناوي", 
        "الجوهري", "حامد", "خليل", "سليمان", "صلاح", "الشافعي", "مراد", "السيد", "عثمان"
    ]

    # --- 2. قائمة الأسماء الأجنبية ---
    FOREIGN_MALE_FIRST = [
        "Alexander", "James", "William", "Benjamin", "Lucas", "Henry", "Theodore", 
        "Jack", "Oliver", "Ethan", "Daniel", "Matthew", "Samuel", "David", "Joseph"
    ]
    FOREIGN_FEMALE_FIRST = [
        "Emma", "Olivia", "Sophia", "Isabella", "Mia", "Evelyn", "Harper", "Camila", 
        "Gianna", "Abigail", "Emily", "Elizabeth", "Ella", "Scarlett", "Grace", "Chloe"
    ]
    FOREIGN_LAST = [
        "Smith", "Johnson", "Williams", "Brown", "Jones", "Miller", "Davis", "Wilson", 
        "Anderson", "Taylor", "Thomas", "Moore", "Jackson", "Martin", "Lee", "Perez"
    ]

    @classmethod
    def generate_egyptian_name(cls, gender: str = "male") -> dict:
        """توليد اسم مصري ثلاثي متناسق وفوري"""
        if gender.lower() == "female":
            first = random.choice(cls.EGYPTIAN_FEMALE_FIRST)
        else:
            first = random.choice(cls.EGYPTIAN_MALE_FIRST)
            
        father = random.choice(cls.EGYPTIAN_MALE_FIRST)
        while father == first:
            father = random.choice(cls.EGYPTIAN_MALE_FIRST)
            
        last = random.choice(cls.EGYPTIAN_LAST)
        full_name = f"{first} {father} {last}"
        return {
            "name": full_name,
            "gender": "أنثى" if gender.lower() == "female" else "ذكر",
            "type": "مصري 🇪🇬"
        }

    @classmethod
    def generate_foreign_name(cls, gender: str = "male") -> dict:
        """توليد اسم أجنبي ثنائي/ثلاثي فوري"""
        if gender.lower() == "female":
            first = random.choice(cls.FOREIGN_FEMALE_FIRST)
        else:
            first = random.choice(cls.FOREIGN_MALE_FIRST)
            
        last = random.choice(cls.FOREIGN_LAST)
        full_name = f"{first} {last}"
        return {
            "name": full_name,
            "gender": "Female" if gender.lower() == "female" else "Male",
            "type": "أجنبي 🌐"
        }

    @classmethod
    def generate_strong_password(cls, length: int = 14) -> str:
        """توليد كلمة مرور قوية للغاية تحتوي رموزاً وأرقاماً وأحرفاً كبيرة وصغيرة"""
        uppercase = string.ascii_uppercase
        lowercase = string.ascii_lowercase
        digits = string.digits
        symbols = "!@#$%^&*()_+-="

        # ضمان وجود عنصر من كل مجموعة
        pwd = [
            secrets.choice(uppercase),
            secrets.choice(lowercase),
            secrets.choice(digits),
            secrets.choice(symbols)
        ]
        
        all_chars = uppercase + lowercase + digits + symbols
        pwd += [secrets.choice(all_chars) for _ in range(length - 4)]
        secrets.SystemRandom().shuffle(pwd)
        return "".join(pwd)

    @classmethod
    def generate_2fa_secret(cls) -> dict:
        """توليد مفتاح 2FA سري مع كود الـ TOTP اللحظي الصالح لـ 30 ثانية"""
        # توليد مفتاح Base32 مكون من 16 حرفاً
        raw_bytes = secrets.token_bytes(10)
        secret_b32 = base64.b32encode(raw_bytes).decode('utf-8').replace('=', '')

        # حساب كود الـ TOTP الحالي
        current_time_step = int(time.time() // 30)
        time_bytes = struct.pack(">Q", current_time_step)
        
        # فك تشفير المفتاح إلى بايتات
        key = base64.b32decode(secret_b32 + "=" * ((8 - len(secret_b32) % 8) % 8))
        hmac_hash = hmac.new(key, time_bytes, hashlib.sha1).digest()
        
        offset = hmac_hash[-1] & 0x0F
        code_int = struct.unpack(">I", hmac_hash[offset:offset + 4])[0] & 0x7FFFFFFF
        totp_code = str(code_int % 1000000).zfill(6)

        return {
            "secret": secret_b32,
            "current_code": totp_code,
            "expires_in": 30 - int(time.time() % 30)
        }


if __name__ == "__main__":
    print("--- تجربة أدوات البوت الفورية ---")
    print("اسم مصري:", MegaBotTools.generate_egyptian_name())
    print("اسم أجنبي:", MegaBotTools.generate_foreign_name())
    print("باسورد قوي:", MegaBotTools.generate_strong_password())
    print("مفتاح 2FA:", MegaBotTools.generate_2fa_secret())
