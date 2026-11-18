# -*- coding: utf-8 -*-
"""
محرك استخراج أكواد التحقق (OTP) والروابط النشطة الشامل لجميع المنصات العالمية
-----------------------------------------------------------------------------
يدعم استخراج الأكواد والروابط من كافة المنصات بدون استثناء:
1. المنصات العالمية: Google, Facebook, Instagram, WhatsApp, Telegram, Twitter/X,
   TikTok, Microsoft, Steam Guard, Discord, Binance, Amazon, Netflix, Apple ID,
   GitHub, Spotify, Snapchat, LinkedIn, Uber, Careem, PayPal, Claude/Anthropic وغيرها.
2. كافة تنسيقات الأكواد:
   - 6 أرقام قياسية (ChatGPT, Google, Instagram, WhatsApp, TikTok, Binance)
   - 5 أرقام (Telegram, Steam)
   - 4 أرقام (Netflix, Uber, PayPal)
   - 7 و 8 أرقام (Microsoft, Apple, 2FA)
   - الأكواد المبدوءة ببادئة: G-123456 (Google), FB-12345 (Facebook)
   - الأكواد المفصولة بشرطة أو مسافة: 123-456, 123 456
   - الأكواد الأبجدية الرقمية: Steam Guard (مثل HV79X)
3. استخراج روابط التفعيل والتأكيد المباشرة (Buttons / Magic Links) لجميع المنصات التي لا ترسل أرقاماً.
4. التعرف التلقائي الذكي على اسم المنصة وأيقونتها.
5. استبعاد أكواد الألوان والستايلات (#202123) والسنوات وتواريخ الـ Timestamps.
"""
from __future__ import annotations

import re
import html
from typing import Optional, List, Tuple


