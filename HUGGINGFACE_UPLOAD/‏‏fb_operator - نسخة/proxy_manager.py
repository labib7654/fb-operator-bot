# -*- coding: utf-8 -*-
"""
محرك البروكسيات السحابي ونفق الفورجي (Proxy Mesh & Zero-VPS 4G Mobile Bridge)
------------------------------------------------------------------------------
يدمج محركين قويين مفتوحي المصدر:
1) pproxy (qwj/python-proxy): جسر غير متزامن مدمج يحوّل بروكسيات SOCKS5/SS/SSH
   المحمية بكلمة مرور إلى بوابة HTTP محلية صالحة لمتصفح Chromium/Playwright.
2) go-gost/gost v3 + cloudflared: نفق WebSocket عكسي مشفّر TLS (WSS) يربط
   هاتف الأندرويد (بيانات 4G/5G عبر Termux) أو جهاز المنزل مباشرةً بالبوت
   السحابي (GitHub Actions / Cloud) بدون الحاجة لأي VPS مدفوع.
"""
from __future__ import annotations

import asyncio
import json
import os
import platform
import re
import secrets
import shutil
import socket
import subprocess
import tarfile
import threading
import time
import urllib.parse
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

import fb_operator.config as config

GOST_VERSION = "3.3.3"

_proxy_lock = threading.RLock()
_bridge_lock = threading.Lock()
_4g_lock = threading.Lock()
_proxy_exec_locks_guard = threading.Lock()
_proxy_exec_locks: dict[str, threading.RLock] = {}
_proxy_last_used: dict[str, float] = {}

# جسر pproxy المشترك داخل العملية: uri_canonical -> {"port": int, "server": Any, "started_at": float}
_pproxy_loop: asyncio.AbstractEventLoop | None = None
_pproxy_thread: threading.Thread | None = None
_pproxy_bridges: dict[str, dict[str, Any]] = {}

# عملية نفق الفورجي العكسي (gost server + cloudflared tunnel)
_4g_runtime: dict[str, Any] = {
    "running": False,
    "ws_port": 0,
    "exit_port": 0,
    "tunnel_url": "",
    "tunnel_host": "",
    "username": "",
    "password": "",
    "gost_proc": None,
    "cf_proc": None,
    "error": "",
    "started_at": "",
}

_VALID_SCHEMES = {"http", "https", "socks4", "socks5", "ss", "ssh"}
_PROXY_CHECK_URLS = (
    "http://ip-api.com/json/?fields=status,country,countryCode,timezone,query,isp",
    "https://ipinfo.io/json",
)
_ARAB_COUNTRIES = {
    "EG", "SA", "YE", "AE", "KW", "QA", "BH", "OM", "JO", "LB",
    "SY", "IQ", "PS", "SD", "LY", "TN", "DZ", "MA", "MR", "SO", "DJ", "KM",
}
_COUNTRY_LOCALES = {
    "EG": "ar-EG",
    "SA": "ar-SA",
    "YE": "ar-YE",
    "AE": "ar-AE",
    "KW": "ar-KW",
    "QA": "ar-QA",
    "BH": "ar-BH",
    "OM": "ar-OM",
    "JO": "ar-JO",
    "LB": "ar-LB",
    "IQ": "ar-IQ",
    "MA": "ar-MA",
    "DZ": "ar-DZ",
    "TN": "ar-TN",
    "US": "en-US",
    "GB": "en-GB",
    "CA": "en-CA",
    "AU": "en-AU",
    "DE": "de-DE",
    "FR": "fr-FR",
    "TR": "tr-TR",
}


def _proxies_file_path() -> Path:
    return Path(getattr(config, "PROXIES_FILE", Path(config.DATA_DIR) / "proxies.json"))


_proxy_alert_callbacks: list[Any] = []
_watchdog_run_lock = threading.Lock()


def register_proxy_alert_callback(cb) -> None:
    if cb and cb not in _proxy_alert_callbacks:
        _proxy_alert_callbacks.append(cb)


def _emit_proxy_alert(payload: dict[str, Any]) -> None:
    for cb in list(_proxy_alert_callbacks):
        try:
            cb(payload)
        except Exception:
            pass


def _notify_change(reason: str = "proxies") -> None:
    try:
        from fb_operator.state_events import publish_event
        publish_event("proxies", 0, reason)
    except Exception:
        pass
    try:
        from fb_operator import persistence_manager
        persistence_manager.notify_data_changed(reason)
    except Exception:
        pass


def _default_state() -> dict[str, Any]:
    return {
        "mode": "sticky",  # sticky | 4g_bridge | direct
        "max_per_proxy": 3,  # الحد الآمن الموصى به للحسابات لكل بروكسي (3=آمن، 5=حد أقصى، 0=غير محدود)
        "auto_check_enabled": True,
        "auto_check_interval_sec": 120,
        "last_auto_check_ts": 0.0,
        "proxies": [],
        "bindings": {},    # account_id -> canonical_uri
        "bridge_4g": {
            "username": f"g4_{secrets.token_hex(3)}",
            "password": secrets.token_urlsafe(12),
            "exit_port": 18080,
            "country_code": "",
            "timezone": "",
            "exit_ip": "",
        },
    }


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(f".json.tmp.{threading.get_ident()}")
    raw = json.dumps(payload, ensure_ascii=False, indent=2)
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(raw)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def load_proxy_state() -> dict[str, Any]:
    with _proxy_lock:
        path = _proxies_file_path()
        base = _default_state()
        if not path.exists():
            return base
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return base
        if not isinstance(data, dict):
            return base
        mode = str(data.get("mode") or "sticky").strip().lower()
        if mode not in ("sticky", "4g_bridge", "direct"):
            mode = "sticky"
        try:
            raw_max = data.get("max_per_proxy", 3)
            max_per_proxy = int(raw_max) if raw_max is not None else 3
            if max_per_proxy < 0:
                max_per_proxy = 3
        except Exception:
            max_per_proxy = 3
        proxies: list[dict[str, Any]] = []
        for idx_p, raw_p in enumerate(data.get("proxies") or []):
            if isinstance(raw_p, dict) and raw_p.get("uri"):
                p_obj = dict(raw_p)
                if not p_obj.get("id"):
                    p_obj["id"] = f"prx_{idx_p + 1}_{secrets.token_hex(2)}"
                p_obj.setdefault("uses_count", 0)
                p_obj.setdefault("success_count", 0)
                p_obj.setdefault("fail_count", 0)
                p_obj.setdefault("total_fail_count", 0)
                p_obj.setdefault("last_used_at", "")
                p_obj.setdefault("last_error", "")
                proxies.append(p_obj)
        bindings = {
            str(k): str(v)
            for k, v in (data.get("bindings") or {}).items()
            if k and v
        }
        b4g = dict(base["bridge_4g"])
        if isinstance(data.get("bridge_4g"), dict):
            b4g.update({k: v for k, v in data["bridge_4g"].items() if v not in (None, "")})
        try:
            interval_s = max(30, min(3600, int(data.get("auto_check_interval_sec", 120) or 120)))
        except Exception:
            interval_s = 120
        try:
            last_auto_ts = float(data.get("last_auto_check_ts", 0.0) or 0.0)
        except Exception:
            last_auto_ts = 0.0
        return {
            "mode": mode,
            "max_per_proxy": max_per_proxy,
            "auto_check_enabled": bool(data.get("auto_check_enabled", True)),
            "auto_check_interval_sec": interval_s,
            "last_auto_check_ts": last_auto_ts,
            "proxies": proxies,
            "bindings": bindings,
            "bridge_4g": b4g,
        }


def save_proxy_state(state: dict[str, Any], notify: bool = True) -> None:
    with _proxy_lock:
        path = _proxies_file_path()
        _atomic_write_json(path, state)
    if notify:
        _notify_change("proxies")


