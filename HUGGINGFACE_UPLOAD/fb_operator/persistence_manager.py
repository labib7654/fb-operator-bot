"""
محرك الحفظ الدائم وعزل البيانات عن مجلد الأكواد (Persistent Storage, Backup Vault & Cloud Sync)
يضمن عدم فقدان بيانات المستخدمين، الرصيد المالي، التذاكر، الحسابات، وجلسات المتصفح
عند إعادة رفع التحديثات فوق السيرفر أو إعادة بناء حاوية Hugging Face.
"""

import base64
import io
import json
import os
import re
import shutil
import stat
import threading
import time
import zipfile
from datetime import datetime
from pathlib import Path

import requests
import fb_operator.config as _cfg
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
)

_SESSION_ENTRY_RE = re.compile(r"^sessions/(acc_\d+)\.json$")
_MAX_ZIP_BYTES = 25 * 1024 * 1024
_MAX_ENTRY_BYTES = 5 * 1024 * 1024
_MAX_TOTAL_UNCOMPRESSED = 40 * 1024 * 1024

_sync_lock = threading.Lock()
_dirty_seq = 0
_synced_seq = 0
_channel_synced_seq = 0
_last_hf_sync_ts = 0.0
_last_tg_vault_ts = 0.0
_last_backup_iso = ""
_last_hf_status = "غير مفعّل (أضف HF_TOKEN في Secrets للمزامنة السحابية التلقائية)"
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
    base_data_dir = Path(cfg_m.DATA_DIR)
    meta_path = (active_data_dir / "backup_meta.json") if (raw_meta.parent == base_data_dir and active_data_dir != base_data_dir) else raw_meta
    ui_path = (active_data_dir / "ui_states.json") if (raw_ui.parent == base_data_dir and active_data_dir != base_data_dir) else raw_ui

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


def restore_backup_zip_bytes(raw_bytes: bytes) -> dict:
    """
    استعادة حزمة النسخة الاحتياطية بأمان تام (حماية كاملة ضد ZipSlip والملفات الخبيثة وقنابل الضغط)
    مع التحقق من صحة JSON لكل ملف قبل الكتابة الذرية.
    """
    global _last_backup_iso
    if not raw_bytes or len(raw_bytes) > _MAX_ZIP_BYTES:
        return {"ok": False, "error": "حجم ملف النسخة الاحتياطية غير صالح أو يتجاوز الحد المسموح (25MB)."}

    acc_m, adm_m, eco_m = _active_modules()
    json_map, profiles_dir, sessions_dir = _active_paths()

    staged_json: dict[str, bytes] = {}
    staged_sessions: dict[str, bytes] = {}
    manifest_info: dict = {}

    try:
        with zipfile.ZipFile(io.BytesIO(raw_bytes), mode="r") as zf:
            total_uncomp = 0
            for info in zf.infolist():
                if info.is_dir():
                    continue
                # منع الروابط الرمزية (Symlinks) وهجمات Path Traversal
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
                    if clean_name in ("accounts.json", "audit_logs.json", "points_ledger.json", "invite_codes.json", "support_tickets.json") and not isinstance(parsed, list):
                        return {"ok": False, "error": f"بنية غير صحيحة للملف: {clean_name}"}
                    if clean_name in ("users.json", "economy_settings.json", "backup_meta.json", "ui_states.json") and not isinstance(parsed, dict):
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

    restored_acc_ids: set[str] = set()
    with _meta_lock, eco_m._economy_lock, adm_m._users_lock, acc_m._accounts_lock:
        for fname, content in staged_json.items():
            target = json_map[fname]
            if fname == "accounts.json":
                try:
                    accs = json.loads(content.decode("utf-8"))
                    for a in accs:
                        aid = a.get("id")
                        if aid:
                            restored_acc_ids.add(str(aid))
                            p_dir = profiles_dir / aid
                            p_dir.mkdir(parents=True, exist_ok=True)
                            a["profile_dir"] = str(p_dir.resolve())
                    content = json.dumps(accs, ensure_ascii=False, indent=2).encode("utf-8")
                except Exception:
                    pass
            _atomic_write_bytes(target, content)

        sessions_dir.mkdir(parents=True, exist_ok=True)
        if "accounts.json" in staged_json and manifest_info.get("format") == "fb_operator_backup_v2" and manifest_info.get("includes_sessions", True):
            for existing_sf in list(sessions_dir.glob("acc_*.json")):
                if existing_sf.name not in staged_sessions:
                    try:
                        existing_sf.unlink()
                    except Exception:
                        pass
        elif "accounts.json" in staged_json and staged_sessions:
            for existing_sf in list(sessions_dir.glob("acc_*.json")):
                if existing_sf.name not in staged_sessions and existing_sf.stem not in restored_acc_ids:
                    try:
                        existing_sf.unlink()
                    except Exception:
                        pass

        for s_name, s_bytes in staged_sessions.items():
            _atomic_write_bytes(sessions_dir / s_name, s_bytes)

        users_cnt = len(adm_m.load_users())
        accs_cnt = len(acc_m.load_accounts())

    global _channel_synced_seq
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
        "manifest": manifest_info,
    }


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


def bootstrap_persistence() -> dict:
    """تهيئة مجلد البيانات المنفصل واستعادة النسخة السحابية وتنظيف التالف الأقدم من 24 ساعة"""
    mig = migrate_legacy_data()
    hf_res = hf_dataset_sync_download()
    acc_m, _, _ = _active_modules()
    purged_cnt, purged_names = acc_m.purge_expired_broken_accounts(_cfg.BROKEN_ACCOUNT_TTL_HOURS)
    return {
        "migration": mig,
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

    meta = load_backup_settings()
    target_ch = channel_id if channel_id is not None else meta.get("channel_id")
    if not target_ch:
        return {"ok": False, "error": "لم يتم ربط قناة نسخ احتياطي بعد."}

    with _sync_lock:
        snapshot_dirty_seq = _dirty_seq

    now = time.time()
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


def flush_cloud_backups(bot=None, super_admin_id: int = 0, force: bool = False) -> None:
    """مزامنة دورية مضبوطة التوقيت إلى Hugging Face + قناة النسخ الاحتياطي أو خزنة المطور"""
    global _synced_seq, _last_tg_vault_ts, _last_backup_iso
    with _sync_lock:
        current_dirty = _dirty_seq
        already_synced = _synced_seq
        ch_synced = _channel_synced_seq

    token, _ = _resolve_hf_sync_config()
    now = time.time()
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

    if bot is not None and super_admin_id and (force or (current_dirty > already_synced and (now - _last_tg_vault_ts) >= 180.0)):
        try:
            zip_bytes = export_backup_zip_bytes(include_sessions=True)
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
    return {
        "data_dir": str(_cfg.DATA_DIR),
        "code_dir": str(_cfg.BASE_DIR),
        "separated": str(_cfg.DATA_DIR) != str(_cfg.BASE_DIR),
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
        "backup_channel": bkp_cfg,
        "last_backup_iso": bkp_cfg.get("last_channel_backup_iso") or _last_backup_iso or "لم يُصدر بعد في هذه الجلسة",
    }
