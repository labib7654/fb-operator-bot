"""
محرك الحفظ الدائم وعزل البيانات عن مجلد الأكواد (Persistent Storage, Backup Vault & Cloud Sync)
يضمن عدم فقدان بيانات المستخدمين، الرصيد المالي، التذاكر، الحسابات، وجلسات المتصفح
عند إعادة رفع التحديثات فوق السيرفر أو إعادة بناء حاوية Hugging Face.
"""

import base64
import hashlib
import hmac
import io
import json
import os
import re
import secrets
import shutil
import stat
import threading
import time
import zipfile
import zlib
from datetime import datetime
from pathlib import Path

import requests
import fb_operator.config as _cfg
import fb_operator.cloud_db as cloud_db
from fb_operator.state_events import publish_event

WHITELIST_JSON_FILES = (
    "accounts.json",
    "users.json",
    "audit_logs.json",
    "economy_settings.json",
    "points_ledger.json",
    "invite_codes.json",
    "support_tickets.json",
    "backup_meta.json",
    "ui_states.json",
    "proxies.json",
    "announcements.json",
    "feature_gates.json",
    "temp_emails.json",
    "trash_emails.json",
)

_SESSION_ENTRY_RE = re.compile(r"^sessions/(acc_\d+)\.json$")
_MAX_ZIP_BYTES = 25 * 1024 * 1024
_MAX_ENTRY_BYTES = 5 * 1024 * 1024
_MAX_TOTAL_UNCOMPRESSED = 40 * 1024 * 1024

_sync_lock = threading.Lock()
_dirty_seq = 0
_synced_seq = 0
_cloud_db_synced_seq = 0
_sqlite_synced_seq = 0
_vault_synced_seq = 0
_channel_synced_seq = 0
_last_hf_sync_ts = 0.0
_last_cloud_db_sync_ts = 0.0
_last_vault_sync_ts = 0.0
_last_tg_vault_ts = 0.0
_last_tg_dm_hash = ""
_tg_send_lock = threading.Lock()
_last_backup_iso = ""
_last_hf_status = "غير مفعّل (أضف HF_TOKEN في Secrets للمزامنة السحابية التلقائية)"
_last_vault_status = "غير مهيأ بعد"
_meta_lock = threading.RLock()
_pre_backup_callbacks: list = []
_post_restore_callbacks: list = []

MIN_BACKUP_INTERVAL_SEC = 10
MAX_BACKUP_INTERVAL_SEC = 10 * 365 * 86400
_AR_DIGIT_TRANS = str.maketrans("٠١٢٣٤٥٦٧٨٩٫،", "0123456789.,")

_UNIT_SECONDS = {
    "s": 1, "sec": 1, "secs": 1, "second": 1, "seconds": 1,
    "ث": 1, "ثانية": 1, "ثانيه": 1, "ثواني": 1, "ثوان": 1, "ثوانٍ": 1,
    "ثانيتين": 2, "ثانيتان": 2,
    "m": 60, "min": 60, "mins": 60, "minute": 60, "minutes": 60,
    "د": 60, "دقيقة": 60, "دقيقه": 60, "دقائق": 60,
    "دقيقتين": 120, "دقيقتان": 120,
    "h": 3600, "hr": 3600, "hrs": 3600, "hour": 3600, "hours": 3600,
    "س": 3600, "ساعة": 3600, "ساعه": 3600, "ساعات": 3600,
    "ساعتين": 7200, "ساعتان": 7200,
    "d": 86400, "day": 86400, "days": 86400,
    "ي": 86400, "يوم": 86400, "يومي": 86400, "يوميا": 86400, "يومياً": 86400, "أيام": 86400, "ايام": 86400,
    "يومين": 172800, "يومان": 172800,
    "w": 604800, "week": 604800, "weeks": 604800,
    "أ": 604800, "أسبوع": 604800, "اسبوع": 604800, "أسابيع": 604800, "اسابيع": 604800,
    "أسبوعي": 604800, "اسبوعي": 604800, "أسبوعاً": 604800,
    "أسبوعين": 1209600, "اسبوعين": 1209600,
    "mo": 2592000, "month": 2592000, "months": 2592000,
    "ش": 2592000, "شهر": 2592000, "شهري": 2592000, "شهريا": 2592000, "شهرياً": 2592000, "شهور": 2592000, "أشهر": 2592000, "اشهر": 2592000,
    "شهرين": 5184000, "شهران": 5184000,
    "y": 31536000, "yr": 31536000, "yrs": 31536000, "year": 31536000, "years": 31536000,
    "سن": 31536000, "سنة": 31536000, "سنه": 31536000, "سنين": 31536000, "سنوات": 31536000,
    "سنوي": 31536000, "سنويا": 31536000, "سنوياً": 31536000, "سنويًا": 31536000,
    "سنتين": 63072000, "سنتان": 63072000,
}
_UNITS_ALT = "|".join(sorted(_UNIT_SECONDS.keys(), key=len, reverse=True))
_INTERVAL_PAIR_RE = re.compile(rf"(\d+(?:\.\d+)?)\s*({_UNITS_ALT})(?![a-zA-Z0-9\u0600-\u06FF])", re.IGNORECASE)
_INTERVAL_SOLO_RE = re.compile(rf"(?<![a-zA-Z0-9\u0600-\u06FF])({_UNITS_ALT})(?![a-zA-Z0-9\u0600-\u06FF])", re.IGNORECASE)


def register_pre_backup_callback(cb) -> None:
    if cb not in _pre_backup_callbacks:
        _pre_backup_callbacks.append(cb)


def register_restore_callback(cb) -> None:
    if cb not in _post_restore_callbacks:
        _post_restore_callbacks.append(cb)


PERSISTENT_UI_STATE_KEYS = (
    "target_url", "selected_acc", "acc_count_limit",
    "like", "reaction_type", "react_post_index", "react_post_url", "react_acc_count",
    "comment", "comment_text", "comment_post_index", "comment_post_url", "comment_acc_count",
    "interact_cmt", "cmt_target_mode", "cmt_target_val", "cmt_reaction", "cmt_reply",
    "friend", "cancel_friend", "follow", "unfollow",
    "message", "message_text",
    "report_post", "report_profile", "rep_reason", "rep_victim", "block",
)


