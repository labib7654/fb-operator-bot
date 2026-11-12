"""
نظام إدارة المستخدمين، بوابة الموافقة الصارمة، والرادار الشامل للمطور الأكبر
(Omniscient Surveillance, Strict Granular Permissions & Audit Log Engine)
يضمن سيادة أمنية مطلقة للمطور الأكبر ويمنع أي اختراق أو تصعيد صلاحيات،
ويتحكم بكل أداة وميزة بشكل منفصل مع تسجيل فوري لكل حساب نشط أو فاشل يتم إضافته.
"""

import json
import os
import shutil
import threading
from pathlib import Path
from datetime import datetime
from fb_operator.account_manager import git_sync_save
from fb_operator.config import USERS_FILE, AUDIT_LOG_FILE
from fb_operator.state_events import publish_event

_users_lock = threading.RLock()
_audit_lock = threading.RLock()
_USERS_CACHE_KEY: tuple[str, int, int] | None = None
_USERS_CACHE_DATA: dict = {}

# الآيدي السيادي للمطور الأكبر — محمي برمجياً ولا يمكن تغييره أو انتحاله أبداً
SUPER_ADMIN_ID = 7411444902

# مصفوفة الصلاحيات الدقيقة (كل ميزة مغلقة تماماً افتراضياً حتى يفتحها المطور بنفسه)
DEFAULT_PERMISSIONS = {
    "can_use_accounts": False,        # استخدام حسابات البوت الموجودة في المهام
    "can_add_accounts": False,        # إضافة حسابات فيسبوك جديدة للبوت
    "can_react": False,               # استخدام التفاعلات السبعة والإعجاب وإلغائه
    "can_comment": False,             # كتابة التعليقات واصطياد المنشورات
    "can_interact_comments": False,   # التفاعل والرد على تعليق محدد
    "can_friend_follow": False,       # إرسال وإلغاء طلبات الصداقة والمتابعة
    "can_message": False,             # إرسال رسائل الماسنجر الخاصة
    "can_report": False,              # تقديم البلاغات الرسمية وحظر الحسابات
    "can_delete_accounts": False,     # حذف أو تنظيف الحسابات الخاصة
    "can_execute": False,             # تشغيل زر الإطلاق الميداني
    "can_invite": False               # إنشاء روابط وأكواد إحالة (+4 نقاط)
}

PERMISSION_LABELS = {
    "can_use_accounts": "استخدام حسابات البوت",
    "can_add_accounts": "إضافة حسابات للبوت",
    "can_react": "التفاعلات والإعجاب",
    "can_comment": "كتابة التعليقات",
    "can_interact_comments": "الرد على تعليق محدد",
    "can_friend_follow": "الصداقة والمتابعة",
    "can_message": "الرسائل الخاصة",
    "can_report": "البلاغات والحظر",
    "can_delete_accounts": "حذف الحسابات المضافة",
    "can_execute": "التنفيذ الميداني (الإطلاق)",
    "can_invite": "روابط وأكواد الإحالة"
}

ALL_TRUE_PERMISSIONS = {k: True for k in DEFAULT_PERMISSIONS}


def _atomic_write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + f".tmp.{threading.get_ident()}")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        try:
            os.fsync(f.fileno())
        except Exception:
            pass
    os.replace(tmp_path, path)


def is_super_admin(user_id: int | str) -> bool:
    """التحقق الصارم من الهوية السيادية للمطور الأكبر"""
    if isinstance(user_id, bool):
        return False
    try:
        return int(user_id) == SUPER_ADMIN_ID
    except Exception:
        return False


def _safe_nonneg_int(val, default: int = 0) -> int:
    try:
        return max(0, int(val))
    except Exception:
        return default


def safe_nonneg_points(val, default: int | float = 0) -> int | float:
    """تنظيف رصيد النقاط مع دعم الكسور الدقيقة (مثل 0.5 نقطة = 5 ريال) وإرجاع int متى ما كان عدداً صحيحاً."""
    try:
        v = round(max(0.0, float(val)), 2)
        if abs(v - int(v)) < 1e-9:
            return int(v)
        return v
    except Exception:
        return default


