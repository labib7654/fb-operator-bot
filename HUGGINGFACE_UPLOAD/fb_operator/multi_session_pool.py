# -*- coding: utf-8 -*-
"""
حوض تدوير الجلسات المتعددة لكاشف الأرقام (Multi-Session Rotating Pool)
---------------------------------------------------------------------
1. إدارة واكتشاف كافة حسابات تليجرام المساعدة تلقائياً.
2. التحويل التلقائي الفوري (Failover) عند انتهاء باقة أي حساب أو طلب الترقية.
3. معالج تفاعلي مدمج في تلغرام للمطور لإضافة أي رقم هاتف جديد واستقبال الكود و2FA من الشات مباشرة!
4. كاش محلي فوري عبر SQLite لسرعة 0.01 ثانية وتوفير استهلاك الجلسات.
"""
from __future__ import annotations

import os
import re
import glob
import time
import asyncio
import sqlite3
import logging
from pathlib import Path
from typing import List, Dict, Optional, Any

import fb_operator.config as config

try:
    from telethon import TelegramClient
    from telethon.errors import (
        FloodWaitError,
        PhoneNumberInvalidError,
        PhoneCodeInvalidError,
        PhoneCodeExpiredError,
        SessionPasswordNeededError
    )
    HAS_TELETHON = True
except ImportError:
    HAS_TELETHON = False

logger = logging.getLogger("MultiSessionPool")

TARGET_BOT = "Yemennumber_bot"
OFFICIAL_API_ID = 2040
OFFICIAL_API_HASH = "b18441a1ff607e10a989891a5462e627"

# معجم لتخزين طلبات تسجيل الدخول المعلقة للمطور {user_id: {"client": ..., "phone": ..., "phone_code_hash": ...}}
_PENDING_AUTHS: Dict[int, Dict[str, Any]] = {}


def _get_search_dirs() -> List[Path]:
    dirs = [
        getattr(config, "DATA_DIR", Path.cwd()),
        Path(__file__).parent,
        Path(r"C:\Users\XPRISTO\Downloads\LikeStory_TempMail_Project"),
        Path.cwd()
    ]
    unique_dirs = []
    for d in dirs:
        p = Path(d).resolve()
        if p.exists() and p not in unique_dirs:
            unique_dirs.append(p)
    return unique_dirs


def _resolve_db_path() -> str:
    for d in _get_search_dirs():
        db_file = d / "yemen_numbers_cache.db"
        if db_file.exists():
            return str(db_file)
    default_db = getattr(config, "DATA_DIR", Path.cwd()) / "yemen_numbers_cache.db"
    return str(default_db)


def format_international_phone(raw: str) -> str:
    cleaned = re.sub(r'[\s\-\(\)]', '', str(raw or "")).strip()
    if not cleaned.startswith("+"):
        if cleaned.startswith("00"):
            cleaned = "+" + cleaned[2:]
        elif cleaned.startswith("967"):
            cleaned = "+" + cleaned
        elif cleaned.startswith("0") and len(cleaned) == 10:
            cleaned = "+967" + cleaned[1:]
        elif len(cleaned) == 9 and cleaned.startswith("7"):
            cleaned = "+967" + cleaned
        elif len(cleaned) == 8 and cleaned.startswith("7"):
            cleaned = "+967" + cleaned
    return cleaned


