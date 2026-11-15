# -*- coding: utf-8 -*-
"""
جسر كاشف الأرقام عبر تيليجرام.
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

TARGET_BOT = "Yemennumber_bot"
OFFICIAL_API_ID = 2040
OFFICIAL_API_HASH = "b18441a1ff607e10a989891a5462e627"


def _resolve_session_path() -> str:
    candidates = [
        getattr(config, "DATA_DIR", Path.cwd()) / "yemen_bridge_session",
        Path(__file__).parent / "yemen_bridge_session",
        Path(r"C:\Users\XPRISTO\Downloads\LikeStory_TempMail_Project\yemen_bridge_session"),
        Path.cwd() / "yemen_bridge_session",
    ]
    for c in candidates:
        sess_file = Path(f"{c}.session")
        if sess_file.exists() and sess_file.stat().st_size > 0:
            return str(c)
    return str(getattr(config, "DATA_DIR", Path.cwd()) / "yemen_bridge_session")


def _resolve_db_path() -> str:
    candidates = [
        getattr(config, "DATA_DIR", Path.cwd()) / "yemen_numbers_cache.db",
        Path(__file__).parent / "yemen_numbers_cache.db",
        Path(r"C:\Users\XPRISTO\Downloads\LikeStory_TempMail_Project\yemen_numbers_cache.db"),
        Path.cwd() / "yemen_numbers_cache.db",
    ]
    for c in candidates:
        if Path(c).exists() and Path(c).stat().st_size > 0:
            return str(c)
    return str(getattr(config, "DATA_DIR", Path.cwd()) / "yemen_numbers_cache.db")


class YemenNumberBridge:
    _instance: Optional[YemenNumberBridge] = None

    def __init__(self, api_id: Optional[int] = None, api_hash: Optional[str] = None):
        self.api_id = api_id or int(os.environ.get("TG_API_ID", str(OFFICIAL_API_ID)))
        self.api_hash = api_hash or os.environ.get("TG_API_HASH", OFFICIAL_API_HASH)
        self.session_path = _resolve_session_path()
        self.db_path = _resolve_db_path()
        self.client: Optional[TelegramClient] = None
        self._init_db()

    @classmethod
    def get_instance(cls) -> YemenNumberBridge:
        if cls._instance is None:
            cls._instance = YemenNumberBridge()
        return cls._instance

    def _init_db(self):
        """إنشاء وتحديث قاعدة بيانات التخزين المؤقت المحلي (Zero-Delay SQLite Cache)"""
        try:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS cached_numbers (
                        phone TEXT PRIMARY KEY,
                        primary_name TEXT,
                        records_count INTEGER,
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
        """التحقق مما إذا كان الرقم محفوظاً مسبقاً في السجل"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                try:
                    cursor.execute("SELECT primary_name, records_count, names, carrier FROM cached_numbers WHERE phone = ?", (phone,))
                    row = cursor.fetchone()
                    if row:
                        names_list = [n.strip() for n in (row[2] or "").split("\n") if n.strip()]
                        return {
                            "phone": phone,
                            "primary_name": row[0] or (names_list[0] if names_list else ""),
                            "records_count": row[1] or len(names_list),
                            "names": names_list,
                            "carrier": row[3] or "",
                            "from_cache": True
                        }
                except sqlite3.OperationalError:
                    cursor.execute("SELECT names, carrier FROM cached_numbers WHERE phone = ?", (phone,))
                    row = cursor.fetchone()
                    if row and row[0]:
                        names_list = [n.strip() for n in row[0].split("\n") if n.strip()]
                        return {
                            "phone": phone,
                            "primary_name": names_list[0] if names_list else "",
                            "records_count": len(names_list),
                            "names": names_list,
                            "carrier": row[1] or "",
                            "from_cache": True
                        }
        except Exception:
            pass
        return None

    def save_cache(self, phone: str, primary_name: str, records_count: int, names: List[str], carrier: str):
        """حفظ نتائج الاستعلام في الكاش لتوفير الطلبات وتسريع الرد إلى 0.01 ثانية"""
        if not names:
            return
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT OR REPLACE INTO cached_numbers (phone, primary_name, records_count, names, carrier) VALUES (?, ?, ?, ?, ?)",
                    (phone, primary_name, records_count, "\n".join(names), carrier)
                )
                conn.commit()
        except Exception as e:
            logger.error(f"Error saving to cache: {e}")

    @staticmethod
    def parse_full_results(messages_text: List[str]) -> Dict[str, Any]:
        """تحليل الرسائل المستلمة واستخراج الاسم الأشهر، العدد، وقائمة الأسماء الصافية"""
        primary_name = ""
        records_count = 0
        all_names = []

        blacklist_words = [
            "t.me/", "http", "telegram", "اشترك", "قناة", "بوت", "ملخص البحث",
            "السجلات المكتشفة", "الاسم الأشهر", "الأسماء المرتبطة", "الرقم:",
            "هذا هو الاسم", "لحفظ الاسم", "عرض نتائج أكثر", "━━━━━━━━"
        ]

        for text in messages_text:
            if not text:
                continue

            if "ملخص البحث" in text or "الاسم الأشهر" in text:
                name_match = re.search(r'الاسم الأشهر[:\s*]+([^\n\*_]+)', text)
                if name_match:
                    primary_name = name_match.group(1).strip()

                count_match = re.search(r'السجلات المكتشفة[:\s*]+(\d+)', text)
                if count_match:
                    records_count = int(count_match.group(1))

            for line in text.splitlines():
                line_str = line.strip()
                if not line_str or any(bad in line_str.lower() for bad in blacklist_words):
                    continue
                cleaned = re.sub(r"^[\d\.\-\)\s👤🔹🔸•\:]+", "", line_str).strip()
                cleaned = re.sub(r"[*_`~]+", "", cleaned).strip()
                if cleaned and len(cleaned) > 2 and cleaned not in all_names:
                    all_names.append(cleaned)

        if not primary_name and all_names:
            primary_name = all_names[0]
        elif not primary_name:
            primary_name = "غير مسجل"

        return {
            "primary_name": primary_name,
            "records_count": records_count if records_count > 0 else len(all_names),
            "names": all_names
        }

    def is_configured(self) -> bool:
        """هل تم ضبط مفاتيح تيليجرام وحفظ الجلسة؟"""
        return bool(HAS_TELETHON and self.api_id > 0 and self.api_hash)

    def is_session_ready(self) -> bool:
        """هل ملف جلسة التيليجرام موجود وجاهز على القرص؟"""
        sess_file = Path(f"{self.session_path}.session")
        if not sess_file.exists():
            self.session_path = _resolve_session_path()
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
                "primary_name": cached["primary_name"],
                "records_count": cached["records_count"],
                "names": cached["names"],
                "carrier": cached["carrier"],
                "source": "قاعدة البيانات المحلية (سريع ⚡)"
            }

        # 2. الاستعلام عبر جلسة Telethon
        if not self.client:
            self.client = TelegramClient(self.session_path, self.api_id, self.api_hash)

        if not self.client.is_connected():
            await self.client.connect()
            if not await self.client.is_user_authorized():
                return {"success": False, "error": "جلسة التليجرام غير مصرحة، يرجى تسجيل الدخول أولاً."}

        try:
            sent_msg = await self.client.send_message(TARGET_BOT, phone)
            await asyncio.sleep(2.5)

            received_texts = []
            async for msg in self.client.iter_messages(TARGET_BOT, min_id=sent_msg.id):
                if msg.text and "جاري البحث" not in msg.text:
                    received_texts.append(msg.text)

            parsed = self.parse_full_results(received_texts)

            if not parsed["names"]:
                parsed["names"] = ["لم يتم العثور على اسم مسجل لهذا الرقم في قاعدة البيانات."]

            carrier = ""
            self.save_cache(phone, parsed["primary_name"], parsed["records_count"], parsed["names"], carrier)

            return {
                "success": True,
                "phone": phone,
                "carrier": carrier,
                "primary_name": parsed["primary_name"],
                "records_count": parsed["records_count"],
                "names": parsed["names"],
                "source": "كاشف الأرقام 🌐"
            }
        except FloodWaitError as e:
            return {"success": False, "error": f"يرجى الانتظار {e.seconds} ثانية بسبب ضغط تليجرام."}
        except asyncio.TimeoutError:
            return {"success": False, "error": "انتهت مهلة انتظار رد البوت الرسمي."}
        except Exception as e:
            return {"success": False, "error": f"تعذر الاستعلام: {str(e)}"}