def parse_proxy_parts(raw: str) -> dict[str, Any] | None:
    """
    تحليل وتوحيد صيغ البروكسي الشائعة إلى مكونات قياسية:
    - http://user:pass@host:port / socks5://user:pass@host:port / socks4://... / ss://...
    - host:port
    - host:port:user:pass
    - user:pass@host:port
    """
    text = str(raw or "").strip()
    if not text or text.startswith("#"):
        return None
    # إزالة مسافات زائدة أو أرقام ترقيم مثل "1. socks5://..."
    text = re.sub(r"^\d+[\)\.\-]\s+", "", text).strip()
    if not text or " " in text and "://" not in text:
        text = text.split()[0].strip()

    scheme = "http"
    body = text
    if "://" in text:
        sc, body = text.split("://", 1)
        scheme = sc.strip().lower()
        if scheme == "socks":
            scheme = "socks5"
        elif scheme == "socks5h":
            scheme = "socks5"
        elif scheme == "http+socks5":
            scheme = "http"
        if scheme not in _VALID_SCHEMES:
            return None
    else:
        # دعم host:port:user:pass عندما يكون الجزء الثاني رقماً لمنفذ صالح
        colon_parts = body.split(":")
        if len(colon_parts) == 4 and "@" not in body and colon_parts[1].isdigit():
            h_p, port_s, u_p, pw_p = colon_parts
            port_n = int(port_s)
            if 1 <= port_n <= 65535 and h_p.strip():
                body = f"{u_p}:{pw_p}@{h_p.strip()}:{port_n}"

    parsed = urllib.parse.urlsplit(f"{scheme}://{body.lstrip('/')}")
    host = (parsed.hostname or "").strip()
    try:
        port = parsed.port
    except ValueError:
        return None
    if not host or not port or not (1 <= int(port) <= 65535):
        return None

    username = urllib.parse.unquote(parsed.username) if parsed.username is not None else ""
    password = urllib.parse.unquote(parsed.password) if parsed.password is not None else ""

    host_fmt = f"[{host}]" if ":" in host and not host.startswith("[") else host
    if username or password:
        u_enc = urllib.parse.quote(username, safe="")
        p_enc = urllib.parse.quote(password, safe="")
        canonical = f"{scheme}://{u_enc}:{p_enc}@{host_fmt}:{port}"
    else:
        canonical = f"{scheme}://{host_fmt}:{port}"

    return {
        "scheme": scheme,
        "host": host,
        "port": int(port),
        "username": username,
        "password": password,
        "uri": canonical,
    }


def normalize_proxy_uri(raw: str) -> str:
    parts = parse_proxy_parts(raw)
    return parts["uri"] if parts else ""


def mask_proxy_uri(raw: str) -> str:
    """إخفاء كلمة المرور واسم المستخدم الحساسين عند عرض البروكسي في الواجهة."""
    parts = parse_proxy_parts(raw)
    if not parts:
        return "***"
    scheme = parts["scheme"]
    host = parts["host"]
    port = parts["port"]
    host_fmt = f"[{host}]" if ":" in host else host
    if parts["username"] or parts["password"]:
        u = parts["username"]
        u_mask = f"{u[:2]}***" if len(u) > 2 else "***"
        return f"{scheme}://{u_mask}:***@{host_fmt}:{port}"
    return f"{scheme}://{host_fmt}:{port}"


def add_proxies_bulk(raw_lines: str | list[str]) -> dict[str, Any]:
    if isinstance(raw_lines, str):
        lines = [ln.strip() for ln in re.split(r"[\r\n,;]+", raw_lines) if ln.strip()]
    else:
        lines = [str(ln).strip() for ln in raw_lines if str(ln).strip()]

    added = 0
    duplicates = 0
    invalid = 0
    now_iso = datetime.now().isoformat(timespec="seconds")

    with _proxy_lock:
        state = load_proxy_state()
        existing = {str(p.get("uri")): p for p in state["proxies"]}
        for line in lines:
            parts = parse_proxy_parts(line)
            if not parts:
                invalid += 1
                continue
            uri = parts["uri"]
            if uri in existing:
                duplicates += 1
                continue
            item = {
                "id": f"prx_{secrets.token_hex(4)}",
                "uri": uri,
                "scheme": parts["scheme"],
                "host": parts["host"],
                "port": parts["port"],
                "alive": None,
                "latency_ms": None,
                "exit_ip": "",
                "country_code": "",
                "country_name": "",
                "timezone": "",
                "added_at": now_iso,
                "last_checked": "",
                "fail_count": 0,
                "total_fail_count": 0,
                "uses_count": 0,
                "success_count": 0,
                "last_used_at": "",
                "last_error": "",
            }
            state["proxies"].append(item)
            existing[uri] = item
            added += 1
        if added > 0:
            save_proxy_state(state, notify=True)

    return {
        "added": added,
        "duplicates": duplicates,
        "invalid": invalid,
        "total": len(load_proxy_state()["proxies"]),
    }


def seed_env_proxies() -> dict[str, int]:
    """استيراد FB_PROXY / FB_PROXY_POOL من البيئة إلى المخزن تلقائياً دون تكرار."""
    candidates: list[str] = []
    single = (os.environ.get("FB_PROXY") or "").strip()
    if single:
        candidates.append(single)
    pool_raw = (os.environ.get("FB_PROXY_POOL") or "").strip()
    if pool_raw:
        for item in re.split(r"[\r\n,;]+", pool_raw):
            if item.strip():
                candidates.append(item.strip())
    if not candidates:
        return {"added": 0}
    res = add_proxies_bulk(candidates)
    return {"added": int(res.get("added", 0))}


def set_proxy_mode(mode: str) -> str:
    clean = str(mode or "").strip().lower()
    if clean not in ("sticky", "4g_bridge", "direct"):
        clean = "sticky"
    with _proxy_lock:
        state = load_proxy_state()
        state["mode"] = clean
        save_proxy_state(state, notify=True)
    return clean


def set_max_per_proxy(limit: int) -> int:
    """تعيين الحد الآمن المستهدف لعدد الحسابات على كل بروكسي (3=آمن، 5=أقصى حد مستحسن، 0=مفتوح)."""
    try:
        val = int(limit)
    except Exception:
        val = 3
    if val < 0:
        val = 3
    with _proxy_lock:
        state = load_proxy_state()
        state["max_per_proxy"] = val
        save_proxy_state(state, notify=True)
    return val


def proxy_lock_key(proxy_uri: str | None) -> str:
    """استخراج مفتاح قفل موحد حسب الـ IP والمنفذ لمنع تشغيل حسابين على نفس البروكسي بالثانية نفسها."""
    raw = str(proxy_uri or "").strip()
    if not raw:
        return "direct"
    parts = parse_proxy_parts(raw)
    if parts and parts.get("host") and parts.get("port"):
        return f"proxy:{parts['host'].lower()}:{parts['port']}"
    return f"proxy:{raw.lower()}"


def get_proxy_lock(proxy_uri: str | None) -> threading.RLock:
    """قفل تسلسلي لكل IP بروكسي بحيث تعمل البروكسيات المختلفة بالتوازي وتتناوب الحسابات التي تشترك بنفس الـ IP."""
    key = proxy_lock_key(proxy_uri)
    with _proxy_exec_locks_guard:
        if key not in _proxy_exec_locks:
            _proxy_exec_locks[key] = threading.RLock()
        return _proxy_exec_locks[key]


@contextmanager
def proxy_execution_guard(proxy_uri: str | None, min_gap_sec: float = 1.5):
    """
    حارس منع التزامن على نفس الـ IP:
    يضمن عدم إرسال أي مهمتين في نفس الثانية من نفس البروكسي مع فاصل تهدئة إنساني بسيط.
    يجب أن يُستدعى بترتيب ثابت: profile_lock -> proxy_execution_guard -> _browser_semaphore.
    """
    key = proxy_lock_key(proxy_uri)
    plock = get_proxy_lock(key)
    plock.acquire()
    try:
        gap = max(0.0, float(min_gap_sec or 0.0))
        if gap > 0.0:
            with _proxy_exec_locks_guard:
                last_ts = _proxy_last_used.get(key, 0.0)
            elapsed = time.monotonic() - last_ts if last_ts > 0.0 else gap
            wait_s = gap - elapsed
            if wait_s > 0.0:
                time.sleep(min(wait_s, gap))
        yield key
    finally:
        with _proxy_exec_locks_guard:
            _proxy_last_used[key] = time.monotonic()
        plock.release()


def remove_proxy(uri_or_index: str | int) -> bool:
    with _proxy_lock:
        state = load_proxy_state()
        proxies = state["proxies"]
        removed_uri = ""
        if isinstance(uri_or_index, int):
            if 0 <= uri_or_index < len(proxies):
                removed_uri = proxies.pop(uri_or_index)["uri"]
        else:
            target = normalize_proxy_uri(str(uri_or_index)) or str(uri_or_index).strip()
            for idx, p in enumerate(proxies):
                if p.get("uri") == target:
                    removed_uri = proxies.pop(idx)["uri"]
                    break
        if not removed_uri:
            return False
        state["bindings"] = {k: v for k, v in state["bindings"].items() if v != removed_uri}
        save_proxy_state(state, notify=True)
        return True


