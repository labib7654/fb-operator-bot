"""
إعدادات وثوابت أداة FB Operator ومسارات البيانات الدائمة المعزولة عن مجلد الأكواد
"""

import os
from pathlib import Path

# مجلد الأكواد المصدري فقط (يُعاد بناؤه عند التحديثات ولا تُخزَّن فيه البيانات الحساسة)
BASE_DIR = Path(__file__).resolve().parent


def _resolve_persistent_data_dir() -> Path:
    """
    تحديد مجلد البيانات الدائم خارج مجلد الأكواد fb_operator:
    1. متغير البيئة FB_DATA_DIR إن وُجد.
    2. القرص الدائم /data في مساحات Hugging Face عند تفعيل Persistent Storage.
    3. مجلد خارجي ثابت في مجلد المستخدم (~/.fb_operator_data) أو بجانب المشروع.
    """
    env_dir = (os.environ.get("FB_DATA_DIR") or "").strip()
    if env_dir:
        p = Path(env_dir).expanduser().resolve()
        p.mkdir(parents=True, exist_ok=True)
        return p

    hf_persistent = Path("/data")
    try:
        if hf_persistent.exists() and hf_persistent.is_dir() and os.access(hf_persistent, os.W_OK):
            p = hf_persistent / "fb_operator_data"
            p.mkdir(parents=True, exist_ok=True)
            return p
    except Exception:
        pass

    try:
        home_data = (Path.home() / ".fb_operator_data").resolve()
        home_data.mkdir(parents=True, exist_ok=True)
        if os.access(home_data, os.W_OK):
            return home_data
    except Exception:
        pass

    fallback = (BASE_DIR.parent / ".fb_operator_data").resolve()
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


# المجلد المنفصل الدائم لكافة قواعد البيانات والملفات الشخصية والجلسات
DATA_DIR = _resolve_persistent_data_dir()

# مجلد حفظ جلسات وبروفايلات الحسابات (معزولة بالكامل)
PROFILES_DIR = DATA_DIR / "profiles"
PROFILES_DIR.mkdir(parents=True, exist_ok=True)

# مجلد حفظ ملفات الجلسات الخفيفة القابلة للاستعادة (Cookies + storage_state)
SESSIONS_DIR = DATA_DIR / "sessions"
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

# مسارات قواعد البيانات في المجلد المنفصل الدائم
ACCOUNTS_FILE = DATA_DIR / "accounts.json"
USERS_FILE = DATA_DIR / "users.json"
AUDIT_LOG_FILE = DATA_DIR / "audit_logs.json"
ECONOMY_SETTINGS_FILE = DATA_DIR / "economy_settings.json"
POINTS_LEDGER_FILE = DATA_DIR / "points_ledger.json"
INVITE_CODES_FILE = DATA_DIR / "invite_codes.json"
SUPPORT_TICKETS_FILE = DATA_DIR / "support_tickets.json"
BACKUP_META_FILE = DATA_DIR / "backup_meta.json"
UI_STATES_FILE = DATA_DIR / "ui_states.json"
CLOUD_DB_CONFIG_FILE = DATA_DIR / "cloud_db_config.json"
PROXIES_FILE = DATA_DIR / "proxies.json"
ANNOUNCEMENTS_FILE = DATA_DIR / "announcements.json"
SQLITE_MIRROR_FILE = DATA_DIR / "fb_operator.db"

# ملف قاعدة البيانات الخارجي المعزول خارج مجلد الأكواد (بجانب HUGGINGFACE_UPLOAD/ في جذر المستودع)
EXTERNAL_VAULT_FILENAME = "fb_operator_vault.json"


def resolve_external_vault_file() -> Path | None:
    """
    تحديد مسار ملف قاعدة البيانات الخارجي (خارج مجلد التحديثات HUGGINGFACE_UPLOAD) بحيث لا يُمس ولا يُستبدل عند رفع المجلد بالكامل:
    1. متغير البيئة FB_VAULT_FILE إن تم تحديده.
    2. ملف fb_operator_vault.json موجود فعلاً بجانب HUGGINGFACE_UPLOAD أو في مجلد التشغيل الحالي.
    3. أو جذر مستودع Git (.git / .github) بجانب المجلد لتتم المزامنة التلقائية معه.
    """
    env_v = (os.environ.get("FB_VAULT_FILE") or "").strip()
    if env_v:
        return Path(env_v).expanduser().resolve()

    parent_up = BASE_DIR.parent       # HUGGINGFACE_UPLOAD أو جذر المشروع
    repo_root = parent_up.parent      # جذر مستودع GitHub (بجانب HUGGINGFACE_UPLOAD)
    cwd = Path.cwd().resolve()

    candidates: list[Path] = []
    for raw_c in (
        repo_root / EXTERNAL_VAULT_FILENAME,
        cwd / EXTERNAL_VAULT_FILENAME,
        parent_up / EXTERNAL_VAULT_FILENAME,
    ):
        try:
            rc = raw_c.resolve()
        except Exception:
            rc = raw_c
        if rc not in candidates:
            candidates.append(rc)

    for cand in candidates:
        if cand.exists() and cand.is_file():
            return cand

    is_gh_actions = os.environ.get("GITHUB_ACTIONS", "").lower() == "true"
    for root_dir in (repo_root, cwd, parent_up):
        try:
            r = root_dir.resolve()
            if r != BASE_DIR.resolve() and ((r / ".git").exists() or (is_gh_actions and (r / ".github").exists())):
                return (r / EXTERNAL_VAULT_FILENAME).resolve()
        except Exception:
            pass
    return None


EXTERNAL_VAULT_FILE = resolve_external_vault_file()

# إعدادات التخفي وفترات الانتظار البشري (بالثواني)
DEFAULT_MIN_DELAY = 2.5
DEFAULT_MAX_DELAY = 5.0

# مهلة التنظيف التلقائي للحسابات التالفة أو غير النشطة (بالساعات)
BROKEN_ACCOUNT_TTL_HOURS = 24

# مسار متصفح جوجل كروم على نظام ويندوز
CHROME_EXECUTABLE = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
