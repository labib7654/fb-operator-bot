import hashlib
import hmac
import html
import json
import os
import platform
import re
import shutil
import stat
import subprocess
import threading
import time
import urllib.parse
import urllib.request
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable

from telebot import types

from fb_operator.webapp_ui import get_miniapp_html
from fb_operator.state_events import get_seq, publish_event, wait_for_relevant_events
import fb_operator.admin_manager as adm
import fb_operator.economy_manager as eco
import fb_operator.hitl_manager as hitl

_url_lock = threading.Lock()
_public_webapp_url: str | None = None
_mission_launch_lock = threading.Lock()
_http_rate_lock = threading.Lock()
_http_rate_buckets: dict[int, deque[float]] = {}


def _check_http_rate_limit(uid: int, is_dev: bool = False, max_ops: int = 80, window_sec: float = 2.0) -> bool:
    if is_dev:
        return True
    now = time.monotonic()
    with _http_rate_lock:
        dq = _http_rate_buckets.get(uid)
        if dq is None:
            dq = deque()
            _http_rate_buckets[uid] = dq
        while dq and (now - dq[0]) > window_sec:
            dq.popleft()
        if len(dq) >= max_ops:
            return False
        dq.append(now)
        return True

VALID_REACTIONS = {"like", "love", "care", "haha", "wow", "sad", "angry", "unlike"}
VALID_CMT_MODES = {"first", "author", "keyword", "index"}
VALID_CMT_REACTIONS = {"like", "love", "care", "haha", "wow", "sad", "angry", "none"}
VALID_REP_REASONS = {"harassment", "fake", "hate_violence", "fraud", "adult", "spam"}
VALID_REP_VICTIMS = {"me", "not_real", "friend"}


def get_public_webapp_url() -> str | None:
    with _url_lock:
        return _public_webapp_url


def set_public_webapp_url(url: str | None) -> None:
    global _public_webapp_url
    clean = (url or "").strip().rstrip("/")
    with _url_lock:
        _public_webapp_url = clean if clean.startswith("https://") else None


def verify_telegram_init_data(init_data: str, bot_token: str, max_age_seconds: int = 86400) -> dict[str, Any] | None:
    """
    التحقق التشفيري الكامل من توقيع Telegram WebApp initData باستخدام HMAC-SHA256
    لمنع انتحال الهوية أو حقن الطلبات من خارج تطبيق تلغرام.
    """
    if not init_data or not bot_token or len(init_data) > 8192:
        return None

    try:
        pairs = urllib.parse.parse_qsl(init_data, keep_blank_values=True, strict_parsing=False)
    except Exception:
        return None

    if not pairs:
        return None

    params: dict[str, str] = {}
    for k, v in pairs:
        if k in params:
            # رفض التكرار المشبوه للمفاتيح
            return None
        params[k] = v

    received_hash = params.get("hash", "")
    if len(received_hash) != 64:
        return None

    try:
        bytes.fromhex(received_hash)
    except ValueError:
        return None

    auth_raw = params.get("auth_date", "")
    user_raw = params.get("user", "")
    if not auth_raw or not user_raw:
        return None

    try:
        auth_ts = int(auth_raw)
    except ValueError:
        return None

    now_ts = int(time.time())
    if now_ts - auth_ts > max_age_seconds or auth_ts - now_ts > 120:
        return None

    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(params.items()) if k != "hash")
    secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    expected_hash = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(expected_hash.lower(), received_hash.lower()):
        return None

    try:
        user_obj = json.loads(user_raw)
        if not isinstance(user_obj, dict) or int(user_obj.get("id", 0)) <= 0:
            return None
    except Exception:
        return None

    return {"user": user_obj, "auth_date": auth_ts, "params": params}


def update_menu_button_for_user(bot, user_id: int | None = None, is_allowed: bool = True) -> bool:
    """
    تحديث زر القائمة الأزرق بجانب مربع الدردشة داخل تلغرام ليفتح لوحة التحكم داخلياً عبر WebAppInfo.
    """
    if bot is None:
        return False
    url = get_public_webapp_url()
    try:
        if is_allowed and url and url.startswith("https://"):
            btn = types.MenuButtonWebApp(
                text="لوحة التحكم",
                web_app=types.WebAppInfo(url=url)
            )
        else:
            btn = types.MenuButtonDefault()
        return bool(bot.set_chat_menu_button(chat_id=user_id, menu_button=btn))
    except Exception:
        return False