def clear_dead_proxies() -> int:
    with _proxy_lock:
        state = load_proxy_state()
        before = len(state["proxies"])
        alive_list = [p for p in state["proxies"] if p.get("alive") is not False]
        removed = before - len(alive_list)
        if removed > 0:
            alive_uris = {p["uri"] for p in alive_list}
            state["proxies"] = alive_list
            state["bindings"] = {k: v for k, v in state["bindings"].items() if v in alive_uris}
            save_proxy_state(state, notify=True)
        return removed


def clear_all_proxies() -> int:
    with _proxy_lock:
        state = load_proxy_state()
        cnt = len(state["proxies"])
        if cnt or state["bindings"]:
            state["proxies"] = []
            state["bindings"] = {}
            save_proxy_state(state, notify=True)
        return cnt


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _ensure_pproxy_loop() -> asyncio.AbstractEventLoop:
    global _pproxy_loop, _pproxy_thread
    with _bridge_lock:
        if _pproxy_loop is not None and _pproxy_thread is not None and _pproxy_thread.is_alive():
            return _pproxy_loop
        ready_ev = threading.Event()

        def _runner() -> None:
            global _pproxy_loop
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            _pproxy_loop = loop
            ready_ev.set()
            loop.run_forever()

        _pproxy_thread = threading.Thread(target=_runner, daemon=True, name="pproxy-bridge-loop")
        _pproxy_thread.start()
        ready_ev.wait(timeout=5.0)
        assert _pproxy_loop is not None
        return _pproxy_loop


def _format_pproxy_upstream(parts: dict[str, Any]) -> str:
    scheme = parts["scheme"]
    host = parts["host"]
    port = parts["port"]
    host_fmt = f"[{host}]" if ":" in host else host
    base = f"{scheme}://{host_fmt}:{port}"
    if parts["username"] or parts["password"]:
        return f"{base}#{parts['username']}:{parts['password']}"
    return base


def get_pproxy_local_url(upstream_uri: str) -> str:
    """
    تشغيل أو استرجاع بوابة HTTP محلية عبر pproxy تُمرر الطلبات إلى أي بروكسي خارجي
    (خصوصاً SOCKS5/SS/SSH بكلمة مرور التي لا يدعمها Chromium مباشرة).
    """
    parts = parse_proxy_parts(upstream_uri)
    if not parts:
        raise ValueError("صيغة البروكسي غير صالحة لـ pproxy.")
    canonical = parts["uri"]

    with _bridge_lock:
        cached = _pproxy_bridges.get(canonical)
        if cached and cached.get("port"):
            return f"http://127.0.0.1:{cached['port']}"

    import pproxy

    loop = _ensure_pproxy_loop()
    upstream_conn = pproxy.Connection(_format_pproxy_upstream(parts))
    base_args = {
        "block": None,
        "salgorithm": "fa",
        "httpget": {},
        "authtime": 2592000,
        "verbose": lambda _msg: None,
    }

    last_err: Exception | None = None
    for _ in range(3):
        local_port = _find_free_port()

        async def _start() -> Any:
            srv = pproxy.Server(f"http://127.0.0.1:{local_port}")
            return await srv.start_server({**base_args, "rserver": [upstream_conn]})

        try:
            fut = asyncio.run_coroutine_threadsafe(_start(), loop)
            asyncio_srv = fut.result(timeout=6.0)
            with _bridge_lock:
                _pproxy_bridges[canonical] = {
                    "port": local_port,
                    "server": asyncio_srv,
                    "started_at": time.time(),
                }
            return f"http://127.0.0.1:{local_port}"
        except Exception as e:
            last_err = e
            continue
    raise RuntimeError(f"تعذر تشغيل جسر pproxy المحلي: {last_err}")


def build_playwright_proxy_config(proxy_uri: str) -> dict[str, str] | None:
    """
    تحويل أي بروكسي إلى قاموس Playwright الرسمي الآمن:
    - http/https/socks بدون كلمة مرور -> {"server": "scheme://host:port"}
    - http/https بكلمة مرور -> {"server": "scheme://host:port", "username": u, "password": p}
    - socks5/socks4/ss/ssh بكلمة مرور -> جسر pproxy محلي http://127.0.0.1:<port>
    """
    parts = parse_proxy_parts(proxy_uri)
    if not parts:
        return None

    scheme = parts["scheme"]
    host = parts["host"]
    port = parts["port"]
    user = parts["username"]
    pw = parts["password"]
    host_fmt = f"[{host}]" if ":" in host else host

    if not user and not pw:
        if scheme in ("http", "https", "socks4", "socks5"):
            return {"server": f"{scheme}://{host_fmt}:{port}"}
        local_http = get_pproxy_local_url(parts["uri"])
        return {"server": local_http}

    if scheme in ("http", "https"):
        return {
            "server": f"{scheme}://{host_fmt}:{port}",
            "username": user,
            "password": pw,
        }

    # Chromium لا يدعم user:pass مع socks5 مباشرة، لذا نمرره عبر جسر pproxy المحلي
    local_http = get_pproxy_local_url(parts["uri"])
    return {"server": local_http}


def _tcp_is_open(host: str, port: int, timeout: float = 0.6) -> bool:
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True
    except Exception:
        return False


def _probe_geo_over_http_proxy(http_proxy_url: str, timeout: float = 8.0) -> dict[str, str]:
    proxies = {"http": http_proxy_url, "https": http_proxy_url}
    for check_url in _PROXY_CHECK_URLS:
        try:
            r = requests.get(check_url, proxies=proxies, timeout=timeout)
            if r.status_code != 200:
                continue
            j = r.json()
            if not isinstance(j, dict):
                continue
            if "ip-api.com" in check_url and j.get("status") not in (None, "success"):
                continue
            cc = str(j.get("countryCode") or j.get("country") or "").upper()[:2]
            return {
                "exit_ip": str(j.get("query") or j.get("ip") or "").strip(),
                "country_code": cc,
                "country_name": str(j.get("country") or cc or "").strip(),
                "timezone": str(j.get("timezone") or "").strip(),
            }
        except Exception:
            continue
    return {}


def check_proxy_health(proxy_uri: str, timeout: float = 8.0) -> dict[str, Any]:
    parts = parse_proxy_parts(proxy_uri)
    if not parts:
        return {"uri": proxy_uri, "alive": False, "error": "صيغة غير صالحة"}

    t0 = time.monotonic()
    local_bridge_url = ""
    try:
        scheme = parts["scheme"]
        # تحويل جميع البروكسيات غير HTTP (مثل socks5/socks4/ss/ssh) عبر جسر pproxy المحلي
        # لتفادي الحاجة لمكتبات إضافية مثل PySocks وفحصها مباشرةً عبر requests و Chromium.
        if scheme != "http":
            local_bridge_url = get_pproxy_local_url(parts["uri"])
            proxy_for_req = local_bridge_url
        else:
            proxy_for_req = parts["uri"]

        geo = _probe_geo_over_http_proxy(proxy_for_req, timeout=timeout)
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        alive = bool(geo.get("exit_ip"))
        if not alive:
            # محاولة فحص TCP فقط إن حُجبت مواقع الفحص لكن المنفذ حي
            alive_tcp = _tcp_is_open(parts["host"], parts["port"], timeout=min(3.0, timeout))
            return {
                "uri": parts["uri"],
                "alive": False if not alive_tcp else True,
                "latency_ms": elapsed_ms,
                "exit_ip": "",
                "country_code": "",
                "country_name": "",
                "timezone": "",
                "error": "" if alive_tcp else "تعذر الوصول للبروكسي",
            }
        return {
            "uri": parts["uri"],
            "alive": True,
            "latency_ms": elapsed_ms,
            **geo,
            "error": "",
        }
    except Exception as e:
        return {
            "uri": parts["uri"],
            "alive": False,
            "latency_ms": int((time.monotonic() - t0) * 1000),
            "error": str(e)[:120],
        }


