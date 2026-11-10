"""
إدارة حسابات فيسبوك وحفظ بيانات الاعتماد والجلسات وكشف بروفايلات كروم المحلية
"""

import json
import os
import re
from pathlib import Path
from fb_operator.config import ACCOUNTS_FILE, PROFILES_DIR

def load_accounts() -> list[dict]:
    """قراءة قائمة الحسابات المسجلة من الملف"""
    if not ACCOUNTS_FILE.exists():
        return []
    try:
        with open(ACCOUNTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def save_accounts(accounts: list[dict]) -> None:
    """حفظ قائمة الحسابات في الملف"""
    with open(ACCOUNTS_FILE, "w", encoding="utf-8") as f:
        json.dump(accounts, f, ensure_ascii=False, indent=2)

def add_account(name: str, email: str, password: str) -> dict:
    """إضافة حساب جديد بمعرف تزايدي آمن وتخصيص مجلد بروفايل دائم له"""
    accounts = load_accounts()
    existing_nums = []
    for a in accounts:
        match = re.search(r"acc_(\d+)", a.get("id", ""))
        if match:
            existing_nums.append(int(match.group(1)))
    next_num = (max(existing_nums) + 1) if existing_nums else 1
    account_id = f"acc_{next_num}"

    profile_path = PROFILES_DIR / account_id
    profile_path.mkdir(parents=True, exist_ok=True)

    new_acc = {
        "id": account_id,
        "name": name.strip() if name.strip() else f"حساب {account_id}",
        "email": email.strip(),
        "password": password.strip(),
        "profile_dir": str(profile_path),
        "status": "مسجل البيانات"
    }
    accounts.append(new_acc)
    save_accounts(accounts)
    return new_acc

def update_account(account_id: str, updates: dict) -> bool:
    """تحديث بيانات أو حالة حساب معين"""
    accounts = load_accounts()
    updated = False
    for acc in accounts:
        if acc["id"] == account_id:
            acc.update(updates)
            updated = True
            break
    if updated:
        save_accounts(accounts)
    return updated

def delete_account(account_id: str) -> bool:
    """حذف حساب من السجل"""
    accounts = load_accounts()
    updated = [acc for acc in accounts if acc["id"] != account_id]
    if len(updated) != len(accounts):
        save_accounts(updated)
        return True
    return False

def get_account_by_id(account_id: str) -> dict | None:
    """استرجاع بيانات حساب محدد عبر معرّفه"""
    accounts = load_accounts()
    for acc in accounts:
        if acc["id"] == account_id:
            return acc
    return None

def get_detected_chrome_profiles() -> list[dict]:
    """
    استكشاف بروفايلات متصفح جوجل كروم المثبتة على جهاز المستخدم
    وقراءة أسمائها وحسابات الجيميل التابعة لها
    """
    profiles = []
    local_state_path = os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\User Data\Local State")
    if not os.path.exists(local_state_path):
        return profiles

    try:
        with open(local_state_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        info_cache = data.get("profile", {}).get("info_cache", {})
        for p_dir, p_info in info_cache.items():
            name = p_info.get("name", "").strip()
            user_name = p_info.get("user_name", "").strip()
            # تجاهل بروفايلات النظام الفارغة إذا رغبنا
            if name:
                profiles.append({
                    "dir": p_dir,
                    "name": name,
                    "user_name": user_name
                })
    except Exception:
        pass
    return profiles