class OtpExtractor:
    PLATFORM_SIGNATURES: List[Tuple[str, str]] = [
        (r'chatgpt|openai', '🤖 ChatGPT / OpenAI'),
        (r'google|gmail|accounts\.google', '🔴 Google'),
        (r'facebook|meta|fb\.com|facebookmail', '📘 Facebook'),
        (r'instagram', '📸 Instagram'),
        (r'whatsapp', '💬 WhatsApp'),
        (r'telegram', '✈️ Telegram'),
        (r'twitter|\bx\.com|tweet', '🐦 Twitter / X'),
        (r'tiktok', '🎵 TikTok'),
        (r'microsoft|outlook|hotmail|live\.com', '🪟 Microsoft'),
        (r'discord', '🎮 Discord'),
        (r'steam|valve', '🕹️ Steam'),
        (r'binance', '🪙 Binance'),
        (r'amazon', '📦 Amazon'),
        (r'netflix', '🎬 Netflix'),
        (r'apple|icloud', '🍏 Apple ID'),
        (r'github', '🐙 GitHub'),
        (r'spotify', '🎧 Spotify'),
        (r'snapchat', '👻 Snapchat'),
        (r'linkedin', '💼 LinkedIn'),
        (r'claude|anthropic', '🧠 Claude / Anthropic'),
        (r'roblox', '🧱 Roblox'),
        (r'canva', '🎨 Canva'),
        (r'reddit', '🤖 Reddit'),
        (r'epic\s*games', '⚡ Epic Games'),
        (r'uber', '🚗 Uber'),
        (r'careem', '🚗 Careem'),
        (r'paypal', '💳 PayPal')
    ]

    YEARS = {'2024', '2025', '2026', '2027', '2028'}

    @classmethod
    def clean_html(cls, raw_html: str) -> str:
        """إزالة وسوم الـ HTML والـ CSS والألوان والحصول على نص نقي 100%"""
        if not raw_html:
            return ""
        # 1. إزالة سكريبتات وستايل مع محتواها الداخلي
        cleaned = re.sub(r'<(script|style)\b[^>]*>.*?</\1>', ' ', raw_html, flags=re.DOTALL | re.IGNORECASE)
        # 2. إزالة تعليقات الـ HTML
        cleaned = re.sub(r'<!--.*?-->', ' ', cleaned, flags=re.DOTALL)
        # 3. إزالة كافة وسوم الـ HTML
        cleaned = re.sub(r'<[^>]+>', ' ', cleaned)
        # 4. فك تشفير المحارف المرمزة
        cleaned = html.unescape(cleaned)
        # 5. تنظيف وتنسيق المسافات
        return ' '.join(cleaned.split())

    @classmethod
    def detect_platform(cls, sender: str = "", subject: str = "", body: str = "") -> str:
        """التعرف الذكي على اسم وأيقونة المنصة المرسلة"""
        target = f"{sender} {subject} {body[:400]}".lower()
        for pat, name in cls.PLATFORM_SIGNATURES:
            if re.search(pat, target, re.IGNORECASE):
                return name
        return "🌐 منصة إلكترونية"

    @classmethod
    def extract_otp(cls, text: str, html_content: str = "", subject: str = "") -> Optional[str]:
        """
        البحث الذكي عن كود التحقق وإرجاعه من العنوان أولاً ثم النص ثم الـ HTML.
        """
        # 1. فحص سطر الموضوع (Subject) أولاً - غالباً ما يكون الأنقى والأدق
        if subject:
            sub_otp = cls._extract_candidate(subject)
            if sub_otp:
                return sub_otp

        # 2. فحص النص النقي ومحتوى الرسالة
        clean_t = cls.clean_html(text) if ("<" in text and ">" in text) else text
        clean_h = cls.clean_html(html_content) if html_content else ""
        full_text = f"{clean_t} {clean_h}".strip()
        if not full_text:
            return None

        return cls._extract_candidate(full_text)

    @classmethod
    def _extract_candidate(cls, text: str) -> Optional[str]:
        # أ. الأكواد ذات البادئات الرسمية: G-123456 (Google) أو FB-12345 (Facebook)
        g_match = re.search(r'\b(?:G|FB)[-–—\s](\d{4,8})\b', text, re.IGNORECASE)
        if g_match:
            return g_match.group(1)

        # ب. الأكواد المفصولة بشرطة أو مسافة: 123-456 (WhatsApp / Microsoft) أو 123 456 (Instagram)
        hyphen_match = re.search(r'\b(\d{3})[-–—\s](\d{3})\b', text)
        if hyphen_match:
            candidate = f"{hyphen_match.group(1)}{hyphen_match.group(2)}"
            if candidate not in cls.YEARS and candidate != "202123":
                return candidate

        # ج. أكواد Steam Guard الأبجدية الرقمية (مثل HV79X أو C89B2)
        if re.search(r'steam', text, re.IGNORECASE):
            steam_m = re.search(r'(?:steam guard|code|login)[^\w]{1,25}([A-Z0-9]{5})\b', text, re.IGNORECASE)
            if steam_m:
                cand = steam_m.group(1).upper()
                if not cand.isdigit() or cand not in cls.YEARS:
                    return cand

        # د. الأكواد المصاحبة لكلمات مفتاحية صريحة (عربية وإنجليزية)
        kw_pattern = re.compile(
            r'(?:code|pin|otp|verification|verify|security|password|confirmation|confirm|auth|رمز|كود|التحقق|تأكيد|المصادقة|أمان)[\s:=_\-\w\u0600-\u06FF]{0,45}?\b(\d{4,8})\b',
            re.IGNORECASE
        )
        m = kw_pattern.search(text)
        if m:
            cand = m.group(1)
            if cand not in cls.YEARS and cand != "202123":
                return cand

        # هـ. فحص الأكواد القياسية المكونة من 6 أرقام (الأكثر انتشاراً عالمياً)
        for m in re.finditer(r'\b(\d{6})\b', text):
            cand = m.group(1)
            if cand not in cls.YEARS and cand != "202123":
                return cand

        # و. فحص الأكواد المكونة من 5 أرقام (Telegram)
        for m in re.finditer(r'\b(\d{5})\b', text):
            cand = m.group(1)
            return cand

        # ز. فحص الأكواد المكونة من 4 أرقام أو 7-8 أرقام (Netflix, Uber, Microsoft, Apple)
        for m in re.finditer(r'\b(\d{4}|\d{7,8})\b', text):
            cand = m.group(1)
            if cand not in cls.YEARS:
                return cand

        return None

    @classmethod
    def extract_links(cls, text: str, html_content: str = "") -> list[str]:
        """
        استخراج روابط التفعيل والتأكيد المباشرة لجميع المنصات
        (أزرار التأكيد لـ Discord, Spotify, Twitter, GitHub, Facebook وغيرها)
        """
        full_content = f"{text} {html_content}"
        links = []

        # 1. فحص وسوم الروابط <a> والبحث عن نصوص التفعيل الصريحة
        a_tags = re.findall(r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', full_content, re.IGNORECASE | re.DOTALL)
        for href, label in a_tags:
            lbl_clean = re.sub(r'<[^>]+>', '', label).strip().lower()
            if any(k in lbl_clean for k in [
                'verify', 'confirm', 'activate', 'validate', 'complete registration',
                'get started', 'log in', 'sign in', 'تأكيد', 'تفعيل', 'تحقق', 'اضغط هنا',
                'إكمال التسجيل', 'تسجيل الدخول'
            ]):
                if not any(ign in href.lower() for ign in ['unsubscribe', 'privacy', 'terms', 'help', 'settings', 'faq']):
                    if href not in links:
                        links.append(href)

        # 2. البحث عن الروابط المباشرة الحاوية على مسارات وبارامترات التفعيل
        raw_urls = re.findall(
            r'https?://[^\s<>"\'\)]+(?:verify|confirm|activate|validation|token=|auth=)[^\s<>"\'\)]*',
            full_content,
            re.IGNORECASE
        )
        for u in raw_urls:
            u_clean = u.rstrip('.,;)"\'')
            if not any(ign in u_clean.lower() for ign in ['unsubscribe', 'privacy', 'terms', 'help']):
                if u_clean not in links:
                    links.append(u_clean)

        return links[:3]