def check_all_proxies(max_workers: int = 12, timeout: float = 8.0) -> dict[str, Any]:
    state = load_proxy_state()
    items = list(state["proxies"])
    if not items:
        return {"checked": 0, "alive": 0, "dead": 0}

    results_by_uri: dict[str, dict[str, Any]] = {}
    workers = max(1, min(max_workers, len(items)))
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(check_proxy_health, p["uri"], timeout): p["uri"] for p in items}
        for fut in as_completed(futs):
            u = futs[fut]
            try:
                results_by_uri[u] = fut.result()
            except Exception as e:
                results_by_uri[u] = {"uri": u, "alive": False, "error": str(e)}

    now_iso = datetime.now().isoformat(timespec="seconds")
    alive_cnt = 0
    dead_cnt = 0
    newly_dead: list[dict[str, Any]] = []
    recovered: list[dict[str, Any]] = []
    with _proxy_lock:
        fresh = load_proxy_state()
        fresh["last_auto_check_ts"] = time.time()
        bindings = fresh.get("bindings") or {}
        for p in fresh["proxies"]:
            res = results_by_uri.get(p["uri"])
            if not res:
                continue
            was_alive = p.get("alive")
            is_ok = bool(res.get("alive"))
            p["alive"] = is_ok
            p["latency_ms"] = res.get("latency_ms")
            p["last_checked"] = now_iso
            bound_ids = [aid for aid, u in bindings.items() if u == p["uri"]]
            if is_ok:
                alive_cnt += 1
                p["fail_count"] = 0
                p["last_error"] = ""
                for gk in ("exit_ip", "country_code", "country_name", "timezone"):
                    if res.get(gk):
                        p[gk] = res[gk]
                if was_alive is False:
                    recovered.append({
                        "id": p.get("id", ""),
                        "masked_uri": mask_proxy_uri(p["uri"]),
                        "host": p.get("host", ""),
                        "port": p.get("port", ""),
                        "country_code": p.get("country_code", ""),
                        "bound_account_ids": bound_ids,
                    })
            else:
                dead_cnt += 1
                p["fail_count"] = int(p.get("fail_count") or 0) + 1
                p["total_fail_count"] = int(p.get("total_fail_count") or 0) + 1
                p["last_error"] = str(res.get("error") or "فشل الاتصال بالبروكسي")[:160]
                if was_alive is not False:
                    newly_dead.append({
                        "id": p.get("id", ""),
                        "uri": p["uri"],
                        "masked_uri": mask_proxy_uri(p["uri"]),
                        "host": p.get("host", ""),
                        "port": p.get("port", ""),
                        "error": p["last_error"],
                        "bound_account_ids": bound_ids,
                    })
        save_proxy_state(fresh, notify=True)

    return {
        "checked": len(items),
        "alive": alive_cnt,
        "dead": dead_cnt,
        "newly_dead": newly_dead,
        "recovered": recovered,
    }


GITHUB_FREE_PROXY_SOURCES: tuple[tuple[str, str], ...] = (
    ("socks5", "https://cdn.jsdelivr.net/gh/proxifly/free-proxy-list@main/proxies/protocols/socks5/data.txt"),
    ("http", "https://cdn.jsdelivr.net/gh/proxifly/free-proxy-list@main/proxies/protocols/http/data.txt"),
    ("socks5", "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks5.txt"),
    ("socks5", "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/socks5.txt"),
)


def fetch_and_check_github_free_proxies(
    limit_candidates: int = 36,
    max_keep: int = 12,
    timeout: float = 4.5,
    max_workers: int = 12,
    sources: tuple[tuple[str, str], ...] | None = None,
) -> dict[str, Any]:
    """
    جلب قائمة بروكسيات مجانية مفتوحة من GitHub وفلترتها بفحص اتصال HTTPS حقيقي قبل إضافتها للتجمع.
    تنبيه: القوائم العامة مشتركة ولا تُقارن ببروكسيات 4G أو الخاصة للحسابات الحساسة.
    """
    feed_list = sources or GITHUB_FREE_PROXY_SOURCES
    candidates: list[str] = []
    seen_cand: set[str] = set()
    sources_ok = 0

    for scheme, url in feed_list:
        if len(candidates) >= limit_candidates:
            break
        try:
            resp = requests.get(url, timeout=6.0)
            if resp.status_code != 200 or not resp.text:
                continue
            sources_ok += 1
            for raw_line in resp.text.splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                if "://" not in line:
                    line = f"{scheme}://{line}"
                norm = normalize_proxy_uri(line)
                if norm and norm not in seen_cand:
                    seen_cand.add(norm)
                    candidates.append(norm)
                    if len(candidates) >= limit_candidates:
                        break
        except Exception:
            continue

    if not candidates:
        return {
            "ok": False,
            "sources_ok": sources_ok,
            "fetched": 0,
            "tested": 0,
            "alive": 0,
            "added": 0,
            "error": "تعذر سحب قوائم البروكسيات من GitHub حالياً.",
        }

    verified: list[dict[str, Any]] = []
    workers = max(1, min(max_workers, len(candidates)))
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(check_proxy_health, uri, timeout): uri for uri in candidates}
        for fut in as_completed(futs):
            try:
                res = fut.result()
                # للمجاني المشترك نُشترط عبور اتصال HTTPS فعلي وعودة exit_ip حقيقي (لا نكتفي بفحص منفذ TCP)
                if res.get("alive") and res.get("exit_ip"):
                    verified.append(res)
            except Exception:
                pass

    verified.sort(key=lambda r: int(r.get("latency_ms") or 9999))
    chosen = verified[:max(1, max_keep)] if verified else []
    added_cnt = 0
    if chosen:
        bulk_res = add_proxies_bulk("\n".join(r["uri"] for r in chosen))
        added_cnt = int(bulk_res.get("added") or 0)
        by_uri = {r["uri"]: r for r in chosen}
        now_iso = datetime.now().isoformat(timespec="seconds")
        with _proxy_lock:
            fresh = load_proxy_state()
            for p in fresh["proxies"]:
                r = by_uri.get(p.get("uri", ""))
                if r:
                    p["alive"] = True
                    p["latency_ms"] = r.get("latency_ms")
                    p["last_checked"] = now_iso
                    p["fail_count"] = 0
                    p["source_tag"] = "github_free"
                    for gk in ("exit_ip", "country_code", "country_name", "timezone"):
                        if r.get(gk):
                            p[gk] = r[gk]
            save_proxy_state(fresh, notify=True)

    return {
        "ok": True,
        "sources_ok": sources_ok,
        "fetched": len(candidates),
        "tested": len(candidates),
        "alive": len(verified),
        "added": added_cnt,
        "kept": len(chosen),
    }


def _match_proxy_entry(proxies: list[dict[str, Any]], selector: str | int) -> tuple[int, dict[str, Any] | None]:
    if isinstance(selector, int):
        if 0 <= selector < len(proxies):
            return selector, proxies[selector]
        return -1, None
    raw = str(selector or "").strip()
    if raw.isdigit():
        idx = int(raw)
        if 0 <= idx < len(proxies):
            return idx, proxies[idx]
    norm = normalize_proxy_uri(raw) or raw
    for idx, p in enumerate(proxies):
        if p.get("id") == raw or p.get("uri") == norm or p.get("uri") == raw:
            return idx, p
    return -1, None


def toggle_auto_check(enabled: bool | None = None) -> bool:
    with _proxy_lock:
        state = load_proxy_state()
        new_val = (not bool(state.get("auto_check_enabled", True))) if enabled is None else bool(enabled)
        state["auto_check_enabled"] = new_val
        save_proxy_state(state, notify=True)
        return new_val


def set_auto_check_interval(seconds: int) -> int:
    try:
        val = max(30, min(3600, int(seconds)))
    except Exception:
        val = 120
    with _proxy_lock:
        state = load_proxy_state()
        state["auto_check_interval_sec"] = val
        save_proxy_state(state, notify=True)
        return val


def record_proxy_use(proxy_uri: str, success: bool = True, error: str = "") -> None:
    target = normalize_proxy_uri(proxy_uri) or str(proxy_uri or "").strip()
    if not target:
        return
    now_iso = datetime.now().isoformat(timespec="seconds")
    with _proxy_lock:
        state = load_proxy_state()
        changed = False
        for p in state["proxies"]:
            if p.get("uri") == target:
                p["uses_count"] = int(p.get("uses_count") or 0) + 1
                p["last_used_at"] = now_iso
                if success:
                    p["success_count"] = int(p.get("success_count") or 0) + 1
                    p["fail_count"] = 0
                    p["last_error"] = ""
                    if p.get("alive") is None:
                        p["alive"] = True
                else:
                    p["fail_count"] = int(p.get("fail_count") or 0) + 1
                    p["total_fail_count"] = int(p.get("total_fail_count") or 0) + 1
                    if error:
                        p["last_error"] = str(error)[:160]
                changed = True
                break
        if changed:
            save_proxy_state(state, notify=True)


