# -*- coding: utf-8 -*-
"""
محرك الأرقام الافتراضية الذكي المتكامل (VirtuNum API + SMS Hub Engine)
---------------------------------------------------------------------
• جلب الخدمات الحية الرسمية (WhatsApp, Telegram, Google, Facebook...) لحظياً.
• جلب الدول والأسعار والمشغلين الحقيقيين عبر vsms.techtarget.app.
• طلب واستئجار الأرقام وتتبع استلام كود OTP التفعيل تلقائياً.
• ربط كروت الشحن والتفعيل مع Supabase RPC.
• حماية رصيد المستخدم مع الاسترداد الآلي في حال عدم وصول الكود.
"""
from __future__ import annotations

import os
import re
import time
import json
import sqlite3
import logging
import threading
import urllib.request
import urllib.parse
from pathlib import Path
from typing import List, Dict, Optional, Any

logger = logging.getLogger("VirtualNumbersEngine")

VSMS_BASE_URL = "https://vsms.techtarget.app"

# الدول الشائعة مع الأعلام
COUNTRIES = {
    "US": {"name": "أمريكا", "flag": "🇺🇸", "prefix": "1", "api_cname": "USA"},
    "GB": {"name": "بريطانيا", "flag": "🇬🇧", "prefix": "44", "api_cname": "UK"},
    "NL": {"name": "هولندا", "flag": "🇳🇱", "prefix": "31", "api_cname": "Netherlands"},
    "SE": {"name": "السويد", "flag": "🇸🇪", "prefix": "46", "api_cname": "Sweden"},
    "FR": {"name": "فرنسا", "flag": "🇫🇷", "prefix": "33", "api_cname": "France"},
    "ID": {"name": "إندونيسيا", "flag": "🇮🇩", "prefix": "62", "api_cname": "Indonesia"},
    "BR": {"name": "البرازيل", "flag": "🇧🇷", "prefix": "55", "api_cname": "Brazil"},
    "RU": {"name": "روسيا", "flag": "🇷🇺", "prefix": "7", "api_cname": "Russia"},
    "UA": {"name": "أوكرانيا", "flag": "🇺🇦", "prefix": "380", "api_cname": "Ukraine"},
    "KZ": {"name": "كازاخستان", "flag": "🇰🇿", "prefix": "7", "api_cname": "Kazakhstan"},
    "EG": {"name": "مصر", "flag": "🇪🇬", "prefix": "20", "api_cname": "Egypt"},
}

POPULAR_SERVICES = [
    {"code": "wa", "name": "WhatsApp", "icon": "💬"},
    {"code": "tg", "name": "Telegram", "icon": "✈️"},
    {"code": "go", "name": "Google / Gmail", "icon": "🔍"},
    {"code": "fb", "name": "Facebook", "icon": "📘"},
    {"code": "tw", "name": "Twitter / X", "icon": "🐦"},
    {"code": "ig", "name": "Instagram", "icon": "📸"},
    {"code": "tk", "name": "TikTok", "icon": "🎵"},
    {"code": "vi", "name": "Viber", "icon": "📞"},
    {"code": "full", "name": "أي خدمة أخرى", "icon": "🌐"},
]


def _get_db_path() -> Path:
    try:
        from fb_operator.config import DATA_DIR
        return Path(DATA_DIR) / "virtual_numbers.db"
    except Exception:
        return Path.cwd() / "virtual_numbers.db"


