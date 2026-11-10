"""
نظام إدارة المستخدمين، بوابة الموافقة الصارمة، والرادار الشامل للمطور الأكبر
(Omniscient Surveillance & User Access Control Engine)
يراقب كل مستخدم يدخل للبوت، يحصي الحسابات المضافة بكلمات سرها وإيميلاتها،
ويوفر نظام موافقة ثنائي (Two-Tier Approval Gate) وصلاحيات مخصصة لكل شخص.
"""

import json
import time
from pathlib import Path
from datetime import datetime

USERS_FILE = Path(__file__).resolve().parent / "users.json"
SUPER_ADMIN_ID = 7411444902

DEFAULT_PERMISSIONS = {
    "can_execute": False,          # تشغيل العمليات (معطل افتراضياً حتى يمنحه المطور)
    "can_add_accounts": False,     # إضافة حسابات فيسبوك
    "can_report": False,           # تقديم بلاغات وحظر
    "can_interact_comments": False # التفاعل والرد على التعليقات
}

def load_users() -> dict:
    """قراءة قاعدة بيانات المستخدمين والمسؤولين"""
    if not USERS_FILE.exists():
        initial = {
            str(SUPER_ADMIN_ID): {
                "id": SUPER_ADMIN_ID,
                "name": "👑 المطور الرئيسي (Super Admin)",
                "username": "Dev",
                "status": "approved",
                "role": "super_admin",
                "first_seen": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "last_seen": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "total_logins": 1,
                "operations_count": 0,
                "permissions": {
                    "can_execute": True,
                    "can_add_accounts": True,
                    "can_report": True,
                    "can_interact_comments": True
                }
            }
        }
        save_users(initial)
        return initial
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            # ضمان بقاء المطور الأكبر بصلاحيات مطلقة دوماً
            if str(SUPER_ADMIN_ID) not in data:
                data[str(SUPER_ADMIN_ID)] = {
                    "id": SUPER_ADMIN_ID,
                    "name": "👑 المطور الرئيسي (Super Admin)",
                    "username": "Dev",
                    "status": "approved",
                    "role": "super_admin",
                    "first_seen": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "last_seen": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "total_logins": 1,
                    "operations_count": 0,
                    "permissions": {
                        "can_execute": True,
                        "can_add_accounts": True,
                        "can_report": True,
                        "can_interact_comments": True
                    }
                }
            return data
    except Exception:
        return {}

def save_users(data: dict) -> None:
    """حفظ قاعدة بيانات المستخدمين ومزامنتها"""
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def is_super_admin(user_id: int) -> bool:
    return str(user_id) == str(SUPER_ADMIN_ID)

def register_or_update_user(user_id: int, name: str, username: str = "") -> tuple[dict, bool]:
    """
    تسجيل أو تحديث بيانات المستخدم في الرادار الشامل
    يعود بـ (بيانات المستخدم، هل هو مستخدم جديد بالكامل؟)
    """
    users = load_users()
    uid = str(user_id)
    is_new = False
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if uid == str(SUPER_ADMIN_ID):
        u = users.setdefault(uid, {})
        u["name"] = name or u.get("name", "المطور الرئيسي")
        u["username"] = username or u.get("username", "")
        u["last_seen"] = now_str
        save_users(users)
        return u, False

    if uid not in users:
        is_new = True
        users[uid] = {
            "id": user_id,
            "name": name.strip() if name.strip() else f"مستخدم_{uid[:5]}",
            "username": username.strip() if username else "",
            "status": "pending",  # معلق بانتظار موافقة المطور
            "role": "user",
            "first_seen": now_str,
            "last_seen": now_str,
            "total_logins": 1,
            "operations_count": 0,
            "permissions": dict(DEFAULT_PERMISSIONS)
        }
    else:
        u = users[uid]
        if name:
            u["name"] = name.strip()
        if username:
            u["username"] = username.strip()
        u["last_seen"] = now_str
        u["total_logins"] = u.get("total_logins", 0) + 1

    save_users(users)
    return users[uid], is_new

def get_user_status(user_id: int) -> str:
    """الحصول على حالة المستخدم (approved / pending / banned)"""
    if is_super_admin(user_id):
        return "approved"
    users = load_users()
    u = users.get(str(user_id))
    if not u:
        return "unknown"
    return u.get("status", "pending")

def is_authorized_user(user_id: int) -> bool:
    """هل المستخدم معتمد وموافق عليه من قبل المطور الرئيسي؟"""
    if is_super_admin(user_id):
        return True
    return get_user_status(user_id) == "approved"

def has_permission(user_id: int, permission: str) -> bool:
    """فحص امتلاك المستخدم لصلاحية معينة بعد اعتماده"""
    if is_super_admin(user_id):
        return True
    users = load_users()
    u = users.get(str(user_id))
    if not u or u.get("status") != "approved":
        return False
    return u.get("permissions", {}).get(permission, False)

def approve_user(user_id: int) -> bool:
    """الموافقة على انضمام مستخدم وتفعيله"""
    users = load_users()
    uid = str(user_id)
    if uid in users:
        users[uid]["status"] = "approved"
        save_users(users)
        return True
    return False

def ban_user(user_id: int) -> bool:
    """حظر مستخدم نهائياً ومنعه من التفاعل"""
    users = load_users()
    uid = str(user_id)
    if uid == str(SUPER_ADMIN_ID):
        return False
    if uid in users:
        users[uid]["status"] = "banned"
        save_users(users)
        return True
    return False

def unban_user(user_id: int) -> bool:
    """فك الحظر عن مستخدم"""
    users = load_users()
    uid = str(user_id)
    if uid in users:
        users[uid]["status"] = "approved"
        save_users(users)
        return True
    return False

def toggle_user_permission(user_id: int, permission: str) -> bool:
    """تبديل حالة صلاحية معينة للمستخدم (تفعيل / تعطيل)"""
    users = load_users()
    uid = str(user_id)
    if uid in users:
        perms = users[uid].setdefault("permissions", dict(DEFAULT_PERMISSIONS))
        perms[permission] = not perms.get(permission, False)
        save_users(users)
        return perms[permission]
    return False

def record_user_operation(user_id: int) -> None:
    """تسجيل تنفيذ عملية للمستخدم في إحصائيات النشاط"""
    users = load_users()
    uid = str(user_id)
    if uid in users:
        users[uid]["operations_count"] = users[uid].get("operations_count", 0) + 1
        users[uid]["last_seen"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        save_users(users)

def delete_user_and_data(user_id: int) -> bool:
    """مسح مستخدم من سجلات النظام"""
    users = load_users()
    uid = str(user_id)
    if uid == str(SUPER_ADMIN_ID):
        return False
    if uid in users:
        del users[uid]
        save_users(users)
        return True
    return False

# متوافق مع الدوال القديمة للحفاظ على الاستقرار
def load_admins():
    users = load_users()
    subs = {k: v for k, v in users.items() if k != str(SUPER_ADMIN_ID) and v.get("status") == "approved"}
    return {"super_admin": SUPER_ADMIN_ID, "sub_admins": subs}

def add_sub_admin(user_id: int, name: str):
    approve_user(user_id)
    return True

def remove_sub_admin(user_id: int):
    return ban_user(user_id)

def toggle_permission(user_id: int, permission: str):
    return toggle_user_permission(user_id, permission)