class MultiSessionPoolManager:
    _instance: Optional[MultiSessionPoolManager] = None

    def __init__(self):
        self.db_path = _resolve_db_path()
        self.clients: Dict[str, TelegramClient] = {}
        self.exhausted_sessions = set()
        self._init_db()

    @classmethod
    def get_instance(cls) -> MultiSessionPoolManager:
        if cls._instance is None:
            cls._instance = MultiSessionPoolManager()
        return cls._instance

    def _init_db(self):
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
                conn.commit()
        except Exception as e:
            logger.error(f"Error initializing SQLite in MultiSessionPool: {e}")

    def discover_sessions(self) -> List[Dict[str, Any]]:
        """اكتشاف كافة ملفات الجلسات (.session) الصالحة عبر مجلدات المنظومة"""
        found: Dict[str, Path] = {}
        for d in _get_search_dirs():
            for s in d.glob("*.session"):
                name = s.stem
                if name.startswith("temp_") or "journal" in name:
                    continue
                if name not in found and s.stat().st_size > 0:
                    found[name] = s

        result = []
        # وضع الجلسة الأساسية في البداية
        ordered_keys = sorted(found.keys(), key=lambda k: 0 if k == "yemen_bridge_session" else 1)
        for k in ordered_keys:
            p = found[k]
            size_kb = round(p.stat().st_size / 1024, 1)
            result.append({
                "name": k,
                "file_path": str(p),
                "size_kb": size_kb,
                "is_active": k not in self.exhausted_sessions
            })
        return result

    def get_cached(self, phone: str) -> Optional[Dict[str, Any]]:
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
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
        except Exception:
            pass
        return None

    def save_cache(self, phone: str, primary_name: str, records_count: int, names: List[str], carrier: str):
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
            logger.error(f"Error saving to cache in MultiSessionPool: {e}")

    @staticmethod
    def is_upgrade_or_exhausted(text: str) -> bool:
        keywords = [
            "انتهت باقتك", "عمليات البحث المتبقية: 0", "الاشتراك المميز",
            "ترقية 💎", "اشترك في الباقة", "شراء نجوم", "لقد استنفدت"
        ]
        return any(kw in text for kw in keywords)

    @staticmethod
    def parse_full_results(messages_text: List[str]) -> Dict[str, Any]:
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

    async def get_client(self, session_path: str) -> TelegramClient:
        stem = Path(session_path).stem
        if stem not in self.clients or not self.clients[stem].is_connected():
            client = TelegramClient(session_path, OFFICIAL_API_ID, OFFICIAL_API_HASH)
            await client.connect()
            self.clients[stem] = client
        return self.clients[stem]

    async def query_number(self, phone: str) -> Dict[str, Any]:
        """الاستعلام مع التحويل التلقائي الفوري (Failover) بين حسابات التيليجرام في الحوض"""
        # 1. فحص الكاش المحلي أولاً (0 ملي ثانية)
        cached = self.get_cached(phone)
        if cached:
            return {
                "success": True,
                "phone": phone,
                "carrier": cached["carrier"],
                "primary_name": cached["primary_name"],
                "records_count": cached["records_count"],
                "names": cached["names"],
                "source": "قاعدة البيانات المحلية (سريع ⚡)"
            }

        # 2. جلب الجلسات المتاحة
        all_sessions = self.discover_sessions()
        if not all_sessions:
            return {"success": False, "error": "لا توجد أي جلسة تليجرام مسجلة. يرجى إضافة رقم مساعد أولاً."}

        available = [s for s in all_sessions if s["name"] not in self.exhausted_sessions]
        if not available:
            logger.warning("⚠️ جميع الجلسات استنفدت باقاتها. إعادة تهيئة الحوض...")
            self.exhausted_sessions.clear()
            available = all_sessions

        # 3. تدوير الجلسات مع التبديل التلقائي
        for sess_info in available:
            s_name = sess_info["name"]
            s_path = sess_info["file_path"]
            try:
                client = await self.get_client(s_path)
                if not await client.is_user_authorized():
                    logger.warning(f"الجلسة [{s_name}] غير مصرحة، تخطي...")
                    continue

                sent_msg = await client.send_message(TARGET_BOT, phone)
                await asyncio.sleep(2.5)

                received_texts = []
                async for msg in client.iter_messages(TARGET_BOT, min_id=sent_msg.id):
                    if msg.text and "جاري البحث" not in msg.text:
                        received_texts.append(msg.text)

                combined_text = " ".join(received_texts)
                if self.is_upgrade_or_exhausted(combined_text) and not any("الاسم الأشهر" in t or "الأسماء المرتبطة" in t for t in received_texts):
                    logger.warning(f"⚠️ الجلسة [{s_name}] طلبت ترقية. التحويل للحساب البديل فوراً...")
                    self.exhausted_sessions.add(s_name)
                    continue

                parsed = self.parse_full_results(received_texts)
                if not parsed["names"]:
                    parsed["names"] = ["لم يتم العثور على اسم مسجل لهذا الرقم في قاعدة البيانات."]

                prefix = phone[:2] if len(phone) >= 2 else ""
                carriers = {"77": "يمن موبايل 3G/4G", "78": "يمن موبايل 4G", "73": "يو (YOU)", "71": "سبأفون", "70": "واي"}
                carrier = carriers.get(prefix, "شبكة يمنية أخرى")

                self.save_cache(phone, parsed["primary_name"], parsed["records_count"], parsed["names"], carrier)

                return {
                    "success": True,
                    "phone": phone,
                    "carrier": carrier,
                    "primary_name": parsed["primary_name"],
                    "records_count": parsed["records_count"],
                    "names": parsed["names"],
                    "source": f"كاشف الأرقام (عبر {s_name})"
                }

            except FloodWaitError as e:
                logger.warning(f"الجلسة [{s_name}] واجهت انتظار {e.seconds}s. التحويل للبديل...")
                self.exhausted_sessions.add(s_name)
                continue
            except Exception as e:
                logger.error(f"خطأ في الجلسة [{s_name}]: {e}. التحويل للبديل...")
                continue

        return {"success": False, "error": "تعذر الاستعلام من جميع الحسابات المساعدة حالياً. يرجى المحاولة لاحقاً."}

    def delete_session(self, session_name: str) -> bool:
        """حذف جلسة محددة من القرص"""
        deleted = False
        for d in _get_search_dirs():
            target_f = d / f"{session_name}.session"
            if target_f.exists():
                try:
                    target_f.unlink()
                    deleted = True
                except Exception:
                    pass
        if session_name in self.clients:
            try:
                # إغلاق العميل
                asyncio.run(self.clients[session_name].disconnect())
            except Exception:
                pass
            self.clients.pop(session_name, None)
        return deleted


