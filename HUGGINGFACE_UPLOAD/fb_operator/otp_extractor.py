import re
import html

class OtpExtractor:
    """
    محرك استخراج أكواد التحقق (OTP) والروابط النشطة بذكاء
    يتعرف على:
    - الأكواد الرقمية (4 إلى 8 أرقام)
    - الأكواد النصية-الرقمية المصاحبة لكلمات التحقق (Verify, Code, PIN, Security)
    - روابط التفعيل والتأكيد المباشرة (Verify Link / Confirmation URL)
    """

    # أنماط الكلمات المفتاحية المصاحبة للكود
    OTP_KEYWORDS_PATTERN = re.compile(
        r'(?:code|pin|otp|verification|verify|security|password|رمز|كود|التحقق|تأكيد)[\s:=_-]*([a-zA-Z0-9]{4,8})\b',
        re.IGNORECASE
    )

    # النمط العام للأرقام المتتالية
    NUMERIC_OTP_PATTERN = re.compile(r'\b(\d{4,8})\b')

    # نمط روابط التفعيل
    VERIFY_URL_PATTERN = re.compile(
        r'https?://[^\s<>"]+(?:verify|confirm|activate|validation|token|auth)[^\s<>"]*',
        re.IGNORECASE
    )

    @classmethod
    def clean_html(cls, raw_html: str) -> str:
        """إزالة وسوم الـ HTML والحصول على نص نقي"""
        if not raw_html:
            return ""
        # إزالة سكريبتات وستايل
        cleaned = re.sub(r'<(script|style).*?</\1>', '', raw_html, flags=re.DOTALL | re.IGNORECASE)
        # إزالة باقي الوسوم
        cleaned = re.sub(r'<[^<]+?>', ' ', cleaned)
        # فك تشفير المحارف المرمزة
        cleaned = html.unescape(cleaned)
        # تنسيق المسافات
        return ' '.join(cleaned.split())

    @classmethod
    def extract_otp(cls, text: str, html_content: str = "") -> str | None:
        """البحث عن كود التحقق وإرجاعه"""
        full_text = f"{text} {cls.clean_html(html_content)}".strip()
        if not full_text:
            return None

        # 1. فحص الأكواد المصاحبة لكلمات مفتاحية (الأعلى دقة)
        match = cls.OTP_KEYWORDS_PATTERN.search(full_text)
        if match:
            candidate = match.group(1)
            # تجنب التقاط الكلمات العادية
            if not candidate.isalpha():
                return candidate

        # 2. فحص الأكواد الرقمية الصريحة
        matches = cls.NUMERIC_OTP_PATTERN.findall(full_text)
        if matches:
            # فلترة التواريخ الشائعة (مثل 2024, 2025, 2026) إذا كانت 4 أرقام فقط
            for m in matches:
                if len(m) == 4 and m in ["2024", "2025", "2026", "2027"]:
                    continue
                return m
            return matches[0]

        return None

    @classmethod
    def extract_links(cls, text: str, html_content: str = "") -> list[str]:
        """استخراج روابط التفعيل المباشرة"""
        full_content = f"{text} {html_content}"
        found = cls.VERIFY_URL_PATTERN.findall(full_content)
        # إزالة التكرار مع الحفاظ على الترتيب
        seen = set()
        clean_links = []
        for url in found:
            clean = url.rstrip('.,;)"\'')
            if clean not in seen:
                seen.add(clean)
                clean_links.append(clean)
        return clean_links