def report_proxy_network_error(proxy_uri: str, error: str = "") -> dict[str, Any]:
    """رصد تعطل فوري للـ IP أثناء التشغيل، إعلانه غير صالح، وإرسال تنبيه فوري للمسؤولين."""
    target = normalize_proxy_uri(proxy_uri) or str(proxy_uri or "").strip()
    if not target:
        return {"ok": False}
    now_iso = datetime.now().isoformat(timespec="seconds")
    err_txt = str(error or "انقطع اتصال البروكسي أثناء التشغيل").strip()[:160]
    alert_item: dict[str, Any] | None = None
    with _proxy_lock:
        state = load_proxy_state()
        bindings = state.get("bindings") or {}
        for idx, p in enumerate(state["proxies"]):
            if p.get("uri") == target:
                was_alive = p.get("alive")
                p["alive"] = False
                p["fail_count"] = int(p.get("fail_count") or 0) + 1
                p["total_fail_count"] = int(p.get("total_fail_count") or 0) + 1
                p["last_checked"] = now_iso
                p["last_error"] = err_txt
                bound_ids = [aid for aid, u in bindings.items() if u == target]
                save_proxy_state(state, notify=True)
                alert_item = {
                    "idx": idx,
                    "id": p.get("id", ""),
                    "uri": target,
                    "masked_uri": mask_proxy_uri(target),
                    "host": p.get("host", ""),
                    "port": p.get("port", ""),
                    "error": err_txt,
                    "bound_account_ids": bound_ids,
                    "was_alive": was_alive,
                }
                break
    if alert_item and alert_item.get("was_alive") is not False:
        _emit_proxy_alert({
            "kind": "proxy_down",
            "newly_dead": [alert_item],
            "recovered": [],
            "reason": "runtime_error",
        })
    return {"ok": bool(alert_item), "item": alert_item}


def check_single_proxy(selector: str | int, timeout: float = 8.0) -> dict[str, Any]:
    state = load_proxy_state()
    idx, entry = _match_proxy_entry(state["proxies"], selector)
    if not entry:
        return {"ok": False, "error": "البروكسي غير موجود."}
    res = check_proxy_health(entry["uri"], timeout=timeout)
    now_iso = datetime.now().isoformat(timespec="seconds")
    with _proxy_lock:
        fresh = load_proxy_state()
        idx2, p = _match_proxy_entry(fresh["proxies"], entry.get("id") or entry["uri"])
        if not p:
            return {"ok": False, "error": "البروكسي غير موجود."}
        was_alive = p.get("alive")
        is_ok = bool(res.get("alive"))
        p["alive"] = is_ok
        p["latency_ms"] = res.get("latency_ms")
        p["last_checked"] = now_iso
        if is_ok:
            p["fail_count"] = 0
            p["last_error"] = ""
            for gk in ("exit_ip", "country_code", "country_name", "timezone"):
                if res.get(gk):
                    p[gk] = res[gk]
        else:
            p["fail_count"] = int(p.get("fail_count") or 0) + 1
            p["total_fail_count"] = int(p.get("total_fail_count") or 0) + 1
            p["last_error"] = str(res.get("error") or "تعذر الوصول للبروكسي")[:160]
        save_proxy_state(fresh, notify=True)
    return {
        "ok": True,
        "idx": idx2 if idx2 >= 0 else idx,
        "id": p.get("id", ""),
        "masked_uri": mask_proxy_uri(p["uri"]),
        "alive": is_ok,
        "was_alive": was_alive,
        "latency_ms": p.get("latency_ms"),
        "exit_ip": p.get("exit_ip", ""),
        "country_code": p.get("country_code", ""),
        "error": p.get("last_error", ""),
    }


def rebind_proxy_accounts(selector: str | int) -> dict[str, Any]:
    """نقل الحسابات المرتبطة ببروكسي محدد (متعطل أو مزدحم) إلى بروكسيات أخرى سليمة متوازنة."""
    try:
        from fb_operator import account_manager as acc_m
    except Exception:
        acc_m = None

    moved: list[dict[str, str]] = []
    with _proxy_lock:
        state = load_proxy_state()
        idx, entry = _match_proxy_entry(state["proxies"], selector)
        if not entry:
            return {"ok": False, "error": "البروكسي غير موجود.", "moved": 0}
        target_uri = entry["uri"]
        affected_ids = [aid for aid, u in state["bindings"].items() if u == target_uri]
        if not affected_ids:
            return {"ok": True, "moved": 0, "accounts": [], "message": "لا توجد حسابات مربوطة بهذا الـ IP."}

        alt_candidates = [
            p for p in state["proxies"]
            if p.get("uri") != target_uri and p.get("alive") is not False
        ]
        if not alt_candidates:
            return {
                "ok": False,
                "error": "لا توجد بروكسيات بديلة صالحة لنقل الحسابات إليها حالياً.",
                "moved": 0,
            }

        usage: dict[str, int] = {p["uri"]: 0 for p in alt_candidates}
        for bound_u in state["bindings"].values():
            if bound_u in usage:
                usage[bound_u] += 1

        for aid in affected_ids:
            best = min(
                alt_candidates,
                key=lambda p: (usage.get(p["uri"], 0), int(p.get("latency_ms") or 9999), str(p.get("uri"))),
            )
            state["bindings"][aid] = best["uri"]
            usage[best["uri"]] = usage.get(best["uri"], 0) + 1
            moved.append({
                "id": aid,
                "new_masked": mask_proxy_uri(best["uri"]),
                "country_code": str(best.get("country_code") or "").upper(),
            })
        save_proxy_state(state, notify=True)

    if acc_m and moved:
        for mv in moved:
            try:
                acc_m.update_account(
                    mv["id"],
                    {"bound_proxy": mv["new_masked"], "bound_proxy_country": mv["country_code"]},
                    sync_git=False,
                )
            except Exception:
                pass
        _notify_change("proxies_rebind")

    return {"ok": True, "moved": len(moved), "accounts": moved}


def delete_single_proxy(selector: str | int, auto_rebind: bool = True) -> dict[str, Any]:
    rebound_cnt = 0
    with _proxy_lock:
        state = load_proxy_state()
        idx, entry = _match_proxy_entry(state["proxies"], selector)
        if not entry:
            return {"ok": False, "error": "البروكسي غير موجود."}
        target_uri = entry["uri"]
        masked = mask_proxy_uri(target_uri)
        orphans = [aid for aid, u in state["bindings"].items() if u == target_uri]

    if auto_rebind and orphans:
        rb = rebind_proxy_accounts(target_uri)
        if rb.get("ok"):
            rebound_cnt = int(rb.get("moved") or 0)

    ok_del = remove_proxy(target_uri)
    return {
        "ok": ok_del,
        "masked_uri": masked,
        "rebound": rebound_cnt,
        "orphans": len(orphans),
    }


def unbind_accounts(account_ids: list[str] | tuple[str, ...] | set[str]) -> int:
    """فك ربط حسابات محذوفة من سجل البروكسيات لتحرير خاناتها فوراً دون حذف البروكسي نفسه من التجمع."""
    clean_ids = {str(aid or "").strip() for aid in (account_ids or []) if str(aid or "").strip()}
    if not clean_ids:
        return 0
    removed = 0
    with _proxy_lock:
        state = load_proxy_state()
        bindings = state.get("bindings")
        if isinstance(bindings, dict):
            for aid in list(bindings.keys()):
                if str(aid) in clean_ids:
                    bindings.pop(aid, None)
                    removed += 1
        if removed > 0:
            save_proxy_state(state, notify=True)
    return removed