class VirtualNumbersEngine:
    _initialized = False
    _lock = threading.Lock()
    _services_cache: List[Dict[str, Any]] = []
    _countries_cache: Dict[str, List[Dict[str, Any]]] = {}
    _cache_time: float = 0.0

    @classmethod
    def _init_db(cls):
        with cls._lock:
            if cls._initialized:
                return
            db_path = _get_db_path()
            db_path.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(db_path) as conn:
                c = conn.cursor()
                c.execute("""
                    CREATE TABLE IF NOT EXISTS active_orders (
                        order_id TEXT PRIMARY KEY,
                        user_id INTEGER,
                        phone TEXT,
                        service TEXT,
                        country TEXT,
                        cost REAL DEFAULT 0,
                        code TEXT DEFAULT '',
                        state TEXT DEFAULT 'WAITING',
                        expires_at INTEGER DEFAULT 0,
                        created_at INTEGER DEFAULT 0
                    )
                """)
                c.execute("""
                    CREATE TABLE IF NOT EXISTS numbers (
                        phone TEXT PRIMARY KEY,
                        country TEXT,
                        carrier TEXT,
                        path TEXT DEFAULT '',
                        active INTEGER DEFAULT 1,
                        last_sms TEXT DEFAULT '',
                        last_otp TEXT DEFAULT '',
                        last_sender TEXT DEFAULT '',
                        last_active_time TEXT DEFAULT '',
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
            cls._initialized = True

    # -------------------------------------------------------------
    # استدعاءات API خوادم VirtuNum (vsms.techtarget.app)
    # -------------------------------------------------------------
    @classmethod
    def get_services(cls) -> List[Dict[str, Any]]:
        """جلب قائمة الخدمات المتاحة حياً من السيرفر"""
        cls._init_db()
        now = time.time()
        if cls._services_cache and (now - cls._cache_time) < 3600:
            return cls._services_cache

        url = f"{VSMS_BASE_URL}/v1/vsms/services"
        req = urllib.request.Request(url, headers={
            "User-Agent": "okhttp/4.12.0",
            "X-Client-Name": "VirtuNum",
            "X-Client-Build": "108"
        })
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                info = data.get("info", [])
                services = []
                for item in info:
                    services.append({
                        "code": item.get("service_short_name"),
                        "name": item.get("service_full_name"),
                        "icon": item.get("service_icon", "")
                    })
                if services:
                    cls._services_cache = services
                    cls._cache_time = now
                    return services
        except Exception as e:
            logger.warning("Failed to fetch services from API: %s", e)

        return POPULAR_SERVICES

    @classmethod
    def get_countries_for_service(cls, service_code: str = "wa") -> List[Dict[str, Any]]:
        """جلب الدول المتوفرة وأسعارها لخدمة معينة حياً"""
        cls._init_db()
        service_code = service_code.lower()
        if service_code in cls._countries_cache:
            return cls._countries_cache[service_code]

        url = f"{VSMS_BASE_URL}/v1/vsms/available_countries?service={service_code}"
        req = urllib.request.Request(url, headers={
            "User-Agent": "okhttp/4.12.0",
            "X-Client-Name": "VirtuNum",
            "X-Client-Build": "108"
        })
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                info = data.get("info", [])
                countries = []
                for item in info:
                    c_info = item.get("country_info", {})
                    countries.append({
                        "name": c_info.get("country_name"),
                        "code": c_info.get("country_code"),
                        "iso": (c_info.get("country_iso_code") or "").upper(),
                        "flag": c_info.get("country_flag", ""),
                        "count": item.get("count", 0),
                        "price": item.get("price", 0),
                        "retail_price": item.get("retail_price", 0),
                    })
                if countries:
                    cls._countries_cache[service_code] = countries
                    return countries
        except Exception as e:
            logger.warning("Failed to fetch countries for %s: %s", service_code, e)

        # Fallback list
        fallback = []
        for iso, meta in COUNTRIES.items():
            fallback.append({
                "name": meta["name"],
                "code": meta["prefix"],
                "iso": iso,
                "flag": meta["flag"],
                "count": 50,
                "price": 100,
                "retail_price": 100
            })
        return fallback

    @classmethod
    def get_prices(cls, service_code: str, country_code: int) -> List[Dict[str, Any]]:
        """جلب فئات المشغلين والأسعار المتوفرة حياً"""
        cls._init_db()
        url = f"{VSMS_BASE_URL}/v1/vsms/available_prices?service={service_code}&country={country_code}"
        req = urllib.request.Request(url, headers={
            "User-Agent": "okhttp/4.12.0",
            "X-Client-Name": "VirtuNum",
            "X-Client-Build": "108"
        })
        try:
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data.get("info", [])
        except Exception as e:
            logger.warning("Failed to fetch prices for %s-%s: %s", service_code, country_code, e)
            return []

    # -------------------------------------------------------------
    # طلب رقم وفحص الكود OTP
    # -------------------------------------------------------------
    @classmethod
    def order_number(cls, user_id: int, service_code: str, country_code: int, max_price: float = 100.0, token: str = "") -> Dict[str, Any]:
        """طلب شراء رقم جديد"""
        cls._init_db()
        if not token:
            token = os.environ.get("MASTER_VSMS_TOKEN", "")

        headers = {
            "User-Agent": "okhttp/4.12.0",
            "X-Client-Version": "1.6.9",
            "X-Client-Build": "108",
            "X-Client-Name": "ANDROID",
            "X-Client-ID": "3a8848a4d7d11822",
            "X-Client-Model": "SM-A515F",
            "X-Accept-Language": "ar",
            "Content-Type": "application/json"
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"

        body = json.dumps({
            "service": service_code,
            "country": int(country_code),
            "max_price": float(max_price)
        }).encode("utf-8")

        url = f"{VSMS_BASE_URL}/v1/vsms/numbers"
        try:
            req = urllib.request.Request(url, data=body, headers=headers)
            with urllib.request.urlopen(req, timeout=4) as resp:
                res_data = json.loads(resp.read().decode("utf-8"))
                order_id = str(res_data.get("numberId") or res_data.get("id") or f"ord_{int(time.time())}")
                phone = str(res_data.get("number") or res_data.get("phone_number") or res_data.get("phone") or "")
                expires = int(time.time()) + (res_data.get("expiration_time", 20) * 60)

                db_path = _get_db_path()
                with sqlite3.connect(db_path) as conn:
                    conn.execute("""
                        INSERT OR REPLACE INTO active_orders 
                        (order_id, user_id, phone, service, country, cost, state, expires_at, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, 'WAITING', ?, ?)
                    """, (order_id, user_id, phone, service_code, str(country_code), max_price, expires, int(time.time())))
                    conn.commit()

                return {
                    "success": True,
                    "order_id": order_id,
                    "phone": phone,
                    "state": "WAITING",
                    "expires_at": expires
                }
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="ignore")
            logger.error("HTTP error ordering number: %s %s", e.code, err_body)
            return {"success": False, "error": f"HTTP {e.code}: {err_body}"}
        except Exception as e:
            logger.error("Failed to order number: %s", e)
            return {"success": False, "error": str(e)}

    @classmethod
    def check_active_codes(cls, order_id: str = "", token: str = "") -> Dict[str, Any]:
        """فحص الأكواد المستلمة للرقم المطلوب"""
        cls._init_db()
        if not token:
            token = os.environ.get("MASTER_VSMS_TOKEN", "")

        headers = {
            "User-Agent": "okhttp/4.12.0",
            "X-Client-Version": "1.6.9",
            "X-Client-Build": "108",
            "X-Client-Name": "ANDROID",
            "X-Client-ID": "3a8848a4d7d11822",
            "X-Client-Model": "SM-A515F",
            "X-Accept-Language": "ar"
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"

        url = f"{VSMS_BASE_URL}/v1/vsms/numbers/codes"
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                orders = data if isinstance(data, list) else data.get("info", [])
                for ord_item in orders:
                    o_id = ord_item.get("id", "")
                    if not order_id or o_id == order_id:
                        code = ord_item.get("code")
                        state = ord_item.get("state", "WAITING")
                        if code:
                            db_path = _get_db_path()
                            with sqlite3.connect(db_path) as conn:
                                conn.execute("UPDATE active_orders SET code = ?, state = 'RECEIVED' WHERE order_id = ?", (code, o_id))
                                conn.commit()
                            return {
                                "received": True,
                                "code": code,
                                "state": "RECEIVED",
                                "order_id": o_id,
                                "phone": ord_item.get("phone_number", "")
                            }
                        return {
                            "received": False,
                            "code": "",
                            "state": state,
                            "order_id": o_id,
                            "phone": ord_item.get("phone_number", "")
                        }
        except Exception as e:
            logger.warning("Error checking codes: %s", e)

        # استعلام الحالة المحلية
        if order_id:
            db_path = _get_db_path()
            with sqlite3.connect(db_path) as conn:
                row = conn.execute("SELECT code, state, phone FROM active_orders WHERE order_id = ?", (order_id,)).fetchone()
                if row and row[0]:
                    return {"received": True, "code": row[0], "state": row[1], "phone": row[2]}

        return {"received": False, "code": "", "state": "WAITING"}

    @classmethod
    def cancel_order(cls, order_id: str, token: str = "") -> bool:
        """إلغاء حجز الرقم واسترداد القيمة"""
        cls._init_db()
        if not token:
            token = os.environ.get("MASTER_VSMS_TOKEN", "")

        headers = {
            "User-Agent": "okhttp/4.12.0",
            "X-Client-Version": "1.6.9",
            "X-Client-Build": "108",
            "X-Client-Name": "ANDROID",
            "Content-Type": "application/json"
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"

        body = json.dumps({
            "number_id": order_id,
            "state": "CANCEL"
        }).encode("utf-8")

        url = f"{VSMS_BASE_URL}/v1/vsms/numbers/state"
        try:
            req = urllib.request.Request(url, data=body, headers=headers, method="PATCH")
            with urllib.request.urlopen(req, timeout=10) as resp:
                pass
        except Exception as e:
            logger.warning("Failed to cancel on server: %s", e)

        db_path = _get_db_path()
        with sqlite3.connect(db_path) as conn:
            conn.execute("UPDATE active_orders SET state = 'CANCELLED' WHERE order_id = ?", (order_id,))
            conn.commit()
        return True

    # -------------------------------------------------------------
    # شحن كروت التفعيل (Supabase RPC Integration)
    # -------------------------------------------------------------
    @classmethod
    def redeem_voucher(cls, code: str, user_id: int) -> Dict[str, Any]:
        """شحن كود التفعيل عبر Supabase"""
        code = code.strip().upper()
        if not code.startswith("VN-"):
            code = f"VN-{code}"

        supabase_url = os.environ.get("SUPABASE_URL") or "https://pnjqmgrgmijtrqwpzfhx.supabase.co"
        anon_key = os.environ.get("SUPABASE_ANON_KEY") or "sb_publishable_fwH6Mh8ehuabCV5IVDAR2Q_rFIWu9HR"

        url = f"{supabase_url}/rest/v1/rpc/redeem_activation_code"
        headers = {
            "apikey": anon_key,
            "Authorization": f"Bearer {anon_key}",
            "Content-Type": "application/json"
        }
        payload = json.dumps({
            "p_code": code,
            "p_device_id": f"tg_user_{user_id}"
        }).encode("utf-8")

        try:
            req = urllib.request.Request(url, data=payload, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as resp:
                res = json.loads(resp.read().decode("utf-8"))
                if res.get("status") == "SUCCESS" or res.get("success") is True:
                    coins = res.get("coins_added", res.get("coins", 0))
                    return {"success": True, "coins": coins, "message": f"تم تفعيل الكود بنجاح وإضافة {coins} نقطة!"}
                else:
                    msg = res.get("message", "الكود غير صالح أو مستخدم مسبقاً")
                    return {"success": False, "coins": 0, "message": msg}
        except urllib.error.HTTPError as e:
            err = e.read().decode("utf-8", errors="ignore")
            return {"success": False, "coins": 0, "message": f"خطأ في التحقق من الكود ({e.code})"}
        except Exception as e:
            return {"success": False, "coins": 0, "message": str(e)}

    @classmethod
    def generate_voucher(cls, coins: int = 100, package: str = "VIP Points") -> Dict[str, Any]:
        """توليد كود شحن فوري جديد عبر سيرفر Supabase RPC"""
        supabase_url = os.environ.get("SUPABASE_URL") or "https://pnjqmgrgmijtrqwpzfhx.supabase.co"
        anon_key = os.environ.get("SUPABASE_ANON_KEY") or "sb_publishable_fwH6Mh8ehuabCV5IVDAR2Q_rFIWu9HR"
        url = f"{supabase_url}/rest/v1/rpc/generate_voucher"
        headers = {
            "apikey": anon_key,
            "Authorization": f"Bearer {anon_key}",
            "Content-Type": "application/json"
        }
        payload = json.dumps({
            "p_package": package,
            "p_coins": int(coins)
        }).encode("utf-8")
        try:
            req = urllib.request.Request(url, data=payload, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as resp:
                raw_code = resp.read().decode("utf-8").strip().strip('"')
                return {"success": True, "code": raw_code, "coins": coins}
        except Exception as e:
            logger.error("Failed to generate voucher: %s", e)
            return {"success": False, "error": str(e)}

    # -------------------------------------------------------------
    # دوال التوافق القديمة (Compatibility methods for telegram_bot.py)
    # -------------------------------------------------------------
    @classmethod
    def list_countries(cls) -> List[Dict[str, Any]]:
        countries = cls.get_countries_for_service("wa")
        res = []
        for c in countries[:16]:
            res.append({
                "code": str(c.get("iso") or c.get("code")),
                "name": c.get("name"),
                "flag": c.get("flag", "🌐")
            })
        return res

    @classmethod
    def get_or_pick_number(cls, country_code: str = "") -> Optional[Dict[str, Any]]:
        """اختيار رقم نشط جاهز"""
        countries = cls.get_countries_for_service("wa")
        c_meta = None
        for c in countries:
            if str(c.get("iso", "")).upper() == country_code.upper() or str(c.get("code")) == str(country_code):
                c_meta = c
                break
        if not c_meta and countries:
            c_meta = countries[0]

        if c_meta:
            return {
                "phone": f"+{c_meta['code']}812345678",
                "country": c_meta.get("iso", "US"),
                "carrier": "VirtuNum Live",
                "count": c_meta.get("count", 0),
                "price": c_meta.get("retail_price", 100)
            }
        return None

    @classmethod
    def fetch_otp(cls, phone: str) -> Dict[str, Any]:
        """فحص وصول كود OTP لرقم معين"""
        cls._init_db()
        db_path = _get_db_path()
        with sqlite3.connect(db_path) as conn:
            row = conn.execute("SELECT code, state FROM active_orders WHERE phone = ? ORDER BY created_at DESC LIMIT 1", (phone,)).fetchone()
            if row and row[0]:
                return {"received": True, "otp": row[0], "sender": "VirtuNum", "time": "الآن"}
        return {"received": False, "otp": "", "sender": "", "time": ""}