def _ensure_wallet_fields(u: dict) -> None:
    u["points"] = safe_nonneg_points(u.get("points", 0))
    u["total_points_earned"] = safe_nonneg_points(u.get("total_points_earned", 0))
    u["total_points_spent"] = safe_nonneg_points(u.get("total_points_spent", 0))
    u["total_yer_settled"] = _safe_nonneg_int(u.get("total_yer_settled", 0))
    u["referred_by"] = _safe_nonneg_int(u.get("referred_by", 0))
    u["referral_code_used"] = str(u.get("referral_code_used") or "")[:40]
    u["referral_rewarded"] = bool(u.get("referral_rewarded", False))
    u["referred_count"] = _safe_nonneg_int(u.get("referred_count", 0))
    u["ref_code"] = str(u.get("ref_code") or "")[:32]
    u["profile_warnings_used"] = _safe_nonneg_int(u.get("profile_warnings_used", 0))


def _build_super_profile(existing: dict | None = None) -> dict:
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    existing = existing or {}
    prof = {
        "id": SUPER_ADMIN_ID,
        "name": existing.get("name", "👑 المطور الرئيسي (Super Admin)"),
        "username": existing.get("username", "Dev"),
        "status": "approved",
        "role": "super_admin",
        "first_seen": existing.get("first_seen", now_str),
        "last_seen": existing.get("last_seen", now_str),
        "total_logins": existing.get("total_logins", 1),
        "operations_count": existing.get("operations_count", 0),
        "active_accounts_added": existing.get("active_accounts_added", 0),
        "inactive_accounts_added": existing.get("inactive_accounts_added", 0),
        "points": safe_nonneg_points(existing.get("points", 0)),
        "total_points_earned": safe_nonneg_points(existing.get("total_points_earned", 0)),
        "total_points_spent": safe_nonneg_points(existing.get("total_points_spent", 0)),
        "total_yer_settled": _safe_nonneg_int(existing.get("total_yer_settled", 0)),
        "referred_by": 0,
        "referral_code_used": "",
        "referral_rewarded": False,
        "referred_count": _safe_nonneg_int(existing.get("referred_count", 0)),
        "ref_code": str(existing.get("ref_code") or "")[:32],
        "permissions": dict(ALL_TRUE_PERMISSIONS)
    }
    return prof


def _copy_users_snapshot(raw: dict) -> dict:
    out: dict = {}
    for k, v in raw.items():
        if isinstance(v, dict):
            item = dict(v)
            if isinstance(v.get("permissions"), dict):
                item["permissions"] = dict(v["permissions"])
            out[k] = item
        else:
            out[k] = v
    return out