def run_scheduled_proxy_watchdog(force: bool = False) -> dict[str, Any]:
    """مراقب آلي دوري يفحص جميع البروكسيات ويرسل تنبيهاً فورياً عند سقوط أو تعافي أي IP."""
    if not _watchdog_run_lock.acquire(blocking=False):
        return {"skipped": True, "reason": "already_running"}
    try:
        state = load_proxy_state()
        if not state["proxies"]:
            return {"skipped": True, "reason": "empty"}
        if not force:
            if not state.get("auto_check_enabled", True):
                return {"skipped": True, "reason": "disabled"}
            interval = max(30, int(state.get("auto_check_interval_sec") or 120))
            last_ts = float(state.get("last_auto_check_ts") or 0.0)
            if (time.time() - last_ts) < interval:
                return {"skipped": True, "reason": "interval"}

        res = check_all_proxies(timeout=6.0, max_workers=8)
        newly_dead = res.get("newly_dead") or []
        recovered = res.get("recovered") or []
        if newly_dead or recovered:
            _emit_proxy_alert({
                "kind": "watchdog",
                "newly_dead": newly_dead,
                "recovered": recovered,
                "alive": res.get("alive", 0),
                "dead": res.get("dead", 0),
                "checked": res.get("checked", 0),
            })
        return {"skipped": False, **res}
    finally:
        _watchdog_run_lock.release()


def mark_proxy_failure(proxy_uri: str, error: str = "") -> None:
    target = normalize_proxy_uri(proxy_uri) or str(proxy_uri or "").strip()
    if not target:
        return
    became_dead_item: dict[str, Any] | None = None
    with _proxy_lock:
        state = load_proxy_state()
        changed = False
        bindings = state.get("bindings") or {}
        for idx, p in enumerate(state["proxies"]):
            if p.get("uri") == target:
                was_alive = p.get("alive")
                p["fail_count"] = int(p.get("fail_count") or 0) + 1
                p["total_fail_count"] = int(p.get("total_fail_count") or 0) + 1
                if error:
                    p["last_error"] = str(error)[:160]
                if p["fail_count"] >= 3:
                    p["alive"] = False
                    if was_alive is not False:
                        became_dead_item = {
                            "idx": idx,
                            "id": p.get("id", ""),
                            "uri": target,
                            "masked_uri": mask_proxy_uri(target),
                            "host": p.get("host", ""),
                            "port": p.get("port", ""),
                            "error": p.get("last_error") or "فشل متكرر 3 مرات",
                            "bound_account_ids": [aid for aid, u in bindings.items() if u == target],
                        }
                changed = True
                break
        if changed:
            save_proxy_state(state, notify=True)
    if became_dead_item:
        _emit_proxy_alert({
            "kind": "proxy_down",
            "newly_dead": [became_dead_item],
            "recovered": [],
            "reason": "threshold",
        })


def locale_hints_for_geo(country_code: str, timezone: str) -> dict[str, Any]:
    """استنتاج اللغة والـ locale والمنطقة الزمنية المتوافقة مع دولة البروكسي."""
    cc = str(country_code or "").strip().upper()
    tz = str(timezone or "").strip()
    if not cc and not tz:
        return {}
    loc = _COUNTRY_LOCALES.get(cc)
    if not loc:
        loc = "ar-EG" if cc in _ARAB_COUNTRIES else "en-US"
    is_ar = loc.lower().startswith("ar") or cc in _ARAB_COUNTRIES
    langs = [loc, "ar", "en-US", "en"] if is_ar else [loc, loc.split("-")[0], "en-US", "en"]
    # إزالة التكرار مع الحفاظ على الترتيب
    dedup_langs: list[str] = []
    for item in langs:
        if item and item not in dedup_langs:
            dedup_langs.append(item)
    return {
        "country_code": cc,
        "timezone": tz,
        "locale": loc,
        "languages": dedup_langs,
    }


def _pick_least_loaded_proxy(state: dict[str, Any]) -> dict[str, Any] | None:
    candidates = [p for p in state["proxies"] if p.get("alive") is not False]
    if not candidates:
        candidates = list(state["proxies"])
    if not candidates:
        return None
    usage: dict[str, int] = {p["uri"]: 0 for p in candidates}
    for bound_uri in state.get("bindings", {}).values():
        if bound_uri in usage:
            usage[bound_uri] += 1
    # اختيار الأقل تحميلاً ثم الأسرع استجابة عند التساوي
    return min(
        candidates,
        key=lambda p: (
            usage.get(p["uri"], 0),
            int(p.get("latency_ms") or 9999),
            str(p.get("uri")),
        ),
    )


def resolve_proxy_for_account(
    account_id: str | None = None,
    explicit_proxy: str | None = None,
) -> dict[str, Any]:
    """
    حساب البروكسي المناسب لتشغيل الحساب بترتيب الأولوية:
    1) بروكسي مُمرر صراحةً للدالة (explicit_proxy)
    2) وضع نفق الفورجي 4G النشط والموصول بالهاتف فعلياً (4g_bridge)
    3) ربط الحساب الثابت (Sticky Binding) عبر تجمع البروكسيات (proxies.json)
       مع توزيع متوازن على 1,000+ حساب وعدم تغيير الدولة عشوائياً
    4) FB_PROXY من متغيرات البيئة
    5) مباشر (direct)
    """
    exp = (explicit_proxy or "").strip()
    if exp:
        return {
            "source": "explicit",
            "raw_uri": exp,
            "playwright_proxy": build_playwright_proxy_config(exp) or {"server": exp},
            "geo_hints": {},
        }

    with _proxy_lock:
        state = load_proxy_state()
        mode = state.get("mode", "sticky")

        # إذا اختار المشرف وضع نفق الفورجي وكان الهاتف متصلاً الآن على منفذ الخروج
        if mode == "4g_bridge":
            b4g = state.get("bridge_4g") or {}
            exit_port = int(_4g_runtime.get("exit_port") or b4g.get("exit_port") or 0)
            if exit_port and _4g_runtime.get("running") and _tcp_is_open("127.0.0.1", exit_port, timeout=0.35):
                uri_4g = f"http://127.0.0.1:{exit_port}"
                hints = locale_hints_for_geo(
                    str(b4g.get("country_code") or ""),
                    str(b4g.get("timezone") or ""),
                )
                return {
                    "source": "4g_bridge",
                    "raw_uri": uri_4g,
                    "playwright_proxy": {"server": uri_4g},
                    "geo_hints": hints,
                }

        # نفق مخصص من متغير البيئة FB_4G_TUNNEL
        env_4g = (os.environ.get("FB_4G_TUNNEL") or "").strip()
        if mode == "4g_bridge" and env_4g:
            pw_cfg = build_playwright_proxy_config(env_4g)
            if pw_cfg:
                return {
                    "source": "env_4g_tunnel",
                    "raw_uri": env_4g,
                    "playwright_proxy": pw_cfg,
                    "geo_hints": {},
                }

        if mode != "direct" and state["proxies"]:
            by_uri = {p["uri"]: p for p in state["proxies"]}
            acc_key = str(account_id or "").strip()
            chosen: dict[str, Any] | None = None

            if acc_key and acc_key in state["bindings"]:
                bound_uri = state["bindings"][acc_key]
                cand = by_uri.get(bound_uri)
                if cand and cand.get("alive") is not False:
                    chosen = cand

            if chosen is None:
                chosen = _pick_least_loaded_proxy(state)
                if chosen and acc_key:
                    state["bindings"][acc_key] = chosen["uri"]
                    save_proxy_state(state, notify=True)

            if chosen:
                pw_cfg = build_playwright_proxy_config(chosen["uri"])
                if pw_cfg:
                    max_cap = int(state.get("max_per_proxy", 3) or 0)
                    assigned_cnt = sum(1 for u in state["bindings"].values() if u == chosen["uri"])
                    return {
                        "source": "sticky_pool",
                        "raw_uri": chosen["uri"],
                        "playwright_proxy": pw_cfg,
                        "geo_hints": locale_hints_for_geo(
                            str(chosen.get("country_code") or ""),
                            str(chosen.get("timezone") or ""),
                        ),
                        "assigned_count": assigned_cnt,
                        "max_per_proxy": max_cap,
                        "over_capacity": bool(max_cap > 0 and assigned_cnt > max_cap),
                    }

    env_proxy = (os.environ.get("FB_PROXY") or "").strip()
    if env_proxy:
        return {
            "source": "env_fb_proxy",
            "raw_uri": env_proxy,
            "playwright_proxy": build_playwright_proxy_config(env_proxy) or {"server": env_proxy},
            "geo_hints": {},
        }

    return {"source": "direct", "raw_uri": "", "playwright_proxy": None, "geo_hints": {}}


