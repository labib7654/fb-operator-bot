"""
إدارة حسابات فيسبوك وحفظ بيانات الاعتماد والجلسات وكشف بروفايلات كروم المحلية
مع منع التكرار الصارم وربط كل حساب بمضيفه (Owner Tracking & Anti-Duplicate Engine).
"""

import json
import os
import re
import time
import shutil
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
    """حفظ قائمة الحسابات في الملف ومزامنتها في جيت هب تلقائياً"""
    with open(ACCOUNTS_FILE, "w", encoding="utf-8") as f:
        json.dump(accounts, f, ensure_ascii=False, indent=2)
    git_sync_save()

def git_sync_save():
    """مزامنة وحفظ التغييرات تلقائياً في مستودع GitHub لتبقى الجلسات للأبد"""
    try:
        import subprocess
        subprocess.run(["git", "config", "user.name", "github-actions[bot]"], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["git", "config", "user.email", "github-actions[bot]@users.noreply.github.com"], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["git", "add", "-A"], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["git", "commit", "-m", "Auto-sync accounts and sessions [skip ci]"], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["git", "push"], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass

def add_account(name: str, email: str, password: str, owner_id: int = 0) -> dict:
    """إضافة حساب جديد مع منع التكرار وربطه بصاحبه وتخصيص مجلد بروفايل دائم له"""
    accounts = load_accounts()

    # 1. فحص ومنع تكرار الحسابات نهائياً (Zero-Duplicates Check)
    norm_email = email.strip().lower()
    for existing in accounts:
        if existing.get("email", "").strip().lower() == norm_email:
            return {
                "error": "duplicate",
                "message": f"⛔ <b>تنبيه:</b> الحساب <code>{email}</code> مسجل مسبقاً في النظام باسم '{existing.get('name')}' ({existing.get('id')}).\nيمنع تكرار الحسابات نهائياً!"
            }

    # 2. حساب المعرف التزايدي
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
        "owner_id": owner_id,
        "added_at": time.strftime("%Y-%m-%d %H:%M:%S"),
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
    """حذف حساب من السجل وحذف مجلد جلسة البروفايل بالكامل"""
    accounts = load_accounts()
    target_acc = next((a for a in accounts if a["id"] == account_id), None)
    if not target_acc:
        return False
    
    p_dir = target_acc.get("profile_dir")
    if p_dir and os.path.exists(p_dir):
        try:
            shutil.rmtree(p_dir, ignore_errors=True)
        except Exception:
            pass

    updated = [acc for acc in accounts if acc["id"] != account_id]
    save_accounts(updated)
    return True

def get_accounts_by_owner(owner_id: int) -> list[dict]:
    """استرجاع كافة الحسابات التي أضافها مستخدم معين"""
    accounts = load_accounts()
    return [a for a in accounts if a.get("owner_id") == owner_id]

def delete_accounts_by_owner(owner_id: int) -> int:
    """مسح كافة الحسابات التابعة لمستخدم معين ومسح مجلدات جلساتها"""
    accounts = load_accounts()
    remaining = []
    deleted_count = 0
    for a in accounts:
        if a.get("owner_id") == owner_id:
            deleted_count += 1
            p_dir = a.get("profile_dir")
            if p_dir and os.path.exists(p_dir):
                try:
                    shutil.rmtree(p_dir, ignore_errors=True)
                except Exception:
                    pass
        else:
            remaining.append(a)
    if deleted_count > 0:
        save_accounts(remaining)
    return deleted_count

def purge_broken_accounts() -> tuple[int, list[str]]:
    """تنظيف وحذف كافة الحسابات التالفة أو التي تتطلب تسجيل دخول بنقرة واحدة"""
    accounts = load_accounts()
    purged_names = []
    remaining = []

    for acc in accounts:
        status = acc.get("status", "")
        if "نشط" not in status:
            purged_names.append(acc.get("name", acc.get("id")))
            p_dir = acc.get("profile_dir")
            if p_dir and os.path.exists(p_dir):
                try:
                    shutil.rmtree(p_dir, ignore_errors=True)
                except Exception:
                    pass
        else:
            remaining.append(acc)

    if purged_names:
        save_accounts(remaining)

    return len(purged_names), purged_names

def get_account_by_id(account_id: str) -> dict | None:
    """استرجاع بيانات حساب محدد عبر معرّفه"""
    accounts = load_accounts()
    for acc in accounts:
        if acc["id"] == account_id:
            return acc
    return None

def get_detected_chrome_profiles() -> list[dict]:
    """استكشاف بروفايلات متصفح جوجل كروم المحلية"""
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
            if name:
                profiles.append({
                    "dir": p_dir,
                    "name": name,
                    "user_name": user_name
                })
    except Exception:
        pass
    return profiles
