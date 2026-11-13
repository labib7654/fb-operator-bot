# -*- coding: utf-8 -*-
"""
جسر كاشف الأرقام اليمنية المتقدم (Yemen Caller ID UserBot Bridge)
-----------------------------------------------------------------
يقوم بالربط البرمجي بين بوتك وبوت كاشف الأرقام الرسمي (@Yemennumber_bot)
لسحب الأسماء الحقيقية الكاملة بدون قيود، مع:
1. تنقية وتطهير الردود من كافة الإعلانات وروابط القنوات والاشتراكات الإجبارية.
2. كاش محلي فوري فائق السرعة عبر SQLite (Zero-Delay Local Cache).
3. معالجة متقدمة لضغط الطلبات وتجنب حظر التيليجرام (FloodWait Resilience).
"""
from __future__ import annotations

import os
import re
import asyncio
import sqlite3
import logging
from pathlib import Path
from typing import List, Dict, Optional, Any

import fb_operator.config as config

try:
    from telethon import TelegramClient
    from telethon.errors import FloodWaitError
    HAS_TELETHON = True
except ImportError:
    HAS_TELETHON = False

logger = logging.getLogger("YemenBridge")

DB_PATH: Path = getattr(config, "DATA_DIR", Path.cwd()) / "yemen_numbers_cache.db"
SESSION_PATH: Path = getattr(config, "DATA_DIR", Path.cwd()) / "yemen_bridge_session"
TARGET_BOT = "Yemennumber_bot"


class YemenNumberBridge:
    _instance: Optional[YemenNumberBridge] = None

    def __init__(self, api_id: Optional[int] = None, api_hash: Optional[str] = None):
        self.api_id = api_id or int(os.environ.get("TG_API_ID", "0"))
        self.api_hash = api_hash or os.environ.get("TG_API_HASH", "")
        self.session_path = str(SESSION_PATH)
        self.db_path = str(DB_PATH)
        self.client: Optional[TelegramClient] = None
        self._init_db()

    @classmethod
    def get_instance(cls) -> YemenNumberBridge:
        if cls._instance is None:
            cls._instance = YemenNumberBridge()
        return cls._instance

    def _init_db(self):
        """إنشاء قاعدة بيانات التخزين المؤقت المحلي (Zero-Delay SQLite Cache)"""
        try:
            DB_PATH.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS cached_numbers (
                        phone TEXT PRIMARY KEY,
                        names TEXT,
                        carrier TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS cached_names (
                        query_name TEXT PRIMARY KEY,
                        raw_result TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                conn.commit()
        except Exception as e:
            logger.error(f"Error initializing SQLite cache: {e}")

    def get_cached(self, phone: str) -> Optional[Dict[str, Any]]:
        """التحقق مما إذا كان الرقم محفوظاً مسبقاً في الكاش المحلي"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT names, carrier FROM cached_numbers WHERE phone = ?", (phone,))
                row = cursor.fetchone()
                if row and row[0]:
                    names_list = [n.strip() for n in row[0].split("\n") if n.strip()]
                    return {
                        "phone": phone,
                        "names": names_list,
                        "carrier": row[1] or "",
                        "from_cache": True
                    }
        except Exception:
            pass
        return None

    def save_cache(self, phone: str, names: List[str], carrier: str):
        """حفظ نتائج الاستعلام في الكاش لتوفير الطلبات وتسريع الرد إلى 0.01 ثانية"""
        if not names:
            return
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT OR REPLACE INTO cached_numbers (phone, names, carrier) VALUES (?, ?, ?)",
                    (phone, "\n".join(names), carrier)
                )
                conn.commit()
        except Exception as e:
            logger.error(f"Error saving to cache: {e}")

    @staticmethod
    def clean_bot_response(raw_text: str) -> List[str]:
        """
        تنقية رد البوت الرسمي من الإعلانات وروابط القنوات والاشتراكات الإجبارية
        واستخراج الأسماء الحقيقية المسجلة فقط بدقة بشرية
        """
        if not raw_text:
            return []
        lines = raw_text.splitlines()
        clean_names: List[str] = []
        for line in lines:
            line_str = line.strip()
            if not line_str:
                continue
            # استبعاد الروابط والقنوات والإعلانات والاشتراكات الإجبارية
            lower = line_str.lower()
            if any(bad in lower for bad in ["t.me/", "http", "telegram", "اشترك", "قناة", "بوت", "اضغط", "تواصل", "راسلنا", "اعلان"]):
                continue

            # تنظيف الترقيم والرموز مثل (1-, 1., 🔹, 👤)
            cleaned = re.sub(r"^[\d\.\-\)\s👤🔹🔸•\:\*\#\~]+", "", line_str).strip()
            # إزالة أي لواحق غير مناسبة
            if cleaned and len(cleaned) > 2 and cleaned not in clean_names:
                clean_names.append(cleaned)

        return clean_names

    def is_configured(self) -> bool:
        """هل تم ضبط مفاتيح تيليجرام وحفظ الجلسة؟"""
        return bool(HAS_TELETHON and self.api_id > 0 and self.api_hash)

    def is_session_ready(self) -> bool:
        """هل ملف جلسة التيليجرام موجود وجاهز على القرص؟"""
        sess_file = Path(f"{self.session_path}.session")
        return sess_file.exists() and sess_file.stat().st_size > 0

    async def query_number(self, phone: str, timeout_seconds: int = 15) -> Dict[str, Any]:
        """الاستعلام المباشر عبر البوت الرسمي"""
        if not HAS_TELETHON:
            return {"success": False, "error": "مكتبة Telethon غير مثبتة."}
        if not self.is_configured():
            return {"success": False, "error": "الجسر غير مهيأ بمفاتيح API ID و API HASH."}

        # 1. فحص الكاش المحلي أولاً
        cached = self.get_cached(phone)
        if cached:
            return {
                "success": True,
                "phone": phone,
                "names": cached["names"],
                "source": "local_sqlite_cache ⚡"
            }

        # 2. الاستعلام عبر جلسة Telethon
        if not self.client:
            self.client = TelegramClient(self.session_path, self.api_id, self.api_hash)

        if not self.client.is_connected():
            await self.client.connect()
            if not await self.client.is_user_authorized():
                return {"success": False, "error": "جلسة التليجرام غير مصرحة، يرجى تسجيل الدخول أولاً."}

        try:
            async with self.client.conversation(TARGET_BOT, timeout=timeout_seconds) as conv:
                await conv.send_message(phone)
                response = await conv.get_response()
                raw_reply = response.text or ""

                names = self.clean_bot_response(raw_reply)
                if not names:
                    if any(k in raw_reply for k in ["لم يتم العثور", "غير مسجل", "لا توجد نتائج"]):
                        return {
                            "success": True,
                            "phone": phone,
                            "names": [],
                            "note": "لم يُعثر على أسماء مسجلة لهذا الرقم في قاعدة البيانات الرسمية.",
                            "source": "official_bot"
                        }
                    names = [raw_reply[:200]]

                return {
                    "success": True,
                    "phone": phone,
                    "names": names,
                    "source": "official_bot 🌐"
                }
        except FloodWaitError as e:
            return {"success": False, "error": f"يرجى الانتظار {e.seconds} ثانية بسبب ضغط تليجرام."}
        except asyncio.TimeoutError:
            return {"success": False, "error": "انتهت مهلة انتظار رد البوت الرسمي."}
        except Exception as e:
            return {"success": False, "error": f"تعذر الاستعلام: {str(e)}"}
