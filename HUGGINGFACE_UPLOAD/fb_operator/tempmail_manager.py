# -*- coding: utf-8 -*-
"""
محرك إدارة البريد المؤقت والدائم (TempMail & Recovery Vault Manager)
-------------------------------------------------------------------
يدير:
1. توليد الإيميلات العشوائية والمخصصة عبر 4 محركات سحابية عالمية مجانية.
2. تخزين دائم لحساب كل مستخدم وسجل إيميلاته السابقة (مع إمكانية التبديل بينها والرجوع لها في أي وقت).
3. فحص البريد الوارد واستخراج أكواد التحقق (OTP) وروابط التفعيل عبر OtpExtractor.
4. رقابة وتحكم شامل للمطور (عرض كل المستخدمين وإيميلاتهم ورسائلهم الواردة).
5. سلة المحذوفات والخزنة الفورية للاسترجاع (Soft-Delete & 1-Tap Recovery Vault):
   أي إيميل يُحذف بالغلط يُحفظ في trash_emails.json ويمكن للمطور أو المستخدم استرجاعه فوراً بضغطة واحدة.
6. مزامنة فورية مع قاعدة البيانات المتعددة (SQLite WAL / External Vault / Supabase / Backup ZIP).
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import re
import threading
from pathlib import Path
from typing import Any

import fb_operator.config as config
from fb_operator.mail_engines import MailEngineManager
from fb_operator.mail_engines.master_tempmail_suite import master_suite, DOMAINS_CATALOG
from fb_operator.otp_extractor import OtpExtractor

_tm_lock = threading.RLock()

TEMP_EMAILS_FILE: Path = getattr(config, "TEMP_EMAILS_FILE", config.DATA_DIR / "temp_emails.json")
TRASH_EMAILS_FILE: Path = getattr(config, "TRASH_EMAILS_FILE", config.DATA_DIR / "trash_emails.json")


def _atomic_write_json(file_path: Path, data: Any) -> None:
    file_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = file_path.with_suffix(file_path.suffix + f".tmp.{threading.get_ident()}")
    payload = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    with open(tmp_path, "wb") as f:
        f.write(payload)
        f.flush()
        try:
            os.fsync(f.fileno())
        except Exception:
            pass
    os.replace(tmp_path, file_path)


def _safe_load_json(file_path: Path, default_val: Any) -> Any:
    if not file_path.exists():
        return default_val
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default_val


def _notify_persistence(reason: str = "tempmail") -> None:
    try:
        from fb_operator.persistence_manager import notify_data_changed
        notify_data_changed(reason)
    except Exception:
        pass


def _get_data() -> dict[str, Any]:
    data = _safe_load_json(TEMP_EMAILS_FILE, {})
    if not isinstance(data, dict):
        data = {}
    data.setdefault("users", {})             # {str(user_id): {...active_mailbox...}}
    data.setdefault("history", [])           # list of {id, user_id, email, provider, token, domain, username, created_at}
    data.setdefault("seen_messages", {})     # {str(user_id): [msg_id, ...]}
    data.setdefault("mailbox_messages", {})  # {email_lower: [msg1, msg2, ...]} خزنة الرسائل الدائمة لكل إيميل
    return data


def _get_trash() -> list[dict[str, Any]]:
    trash = _safe_load_json(TRASH_EMAILS_FILE, [])
    if isinstance(trash, dict):
        trash = trash.get("trash", [])
    if not isinstance(trash, list):
        trash = []
    return trash


def get_available_domains() -> list[dict[str, str]]:
    """جلب قائمة النطاقات الـ 23+ المدعومة رسمياً"""
    flat = []
    # 1. النطاقات المفتوحة المجانية بدون كوكيز (Temporary-Mail.net)
    for d in DOMAINS_CATALOG.get("tempmail_free", []):
        flat.append({"domain": d, "engine": "tempmail_net", "category": "مجاني"})
    # 2. نطاقات VIP البريميوم
    for d in DOMAINS_CATALOG.get("tempmail_vip", []):
        flat.append({"domain": d, "engine": "tempmail_net", "category": "VIP"})
    # 3. النطاقات الكبرى الرسمية
    for d in DOMAINS_CATALOG.get("major", []):
        flat.append({"domain": d, "engine": "smailpro", "category": "رسمي"})
    # 4. النطاقات السريعة
    for d in DOMAINS_CATALOG.get("guerrilla", []):
        flat.append({"domain": d, "engine": "guerrilla", "category": "سريع"})
    return flat


def create_random_email(user_id: int, preferred_engine: str | None = None) -> dict[str, Any]:
    """توليد بريد عشوائي جديد وتعيينه كبريد نشط للمستخدم وحفظه في الأرشيف الدائم"""
    with _tm_lock:
        import random
        import time
        # اختيار نطاق مجاني مفضل مثل deepmails.org أو agogmail.com
        free_domains = DOMAINS_CATALOG.get("tempmail_free", ["deepmails.org", "agogmail.com"])
        target_domain = random.choice(free_domains)
        res = master_suite.generate_email(target_domain)
        if not res or not res.get("success"):
            res = master_suite.generate_email("deepmails.org")

        now = datetime.datetime.now().isoformat()
        clean_email = res.get("email", f"user_{int(time.time()) % 10000}@deepmails.org")
        code = res.get("code") or res.get("token") or ""

        mailbox_record = {
            "id": hashlib.sha1(f"{user_id}_{clean_email}_{now}".encode()).hexdigest()[:12],
            "user_id": int(user_id),
            "email": clean_email,
            "provider": res.get("engine", "tempmail_net"),
            "token": code,
            "code": code,
            "domain": res.get("domain", clean_email.split("@")[-1] if "@" in clean_email else "deepmails.org"),
            "username": clean_email.split("@")[0] if "@" in clean_email else "user",
            "created_at": now,
            "auto_notify": True
        }

        data = _get_data()
        data["users"][str(user_id)] = mailbox_record
        data["history"].insert(0, mailbox_record)
        data["history"] = data["history"][:300]

        _atomic_write_json(TEMP_EMAILS_FILE, data)
        _notify_persistence("tempmail_random_created")
        return mailbox_record


def create_custom_email(user_id: int, username: str, domain: str) -> dict[str, Any]:
    """توليد بريد مخصص باسم ونطاق يختارهما المستخدم وتعيينه كبريد نشط"""
    with _tm_lock:
        clean_user = re.sub(r'[^a-zA-Z0-9._-]', '', username.strip().lower())
        if not clean_user:
            clean_user = f"user_{int(user_id) % 10000}"

        clean_dom = domain.strip().lower().replace("@", "")
        res = master_suite.generate_email(clean_dom, username=clean_user)
        if not res or not res.get("success"):
            res = master_suite.generate_email("deepmails.org", username=clean_user)

        now = datetime.datetime.now().isoformat()
        clean_email = res.get("email", f"{clean_user}@{clean_dom}")
        code = res.get("code") or res.get("token") or ""

        mailbox_record = {
            "id": hashlib.sha1(f"{user_id}_{clean_email}_{now}".encode()).hexdigest()[:12],
            "user_id": int(user_id),
            "email": clean_email,
            "provider": res.get("engine", "tempmail_net"),
            "token": code,
            "code": code,
            "domain": res.get("domain", clean_dom),
            "username": clean_user,
            "created_at": now,
            "auto_notify": True
        }

        data = _get_data()
        data["users"][str(user_id)] = mailbox_record
        data["history"].insert(0, mailbox_record)
        data["history"] = data["history"][:300]

        _atomic_write_json(TEMP_EMAILS_FILE, data)
        _notify_persistence("tempmail_custom_created")
        return mailbox_record


def get_user_active_mailbox(user_id: int) -> dict[str, Any] | None:
    """جلب صندوق البريد النشط الحالي للمستخدم"""
    with _tm_lock:
        data = _get_data()
        return data["users"].get(str(user_id))


def set_user_active_mailbox(user_id: int, email: str) -> dict[str, Any] | None:
    """التبديل إلى بريد سابق مخزن في الأرشيف وتفعيله كبريد نشط"""
    with _tm_lock:
        data = _get_data()
        uid_str = str(user_id)
        # البحث في الأرشيف
        target = None
        for item in data.get("history", []):
            if int(item.get("user_id", 0)) == int(user_id) and item.get("email", "").lower() == email.strip().lower():
                target = item
                break

        if not target:
            # التحقق هل هو في السلة
            trash = _get_trash()
            for t in trash:
                if t.get("email", "").lower() == email.strip().lower() and int(t.get("original_user_id", 0)) == int(user_id):
                    # استرجاعه تلقائياً
                    return restore_deleted_email(email, target_user_id=user_id)
            return None

        data["users"][uid_str] = dict(target)
        _atomic_write_json(TEMP_EMAILS_FILE, data)
        _notify_persistence("tempmail_switched")
        return target


def get_user_history(user_id: int, limit: int = 15) -> list[dict[str, Any]]:
    """جلب سجل الإيميلات السابقة للمستخدم مع إزالة التكرارات بالبريد وتضمين عدد الرسائل المؤرشفة"""
    with _tm_lock:
        data = _get_data()
        mb_map = data.get("mailbox_messages", {})
        seen = set()
        result = []
        for item in data.get("history", []):
            if int(item.get("user_id", 0)) == int(user_id):
                em = item.get("email", "").lower()
                if em and em not in seen:
                    seen.add(em)
                    item_copy = dict(item)
                    item_copy["msg_count"] = len(mb_map.get(em, []))
                    result.append(item_copy)
                    if len(result) >= limit:
                        break
        return result


def get_mailbox_messages(email: str) -> list[dict[str, Any]]:
    """جلب كافة الرسائل المحفوظة والمؤرشفة لصندوق بريد محدد"""
    if not email:
        return []
    with _tm_lock:
        data = _get_data()
        return list(data.get("mailbox_messages", {}).get(email.lower().strip(), []))


def get_mailbox_message_count(email: str) -> int:
    """جلب عدد الرسائل المستلمة لصندوق بريد محدد"""
    if not email:
        return 0
    with _tm_lock:
        data = _get_data()
        return len(data.get("mailbox_messages", {}).get(email.lower().strip(), []))


def delete_user_email(user_id: int, email: str, deleted_by: int = 0) -> bool:
    """
    حذف ناعم للإيميل (Soft-Delete):
    يُنقل البريد بكافة توكناته وبياناته إلى trash_emails.json
    ويُرفع من الصندوق النشط، لحمايته من الضياع العفوي وتمكين المطور من استرجاعه بضغطة واحدة.
    """
    with _tm_lock:
        data = _get_data()
        trash = _get_trash()
        uid_str = str(user_id)
        clean_email = email.strip().lower()

        # إيجاد السجل في النشط أو الأرشيف
        found_record = None
        active_mb = data["users"].get(uid_str)
        if active_mb and active_mb.get("email", "").lower() == clean_email:
            found_record = active_mb
            # مسح من النشط
            data["users"].pop(uid_str, None)

        # فلترة الأرشيف
        new_hist = []
        for h in data.get("history", []):
            if int(h.get("user_id", 0)) == int(user_id) and h.get("email", "").lower() == clean_email:
                if not found_record:
                    found_record = h
            else:
                new_hist.append(h)
        data["history"] = new_hist

        if not found_record:
            # بريد تجريبي أو غير مسجل في القائمة
            found_record = {
                "email": clean_email,
                "provider": "1timetech",
                "token": "",
                "domain": clean_email.split("@")[-1] if "@" in clean_email else "",
                "username": clean_email.split("@")[0] if "@" in clean_email else "",
                "user_id": int(user_id),
                "created_at": datetime.datetime.now().isoformat()
            }

        # نقل إلى سلة المحذوفات
        now = datetime.datetime.now().isoformat()
        trash_record = {
            **found_record,
            "original_user_id": int(user_id),
            "deleted_by": int(deleted_by) if deleted_by else int(user_id),
            "deleted_at": now
        }
        # تجنب التكرار في السلة
        trash = [t for t in trash if t.get("email", "").lower() != clean_email]
        trash.insert(0, trash_record)
        trash = trash[:200]

        _atomic_write_json(TEMP_EMAILS_FILE, data)
        _atomic_write_json(TRASH_EMAILS_FILE, trash)
        _notify_persistence("tempmail_deleted_to_trash")
        return True


def restore_deleted_email(email: str, target_user_id: int | None = None, restored_by: int = 0) -> dict[str, Any] | None:
    """
    استرجاع فوري من سلة المحذوفات (1-Tap Recovery Vault):
    يُعاد البريد إلى قائمة المستخدم النشط والأرشيف بكل أمان.
    """
    with _tm_lock:
        trash = _get_trash()
        clean_email = email.strip().lower()
        target_item = None
        new_trash = []
        for t in trash:
            if t.get("email", "").lower() == clean_email:
                target_item = t
            else:
                new_trash.append(t)

        if not target_item:
            return None

        # تحديد المستخدم المستهدف
        dest_uid = int(target_user_id) if target_user_id is not None else int(target_item.get("original_user_id", 0))
        if dest_uid <= 0:
            dest_uid = int(restored_by) if restored_by else 0

        data = _get_data()
        restored_record = {
            "id": target_item.get("id") or hashlib.sha1(f"{dest_uid}_{clean_email}".encode()).hexdigest()[:12],
            "user_id": dest_uid,
            "email": clean_email,
            "provider": target_item.get("provider", "1timetech"),
            "token": target_item.get("token", ""),
            "domain": target_item.get("domain", clean_email.split("@")[-1] if "@" in clean_email else ""),
            "username": target_item.get("username", clean_email.split("@")[0] if "@" in clean_email else ""),
            "created_at": target_item.get("created_at", datetime.datetime.now().isoformat()),
            "restored_at": datetime.datetime.now().isoformat(),
            "auto_notify": True
        }

        if dest_uid > 0:
            data["users"][str(dest_uid)] = restored_record
        data["history"].insert(0, restored_record)
        data["history"] = data["history"][:300]

        _atomic_write_json(TEMP_EMAILS_FILE, data)
        _atomic_write_json(TRASH_EMAILS_FILE, new_trash)
        _notify_persistence("tempmail_restored_from_trash")
        return restored_record


def check_inbox(user_id: int, email: str | None = None) -> list[dict[str, Any]]:
    """
    فحص البريد الوارد لصندوق المستخدم:
    يجلب الرسائل، يستخرج أكواد التحقق OTP وروابط التفعيل، ويسجل الرسائل المقروءة.
    """
    with _tm_lock:
        data = _get_data()
        active = data["users"].get(str(user_id))
        target_email = email or (active.get("email") if active else None)
        if not target_email:
            return []

        provider = active.get("provider", "1timetech") if (active and active.get("email") == target_email) else "1timetech"
        token = active.get("token", "") if (active and active.get("email") == target_email) else ""

        # إذا لم يتم العثور على المزود في النشط، ابحث في الأرشيف
        if not token:
            for h in data.get("history", []):
                if h.get("email", "").lower() == target_email.strip().lower():
                    provider = h.get("provider", provider)
                    token = h.get("token", token)
                    break

    # استدعاء المحرك المباشر عبر master_suite أولاً ثم MailEngineManager
    raw_messages = []
    try:
        mail_obj = {
            "email": target_email,
            "engine": "tempmail_net" if provider != "smailpro" else "smailpro",
            "code": token,
            "token": token,
            "jwt_key": token
        }
        raw_messages = master_suite.fetch_inbox(mail_obj)
    except Exception:
        raw_messages = []

    if not raw_messages:
        try:
            raw_messages = MailEngineManager.check_inbox(target_email, provider, token)
        except Exception:
            raw_messages = []

    parsed_messages = []

    with _tm_lock:
        data = _get_data()
        uid_str = str(user_id)
        seen_list = set(data["seen_messages"].get(uid_str, []))
        em_key = target_email.lower().strip()
        mb_history = data.setdefault("mailbox_messages", {}).setdefault(em_key, [])

        for msg in raw_messages:
            msg_id = str(msg.get("id", ""))
            body_text = msg.get("body_text", "")
            body_html = msg.get("body_html", "")
            subject = msg.get("subject", "")

            # استخراج كود الـ OTP وروابط التفعيل
            otp_code = OtpExtractor.extract_otp(f"{subject} {body_text}", body_html)
            links = OtpExtractor.extract_links(body_text, body_html)

            is_new = msg_id not in seen_list
            if msg_id:
                seen_list.add(msg_id)

            p_item = {
                "id": msg_id,
                "sender": msg.get("sender", "Unknown"),
                "subject": subject,
                "date": msg.get("date", ""),
                "body_text": body_text,
                "body_html": body_html,
                "otp_code": otp_code,
                "links": links,
                "is_new": is_new,
                "email": target_email
            }
            parsed_messages.append(p_item)

            # دمج وتحديث الرسائل في الأرشيف الدائم لصندوق هذا البريد بالتحديد لمنع فقدان الأكواد نهائياً
            existing_idx = None
            for idx_h, h_item in enumerate(mb_history):
                if str(h_item.get("id", "")) == msg_id:
                    existing_idx = idx_h
                    break
            if existing_idx is None:
                mb_history.insert(0, p_item)
            else:
                # تحديث الرسالة القديمة بالأكواد والنصوص الأحدث إن كانت فارغة أو مقتضبة
                if not mb_history[existing_idx].get("otp_code") and otp_code:
                    mb_history[existing_idx]["otp_code"] = otp_code
                if len(body_text) > len(mb_history[existing_idx].get("body_text", "")):
                    mb_history[existing_idx]["body_text"] = body_text
                if body_html and not mb_history[existing_idx].get("body_html"):
                    mb_history[existing_idx]["body_html"] = body_html
                if links and not mb_history[existing_idx].get("links"):
                    mb_history[existing_idx]["links"] = links

        data["seen_messages"][uid_str] = list(seen_list)[-300:]

        # إذا كانت الاستجابة المباشرة فارغة، نعيد الرسائل المحفوظة في الصندوق الدائم لهذا البريد
        if not parsed_messages and mb_history:
            parsed_messages = list(mb_history)

        _atomic_write_json(TEMP_EMAILS_FILE, data)

    return parsed_messages


def list_all_emails_admin(viewer_id: int) -> list[dict[str, Any]]:
    """
    بريد المستخدمين:
    عرض الإيميلات المنشأة لجميع المستخدمين.
    """
    with _tm_lock:
        data = _get_data()
        users_map = data.get("users", {})
        history = data.get("history", [])

        # تجميع أحدث البيانات لكل إيميل
        combined: list[dict[str, Any]] = []
        seen_emails = set()

        # 1. الحسابات النشطة حالياً
        for uid_str, mb in users_map.items():
            em = mb.get("email", "").lower()
            if em and em not in seen_emails:
                seen_emails.add(em)
                combined.append({
                    **mb,
                    "is_active": True,
                    "user_id": int(uid_str)
                })

        # 2. بقية الأرشيف
        for h in history:
            em = h.get("email", "").lower()
            if em and em not in seen_emails:
                seen_emails.add(em)
                combined.append({
                    **h,
                    "is_active": False
                })

        return combined


def list_trash_emails_admin(viewer_id: int) -> list[dict[str, Any]]:
    """استرجاع الإيميلات المحذوفة للمطور"""
    with _tm_lock:
        return _get_trash()


def get_telemetry_stats() -> dict[str, int]:
    """إحصائيات النظام"""
    with _tm_lock:
        data = _get_data()
        trash = _get_trash()
        return {
            "active_users_with_mail": len(data.get("users", {})),
            "total_history_emails": len(data.get("history", [])),
            "trash_emails_count": len(trash),
            "seen_messages_count": sum(len(v) for v in data.get("seen_messages", {}).values())
        }


# ==============================================================================
# إدارة البريد المميز (SmailPro VIP Engine) والحذف التلقائي بعد 5 دقائق
# ==============================================================================
_vip_timers: dict[str, threading.Timer] = {}


def get_vip_cookie() -> str | None:
    """جلب كوكيز SmailPro المحفوظة إما من متغيرات البيئة أو إعدادات المشرف"""
    cookie = os.environ.get("SMAILPRO_COOKIE", "").strip()
    if cookie:
        return cookie
    data = _get_data()
    return data.get("smailpro_cookie")


def set_vip_cookie(cookie_str: str) -> None:
    """تحديث كوكيز SmailPro"""
    with _tm_lock:
        data = _get_data()
        data["smailpro_cookie"] = cookie_str.strip()
        _atomic_write_json(TEMP_EMAILS_FILE, data)
        _notify_persistence("smailpro_cookie_updated")


def create_vip_email(user_id: int, domain: str = "gmail.com", session_cookie: str | None = None, auto_delete_sec: int = 300, on_expired_callback: Any = None) -> dict[str, Any]:
    """
    إنشاء بريد معتمد (Gmail أو Outlook أو بديل فوري معتمد مثل deepmails.org)
    بدون أي أخطاء أو تعليق، مع التبديل التلقائي الذكي.
    """
    effective_cookie = session_cookie or get_vip_cookie()
    with _tm_lock:
        if effective_cookie and not master_suite.smailpro.has_cookies:
            master_suite.smailpro.set_cookies(effective_cookie)

        # توليد البريد عبر المحرك الذكي
        res = master_suite.generate_email(domain)
        if not res or not res.get("success"):
            res = master_suite.generate_email("deepmails.org")

        now_dt = datetime.datetime.now()
        now_ts = now_dt.timestamp()
        clean_email = res.get("email", f"user_{int(now_ts)%10000}@deepmails.org").strip().lower()
        code = res.get("code") or res.get("token") or res.get("jwt_key", "")

        mailbox_record = {
            "id": hashlib.sha1(f"{user_id}_{clean_email}_{now_ts}".encode()).hexdigest()[:12],
            "user_id": int(user_id),
            "email": clean_email,
            "provider": res.get("engine", "tempmail_net"),
            "token": code,
            "code": code,
            "jwt_key": res.get("jwt_key", ""),
            "domain": res.get("domain", clean_email.split("@")[-1]),
            "username": clean_email.split("@")[0],
            "created_at": now_dt.isoformat(),
            "created_ts": now_ts,
            "expires_at_ts": (now_ts + auto_delete_sec) if auto_delete_sec else None,
            "is_vip": True,
            "used": False,
            "auto_notify": True
        }

        data = _get_data()
        data["users"][str(user_id)] = mailbox_record
        data["history"].insert(0, mailbox_record)
        data["history"] = data["history"][:300]
        _atomic_write_json(TEMP_EMAILS_FILE, data)
        _notify_persistence("tempmail_vip_created")

        if auto_delete_sec and on_expired_callback:
            _schedule_vip_auto_cleanup(user_id, clean_email, auto_delete_sec, on_expired_callback)

        return mailbox_record


def _schedule_vip_auto_cleanup(user_id: int, email: str, delay_sec: int = 300, on_expired_callback: Any = None) -> None:
    """جدولة مؤقت الحذف التلقائي بعد انتهاء المهلة"""
    clean_email = email.strip().lower()
    old_timer = _vip_timers.pop(clean_email, None)
    if old_timer:
        try:
            old_timer.cancel()
        except Exception:
            pass

    def _worker():
        try:
            _execute_vip_auto_cleanup(user_id, clean_email, on_expired_callback)
        except Exception as e:
            print(f"[VIP TempMail Expiry Error] {e}")

    t = threading.Timer(delay_sec, _worker)
    t.daemon = True
    _vip_timers[clean_email] = t
    t.start()


def _execute_vip_auto_cleanup(user_id: int, email: str, on_expired_callback: Any = None) -> None:
    """تنفيذ الحذف التلقائي واستدعاء delete_email على خادم المزود إن لم يُستخدم البريد"""
    clean_email = email.strip().lower()
    with _tm_lock:
        data = _get_data()
        uid_str = str(user_id)
        active = data.get("users", {}).get(uid_str)

        # التحقق هل البريد لا يزال هو النشط
        if not active or active.get("email", "").lower() != clean_email:
            return

        # التحقق هل تم استخدامه (استلام رسائل أو تأكيد الاستخدام)
        msg_count = len(data.get("mailbox_messages", {}).get(clean_email, []))
        if active.get("used") or msg_count > 0:
            return

    # 1. استدعاء دالة الحذف على خادم SmailPro لتحرير الخانة للعامة
    cookie = get_vip_cookie()
    MailEngineManager.delete_mailbox(clean_email, provider="smailpro", session_cookie=cookie)

    # 2. نقله محلياً إلى سلة المحذوفات
    delete_user_email(user_id, clean_email, deleted_by=0)

    # 3. إشعار المستخدم عبر التليجرام
    if on_expired_callback:
        try:
            on_expired_callback(user_id, clean_email)
        except Exception:
            pass


def mark_vip_email_used(user_id: int, email: str) -> None:
    """تحديد أن المستخدم استخدم البريد المميز لمنع حذفه التلقائي"""
    clean_email = email.strip().lower()
    with _tm_lock:
        data = _get_data()
        uid_str = str(user_id)
        active = data.get("users", {}).get(uid_str)
        if active and active.get("email", "").lower() == clean_email:
            active["used"] = True
            _atomic_write_json(TEMP_EMAILS_FILE, data)

