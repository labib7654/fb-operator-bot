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

USERS_FILE = Path(__file__).resolve().parent / "users.json"
AUDIT_LOG_FILE = Path(__file__).resolve().parent / "audit_logs.json"

_users_lock = threading.RLock()
_audit_lock = threading.RLock()

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
    "can_execute": False              # تشغيل زر الإطلاق الميداني
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
    "can_execute": "التنفيذ الميداني (الإطلاق)"
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


def _build_super_profile(existing: dict | None = None) -> dict:
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    existing = existing or {}
    return {
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
        "permissions": dict(ALL_TRUE_PERMISSIONS)
    }


def load_users() -> dict:
    """قراءة قاعدة بيانات المستخدمين والمسؤولين مع حماية حصانة المطور الأكبر ومنع تصعيد الرتب"""
    with _users_lock:
        if not USERS_FILE.exists():
            initial = {str(SUPER_ADMIN_ID): _build_super_profile()}
            _atomic_write_json(USERS_FILE, initial)
            return initial
        try:
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
    """حفظ قاعدة بيانات المستخدمين بصورة ذرية مع فرض سلامة المطور الأكبر"""
    with _users_lock:
        # إعادة التحقق الحتمي قبل الكتابة على القرص منعاً لأي تلاعب عارض بالذاكرة
        existing_super = data.get(str(SUPER_ADMIN_ID))
        data[str(SUPER_ADMIN_ID)] = _build_super_profile(existing_super if isinstance(existing_super, dict) else None)
        for k, v in data.items():
            if k != str(SUPER_ADMIN_ID) and isinstance(v, dict):
                v["role"] = "user"
        _atomic_write_json(USERS_FILE, data)
    if sync_git:
        git_sync_save(async_mode=True)


def register_or_update_user(user_id: int, name: str, username: str = "", touch_login: bool = True) -> tuple[dict, bool]:
    """
    تسجيل أو تحديث بيانات المستخدم في الرادار الشامل.
    يعود بـ (بيانات المستخدم، هل هو مستخدم جديد؟)
    """
    with _users_lock:
        users = load_users()
        uid = str(int(user_id))
        is_new = False
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
            return dict(u), False

        if uid not in users:
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
                "permissions": dict(DEFAULT_PERMISSIONS)
            }
            save_users(users, sync_git=True)
            record_audit_log(int(user_id), users[uid]["name"], "JOIN_REQUEST", "دخول مستخدم جديد وطلب موافقة المطور")
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

        return dict(users[uid]), is_new


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
    with _users_lock:
        users = load_users()
        uid = str(int(user_id))
        if uid in users:
            users[uid]["status"] = "approved"
            users[uid]["role"] = "user"
            # ضمان بقاء الصلاحيات كما يختارها المطور (لا يُفتح شيء تلقائياً)
            perms = users[uid].get("permissions", {})
            users[uid]["permissions"] = {pk: bool(perms.get(pk, False)) for pk in DEFAULT_PERMISSIONS}
            save_users(users, sync_git=True)
            record_audit_log(int(user_id), users[uid].get("name", ""), "USER_APPROVED", "تم قبول واعتماد المستخدم (كافة الأدوات مغلقة بانتظار التخصيص)")
            return True
    return False


def ban_user(user_id: int) -> bool:
    if is_super_admin(user_id):
        return False  # ممنوع حظر المطور الأكبر مطلقاً
    with _users_lock:
        users = load_users()
        uid = str(int(user_id))
        if uid in users:
            users[uid]["status"] = "banned"
            users[uid]["role"] = "user"
            users[uid]["permissions"] = dict(DEFAULT_PERMISSIONS)
            save_users(users, sync_git=True)
            record_audit_log(int(user_id), users[uid].get("name", ""), "USER_BANNED", "تم حظر المستخدم وتجريده من كافة الصلاحيات")
            return True
    return False


