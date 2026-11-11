"""
إدارة حسابات فيسبوك وحفظ بيانات الاعتماد والجلسات وكشف بروفايلات كروم المحلية
مع منع التكرار الصارم، العزل الأمني بالملكية، وتصنيف الحسابات النشطة والفاشلة،
والكتابة الذرية الآمنة لتعدد الخيوط (Thread-Safe Atomic I/O).
"""

import json
import os
import re
import time
import shutil
import threading
import subprocess
from pathlib import Path
from fb_operator.config import ACCOUNTS_FILE, PROFILES_DIR
from fb_operator.state_events import publish_event

BASE_OPERATOR_DIR = Path(__file__).resolve().parent
_accounts_lock = threading.RLock()
_git_lock = threading.Lock()


def _atomic_write_json(path: Path, data) -> None:
    """كتابة ذرية آمنة تمنع تلف الملفات عند تعدد الخيوط المتزامنة"""
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


def _run_git_sync() -> None:
    """تنفيذ مزامنة Git الآمنة لملفات الحالة والجلسات فقط بدون تضارب خيوط"""
    with _git_lock:
        try:
            cwd = str(BASE_OPERATOR_DIR)
            # التحقق أولاً من وجود مستودع git صالح
            chk = subprocess.run(
                ["git", "rev-parse", "--is-inside-work-tree"],
                cwd=cwd, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            if chk.returncode != 0:
                return

            subprocess.run(["git", "config", "user.name", "github-actions[bot]"], cwd=cwd, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(["git", "config", "user.email", "github-actions[bot]@users.noreply.github.com"], cwd=cwd, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            targets = [name for name in ("accounts.json", "users.json", "audit_logs.json", "profiles") if (BASE_OPERATOR_DIR / name).exists()]
            if not targets:
                return

            subprocess.run(["git", "add", "--"] + targets, cwd=cwd, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            # الالتزام فقط إن كان هناك تغييرات مرحّلة
            diff_chk = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=cwd, check=False)
            if diff_chk.returncode == 0:
                return

            subprocess.run(["git", "commit", "-m", "Auto-sync accounts, permissions, and audit logs [skip ci]"], cwd=cwd, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(["git", "push"], cwd=cwd, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass


def git_sync_save(async_mode: bool = True) -> None:
    """مزامنة وحفظ التغييرات تلقائياً في مستودع GitHub لتبقى الجلسات والصلاحيات دائمة"""
    if async_mode:
        threading.Thread(target=_run_git_sync, daemon=True).start()
    else:
        _run_git_sync()


def load_accounts() -> list[dict]:
    """قراءة قائمة الحسابات المسجلة من الملف بأمان ضد تعدد الخيوط"""
    with _accounts_lock:
        if not ACCOUNTS_FILE.exists():
            return []
        try:
            with open(ACCOUNTS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, list) else []
        except Exception:
            # في حال تلف الملف مؤقتاً نحفظ نسخة احتياطية ولا نعيد الكتابة عشوائياً
            try:
                corrupt_bak = ACCOUNTS_FILE.with_suffix(".corrupt.bak")
                if ACCOUNTS_FILE.exists() and not corrupt_bak.exists():
                    shutil.copy2(ACCOUNTS_FILE, corrupt_bak)
            except Exception:
                pass
            return []


def save_accounts(accounts: list[dict], sync_git: bool = True) -> None:
    """حفظ قائمة الحسابات في الملف بصورة ذرية ومزامنتها في جيت هب"""
    with _accounts_lock:
        _atomic_write_json(ACCOUNTS_FILE, accounts)
    if sync_git:
        git_sync_save(async_mode=True)


def add_account(name: str, email: str, password: str, owner_id: int = 0, owner_name: str = "") -> dict:
    """إضافة حساب جديد مع منع التكرار وربطه بصاحبه وتخصيص مجلد بروفايل دائم له"""
    with _accounts_lock:
        accounts = load_accounts()

        # 1. فحص ومنع تكرار الحسابات نهائياً (Zero-Duplicates Check)
        norm_email = email.strip().lower()
        for existing in accounts:
            if existing.get("email", "").strip().lower() == norm_email:
                return {
                    "error": "duplicate",
                    "existing_id": existing.get("id"),
                    "existing_name": existing.get("name"),
                    "message": "هذا الحساب مسجل مسبقاً في النظام، يمنع تكرار الحسابات نهائياً!"
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
            "owner_id": int(owner_id) if owner_id else 0,
            "owner_name": owner_name.strip() if owner_name else "",
            "added_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "profile_dir": str(profile_path),
            "status": "قيد الفحص والتسجيل",
            "diagnostic_reason": ""
        }
        accounts.append(new_acc)
        save_accounts(accounts, sync_git=False)

    publish_event("accounts", int(owner_id) if owner_id else 0, "account_add")
    return dict(new_acc)


def update_account(account_id: str, updates: dict, sync_git: bool = True) -> bool:
    """تحديث بيانات أو حالة حساب معين بأمان تام"""
    updated = False
    owner_id = 0
    with _accounts_lock:
        accounts = load_accounts()
        for acc in accounts:
            if acc.get("id") == account_id:
                acc.update(updates)
                owner_id = int(acc.get("owner_id") or 0)
                updated = True
                break
        if updated:
            save_accounts(accounts, sync_git=sync_git)
    if updated:
        publish_event("accounts", owner_id, "account_update")
    return updated


def delete_account(account_id: str) -> bool:
    """حذف حساب من السجل وحذف مجلد جلسة البروفايل بالكامل"""
    deleted = False
    owner_id = 0
    with _accounts_lock:
        accounts = load_accounts()
        target_acc = next((a for a in accounts if a.get("id") == account_id), None)
        if not target_acc:
            return False

        owner_id = int(target_acc.get("owner_id") or 0)
        p_dir = target_acc.get("profile_dir")
        if p_dir:
            acc_folder = Path(p_dir).name
            real_p_dir = PROFILES_DIR / acc_folder
            if real_p_dir.exists():
                try:
                    shutil.rmtree(real_p_dir, ignore_errors=True)
                except Exception:
                    pass

        updated = [acc for acc in accounts if acc.get("id") != account_id]
        save_accounts(updated, sync_git=True)
        deleted = True

    if deleted:
        publish_event("accounts", owner_id, "account_delete")
    return True


def get_accounts_by_owner(owner_id: int) -> list[dict]:
    """استرجاع كافة الحسابات التي أضافها مستخدم معين"""
    accounts = load_accounts()
    return [a for a in accounts if a.get("owner_id") == int(owner_id)]


def get_accounts_breakdown_by_owner(owner_id: int) -> dict:
    """استرجاع تصنيف دقيق لحسابات المستخدم: النشطة وغير النشطة مع أسباب الفشل"""
    user_accs = get_accounts_by_owner(owner_id)
    active = [a for a in user_accs if "نشط" in a.get("status", "")]
    inactive = [a for a in user_accs if "نشط" not in a.get("status", "")]
    return {
        "all": user_accs,
        "active": active,
        "inactive": inactive
    }


def delete_accounts_by_owner(owner_id: int) -> int:
    """مسح كافة الحسابات التابعة لمستخدم معين ومسح مجلدات جلساتها"""
    with _accounts_lock:
        accounts = load_accounts()
        remaining = []
        deleted_count = 0
        uid_int = int(owner_id)
        for a in accounts:
            if a.get("owner_id") == uid_int:
                deleted_count += 1
                p_dir = a.get("profile_dir")
                if p_dir:
                    acc_folder = Path(p_dir).name
                    real_p_dir = PROFILES_DIR / acc_folder
                    if real_p_dir.exists():
                        try:
                            shutil.rmtree(real_p_dir, ignore_errors=True)
                        except Exception:
                            pass
            else:
                remaining.append(a)
        if deleted_count > 0:
            save_accounts(remaining, sync_git=True)
    if deleted_count > 0:
        publish_event("accounts", uid_int, "delete_accounts_by_owner")
    return deleted_count


def purge_broken_accounts(owner_id: int | None = None) -> tuple[int, list[str]]:
    """
    تنظيف وحذف كافة الحسابات التالفة أو التي تتطلب تسجيل دخول.
    إذا تم تمرير owner_id يتم تنظيف حسابات هذا المستخدم فقط لضمان عدم المساس بحسابات المطور أو الآخرين.
    """
    purged_names: list[str] = []
    with _accounts_lock:
        accounts = load_accounts()
        remaining = []

        for acc in accounts:
            status = acc.get("status", "")
            in_scope = True if owner_id is None else (acc.get("owner_id") == int(owner_id))
            if in_scope and ("نشط" not in status):
                purged_names.append(acc.get("name", acc.get("id")))
                p_dir = acc.get("profile_dir")
                if p_dir:
                    acc_folder = Path(p_dir).name
                    real_p_dir = PROFILES_DIR / acc_folder
                    if real_p_dir.exists():
                        try:
                            shutil.rmtree(real_p_dir, ignore_errors=True)
                        except Exception:
                            pass
            else:
                remaining.append(acc)

        if purged_names:
            save_accounts(remaining, sync_git=True)

    if purged_names:
        publish_event("accounts", int(owner_id) if owner_id else 0, "purge_broken")
    return len(purged_names), purged_names


def get_account_by_id(account_id: str) -> dict | None:
    """استرجاع بيانات حساب محدد عبر معرّفه"""
    accounts = load_accounts()
    for acc in accounts:
        if acc.get("id") == account_id:
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