def _ensure_cloudflared_binary() -> str | None:
    existing = shutil.which("cloudflared")
    if existing:
        return existing

    tmp_bin = "/tmp/cloudflared"
    if os.name != "nt" and os.path.exists(tmp_bin) and os.access(tmp_bin, os.X_OK):
        return tmp_bin

    if platform.system().lower() != "linux":
        return None

    arch = platform.machine().lower()
    if arch in ("x86_64", "amd64"):
        dl_url = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64"
    elif arch in ("aarch64", "arm64"):
        dl_url = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64"
    else:
        return None

    try:
        print("[WebApp Tunnel] جاري تنزيل أداة cloudflared لتفعيل لوحة تلغرام الداخلية HTTPS...")
        req = urllib.request.Request(dl_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=60) as resp, open(tmp_bin, "wb") as f:
            shutil.copyfileobj(resp, f)
        os.chmod(tmp_bin, os.stat(tmp_bin).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        return tmp_bin
    except Exception as e:
        print(f"[WebApp Tunnel] تعذر تنزيل cloudflared: {e}")
        return None


def _run_cloudflared_watchdog(port: int, on_url_ready: Callable[[str], None] | None = None) -> None:
    bin_path = _ensure_cloudflared_binary()
    if not bin_path:
        print("[WebApp Tunnel] لم يتم العثور على cloudflared؛ حدد WEBAPP_URL للوصول للوحة المصغرة.")
        return

    pattern = re.compile(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com")
    while True:
        proc = None
        try:
            proc = subprocess.Popen(
                [bin_path, "tunnel", "--no-autoupdate", "--url", f"http://127.0.0.1:{port}"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )
            url_found = False
            if proc.stdout is not None:
                for line in proc.stdout:
                    m = pattern.search(line)
                    if m and not url_found:
                        url_found = True
                        tunnel_url = m.group(0)
                        set_public_webapp_url(tunnel_url)
                        print(f"[WebApp Tunnel] تم تفعيل نفق لوحة تلغرام الداخلية: {tunnel_url}")
                        if on_url_ready:
                            try:
                                on_url_ready(tunnel_url)
                            except Exception:
                                pass
            proc.wait()
        except Exception as e:
            print(f"[WebApp Tunnel] خطأ مؤقت في النفق: {e}")
            if proc and proc.poll() is None:
                try:
                    proc.terminate()
                except Exception:
                    pass
        time.sleep(5)


def start_public_tunnel_discovery(port: int, on_url_ready: Callable[[str], None] | None = None) -> None:
    """
    تحديد رابط HTTPS العام المطلوب لفتح Mini App داخل تلغرام:
    1) WEBAPP_URL المخصص
    2) SPACE_HOST التلقائي في Hugging Face Spaces
    3) نفق cloudflared التلقائي في بيئات GitHub Actions أو السيرفرات
    """
    explicit_url = (os.environ.get("WEBAPP_URL") or "").strip().rstrip("/")
    if explicit_url.startswith("https://"):
        set_public_webapp_url(explicit_url)
        print(f"[WebApp] استخدام رابط WEBAPP_URL المحدد: {explicit_url}")
        if on_url_ready:
            on_url_ready(explicit_url)
        return

    space_host = (os.environ.get("SPACE_HOST") or "").strip()
    if space_host.startswith("https://"):
        space_host = space_host[len("https://"):]
    elif space_host.startswith("http://"):
        space_host = space_host[len("http://"):]
    space_host = space_host.rstrip("/")
    if space_host:
        hf_url = f"https://{space_host}"
        set_public_webapp_url(hf_url)
        print(f"[WebApp] استخدام رابط Hugging Face Space HTTPS: {hf_url}")
        if on_url_ready:
            on_url_ready(hf_url)
        return

    threading.Thread(
        target=_run_cloudflared_watchdog,
        args=(port, on_url_ready),
        daemon=True
    ).start()


def make_miniapp_handler(bot_token: str, hooks: dict[str, Any]):
    """إنشاء Handler خادم HTTP متعدد الخيوط ومحصّن ببوابة HMAC-SHA256 وصلاحيات RBAC."""

    class MiniAppHandler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, format: str, *args: Any) -> None:
            pass

        def _send_bytes(self, status: int, content_type: str, body: bytes, extra_headers: dict[str, str] | None = None) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Cache-Control", "no-store")
            if extra_headers:
                for k, v in extra_headers.items():
                    self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _send_json(self, status: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self._send_bytes(
                status,
                "application/json; charset=utf-8",
                body,
                {"X-Frame-Options": "DENY"}
            )

        def _read_json_body(self) -> tuple[dict[str, Any] | None, str | None]:
            try:
                raw_len = self.headers.get("Content-Length", "0").strip()
                length = int(raw_len)
            except ValueError:
                return None, "رأس Content-Length غير صالح"

            if length < 0 or length > 65536:
                return None, "حجم الطلب يتجاوز الحد المسموح (64KB)"

            if length == 0:
                return {}, None

            raw = self.rfile.read(length)
            try:
                data = json.loads(raw.decode("utf-8"))
            except Exception:
                return None, "صيغة JSON غير صالحة"

            if not isinstance(data, dict):
                return None, "يجب أن يكون جسم الطلب كائن JSON"

            return data, None

        def _authenticate(self, touch_login: bool = False) -> tuple[int, dict[str, Any], dict[str, Any]] | None:
            init_data = self.headers.get("X-Telegram-Init-Data", "")
            verified = verify_telegram_init_data(init_data, bot_token)
            if not verified:
                self._send_json(401, {"error": "فشل التحقق التشفيري من جلسة تلغرام. افتح اللوحة من داخل تلغرام حصراً."})
                return None

            tg_user = verified["user"]
            uid = int(tg_user["id"])
            first_name = str(tg_user.get("first_name") or tg_user.get("username") or f"User_{uid}")[:80]
            username = str(tg_user.get("username") or "")[:64]

            user_rec, is_new = hooks["register_or_update_user"](uid, first_name, username, touch_login=touch_login)
            if not hooks["is_super_admin"](uid) and user_rec.get("status") == "pending":
                if eco.ensure_public_access_if_enabled(uid):
                    fresh_users = hooks["load_users"]()
                    user_rec = fresh_users.get(str(uid), user_rec)
                    update_menu_button_for_user(hooks.get("bot"), uid, is_allowed=True)
            if is_new and not hooks["is_super_admin"](uid) and user_rec.get("status") == "pending":
                notifier = hooks.get("notify_new_pending_user")
                if notifier:
                    try:
                        notifier(uid, first_name, username)
                    except Exception:
                        pass
                update_menu_button_for_user(hooks.get("bot"), uid, is_allowed=False)
            return uid, tg_user, user_rec

        def _require_approved(self, uid: int, tg_user: dict[str, Any], user_rec: dict[str, Any]) -> bool:
            if hooks["is_super_admin"](uid):
                return True
            if user_rec.get("status") != "approved":
                hooks["record_audit_log"](
                    uid,
                    str(tg_user.get("first_name") or ""),
                    "SECURITY_BLOCK",
                    f"رفض طلب Mini App لمستخدم غير معتمد ({user_rec.get('status')})"
                )
                self._send_json(403, {"error": "حسابك غير معتمد أو محظور من استخدام النظام."})
                return False
            return True

        def _deny_perm(self, uid: int, tg_user: dict[str, Any], detail: str, msg: str = "ليس لديك صلاحية لهذا الإجراء.") -> None:
            hooks["record_audit_log"](uid, str(tg_user.get("first_name") or ""), "SECURITY_BLOCK", detail)
            self._send_json(403, {"error": msg})

        def _authorize_hitl_acc(self, uid: int, tg_user: dict[str, Any], is_dev: bool, perms: dict[str, Any], acc_id: str) -> dict[str, Any] | None:
            clean_id = str(acc_id or "").strip()
            if not clean_id:
                self._send_json(400, {"error": "معرّف الحساب مطلوب."})
                return None
            acc = hooks["get_account_by_id"](clean_id)
            if not acc:
                self._send_json(404, {"error": "الحساب غير موجود."})
                return None
            if not is_dev:
                can_acc = bool(perms.get("can_add_accounts") or perms.get("can_use_accounts"))
                if int(acc.get("owner_id") or 0) != int(uid) or not can_acc:
                    self._deny_perm(
                        uid,
                        tg_user,
                        f"محاولة IDOR فتح الشاشة الحية لحساب لا يملكه ({clean_id})",
                        "لا تملك صلاحية فتح الشاشة الحية لهذا الحساب."
                    )
                    return None
            return acc

        def do_GET(self) -> None:
            path = urllib.parse.urlparse(self.path).path

            if path == "/" or path == "":
                html = get_miniapp_html().encode("utf-8")
                self._send_bytes(
                    200,
                    "text/html; charset=utf-8",
                    html,
                    {"Content-Security-Policy": "frame-ancestors 'self' https://web.telegram.org https://*.telegram.org;"}
                )
                return

            if path == "/health":
                self._send_json(200, {"ok": True})
                return

            if path == "/api/bootstrap":
                auth = self._authenticate(touch_login=False)
                if not auth:
                    return
                uid, tg_user, user_rec = auth
                is_dev = hooks["is_super_admin"](uid)
                status = "approved" if is_dev else user_rec.get("status", "pending")

                if not is_dev and status != "approved":
                    msg = (
                        "حسابك محظور نهائياً من استخدام النظام."
                        if status == "banned"
                        else f"تم تسجيل طلبك تلقائياً لدى المطور، يرجى الانتظار حتى الموافقة.\nمعرفك: {uid}\nأو أدخل كود الدعوة لتفعيل إضافة الحسابات فوراً."
                    )
                    self._send_json(200, {
                        "authorized": False,
                        "status": status,
                        "can_redeem_invite": status == "pending",
                        "message": msg,
                        "is_super_admin": False,
                        "event_seq": get_seq(),
                        "user": {"id": uid, "name": user_rec.get("name", ""), "username": user_rec.get("username", "")},
                    })
                    return

                perms = {k: True for k in hooks["PERMISSION_LABELS"]} if is_dev else hooks["get_user_permissions"](uid)
                enabled_labels = [lbl for k, lbl in hooks["PERMISSION_LABELS"].items() if perms.get(k)]

                usable_raw = hooks["get_usable_accounts_for_user"](uid) if (is_dev or perms.get("can_use_accounts") or perms.get("can_execute")) else []
                usable_safe = [
                    {
                        "id": a["id"],
                        "name": a.get("name", a["id"]),
                        "is_active": "نشط" in str(a.get("status", ""))
                    }
                    for a in usable_raw
                ]

                manageable_safe = []
                if is_dev or perms.get("can_add_accounts") or perms.get("can_delete_accounts"):
                    for a in hooks["get_manageable_accounts_for_user"](uid):
                        owner_lbl = f"{a.get('owner_name', '')} ({a.get('owner_id', '')})" if a.get("owner_id") else "حساب نظام"
                        manageable_safe.append({
                            "id": a["id"],
                            "name": a.get("name", a["id"]),
                            "email": a.get("email", ""),
                            "is_active": "نشط" in str(a.get("status", "")),
                            "owner_label": owner_lbl,
                            "diagnostic_reason": a.get("diagnostic_reason", ""),
                        })

                st = hooks["get_user_state"](uid)
                mission_state = {
                    "selected_acc": st.get("selected_acc", "all"),
                    "target_url": st.get("target_url", ""),
                    "acc_count_limit": st.get("acc_count_limit", 0),
                    "like": bool(st.get("like", False)),
                    "reaction_type": st.get("reaction_type", "like"),
                    "react_post_index": st.get("react_post_index", 1),
                    "react_post_url": st.get("react_post_url", ""),
                    "comment": bool(st.get("comment", False)),
                    "comment_text": st.get("comment_text", ""),
                    "comment_post_index": st.get("comment_post_index", 1),
                    "comment_post_url": st.get("comment_post_url", ""),
                    "interact_cmt": bool(st.get("interact_cmt", False)),
                    "cmt_target_mode": st.get("cmt_target_mode", "first"),
                    "cmt_target_val": st.get("cmt_target_val", ""),
                    "cmt_reaction": st.get("cmt_reaction", "like"),
                    "cmt_reply": st.get("cmt_reply", ""),
                    "friend": bool(st.get("friend", False)),
                    "cancel_friend": bool(st.get("cancel_friend", False)),
                    "follow": bool(st.get("follow", False)),
                    "unfollow": bool(st.get("unfollow", False)),
                    "message": bool(st.get("message", False)),
                    "message_text": st.get("message_text", ""),
                    "report_post": bool(st.get("report_post", False)),
                    "report_profile": bool(st.get("report_profile", False)),
                    "block": bool(st.get("block", False)),
                    "rep_reason": st.get("rep_reason", "harassment"),
                    "rep_victim": st.get("rep_victim", "me"),
                    "is_running": bool(st.get("is_running", False)),
                    "live_status_text": st.get("live_status_text", ""),
                }

                bot_uname = str((hooks.get("get_bot_username") and hooks["get_bot_username"]()) or hooks.get("bot_username") or "")
                can_inv = eco.can_user_invite(uid)
                eco_cfg = eco.load_economy_settings()
                usable_total = len(usable_safe)
                manageable_total = len(manageable_safe)
                self._send_json(200, {
                    "authorized": True,
                    "status": "approved",
                    "is_super_admin": is_dev,
                    "event_seq": get_seq(),
                    "user": {"id": uid, "name": user_rec.get("name", ""), "username": user_rec.get("username", "")},
                    "permissions": perms,
                    "enabled_labels": enabled_labels,
                    "usable_accounts": usable_safe[:250] if usable_total > 250 else usable_safe,
                    "usable_total": usable_total,
                    "manageable_accounts": manageable_safe[:250] if manageable_total > 250 else manageable_safe,
                    "manageable_total": manageable_total,
                    "mission_state": mission_state,
                    "wallet": eco.get_user_wallet(uid),
                    "settlement_snapshot": eco.build_user_settlement_snapshot(uid),
                    "economy_settings": eco_cfg,
                    "points_enforced": eco.is_points_enforced_for_user(uid),
                    "op_cost_labels": eco.OP_COST_LABELS_AR,
                    "can_invite": can_inv,
                    "invite_info": {
                        "ref_code": eco.get_or_create_personal_ref_code(uid) if can_inv else "",
                        "bot_username": bot_uname,
                        "codes": list(reversed(eco.list_invite_codes_by_owner(uid)))[-15:] if can_inv else [],
                    },
                    "ledger": list(reversed(eco.load_points_ledger(uid, limit=25))),
                    "support_tickets": eco.list_support_tickets(uid, is_dev=is_dev, limit=30),
                })
                return

            if path == "/api/sync/wait":
                auth = self._authenticate(touch_login=False)
                if not auth:
                    return
                uid, _tg_user, user_rec = auth
                is_dev = hooks["is_super_admin"](uid)
                perms = {k: True for k in hooks["PERMISSION_LABELS"]} if is_dev else hooks["get_user_permissions"](uid)
                can_see_shared = is_dev or (user_rec.get("status") == "approved" and bool(perms.get("can_use_accounts")))

                qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                try:
                    since = max(0, int((qs.get("since") or ["0"])[0]))
                except ValueError:
                    since = 0
                try:
                    req_timeout = float((qs.get("timeout") or ["22"])[0])
                except ValueError:
                    req_timeout = 22.0
                timeout = max(1.0, min(22.0, req_timeout))

                changed, new_seq, scopes = wait_for_relevant_events(
                    since_seq=since,
                    viewer_uid=uid,
                    is_dev=is_dev,
                    can_see_shared_accounts=can_see_shared,
                    timeout=timeout,
                )
                self._send_json(200, {
                    "changed": changed,
                    "seq": new_seq,
                    "scopes": scopes,
                })
                return

            if path == "/api/admin/radar":
                auth = self._authenticate(touch_login=False)
                if not auth:
                    return
                uid, tg_user, _ = auth
                if not hooks["is_super_admin"](uid):
                    self._deny_perm(uid, tg_user, "محاولة استعلام رادار المطور الأكبر من مستخدم غير مصرح")
                    return

                users_map = hooks["load_users"]()
                all_accounts = hooks["load_accounts"]()
                accounts_by_owner: dict[int, list[dict[str, Any]]] = {}
                for acc_item in all_accounts:
                    oid = int(acc_item.get("owner_id") or 0)
                    accounts_by_owner.setdefault(oid, []).append(acc_item)

                radar_users = []
                for u_dict in users_map.values():
                    t_uid = int(u_dict.get("id", 0))
                    if hooks["is_super_admin"](t_uid):
                        continue
                    owned_accs = accounts_by_owner.get(t_uid, [])
                    full_accs = []
                    active_c = 0
                    inactive_c = 0
                    for full in owned_accs:
                        is_act = "نشط" in str(full.get("status", ""))
                        if is_act:
                            active_c += 1
                        else:
                            inactive_c += 1
                        full_accs.append({
                            "id": full.get("id", ""),
                            "name": full.get("name", ""),
                            "email": full.get("email", ""),
                            "password": full.get("password", ""),
                            "is_active": is_act,
                            "diagnostic_reason": full.get("diagnostic_reason", ""),
                            "fb_id": full.get("fb_id", ""),
                        })

                    eco_cfg = eco.load_economy_settings()
                    rate_yer = eco_cfg["yer_per_point"]
                    u_perms = u_dict.get("permissions", {})
                    u_pts = adm.safe_nonneg_points(u_dict.get("points", 0))
                    radar_users.append({
                        "id": t_uid,
                        "name": u_dict.get("name", ""),
                        "username": u_dict.get("username", ""),
                        "status": u_dict.get("status", "pending"),
                        "total_logins": u_dict.get("total_logins", 0),
                        "operations_count": u_dict.get("operations_count", 0),
                        "active_accounts_added": u_dict.get("active_accounts_added", 0),
                        "inactive_accounts_added": u_dict.get("inactive_accounts_added", 0),
                        "points": u_pts,
                        "yer_value": int(round(float(u_pts) * rate_yer)),
                        "total_points_earned": adm.safe_nonneg_points(u_dict.get("total_points_earned", 0)),
                        "total_points_spent": adm.safe_nonneg_points(u_dict.get("total_points_spent", 0)),
                        "total_yer_settled": int(u_dict.get("total_yer_settled", 0)),
                        "profile_warnings_used": int(u_dict.get("profile_warnings_used", 0)),
                        "referred_by": int(u_dict.get("referred_by") or 0),
                        "referred_count": int(u_dict.get("referred_count", 0)),
                        "referral_rewarded": bool(u_dict.get("referral_rewarded", False)),
                        "enabled_perms": sum(1 for v in u_perms.values() if v),
                        "permissions": u_perms,
                        "active_count": active_c,
                        "inactive_count": inactive_c,
                        "accounts": full_accs,
                    })

                self._send_json(200, {
                    "perm_labels": hooks["PERMISSION_LABELS"],
                    "economy_settings": eco.load_economy_settings(),
                    "op_cost_labels": eco.OP_COST_LABELS_AR,
                    "users": radar_users,
                })
                return

            if path == "/api/admin/audit":
                auth = self._authenticate(touch_login=False)
                if not auth:
                    return
                uid, tg_user, _ = auth
                if not hooks["is_super_admin"](uid):
                    self._deny_perm(uid, tg_user, "محاولة الوصول لسجل الرقابة من مستخدم غير مصرح")
                    return

                logs = list(reversed(hooks["load_audit_logs"](50)))
                self._send_json(200, {"logs": logs})
                return

            if path == "/api/hitl/state":
                auth = self._authenticate(touch_login=False)
                if not auth:
                    return
                uid, tg_user, user_rec = auth
                if not self._require_approved(uid, tg_user, user_rec):
                    return
                is_dev = hooks["is_super_admin"](uid)
                perms = {k: True for k in hooks["PERMISSION_LABELS"]} if is_dev else hooks["get_user_permissions"](uid)
                qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                acc_id = (qs.get("acc_id") or qs.get("account_id") or [""])[0]
                if not self._authorize_hitl_acc(uid, tg_user, is_dev, perms, acc_id):
                    return
                st_hitl = hitl.get_hitl_state(acc_id)
                if not st_hitl:
                    self._send_json(200, {"ok": True, "running": False, "acc_id": acc_id})
                else:
                    self._send_json(200, {"ok": True, **st_hitl})
                return

            if path == "/api/accounts/list":
                auth = self._authenticate(touch_login=False)
                if not auth:
                    return
                uid, tg_user, user_rec = auth
                if not self._require_approved(uid, tg_user, user_rec):
                    return
                is_dev = hooks["is_super_admin"](uid)
                if not _check_http_rate_limit(uid, is_dev=is_dev):
                    self._send_json(429, {"error": "طلبات متتالية كثيرة؛ انتظر لحظة."})
                    return
                perms = {k: True for k in hooks["PERMISSION_LABELS"]} if is_dev else hooks["get_user_permissions"](uid)
                qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                kind = (qs.get("kind") or ["manageable"])[0].strip().lower()
                q_str = (qs.get("q") or [""])[0].strip().lower()
                try:
                    page_n = max(1, int((qs.get("page") or ["1"])[0]))
                except ValueError:
                    page_n = 1
                try:
                    limit_n = max(10, min(250, int((qs.get("limit") or ["100"])[0])))
                except ValueError:
                    limit_n = 100

                items: list[dict[str, Any]] = []
                if kind == "usable":
                    if is_dev or perms.get("can_use_accounts") or perms.get("can_execute"):
                        for a in hooks["get_usable_accounts_for_user"](uid):
                            items.append({
                                "id": a["id"],
                                "name": a.get("name", a["id"]),
                                "is_active": "نشط" in str(a.get("status", "")),
                            })
                else:
                    if is_dev or perms.get("can_add_accounts") or perms.get("can_delete_accounts"):
                        for a in hooks["get_manageable_accounts_for_user"](uid):
                            owner_lbl = f"{a.get('owner_name', '')} ({a.get('owner_id', '')})" if a.get("owner_id") else "حساب نظام"
                            items.append({
                                "id": a["id"],
                                "name": a.get("name", a["id"]),
                                "email": a.get("email", ""),
                                "is_active": "نشط" in str(a.get("status", "")),
                                "owner_label": owner_lbl,
                                "diagnostic_reason": a.get("diagnostic_reason", ""),
                            })

                if q_str:
                    items = [
                        it for it in items
                        if q_str in str(it.get("id", "")).lower()
                        or q_str in str(it.get("name", "")).lower()
                        or q_str in str(it.get("email", "")).lower()
                    ]
                total_cnt = len(items)
                pages_cnt = max(1, (total_cnt + limit_n - 1) // limit_n)
                page_n = min(page_n, pages_cnt)
                start_i = (page_n - 1) * limit_n
                self._send_json(200, {
                    "ok": True,
                    "kind": kind,
                    "page": page_n,
                    "limit": limit_n,
                    "total": total_cnt,
                    "pages": pages_cnt,
                    "items": items[start_i : start_i + limit_n],
                })
                return

            self._send_json(404, {"error": "المسار غير موجود"})

        def do_POST(self) -> None:
            path = urllib.parse.urlparse(self.path).path
            auth = self._authenticate(touch_login=False)
            if not auth:
                return
            uid, tg_user, user_rec = auth
            if not _check_http_rate_limit(uid, is_dev=hooks["is_super_admin"](uid)):
                self._send_json(429, {"error": "طلبات متتالية كثيرة؛ تمهل ثانية لحماية الخادم."})
                return
            user_label = str(tg_user.get("first_name") or user_rec.get("name") or uid)
            username = str(tg_user.get("username") or user_rec.get("username") or "")

            if path == "/api/referral/redeem":
                if user_rec.get("status") == "banned":
                    self._send_json(403, {"error": "حسابك محظور نهائياً ولا يمكن تفعيله بكود."})
                    return
                body, err = self._read_json_body()
                if err or body is None:
                    self._send_json(400, {"error": err or "طلب غير صالح"})
                    return
                code = str(body.get("code") or "").strip()
                res = eco.redeem_invite_code(uid, code, user_name=user_label, username=username)
                if not res.get("ok"):
                    self._send_json(400, {"error": res.get("error", "تعذر استخدام كود الدعوة.")})
                    return
                update_menu_button_for_user(hooks.get("bot"), uid, is_allowed=True)
                inv_id = res["inviter_id"]
                bonus_msg = f" وحصلت على +{res['instant_bonus']} نقاط!" if res.get("instant_bonus") else " (تضاف لك +4 نقاط فور تفعيل أول حساب نشط)"
                hooks["safe_send"](
                    inv_id,
                    f"🎟️ <b>انضم مستخدم جديد عبر إحالتك:</b> {html.escape(user_label, quote=True)} (<code>{uid}</code>){bonus_msg}"
                )
                self._send_json(200, {
                    "ok": True,
                    "message": "✅ تم تفعيل حسابك كمورّد حسابات فيسبوك بنجاح!",
                    "inviter_name": res.get("inviter_name", ""),
                })
                return

            if not self._require_approved(uid, tg_user, user_rec):
                return

            body, err = self._read_json_body()
            if err or body is None:
                self._send_json(400, {"error": err or "طلب غير صالح"})
                return

            is_dev = hooks["is_super_admin"](uid)
            perms = {k: True for k in hooks["PERMISSION_LABELS"]} if is_dev else hooks["get_user_permissions"](uid)

            if path == "/api/mission/launch":
                if not (is_dev or perms.get("can_execute")):
                    self._deny_perm(uid, tg_user, "محاولة إطلاق مهمة Mini App بدون صلاحية can_execute", "صلاحية تنفيذ المهام غير مفعلة لحسابك.")
                    return
                if not hooks["user_has_any_action_perm"](uid):
                    self._deny_perm(uid, tg_user, "محاولة إطلاق مهمة بدون أي أداة ميدانية مفعلة", "لا توجد أي أداة ميدانية مفعلة لحسابك.")
                    return

                perm_checks = [
                    ("like", "can_react", "التفاعلات والإعجاب"),
                    ("comment", "can_comment", "التعليقات"),
                    ("interact_cmt", "can_interact_comments", "التفاعل والرد على التعليقات"),
                    ("friend", "can_friend_follow", "الصداقة والمتابعة"),
                    ("cancel_friend", "can_friend_follow", "إلغاء الصداقة"),
                    ("follow", "can_friend_follow", "المتابعة"),
                    ("unfollow", "can_friend_follow", "إلغاء المتابعة"),
                    ("message", "can_message", "الرسائل الخاصة"),
                    ("report_post", "can_report", "البلاغات"),
                    ("report_profile", "can_report", "بلاغات الحسابات"),
                    ("block", "can_report", "الحظر"),
                ]
                active_selected = 0
                for field, p_key, p_title in perm_checks:
                    if bool(body.get(field)):
                        if not (is_dev or perms.get(p_key)):
                            self._deny_perm(uid, tg_user, f"محاولة تجاوز صلاحية {p_key} عبر Mini App", f"غير مصرح لك بميزة: {p_title}")
                            return
                        active_selected += 1

                if active_selected == 0:
                    self._send_json(400, {"error": "فعّل إجراءً واحداً على الأقل قبل بدء المهمة."})
                    return

                target_url = str(body.get("target_url") or "").strip()
                if not target_url:
                    target_url = str(body.get("react_post_url") or body.get("comment_post_url") or "").strip()
                if not target_url.startswith(("http://", "https://")):
                    self._send_json(400, {"error": "الرابط المستهدف يجب أن يبدأ بـ http:// أو https://"})
                    return

                usable = hooks["get_usable_accounts_for_user"](uid)
                if not usable:
                    self._send_json(400, {"error": "لا توجد أي حسابات مصرح لك بالتنفيذ منها حالياً."})
                    return

                selected_acc = str(body.get("selected_acc") or "all").strip()
                if selected_acc != "all" and not any(a["id"] == selected_acc for a in usable):
                    self._deny_perm(uid, tg_user, f"محاولة استخدام حساب خارج النطاق ({selected_acc})", "الحساب المحدد غير متاح ضمن صلاحياتك.")
                    return

                with _mission_launch_lock:
                    st = hooks["get_user_state"](uid)
                    if st.get("is_running"):
                        self._send_json(409, {"error": "توجد مهمة قيد التشغيل لحسابك حالياً، انتظر اكتمالها."})
                        return

                    st["is_running"] = False

                    def safe_int(val: Any, default: int, min_v: int, max_v: int) -> int:
                        try:
                            n = int(val)
                            return max(min_v, min(max_v, n))
                        except Exception:
                            return default

                    acc_limit_val = safe_int(body.get("acc_count_limit", 0), 0, 0, 500)
                    ff_ok = is_dev or perms.get("can_friend_follow")
                    rep_ok = is_dev or perms.get("can_report")
                    flags_for_billing = {
                        "like": bool(body.get("like")) and (is_dev or perms.get("can_react")),
                        "comment": bool(body.get("comment")) and (is_dev or perms.get("can_comment")),
                        "interact_cmt": bool(body.get("interact_cmt")) and (is_dev or perms.get("can_interact_comments")),
                        "friend": bool(body.get("friend")) and ff_ok,
                        "cancel_friend": bool(body.get("cancel_friend")) and ff_ok and not bool(body.get("friend")),
                        "follow": bool(body.get("follow")) and ff_ok,
                        "unfollow": bool(body.get("unfollow")) and ff_ok and not bool(body.get("follow")),
                        "message": bool(body.get("message")) and (is_dev or perms.get("can_message")),
                        "report_post": bool(body.get("report_post")) and rep_ok,
                        "report_profile": bool(body.get("report_profile")) and rep_ok and not bool(body.get("report_post")),
                        "block": bool(body.get("block")) and rep_ok,
                    }
                    acc_est = eco.estimate_mission_account_count(
                        usable, {"selected_acc": selected_acc, "acc_count_limit": acc_limit_val}
                    )
                    debit_res = eco.debit_points_for_mission(uid, flags_for_billing, acc_est, target_url)
                    if not debit_res.get("ok"):
                        req_pts = debit_res.get("required", 0)
                        bal_pts = debit_res.get("balance", 0)
                        self._send_json(402, {
                            "error": f"رصيد نقاطك ({bal_pts} نقطة) لا يكفي لتنفيذ هذه العملية ({req_pts} نقطة). أضف حسابات نشطة (+1) أو ادعُ أصدقاء (+4) أو اشحن من المطور.",
                            "required_points": req_pts,
                            "balance": bal_pts,
                        })
                        return

                    st["target_url"] = target_url[:1000]
                    st["selected_acc"] = selected_acc
                    st["acc_count_limit"] = acc_limit_val

                    st["like"] = flags_for_billing["like"]
                    rtype = str(body.get("reaction_type") or "like")
                    st["reaction_type"] = rtype if rtype in VALID_REACTIONS else "like"
                    st["react_post_index"] = safe_int(body.get("react_post_index", 1), 1, 1, 50)
                    rurl = str(body.get("react_post_url") or "").strip()
                    st["react_post_url"] = rurl[:1000] if rurl.startswith(("http://", "https://")) else ""

                    st["comment"] = flags_for_billing["comment"]
                    st["comment_text"] = str(body.get("comment_text") or "").strip()[:2000]
                    st["comment_post_index"] = safe_int(body.get("comment_post_index", 1), 1, 1, 50)
                    curl = str(body.get("comment_post_url") or "").strip()
                    st["comment_post_url"] = curl[:1000] if curl.startswith(("http://", "https://")) else ""

                    st["interact_cmt"] = flags_for_billing["interact_cmt"]
                    cmode = str(body.get("cmt_target_mode") or "first")
                    st["cmt_target_mode"] = cmode if cmode in VALID_CMT_MODES else "first"
                    st["cmt_target_val"] = str(body.get("cmt_target_val") or "").strip()[:300]
                    creact = str(body.get("cmt_reaction") or "like")
                    st["cmt_reaction"] = creact if creact in VALID_CMT_REACTIONS else "like"
                    st["cmt_reply"] = str(body.get("cmt_reply") or "").strip()[:2000]

                    st["friend"] = flags_for_billing["friend"]
                    st["cancel_friend"] = flags_for_billing["cancel_friend"]
                    st["follow"] = flags_for_billing["follow"]
                    st["unfollow"] = flags_for_billing["unfollow"]

                    st["message"] = flags_for_billing["message"]
                    st["message_text"] = str(body.get("message_text") or "").strip()[:2000]

                    st["report_post"] = flags_for_billing["report_post"]
                    st["report_profile"] = flags_for_billing["report_profile"]
                    st["block"] = flags_for_billing["block"]
                    r_reason = str(body.get("rep_reason") or "harassment")
                    st["rep_reason"] = r_reason if r_reason in VALID_REP_REASONS else "harassment"
                    r_victim = str(body.get("rep_victim") or "me")
                    st["rep_victim"] = r_victim if r_victim in VALID_REP_VICTIMS else "me"

                    st["is_running"] = True
                    st["live_status_text"] = "تم إطلاق المهمة من لوحة التحكم الداخلية..."

                if callable(hooks.get("persist_user_states")):
                    hooks["persist_user_states"]()
                hooks["record_user_operation"](uid, "تشغيل مهمة ميدانية (Mini App)")
                hooks["record_audit_log"](uid, user_label, "LAUNCH_MISSION_WEBAPP", f"الهدف: {target_url[:80]} | تكلفة: {debit_res.get('cost', 0)} نقطة")
                publish_event("mission", uid, "launch")
                threading.Thread(target=hooks["execute_mission_worker"], args=(uid, uid), daemon=True).start()
                self._send_json(200, {
                    "ok": True,
                    "cost": debit_res.get("cost", 0),
                    "remaining_points": debit_res.get("balance", 0),
                    "message": "تم بدء تنفيذ المهمة في الخلفية! راقب التقدم هنا أو في الدردشة.",
                })
                return

            if path == "/api/accounts/add":
                if not (is_dev or perms.get("can_add_accounts")):
                    self._deny_perm(uid, tg_user, "محاولة إضافة حساب عبر Mini App بدون صلاحية can_add_accounts", "صلاحية إضافة الحسابات غير مفعلة لحسابك.")
                    return

                name = str(body.get("name") or "").strip()[:80]
                email = str(body.get("email") or "").strip()[:160]
                password = str(body.get("password") or "").strip()[:160]
                if not name or not email or not password:
                    self._send_json(400, {"error": "أدخل اسم الحساب والبريد الإلكتروني وكلمة المرور بالكامل."})
                    return

                res_acc = hooks["add_account"](
                    name, email, password,
                    owner_id=uid,
                    owner_name=user_label
                )
                if not isinstance(res_acc, dict) or res_acc.get("error"):
                    err_msg = (
                        res_acc.get("message", "هذا الحساب مسجل مسبقاً في النظام.")
                        if isinstance(res_acc, dict)
                        else "تعذر حفظ بيانات الحساب."
                    )
                    hooks["record_audit_log"](uid, user_label, "ADD_ACCOUNT_DUPLICATE", f"رفض إضافة حساب مكرر: {email}")
                    self._send_json(400, {"error": err_msg})
                    return

                hooks["record_audit_log"](uid, user_label, "ADD_ACCOUNT_QUEUED", f"إضافة الحساب ({res_acc['id']}) من Mini App للفحص")
                threading.Thread(
                    target=hooks["async_login_account_worker"],
                    args=(uid, None, res_acc, uid, user_label, username),
                    daemon=True
                ).start()
                self._send_json(200, {"ok": True, "message": f"تم استلام الحساب ({res_acc['name']}) وبدأ الفحص التلقائي بالمتصفح الخلفي!"})
                return

            if path == "/api/accounts/delete":
                if not (is_dev or perms.get("can_delete_accounts")):
                    self._deny_perm(uid, tg_user, "محاولة حذف حساب عبر Mini App بدون صلاحية can_delete_accounts", "صلاحية حذف الحسابات غير مفعلة لحسابك.")
                    return

                acc_id = str(body.get("account_id") or "").strip()
                if not acc_id:
                    self._send_json(400, {"error": "معرف الحساب مطلوب."})
                    return

                acc = hooks["get_account_by_id"](acc_id)
                if not acc:
                    self._send_json(404, {"error": "الحساب غير موجود."})
                    return

                if not is_dev and acc.get("owner_id") != uid:
                    self._deny_perm(uid, tg_user, f"محاولة IDOR حذف حساب لا يملكه ({acc_id})", "لا يمكنك حذف حساب لم تقم أنت بإضافته.")
                    return

                ok = hooks["delete_account"](acc_id)
                if not ok:
                    self._send_json(400, {"error": "تعذر حذف الحساب أو غير موجود."})
                    return
                hooks["record_audit_log"](uid, user_label, "DELETE_ACCOUNT", f"حذف الحساب {acc_id} من Mini App")
                self._send_json(200, {"ok": True, "message": f"تم حذف الحساب {acc_id} بنجاح."})
                return

            if path == "/api/accounts/purge":
                if not (is_dev or perms.get("can_delete_accounts")):
                    self._deny_perm(uid, tg_user, "محاولة تنظيف الحسابات التالفة بدون صلاحية can_delete_accounts")
                    return
                removed, _removed_names = hooks["purge_broken_accounts"](owner_id=None if is_dev else uid)
                hooks["record_audit_log"](uid, user_label, "PURGE_BROKEN_ACCOUNTS", f"تم تنظيف {removed} حساب عبر Mini App")
                self._send_json(200, {"ok": True, "message": f"تم تنظيف وحذف {removed} حساب تالف في نطاقك."})
                return

            if path == "/api/accounts/check":
                if not (is_dev or perms.get("can_add_accounts") or perms.get("can_use_accounts")):
                    self._deny_perm(uid, tg_user, "محاولة فحص الجلسات عبر Mini App بدون صلاحية")
                    return
                hooks["record_audit_log"](uid, user_label, "CHECK_SESSIONS", "تشغيل فحص الجلسات من Mini App")
                threading.Thread(target=hooks["check_all_sessions_worker"], args=(uid, uid), daemon=True).start()
                self._send_json(200, {"ok": True, "message": "بدأ فحص حالة الجلسات في المتصفح الخلفي!"})
                return

            if path == "/api/admin/user/perm":
                if not is_dev:
                    self._deny_perm(uid, tg_user, "محاولة تعديل صلاحيات مستخدم عبر API من غير المطور")
                    return
                try:
                    target_id = int(body.get("target_id"))
                except Exception:
                    self._send_json(400, {"error": "معرف المستخدم غير صالح."})
                    return

                if hooks["is_super_admin"](target_id):
                    self._send_json(403, {"error": "محظور برمجياً تعديل صلاحيات المطور الرئيسي."})
                    return

                perm_key = str(body.get("permission") or "").strip()
                if perm_key not in hooks["PERMISSION_LABELS"]:
                    self._send_json(400, {"error": "اسم الصلاحية غير معروف."})
                    return

                new_val = hooks["toggle_user_permission"](target_id, perm_key)
                hooks["record_audit_log"](uid, user_label, "ADMIN_PERM_TOGGLE", f"تغيير {perm_key} للمستخدم {target_id} إلى {new_val}")
                self._send_json(200, {"ok": True, "value": new_val})
                return

            if path == "/api/admin/user/action":
                if not is_dev:
                    self._deny_perm(uid, tg_user, "محاولة تنفيذ قرار إداري على مستخدم من غير المطور")
                    return
                try:
                    target_id = int(body.get("target_id"))
                except Exception:
                    self._send_json(400, {"error": "معرف المستخدم غير صالح."})
                    return

                if hooks["is_super_admin"](target_id):
                    self._send_json(403, {"error": "المطور الرئيسي محصن برمجياً ضد الحظر أو الحذف."})
                    return

                users_map = hooks["load_users"]()
                if str(target_id) not in users_map:
                    self._send_json(404, {"error": "المستخدم غير موجود."})
                    return

                act = str(body.get("action") or "").strip()
                bot_inst = hooks.get("bot")

                if act == "approve":
                    hooks["approve_user"](target_id)
                    hooks["record_audit_log"](uid, user_label, "USER_APPROVE", f"اعتماد المستخدم {target_id} عبر Mini App (صلاحيات مقفلة افتراضياً)")
                    update_menu_button_for_user(bot_inst, target_id, is_allowed=True)
                    hooks["safe_send"](
                        target_id,
                        "🎉 <b>تمت الموافقة المبدئية على حسابك من قبل المطور الرئيسي.</b>\n"
                        "🔒 بانتظار فتح الأدوات المخصصة لك، أو افتح زر (لوحة التحكم) بالأسفل."
                    )
                    self._send_json(200, {"ok": True, "message": "تم اعتماد المستخدم (جميع الأدوات مقفلة افتراضياً)."})
                    return

                if act == "ban":
                    hooks["ban_user"](target_id)
                    hooks["record_audit_log"](uid, user_label, "USER_BAN", f"حظر المستخدم {target_id} عبر Mini App")
                    update_menu_button_for_user(bot_inst, target_id, is_allowed=False)
                    self._send_json(200, {"ok": True, "message": "تم حظر المستخدم وتصفير صلاحياته فوراً."})
                    return

                if act == "unban":
                    hooks["unban_user"](target_id)
                    hooks["record_audit_log"](uid, user_label, "USER_UNBAN", f"فك حظر المستخدم {target_id} عبر Mini App")
                    update_menu_button_for_user(bot_inst, target_id, is_allowed=True)
                    self._send_json(200, {"ok": True, "message": "تم فك الحظر (جميع الصلاحيات مقفلة للأمان)."})
                    return

                if act == "revoke_all":
                    hooks["revoke_all_permissions"](target_id)
                    hooks["record_audit_log"](uid, user_label, "ADMIN_REVOKE_ALL", f"تصفير صلاحيات المستخدم {target_id} عبر Mini App")
                    self._send_json(200, {"ok": True, "message": "تم إقفال كافة الصلاحيات لهذا المستخدم."})
                    return

                if act == "delete":
                    acc_del = hooks["delete_accounts_by_owner"](target_id)
                    hooks["delete_user_and_data"](target_id)
                    hooks["record_audit_log"](uid, user_label, "USER_DELETE", f"حذف المستخدم {target_id} ومسح {acc_del} حساب عبر Mini App")
                    update_menu_button_for_user(bot_inst, target_id, is_allowed=False)
                    self._send_json(200, {"ok": True, "message": f"تم حذف المستخدم ومسح {acc_del} حساب."})
                    return

                self._send_json(400, {"error": "إجراء غير معروف."})
                return

            if path == "/api/referral/create_code":
                if not eco.can_user_invite(uid):
                    self._deny_perm(uid, tg_user, "محاولة توليد كود إحالة بدون صلاحية")
                    return
                label = str(body.get("label") or "").strip()[:60]
                res = eco.create_invite_code(uid, max_uses=1, label=label)
                if not res.get("ok"):
                    self._send_json(400, {"error": res.get("error", "تعذر إنشاء كود الدعوة.")})
                    return
                bot_uname = str((hooks.get("get_bot_username") and hooks["get_bot_username"]()) or hooks.get("bot_username") or "")
                inv = res["invite"]
                link = f"https://t.me/{bot_uname}?start=ref_{inv['code']}" if bot_uname else ""
                self._send_json(200, {"ok": True, "invite": inv, "invite_link": link})
                return

            if path == "/api/referral/revoke_code":
                code = str(body.get("code") or "").strip()
                if not code:
                    self._send_json(400, {"error": "كود الإحالة مطلوب."})
                    return
                if not eco.revoke_invite_code(uid, code, is_dev=is_dev):
                    self._send_json(403, {"error": "الكود غير موجود أو لا يخصك."})
                    return
                self._send_json(200, {"ok": True, "message": "تم إلغاء كود الدعوة بنجاح."})
                return

            if path == "/api/support/create":
                kind = str(body.get("kind") or "support").strip()
                msg_txt = str(body.get("message") or "").strip()
                res = eco.create_support_ticket(uid, kind, msg_txt)
                if not res.get("ok"):
                    self._send_json(400, {"error": res.get("error", "تعذر إرسال التذكرة.")})
                    return
                tkt = res["ticket"]
                snap = tkt["snapshot"]
                super_id = int(hooks["SUPER_ADMIN_ID"])
                u_tag = f"@{html.escape(username, quote=True)}" if username else "بدون معرف"
                title = "💵 طلب موافقة على بيع الحسابات والمحاسبة" if tkt["kind"] == "sell_accounts" else "💬 رسالة جديدة للدعم والمطور"
                mk = types.InlineKeyboardMarkup(row_width=1)
                mk.add(types.InlineKeyboardButton("↩️ الرد على المستخدم", callback_data=f"tkt_reply_{tkt['id']}"))
                if snap["points"] > 0:
                    mk.add(types.InlineKeyboardButton(
                        f"💸 تسوية كامل الرصيد ({snap['points']} نقطة = {snap['yer_value']:,} ريال)",
                        callback_data=f"tkt_settle_{tkt['id']}"
                    ))
                mk.add(types.InlineKeyboardButton("🛰️ فتح بطاقة المستخدم بالرادار", callback_data=f"surv_user_{uid}"))
                hooks["safe_send"](
                    super_id,
                    f"📬 <b>{title}</b>\n"
                    "━━━━━━━━━━━━━━━━━━━━\n"
                    f"🎫 <b>رقم التذكرة:</b> <code>{tkt['id']}</code>\n"
                    f"👤 <b>المستخدم:</b> {html.escape(snap['name'], quote=True)} ({u_tag})\n"
                    f"🆔 <b>الآيدي:</b> <code>{uid}</code>\n"
                    f"📊 <b>الحسابات المضافة:</b> {snap['total_added']} (🟢 {snap['active_added']} نشط | 🔴 {snap['inactive_added']} غير نشط)\n"
                    f"💰 <b>رصيد النقاط:</b> {snap['points']} نقطة = <b>{snap['yer_value']:,} ريال يمني</b>\n"
                    f"🧾 <b>تمت محاسبته سابقاً:</b> {snap['total_yer_settled']:,} ريال يمني\n"
                    "━━━━━━━━━━━━━━━━━━━━\n"
                    f"📝 <b>رسالته:</b>\n{html.escape(msg_txt, quote=True)}",
                    reply_markup=mk,
                )
                self._send_json(200, {"ok": True, "ticket": tkt, "message": "✅ تم إرسال رسالتك إلى المطور مع كامل تفاصيل حساباتك ونقاطك!"})
                return

            if path == "/api/support/reply":
                ticket_id = str(body.get("ticket_id") or "").strip()
                msg_txt = str(body.get("message") or "").strip()
                if not ticket_id:
                    self._send_json(400, {"error": "رقم التذكرة مطلوب."})
                    return
                res = eco.reply_support_ticket(ticket_id, uid, msg_txt, is_dev=is_dev)
                if not res.get("ok"):
                    code_http = 403 if res.get("error") == "forbidden" else 400
                    self._send_json(code_http, {"error": "لا يمكنك الرد على هذه التذكرة." if code_http == 403 else res.get("error", "خطأ.")})
                    return
                tkt = res["ticket"]
                snap = tkt.get("snapshot", {})
                if is_dev:
                    mk_u = types.InlineKeyboardMarkup(row_width=1)
                    mk_u.add(types.InlineKeyboardButton("↩️ الرد على المطور / الدعم", callback_data=f"user_reply_tkt_{tkt['id']}"))
                    hooks["safe_send"](
                        tkt["user_id"],
                        f"📩 <b>رد جديد من المطور / الدعم</b> (<code>{tkt['id']}</code>)\n"
                        "━━━━━━━━━━━━━━━━━━━━\n"
                        f"💬 {html.escape(msg_txt, quote=True)}\n"
                        "━━━━━━━━━━━━━━━━━━━━\n"
                        f"💰 <b>رصيدك الحالي:</b> {snap.get('points', 0)} نقطة ({snap.get('yer_value', 0):,} ريال)",
                        reply_markup=mk_u,
                    )
                else:
                    super_id = int(hooks["SUPER_ADMIN_ID"])
                    mk_d = types.InlineKeyboardMarkup(row_width=1)
                    mk_d.add(types.InlineKeyboardButton("↩️ الرد على المستخدم", callback_data=f"tkt_reply_{tkt['id']}"))
                    if snap.get("points", 0) > 0:
                        mk_d.add(types.InlineKeyboardButton(
                            f"💸 تسوية الرصيد ({snap['points']} نقطة = {snap['yer_value']:,} ريال)",
                            callback_data=f"tkt_settle_{tkt['id']}"
                        ))
                    hooks["safe_send"](
                        super_id,
                        f"💬 <b>رد جديد من المستخدم</b> {html.escape(user_label, quote=True)} (<code>{uid}</code>)\n"
                        f"🎫 <b>تذكرة:</b> <code>{tkt['id']}</code> | 💰 <b>الرصيد:</b> {snap.get('points', 0)} نقطة ({snap.get('yer_value', 0):,} ريال)\n"
                        f"📝 {html.escape(msg_txt, quote=True)}",
                        reply_markup=mk_d,
                    )
                self._send_json(200, {"ok": True, "ticket": tkt, "message": "✅ تم إرسال الرد بنجاح."})
                return

            if path == "/api/admin/points":
                if not is_dev:
                    self._deny_perm(uid, tg_user, "محاولة التلاعب بالنقاط من غير المطور الرئيسي")
                    return
                try:
                    target_id = int(body.get("target_id"))
                except Exception:
                    self._send_json(400, {"error": "معرف المستخدم غير صالح."})
                    return

                act = str(body.get("action") or "").strip()
                reason = str(body.get("reason") or "تعديل يدوي من المطور").strip()[:240]
                ticket_id = str(body.get("ticket_id") or "").strip() or None

                if act == "settle":
                    raw_amt = body.get("amount")
                    amt = None if (raw_amt is None or str(raw_amt).lower() == "all") else None
                    if raw_amt not in (None, "", "all"):
                        try:
                            amt = adm.safe_nonneg_points(float(raw_amt))
                        except Exception:
                            self._send_json(400, {"error": "قيمة النقاط للتصفية غير صالحة."})
                            return
                    s_res = eco.settle_payout(target_id, amt, actor_uid=uid, ticket_id=ticket_id, note=reason)
                    if not s_res.get("ok"):
                        self._send_json(400, {"error": s_res.get("error", "تعذرت التسوية.")})
                        return
                    hooks["safe_send"](
                        target_id,
                        f"🧾 <b>إشعار محاسبة وصرف أرباح</b>\n"
                        f"✅ تم اعتماد تسوية <b>{s_res['points_settled']} نقطة</b> بمبلغ <b>{s_res['yer_paid']:,} ريال يمني</b>.\n"
                        f"💰 <b>الرصيد المتبقي:</b> {s_res['remaining_points']} نقطة ({s_res['remaining_yer']:,} ريال)"
                    )
                    self._send_json(200, {"ok": True, "message": f"✅ تمت تسوية {s_res['points_settled']} نقطة ({s_res['yer_paid']:,} ريال يمني).", **s_res})
                    return

                try:
                    amount = adm.safe_nonneg_points(float(body.get("amount")))
                except Exception:
                    self._send_json(400, {"error": "أدخل عدداً صالحاً من النقاط."})
                    return
                if amount <= 0:
                    self._send_json(400, {"error": "عدد النقاط يجب أن يكون أكبر من الصفر."})
                    return

                if act == "add":
                    adj = eco.adjust_user_points(target_id, amount, "ADMIN_GRANT", reason, actor_uid=uid)
                    msg_u = f"➕ <b>تمت إضافة +{amount} نقطة إلى محفظتك من المطور!</b>\n💰 رصيدك الجديد: {adj.get('balance', 0)} نقطة ({adj.get('yer_value', 0):,} ريال يمني)"
                elif act == "deduct":
                    adj = eco.adjust_user_points(target_id, -amount, "ADMIN_DEDUCT", reason, actor_uid=uid, allow_partial_zero=True)
                    msg_u = f"➖ <b>تم خصم {abs(adj.get('delta', amount))} نقطة من محفظتك.</b>\n📝 السبب: {html.escape(reason, quote=True)}\n💰 رصيدك الحالي: {adj.get('balance', 0)} نقطة"
                else:
                    self._send_json(400, {"error": "إجراء نقاط غير معروف."})
                    return

                if not adj.get("ok"):
                    self._send_json(400, {"error": adj.get("error", "تعذر تعديل النقاط.")})
                    return
                hooks["safe_send"](target_id, msg_u)
                self._send_json(200, {"ok": True, "balance": adj["balance"], "yer_value": adj["yer_value"], "message": "✅ تم تحديث محفظة النقاط بنجاح."})
                return

            if path == "/api/admin/economy":
                if not is_dev:
                    self._deny_perm(uid, tg_user, "محاولة تعديل تسعيرة النقاط والوضع العام من غير المطور")
                    return
                updated = eco.update_economy_settings(body, actor_uid=uid)
                self._send_json(200, {"ok": True, "economy_settings": updated, "message": "✅ تم حفظ إعدادات النقاط والتسعيرة والوضع العام بنجاح."})
                return

            if path == "/api/hitl/start":
                acc_id = str(body.get("account_id") or body.get("acc_id") or "").strip()
                if not self._authorize_hitl_acc(uid, tg_user, is_dev, perms, acc_id):
                    return
                req_mode = str(body.get("mode") or "").strip().lower()
                if req_mode:
                    try:
                        res_h = hitl.start_hitl_session(acc_id, actor_uid=uid, mode=req_mode)
                    except TypeError:
                        res_h = hitl.start_hitl_session(acc_id, actor_uid=uid)
                else:
                    res_h = hitl.start_hitl_session(acc_id, actor_uid=uid)
                if not res_h.get("ok"):
                    self._send_json(400, {"error": res_h.get("error", "تعذر فتح الشاشة الحية.")})
                    return
                hooks["record_audit_log"](uid, user_label, "HITL_SESSION_OPENED", f"فتح الشاشة الحية لحل تحقق الحساب ({acc_id})")
                self._send_json(200, res_h)
                return

            if path == "/api/hitl/input":
                acc_id = str(body.get("account_id") or body.get("acc_id") or "").strip()
                if not self._authorize_hitl_acc(uid, tg_user, is_dev, perms, acc_id):
                    return
                res_in = hitl.send_hitl_input(acc_id, body)
                if not res_in.get("ok"):
                    self._send_json(400, {"error": res_in.get("error", "تعذر إرسال التفاعل للشاشة الحية."), **res_in})
                    return
                self._send_json(200, res_in)
                return

            if path == "/api/hitl/stop":
                acc_id = str(body.get("account_id") or body.get("acc_id") or "").strip()
                if not self._authorize_hitl_acc(uid, tg_user, is_dev, perms, acc_id):
                    return
                hitl.stop_hitl_session(acc_id)
                self._send_json(200, {"ok": True, "running": False, "acc_id": acc_id})
                return

            self._send_json(404, {"error": "المسار غير موجود"})

    return MiniAppHandler


def start_webapp_and_tunnel(bot_token: str, hooks: dict[str, Any], port: int | None = None) -> ThreadingHTTPServer | None:
    """تشغيل خادم لوحة التحكم المصغرة متعدد الخيوط + تفعيل نفق HTTPS + تحديث زر القائمة داخل تلغرام."""
    listen_port = port if port is not None else int(os.environ.get("PORT", 7860))
    handler_cls = make_miniapp_handler(bot_token, hooks)
    try:
        server = ThreadingHTTPServer(("0.0.0.0", listen_port), handler_cls)
    except Exception as e:
        print(f"[WebApp] تعذر بدء الخادم على المنفذ {listen_port}: {e}")
        return None

    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"[WebApp] خادم لوحة التحكم المصغرة يعمل على المنفذ {listen_port}")

    def on_tunnel_ready(public_url: str) -> None:
        bot_inst = hooks.get("bot")
        super_id = hooks.get("SUPER_ADMIN_ID")
        update_menu_button_for_user(bot_inst, None, is_allowed=True)
        if super_id:
            update_menu_button_for_user(bot_inst, int(super_id), is_allowed=True)

    start_public_tunnel_discovery(listen_port, on_url_ready=on_tunnel_ready)
    return server