def bind_existing_accounts(rebalance_all: bool = False) -> dict[str, int]:
    """
    ربط وتوزيع كل الحسابات الموجودة حالياً (التي أُضيفت قبل البروكسيات) بالتوازن على التجمع المتاح،
    وحفظ الربط في proxies.json وaccounts.json مع إطلاق المزامنة السحابية فوراً.
    """
    try:
        from fb_operator import account_manager as acc_m
        accounts = acc_m.load_accounts()
    except Exception:
        return {"total_accounts": 0, "newly_bound": 0, "already_bound": 0}

    pending_acc_updates: list[tuple[str, dict[str, str]]] = []
    newly_bound = 0
    already_bound = 0

    with _proxy_lock:
        state = load_proxy_state()
        if not state["proxies"] or state.get("mode") == "direct":
            return {"total_accounts": len(accounts), "newly_bound": 0, "already_bound": len(state.get("bindings") or {})}

        by_uri = {p["uri"]: p for p in state["proxies"]}
        changed = False
        for acc in accounts:
            acc_id = str(acc.get("id") or "").strip()
            if not acc_id:
                continue
            cur_uri = state["bindings"].get(acc_id, "")
            cur_item = by_uri.get(cur_uri)
            if not rebalance_all and cur_item and cur_item.get("alive") is not False:
                already_bound += 1
                if not acc.get("bound_proxy"):
                    pending_acc_updates.append((
                        acc_id,
                        {
                            "bound_proxy": mask_proxy_uri(cur_item["uri"]),
                            "bound_proxy_country": str(cur_item.get("country_code") or "").upper(),
                        },
                    ))
                continue

            if rebalance_all and acc_id in state["bindings"]:
                del state["bindings"][acc_id]
            chosen = _pick_least_loaded_proxy(state)
            if chosen:
                state["bindings"][acc_id] = chosen["uri"]
                changed = True
                newly_bound += 1
                pending_acc_updates.append((
                    acc_id,
                    {
                        "bound_proxy": mask_proxy_uri(chosen["uri"]),
                        "bound_proxy_country": str(chosen.get("country_code") or "").upper(),
                    },
                ))

        if changed:
            save_proxy_state(state, notify=True)

    for aid, upd in pending_acc_updates:
        try:
            acc_m.update_account(aid, upd, sync_git=False)
        except Exception:
            pass
    if pending_acc_updates:
        _notify_change("proxies_bind_existing")

    return {
        "total_accounts": len(accounts),
        "newly_bound": newly_bound,
        "already_bound": already_bound,
    }


# ==============================================================================
# محرك نفق الفورجي العكسي من الهاتف إلى السيرفر (go-gost v3 + cloudflared)
# ==============================================================================

def ensure_gost_binary() -> str | None:
    """البحث عن أداة go-gost/gost v3 أو تنزيلها تلقائياً من إصدارات GitHub الرسمية."""
    existing = shutil.which("gost")
    if existing:
        return existing

    is_win = platform.system().lower().startswith("win")
    bin_name = "gost.exe" if is_win else "gost"
    cache_dir = Path(config.DATA_DIR) / "bin"
    cache_bin = cache_dir / bin_name
    tmp_bin = Path("/tmp/gost") if not is_win else (cache_dir / "gost.exe")

    for p in (cache_bin, tmp_bin):
        if p.exists() and (is_win or os.access(p, os.X_OK)):
            return str(p)

    sys_name = platform.system().lower()
    mach = platform.machine().lower()
    if sys_name == "linux":
        if mach in ("x86_64", "amd64"):
            asset = f"gost_{GOST_VERSION}_linux_amd64.tar.gz"
        elif mach in ("aarch64", "arm64"):
            asset = f"gost_{GOST_VERSION}_linux_arm64.tar.gz"
        else:
            return None
    elif sys_name == "windows" and mach in ("amd64", "x86_64"):
        asset = f"gost_{GOST_VERSION}_windows_amd64.zip"
    else:
        return None

    url = f"https://github.com/go-gost/gost/releases/download/v{GOST_VERSION}/{asset}"
    cache_dir.mkdir(parents=True, exist_ok=True)
    archive_path = cache_dir / asset

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=60) as resp, open(archive_path, "wb") as f:
            shutil.copyfileobj(resp, f)

        if asset.endswith(".tar.gz"):
            with tarfile.open(archive_path, "r:gz") as tf:
                for member in tf.getmembers():
                    if member.name.endswith("/gost") or member.name == "gost":
                        extracted = tf.extractfile(member)
                        if extracted:
                            with open(cache_bin, "wb") as out:
                                shutil.copyfileobj(extracted, out)
                            os.chmod(cache_bin, 0o755)
                            break
        else:
            with zipfile.ZipFile(archive_path, "r") as zf:
                for name in zf.namelist():
                    if name.lower().endswith("gost.exe"):
                        with zf.open(name) as src, open(cache_bin, "wb") as out:
                            shutil.copyfileobj(src, out)
                        break

        try:
            archive_path.unlink(missing_ok=True)
        except Exception:
            pass
        return str(cache_bin) if cache_bin.exists() else None
    except Exception:
        return None


def _find_cloudflared_binary() -> str | None:
    try:
        from fb_operator import webapp_server
        return webapp_server._ensure_cloudflared_binary()
    except Exception:
        return shutil.which("cloudflared")


def stop_gost_4g_bridge() -> None:
    with _4g_lock:
        for key in ("cf_proc", "gost_proc"):
            proc = _4g_runtime.get(key)
            if proc is not None and proc.poll() is None:
                try:
                    proc.terminate()
                    proc.wait(timeout=3)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass
            _4g_runtime[key] = None
        _4g_runtime["running"] = False
        _4g_runtime["tunnel_url"] = ""
        _4g_runtime["tunnel_host"] = ""
        _4g_runtime["error"] = ""


