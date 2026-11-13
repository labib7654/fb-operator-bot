# -*- coding: utf-8 -*-
"""
محرك الأرقام المؤقتة واستقبال رسائل التفعيل (Virtual Numbers & SMS OTP Engine)
مختصر، سريع، فحص تلقائي للأكواد، وتصفية الأرقام التالفة.
"""
from __future__ import annotations

import os
import re
import time
import sqlite3
import logging
from pathlib import Path
from typing import List, Dict, Optional, Any

try:
    import urllib.request
    HAS_URLLIB = True
except ImportError:
    HAS_URLLIB = False

logger = logging.getLogger("VirtualNumbers")

COUNTRIES = {
    "SE": {"name": "السويد", "flag": "🇸🇪", "prefix": "46"},
    "GB": {"name": "بريطانيا", "flag": "🇬🇧", "prefix": "44"},
    "FI": {"name": "فنلندا", "flag": "🇫🇮", "prefix": "358"},
    "NL": {"name": "هولندا", "flag": "🇳🇱", "prefix": "31"},
    "US": {"name": "أمريكا", "flag": "🇺🇸", "prefix": "1"},
    "FR": {"name": "فرنسا", "flag": "🇫🇷", "prefix": "33"},
}

DEFAULT_POOL = [
    # السويد
    {"phone": "+46731299509", "country": "SE", "carrier": "Tele2"},
    {"phone": "+46726405830", "country": "SE", "carrier": "Telia"},
    {"phone": "+46726415053", "country": "SE", "carrier": "Telenor"},
    # بريطانيا
    {"phone": "+447378912987", "country": "GB", "carrier": "O2"},
    {"phone": "+447723122306", "country": "GB", "carrier": "EE"},
    {"phone": "+447451278149", "country": "GB", "carrier": "Vodafone"},
    # فنلندا
    {"phone": "+3584573994600", "country": "FI", "carrier": "Elisa"},
    {"phone": "+3584573983201", "country": "FI", "carrier": "DNA"},
    # هولندا
    {"phone": "+3197010291207", "country": "NL", "carrier": "KPN"},
    {"phone": "+3197010287413", "country": "NL", "carrier": "Vodafone NL"},
    # أمريكا
    {"phone": "+12068061234", "country": "US", "carrier": "T-Mobile"},
    {"phone": "+12135550192", "country": "US", "carrier": "AT&T"},
    # فرنسا
    {"phone": "+33757130192", "country": "FR", "carrier": "Orange"},
    {"phone": "+33756891042", "country": "FR", "carrier": "SFR"},
]


def _get_db_path() -> Path:
    from fb_operator.config import DATA_DIR
    return Path(DATA_DIR) / "virtual_numbers.db"


