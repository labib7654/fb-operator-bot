# -*- coding: utf-8 -*-
"""
محرك استخراج أكواد التحقق (OTP) والروابط النشطة بذكاء
------------------------------------------------------
1. تنظيف شامل للـ HTML وتعطيل أي أكواد ألوان أو CSS Styles (مثل #202123) من التحول لأكواد OTP بالخطأ.
2. استخراج الأكواد الرقمية الصريحة (4 إلى 8 أرقام) المصاحبة لكلمات التحقق والتفعيل.
3. استخراج روابط التفعيل والتأكيد المباشرة.
"""
from __future__ import annotations

import re
import html
from typing import Optional


class OtpExtractor:
    # أنماط الكلمات المفتاحية المصاحبة للكود
    OTP_KEYWORDS_PATTERN = re.compile(
        r'(?:code|pin|otp|verification|verify|security|password|رمز|كود|التحقق|تأكيد|المصادقة|مصادقة)[\s:=_\-\w\u0600-\u06FF]{0,45}?\b(\d{4,8})\b',
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
        """إزالة وسوم الـ HTML والـ CSS والألوان والحصول على نص نقي 100%"""
        if not raw_html:
            return ""
        # 1. إزالة سكريبتات وستايل مع محتواها الداخلي
        cleaned = re.sub(r'<(script|style)\b[^>]*>.*?</\1>', ' ', raw_html, flags=re.DOTALL | re.IGNORECASE)
        # 2. إزالة تعليقات الـ HTML
        cleaned = re.sub(r'<!--.*?-->', ' ', cleaned, flags=re.DOTALL)
        # 3. إزالة كافة وسوم الـ HTML مع خصائص الـ style والألوان
        cleaned = re.sub(r'<[^>]+>', ' ', cleaned)
        # 4. فك تشفير المحارف المرمزة
        cleaned = html.unescape(cleaned)
        # 5. تنظيف وتنسيق المسافات
        return ' '.join(cleaned.split())

    @classmethod
    def extract_otp(cls, text: str, html_content: str = "") -> Optional[str]:
        """البحث عن كود التحقق وإرجاعه من النص النقي فقط"""
        clean_t = cls.clean_html(text) if ("<" in text and ">" in text) else text
        clean_h = cls.clean_html(html_content) if html_content else ""
        full_text = f"{clean_t} {clean_h}".strip()
        if not full_text:
            return None

        # 1. فحص الأكواد المصاحبة لكلمات مفتاحية (الأعلى دقة)
        match = cls.OTP_KEYWORDS_PATTERN.search(full_text)
        if match:
            candidate = match.group(1)
            if candidate not in ["2024", "2025", "2026", "2027"]:
                return candidate

        # 2. فحص الأكواد الرقمية المكونة من 6 أرقام أولاً (الأكثر شيوعاً مثل ChatGPT/Google/WhatsApp)
        six_digit = re.search(r'\b(\d{6})\b', full_text)
        if six_digit:
            code = six_digit.group(1)
            if code not in ["202425", "202526", "202627"]:
                return code

        # 3. فحص الأكواد الرقمية العامة (4 إلى 8 أرقام)
        matches = cls.NUMERIC_OTP_PATTERN.findall(full_text)
        if matches:
            for m in matches:
                if len(m) == 4 and m in ["2024", "2025", "2026", "2027"]:
                    continue
                return m

        return None

    @classmethod
    def extract_links(cls, text: str, html_content: str = "") -> list[str]:
        """استخراج روابط التفعيل المباشرة"""
        full_content = f"{text} {html_content}"
        found = cls.VERIFY_URL_PATTERN.findall(full_content)
        seen = set()
        clean_links = []
        for url in found:
            clean = url.rstrip('.,;)"\'')
            if clean not in seen:
                seen.add(clean)
                clean_links.append(clean)
        return clean_links