def load_ui_states_data() -> dict[int, dict]:
    """تحميل إعدادات الضبط والواجهة لجميع المستخدمين من ui_states.json"""
    with _meta_lock:
        json_map, _, _ = _active_paths()
        ui_path = json_map["ui_states.json"]
        if not ui_path.exists() or not ui_path.is_file():
            return {}
        try:
            raw = json.loads(ui_path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                return {}
            out: dict[int, dict] = {}
            for k_str, val in raw.items():
                try:
                    uid = int(k_str)
                except Exception:
                    continue
                if isinstance(val, dict):
                    out[uid] = {k: val[k] for k in PERSISTENT_UI_STATE_KEYS if k in val}
            return out
        except Exception:
            return {}


def save_ui_states_data(states_by_uid: dict, mark_dirty: bool = True) -> bool:
    """حفظ حالات الضبط والواجهة لجميع المستخدمين ذرياً إذا طرأ أي تعديل فعلي"""
    clean_payload: dict[str, dict] = {}
    for uid, st in sorted((states_by_uid or {}).items(), key=lambda kv: str(kv[0])):
        if not isinstance(st, dict):
            continue
        clean_payload[str(int(uid))] = {k: st[k] for k in PERSISTENT_UI_STATE_KEYS if k in st}

    encoded = json.dumps(clean_payload, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
    changed = False
    with _meta_lock:
        json_map, _, _ = _active_paths()
        ui_path = json_map["ui_states.json"]
        try:
            existing = ui_path.read_bytes() if ui_path.exists() else b""
        except Exception:
            existing = b""
        if existing != encoded:
            _atomic_write_bytes(ui_path, encoded)
            changed = True
    if changed and mark_dirty:
        notify_data_changed("ui_state")
    return changed


def format_backup_interval(seconds: int) -> str:
    sec = max(1, int(seconds))
    units = (
        ("سنة", 31536000),
        ("شهر", 2592000),
        ("أسبوع", 604800),
        ("يوم", 86400),
        ("ساعة", 3600),
        ("دقيقة", 60),
        ("ثانية", 1),
    )
    parts: list[str] = []
    rem = sec
    for uname, uval in units:
        if rem >= uval:
            qty = rem // uval
            rem = rem % uval
            parts.append(f"{qty} {uname}")
        if len(parts) >= 2:
            break
    if not parts:
        parts.append(f"{sec} ثانية")
    return "كل " + " و ".join(parts)


def parse_backup_interval(raw: str) -> dict:
    """تحويل نص المدة الزمنية المرن (ثوانٍ، دقائق، ساعات، أيام، أسابيع، أشهر، سنوات) إلى ثوانٍ."""
    norm = (raw or "").strip().translate(_AR_DIGIT_TRANS).lower()
    if not norm:
        return {"ok": False, "error": "أدخل قيمة زمنية صالحة (مثلاً: 30 ثانية أو 15 دقيقة أو 1 ساعة أو 1 يوم أو 1 سنة)."}

    norm = re.sub(r"\b(كل|every|each|and)\b", " ", norm)
    norm = re.sub(r"(?:^|\s)و(?:\s|$)", " ", norm)
    norm = norm.replace(",", " ").replace("+", " ").strip()

    if re.fullmatch(r"\d+(?:\.\d+)?", norm):
        total = int(round(float(norm)))
    else:
        matched_spans: list[tuple[int, int]] = []
        total_f = 0.0
        for m in _INTERVAL_PAIR_RE.finditer(norm):
            qty = float(m.group(1))
            unit = m.group(2).lower()
            mult = _UNIT_SECONDS.get(unit, 0)
            if unit in ("ثانيتين", "ثانيتان", "دقيقتين", "دقيقتان", "ساعتين", "ساعتان", "يومين", "يومان", "أسبوعين", "اسبوعين", "شهرين", "شهران", "سنتين", "سنتان"):
                mult = mult // 2
            total_f += qty * mult
            matched_spans.append(m.span())

        cleaned = list(norm)
        for s_idx, e_idx in matched_spans:
            for i in range(s_idx, e_idx):
                cleaned[i] = " "
        remainder_str = "".join(cleaned)

        solo_spans: list[tuple[int, int]] = []
        for m in _INTERVAL_SOLO_RE.finditer(remainder_str):
            unit = m.group(1).lower()
            if len(unit) <= 1 and unit not in ("s", "m", "h", "d", "w", "y", "ث", "د", "س", "ي", "أ", "ش"):
                continue
            total_f += float(_UNIT_SECONDS[unit])
            solo_spans.append(m.span())

        rem2 = list(remainder_str)
        for s_idx, e_idx in solo_spans:
            for i in range(s_idx, e_idx):
                rem2[i] = " "
        leftover = "".join(rem2).strip()
        if leftover or (not matched_spans and not solo_spans):
            return {
                "ok": False,
                "error": (
                    "صيغة وقت غير مفهومة.\n"
                    "أمثلة مقبولة: <code>30 ثانية</code>، <code>5m</code>، <code>2 ساعة</code>، "
                    "<code>يوم</code>، <code>1w</code>، <code>1 شهر</code>، <code>1 سنة</code>، أو <code>1 ساعة و 30 دقيقة</code>."
                ),
            }
        total = int(round(total_f))

    if total < MIN_BACKUP_INTERVAL_SEC:
        return {
            "ok": False,
            "error": f"الحد الأدنى لجدولة القناة هو {MIN_BACKUP_INTERVAL_SEC} ثوانٍ لحماية البوت من حظر FloodWait في تلغرام.",
        }
    if total > MAX_BACKUP_INTERVAL_SEC:
        return {
            "ok": False,
            "error": "المدة المدخلة كبيرة جداً (الحد الأقصى 10 سنوات).",
        }
    return {"ok": True, "seconds": total, "label": format_backup_interval(total)}


def default_backup_settings() -> dict:
    return {
        "channel_id": None,
        "channel_title": "",
        "enabled": True,
        "dm_enabled": True,
        "interval_seconds": 3600,
        "interval_label": "كل 1 ساعة",
        "on_change": False,
        "last_channel_backup_ts": 0.0,
        "last_channel_backup_iso": "",
        "channel_backup_count": 0,
        "last_trigger": "",
        "last_error": "",
    }


def load_backup_settings() -> dict:
    with _meta_lock:
        json_map, _, _ = _active_paths()
        meta_path = json_map["backup_meta.json"]
        cfg = default_backup_settings()
        if meta_path.exists():
            try:
                raw = json.loads(meta_path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    cfg.update(raw)
            except Exception:
                pass
        sec = max(MIN_BACKUP_INTERVAL_SEC, min(MAX_BACKUP_INTERVAL_SEC, int(cfg.get("interval_seconds") or 3600)))
        cfg["interval_seconds"] = sec
        cfg["interval_label"] = format_backup_interval(sec)
        cfg["enabled"] = bool(cfg.get("enabled", True))
        cfg["dm_enabled"] = bool(cfg.get("dm_enabled", True))
        cfg["on_change"] = bool(cfg.get("on_change", False))
        cfg["channel_backup_count"] = int(cfg.get("channel_backup_count") or 0)
        cfg["last_channel_backup_ts"] = float(cfg.get("last_channel_backup_ts") or 0.0)
        return cfg


def save_backup_settings(patch: dict, mark_dirty: bool = True) -> dict:
    with _meta_lock:
        json_map, _, _ = _active_paths()
        meta_path = json_map["backup_meta.json"]
        cur = load_backup_settings()
        cur.update(patch or {})
        sec = max(MIN_BACKUP_INTERVAL_SEC, min(MAX_BACKUP_INTERVAL_SEC, int(cur.get("interval_seconds") or 3600)))
        cur["interval_seconds"] = sec
        cur["interval_label"] = format_backup_interval(sec)
        _atomic_write_bytes(meta_path, json.dumps(cur, ensure_ascii=False, indent=2).encode("utf-8"))
    if mark_dirty:
        notify_data_changed("backup_settings")
    publish_event("system", 0, "backup_settings_updated")
    return cur


def _active_modules():
    import fb_operator.account_manager as acc_m
    import fb_operator.admin_manager as adm_m
    import fb_operator.economy_manager as eco_m
    return acc_m, adm_m, eco_m


def _active_paths() -> tuple[dict[str, Path], Path, Path]:
    """استرجاع المسارات النشطة حالياً (متوافقة مع الإنتاج والاختبارات المعزولة)"""
    import fb_operator.config as cfg_m

    acc_m, adm_m, eco_m = _active_modules()
    active_data_dir = Path(acc_m.ACCOUNTS_FILE).parent
    raw_meta = Path(cfg_m.BACKUP_META_FILE)
    raw_ui = Path(cfg_m.UI_STATES_FILE)
    raw_proxies = Path(getattr(cfg_m, "PROXIES_FILE", Path(cfg_m.DATA_DIR) / "proxies.json"))
    raw_ann = Path(getattr(cfg_m, "ANNOUNCEMENTS_FILE", Path(cfg_m.DATA_DIR) / "announcements.json"))
    raw_temp = Path(getattr(cfg_m, "TEMP_EMAILS_FILE", Path(cfg_m.DATA_DIR) / "temp_emails.json"))
    raw_trash = Path(getattr(cfg_m, "TRASH_EMAILS_FILE", Path(cfg_m.DATA_DIR) / "trash_emails.json"))
    base_data_dir = Path(cfg_m.DATA_DIR)
    meta_path = (active_data_dir / "backup_meta.json") if (raw_meta.parent == base_data_dir and active_data_dir != base_data_dir) else raw_meta
    ui_path = (active_data_dir / "ui_states.json") if (raw_ui.parent == base_data_dir and active_data_dir != base_data_dir) else raw_ui
    proxies_path = (active_data_dir / "proxies.json") if (raw_proxies.parent == base_data_dir and active_data_dir != base_data_dir) else raw_proxies
    ann_path = (active_data_dir / "announcements.json") if (raw_ann.parent == base_data_dir and active_data_dir != base_data_dir) else raw_ann
    temp_path = (active_data_dir / "temp_emails.json") if (raw_temp.parent == base_data_dir and active_data_dir != base_data_dir) else raw_temp
    trash_path = (active_data_dir / "trash_emails.json") if (raw_trash.parent == base_data_dir and active_data_dir != base_data_dir) else raw_trash

    json_map = {
        "accounts.json": Path(acc_m.ACCOUNTS_FILE),
        "users.json": Path(adm_m.USERS_FILE),
        "audit_logs.json": Path(adm_m.AUDIT_LOG_FILE),
        "economy_settings.json": Path(eco_m.ECONOMY_SETTINGS_FILE),
        "points_ledger.json": Path(eco_m.POINTS_LEDGER_FILE),
        "invite_codes.json": Path(eco_m.INVITE_CODES_FILE),
        "support_tickets.json": Path(eco_m.SUPPORT_TICKETS_FILE),
        "backup_meta.json": meta_path,
        "ui_states.json": ui_path,
        "proxies.json": proxies_path,
        "announcements.json": ann_path,
        "temp_emails.json": temp_path,
        "trash_emails.json": trash_path,
    }
    profiles_dir = Path(acc_m.PROFILES_DIR)
    sessions_dir = Path(acc_m.SESSIONS_DIR)
    return json_map, profiles_dir, sessions_dir


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + f".tmp.{threading.get_ident()}")
    with open(tmp_path, "wb") as f:
        f.write(data)
        f.flush()
        try:
            os.fsync(f.fileno())
        except Exception:
            pass
    os.replace(tmp_path, path)


def notify_data_changed(reason: str = "") -> None:
    """إشعار طبقة الحفظ بوجود تعديل جديد يحتاج نسخاً احتياطياً"""
    global _dirty_seq
    with _sync_lock:
        _dirty_seq += 1


def migrate_legacy_data() -> dict:
    """
    ترحيل آمن لمرة واحدة لأي ملفات قديمة كانت داخل مجلد الأكواد (fb_operator/*.json و profiles/)
    إلى مجلد البيانات المنفصل الدائم DATA_DIR دون الكتابة فوق البيانات الأحدث.
    """
    migrated: list[str] = []
    json_map, profiles_dir, sessions_dir = _active_paths()
    base_dir = _cfg.BASE_DIR

    for fname, dst in json_map.items():
        src = base_dir / fname
        try:
            if src.resolve() == dst.resolve():
                continue
        except Exception:
            pass
        if src.exists() and not dst.exists():
            try:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                migrated.append(fname)
            except Exception:
                pass

    legacy_profiles = base_dir / "profiles"
    if legacy_profiles.exists() and legacy_profiles.is_dir():
        try:
            same_prof = legacy_profiles.resolve() == profiles_dir.resolve()
        except Exception:
            same_prof = False
        if not same_prof:
            for item in legacy_profiles.iterdir():
                if item.is_dir() and re.fullmatch(r"acc_\d+", item.name):
                    dst_p = profiles_dir / item.name
                    if not dst_p.exists():
                        try:
                            shutil.copytree(item, dst_p, dirs_exist_ok=True)
                            migrated.append(f"profiles/{item.name}")
                        except Exception:
                            pass

    sessions_dir.mkdir(parents=True, exist_ok=True)
    profiles_dir.mkdir(parents=True, exist_ok=True)

    # تطبيع profile_dir في accounts.json ليشير إلى المجلد المنفصل الحالي
    acc_m, _, _ = _active_modules()
    try:
        with acc_m._accounts_lock:
            accs = acc_m.load_accounts()
            changed = False
            for a in accs:
                aid = a.get("id")
                if aid:
                    desired = str((profiles_dir / aid).resolve())
                    if a.get("profile_dir") != desired:
                        a["profile_dir"] = desired
                        changed = True
                    inline_cookies = a.get("cookies")
                    if isinstance(inline_cookies, list) and inline_cookies and re.fullmatch(r"acc_\d+", str(aid)):
                        sess_p = sessions_dir / f"{aid}.json"
                        if not sess_p.exists() and any(
                            isinstance(c, dict) and str(c.get("name", "")) == "c_user" and str(c.get("value", "")).strip()
                            for c in inline_cookies
                        ):
                            _atomic_write_bytes(
                                sess_p,
                                json.dumps({"cookies": inline_cookies, "origins": a.get("origins") or []}, ensure_ascii=False).encode("utf-8"),
                            )
            if changed:
                acc_m.save_accounts(accs, sync_git=False)
    except Exception:
        pass

    return {"migrated": migrated, "data_dir": str(_cfg.DATA_DIR)}


def export_backup_zip_bytes(include_sessions: bool = True) -> bytes:
    """
    إنشاء حزمة ZIP كاملة وشاملة تحتوي على كافة قواعد البيانات والضبط وحالات الواجهة
    والملفات الشخصية (Cookies/Sessions) بقفل ثابت الترتيب بدون استثناء أي بيانات.
    """
    for cb in list(_pre_backup_callbacks):
        try:
            cb()
        except Exception:
            pass

    acc_m, adm_m, eco_m = _active_modules()
    json_map, _, sessions_dir = _active_paths()

    buf = io.BytesIO()
    with _meta_lock, eco_m._economy_lock, adm_m._users_lock, acc_m._accounts_lock:
        counts = {"files": 0, "sessions": 0}
        with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            for fname, fpath in json_map.items():
                if fpath.exists() and fpath.is_file():
                    try:
                        zf.write(fpath, arcname=fname)
                        counts["files"] += 1
                    except Exception:
                        pass

            if include_sessions and sessions_dir.exists() and sessions_dir.is_dir():
                for sf in sorted(sessions_dir.glob("acc_*.json")):
                    if re.fullmatch(r"acc_\d+\.json", sf.name) and sf.is_file():
                        try:
                            zf.write(sf, arcname=f"sessions/{sf.name}")
                            counts["sessions"] += 1
                        except Exception:
                            pass

            manifest = {
                "format": "fb_operator_backup_v2",
                "exported_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "exported_ts": time.time(),
                "includes_sessions": bool(include_sessions),
                "files_count": counts["files"],
                "sessions_count": counts["sessions"],
            }
            zf.writestr("backup_manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))

    return buf.getvalue()


def _collect_snapshot_unlocked(json_map: dict[str, Path], sessions_dir: Path) -> tuple[dict[str, bytes], dict[str, bytes]]:
    docs: dict[str, bytes] = {}
    sessions: dict[str, bytes] = {}
    for fname, fpath in json_map.items():
        if fpath.exists() and fpath.is_file():
            try:
                docs[fname] = fpath.read_bytes()
            except Exception:
                pass
    if sessions_dir.exists() and sessions_dir.is_dir():
        for sf in sorted(sessions_dir.glob("acc_*.json")):
            if re.fullmatch(r"acc_\d+\.json", sf.name) and sf.is_file():
                try:
                    sessions[sf.name] = sf.read_bytes()
                except Exception:
                    pass
    return docs, sessions


def collect_persistent_snapshot() -> tuple[dict[str, bytes], dict[str, bytes]]:
    for cb in list(_pre_backup_callbacks):
        try:
            cb()
        except Exception:
            pass
    acc_m, adm_m, eco_m = _active_modules()
    json_map, _, sessions_dir = _active_paths()
    with _meta_lock, eco_m._economy_lock, adm_m._users_lock, acc_m._accounts_lock:
        return _collect_snapshot_unlocked(json_map, sessions_dir)


def _session_bytes_has_c_user(raw_bytes: bytes | None) -> bool:
    if not raw_bytes:
        return False
    try:
        parsed = json.loads(raw_bytes.decode("utf-8"))
        cookies = parsed.get("cookies", []) if isinstance(parsed, dict) else []
        return any(isinstance(c, dict) and c.get("name") == "c_user" and str(c.get("value") or "").strip() for c in cookies)
    except Exception:
        return False


def _parse_and_validate_backup_zip(raw_bytes: bytes) -> dict:
    """فحص أرشيف ZIP أمنياً ضد ZipSlip والروابط الرمزية وقنابل الضغط مع استخلاص ملفات JSON والجلسات."""
    if not raw_bytes or len(raw_bytes) > _MAX_ZIP_BYTES:
        return {"ok": False, "error": "حجم ملف النسخة الاحتياطية غير صالح أو يتجاوز الحد المسموح (25MB)."}

    json_map, _, _ = _active_paths()
    staged_json: dict[str, bytes] = {}
    staged_sessions: dict[str, bytes] = {}
    manifest_info: dict = {}

    try:
        with zipfile.ZipFile(io.BytesIO(raw_bytes), mode="r") as zf:
            total_uncomp = 0
            for info in zf.infolist():
                if info.is_dir():
                    continue
                if stat.S_ISLNK(info.external_attr >> 16):
                    return {"ok": False, "error": "مرفوض أمنياً: الملف يحتوي على روابط رمزية غير آمنة."}
                clean_name = info.filename.replace("\\", "/")
                if clean_name.startswith("/") or ".." in clean_name.split("/"):
                    return {"ok": False, "error": f"مرفوض أمنياً (Path Traversal): {clean_name}"}
                if info.file_size > _MAX_ENTRY_BYTES:
                    return {"ok": False, "error": f"ملف ضخم جداً داخل الحزمة: {clean_name}"}
                total_uncomp += info.file_size
                if total_uncomp > _MAX_TOTAL_UNCOMPRESSED:
                    return {"ok": False, "error": "حجم البيانات المفكوكة يتجاوز الحد المسموح."}

                content = zf.read(info.filename)
                if len(content) > _MAX_ENTRY_BYTES:
                    return {"ok": False, "error": f"ملف ضخم جداً بعد القراءة: {clean_name}"}

                if clean_name == "backup_manifest.json":
                    try:
                        manifest_info = json.loads(content.decode("utf-8"))
                    except Exception:
                        pass
                    continue

                if clean_name in json_map:
                    try:
                        parsed = json.loads(content.decode("utf-8"))
                    except Exception:
                        return {"ok": False, "error": f"ملف JSON تالف داخل النسخة: {clean_name}"}
                    if clean_name in ("accounts.json", "audit_logs.json", "points_ledger.json", "invite_codes.json", "support_tickets.json", "trash_emails.json") and not isinstance(parsed, list):
                        if clean_name == "trash_emails.json" and isinstance(parsed, dict):
                            pass  # Allow dict wrapper if exported that way
                        else:
                            return {"ok": False, "error": f"بنية غير صحيحة للملف: {clean_name}"}
                    if clean_name in ("users.json", "economy_settings.json", "backup_meta.json", "ui_states.json", "proxies.json", "announcements.json", "temp_emails.json") and not isinstance(parsed, dict):
                        return {"ok": False, "error": f"بنية غير صحيحة للملف: {clean_name}"}
                    staged_json[clean_name] = content
                else:
                    m = _SESSION_ENTRY_RE.match(clean_name)
                    if m:
                        try:
                            s_parsed = json.loads(content.decode("utf-8"))
                            if not isinstance(s_parsed, dict) or not isinstance(s_parsed.get("cookies"), list):
                                continue
                        except Exception:
                            continue
                        staged_sessions[f"{m.group(1)}.json"] = content
    except zipfile.BadZipFile:
        return {"ok": False, "error": "الملف المرفوع ليس أرشيف ZIP صالحاً."}
    except Exception as e:
        return {"ok": False, "error": f"تعذر فحص ملف النسخة الاحتياطية: {e}"}

    if not staged_json and not staged_sessions:
        return {"ok": False, "error": "لم يُعثر على ملفات بيانات صالحة داخل هذا الأرشيف."}

    return {
        "ok": True,
        "staged_json": staged_json,
        "staged_sessions": staged_sessions,
        "manifest": manifest_info,
    }


def inspect_backup_zip_bytes(raw_bytes: bytes) -> dict:
    """معاينة محتويات ملف النسخة الاحتياطية ومقارنتها بالوضع الحالي قبل الدمج أو الاستبدال."""
    parsed_res = _parse_and_validate_backup_zip(raw_bytes)
    if not parsed_res.get("ok"):
        return parsed_res

    staged_json = parsed_res["staged_json"]
    staged_sessions = parsed_res["staged_sessions"]

    def _cnt(fname: str) -> int:
        if fname not in staged_json:
            return 0
        try:
            obj = json.loads(staged_json[fname].decode("utf-8"))
            return len(obj) if isinstance(obj, (list, dict)) else 0
        except Exception:
            return 0

    acc_m, adm_m, _ = _active_modules()
    cur_accs = acc_m.load_accounts()
    cur_users = adm_m.load_users()
    return {
        "ok": True,
        "users_count": _cnt("users.json"),
        "accounts_count": _cnt("accounts.json"),
        "sessions_count": len(staged_sessions),
        "ledger_count": _cnt("points_ledger.json"),
        "invites_count": _cnt("invite_codes.json"),
        "tickets_count": _cnt("support_tickets.json"),
        "ui_states_count": _cnt("ui_states.json"),
        "audit_count": _cnt("audit_logs.json"),
        "manifest": parsed_res.get("manifest", {}),
        "current_accounts_count": len(cur_accs),
        "current_users_count": len(cur_users),
        "has_existing_data": len(cur_accs) > 0 or len(cur_users) > 1,
    }


def _apply_full_snapshot(staged_json: dict[str, bytes], staged_sessions: dict[str, bytes], clear_missing_sessions: bool = True) -> dict:
    global _last_backup_iso, _channel_synced_seq
    acc_m, adm_m, eco_m = _active_modules()
    json_map, profiles_dir, sessions_dir = _active_paths()

    restored_acc_ids: set[str] = set()
    with _meta_lock, eco_m._economy_lock, adm_m._users_lock, acc_m._accounts_lock:
        for fname, content in staged_json.items():
            if fname not in json_map:
                continue
            target = json_map[fname]
            if fname == "accounts.json":
                try:
                    accs = json.loads(content.decode("utf-8"))
                    for a in accs:
                        aid = a.get("id")
                        if aid:
                            restored_acc_ids.add(str(aid))
                            p_dir = profiles_dir / str(aid)
                            p_dir.mkdir(parents=True, exist_ok=True)
                            a["profile_dir"] = str(p_dir.resolve())
                    content = json.dumps(accs, ensure_ascii=False, indent=2).encode("utf-8")
                except Exception:
                    pass
            _atomic_write_bytes(target, content)

        sessions_dir.mkdir(parents=True, exist_ok=True)
        if clear_missing_sessions and "accounts.json" in staged_json:
            for existing_sf in list(sessions_dir.glob("acc_*.json")):
                if existing_sf.name not in staged_sessions and existing_sf.stem not in restored_acc_ids:
                    try:
                        existing_sf.unlink()
                    except Exception:
                        pass

        for s_name, s_bytes in staged_sessions.items():
            if re.fullmatch(r"acc_\d+\.json", s_name):
                _atomic_write_bytes(sessions_dir / s_name, s_bytes)

        docs_now, sess_now = _collect_snapshot_unlocked(json_map, sessions_dir)
        cloud_db.write_local_sqlite_mirror(docs_now, sess_now)
        users_cnt = len(adm_m.load_users())
        accs_cnt = len(acc_m.load_accounts())

    with _sync_lock:
        _channel_synced_seq = max(_channel_synced_seq, _dirty_seq)
    _last_backup_iso = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for cb in list(_post_restore_callbacks):
        try:
            cb()
        except Exception:
            pass

    publish_event("system", 0, "backup_restored")
    return {
        "ok": True,
        "restored_files": sorted(staged_json.keys()),
        "sessions_restored": len(staged_sessions),
        "users_count": users_cnt,
        "accounts_count": accs_cnt,
        "ui_states_restored": "ui_states.json" in staged_json,
        "backup_settings_restored": "backup_meta.json" in staged_json,
    }


def restore_backup_zip_bytes(raw_bytes: bytes) -> dict:
    """
    استعادة حزمة النسخة الاحتياطية بالكامل مع التحقق الأمني والكتابة الذرية.
    """
    parsed_res = _parse_and_validate_backup_zip(raw_bytes)
    if not parsed_res.get("ok"):
        return parsed_res
    manifest_info = parsed_res.get("manifest") or {}
    clear_missing = bool(manifest_info.get("format") != "fb_operator_backup_v2" or manifest_info.get("includes_sessions", True))
    res = _apply_full_snapshot(
        parsed_res["staged_json"],
        parsed_res["staged_sessions"],
        clear_missing_sessions=clear_missing,
    )
    res["manifest"] = manifest_info
    return res


def _merge_staged_payload(staged_json: dict[str, bytes], staged_sessions: dict[str, bytes]) -> dict:
    """
    محرك الدمج الذكي غير التدميري:
    - يدمج الحسابات مع كشف التكرار عبر fb_id والبريد الإلكتروني، وإعادة ترقيم المعرّفات المتعارضة acc_X مع جلساتها.
    - يحافظ على كلمة المرور الحقيقية والجلسة النشطة (c_user) بدل الكتابة فوقها بتالف أو مؤقت.
    - يدمج المستخدمين والصلاحيات وقيود النقاط بدون تكرار أو مضاعفة الرصيد.
    """
    global _last_backup_iso
    acc_m, adm_m, eco_m = _active_modules()
    json_map, profiles_dir, sessions_dir = _active_paths()

    def _safe_parse(raw: bytes | None, fallback):
        if not raw:
            return fallback
        try:
            val = json.loads(raw.decode("utf-8"))
            return val if isinstance(val, type(fallback)) else fallback
        except Exception:
            return fallback

    def _extract_acc_num(aid: str) -> int:
        m = re.fullmatch(r"acc_(\d+)", str(aid or ""))
        return int(m.group(1)) if m else 0

    with _meta_lock, eco_m._economy_lock, adm_m._users_lock, acc_m._accounts_lock:
        sessions_dir.mkdir(parents=True, exist_ok=True)
        cur_accounts: list[dict] = list(acc_m.load_accounts())
        cur_users: dict = dict(adm_m.load_users())
        cur_ledger: list[dict] = _safe_parse(json_map["points_ledger.json"].read_bytes() if json_map["points_ledger.json"].exists() else None, [])
        cur_invites: list[dict] = _safe_parse(json_map["invite_codes.json"].read_bytes() if json_map["invite_codes.json"].exists() else None, [])
        cur_tickets: list[dict] = _safe_parse(json_map["support_tickets.json"].read_bytes() if json_map["support_tickets.json"].exists() else None, [])
        cur_audit: list[dict] = _safe_parse(json_map["audit_logs.json"].read_bytes() if json_map["audit_logs.json"].exists() else None, [])
        cur_ui: dict = _safe_parse(json_map["ui_states.json"].read_bytes() if json_map["ui_states.json"].exists() else None, {})
        cur_meta: dict = _safe_parse(json_map["backup_meta.json"].read_bytes() if json_map["backup_meta.json"].exists() else None, {})
        cur_proxies: dict = _safe_parse(json_map["proxies.json"].read_bytes() if json_map["proxies.json"].exists() else None, {})
        cur_ann: dict = _safe_parse(json_map["announcements.json"].read_bytes() if json_map["announcements.json"].exists() else None, {})
        cur_temp: dict = _safe_parse(json_map["temp_emails.json"].read_bytes() if json_map["temp_emails.json"].exists() else None, {})
        cur_trash: list = _safe_parse(json_map["trash_emails.json"].read_bytes() if json_map["trash_emails.json"].exists() else None, [])

        inc_accounts = _safe_parse(staged_json.get("accounts.json"), [])
        inc_users = _safe_parse(staged_json.get("users.json"), {})
        inc_ledger = _safe_parse(staged_json.get("points_ledger.json"), [])
        inc_invites = _safe_parse(staged_json.get("invite_codes.json"), [])
        inc_tickets = _safe_parse(staged_json.get("support_tickets.json"), [])
        inc_audit = _safe_parse(staged_json.get("audit_logs.json"), [])
        inc_ui = _safe_parse(staged_json.get("ui_states.json"), {})
        inc_eco = _safe_parse(staged_json.get("economy_settings.json"), {})
        inc_meta = _safe_parse(staged_json.get("backup_meta.json"), {})
        inc_proxies = _safe_parse(staged_json.get("proxies.json"), {})
        inc_ann = _safe_parse(staged_json.get("announcements.json"), {})
        inc_temp = _safe_parse(staged_json.get("temp_emails.json"), {})
        inc_trash = _safe_parse(staged_json.get("trash_emails.json"), [])

        stats = {
            "accounts_added": 0,
            "accounts_deduped": 0,
            "accounts_upgraded": 0,
            "sessions_merged": 0,
            "users_added": 0,
            "users_merged": 0,
            "ledger_added": 0,
            "ledger_deduped": 0,
            "invites_added": 0,
            "tickets_added": 0,
            "ui_states_added": 0,
            "announcements_added": 0,
            "proxies_added": 0,
            "temp_emails_merged": 0,
            "trash_emails_merged": 0,
        }

        # 1) دمج الحسابات والجلسات مع إعادة ترقيم التصادمات
        by_fb_id: dict[str, int] = {}
        by_email: dict[str, int] = {}
        used_acc_ids: set[str] = set()
        max_num = 0
        for idx, a in enumerate(cur_accounts):
            aid = str(a.get("id") or "")
            if aid:
                used_acc_ids.add(aid)
                max_num = max(max_num, _extract_acc_num(aid))
            fbid = str(a.get("fb_id") or "").strip()
            if fbid:
                by_fb_id[fbid] = idx
            em = str(a.get("email") or "").strip().lower()
            if em and not em.startswith("cookie_"):
                by_email[em] = idx

        id_remap: dict[str, str] = {}
        for inc_a in inc_accounts:
            if not isinstance(inc_a, dict):
                continue
            old_id = str(inc_a.get("id") or "").strip()
            inc_fbid = str(inc_a.get("fb_id") or "").strip()
            inc_email = str(inc_a.get("email") or "").strip().lower()
            if not inc_fbid and not inc_email:
                continue

            match_idx = None
            if inc_fbid and inc_fbid in by_fb_id:
                match_idx = by_fb_id[inc_fbid]
            elif inc_email and not inc_email.startswith("cookie_") and inc_email in by_email:
                match_idx = by_email[inc_email]

            inc_sess_bytes = staged_sessions.get(f"{old_id}.json") if old_id else None
            inc_has_valid_sess = _session_bytes_has_c_user(inc_sess_bytes)

            if match_idx is not None:
                cur_a = cur_accounts[match_idx]
                cur_id = str(cur_a.get("id") or "")
                if old_id:
                    id_remap[old_id] = cur_id
                upgraded = False

                if inc_fbid and not str(cur_a.get("fb_id") or "").strip():
                    cur_a["fb_id"] = inc_fbid
                    by_fb_id[inc_fbid] = match_idx
                    upgraded = True
                if cur_a.get("password") in ("", "[SESSION_COOKIES]", None) and inc_a.get("password") not in ("", "[SESSION_COOKIES]", None):
                    cur_a["password"] = inc_a["password"]
                    upgraded = True
                if int(cur_a.get("owner_id") or 0) == 0 and int(inc_a.get("owner_id") or 0) != 0:
                    cur_a["owner_id"] = int(inc_a["owner_id"])
                    if inc_a.get("owner_name"):
                        cur_a["owner_name"] = inc_a["owner_name"]
                    upgraded = True
                if not cur_a.get("bound_proxy") and inc_a.get("bound_proxy"):
                    cur_a["bound_proxy"] = str(inc_a["bound_proxy"])
                    if inc_a.get("bound_proxy_country"):
                        cur_a["bound_proxy_country"] = str(inc_a["bound_proxy_country"])
                    upgraded = True

                cur_sf = sessions_dir / f"{cur_id}.json"
                cur_has_valid_sess = _session_bytes_has_c_user(cur_sf.read_bytes() if cur_sf.exists() else None)
                cur_active = "نشط" in str(cur_a.get("status", ""))
                inc_active = "نشط" in str(inc_a.get("status", ""))

                if inc_sess_bytes and (inc_has_valid_sess or inc_active) and (not cur_active or not cur_has_valid_sess):
                    _atomic_write_bytes(cur_sf, inc_sess_bytes)
                    stats["sessions_merged"] += 1
                    cur_a["status"] = inc_a.get("status") or "نشط ومسجل"
                    cur_a["diagnostic_reason"] = inc_a.get("diagnostic_reason") or "تم استعادة الجلسة عبر الدمج الذكي"
                    upgraded = True
                elif inc_sess_bytes and not cur_sf.exists():
                    _atomic_write_bytes(cur_sf, inc_sess_bytes)
                    stats["sessions_merged"] += 1
                    upgraded = True

                stats["accounts_deduped"] += 1
                if upgraded:
                    stats["accounts_upgraded"] += 1
            else:
                if re.fullmatch(r"acc_\d+", old_id) and old_id not in used_acc_ids:
                    new_id = old_id
                    max_num = max(max_num, _extract_acc_num(new_id))
                else:
                    max_num += 1
                    new_id = f"acc_{max_num}"
                    while new_id in used_acc_ids:
                        max_num += 1
                        new_id = f"acc_{max_num}"
                used_acc_ids.add(new_id)
                if old_id:
                    id_remap[old_id] = new_id

                p_dir = profiles_dir / new_id
                p_dir.mkdir(parents=True, exist_ok=True)
                new_rec = dict(inc_a)
                new_rec["id"] = new_id
                new_rec["profile_dir"] = str(p_dir.resolve())
                cur_accounts.append(new_rec)
                new_idx = len(cur_accounts) - 1
                if inc_fbid:
                    by_fb_id[inc_fbid] = new_idx
                if inc_email and not inc_email.startswith("cookie_"):
                    by_email[inc_email] = new_idx
                if inc_sess_bytes:
                    _atomic_write_bytes(sessions_dir / f"{new_id}.json", inc_sess_bytes)
                    stats["sessions_merged"] += 1
                stats["accounts_added"] += 1

        if cur_accounts or inc_accounts:
            _atomic_write_bytes(json_map["accounts.json"], json.dumps(cur_accounts, ensure_ascii=False, indent=2).encode("utf-8"))

        # 2) دمج المستخدمين والصلاحيات
        existing_uids = set(cur_users.keys())
        super_str = str(adm_m.SUPER_ADMIN_ID)
        inc_tx_uids = {str(e.get("user_id")) for e in inc_ledger if isinstance(e, dict) and e.get("user_id") is not None}

        for uid_k, inc_u in inc_users.items():
            if not isinstance(inc_u, dict) or not str(uid_k).lstrip("-").isdigit():
                continue
            uid_s = str(int(uid_k))
            if uid_s == super_str:
                continue
            if uid_s not in cur_users:
                clean_u = dict(inc_u)
                clean_u["id"] = int(uid_s)
                clean_u["role"] = "user"
                if clean_u.get("status") not in ("pending", "approved", "banned"):
                    clean_u["status"] = "pending"
                raw_p = clean_u.get("permissions") if isinstance(clean_u.get("permissions"), dict) else {}
                clean_u["permissions"] = {pk: bool(raw_p.get(pk, False)) for pk in adm_m.DEFAULT_PERMISSIONS}
                adm_m._ensure_wallet_fields(clean_u)
                if clean_u.get("status") == "banned":
                    clean_u["admin_tier"] = "none"
                    clean_u["admin_restrictions"] = dict(adm_m.DEFAULT_ADMIN_RESTRICTIONS)
                cur_users[uid_s] = clean_u
                stats["users_added"] += 1
            else:
                cur_u = cur_users[uid_s]
                adm_m._ensure_wallet_fields(cur_u)
                if cur_u.get("status") != "banned":
                    if inc_u.get("status") == "approved":
                        cur_u["status"] = "approved"
                    cur_p = cur_u.get("permissions") if isinstance(cur_u.get("permissions"), dict) else {}
                    inc_p = inc_u.get("permissions") if isinstance(inc_u.get("permissions"), dict) else {}
                    cur_u["permissions"] = {
                        pk: bool(cur_p.get(pk, False) or (inc_p.get(pk, False) if cur_u.get("status") == "approved" else False))
                        for pk in adm_m.DEFAULT_PERMISSIONS
                    }
                    inc_tier = str(inc_u.get("admin_tier") or "none").strip().lower()
                    if cur_u.get("admin_tier", "none") == "none" and cur_u.get("status") == "approved" and inc_tier in adm_m.ADMIN_TIERS and inc_tier != "none":
                        cur_u["admin_tier"] = inc_tier
                        inc_restr = inc_u.get("admin_restrictions") if isinstance(inc_u.get("admin_restrictions"), dict) else {}
                        cur_u["admin_restrictions"] = {
                            rk: bool(inc_restr.get(rk, False))
                            for rk in adm_m.DEFAULT_ADMIN_RESTRICTIONS
                        }
                else:
                    cur_u["admin_tier"] = "none"
                    cur_u["admin_restrictions"] = dict(adm_m.DEFAULT_ADMIN_RESTRICTIONS)
                if not cur_u.get("username") and inc_u.get("username"):
                    cur_u["username"] = inc_u["username"]
                if not cur_u.get("ref_code") and inc_u.get("ref_code"):
                    cur_u["ref_code"] = str(inc_u["ref_code"])[:32]
                if not cur_u.get("referred_by") and inc_u.get("referred_by"):
                    cur_u["referred_by"] = inc_u["referred_by"]
                if inc_u.get("referral_rewarded"):
                    cur_u["referral_rewarded"] = True
                cur_u["total_logins"] = max(int(cur_u.get("total_logins", 0)), int(inc_u.get("total_logins", 0)))
                cur_u["referred_count"] = max(int(cur_u.get("referred_count", 0)), int(inc_u.get("referred_count", 0)))
                cur_u["profile_warnings_used"] = max(int(cur_u.get("profile_warnings_used", 0)), int(inc_u.get("profile_warnings_used", 0)))
                if uid_s not in inc_tx_uids:
                    # أرشيف قديم بلا سجل قيود: لا نضيع النقاط إن لم تكن مسجلة في قيود قادمة
                    if float(inc_u.get("points", 0) or 0) > float(cur_u.get("points", 0) or 0) and float(cur_u.get("total_points_earned", 0) or 0) == 0:
                        cur_u["points"] = adm_m.safe_nonneg_points(inc_u.get("points", 0))
                        cur_u["total_points_earned"] = adm_m.safe_nonneg_points(inc_u.get("total_points_earned", 0) or inc_u.get("points", 0))
                stats["users_merged"] += 1

        # 3) دمج سجل النقاط بدون مضاعفة الرصيد
        seen_tx_ids = {str(e.get("id")) for e in cur_ledger if isinstance(e, dict) and e.get("id")}
        seen_idem = {str(e.get("idempotency_key")) for e in cur_ledger if isinstance(e, dict) and e.get("idempotency_key")}
        seen_sigs = {
            (str(e.get("user_id")), str(e.get("tx_type")), str(e.get("delta")), str(e.get("timestamp")), str(e.get("reason") or ""))
            for e in cur_ledger if isinstance(e, dict)
        }
        delta_adj: dict[str, tuple[float, float, float, int]] = {}  # net_delta, earned, spent, settled

        for inc_e in inc_ledger:
            if not isinstance(inc_e, dict):
                continue
            eid = str(inc_e.get("id") or "")
            idem = str(inc_e.get("idempotency_key") or "")
            # توحيد مفتاح تفعيل الحساب عند إعادة ترقيم المعرف لمنع مضاعفة مكافأة نفس الحساب
            if idem.startswith("acct_act_"):
                old_acc_ref = idem[len("acct_act_"):]
                mapped_acc_ref = id_remap.get(old_acc_ref, old_acc_ref)
                remapped_idem = f"acct_act_{mapped_acc_ref}"
            else:
                remapped_idem = idem

            sig = (str(inc_e.get("user_id")), str(inc_e.get("tx_type")), str(inc_e.get("delta")), str(inc_e.get("timestamp")), str(inc_e.get("reason") or ""))
            if (eid and eid in seen_tx_ids) or (remapped_idem and remapped_idem in seen_idem) or (idem and idem in seen_idem) or (sig in seen_sigs):
                stats["ledger_deduped"] += 1
                continue

            entry_copy = dict(inc_e)
            if remapped_idem != idem:
                entry_copy["idempotency_key"] = remapped_idem
            if eid:
                seen_tx_ids.add(eid)
            if remapped_idem:
                seen_idem.add(remapped_idem)
            seen_sigs.add(sig)
            cur_ledger.append(entry_copy)
            stats["ledger_added"] += 1

            uid_s = str(int(inc_e.get("user_id") or 0))
            if uid_s in existing_uids:
                d_val = round(float(inc_e.get("delta") or 0), 2)
                n_d, earn, spnt, sttl = delta_adj.get(uid_s, (0.0, 0.0, 0.0, 0))
                n_d = round(n_d + d_val, 2)
                if d_val > 0:
                    earn = round(earn + d_val, 2)
                elif d_val < 0:
                    spnt = round(spnt + abs(d_val), 2)
                    if "تصفية" in str(inc_e.get("tx_type", "")) or "تسوية" in str(inc_e.get("reason", "")):
                        sttl += abs(int(inc_e.get("yer_amount") or 0))
                delta_adj[uid_s] = (n_d, earn, spnt, sttl)

        for uid_s, (n_d, earn, spnt, sttl) in delta_adj.items():
            u_obj = cur_users.get(uid_s)
            if u_obj:
                u_obj["points"] = adm_m.safe_nonneg_points(float(u_obj.get("points", 0) or 0) + n_d)
                u_obj["total_points_earned"] = adm_m.safe_nonneg_points(float(u_obj.get("total_points_earned", 0) or 0) + earn)
                u_obj["total_points_spent"] = adm_m.safe_nonneg_points(float(u_obj.get("total_points_spent", 0) or 0) + spnt)
                u_obj["total_yer_settled"] = int(u_obj.get("total_yer_settled", 0)) + sttl

        adm_m.save_users(cur_users, sync_git=False)
        if cur_ledger or inc_ledger:
            cur_ledger = cur_ledger[-2000:]
            _atomic_write_bytes(json_map["points_ledger.json"], json.dumps(cur_ledger, ensure_ascii=False, indent=2).encode("utf-8"))

        # 4) دمج أكواد الدعوة والتذاكر والسجلات وحالات الواجهة
        inv_map = {str(c.get("code")): dict(c) for c in cur_invites if isinstance(c, dict) and c.get("code")}
        for inc_c in inc_invites:
            if not isinstance(inc_c, dict) or not inc_c.get("code"):
                continue
            code = str(inc_c["code"])
            if code not in inv_map:
                inv_map[code] = dict(inc_c)
                stats["invites_added"] += 1
            elif inc_c.get("used") and not inv_map[code].get("used"):
                inv_map[code]["used"] = True
                inv_map[code]["used_by"] = inc_c.get("used_by")
                inv_map[code]["used_at"] = inc_c.get("used_at")
        if inv_map or inc_invites:
            _atomic_write_bytes(json_map["invite_codes.json"], json.dumps(list(inv_map.values()), ensure_ascii=False, indent=2).encode("utf-8"))

        t_map = {str(t.get("id")): dict(t) for t in cur_tickets if isinstance(t, dict) and t.get("id")}
        for inc_t in inc_tickets:
            if not isinstance(inc_t, dict) or not inc_t.get("id"):
                continue
            tid = str(inc_t["id"])
            if tid not in t_map:
                t_map[tid] = dict(inc_t)
                stats["tickets_added"] += 1
            else:
                existing_rep = t_map[tid].get("replies") if isinstance(t_map[tid].get("replies"), list) else []
                seen_r = {(str(r.get("timestamp")), str(r.get("sender_uid")), str(r.get("text"))) for r in existing_rep if isinstance(r, dict)}
                for ir in (inc_t.get("replies") or []):
                    if not isinstance(ir, dict):
                        continue
                    rk = (str(ir.get("timestamp")), str(ir.get("sender_uid")), str(ir.get("text")))
                    if rk not in seen_r:
                        existing_rep.append(dict(ir))
                        seen_r.add(rk)
                t_map[tid]["replies"] = existing_rep
                if t_map[tid].get("status") == "open" and inc_t.get("status") in ("replied", "closed"):
                    t_map[tid]["status"] = inc_t["status"]
        if t_map or inc_tickets:
            _atomic_write_bytes(json_map["support_tickets.json"], json.dumps(list(t_map.values())[-500:], ensure_ascii=False, indent=2).encode("utf-8"))

        if inc_audit:
            seen_aud = {
                (str(l.get("timestamp")), str(l.get("user_id")), str(l.get("action")), str(l.get("details")))
                for l in cur_audit if isinstance(l, dict)
            }
            for il in inc_audit:
                if not isinstance(il, dict):
                    continue
                ak = (str(il.get("timestamp")), str(il.get("user_id")), str(il.get("action")), str(il.get("details")))
                if ak not in seen_aud:
                    cur_audit.append(dict(il))
                    seen_aud.add(ak)
            cur_audit.sort(key=lambda x: str(x.get("timestamp", "")))
            _atomic_write_bytes(json_map["audit_logs.json"], json.dumps(cur_audit[-1000:], ensure_ascii=False, indent=2).encode("utf-8"))

        if inc_ui:
            for uid_s, st_v in inc_ui.items():
                if uid_s not in cur_ui and isinstance(st_v, dict):
                    cur_ui[uid_s] = {k: st_v[k] for k in PERSISTENT_UI_STATE_KEYS if k in st_v}
                    stats["ui_states_added"] += 1
            _atomic_write_bytes(json_map["ui_states.json"], json.dumps(cur_ui, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8"))

        if inc_eco and not json_map["economy_settings.json"].exists():
            _atomic_write_bytes(json_map["economy_settings.json"], json.dumps(eco_m._normalize_settings(inc_eco), ensure_ascii=False, indent=2).encode("utf-8"))

        if inc_meta and not cur_meta.get("channel_id") and inc_meta.get("channel_id"):
            cur_meta.update(inc_meta)
            _atomic_write_bytes(json_map["backup_meta.json"], json.dumps(cur_meta, ensure_ascii=False, indent=2).encode("utf-8"))

        if inc_proxies and isinstance(inc_proxies, dict):
            if not isinstance(cur_proxies, dict):
                cur_proxies = {}
            cur_list = cur_proxies.get("proxies") if isinstance(cur_proxies.get("proxies"), list) else []
            by_uri_existing = {
                str(p.get("uri", "")).strip(): p
                for p in cur_list
                if isinstance(p, dict) and p.get("uri")
            }
            for item in (inc_proxies.get("proxies") or []):
                if not isinstance(item, dict):
                    continue
                u = str(item.get("uri", "")).strip()
                if not u:
                    continue
                if u not in by_uri_existing:
                    copied = dict(item)
                    cur_list.append(copied)
                    by_uri_existing[u] = copied
                    stats["proxies_added"] += 1
                else:
                    ex = by_uri_existing[u]
                    for cnt_k in ("uses_count", "success_count", "total_fail_count"):
                        ex[cnt_k] = max(int(ex.get(cnt_k) or 0), int(item.get(cnt_k) or 0))
            cur_proxies["proxies"] = cur_list
            cur_binds = cur_proxies.get("bindings") if isinstance(cur_proxies.get("bindings"), dict) else {}
            inc_binds = inc_proxies.get("bindings") if isinstance(inc_proxies.get("bindings"), dict) else {}
            for acc_k, p_uri in inc_binds.items():
                mapped_k = id_remap.get(str(acc_k), str(acc_k))
                if mapped_k and mapped_k not in cur_binds and p_uri:
                    cur_binds[mapped_k] = str(p_uri)
            cur_proxies["bindings"] = cur_binds
            if not cur_proxies.get("mode") and inc_proxies.get("mode"):
                cur_proxies["mode"] = str(inc_proxies.get("mode"))
            if "auto_check_enabled" not in cur_proxies and "auto_check_enabled" in inc_proxies:
                cur_proxies["auto_check_enabled"] = bool(inc_proxies.get("auto_check_enabled"))
            if not cur_proxies.get("auto_check_interval_sec") and inc_proxies.get("auto_check_interval_sec"):
                cur_proxies["auto_check_interval_sec"] = int(inc_proxies.get("auto_check_interval_sec"))
            _atomic_write_bytes(json_map["proxies.json"], json.dumps(cur_proxies, ensure_ascii=False, indent=2).encode("utf-8"))

        if inc_ann and isinstance(inc_ann, dict):
            if not isinstance(cur_ann, dict):
                cur_ann = {"announcements": []}
            cur_a_list = cur_ann.get("announcements") if isinstance(cur_ann.get("announcements"), list) else []
            seen_aids = {str(a.get("id") or "") for a in cur_a_list if isinstance(a, dict) and a.get("id")}
            for a_item in (inc_ann.get("announcements") or []):
                if isinstance(a_item, dict) and a_item.get("id") and str(a_item["id"]) not in seen_aids:
                    cur_a_list.append(dict(a_item))
                    seen_aids.add(str(a_item["id"]))
                    stats["announcements_added"] += 1
            cur_ann["announcements"] = cur_a_list[-100:]
            _atomic_write_bytes(json_map["announcements.json"], json.dumps(cur_ann, ensure_ascii=False, indent=2).encode("utf-8"))

        if inc_temp and isinstance(inc_temp, dict):
            if not isinstance(cur_temp, dict):
                cur_temp = {"users": {}, "history": [], "seen_messages": {}, "mailbox_messages": {}}
            cur_temp.setdefault("users", {})
            cur_temp.setdefault("history", [])
            cur_temp.setdefault("seen_messages", {})
            cur_temp.setdefault("mailbox_messages", {})
            for uid, mb in (inc_temp.get("users") or {}).items():
                if uid not in cur_temp["users"] and isinstance(mb, dict):
                    cur_temp["users"][uid] = mb
                    stats["temp_emails_merged"] += 1
            seen_hist_emails = {h.get("email", "").lower() for h in cur_temp["history"] if isinstance(h, dict) and h.get("email")}
            for h in (inc_temp.get("history") or []):
                if isinstance(h, dict) and h.get("email") and h.get("email").lower() not in seen_hist_emails:
                    cur_temp["history"].append(h)
                    seen_hist_emails.add(h.get("email").lower())
                    stats["temp_emails_merged"] += 1
            cur_temp["history"] = cur_temp["history"][:300]

            # دمج خزنة الرسائل المؤرشفة لكل صندوق بريد لمنع ضياع أكواد التفعيل
            for em_k, msgs in (inc_temp.get("mailbox_messages") or {}).items():
                if isinstance(msgs, list):
                    cur_box = cur_temp["mailbox_messages"].setdefault(em_k.lower().strip(), [])
                    seen_mids = {str(m.get("id", "")) for m in cur_box if isinstance(m, dict) and m.get("id")}
                    for m_item in msgs:
                        mid = str(m_item.get("id", "")) if isinstance(m_item, dict) else ""
                        if mid and mid not in seen_mids:
                            cur_box.append(dict(m_item))
                            seen_mids.add(mid)
                            stats["temp_emails_merged"] += 1

            _atomic_write_bytes(json_map["temp_emails.json"], json.dumps(cur_temp, ensure_ascii=False, indent=2).encode("utf-8"))

        if inc_trash:
            inc_trash_list = inc_trash.get("trash", []) if isinstance(inc_trash, dict) else (inc_trash if isinstance(inc_trash, list) else [])
            cur_trash_list = cur_trash.get("trash", []) if isinstance(cur_trash, dict) else (cur_trash if isinstance(cur_trash, list) else [])
            seen_trash = {t.get("email", "").lower() for t in cur_trash_list if isinstance(t, dict) and t.get("email")}
            for t in inc_trash_list:
                if isinstance(t, dict) and t.get("email") and t.get("email").lower() not in seen_trash:
                    cur_trash_list.append(t)
                    seen_trash.add(t.get("email").lower())
                    stats["trash_emails_merged"] += 1
            cur_trash_list = cur_trash_list[:200]
            _atomic_write_bytes(json_map["trash_emails.json"], json.dumps(cur_trash_list, ensure_ascii=False, indent=2).encode("utf-8"))

        docs_now, sess_now = _collect_snapshot_unlocked(json_map, sessions_dir)
        cloud_db.write_local_sqlite_mirror(docs_now, sess_now)
        total_users = len(cur_users)
        total_accounts = len(cur_accounts)

    notify_data_changed("backup_merged")
    _last_backup_iso = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for cb in list(_post_restore_callbacks):
        try:
            cb()
        except Exception:
            pass
    publish_event("system", 0, "backup_merged")
    return {
        "ok": True,
        "mode": "merge",
        "stats": stats,
        "users_count": total_users,
        "accounts_count": total_accounts,
        "sessions_count": len(list(sessions_dir.glob("acc_*.json"))) if sessions_dir.exists() else 0,
    }


def merge_backup_zip_bytes(raw_bytes: bytes) -> dict:
    """دمج حزمة .zip قديمة أو إضافية مع القاعدة الحالية دون حذف أو تكرار أو إتلاف."""
    parsed_res = _parse_and_validate_backup_zip(raw_bytes)
    if not parsed_res.get("ok"):
        return parsed_res
    return _merge_staged_payload(parsed_res["staged_json"], parsed_res["staged_sessions"])


def merge_legacy_json_bytes(raw_bytes: bytes, filename_hint: str = "") -> dict:
    """دعم استيراد ودمج ملفات JSON القديمة المفردة (accounts.json أو users.json) بدون تعارض."""
    if not raw_bytes or len(raw_bytes) > _MAX_ENTRY_BYTES:
        return {"ok": False, "error": "حجم ملف JSON غير صالح."}
    try:
        parsed = json.loads(raw_bytes.decode("utf-8"))
    except Exception:
        return {"ok": False, "error": "ملف JSON تالف أو غير مقروء."}

    fname_low = (filename_hint or "").lower()
    if isinstance(parsed, list):
        looks_like_accounts = (not parsed) or any(isinstance(x, dict) and ("email" in x or "fb_id" in x or "password" in x) for x in parsed)
        if looks_like_accounts:
            staged_sessions: dict[str, bytes] = {}
            for item in parsed:
                if isinstance(item, dict) and isinstance(item.get("cookies"), list) and item.get("id"):
                    staged_sessions[f"{item['id']}.json"] = json.dumps({"cookies": item["cookies"], "origins": item.get("origins", [])}, ensure_ascii=False).encode("utf-8")
            return _merge_staged_payload({"accounts.json": raw_bytes}, staged_sessions)
        return {"ok": False, "error": "قائمة JSON هذه لا تطابق صيغة accounts.json."}

    if isinstance(parsed, dict):
        if "users" in fname_low or any(str(k).lstrip("-").isdigit() and isinstance(v, dict) and ("permissions" in v or "status" in v) for k, v in parsed.items()):
            return _merge_staged_payload({"users.json": raw_bytes}, {})
        return {"ok": False, "error": "كائن JSON هذا لا يطابق صيغة users.json."}

    return {"ok": False, "error": "صيغة الملف غير مدعومة للدمج."}


def _resolve_hf_sync_config() -> tuple[str, str]:
    token = (os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_TOKEN") or "").strip()
    if not token:
        return "", ""
    repo = (os.environ.get("HF_BACKUP_REPO") or os.environ.get("HF_DATA_REPO") or "").strip()
    if not repo:
        space_id = (os.environ.get("SPACE_ID") or "").strip()
        if "/" in space_id:
            repo = f"{space_id}-data"
    return token, repo


def hf_dataset_sync_download() -> dict:
    """
    استعادة تلقائية عند الإقلاع من Hugging Face Private Dataset إذا كان HF_TOKEN مضبوطاً
    وكانت قاعدة البيانات المحلية فارغة/جديدة بعد إعادة بناء السيرفر.
    """
    global _last_hf_status
    token, repo = _resolve_hf_sync_config()
    if not token or not repo:
        return {"ok": False, "skipped": True, "reason": "no_hf_config"}

    acc_m, adm_m, _ = _active_modules()
    local_users = adm_m.load_users()
    local_accs = acc_m.load_accounts()
    if len(local_users) > 1 or len(local_accs) > 0:
        _last_hf_status = f"متصل ({repo}) — البيانات المحلية موجودة مسبقاً"
        return {"ok": True, "skipped": True, "reason": "local_data_present"}

    url = f"https://huggingface.co/datasets/{repo}/resolve/main/fb_operator_snapshot.zip"
    try:
        resp = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=25)
        if resp.status_code == 200 and resp.content:
            res = restore_backup_zip_bytes(resp.content)
            if res.get("ok"):
                _last_hf_status = f"تمت الاستعادة من HF Dataset ({repo}) بنجاح ✅"
                return res
            _last_hf_status = f"فشل فك الحزمة من HF: {res.get('error')}"
            return res
        _last_hf_status = f"متصل ({repo}) — لم تُرفع نسخة بعد (HTTP {resp.status_code})"
        return {"ok": False, "status_code": resp.status_code}
    except Exception as e:
        _last_hf_status = f"تنبيه شبكة HF: {e}"
        return {"ok": False, "error": str(e)}


def hf_dataset_sync_upload() -> dict:
    """رفع النسخة الكاملة المضغوطة تلقائياً إلى Hugging Face Private Dataset"""
    global _last_hf_sync_ts, _last_hf_status, _last_backup_iso
    token, repo = _resolve_hf_sync_config()
    if not token or not repo or "/" not in repo:
        return {"ok": False, "skipped": True, "reason": "no_hf_config"}

    owner, name = repo.split("/", 1)
    headers = {"Authorization": f"Bearer {token}"}
    try:
        # إنشاء مستودع Dataset خاص تلقائياً إذا لم يكن منشأً بعد
        requests.post(
            "https://huggingface.co/api/repos/create",
            headers={**headers, "Content-Type": "application/json"},
            json={"type": "dataset", "name": name, "organization": owner, "private": True},
            timeout=15,
        )
    except Exception:
        pass

    zip_bytes = export_backup_zip_bytes(include_sessions=True)
    b64_payload = base64.b64encode(zip_bytes).decode("ascii")
    lines = [
        json.dumps({"key": "header", "value": {"summary": "Auto-backup FB Operator state & sessions"}}),
        json.dumps({"key": "file", "value": {"content": b64_payload, "path": "fb_operator_snapshot.zip", "encoding": "base64"}}),
    ]
    ndjson_body = "\n".join(lines).encode("utf-8")

    try:
        resp = requests.post(
            f"https://huggingface.co/api/datasets/{repo}/commit/main",
            headers={**headers, "Content-Type": "application/x-ndjson"},
            data=ndjson_body,
            timeout=35,
        )
        if 200 <= resp.status_code < 300:
            _last_hf_sync_ts = time.time()
            _last_backup_iso = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            _last_hf_status = f"مُحدّث وسليم في HF ({repo}) ✅ ({_last_backup_iso})"
            return {"ok": True, "repo": repo, "bytes": len(zip_bytes)}
        _last_hf_status = f"فشل الرفع لـ HF (HTTP {resp.status_code})"
        return {"ok": False, "status_code": resp.status_code, "body": resp.text[:200]}
    except Exception as e:
        _last_hf_status = f"خطأ شبكة HF: {e}"
        return {"ok": False, "error": str(e)}


def cloud_db_sync_upload(force: bool = False) -> dict:
    """مزامنة الحالة الكاملة إلى SQLite WAL المحلي + القاعدة السحابية الخارجية (Turso/Supabase/Firebase)."""
    global _last_cloud_db_sync_ts
    docs, sessions = collect_persistent_snapshot()
    res = cloud_db.push_cloud_db_state(docs, sessions, force=force)
    if res.get("ok") and not res.get("cloud_skipped"):
        _last_cloud_db_sync_ts = time.time()
    return res


def cloud_db_sync_download(mode: str = "auto") -> dict:
    """
    استرجاع البيانات من القاعدة السحابية الخارجية:
    - mode='auto': يُستعاد عند الإقلاع فقط إذا كانت القاعدة المحلية فارغة.
    - mode='merge': دمج ذكي مع البيانات المحلية بدون حذف أو تكرار.
    - mode='replace': استبدال القاعدة المحلية بما في السحابة.
    """
    acc_m, adm_m, _ = _active_modules()
    local_users = adm_m.load_users()
    local_accs = acc_m.load_accounts()
    if mode == "auto" and (len(local_users) > 1 or len(local_accs) > 0):
        return {"ok": True, "skipped": True, "reason": "local_data_present"}

    pulled = cloud_db.pull_cloud_db_state()
    if not pulled.get("ok"):
        return pulled
    docs = pulled.get("docs") or {}
    sessions = pulled.get("sessions") or {}
    if not docs and not sessions:
        return {"ok": True, "skipped": True, "reason": "cloud_empty"}

    if mode == "merge":
        return _merge_staged_payload(docs, sessions)
    res = _apply_full_snapshot(docs, sessions, clear_missing_sessions=True)
    res["provider"] = pulled.get("provider", "")
    return res


def _active_external_vault_path() -> Path | None:
    """إرجاع مسار ملف الخزنة الخارجي المعزول بجانب مجلد الأكواد مع احترام عزل مجلد الاختبارات."""
    acc_m, _, _ = _active_modules()
    active_dir = Path(acc_m.ACCOUNTS_FILE).parent
    base_data_dir = Path(_cfg.DATA_DIR)
    explicit_v = getattr(_cfg, "EXTERNAL_VAULT_FILE", None)

    # أثناء تشغيل الاختبارات في مجلد مؤقت لا نلمس أي ملف خارج المجلد المؤقت إلا إذا تم توجيه EXTERNAL_VAULT_FILE إليه
    if active_dir != base_data_dir:
        if explicit_v:
            vp = Path(explicit_v)
            try:
                import tempfile as _tf
                vp_res = vp.resolve()
                if (
                    vp_res.parent == active_dir.resolve()
                    or str(vp_res).startswith(str(active_dir.resolve()))
                    or str(vp_res).startswith(str(Path(_tf.gettempdir()).resolve()))
                ):
                    return vp
            except Exception:
                return vp
        return None

    if explicit_v:
        return Path(explicit_v)
    return _cfg.resolve_external_vault_file()


def _vault_secret_key() -> str:
    return (os.environ.get("FB_VAULT_KEY") or os.environ.get("FB_VAULT_SECRET") or "").strip()


def _derive_vault_keys(secret: str, salt: bytes) -> tuple[bytes, bytes]:
    dk = hashlib.pbkdf2_hmac("sha256", secret.encode("utf-8"), salt + b"|fb_op_vault_v1", 100_000, dklen=64)
    return dk[:32], dk[32:]


def _ctr_xor(enc_key: bytes, nonce: bytes, data: bytes) -> bytes:
    out = bytearray(len(data))
    block_idx = 0
    pos = 0
    total = len(data)
    while pos < total:
        ks = hashlib.sha256(enc_key + nonce + block_idx.to_bytes(8, "big")).digest()
        take = min(32, total - pos)
        for i in range(take):
            out[pos + i] = data[pos + i] ^ ks[i]
        pos += take
        block_idx += 1
    return bytes(out)


def _encrypt_vault_envelope(docs_dict: dict[str, bytes], sessions_dict: dict[str, bytes], secret: str, ts_val: float) -> bytes:
    inner = {
        "docs": {k: v.decode("utf-8", errors="ignore") for k, v in docs_dict.items()},
        "sessions": {k: v.decode("utf-8", errors="ignore") for k, v in sessions_dict.items()},
        "updated_ts": ts_val,
    }
    plain_compressed = zlib.compress(json.dumps(inner, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), 6)
    salt = secrets.token_bytes(16)
    nonce = secrets.token_bytes(16)
    enc_k, mac_k = _derive_vault_keys(secret, salt)
    ct = _ctr_xor(enc_k, nonce, plain_compressed)
    tag = hmac.new(mac_k, b"v1" + salt + nonce + ct, hashlib.sha256).hexdigest()
    envelope = {
        "format": "fb_operator_vault_enc_v1",
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "updated_ts": ts_val,
        "salt": base64.b64encode(salt).decode("ascii"),
        "nonce": base64.b64encode(nonce).decode("ascii"),
        "mac": tag,
        "ciphertext": base64.b64encode(ct).decode("ascii"),
    }
    return json.dumps(envelope, ensure_ascii=False, indent=2).encode("utf-8")


def _decrypt_vault_envelope(env: dict, secret: str) -> dict:
    if not secret:
        return {"ok": False, "error": "الملف الخارجي مشفّر ويتطلب مفتاح FB_VAULT_KEY في أسرار التشغيل لفك تشفيره."}
    try:
        salt = base64.b64decode(env["salt"])
        nonce = base64.b64decode(env["nonce"])
        ct = base64.b64decode(env["ciphertext"])
        given_mac = str(env.get("mac") or "").strip().lower()
        enc_k, mac_k = _derive_vault_keys(secret, salt)
        expected_mac = hmac.new(mac_k, b"v1" + salt + nonce + ct, hashlib.sha256).hexdigest().lower()
        if not hmac.compare_digest(given_mac, expected_mac):
            return {"ok": False, "error": "فشل التحقق من توقيع أو مفتاح تشفير الملف الخارجي (FB_VAULT_KEY)."}
        raw_json = zlib.decompress(_ctr_xor(enc_k, nonce, ct)).decode("utf-8")
        inner = json.loads(raw_json)
        return {"ok": True, "inner": inner}
    except Exception as e:
        return {"ok": False, "error": f"تعذر فك تشفير الخزنة الخارجية: {e}"}


def _extract_docs_sessions_from_raw(docs_raw: dict, sess_raw: dict) -> tuple[dict[str, bytes], dict[str, bytes]]:
    docs: dict[str, bytes] = {}
    sessions: dict[str, bytes] = {}
    for fname, txt in (docs_raw or {}).items():
        if fname in WHITELIST_JSON_FILES and isinstance(txt, (str, dict, list)):
            s = txt if isinstance(txt, str) else json.dumps(txt, ensure_ascii=False, indent=2)
            docs[fname] = s.encode("utf-8")
    for sname, txt in (sess_raw or {}).items():
        clean_s = sname if str(sname).endswith(".json") else f"{sname}.json"
        if re.fullmatch(r"acc_\d+\.json", clean_s) and isinstance(txt, (str, dict)):
            s = txt if isinstance(txt, str) else json.dumps(txt, ensure_ascii=False, indent=2)
            sessions[clean_s] = s.encode("utf-8")
    return docs, sessions


def read_external_vault(vault_path: Path | None = None) -> dict:
    """قراءة وتحليل ملف الخزنة الخارجي المعزول خارج مجلد الأكواد بجميع صيغه (فارغ / عادي / مشفر / JSON قديم)."""
    vp = vault_path or _active_external_vault_path()
    if not vp:
        return {"ok": False, "exists": False, "reason": "not_configured", "docs": {}, "sessions": {}}
    if not vp.exists():
        return {"ok": False, "exists": False, "path": str(vp), "reason": "not_found", "docs": {}, "sessions": {}}

    try:
        raw_txt = vp.read_text(encoding="utf-8", errors="ignore").strip()
    except Exception as e:
        return {"ok": False, "exists": True, "path": str(vp), "error": str(e), "docs": {}, "sessions": {}}

    if not raw_txt or raw_txt in ("{}", "[]", "null") or raw_txt.startswith("#"):
        return {"ok": True, "exists": True, "empty": True, "path": str(vp), "updated_ts": 0.0, "docs": {}, "sessions": {}}

    try:
        parsed = json.loads(raw_txt)
    except Exception as e:
        return {"ok": False, "exists": True, "path": str(vp), "error": f"تنسيق JSON غير صالح: {e}", "docs": {}, "sessions": {}}

    if isinstance(parsed, dict) and parsed.get("format") == "fb_operator_vault_enc_v1":
        dec = _decrypt_vault_envelope(parsed, _vault_secret_key())
        if not dec.get("ok"):
            return {"ok": False, "exists": True, "path": str(vp), "encrypted": True, "error": dec.get("error"), "docs": {}, "sessions": {}}
        inner = dec["inner"]
        docs, sessions = _extract_docs_sessions_from_raw(inner.get("docs") or {}, inner.get("sessions") or {})
        return {
            "ok": True,
            "exists": True,
            "empty": not docs and not sessions,
            "encrypted": True,
            "path": str(vp),
            "updated_ts": float(parsed.get("updated_ts") or inner.get("updated_ts") or 0.0),
            "docs": docs,
            "sessions": sessions,
        }

    if isinstance(parsed, dict) and parsed.get("format") == "fb_operator_vault_v1":
        docs, sessions = _extract_docs_sessions_from_raw(parsed.get("docs") or {}, parsed.get("sessions") or {})
        return {
            "ok": True,
            "exists": True,
            "empty": not docs and not sessions,
            "encrypted": False,
            "path": str(vp),
            "updated_ts": float(parsed.get("updated_ts") or 0.0),
            "docs": docs,
            "sessions": sessions,
        }

    # دعم تلقائي إذا لصق المستخدم محتوى accounts.json أو users.json خاماً داخل الملف الخارجي
    if isinstance(parsed, list):
        staged_sess: dict[str, bytes] = {}
        for item in parsed:
            if isinstance(item, dict) and isinstance(item.get("cookies"), list) and item.get("id"):
                aid = str(item["id"])
                if re.fullmatch(r"acc_\d+", aid):
                    staged_sess[f"{aid}.json"] = json.dumps({"cookies": item["cookies"], "origins": item.get("origins", [])}, ensure_ascii=False).encode("utf-8")
        return {
            "ok": True,
            "exists": True,
            "empty": len(parsed) == 0,
            "legacy_merge": True,
            "path": str(vp),
            "updated_ts": float(vp.stat().st_mtime),
            "docs": {"accounts.json": raw_txt.encode("utf-8")},
            "sessions": staged_sess,
        }

    if isinstance(parsed, dict):
        looks_like_users = any(str(k).lstrip("-").isdigit() and isinstance(v, dict) and ("permissions" in v or "status" in v) for k, v in parsed.items())
        if looks_like_users:
            return {
                "ok": True,
                "exists": True,
                "empty": False,
                "legacy_merge": True,
                "path": str(vp),
                "updated_ts": float(vp.stat().st_mtime),
                "docs": {"users.json": raw_txt.encode("utf-8")},
                "sessions": {},
            }
        # إذا كان قاموس docs مباشر بدون غلاف format
        docs, sessions = _extract_docs_sessions_from_raw(parsed.get("docs") or parsed, parsed.get("sessions") or {})
        return {
            "ok": True,
            "exists": True,
            "empty": not docs and not sessions,
            "path": str(vp),
            "updated_ts": float(parsed.get("updated_ts") or vp.stat().st_mtime),
            "docs": docs,
            "sessions": sessions,
        }

    return {"ok": False, "exists": True, "path": str(vp), "error": "بنية الملف الخارجي غير مدعومة.", "docs": {}, "sessions": {}}


def write_external_vault(docs_dict: dict[str, bytes] | None = None, sessions_dict: dict[str, bytes] | None = None, vault_path: Path | None = None) -> dict:
    """كتابة اللقطة الكاملة (كل القواعد الـ 9 والجلسات) إلى الملف الخارجي المعزول بجانب المجلد."""
    global _last_vault_sync_ts, _last_vault_status
    vp = vault_path or _active_external_vault_path()
    if not vp:
        return {"ok": True, "skipped": True, "reason": "no_external_vault"}

    if docs_dict is None or sessions_dict is None:
        docs_dict, sessions_dict = collect_persistent_snapshot()

    ts_val = time.time()
    secret = _vault_secret_key()
    try:
        if secret:
            raw_bytes = _encrypt_vault_envelope(docs_dict, sessions_dict, secret, ts_val)
            enc_mode = True
        else:
            payload = {
                "format": "fb_operator_vault_v1",
                "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "updated_ts": ts_val,
                "docs": {k: v.decode("utf-8", errors="ignore") for k, v in docs_dict.items()},
                "sessions": {k: v.decode("utf-8", errors="ignore") for k, v in sessions_dict.items()},
            }
            raw_bytes = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
            enc_mode = False
        _atomic_write_bytes(vp, raw_bytes)
        _last_vault_sync_ts = ts_val
        _last_vault_status = f"متصل ({vp.name} | {'مشفّر PBKDF2/HMAC' if enc_mode else 'مباشر'} | {datetime.now().strftime('%H:%M:%S')})"
        return {"ok": True, "path": str(vp), "encrypted": enc_mode, "bytes": len(raw_bytes)}
    except Exception as e:
        _last_vault_status = f"خطأ كتابة الخزنة الخارجية: {str(e)[:120]}"
        return {"ok": False, "path": str(vp), "error": str(e)}


def bootstrap_persistence() -> dict:
    """تهيئة مجلد البيانات المنفصل واستعادة النسخة من الخزنة الخارجية / القاعدة السحابية / HF قبل أي ترحيل قديم"""
    global _last_vault_status
    acc_m, adm_m, _ = _active_modules()
    ext_vp = _active_external_vault_path()
    ext_res: dict = {"ok": True, "skipped": True, "reason": "not_configured"}
    cdb_res: dict = {"ok": True, "skipped": True, "reason": "not_checked"}

    local_empty_before = (len(adm_m.load_users()) <= 1 and len(acc_m.load_accounts()) == 0)
    ext_peek = read_external_vault(ext_vp) if ext_vp else {"ok": False, "exists": False}
    if ext_peek.get("error"):
        _last_vault_status = f"تنبيه: {ext_peek['error']}"

    # إذا كان هناك ملف خزنة خارجي بجانب المجلد يحتوي على بيانات
    if ext_peek.get("ok") and not ext_peek.get("empty"):
        if ext_peek.get("legacy_merge"):
            m_res = _merge_staged_payload(ext_peek["docs"], ext_peek["sessions"])
            ext_res = {**m_res, "source": "external_vault_legacy_merge", "path": ext_peek.get("path", "")}
            _last_vault_status = f"تم استيراد ودمج البيانات من {Path(ext_peek['path']).name}"
        elif local_empty_before:
            snap_res = _apply_full_snapshot(ext_peek["docs"], ext_peek["sessions"], clear_missing_sessions=True)
            ext_res = {**snap_res, "source": "external_vault", "path": ext_peek.get("path", "")}
            _last_vault_status = f"متصل — استعيدت البيانات من {Path(ext_peek['path']).name}"
        else:
            # كلاهما فيه بيانات: ادمج غير مدمّر بدون حذف أي تعديل محلي
            m_res = _merge_staged_payload(ext_peek["docs"], ext_peek["sessions"])
            ext_res = {**m_res, "source": "external_vault_merge", "path": ext_peek.get("path", "")}
            _last_vault_status = f"متصل — دُمجت المحدثات من {Path(ext_peek['path']).name}"

    # التحقق من القاعدة السحابية الخارجية (Turso/Supabase/Firebase) — استعادة عند الفراغ أو دمج التحديثات
    local_empty_now = (len(adm_m.load_users()) <= 1 and len(acc_m.load_accounts()) == 0)
    cdb_cfg = cloud_db.load_cloud_db_config(mask_secrets=False)
    if cdb_cfg.get("enabled"):
        cdb_res = cloud_db_sync_download(mode="auto" if local_empty_now else "merge")
    else:
        cdb_res = {"ok": True, "skipped": True, "reason": "not_configured"}

    hf_res = hf_dataset_sync_download()
    mig = migrate_legacy_data()
    purged_cnt, purged_names = acc_m.purge_expired_broken_accounts(_cfg.BROKEN_ACCOUNT_TTL_HOURS)

    # مزامنة مرآة SQLite المحلية والملف الخارجي بجانب المجلد إذا وُجد مساره
    try:
        docs, sessions = collect_persistent_snapshot()
        cloud_db.write_local_sqlite_mirror(docs, sessions)
        if ext_vp and (ext_vp.exists() or len(acc_m.load_accounts()) > 0 or len(adm_m.load_users()) > 1):
            if ext_peek.get("empty") or ext_peek.get("legacy_merge") or not ext_vp.exists():
                if docs or sessions:
                    write_external_vault(docs, sessions, ext_vp)
            elif not _last_vault_status or _last_vault_status == "غير مهيأ بعد":
                _last_vault_status = f"متصل ({ext_vp.name})"
    except Exception:
        pass

    restored_ok = bool(
        (ext_res.get("ok") and not ext_res.get("skipped"))
        or (cdb_res.get("ok") and not cdb_res.get("skipped"))
        or (hf_res.get("ok") and not hf_res.get("skipped"))
    )
    global _last_tg_vault_ts
    if _last_tg_vault_ts <= 0.0:
        _last_tg_vault_ts = time.time()
    return {
        "restored": restored_ok,
        "data_dir": str(_cfg.DATA_DIR),
        "external_vault_restore": ext_res,
        "external_vault_path": str(ext_vp) if ext_vp else "",
        "migration": mig,
        "cloud_db_restore": cdb_res,
        "hf_restore": hf_res,
        "purged_24h": purged_cnt,
        "purged_names": purged_names,
    }


def _safe_json_len(path: Path, expected_type) -> int:
    if not path.exists() or not path.is_file():
        return 0
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return len(data) if isinstance(data, expected_type) else 0
    except Exception:
        return 0


def send_backup_to_channel(bot, channel_id=None, trigger_label: str = "يدوي") -> dict:
    """إرسال نسخة احتياطية كاملة الصلاحيات والضبط والحسابات إلى قناة النسخ الاحتياطي المحددة"""
    global _last_tg_vault_ts, _last_backup_iso, _channel_synced_seq
    if bot is None:
        return {"ok": False, "error": "كائن البوت غير متاح لإرسال النسخة."}

    is_manual = trigger_label in ("إرسال يدوي فوري", "نسخ يدوي فوري", "اختبار الربط", "يدوي")
    with _tg_send_lock:
        meta = load_backup_settings()
        target_ch = channel_id if channel_id is not None else meta.get("channel_id")
        if not target_ch:
            return {"ok": False, "error": "لم يتم ربط قناة نسخ احتياطي بعد."}

        now = time.time()
        last_ts = float(meta.get("last_channel_backup_ts") or 0.0)
        min_gap = max(5.0, min(30.0, float(meta.get("interval_seconds") or 3600) * 0.5))
        if not is_manual and last_ts > 0 and (now - last_ts) < min_gap:
            return {"ok": True, "skipped": True, "reason": "cooldown_dedup"}

        with _sync_lock:
            snapshot_dirty_seq = _dirty_seq

        now_iso = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        next_num = int(meta.get("channel_backup_count") or 0) + 1
        try:
            zip_bytes = export_backup_zip_bytes(include_sessions=True)
            st_info = get_persistence_status()
            bio = io.BytesIO(zip_bytes)
            bio.name = f"fb_op_bkp_{next_num}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
            caption = (
                f"💾 <b>نسخة احتياطية شاملة #{next_num} (#FB_BACKUP)</b>\n"
                f"🕒 <code>{now_iso}</code> | 📌 <b>{trigger_label}</b>\n"
                f"👥 المستخدمون: <b>{st_info['users_count']}</b> | 📱 الحسابات: <b>{st_info['accounts_count']}</b> (🟢 {st_info['active_accounts']}) | 🍪 الجلسات: <b>{st_info['sessions_count']}</b>\n"
                f"💰 القيود المالية: <b>{st_info['ledger_count']}</b> | 🎟️ الدعوات: <b>{st_info['invites_count']}</b> | 💬 التذاكر: <b>{st_info['tickets_count']}</b>\n"
                f"🎛️ حالات الضبط والواجهة: <b>{st_info['ui_states_count']}</b> | 📜 السجلات: <b>{st_info['audit_count']}</b>\n"
                f"⏱️ الجدولة: <b>{meta['interval_label']}</b>\n"
                "📥 <i>للاسترجاع الفوري: أرسل أو أعد توجيه هذا الملف للبوت ليعود كل شيء كما كان الآن.</i>"
            )
            bot.send_document(target_ch, bio, caption=caption, parse_mode="HTML")
            _last_tg_vault_ts = now
            _last_backup_iso = now_iso
            save_backup_settings(
                {
                    "last_channel_backup_ts": now,
                    "last_channel_backup_iso": now_iso,
                    "channel_backup_count": next_num,
                    "last_trigger": trigger_label,
                    "last_error": "",
                },
                mark_dirty=False,
            )
            with _sync_lock:
                _channel_synced_seq = max(_channel_synced_seq, snapshot_dirty_seq)
            return {"ok": True, "backup_number": next_num, "size_bytes": len(zip_bytes), "timestamp": now_iso}
        except Exception as e:
            err_msg = str(e)[:250]
            save_backup_settings({"last_error": err_msg}, mark_dirty=False)
            return {"ok": False, "error": err_msg}


def _is_dm_backup_due(meta: dict, now: float, current_dirty: int, already_synced: int, force: bool, last_dm_ts: float) -> bool:
    """تحديد استحقاق إرسال نسخة DM للمطور مع الالتزام الصارم بإعدادات الإيقاف والجدولة الزمنية."""
    if force:
        return True
    if not bool(meta.get("enabled", True)) or not bool(meta.get("dm_enabled", True)):
        return False
    if current_dirty <= already_synced:
        return False
    interval_s = max(MIN_BACKUP_INTERVAL_SEC, int(meta.get("interval_seconds") or 3600))
    elapsed = now - float(last_dm_ts or 0.0)
    if elapsed >= interval_s:
        return True
    if bool(meta.get("on_change")) and elapsed >= max(60.0, min(float(interval_s), 180.0)):
        return True
    return False


def flush_cloud_backups(bot=None, super_admin_id: int = 0, force: bool = False, skip_tg_dm: bool = False) -> None:
    """مزامنة دورية مضبوطة التوقيت إلى SQLite + الملف الخارجي بجانب المجلد + القاعدة السحابية + HF + قناة النسخ"""
    global _synced_seq, _cloud_db_synced_seq, _sqlite_synced_seq, _vault_synced_seq, _last_tg_vault_ts, _last_tg_dm_hash, _last_backup_iso
    with _sync_lock:
        current_dirty = _dirty_seq
        already_synced = _synced_seq
        cdb_synced = _cloud_db_synced_seq
        sql_synced = _sqlite_synced_seq
        vault_synced = _vault_synced_seq
        ch_synced = _channel_synced_seq

    token, _ = _resolve_hf_sync_config()
    cdb_cfg = cloud_db.load_cloud_db_config(mask_secrets=False)
    ext_vp = _active_external_vault_path()
    now = time.time()

    docs_snap = None
    sessions_snap = None

    # 1. مرآة SQLite WAL المحلية الفورية عند أي تغيير
    if force or current_dirty > sql_synced:
        try:
            docs_snap, sessions_snap = collect_persistent_snapshot()
            sql_res = cloud_db.write_local_sqlite_mirror(docs_snap, sessions_snap)
            if sql_res.get("ok"):
                with _sync_lock:
                    _sqlite_synced_seq = max(_sqlite_synced_seq, current_dirty)
        except Exception:
            pass

    # 1ب. تحديث الملف الخارجي المعزول بجانب مجلد الأكواد (fb_operator_vault.json) ومزامنته مع Git
    if ext_vp and (force or current_dirty > vault_synced):
        try:
            if docs_snap is None or sessions_snap is None:
                docs_snap, sessions_snap = collect_persistent_snapshot()
            v_res = write_external_vault(docs_snap, sessions_snap, ext_vp)
            if v_res.get("ok") and not v_res.get("skipped"):
                with _sync_lock:
                    _vault_synced_seq = max(_vault_synced_seq, current_dirty)
                try:
                    acc_m, _, _ = _active_modules()
                    if hasattr(acc_m, "sync_external_vault_git"):
                        acc_m.sync_external_vault_git(force=force)
                except Exception:
                    pass
        except Exception:
            pass

    # 2. مزامنة سريعة إلى القاعدة السحابية الخارجية المجانية (Turso / Supabase / Firebase)
    if cdb_cfg.get("enabled") and (force or (current_dirty > cdb_synced and (now - _last_cloud_db_sync_ts) >= 12.0)):
        res_cdb = cloud_db_sync_upload(force=force)
        if res_cdb.get("ok") and not res_cdb.get("cloud_skipped"):
            with _sync_lock:
                _cloud_db_synced_seq = max(_cloud_db_synced_seq, current_dirty)

    # 3. مزامنة Hugging Face Dataset
    did_hf_sync = False
    if token and (force or (current_dirty > already_synced and (now - _last_hf_sync_ts) >= 45.0)):
        res = hf_dataset_sync_upload()
        if res.get("ok"):
            did_hf_sync = True

    if did_hf_sync:
        with _sync_lock:
            _synced_seq = max(_synced_seq, current_dirty)

    meta = load_backup_settings()
    if bot is not None and meta.get("channel_id"):
        interval_s = max(MIN_BACKUP_INTERVAL_SEC, int(meta.get("interval_seconds") or 3600))
        elapsed = now - float(meta.get("last_channel_backup_ts") or 0.0)
        due_schedule = bool(meta.get("enabled", True)) and (elapsed >= interval_s)
        due_onchange = bool(meta.get("on_change")) and (current_dirty > ch_synced) and (elapsed >= MIN_BACKUP_INTERVAL_SEC)
        if force or due_schedule or due_onchange:
            trigger = (
                "نسخ يدوي فوري"
                if force
                else (f"مجدول ({meta['interval_label']})" if due_schedule else "تعديل جديد بالبيانات")
            )
            send_backup_to_channel(bot, trigger_label=trigger)
        return

    if not skip_tg_dm and bot is not None and super_admin_id and _is_dm_backup_due(meta, now, current_dirty, already_synced, force, _last_tg_vault_ts):
        with _tg_send_lock:
            try:
                now_dm = time.time()
                if docs_snap is None or sessions_snap is None:
                    docs_snap, sessions_snap = collect_persistent_snapshot()
                h_snap = hashlib.sha256()
                for _dk in sorted(docs_snap.keys()):
                    h_snap.update(_dk.encode("utf-8"))
                    h_snap.update(b":")
                    h_snap.update(docs_snap[_dk])
                    h_snap.update(b"\0")
                for _sk in sorted(sessions_snap.keys()):
                    h_snap.update(b"sess/")
                    h_snap.update(_sk.encode("utf-8"))
                    h_snap.update(b":")
                    h_snap.update(sessions_snap[_sk])
                    h_snap.update(b"\0")
                snap_digest = h_snap.hexdigest()
                if snap_digest == _last_tg_dm_hash and (not force or (now_dm - _last_tg_vault_ts) < 120.0):
                    _last_tg_vault_ts = now_dm
                    if not token:
                        with _sync_lock:
                            _synced_seq = max(_synced_seq, current_dirty)
                    return
                zip_bytes = export_backup_zip_bytes(include_sessions=True)
                zip_digest = snap_digest
                st_info = get_persistence_status()
                bio = io.BytesIO(zip_bytes)
                bio.name = f"fb_operator_backup_{datetime.now().strftime('%Y%m%d_%H%M')}.zip"
                caption = (
                    "💾 <b>نسخة احتياطية تلقائية شاملة (#FB_BACKUP)</b>\n"
                    f"👥 المستخدمون: <b>{st_info['users_count']}</b> | 📱 الحسابات: <b>{st_info['accounts_count']}</b> "
                    f"(🟢 {st_info['active_accounts']}) | 🍪 الجلسات: <b>{st_info['sessions_count']}</b>\n"
                    "<i>أعد إرسال هذا الملف للبوت بعد أي تحديث للسيرفر لاسترجاع كل شيء في ثانية!</i>"
                )
                bot.send_document(super_admin_id, bio, caption=caption, parse_mode="HTML")
                _last_tg_vault_ts = time.time()
                _last_tg_dm_hash = zip_digest
                _last_backup_iso = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                if not token:
                    with _sync_lock:
                        _synced_seq = max(_synced_seq, current_dirty)
            except Exception:
                pass


def get_persistence_status() -> dict:
    json_map, _, sessions_dir = _active_paths()
    acc_m, adm_m, _ = _active_modules()
    users = adm_m.load_users()
    accs = acc_m.load_accounts()
    active_accs = sum(1 for a in accs if "نشط" in str(a.get("status", "")))
    broken_accs = max(0, len(accs) - active_accs)
    sess_cnt = len(list(sessions_dir.glob("acc_*.json"))) if sessions_dir.exists() else 0
    token, repo = _resolve_hf_sync_config()
    bkp_cfg = load_backup_settings()
    ext_vp = _active_external_vault_path()
    return {
        "data_dir": str(_cfg.DATA_DIR),
        "code_dir": str(_cfg.BASE_DIR),
        "separated": str(_cfg.DATA_DIR) != str(_cfg.BASE_DIR),
        "external_vault": {
            "configured": bool(ext_vp),
            "exists": bool(ext_vp and ext_vp.exists()),
            "path": str(ext_vp) if ext_vp else "",
            "filename": getattr(_cfg, "EXTERNAL_VAULT_FILENAME", "fb_operator_vault.json"),
            "encrypted": bool(_vault_secret_key()),
            "status": _last_vault_status,
        },
        "hf_enabled": bool(token and repo),
        "hf_repo": repo,
        "hf_status": _last_hf_status,
        "users_count": len(users),
        "accounts_count": len(accs),
        "active_accounts": active_accs,
        "broken_accounts": broken_accs,
        "sessions_count": sess_cnt,
        "ledger_count": _safe_json_len(json_map["points_ledger.json"], list),
        "invites_count": _safe_json_len(json_map["invite_codes.json"], list),
        "tickets_count": _safe_json_len(json_map["support_tickets.json"], list),
        "audit_count": _safe_json_len(json_map["audit_logs.json"], list),
        "ui_states_count": _safe_json_len(json_map["ui_states.json"], dict),
        "temp_emails_count": _safe_json_len(json_map["temp_emails.json"], dict),
        "trash_emails_count": _safe_json_len(json_map["trash_emails.json"], list),
        "backup_channel": bkp_cfg,
        "cloud_db": cloud_db.get_cloud_db_status_summary(),
        "last_backup_iso": bkp_cfg.get("last_channel_backup_iso") or _last_backup_iso or "لم يُصدر بعد في هذه الجلسة",
    }