# ----------------- المعالج التفاعلي لربط أرقام جديدة من داخل بوت تلغرام -----------------

async def async_start_session_auth(user_id: int, raw_phone: str) -> Dict[str, Any]:
    """الخطوة 1: استقبال رقم الهاتف والاتصال بتيليجرام لطلب كود التحقق"""
    if not HAS_TELETHON:
        return {"success": False, "error": "مكتبة Telethon غير مثبتة."}

    formatted = format_international_phone(raw_phone)
    clean_digits = re.sub(r'\D', '', formatted)
    if len(clean_digits) < 9:
        return {"success": False, "error": "رقم الهاتف غير صالح. تأكد من إدخال رقم صحيح مع المفتاح الدولي."}

    target_dir = getattr(config, "DATA_DIR", Path.cwd())
    session_title = f"helper_{clean_digits[-9:]}"
    session_file = str(target_dir / session_title)

    # تنظيف أي محاولة سابقة معلقة لنفس المستخدم
    old = _PENDING_AUTHS.pop(user_id, None)
    if old and old.get("client"):
        try:
            await old["client"].disconnect()
        except Exception:
            pass

    client = TelegramClient(session_file, OFFICIAL_API_ID, OFFICIAL_API_HASH)
    await client.connect()

    try:
        sent_code = await client.send_code_request(formatted)
        _PENDING_AUTHS[user_id] = {
            "client": client,
            "phone": formatted,
            "phone_code_hash": sent_code.phone_code_hash,
            "session_file": session_file,
            "session_title": session_title,
            "started_at": time.time()
        }
        return {"success": True, "phone": formatted, "session_title": session_title}
    except PhoneNumberInvalidError:
        await client.disconnect()
        return {"success": False, "error": "رقم الهاتف غير مسجل في تيليجرام أو صيغته خاطئة."}
    except FloodWaitError as fe:
        await client.disconnect()
        return {"success": False, "error": f"تيليجرام يطلب الانتظار {fe.seconds} ثانية بسبب كثرة المحاولات."}
    except Exception as e:
        await client.disconnect()
        return {"success": False, "error": f"تعذر إرسال كود التحقق: {str(e)}"}


async def async_submit_session_code(user_id: int, raw_code: str) -> Dict[str, Any]:
    """الخطوة 2: التحقق من الكود وإتمام تسجيل الدخول وحفظ ملف الجلسة"""
    pending = _PENDING_AUTHS.get(user_id)
    if not pending:
        return {"success": False, "error": "انتهت صلاحية جلسة التسجيل المعلقة. يرجى البدء من جديد بإرسال الرقم."}

    client: TelegramClient = pending["client"]
    phone = pending["phone"]
    phone_code_hash = pending["phone_code_hash"]
    session_title = pending["session_title"]

    clean_code = re.sub(r'[\s\-]', '', str(raw_code or "")).strip()

    try:
        await client.sign_in(phone=phone, code=clean_code, phone_code_hash=phone_code_hash)
        await client.disconnect()
        _PENDING_AUTHS.pop(user_id, None)
        return {
            "success": True,
            "phone": phone,
            "session_title": session_title,
            "message": "تم توثيق الحساب وحفظ الجلسة وضمها لحوض كاشف الأرقام بنجاح!"
        }
    except SessionPasswordNeededError:
        # الحساب يتطلب كلمة مرور التحقق بخطوتين 2FA
        return {
            "success": False,
            "needs_2fa": True,
            "phone": phone,
            "error": "هذا الحساب محمي بكلمة مرور التحقق بخطوتين (2-Step Verification)."
        }
    except PhoneCodeInvalidError:
        return {"success": False, "error": "كود التحقق غير صحيح. تأكد من إدخال الكود المرسل من تيليجرام."}
    except PhoneCodeExpiredError:
        await client.disconnect()
        _PENDING_AUTHS.pop(user_id, None)
        return {"success": False, "error": "انتهت صلاحية كود التحقق. يرجى طلب كود جديد."}
    except Exception as e:
        return {"success": False, "error": f"فشل تسجيل الدخول: {str(e)}"}


async def async_submit_session_2fa(user_id: int, password: str) -> Dict[str, Any]:
    """الخطوة 3 (اختيارية): إدخال كلمة سر التحقق بخطوتين في حال كان الحساب محمياً بـ 2FA"""
    pending = _PENDING_AUTHS.get(user_id)
    if not pending:
        return {"success": False, "error": "انتهت صلاحية الجلسة. يرجى البدء من جديد."}

    client: TelegramClient = pending["client"]
    phone = pending["phone"]
    session_title = pending["session_title"]

    try:
        await client.sign_in(password=password.strip())
        await client.disconnect()
        _PENDING_AUTHS.pop(user_id, None)
        return {
            "success": True,
            "phone": phone,
            "session_title": session_title,
            "message": "تم توثيق الحساب بكلمة مرور 2FA وضم الجلسة بنجاح!"
        }
    except Exception as e:
        return {"success": False, "error": f"كلمة المرور غير صحيحة أو حدث خطأ: {str(e)}"}
