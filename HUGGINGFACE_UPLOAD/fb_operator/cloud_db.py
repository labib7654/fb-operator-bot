"""
محرك قاعدة البيانات السحابية المجانية بدون فيزا + مرآة SQLite WAL المحلية
(Zero-Visa External Cloud Database + Local Transactional SQLite WAL Mirror)

يدعم 3 قواعد بيانات سحابية مجانية 100% بدون بطاقة بنكية عبر بروتوكول HTTPS قياسي (لا يتأثر بحجب منافذ 5432):
1. Turso (libSQL / SQLite Cloud — 9GB مجاني بلا فيزا، يعمل فوراً بـ URL + Token بدون إعداد جداول مسبق).
2. Supabase (PostgreSQL PostgREST HTTPS API — 500MB مجاني بلا فيزا).
3. Firebase Realtime Database (Spark Plan — مجاني بلا فيزا عبر REST HTTPS).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

_db_lock = threading.RLock()
_SUPABASE_CHUNK_SIZE = 50
_SUPABASE_PULL_PAGE_SIZE = 1000
_SUPABASE_ROW_HASH_CACHE: dict[str, dict[str, str]] = {}
_sync_state = {
    "last_push_ts": 0.0,
    "last_push_iso": "",
    "last_pull_ts": 0.0,
    "last_pull_iso": "",
    "last_error": "",
    "last_status": "قاعدة محلية نشطة | لم تُربط قاعدة خارجية بعد",
}

SUPPORTED_PROVIDERS = ("turso", "supabase", "firebase")
_ALLOWED_KEY_RE = re.compile(r"^[a-zA-Z0-9_.:-]{2,120}$")
_TABLE_NAME = "fb_operator_kv"
_META_DOC_DELETED_PREFIX = "__DELETED__"


def _active_db_paths() -> tuple[Path, Path]:
    """استرجاع مسارات cloud_db_config.json و fb_operator.db مع احترام عزل مجلد الاختبارات."""
    import fb_operator.config as cfg_m
    try:
        import fb_operator.account_manager as acc_m
        active_data_dir = Path(acc_m.ACCOUNTS_FILE).parent
    except Exception:
        active_data_dir = Path(cfg_m.DATA_DIR)

    base_data_dir = Path(cfg_m.DATA_DIR)
    raw_cfg = Path(getattr(cfg_m, "CLOUD_DB_CONFIG_FILE", base_data_dir / "cloud_db_config.json"))
    raw_sql = Path(getattr(cfg_m, "SQLITE_MIRROR_FILE", base_data_dir / "fb_operator.db"))

    if active_data_dir != base_data_dir:
        cfg_path = active_data_dir / "cloud_db_config.json" if raw_cfg.parent == base_data_dir else raw_cfg
        sql_path = active_data_dir / "fb_operator.db" if raw_sql.parent == base_data_dir else raw_sql
    else:
        cfg_path = raw_cfg
        sql_path = raw_sql
    return cfg_path, sql_path


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp.{threading.get_ident()}")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
        f.flush()
        try:
            os.fsync(f.fileno())
        except Exception:
            pass
    os.replace(tmp, path)


def _mask_secret(val: str) -> str:
    s = (val or "").strip()
    if not s:
        return ""
    if len(s) <= 8:
        return "*" * len(s)
    return f"{s[:4]}...{s[-4:]}"


def _clean_url(url: str) -> str:
    u = (url or "").strip().rstrip("/")
    return u


def _normalize_turso_http_url(raw_url: str) -> str:
    u = _clean_url(raw_url)
    if u.startswith("libsql://"):
        u = "https://" + u[len("libsql://"):]
    return u


def _load_file_cfg_unlocked() -> dict:
    cfg_path, _ = _active_db_paths()
    if not cfg_path.exists():
        fallback = Path(__file__).resolve().parent / "cloud_db_config.json"
        if fallback.exists():
            cfg_path = fallback
        else:
            return {}
    try:
        data = json.loads(cfg_path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def load_cloud_db_config(mask_secrets: bool = False) -> dict:
    """تحميل إعدادات القاعدة السحابية (متغيرات البيئة تتفوق عند تعيينها وإلا ملف الخزنة)."""
    with _db_lock:
        file_cfg = _load_file_cfg_unlocked()
        provider = (os.environ.get("CLOUD_DB_TYPE") or file_cfg.get("provider") or "").strip().lower()

        supa_url = _clean_url(os.environ.get("SUPABASE_URL") or file_cfg.get("supabase_url") or "")
        supa_key = (os.environ.get("SUPABASE_KEY") or file_cfg.get("supabase_key") or "").strip()

        turso_url = _normalize_turso_http_url(os.environ.get("TURSO_DB_URL") or file_cfg.get("turso_url") or "")
        turso_token = (os.environ.get("TURSO_AUTH_TOKEN") or file_cfg.get("turso_token") or "").strip()

        fb_url = _clean_url(os.environ.get("FIREBASE_DB_URL") or file_cfg.get("firebase_url") or "")
        fb_auth = (os.environ.get("FIREBASE_AUTH") or file_cfg.get("firebase_auth") or "").strip()

        if provider in ("", "auto"):
            if turso_url and turso_token:
                provider = "turso"
            elif supa_url and supa_key:
                provider = "supabase"
            elif fb_url:
                provider = "firebase"
            else:
                provider = ""

        enabled = False
        if provider == "turso":
            enabled = bool(turso_url and turso_token)
        elif provider == "supabase":
            enabled = bool(supa_url and supa_key)
        elif provider == "firebase":
            enabled = bool(fb_url)

        out = {
            "provider": provider,
            "enabled": enabled,
            "supabase_url": supa_url,
            "supabase_key": _mask_secret(supa_key) if mask_secrets else supa_key,
            "turso_url": turso_url,
            "turso_token": _mask_secret(turso_token) if mask_secrets else turso_token,
            "firebase_url": fb_url,
            "firebase_auth": _mask_secret(fb_auth) if mask_secrets else fb_auth,
            "updated_at": file_cfg.get("updated_at") or "",
        }
        return out


def save_cloud_db_config(patch: dict) -> dict:
    with _db_lock:
        cfg_path, _ = _active_db_paths()
        cur = _load_file_cfg_unlocked()
        if isinstance(patch, dict):
            for k in ("provider", "supabase_url", "supabase_key", "turso_url", "turso_token", "firebase_url", "firebase_auth"):
                if k in patch:
                    val = str(patch[k] or "").strip()
                    if k == "turso_url" and val:
                        val = _normalize_turso_http_url(val)
                    elif k in ("supabase_url", "firebase_url") and val:
                        val = _clean_url(val)
                    cur[k] = val
        cur["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        _atomic_write_text(cfg_path, json.dumps(cur, ensure_ascii=False, indent=2))
        return load_cloud_db_config(mask_secrets=True)


def clear_cloud_db_config() -> dict:
    with _db_lock:
        _SUPABASE_ROW_HASH_CACHE.clear()
        cfg_path, _ = _active_db_paths()
        if cfg_path.exists():
            try:
                cfg_path.unlink()
            except Exception:
                pass
        _sync_state["last_error"] = ""
        _sync_state["last_status"] = "قاعدة محلية نشطة | تم فصل القاعدة الخارجية"
        return load_cloud_db_config(mask_secrets=True)


# ==============================================================================
# 1. مرآة SQLite WAL المحلية الدائمة (Local Transactional SQLite WAL Mirror)
# ==============================================================================

def _open_sqlite(sql_path: Path) -> sqlite3.Connection:
    sql_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(sql_path), timeout=15.0)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute(
        f"CREATE TABLE IF NOT EXISTS {_TABLE_NAME} ("
        "doc_key TEXT PRIMARY KEY, "
        "payload TEXT NOT NULL, "
        "updated_at REAL NOT NULL)"
    )
    return conn


def write_local_sqlite_mirror(docs_dict: dict[str, bytes], sessions_dict: dict[str, bytes]) -> dict:
    """كتابة ذرية شاملة لكل ملفات JSON والجلسات في قاعدة SQLite WAL المحلية"""
    now = time.time()
    records: list[tuple[str, str, float]] = []
    valid_session_keys: set[str] = set()
    for fname, raw in (docs_dict or {}).items():
        key = f"doc:{fname}"
        txt = raw.decode("utf-8", errors="ignore") if isinstance(raw, (bytes, bytearray)) else str(raw)
        records.append((key, txt, now))
    for sfname, raw in (sessions_dict or {}).items():
        acc_id = sfname[:-5] if sfname.endswith(".json") else sfname
        key = f"session:{acc_id}"
        valid_session_keys.add(key)
        txt = raw.decode("utf-8", errors="ignore") if isinstance(raw, (bytes, bytearray)) else str(raw)
        records.append((key, txt, now))

    with _db_lock:
        _, sql_path = _active_db_paths()
        conn = _open_sqlite(sql_path)
        try:
            with conn:
                conn.executemany(
                    f"INSERT INTO {_TABLE_NAME} (doc_key, payload, updated_at) VALUES (?, ?, ?) "
                    f"ON CONFLICT(doc_key) DO UPDATE SET payload=excluded.payload, updated_at=excluded.updated_at",
                    records,
                )
                existing_sess = [
                    r[0] for r in conn.execute(f"SELECT doc_key FROM {_TABLE_NAME} WHERE doc_key LIKE 'session:%'").fetchall()
                ]
                stale = [(k,) for k in existing_sess if k not in valid_session_keys]
                if stale:
                    conn.executemany(f"DELETE FROM {_TABLE_NAME} WHERE doc_key = ?", stale)
            return {"ok": True, "records": len(records), "path": str(sql_path)}
        except Exception as e:
            return {"ok": False, "error": str(e)}
        finally:
            conn.close()


def read_local_sqlite_mirror() -> dict:
    with _db_lock:
        _, sql_path = _active_db_paths()
        if not sql_path.exists():
            return {"ok": True, "docs": {}, "sessions": {}}
        conn = _open_sqlite(sql_path)
        try:
            rows = conn.execute(f"SELECT doc_key, payload FROM {_TABLE_NAME}").fetchall()
            docs: dict[str, bytes] = {}
            sessions: dict[str, bytes] = {}
            for k, v in rows:
                if k.startswith("doc:"):
                    docs[k[4:]] = v.encode("utf-8")
                elif k.startswith("session:"):
                    sessions[f"{k[8:]}.json"] = v.encode("utf-8")
            return {"ok": True, "docs": docs, "sessions": sessions}
        except Exception as e:
            return {"ok": False, "error": str(e), "docs": {}, "sessions": {}}
        finally:
            conn.close()


# ==============================================================================
# 2. محولات السحابة المجانية بدون فيزا (Turso / Supabase / Firebase RTDB)
# ==============================================================================

def _build_kv_rows(docs_dict: dict[str, bytes], sessions_dict: dict[str, bytes]) -> tuple[dict[str, str], list[str]]:
    now_iso = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    kv: dict[str, str] = {}
    session_ids: list[str] = []
    for fname, raw in (docs_dict or {}).items():
        kv[f"doc:{fname}"] = raw.decode("utf-8", errors="ignore") if isinstance(raw, (bytes, bytearray)) else str(raw)
    for sfname, raw in (sessions_dict or {}).items():
        acc_id = sfname[:-5] if sfname.endswith(".json") else sfname
        session_ids.append(acc_id)
        kv[f"session:{acc_id}"] = raw.decode("utf-8", errors="ignore") if isinstance(raw, (bytes, bytearray)) else str(raw)
    kv["meta:manifest"] = json.dumps(
        {
            "format": "fb_operator_cloud_v1",
            "updated_at": now_iso,
            "updated_ts": time.time(),
            "session_ids": sorted(session_ids),
            "docs_count": len(docs_dict or {}),
            "sessions_count": len(session_ids),
        },
        ensure_ascii=False,
    )
    return kv, sorted(session_ids)


def _split_kv_rows(kv: dict[str, str]) -> tuple[dict[str, bytes], dict[str, bytes]]:
    docs: dict[str, bytes] = {}
    sessions: dict[str, bytes] = {}
    allowed_sessions: set[str] | None = None
    if "meta:manifest" in kv:
        try:
            mf = json.loads(kv["meta:manifest"])
            if isinstance(mf, dict) and isinstance(mf.get("session_ids"), list):
                allowed_sessions = {str(x) for x in mf["session_ids"]}
        except Exception:
            pass

    for k, v in (kv or {}).items():
        if not isinstance(k, str) or not _ALLOWED_KEY_RE.match(k):
            continue
        raw_bytes = (v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)).encode("utf-8")
        if k.startswith("doc:"):
            docs[k[4:]] = raw_bytes
        elif k.startswith("session:"):
            acc_id = k[8:]
            if allowed_sessions is not None and acc_id not in allowed_sessions:
                continue
            sessions[f"{acc_id}.json"] = raw_bytes
    return docs, sessions


# --- Adapter 1: Turso libSQL HTTP Pipeline ---
def _turso_exec(cfg: dict, statements: list[dict], timeout: int = 25) -> dict:
    url = _normalize_turso_http_url(cfg.get("turso_url", ""))
    token = (cfg.get("turso_token") or "").strip()
    if not url or not token:
        return {"ok": False, "error": "بيانات Turso (URL أو Token) غير مكتملة."}
    endpoint = f"{url}/v2/pipeline"
    reqs = [{"type": "execute", "stmt": st} for st in statements] + [{"type": "close"}]
    try:
        resp = requests.post(
            endpoint,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"requests": reqs},
            timeout=timeout,
        )
    except Exception as e:
        return {"ok": False, "error": f"خطأ اتصال Turso: {e}"}

    if not (200 <= resp.status_code < 300):
        return {"ok": False, "error": f"رفض Turso (HTTP {resp.status_code}): {resp.text[:200]}"}
    try:
        data = resp.json()
        results = data.get("results", [])
        for r in results:
            if r.get("type") == "error":
                err = (r.get("error") or {}).get("message") or str(r)
                return {"ok": False, "error": f"خطأ SQL في Turso: {err[:200]}"}
        return {"ok": True, "results": results}
    except Exception as e:
        return {"ok": False, "error": f"استجابة Turso غير صالحة: {e}"}


def _turso_push(cfg: dict, kv: dict[str, str], active_sessions: list[str]) -> dict:
    now_f = time.time()
    stmts: list[dict] = [
        {
            "sql": (
                f"CREATE TABLE IF NOT EXISTS {_TABLE_NAME} ("
                "doc_key TEXT PRIMARY KEY, "
                "payload TEXT NOT NULL, "
                "updated_at REAL NOT NULL)"
            )
        }
    ]
    for k, v in kv.items():
        stmts.append({
            "sql": (
                f"INSERT INTO {_TABLE_NAME} (doc_key, payload, updated_at) VALUES (?, ?, ?) "
                f"ON CONFLICT(doc_key) DO UPDATE SET payload=excluded.payload, updated_at=excluded.updated_at"
            ),
            "args": [
                {"type": "text", "value": k},
                {"type": "text", "value": v},
                {"type": "float", "value": now_f},
            ],
        })
    res = _turso_exec(cfg, stmts)
    if not res.get("ok"):
        return res
    return {"ok": True, "provider": "turso", "keys": len(kv)}


def _turso_pull(cfg: dict) -> dict:
    res = _turso_exec(
        cfg,
        [
            {
                "sql": (
                    f"CREATE TABLE IF NOT EXISTS {_TABLE_NAME} ("
                    "doc_key TEXT PRIMARY KEY, "
                    "payload TEXT NOT NULL, "
                    "updated_at REAL NOT NULL)"
                )
            },
            {"sql": f"SELECT doc_key, payload FROM {_TABLE_NAME}"},
        ],
    )
    if not res.get("ok"):
        return res
    results = res.get("results", [])
    kv: dict[str, str] = {}
    if len(results) >= 2:
        rows = (((results[1].get("response") or {}).get("result") or {}).get("rows")) or []
        for row in rows:
            if len(row) >= 2:
                k = str(row[0].get("value") or "")
                v = str(row[1].get("value") or "")
                if k:
                    kv[k] = v
    return {"ok": True, "provider": "turso", "kv": kv}


# --- Adapter 2: Supabase PostgreSQL PostgREST HTTPS API ---
def _supabase_headers(cfg: dict) -> dict[str, str]:
    key = (cfg.get("supabase_key") or "").strip()
    headers = {
        "apikey": key,
        "Content-Type": "application/json",
    }
    # المفاتيح الحديثة sb_secret_ / sb_publishable_ ليست JWT لذا لا تُرسل في Authorization: Bearer
    if key and not key.startswith("sb_"):
        headers["Authorization"] = f"Bearer {key}"
    return headers


def _supabase_push(cfg: dict, kv: dict[str, str], force: bool = False) -> dict:
    url = _clean_url(cfg.get("supabase_url", ""))
    key = (cfg.get("supabase_key") or "").strip()
    if not url or not key:
        return {"ok": False, "error": "بيانات Supabase (URL أو Key) غير مكتملة."}

    endpoint = f"{url}/rest/v1/{_TABLE_NAME}?on_conflict=doc_key"
    now_f = time.time()
    cache_key = f"{url}|{key[:12]}"
    with _db_lock:
        prev_hashes = dict(_SUPABASE_ROW_HASH_CACHE.get(cache_key) or {})

    pending_rows: list[tuple[dict[str, Any], str]] = []
    manifest_item: tuple[dict[str, Any], str] | None = None
    data_changed = False
    for k, v in kv.items():
        rhash = hashlib.sha256(str(v).encode("utf-8", errors="ignore")).hexdigest()
        if k == "meta:manifest":
            manifest_item = ({"doc_key": k, "payload": v, "updated_at": now_f}, rhash)
            continue
        if not force and prev_hashes.get(k) == rhash:
            continue
        data_changed = True
        pending_rows.append(({"doc_key": k, "payload": v, "updated_at": now_f}, rhash))

    if manifest_item and (force or data_changed):
        pending_rows.append(manifest_item)

    if not pending_rows:
        return {"ok": True, "provider": "supabase", "keys": 0, "chunks": 0, "delta_skipped": True}

    headers = {
        **_supabase_headers(cfg),
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }

    uploaded_count = 0
    chunks_count = 0
    for i in range(0, len(pending_rows), _SUPABASE_CHUNK_SIZE):
        batch = pending_rows[i : i + _SUPABASE_CHUNK_SIZE]
        rows_payload = [item[0] for item in batch]
        try:
            resp = requests.post(endpoint, headers=headers, json=rows_payload, timeout=25)
        except Exception as e:
            return {"ok": False, "error": f"خطأ اتصال Supabase بالدفعة {chunks_count + 1}: {e}"}

        if 200 <= resp.status_code < 300:
            with _db_lock:
                bucket = _SUPABASE_ROW_HASH_CACHE.setdefault(cache_key, {})
                for row_obj, rhash in batch:
                    bucket[row_obj["doc_key"]] = rhash
            uploaded_count += len(batch)
            chunks_count += 1
            continue

        body_low = (resp.text or "").lower()
        if resp.status_code == 404 or "pgrst205" in body_low or "does not exist" in body_low:
            return {
                "ok": False,
                "needs_table": True,
                "error": (
                    f"الجدول {_TABLE_NAME} غير منشأ بعد في Supabase! نفّذ هذا الأمر في SQL Editor هناك:\n"
                    f"CREATE TABLE IF NOT EXISTS {_TABLE_NAME} (doc_key TEXT PRIMARY KEY, payload TEXT NOT NULL, updated_at DOUBLE PRECISION NOT NULL);"
                ),
            }
        return {"ok": False, "error": f"رفض Supabase (HTTP {resp.status_code}): {resp.text[:200]}"}

    return {"ok": True, "provider": "supabase", "keys": uploaded_count, "chunks": chunks_count, "total_keys": len(kv)}


def _supabase_pull(cfg: dict) -> dict:
    url = _clean_url(cfg.get("supabase_url", ""))
    key = (cfg.get("supabase_key") or "").strip()
    if not url or not key:
        return {"ok": False, "error": "بيانات Supabase (URL أو Key) غير مكتملة."}

    base_endpoint = f"{url}/rest/v1/{_TABLE_NAME}?select=doc_key,payload&order=doc_key.asc"
    kv: dict[str, str] = {}
    offset = 0
    page_size = _SUPABASE_PULL_PAGE_SIZE

    while offset < 250_000:
        hdrs = {
            **_supabase_headers(cfg),
            "Range-Unit": "items",
            "Range": f"{offset}-{offset + page_size - 1}",
        }
        try:
            resp = requests.get(base_endpoint, headers=hdrs, timeout=25)
        except Exception as e:
            return {"ok": False, "error": f"خطأ اتصال Supabase: {e}"}

        if not (200 <= resp.status_code < 300):
            body_low = (resp.text or "").lower()
            if resp.status_code == 416:
                break
            if resp.status_code == 404 or "pgrst205" in body_low or "does not exist" in body_low:
                return {
                    "ok": False,
                    "needs_table": True,
                    "error": f"الجدول {_TABLE_NAME} غير منشأ بعد في Supabase SQL Editor.",
                }
            return {"ok": False, "error": f"فشل قراءة Supabase (HTTP {resp.status_code}): {resp.text[:200]}"}

        try:
            rows = resp.json()
        except Exception as e:
            return {"ok": False, "error": f"استجابة Supabase غير صالحة: {e}"}

        if not isinstance(rows, list) or not rows:
            break
        for r in rows:
            if isinstance(r, dict) and r.get("doc_key"):
                kv[str(r["doc_key"])] = str(r.get("payload") or "")
        if len(rows) < page_size:
            break
        offset += len(rows)

    return {"ok": True, "provider": "supabase", "kv": kv}


# --- Adapter 3: Firebase Realtime Database Spark Free REST API ---
def _firebase_endpoint(cfg: dict) -> str:
    url = _clean_url(cfg.get("firebase_url", ""))
    auth = (cfg.get("firebase_auth") or "").strip()
    ep = f"{url}/fb_operator_kv.json"
    if auth:
        ep += f"?auth={requests.utils.quote(auth, safe='')}"
    return ep


def _firebase_push(cfg: dict, kv: dict[str, str]) -> dict:
    url = _clean_url(cfg.get("firebase_url", ""))
    if not url:
        return {"ok": False, "error": "رابط Firebase Realtime Database غير محدد."}
    # Firebase keys cannot include '.' directly inside object property names; encode '.' as '__DOT__' safely
    safe_map = {k.replace(".", "__DOT__"): v for k, v in kv.items()}
    try:
        resp = requests.put(_firebase_endpoint(cfg), json=safe_map, timeout=25)
    except Exception as e:
        return {"ok": False, "error": f"خطأ اتصال Firebase: {e}"}
    if 200 <= resp.status_code < 300:
        return {"ok": True, "provider": "firebase", "keys": len(safe_map)}
    return {"ok": False, "error": f"رفض Firebase (HTTP {resp.status_code}): {resp.text[:200]}"}


def _firebase_pull(cfg: dict) -> dict:
    url = _clean_url(cfg.get("firebase_url", ""))
    if not url:
        return {"ok": False, "error": "رابط Firebase Realtime Database غير محدد."}
    try:
        resp = requests.get(_firebase_endpoint(cfg), timeout=25)
    except Exception as e:
        return {"ok": False, "error": f"خطأ اتصال Firebase: {e}"}
    if not (200 <= resp.status_code < 300):
        return {"ok": False, "error": f"فشل قراءة Firebase (HTTP {resp.status_code}): {resp.text[:200]}"}
    try:
        data = resp.json()
        if data is None:
            return {"ok": True, "provider": "firebase", "kv": {}}
        if not isinstance(data, dict):
            return {"ok": False, "error": "تنسيق غير متوقع من Firebase RTDB."}
        kv = {str(k).replace("__DOT__", "."): str(v) for k, v in data.items() if v is not None}
        return {"ok": True, "provider": "firebase", "kv": kv}
    except Exception as e:
        return {"ok": False, "error": f"استجابة Firebase غير صالحة: {e}"}


# ==============================================================================
# 3. الواجهة الموحدة للمزامنة والاختبار والوثائق
# ==============================================================================

def test_cloud_db_connection(cfg_override: dict | None = None) -> dict:
    cfg = cfg_override if isinstance(cfg_override, dict) else load_cloud_db_config(mask_secrets=False)
    provider = (cfg.get("provider") or "").lower()
    if not provider or not cfg.get("enabled"):
        return {"ok": False, "error": "لم يتم إعداد أي مزود قاعدة بيانات سحابية بعد."}
    if provider == "turso":
        res = _turso_pull(cfg)
    elif provider == "supabase":
        res = _supabase_pull(cfg)
    elif provider == "firebase":
        res = _firebase_pull(cfg)
    else:
        return {"ok": False, "error": f"مزود غير مدعوم: {provider}"}
    if not res.get("ok"):
        return res
    kv = res.get("kv", {})
    docs, sessions = _split_kv_rows(kv)
    return {
        "ok": True,
        "provider": provider,
        "keys_count": len(kv),
        "docs_count": len(docs),
        "sessions_count": len(sessions),
    }


def push_cloud_db_state(docs_dict: dict[str, bytes], sessions_dict: dict[str, bytes], force: bool = False) -> dict:
    """مزامنة فورية إلى SQLite WAL المحلي + القاعدة السحابية الخارجية (بنظام التغييرات الجزئية والدفعات لـ 2,000+ حساب)"""
    local_res = write_local_sqlite_mirror(docs_dict, sessions_dict)
    cfg = load_cloud_db_config(mask_secrets=False)
    if not cfg.get("enabled"):
        with _db_lock:
            _sync_state["last_status"] = "مرآة SQLite WAL محلية محدثة | القاعدة السحابية الخارجية غير مربوطة"
        return {"ok": True, "local_sqlite": local_res, "cloud_skipped": True}

    provider = cfg["provider"]
    kv, session_ids = _build_kv_rows(docs_dict, sessions_dict)
    if provider == "turso":
        res = _turso_push(cfg, kv, session_ids)
    elif provider == "supabase":
        res = _supabase_push(cfg, kv, force=force)
    elif provider == "firebase":
        res = _firebase_push(cfg, kv)
    else:
        res = {"ok": False, "error": f"مزود غير مدعوم: {provider}"}

    now_iso = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with _db_lock:
        if res.get("ok"):
            _sync_state["last_push_ts"] = time.time()
            _sync_state["last_push_iso"] = now_iso
            _sync_state["last_error"] = ""
            _sync_state["last_status"] = f"مُزامن مع {provider.upper()} + SQLite ✅ ({now_iso})"
        else:
            _sync_state["last_error"] = str(res.get("error") or "")[:240]
            _sync_state["last_status"] = f"فشل مزامنة {provider.upper()}: {_sync_state['last_error'][:90]}"

    return {**res, "local_sqlite": local_res}


def pull_cloud_db_state() -> dict:
    """استرجاع البيانات من القاعدة السحابية الخارجية (أو مرآة SQLite عند الحاجة)"""
    cfg = load_cloud_db_config(mask_secrets=False)
    if not cfg.get("enabled"):
        return {"ok": False, "skipped": True, "reason": "no_cloud_db_config", "docs": {}, "sessions": {}}

    provider = cfg["provider"]
    if provider == "turso":
        res = _turso_pull(cfg)
    elif provider == "supabase":
        res = _supabase_pull(cfg)
    elif provider == "firebase":
        res = _firebase_pull(cfg)
    else:
        return {"ok": False, "error": f"مزود غير مدعوم: {provider}", "docs": {}, "sessions": {}}

    if not res.get("ok"):
        with _db_lock:
            _sync_state["last_error"] = str(res.get("error") or "")[:240]
        return {**res, "docs": {}, "sessions": {}}

    docs, sessions = _split_kv_rows(res.get("kv", {}))
    now_iso = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with _db_lock:
        _sync_state["last_pull_ts"] = time.time()
        _sync_state["last_pull_iso"] = now_iso
        _sync_state["last_error"] = ""
        _sync_state["last_status"] = f"متصل بـ {provider.upper()} ✅ ({len(docs)} ملف / {len(sessions)} جلسة)"
    return {
        "ok": True,
        "provider": provider,
        "docs": docs,
        "sessions": sessions,
    }


def get_cloud_db_status_summary() -> dict:
    cfg = load_cloud_db_config(mask_secrets=True)
    _, sql_path = _active_db_paths()
    with _db_lock:
        state_copy = dict(_sync_state)
    return {
        "enabled": bool(cfg.get("enabled")),
        "provider": cfg.get("provider") or "none",
        "sqlite_mirror_exists": sql_path.exists(),
        "sqlite_mirror_path": str(sql_path),
        "config_masked": cfg,
        **state_copy,
    }


def get_provider_setup_guide(provider: str) -> str:
    p = (provider or "").lower()
    if p == "turso":
        return (
            "🟢 <b>إعداد Turso المجاني (بلا فيزا — أسهل خيار ومجاني 9GB):</b>\n"
            "1️⃣ سجّل مجاناً بحساب GitHub في: <code>https://turso.tech</code>\n"
            "2️⃣ أنشئ Database جديد → اضغط <b>Connect / Generate Token</b>.\n"
            "3️⃣ انسخ الرابط والـ Token وأرسلهما هنا في رسالة واحدة بهيئة سطرين:\n"
            "<code>libsql://your-db-name.turso.io\neyJhbGciOi...الـToken</code>\n"
            "<i>💡 لا يحتاج إنشاء أي جدول يدوياً — البوت يُنشئه تلقائياً في ثانية!</i>"
        )
    if p == "supabase":
        return (
            "🟣 <b>إعداد Supabase المجاني (بلا فيزا — 500MB PostgreSQL):</b>\n"
            "1️⃣ سجّل مجاناً بحساب GitHub في: <code>https://supabase.com</code> وأنشئ مشروعاً.\n"
            "2️⃣ من قائمة <b>SQL Editor</b> شغّل هذا الأمر مرة واحدة فقط:\n"
            f"<code>CREATE TABLE IF NOT EXISTS {_TABLE_NAME} (doc_key TEXT PRIMARY KEY, payload TEXT NOT NULL, updated_at DOUBLE PRECISION NOT NULL);</code>\n"
            "3️⃣ من <b>Project Settings → API</b> انسخ <b>Project URL</b> و<b>service_role secret</b> (أو anon key مع RLS) وأرسلهما بسطرين:\n"
            "<code>https://xxxxx.supabase.co\neyJhbGciOi...المفتاح</code>"
        )
    if p == "firebase":
        return (
            "🟡 <b>إعداد Firebase Realtime DB المجاني (بلا فيزا — خطة Spark):</b>\n"
            "1️⃣ ادخل <code>https://console.firebase.google.com</code> → أنشئ مشروعاً → <b>Build → Realtime Database</b> (خطة Spark).\n"
            "2️⃣ من <b>Project Settings → Service Accounts → Database secrets</b> انسخ الـ Secret (أو ضبط Rules للقراءة والكتابة).\n"
            "3️⃣ أرسل رابط القاعدة (والـ Secret إن وُجد في سطر ثانٍ):\n"
            "<code>https://your-project-default-rtdb.firebaseio.com\nSECRET_OPTIONAL</code>"
        )
    return "اختر أحد المزودات المجانية بدون فيزا: Turso أو Supabase أو Firebase."
