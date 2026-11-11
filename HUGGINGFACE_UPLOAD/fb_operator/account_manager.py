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
from datetime import datetime
import fb_operator.config as _cfg
from fb_operator.state_events import publish_event

BASE_OPERATOR_DIR = Path(__file__).resolve().parent
ACCOUNTS_FILE = _cfg.ACCOUNTS_FILE
PROFILES_DIR = _cfg.PROFILES_DIR
SESSIONS_DIR = _cfg.SESSIONS_DIR
_accounts_lock = threading.RLock()
_git_lock = threading.Lock()


def _cleanup_session_file(account_id: str) -> None:
    if not account_id:
        return
    try:
        sf = SESSIONS_DIR / f"{account_id}.json"
        if sf.exists():
            sf.unlink(missing_ok=True)
    except Exception:
        pass


def parse_cookies_payload(raw_text: str) -> tuple[list[dict], str]:
    """
    تحليل وتطبيع كوكيز جلسة فيسبوك المصرح بها من المستخدم (JSON أو Playwright storage_state أو Cookie header)
    والتحقق من وجود c_user و xs بدون أي تكرار أو كسر لتنسيق Playwright.
    """
    txt = (raw_text or "").strip()
    if not txt:
        return [], ""

    raw_items: list[dict] = []
    try:
        parsed = json.loads(txt)
        if isinstance(parsed, dict) and isinstance(parsed.get("cookies"), list):
            raw_items = parsed["cookies"]
        elif isinstance(parsed, list):
            raw_items = parsed
    except Exception:
        raw_items = []

    if not raw_items and ("c_user=" in txt and "xs=" in txt):
        for chunk in txt.split(";"):
            part = chunk.strip()
            if "=" in part:
                k, v = part.split("=", 1)
                k = k.strip()
                v = v.strip()
                if k:
                    raw_items.append({"name": k, "value": v, "domain": ".facebook.com", "path": "/"})

    norm_cookies: list[dict] = []
    c_user_val = ""
    has_xs = False

    for item in raw_items:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        value = str(item.get("value") or "").strip()
        if not name or value == "":
            continue
        domain = str(item.get("domain") or ".facebook.com").strip()
        if not domain.startswith(".") and "facebook.com" in domain:
            domain = "." + domain.lstrip(".")
        path = str(item.get("path") or "/").strip() or "/"
        same_site = str(item.get("sameSite") or item.get("same_site") or "").strip()
        if same_site.lower() == "no_restriction":
            same_site = "None"
        elif same_site.capitalize() in ("Strict", "Lax", "None"):
            same_site = same_site.capitalize()
        else:
            same_site = "Lax"

        c_dict = {
            "name": name,
            "value": value,
            "domain": domain,
            "path": path,
            "secure": bool(item.get("secure", True)),
            "httpOnly": bool(item.get("httpOnly", item.get("http_only", name == "xs"))),
            "sameSite": same_site,
        }
        exp = item.get("expirationDate") or item.get("expires")
        if exp is not None:
            try:
                exp_f = float(exp)
                if exp_f > 0:
                    c_dict["expires"] = exp_f
            except Exception:
                pass
        norm_cookies.append(c_dict)
        if name == "c_user":
            c_user_val = value
        elif name == "xs":
            has_xs = True

    if not (c_user_val and has_xs):
        return [], ""
    return norm_cookies, c_user_val


def save_account_cookies_session(account_id: str, cookies: list[dict], origins: list | None = None) -> Path:
    """حفظ حالة الجلسة الخفيفة (Cookies + Origins) في مجلد sessions الدائم"""
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    sf = SESSIONS_DIR / f"{account_id}.json"
    state = {"cookies": cookies, "origins": origins or []}
    _atomic_write_json(sf, state)
    return sf


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


_last_git_sync_ts = 0.0


def _resolve_active_vault_target() -> Path | None:
    vp = getattr(_cfg, "EXTERNAL_VAULT_FILE", None)
    if vp:
        return Path(vp)
    fn = getattr(_cfg, "resolve_external_vault_file", None)
    return fn() if callable(fn) else None