class VirtualNumbersEngine:
    _initialized = False

    @classmethod
    def _init_db(cls):
        if cls._initialized:
            return
        db_path = _get_db_path()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(db_path) as conn:
            c = conn.cursor()
            c.execute("""
                CREATE TABLE IF NOT EXISTS numbers (
                    phone TEXT PRIMARY KEY,
                    country TEXT,
                    carrier TEXT,
                    active INTEGER DEFAULT 1,
                    last_sms TEXT DEFAULT '',
                    last_otp TEXT DEFAULT '',
                    last_sender TEXT DEFAULT '',
                    updated_at INTEGER DEFAULT 0
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    phone TEXT,
                    sender TEXT,
                    message TEXT,
                    otp TEXT,
                    received_at TEXT,
                    created_at INTEGER
                )
            """)
            conn.commit()

            # بذر الأرقام الأولية إذا كان الجدول فارغاً
            c.execute("SELECT COUNT(*) FROM numbers")
            if c.fetchone()[0] == 0:
                for item in DEFAULT_POOL:
                    c.execute(
                        "INSERT OR IGNORE INTO numbers (phone, country, carrier, active, updated_at) VALUES (?, ?, ?, 1, ?)",
                        (item["phone"], item["country"], item["carrier"], int(time.time()))
                    )
                conn.commit()
        cls._initialized = True

    @classmethod
    def list_countries(cls) -> List[Dict[str, Any]]:
        """قائمة الدول المتاحة مع الأعلام."""
        cls._init_db()
        out = []
        db_path = _get_db_path()
        with sqlite3.connect(db_path) as conn:
            c = conn.cursor()
            for code, meta in COUNTRIES.items():
                c.execute("SELECT COUNT(*) FROM numbers WHERE country = ? AND active = 1", (code,))
                count = c.fetchone()[0]
                out.append({
                    "code": code,
                    "name": meta["name"],
                    "flag": meta["flag"],
                    "count": count
                })
        return out

    @classmethod
    def get_numbers_for_country(cls, country_code: str) -> List[Dict[str, Any]]:
        """الأرقام المتاحة لدولة معينة."""
        cls._init_db()
        db_path = _get_db_path()
        with sqlite3.connect(db_path) as conn:
            c = conn.cursor()
            c.execute(
                "SELECT phone, country, carrier, last_otp, last_sender, updated_at FROM numbers WHERE country = ? AND active = 1",
                (country_code.upper(),)
            )
            rows = c.fetchall()
            meta = COUNTRIES.get(country_code.upper(), {"name": country_code, "flag": "🌐"})
            return [
                {
                    "phone": r[0],
                    "country": r[1],
                    "country_name": meta["name"],
                    "flag": meta["flag"],
                    "carrier": r[2] or "عام",
                    "last_otp": r[3] or "",
                    "last_sender": r[4] or "",
                }
                for r in rows
            ]

    @classmethod
    def get_or_pick_number(cls, country_code: str = "") -> Optional[Dict[str, Any]]:
        """اختيار رقم عشوائي نشط من دولة معينة أو أي دولة."""
        cls._init_db()
        db_path = _get_db_path()
        with sqlite3.connect(db_path) as conn:
            c = conn.cursor()
            if country_code:
                c.execute(
                    "SELECT phone, country, carrier, last_otp, last_sender FROM numbers WHERE country = ? AND active = 1 ORDER BY RANDOM() LIMIT 1",
                    (country_code.upper(),)
                )
            else:
                c.execute(
                    "SELECT phone, country, carrier, last_otp, last_sender FROM numbers WHERE active = 1 ORDER BY RANDOM() LIMIT 1"
                )
            r = c.fetchone()
            if r:
                meta = COUNTRIES.get(r[1], {"name": r[1], "flag": "🌐"})
                return {
                    "phone": r[0],
                    "country": r[1],
                    "country_name": meta["name"],
                    "flag": meta["flag"],
                    "carrier": r[2] or "عام",
                    "last_otp": r[3] or "",
                    "last_sender": r[4] or "",
                }
        return None

    @classmethod
    def fetch_otp(cls, phone: str) -> Dict[str, Any]:
        """فحص الرسائل الواردة للرقم واستخراج كود التحقق OTP."""
        cls._init_db()
        clean_p = phone.replace("+", "").strip()

        # 1. محاولة الجلب الحي من المصدر السحابي
        try:
            url = f"https://receive-sms-online.info/get_sms_register.php?phone={clean_p}"
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0",
                    "X-Alt-Data": str(int(time.time()))
                }
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                import json
                raw_json = resp.read().decode("utf-8", errors="ignore")
                data = json.loads(raw_json)
                if isinstance(data, list) and len(data) > 0:
                    latest = data[0]
                    msg_text = str(latest.get("mesaj", "")).strip()
                    sender = str(latest.get("telefon", "غير محدد")).strip()
                    time_str = str(latest.get("data", "الآن")).strip()

                    # استخراج الكود بالأرقام
                    otp_match = re.search(r'\b\d{4,8}\b', msg_text)
                    otp_code = otp_match.group(0) if otp_match else ""

                    # حفظ في السجل المحلي
                    db_path = _get_db_path()
                    with sqlite3.connect(db_path) as conn:
                        c = conn.cursor()
                        c.execute(
                            "UPDATE numbers SET last_sms = ?, last_otp = ?, last_sender = ?, updated_at = ? WHERE phone = ?",
                            (msg_text[:200], otp_code, sender[:50], int(time.time()), phone)
                        )
                        c.execute(
                            "INSERT INTO messages (phone, sender, message, otp, received_at, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                            (phone, sender, msg_text, otp_code, time_str, int(time.time()))
                        )
                        conn.commit()

                    return {
                        "received": True,
                        "phone": phone,
                        "otp": otp_code,
                        "sender": sender,
                        "message": msg_text,
                        "time": time_str
                    }
        except Exception:
            pass

        # 2. فحص السجل المحلي إذا كان مسجلاً مسبقاً
        db_path = _get_db_path()
        with sqlite3.connect(db_path) as conn:
            c = conn.cursor()
            c.execute(
                "SELECT sender, message, otp, received_at FROM messages WHERE phone = ? ORDER BY id DESC LIMIT 1",
                (phone,)
            )
            row = c.fetchone()
            if row and row[2]:
                return {
                    "received": True,
                    "phone": phone,
                    "sender": row[0],
                    "message": row[1],
                    "otp": row[2],
                    "time": row[3] or "مؤخراً"
                }

        return {
            "received": False,
            "phone": phone,
            "message": "لم يصل الكود بعد. اطلب الكود من الموقع ثم اضغط تحديث."
        }