def start_gost_4g_bridge() -> dict[str, Any]:
    """
    تشغيل بوابة النفق العكسي للفورجي:
    - خادم gost يستمع محلياً على relay+ws مع ?bind=true
    - نفق cloudflared ينشر البوابة على wss://*.trycloudflare.com
    - بمجرد تشغيل سطر واحد في هاتف الأندرويد (Termux)، تفتح بوابة exit_port على السيرفر
      وتخرج طلبات كروم مباشرة عبر شريحة 4G للهاتف!
    """
    gost_bin = ensure_gost_binary()
    if not gost_bin:
        return {"ok": False, "error": "تعذر العثور على أداة gost v3 أو تنزيلها في هذه البيئة."}

    cf_bin = _find_cloudflared_binary()
    if not cf_bin:
        return {"ok": False, "error": "أداة cloudflared غير متوفرة حالياً لفتح نفق HTTPS العكسي."}

    state = load_proxy_state()
    b4g = state["bridge_4g"]
    u4g = str(b4g.get("username") or f"g4_{secrets.token_hex(3)}")
    p4g = str(b4g.get("password") or secrets.token_urlsafe(12))
    exit_port = _find_free_port()
    ws_port = _find_free_port()

    stop_gost_4g_bridge()

    with _4g_lock:
        gost_cmd = [
            gost_bin,
            "-L",
            f"relay+ws://{u4g}:{p4g}@127.0.0.1:{ws_port}?bind=true",
        ]
        try:
            gost_proc = subprocess.Popen(
                gost_cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.STDOUT,
            )
            cf_proc = subprocess.Popen(
                [cf_bin, "tunnel", "--no-autoupdate", "--url", f"http://127.0.0.1:{ws_port}"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
        except Exception as e:
            return {"ok": False, "error": f"فشل تشغيل النفق: {e}"}

        _4g_runtime.update({
            "running": True,
            "ws_port": ws_port,
            "exit_port": exit_port,
            "tunnel_url": "",
            "tunnel_host": "",
            "username": u4g,
            "password": p4g,
            "gost_proc": gost_proc,
            "cf_proc": cf_proc,
            "error": "",
            "started_at": datetime.now().isoformat(timespec="seconds"),
        })

    url_ready = threading.Event()
    pat = re.compile(r"https://([a-zA-Z0-9-]+\.trycloudflare\.com)")

    def _watch_cf() -> None:
        assert cf_proc.stdout is not None
        for line in cf_proc.stdout:
            m = pat.search(line)
            if m and not _4g_runtime.get("tunnel_host"):
                host = m.group(1)
                _4g_runtime["tunnel_host"] = host
                _4g_runtime["tunnel_url"] = f"wss://{host}:443"
                url_ready.set()

    threading.Thread(target=_watch_cf, daemon=True, name="gost-4g-cf-watch").start()
    url_ready.wait(timeout=15.0)

    if not _4g_runtime.get("tunnel_host"):
        _4g_runtime["error"] = "جاري انتظار رابط cloudflared..."

    # حفظ المنفذ وبيانات الربط وتفعيل وضع 4G تلقائياً متى ما اتصل الهاتف
    with _proxy_lock:
        fresh = load_proxy_state()
        fresh["bridge_4g"]["username"] = u4g
        fresh["bridge_4g"]["password"] = p4g
        fresh["bridge_4g"]["exit_port"] = exit_port
        save_proxy_state(fresh, notify=False)

    return get_4g_bridge_status()


def refresh_4g_client_geo() -> dict[str, Any]:
    """فحص اتصال الهاتف فعلياً واكتشاف IP ودولة شريحة 4G بمجرد ربط Termux."""
    st = get_4g_bridge_status()
    if not st.get("client_connected"):
        return {"connected": False}
    geo = _probe_geo_over_http_proxy(f"http://127.0.0.1:{st['exit_port']}", timeout=7.0)
    if geo.get("exit_ip"):
        with _proxy_lock:
            state = load_proxy_state()
            state["bridge_4g"]["exit_ip"] = geo.get("exit_ip", "")
            state["bridge_4g"]["country_code"] = geo.get("country_code", "")
            state["bridge_4g"]["timezone"] = geo.get("timezone", "")
            save_proxy_state(state, notify=False)
    return {"connected": bool(geo.get("exit_ip")), **geo}


def get_4g_bridge_status(include_secrets: bool = False) -> dict[str, Any]:
    exit_port = int(_4g_runtime.get("exit_port") or 0)
    gproc = _4g_runtime.get("gost_proc")
    cproc = _4g_runtime.get("cf_proc")
    running = bool(
        _4g_runtime.get("running")
        and gproc is not None and gproc.poll() is None
        and cproc is not None and cproc.poll() is None
    )
    client_connected = bool(running and exit_port and _tcp_is_open("127.0.0.1", exit_port, timeout=0.3))
    state = load_proxy_state()
    b4g = state["bridge_4g"]

    u = str(_4g_runtime.get("username") or b4g.get("username") or "")
    p = str(_4g_runtime.get("password") or b4g.get("password") or "")
    host = str(_4g_runtime.get("tunnel_host") or "")

    termux_cmd = ""
    pc_cmd = ""
    if running and host:
        termux_cmd = (
            f"curl -sL https://github.com/go-gost/gost/releases/download/v{GOST_VERSION}/"
            f"gost_{GOST_VERSION}_android_arm64.tar.gz | tar xz && chmod +x gost && "
            f'./gost -L "http+socks5://127.0.0.1:10808" '
            f'-L "rtcp://127.0.0.1:{exit_port}/127.0.0.1:10808" '
            f'-F "relay+wss://{u}:{p}@{host}:443"'
        )
        pc_cmd = (
            f'gost -L "http+socks5://127.0.0.1:10808" '
            f'-L "rtcp://127.0.0.1:{exit_port}/127.0.0.1:10808" '
            f'-F "relay+wss://{u}:{p}@{host}:443"'
        )

    out = {
        "ok": True,
        "running": running,
        "client_connected": client_connected,
        "exit_port": exit_port,
        "tunnel_url": str(_4g_runtime.get("tunnel_url") or ""),
        "tunnel_host": host,
        "exit_ip": str(b4g.get("exit_ip") or ""),
        "country_code": str(b4g.get("country_code") or ""),
        "timezone": str(b4g.get("timezone") or ""),
        "error": str(_4g_runtime.get("error") or ""),
    }
    if include_secrets:
        out["termux_cmd"] = termux_cmd
        out["pc_cmd"] = pc_cmd
    return out


def get_proxy_summary() -> dict[str, Any]:
    state = load_proxy_state()
    proxies = state["proxies"]
    alive = sum(1 for p in proxies if p.get("alive") is True)
    dead = sum(1 for p in proxies if p.get("alive") is False)
    untested = len(proxies) - alive - dead
    b4g = get_4g_bridge_status(include_secrets=False)
    usage_counts: dict[str, int] = {}
    for p_uri in state["bindings"].values():
        usage_counts[p_uri] = usage_counts.get(p_uri, 0) + 1
    max_assigned = max(usage_counts.values(), default=0)
    configured_max = int(state.get("max_per_proxy", 3) or 0)
    usable_pool = sum(1 for p in proxies if p.get("alive") is not False)
    safe_capacity = (usable_pool * configured_max) if configured_max > 0 else 0
    overloaded_proxies = (
        sum(1 for cnt in usage_counts.values() if cnt > configured_max)
        if configured_max > 0
        else 0
    )
    total_uses = sum(int(p.get("uses_count") or 0) for p in proxies)
    return {
        "mode": state["mode"],
        "total": len(proxies),
        "alive": alive,
        "dead": dead,
        "untested": untested,
        "bindings_count": len(state["bindings"]),
        "max_accounts_per_proxy": max_assigned,
        "configured_max_per_proxy": configured_max,
        "safe_capacity": safe_capacity,
        "overloaded_proxies": overloaded_proxies,
        "is_overloaded": bool(overloaded_proxies > 0 or (safe_capacity > 0 and len(state["bindings"]) > safe_capacity)),
        "auto_check_enabled": bool(state.get("auto_check_enabled", True)),
        "auto_check_interval_sec": int(state.get("auto_check_interval_sec") or 120),
        "last_auto_check_ts": float(state.get("last_auto_check_ts") or 0.0),
        "total_uses": total_uses,
        "bridge_4g": b4g,
    }


def get_proxy_detailed_report() -> dict[str, Any]:
    """تقرير تفصيلي لحظي لكل IP: عدد مرات الاستخدام، حالة الفحص، وقائمة الحسابات المربوطة به بالاسم."""
    state = load_proxy_state()
    summary = get_proxy_summary()
    try:
        from fb_operator import account_manager as acc_m
        acc_by_id = {str(a.get("id")): a for a in acc_m.load_accounts() if a.get("id")}
    except Exception:
        acc_by_id = {}

    bound_by_uri: dict[str, list[dict[str, str]]] = {}
    for aid, p_uri in (state.get("bindings") or {}).items():
        a_obj = acc_by_id.get(str(aid))
        bound_by_uri.setdefault(p_uri, []).append({
            "id": str(aid),
            "name": str(a_obj.get("name") or aid) if a_obj else str(aid),
            "status": str(a_obj.get("status") or "") if a_obj else "",
            "fb_id": str(a_obj.get("fb_id") or "") if a_obj else "",
        })

    configured_max = int(state.get("max_per_proxy", 3) or 0)
    items: list[dict[str, Any]] = []
    for idx, p in enumerate(state["proxies"]):
        uri = str(p.get("uri") or "")
        bound_accs = bound_by_uri.get(uri, [])
        items.append({
            "idx": idx,
            "id": str(p.get("id") or f"prx_{idx + 1}"),
            "masked_uri": mask_proxy_uri(uri),
            "host": str(p.get("host") or ""),
            "port": p.get("port"),
            "scheme": str(p.get("scheme") or ""),
            "country_code": str(p.get("country_code") or "").upper(),
            "country_name": str(p.get("country_name") or ""),
            "exit_ip": str(p.get("exit_ip") or ""),
            "latency_ms": p.get("latency_ms"),
            "alive": p.get("alive"),
            "uses_count": int(p.get("uses_count") or 0),
            "success_count": int(p.get("success_count") or 0),
            "fail_count": int(p.get("fail_count") or 0),
            "total_fail_count": int(p.get("total_fail_count") or 0),
            "last_used_at": str(p.get("last_used_at") or ""),
            "last_checked": str(p.get("last_checked") or ""),
            "last_error": str(p.get("last_error") or ""),
            "bound_count": len(bound_accs),
            "max_per_proxy": configured_max,
            "over_capacity": bool(configured_max > 0 and len(bound_accs) > configured_max),
            "bound_accounts": bound_accs,
        })
    return {"summary": summary, "items": items}