def _run_git_sync(force: bool = False) -> None:
    """تنفيذ مزامنة Git الآمنة للملف الخارجي المعزول (fb_operator_vault.json) فقط خارج مجلد الأكواد"""
    global _last_git_sync_ts
    with _git_lock:
        try:
            now = time.time()
            if not force and (now - _last_git_sync_ts) < 15.0:
                return
            vault_path = _resolve_active_vault_target()
            if not vault_path or not vault_path.exists():
                return

            cwd = str(vault_path.parent)
            chk = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                cwd=cwd, check=False, capture_output=True, text=True, timeout=5
            )
            if chk.returncode != 0 or not (chk.stdout or "").strip():
                return
            repo_top = Path(chk.stdout.strip()).resolve()
            rel_vault = str(vault_path.resolve().relative_to(repo_top)).replace("\\", "/")

            # التحقق من وجود remote فعلي قبل محاولة الدفع
            rem = subprocess.run(
                ["git", "remote", "get-url", "origin"],
                cwd=str(repo_top), check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5
            )
            if rem.returncode != 0:
                return

            subprocess.run(["git", "config", "user.name", "github-actions[bot]"], cwd=str(repo_top), check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
            subprocess.run(["git", "config", "user.email", "github-actions[bot]@users.noreply.github.com"], cwd=str(repo_top), check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)

            subprocess.run(["git", "add", "--", rel_vault], cwd=str(repo_top), check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
            diff_chk = subprocess.run(["git", "diff", "--cached", "--quiet", "--", rel_vault], cwd=str(repo_top), check=False, timeout=5)
            if diff_chk.returncode == 0:
                return

            subprocess.run(
                ["git", "commit", "-m", f"Auto-sync {rel_vault} [skip ci]", "--", rel_vault],
                cwd=str(repo_top), check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10
            )
            subprocess.run(
                ["git", "pull", "--rebase", "--autostash"],
                cwd=str(repo_top), check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20
            )
            subprocess.run(
                ["git", "push"],
                cwd=str(repo_top), check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=25
            )
            _last_git_sync_ts = time.time()
        except Exception:
            pass


def sync_external_vault_git(force: bool = False) -> None:
    """تزامن ملف الخزنة الخارجي مع مستودع GitHub دون لمس مجلد الأكواد"""
    _run_git_sync(force=force)


def git_sync_save(async_mode: bool = True) -> None:
    """مزامنة وحفظ التغييرات تلقائياً في الملف الخارجي بجانب المجلد وفي السحابة"""
    try:
        from fb_operator.persistence_manager import notify_data_changed
        notify_data_changed("mutation")
    except Exception:
        pass
    if async_mode:
        threading.Thread(target=_run_git_sync, kwargs={"force": False}, daemon=True).start()
    else:
        _run_git_sync(force=True)


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


def add_account(name: str, email: str, password: str, owner_id: int = 0, owner_name: str = "", fb_id: str = "") -> dict:
    """إضافة حساب جديد مع منع التكرار (بالبريد أو بالمعرّف fb_id) وربطه بصاحبه وتخصيص مجلد بروفايل دائم له"""
    with _accounts_lock:
        accounts = load_accounts()

        # 1. فحص ومنع تكرار الحسابات نهائياً (Zero-Duplicates Check)
        norm_email = email.strip().lower()
        norm_fb_id = str(fb_id or "").strip()
        for existing in accounts:
            ex_email = (existing.get("email") or "").strip().lower()
            ex_fb = str(existing.get("fb_id") or "").strip()
            if (norm_email and ex_email == norm_email) or (norm_fb_id and ex_fb == norm_fb_id):
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
            "fb_id": norm_fb_id,
            "owner_id": int(owner_id) if owner_id else 0,
            "owner_name": owner_name.strip() if owner_name else "",
            "added_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "profile_dir": str(profile_path),
            "status": "قيد الفحص والتسجيل",
            "diagnostic_reason": "",
            "failed_at": 0.0,
        }
        accounts.append(new_acc)
        save_accounts(accounts, sync_git=False)

    publish_event("accounts", int(owner_id) if owner_id else 0, "account_add")
    return dict(new_acc)


def update_account(account_id: str, updates: dict, sync_git: bool = True) -> bool:
    """تحديث بيانات أو حالة حساب معين بأمان تام مع تتبع توقيت التعطل للتنظيف التلقائي خلال 24 ساعة"""
    updated = False
    owner_id = 0
    with _accounts_lock:
        accounts = load_accounts()
        for acc in accounts:
            if acc.get("id") == account_id:
                merged = dict(updates)
                if "status" in merged:
                    new_st = str(merged.get("status") or "")
                    if "نشط" in new_st:
                        merged["failed_at"] = 0.0
                        merged["failed_at_iso"] = ""
                    elif new_st != "قيد الفحص والتسجيل":
                        if not acc.get("failed_at") and "failed_at" not in merged:
                            merged["failed_at"] = time.time()
                            merged["failed_at_iso"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                acc.update(merged)
                owner_id = int(acc.get("owner_id") or 0)
                updated = True
                break
        if updated:
            save_accounts(accounts, sync_git=sync_git)
    if updated:
        publish_event("accounts", owner_id, "account_update")
    return updated


def delete_account(account_id: str) -> bool:
    """حذف حساب من السجل وحذف مجلد جلسة البروفايل وملف الجلسة بالكامل"""
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
        _cleanup_session_file(account_id)

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
                _cleanup_session_file(a.get("id", ""))
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
                _cleanup_session_file(acc.get("id", ""))
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


def purge_expired_broken_accounts(max_age_hours: int = 24, now_ts: float | None = None) -> tuple[int, list[str]]:
    """
    حذف تلقائي لكل حساب تالف/غير نشط مرّ على تعطله 24 ساعة (يوم كامل) أو أكثر
    حتى لا تتراكم الحسابات التالفة بين الحسابات السابرة النشطة.
    """
    now_val = float(now_ts if now_ts is not None else time.time())
    ttl_seconds = max(60, int(max_age_hours) * 3600)
    purged_names: list[str] = []
    backfilled = False

    with _accounts_lock:
        accounts = load_accounts()
        remaining = []

        for acc in accounts:
            status = str(acc.get("status") or "")
            if ("نشط" in status) or (status == "قيد الفحص والتسجيل"):
                remaining.append(acc)
                continue

            f_ts = 0.0
            try:
                f_ts = float(acc.get("failed_at") or 0.0)
            except Exception:
                f_ts = 0.0

            if f_ts <= 0.0:
                # محاولة اشتقاق وقت التعطل من added_at للحسابات القديمة
                added_str = str(acc.get("added_at") or "").strip()
                if added_str:
                    try:
                        f_ts = time.mktime(time.strptime(added_str, "%Y-%m-%d %H:%M:%S"))
                    except Exception:
                        f_ts = now_val
                else:
                    f_ts = now_val
                acc["failed_at"] = f_ts
                backfilled = True

            if (now_val - f_ts) >= ttl_seconds:
                purged_names.append(f"{acc.get('name', acc.get('id'))} ({acc.get('id')})")
                _cleanup_session_file(acc.get("id", ""))
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

        if purged_names or backfilled:
            save_accounts(remaining, sync_git=bool(purged_names))

    if purged_names:
        publish_event("accounts", 0, "purge_expired_24h")
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