def unban_user(user_id: int) -> bool:
    if is_super_admin(user_id):
        return True
    with _users_lock:
        users = load_users()
        uid = str(int(user_id))
        if uid in users:
            users[uid]["status"] = "approved"
            users[uid]["role"] = "user"
            users[uid]["permissions"] = dict(DEFAULT_PERMISSIONS)  # إعادة فك الحظر مع صلاحيات مغلقة للأمان
            save_users(users, sync_git=True)
            record_audit_log(int(user_id), users[uid].get("name", ""), "USER_UNBANNED", "تم فك الحظر عن المستخدم مع إبقاء الصلاحيات مقفلة للأمان")
            return True
    return False


def toggle_user_permission(user_id: int, permission: str) -> bool:
    if is_super_admin(user_id):
        return True  # صلاحيات المطور الأكبر مطلقة ولا تتغير
    if permission not in DEFAULT_PERMISSIONS:
        return False
    with _users_lock:
        users = load_users()
        uid = str(int(user_id))
        if uid in users:
            perms = users[uid].setdefault("permissions", dict(DEFAULT_PERMISSIONS))
            perms[permission] = not perms.get(permission, False)
            save_users(users, sync_git=True)
            state_str = "تفعيل" if perms[permission] else "تعطيل"
            perm_ar = PERMISSION_LABELS.get(permission, permission)
            record_audit_log(int(user_id), users[uid].get("name", ""), "PERM_CHANGE", f"{state_str} صلاحية ({perm_ar})")
            return perms[permission]
    return False


def revoke_all_permissions(user_id: int) -> bool:
    """إقفال وسحب كافة الصلاحيات الممنوحة لمستخدم بضغطة واحدة"""
    if is_super_admin(user_id):
        return False
    with _users_lock:
        users = load_users()
        uid = str(int(user_id))
        if uid in users:
            users[uid]["permissions"] = dict(DEFAULT_PERMISSIONS)
            save_users(users, sync_git=True)
            record_audit_log(int(user_id), users[uid].get("name", ""), "PERM_RESET", "تصفير وإقفال كافة الصلاحيات الممنوحة للمستخدم")
            return True
    return False


def record_user_operation(user_id: int, op_desc: str = "تشغيل مهمة ميدانية") -> None:
    with _users_lock:
        users = load_users()
        uid = str(int(user_id))
        if uid in users:
            users[uid]["operations_count"] = users[uid].get("operations_count", 0) + 1
            users[uid]["last_seen"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            save_users(users, sync_git=False)
            record_audit_log(int(user_id), users[uid].get("name", ""), "OPERATION", op_desc)


def record_account_result_for_user(user_id: int, is_active: bool) -> None:
    """تسجيل إحصائية الحساب المضاف للمستخدم (هل نشط أم فشل/غير نشط)"""
    with _users_lock:
        users = load_users()
        uid = str(int(user_id))
        if uid in users:
            if is_active:
                users[uid]["active_accounts_added"] = users[uid].get("active_accounts_added", 0) + 1
            else:
                users[uid]["inactive_accounts_added"] = users[uid].get("inactive_accounts_added", 0) + 1
            save_users(users, sync_git=True)


def delete_user_and_data(user_id: int) -> bool:
    if is_super_admin(user_id):
        return False  # ممنوع مسح المطور الأكبر
    with _users_lock:
        users = load_users()
        uid = str(int(user_id))
        if uid in users:
            name = users[uid].get("name", "")
            del users[uid]
            save_users(users, sync_git=True)
            record_audit_log(int(user_id), name, "USER_DELETED", "تم مسح المستخدم بالكامل من النظام")
            return True
    return False


# ----------------- سجل الرقابة والأحداث الكامل (Audit Logs) -----------------

def record_audit_log(user_id: int, user_name: str, event_type: str, details: str) -> None:
    """حفظ سجل رقابي كامل لكل حدث في النظام للمطور الأكبر بأمان تعدد الخيوط"""
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
        except Exception:
            pass


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