def load_users() -> dict:
    """قراءة قاعدة بيانات المستخدمين مع كاش ذاكرة O(1) وحماية حصانة المطور الأكبر"""
    global _USERS_CACHE_KEY, _USERS_CACHE_DATA
    with _users_lock:
        if not USERS_FILE.exists():
            initial = {str(SUPER_ADMIN_ID): _build_super_profile()}
            _atomic_write_json(USERS_FILE, initial)
            try:
                st = USERS_FILE.stat()
                _USERS_CACHE_KEY = (str(USERS_FILE), int(st.st_mtime_ns), int(st.st_size))
                _USERS_CACHE_DATA = _copy_users_snapshot(initial)
            except Exception:
                _USERS_CACHE_KEY = None
            return initial
        try:
            st = USERS_FILE.stat()
            sig = (str(USERS_FILE), int(st.st_mtime_ns), int(st.st_size))
            if _USERS_CACHE_KEY == sig:
                return _copy_users_snapshot(_USERS_CACHE_DATA)

            with open(USERS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError("Invalid users.json root")

            # ضمان حصانة المطور الأكبر وفرض صلاحياته المطلقة دوماً في الذاكرة
            existing_super = data.get(str(SUPER_ADMIN_ID))
            data[str(SUPER_ADMIN_ID)] = _build_super_profile(existing_super if isinstance(existing_super, dict) else None)

            # التأكد من عدم امتلاك أي مستخدم آخر لرتبة super_admin تحت أي ظرف
            for k, v in list(data.items()):
                if k != str(SUPER_ADMIN_ID):
                    if not isinstance(v, dict):
                        del data[k]
                        continue
                    v["role"] = "user"
                    if v.get("status") not in ("pending", "approved", "banned"):
                        v["status"] = "pending"
                    raw_perms = v.get("permissions")
                    if not isinstance(raw_perms, dict):
                        raw_perms = {}
                    # حصر المفاتيح فقط في المفاتيح الرسمية وفرض False افتراضياً
                    v["permissions"] = {pk: bool(raw_perms.get(pk, False)) for pk in DEFAULT_PERMISSIONS}
                    _ensure_wallet_fields(v)
            _USERS_CACHE_KEY = sig
            _USERS_CACHE_DATA = _copy_users_snapshot(data)
            return data
        except Exception:
            try:
                bak = USERS_FILE.with_suffix(".corrupt.bak")
                if USERS_FILE.exists() and not bak.exists():
                    shutil.copy2(USERS_FILE, bak)
            except Exception:
                pass
            return {str(SUPER_ADMIN_ID): _build_super_profile()}


def save_users(data: dict, sync_git: bool = False) -> None:
    """حفظ قاعدة بيانات المستخدمين ذرياً وتحديث كاش الذاكرة فوراً"""
    global _USERS_CACHE_KEY, _USERS_CACHE_DATA
    with _users_lock:
        # إعادة التحقق الحتمي قبل الكتابة على القرص منعاً لأي تلاعب عارض بالذاكرة
        existing_super = data.get(str(SUPER_ADMIN_ID))
        data[str(SUPER_ADMIN_ID)] = _build_super_profile(existing_super if isinstance(existing_super, dict) else None)
        for k, v in data.items():
            if k != str(SUPER_ADMIN_ID) and isinstance(v, dict):
                v["role"] = "user"
        _atomic_write_json(USERS_FILE, data)
        try:
            st = USERS_FILE.stat()
            _USERS_CACHE_KEY = (str(USERS_FILE), int(st.st_mtime_ns), int(st.st_size))
            _USERS_CACHE_DATA = _copy_users_snapshot(data)
        except Exception:
            _USERS_CACHE_KEY = None
    if sync_git:
        git_sync_save(async_mode=True)


def register_or_update_user(user_id: int, name: str, username: str = "", touch_login: bool = True) -> tuple[dict, bool]:
    """
    تسجيل أو تحديث بيانات المستخدم في الرادار الشامل.
    يعود بـ (بيانات المستخدم، هل هو مستخدم جديد؟)
    """
    is_new = False
    should_publish = False
    res_user: dict = {}
    with _users_lock:
        users = load_users()
        uid = str(int(user_id))
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        clean_name = name.strip() if name else ""
        clean_user = username.strip() if username else ""

        if is_super_admin(user_id):
            u = users[str(SUPER_ADMIN_ID)]
            changed = False
            if clean_name and u.get("name") != clean_name:
                u["name"] = clean_name
                changed = True
            if clean_user and u.get("username") != clean_user:
                u["username"] = clean_user
                changed = True
            if touch_login:
                u["last_seen"] = now_str
                u["total_logins"] = u.get("total_logins", 0) + 1
                changed = True
            if changed:
                save_users(users, sync_git=False)
                should_publish = True
            res_user = dict(u)
        elif uid not in users:
            is_new = True
            users[uid] = {
                "id": int(user_id),
                "name": clean_name if clean_name else f"مستخدم_{uid[:5]}",
                "username": clean_user,
                "status": "pending",  # محجوب تماماً بانتظار موافقة المطور
                "role": "user",
                "first_seen": now_str,
                "last_seen": now_str,
                "total_logins": 1,
                "operations_count": 0,
                "active_accounts_added": 0,
                "inactive_accounts_added": 0,
                "points": 0,
                "total_points_earned": 0,
                "total_points_spent": 0,
                "total_yer_settled": 0,
                "referred_by": 0,
                "referral_code_used": "",
                "referral_rewarded": False,
                "referred_count": 0,
                "ref_code": "",
                "permissions": dict(DEFAULT_PERMISSIONS)
            }
            save_users(users, sync_git=True)
            record_audit_log(int(user_id), users[uid]["name"], "JOIN_REQUEST", "دخول مستخدم جديد وطلب موافقة المطور")
            should_publish = True
            res_user = dict(users[uid])
        else:
            u = users[uid]
            changed = u.get("role") != "user"
            u["role"] = "user"  # حظر تصعيد الرتبة نهائياً
            if clean_name and u.get("name") != clean_name:
                u["name"] = clean_name
                changed = True
            if clean_user and u.get("username") != clean_user:
                u["username"] = clean_user
                changed = True
            if touch_login:
                u["last_seen"] = now_str
                u["total_logins"] = u.get("total_logins", 0) + 1
                changed = True
            if changed:
                save_users(users, sync_git=False)
                should_publish = True
            res_user = dict(users[uid])

    if should_publish:
        publish_event("users", int(user_id), "register_or_update")
    return res_user, is_new


def get_user_permissions(user_id: int) -> dict:
    """إرجاع خريطة الصلاحيات الـ 10 للمستخدم بشكل آمن"""
    if is_super_admin(user_id):
        return {k: True for k in DEFAULT_PERMISSIONS}
    users = load_users()
    u = users.get(str(int(user_id)))
    if not u or u.get("status") != "approved" or u.get("role") != "user":
        return dict(DEFAULT_PERMISSIONS)
    raw_perms = u.get("permissions", {})
    return {k: bool(raw_perms.get(k, False)) for k in DEFAULT_PERMISSIONS}


def get_user_status(user_id: int) -> str:
    if is_super_admin(user_id):
        return "approved"
    users = load_users()
    u = users.get(str(int(user_id)))
    return u.get("status", "pending") if u else "unknown"


def is_authorized_user(user_id: int) -> bool:
    if is_super_admin(user_id):
        return True
    return get_user_status(user_id) == "approved"


def has_permission(user_id: int, permission: str) -> bool:
    """فحص الصلاحية الدقيقة لميزة محددة"""
    if is_super_admin(user_id):
        return True
    if permission not in DEFAULT_PERMISSIONS:
        return False
    users = load_users()
    u = users.get(str(int(user_id)))
    if not u or u.get("status") != "approved" or u.get("role") != "user":
        return False
    return bool(u.get("permissions", {}).get(permission, False))


def approve_user(user_id: int) -> bool:
    """اعتماد المستخدم في حالة 'موافق عليه' مع إبقاء كافة الصلاحيات مغلقة افتراضياً"""
    if is_super_admin(user_id):
        return True
    ok = False
    with _users_lock:
        users = load_users()
        uid = str(int(user_id))
        if uid in users:
            users[uid]["status"] = "approved"
            users[uid]["role"] = "user"
            perms = users[uid].get("permissions", {})
            users[uid]["permissions"] = {pk: bool(perms.get(pk, False)) for pk in DEFAULT_PERMISSIONS}
            save_users(users, sync_git=True)
            record_audit_log(int(user_id), users[uid].get("name", ""), "USER_APPROVED", "تم قبول واعتماد المستخدم (كافة الأدوات مغلقة بانتظار التخصيص)")
            ok = True
    if ok:
        publish_event("users", int(user_id), "approve")
    return ok


def ban_user(user_id: int) -> bool:
    if is_super_admin(user_id):
        return False  # ممنوع حظر المطور الأكبر مطلقاً
    ok = False
    with _users_lock:
        users = load_users()
        uid = str(int(user_id))
        if uid in users:
            users[uid]["status"] = "banned"
            users[uid]["role"] = "user"
            users[uid]["permissions"] = dict(DEFAULT_PERMISSIONS)
            save_users(users, sync_git=True)
            record_audit_log(int(user_id), users[uid].get("name", ""), "USER_BANNED", "تم حظر المستخدم وتجريده من كافة الصلاحيات")
            ok = True
    if ok:
        publish_event("users", int(user_id), "ban")
    return ok


def unban_user(user_id: int) -> bool:
    if is_super_admin(user_id):
        return True
    ok = False
    with _users_lock:
        users = load_users()
        uid = str(int(user_id))
        if uid in users:
            users[uid]["status"] = "approved"
            users[uid]["role"] = "user"
            users[uid]["permissions"] = dict(DEFAULT_PERMISSIONS)
            save_users(users, sync_git=True)
            record_audit_log(int(user_id), users[uid].get("name", ""), "USER_UNBANNED", "تم فك الحظر عن المستخدم مع إبقاء الصلاحيات مقفلة للأمان")
            ok = True
    if ok:
        publish_event("users", int(user_id), "unban")
    return ok


def toggle_user_permission(user_id: int, permission: str) -> bool:
    if is_super_admin(user_id):
        return True  # صلاحيات المطور الأكبر مطلقة ولا تتغير
    if permission not in DEFAULT_PERMISSIONS:
        return False
    new_val = False
    changed = False
    with _users_lock:
        users = load_users()
        uid = str(int(user_id))
        if uid in users:
            perms = users[uid].setdefault("permissions", dict(DEFAULT_PERMISSIONS))
            perms[permission] = not perms.get(permission, False)
            new_val = perms[permission]
            changed = True
            save_users(users, sync_git=True)
            state_str = "تفعيل" if new_val else "تعطيل"
            perm_ar = PERMISSION_LABELS.get(permission, permission)
            record_audit_log(int(user_id), users[uid].get("name", ""), "PERM_CHANGE", f"{state_str} صلاحية ({perm_ar})")
    if changed:
        publish_event("users", int(user_id), "perm_toggle")
    return new_val


def revoke_all_permissions(user_id: int) -> bool:
    """إقفال وسحب كافة الصلاحيات الممنوحة لمستخدم بضغطة واحدة"""
    if is_super_admin(user_id):
        return False
    ok = False
    with _users_lock:
        users = load_users()
        uid = str(int(user_id))
        if uid in users:
            users[uid]["permissions"] = dict(DEFAULT_PERMISSIONS)
            save_users(users, sync_git=True)
            record_audit_log(int(user_id), users[uid].get("name", ""), "PERM_RESET", "تصفير وإقفال كافة الصلاحيات الممنوحة للمستخدم")
            ok = True
    if ok:
        publish_event("users", int(user_id), "revoke_all")
    return ok


def record_user_operation(user_id: int, op_desc: str = "تشغيل مهمة ميدانية") -> None:
    updated = False
    with _users_lock:
        users = load_users()
        uid = str(int(user_id))
        if uid in users:
            users[uid]["operations_count"] = users[uid].get("operations_count", 0) + 1
            users[uid]["last_seen"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            save_users(users, sync_git=False)
            record_audit_log(int(user_id), users[uid].get("name", ""), "OPERATION", op_desc)
            updated = True
    if updated:
        publish_event("users", int(user_id), "operation")


def record_account_result_for_user(user_id: int, is_active: bool) -> None:
    """تسجيل إحصائية الحساب المضاف للمستخدم (هل نشط أم فشل/غير نشط)"""
    updated = False
    with _users_lock:
        users = load_users()
        uid = str(int(user_id))
        if uid in users:
            if is_active:
                users[uid]["active_accounts_added"] = users[uid].get("active_accounts_added", 0) + 1
            else:
                users[uid]["inactive_accounts_added"] = users[uid].get("inactive_accounts_added", 0) + 1
            save_users(users, sync_git=True)
            updated = True
    if updated:
        publish_event("users", int(user_id), "account_result")


def delete_user_and_data(user_id: int) -> bool:
    if is_super_admin(user_id):
        return False  # ممنوع مسح المطور الأكبر
    ok = False
    with _users_lock:
        users = load_users()
        uid = str(int(user_id))
        if uid in users:
            name = users[uid].get("name", "")
            del users[uid]
            save_users(users, sync_git=True)
            record_audit_log(int(user_id), name, "USER_DELETED", "تم مسح المستخدم بالكامل من النظام")
            ok = True
    if ok:
        publish_event("users", int(user_id), "user_delete")
    return ok


# ----------------- سجل الرقابة والأحداث الكامل (Audit Logs) -----------------

def record_audit_log(user_id: int, user_name: str, event_type: str, details: str) -> None:
    """حفظ سجل رقابي كامل لكل حدث في النظام للمطور الأكبر بأمان تعدد الخيوط"""
    written = False
    with _audit_lock:
        try:
            logs = load_audit_logs(limit=0)
            logs.append({
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "user_id": int(user_id),
                "user_name": str(user_name or ""),
                "event": str(event_type),
                "details": str(details)
            })
            if len(logs) > 300:
                logs = logs[-300:]
            _atomic_write_json(AUDIT_LOG_FILE, logs)
            written = True
        except Exception:
            pass
    if written:
        publish_event("audit", int(user_id), str(event_type))


def load_audit_logs(limit: int = 100) -> list[dict]:
    with _audit_lock:
        if not AUDIT_LOG_FILE.exists():
            return []
        try:
            with open(AUDIT_LOG_FILE, "r", encoding="utf-8") as f:
                logs = json.load(f)
            if not isinstance(logs, list):
                return []
            return logs[-limit:] if limit and limit > 0 else logs
        except Exception:
            return []


# دوال متوافقة للحفاظ على استمرارية الكود القديم
def load_admins():
    users = load_users()
    subs = {k: v for k, v in users.items() if k != str(SUPER_ADMIN_ID) and v.get("status") == "approved"}
    return {"super_admin": SUPER_ADMIN_ID, "sub_admins": subs}


def add_sub_admin(user_id: int, name: str):
    return approve_user(user_id)


def remove_sub_admin(user_id: int):
    return ban_user(user_id)


def toggle_permission(user_id: int, permission: str):
    return toggle_user_permission(user_id, permission)


def reset_user_profile_warnings(target_uid: int) -> bool:
    """تصفير عداد إنذارات نقص جودة البروفايل للمستخدم بواسطة المطور الأكبر."""
    tid = str(int(target_uid))
    u_name = ""
    with _users_lock:
        users = load_users()
        u = users.get(tid)
        if not isinstance(u, dict):
            return False
        u_name = str(u.get("name", ""))
        u["profile_warnings_used"] = 0
        save_users(users, sync_git=True)
    record_audit_log(int(target_uid), u_name, "WARNINGS_RESET", "تصفير إنذارات البروفايل (0/5)")
    publish_event("users", int(target_uid), "warnings_reset")
    return True
