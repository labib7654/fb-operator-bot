"""
محرك الشاشة الحية التفاعلية لحل التحقق البشري يدوياً (Interactive Human-in-the-Loop Live View)
يعرض شاشة المتصفح الحية للمستخدم المصرح فقط داخل لوحة Mini App ويتيح له النقر والكتابة وإرسال رمز 2FA بنفسه.
سياسة صارمة: لا يحل أي CAPTCHA آلياً — يقتصر على بث الشاشة وتمرير نقرات الإنسان الحقيقي على خيط واحد مالك للمتصفح (Single-Thread Owner).
"""

from __future__ import annotations

import base64
import queue
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

import fb_operator.account_manager as acc_mgr
from fb_operator.browser_manager import (
    sync_playwright,
    auto_login_facebook,
    check_facebook_login_cookies,
    diagnose_facebook_challenge,
    dismiss_dialogs,
    get_profile_lock,
    launch_account_browser,
    save_account_storage_state,
)

HITL_VIEWPORT = (1280, 800)
HITL_DESKTOP_VIEWPORT = (1280, 800)
HITL_MOBILE_VIEWPORT = (430, 780)
HITL_INACTIVITY_TTL_SEC = 180.0
HITL_MAX_TTL_SEC = 300.0
MAX_CONCURRENT_HITL = 2

ALLOWED_KEYS = frozenset({
    "Enter",
    "Backspace",
    "Tab",
    "Escape",
    "ArrowUp",
    "ArrowDown",
    "ArrowLeft",
    "ArrowRight",
    "Space",
})

_hitl_lock = threading.RLock()
_sessions: dict[str, "HITLSession"] = {}
_on_verified_callback: Callable[[str, str, int], None] | None = None


def register_hitl_verified_callback(cb: Callable[[str, str, int], None]) -> None:
    """تسجيل دالة تُستدعى عند نجاح الإنسان في إتمام التحقق وتثبيت الجلسة (acc_id, fb_id, actor_uid)"""
    global _on_verified_callback
    _on_verified_callback = cb


@dataclass
class HITLSession:
    acc_id: str
    acc_name: str
    owner_uid: int
    started_by: int
    cmd_queue: queue.Queue = field(default_factory=queue.Queue)
    state_lock: threading.Lock = field(default_factory=threading.Lock)
    created_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)
    running: bool = True
    ready: bool = False
    completed: bool = False
    fb_id: str = ""
    challenge_code: str = "starting"
    challenge_message: str = "جاري تشغيل متصفح الحساب وفتح فيسبوك..."
    page_url: str = ""
    can_otp: bool = False
    has_credentials: bool = False
    error: str = ""
    frame_b64: str = ""
    frame_seq: int = 0
    mode: str = "mobile"
    viewport: tuple[int, int] = HITL_MOBILE_VIEWPORT
    _stop_event: threading.Event = field(default_factory=threading.Event)

    def touch(self) -> None:
        self.last_activity = time.time()

    def snapshot_dict(self) -> dict[str, Any]:
        with self.state_lock:
            return {
                "acc_id": self.acc_id,
                "acc_name": self.acc_name,
                "running": self.running,
                "ready": self.ready,
                "completed": self.completed,
                "fb_id": self.fb_id,
                "challenge_code": self.challenge_code,
                "challenge_message": self.challenge_message,
                "page_url": self.page_url,
                "can_otp": self.can_otp,
                "has_credentials": self.has_credentials,
                "error": self.error,
                "frame_b64": self.frame_b64,
                "frame_seq": self.frame_seq,
                "mode": self.mode,
                "viewport": {"width": int(self.viewport[0]), "height": int(self.viewport[1])},
                "ttl_remaining": max(0, int(HITL_MAX_TTL_SEC - (time.time() - self.created_at))),
            }


def _safe_capture_jpeg_b64(page) -> str:
    try:
        raw = page.screenshot(type="jpeg", quality=85)
        return "data:image/jpeg;base64," + base64.b64encode(raw).decode("ascii")
    except Exception:
        return ""


def _hitl_worker(session: HITLSession, acc: dict) -> None:
    """الخيط الوحيد المالك لـ Playwright لهذه الجلسة (يمنع greenlet cross-thread error نهائياً)."""
    acc_id = session.acc_id
    lock = get_profile_lock(acc_id)
    email = str(acc.get("email") or "").strip()
    raw_pass = str(acc.get("password") or "")
    real_pass = "" if raw_pass in ("", "[SESSION_COOKIES]") else raw_pass
    session.has_credentials = bool(email and real_pass)

    try:
        with lock:
            with sync_playwright() as p:
                ctx = launch_account_browser(
                    p,
                    acc["profile_dir"],
                    visible=False,
                    viewport_size=session.viewport,
                    mobile=(session.mode == "mobile"),
                    proxy=acc.get("proxy"),
                )
                try:
                    page = ctx.pages[0] if ctx.pages else ctx.new_page()
                    page.goto("https://www.facebook.com/", wait_until="domcontentloaded", timeout=45000)
                    time.sleep(1.5)
                    dismiss_dialogs(page)

                    def _refresh_state() -> bool:
                        diag = diagnose_facebook_challenge(page)
                        is_logged, fb_id = check_facebook_login_cookies(ctx)
                        frame = _safe_capture_jpeg_b64(page)
                        curr_url = ""
                        try:
                            curr_url = str(page.url or "")[:180]
                        except Exception:
                            pass

                        with session.state_lock:
                            session.ready = True
                            if frame:
                                session.frame_b64 = frame
                                session.frame_seq += 1
                            session.page_url = curr_url
                            session.challenge_code = str(diag.get("code") or "unknown")
                            session.challenge_message = str(diag.get("message") or "")
                            session.can_otp = bool(diag.get("can_otp"))

                            if is_logged and diag.get("is_ok"):
                                session.completed = True
                                session.fb_id = fb_id
                                session.challenge_code = "ok"
                                session.challenge_message = "تم تسجيل الدخول وتثبيت الجلسة بنجاح!"
                                return True
                        return False

                    if _refresh_state():
                        save_account_storage_state(ctx, acc["profile_dir"])
                        if _on_verified_callback:
                            _on_verified_callback(acc_id, session.fb_id, session.started_by)
                        time.sleep(2.0)
                        return

                    last_capture = time.time()
                    while not session._stop_event.is_set():
                        now = time.time()
                        if (now - session.created_at) >= HITL_MAX_TTL_SEC:
                            with session.state_lock:
                                session.error = "انتهى الحد الأقصى لجلسة الشاشة الحية (5 دقائق)."
                            break
                        if (now - session.last_activity) >= HITL_INACTIVITY_TTL_SEC:
                            with session.state_lock:
                                session.error = "أُغلقت الشاشة الحية تلقائياً لعدم التفاعل (3 دقائق)."
                            break
                        if len(ctx.pages) == 0:
                            break

                        processed_cmd = False
                        try:
                            cmd_obj = session.cmd_queue.get(timeout=0.35)
                        except queue.Empty:
                            cmd_obj = None

                        if cmd_obj is not None:
                            processed_cmd = True
                            session.touch()
                            ev = cmd_obj.get("event")
                            ctype = cmd_obj.get("cmd")
                            did_complete = False
                            try:
                                if ctype == "close":
                                    session._stop_event.set()
                                    if ev:
                                        ev.set()
                                    break
                                elif ctype == "click":
                                    vw, vh = session.viewport
                                    x = max(1.0, min(float(vw - 1), float(cmd_obj.get("x") or 0)))
                                    y = max(1.0, min(float(vh - 1), float(cmd_obj.get("y") or 0)))
                                    if session.mode == "mobile":
                                        try:
                                            page.touchscreen.tap(x, y)
                                        except Exception:
                                            page.mouse.click(x, y)
                                    else:
                                        page.mouse.click(x, y)
                                    time.sleep(0.45)
                                elif ctype == "set_mode":
                                    new_mode = "desktop" if str(cmd_obj.get("mode") or "") == "desktop" else "mobile"
                                    new_vp = HITL_DESKTOP_VIEWPORT if new_mode == "desktop" else HITL_MOBILE_VIEWPORT
                                    with session.state_lock:
                                        session.mode = new_mode
                                        session.viewport = new_vp
                                    page.set_viewport_size({"width": new_vp[0], "height": new_vp[1]})
                                    time.sleep(0.5)
                                elif ctype == "type":
                                    txt = str(cmd_obj.get("text") or "")[:300]
                                    if txt:
                                        page.keyboard.insert_text(txt)
                                        if cmd_obj.get("submit"):
                                            time.sleep(0.25)
                                            page.keyboard.press("Enter")
                                        time.sleep(0.5)
                                elif ctype == "otp":
                                    code = str(cmd_obj.get("code") or "").strip()[:24]
                                    if code:
                                        otp_filled = False
                                        for sel in ('input[name="approvals_code"]', 'input#approvals_code', 'input[autocomplete="one-time-code"]', 'input[type="tel"]', 'input[type="text"]'):
                                            try:
                                                loc = page.locator(sel).first
                                                if loc.is_visible(timeout=500):
                                                    loc.click()
                                                    loc.fill("")
                                                    loc.press_sequentially(code, delay=75)
                                                    otp_filled = True
                                                    break
                                            except Exception:
                                                pass
                                        if not otp_filled:
                                            page.keyboard.insert_text(code)
                                        time.sleep(0.3)
                                        clicked_sub = False
                                        for sub_sel in ('button[type="submit"]', 'button:has-text("متابعة")', 'button:has-text("Continue")', 'div[role="button"]:has-text("متابعة")', 'div[role="button"]:has-text("Continue")'):
                                            try:
                                                sloc = page.locator(sub_sel).first
                                                if sloc.is_visible(timeout=500):
                                                    sloc.click()
                                                    clicked_sub = True
                                                    break
                                            except Exception:
                                                pass
                                        if not clicked_sub:
                                            page.keyboard.press("Enter")
                                        time.sleep(1.5)
                                elif ctype == "key":
                                    k = str(cmd_obj.get("key") or "")
                                    if k in ALLOWED_KEYS:
                                        page.keyboard.press(k)
                                        time.sleep(0.4)
                                elif ctype == "scroll":
                                    dy = max(-900, min(900, int(cmd_obj.get("dy") or 300)))
                                    page.mouse.wheel(0, dy)
                                    time.sleep(0.35)
                                elif ctype == "reload":
                                    page.reload(wait_until="domcontentloaded", timeout=30000)
                                    time.sleep(1.0)
                                elif ctype == "prefill_creds":
                                    if email and real_pass:
                                        try:
                                            auto_login_facebook(ctx, page, email, real_pass, max_wait=12)
                                        except Exception:
                                            pass
                            except Exception as ce:
                                with session.state_lock:
                                    session.error = f"تعذر تنفيذ الإجراء: {str(ce)[:120]}"
                            finally:
                                try:
                                    last_capture = time.time()
                                    did_complete = _refresh_state()
                                except Exception:
                                    did_complete = False
                                if ev:
                                    ev.set()

                            if did_complete:
                                save_account_storage_state(ctx, acc["profile_dir"])
                                if _on_verified_callback:
                                    _on_verified_callback(acc_id, session.fb_id, session.started_by)
                                time.sleep(1.8)
                                break
                            continue

                        if (time.time() - last_capture) >= 1.35:
                            last_capture = time.time()
                            if _refresh_state():
                                save_account_storage_state(ctx, acc["profile_dir"])
                                if _on_verified_callback:
                                    _on_verified_callback(acc_id, session.fb_id, session.started_by)
                                time.sleep(1.8)
                                break
                finally:
                    try:
                        if session.completed:
                            save_account_storage_state(ctx, acc["profile_dir"])
                        ctx.close()
                    except Exception:
                        pass
    except Exception as e:
        with session.state_lock:
            session.error = f"خطأ أثناء فتح الشاشة الحية: {str(e)[:160]}"
    finally:
        with session.state_lock:
            session.running = False
            session.ready = True
        with _hitl_lock:
            if _sessions.get(acc_id) is session:
                _sessions.pop(acc_id, None)


def _prune_inactive_locked() -> None:
    dead = [aid for aid, s in _sessions.items() if not s.running]
    for aid in dead:
        _sessions.pop(aid, None)


def start_hitl_session(acc_id: str, actor_uid: int, mode: str = "mobile") -> dict[str, Any]:
    """بدء جلسة شاشة حية تفاعلية لحساب معين (يُفترض التحقق من الصلاحية والملكية قبل الاستدعاء)"""
    acc = next((a for a in acc_mgr.load_accounts() if a.get("id") == acc_id), None)
    if not acc:
        return {"ok": False, "error": "الحساب غير موجود."}

    clean_mode = "desktop" if str(mode or "").strip().lower() == "desktop" else "mobile"
    init_vp = HITL_DESKTOP_VIEWPORT if clean_mode == "desktop" else HITL_MOBILE_VIEWPORT

    with _hitl_lock:
        _prune_inactive_locked()
        existing = _sessions.get(acc_id)
        if existing and existing.running:
            existing.touch()
            return {"ok": True, "reused": True, **existing.snapshot_dict()}

        # إغلاق أقدم جلسة لنفس المستخدم إذا فتح جلسات متعددة، والالتزام بالحد الأقصى للذاكرة
        for other_id, other_s in list(_sessions.items()):
            if other_s.started_by == actor_uid:
                other_s._stop_event.set()
                other_s.cmd_queue.put({"cmd": "close"})
                _sessions.pop(other_id, None)

        if len(_sessions) >= MAX_CONCURRENT_HITL:
            return {
                "ok": False,
                "error": f"يوجد حالياً {MAX_CONCURRENT_HITL} جلسات شاشة حية نشطة. أغلق إحداها أو انتظر انتهاءها.",
            }

        sess = HITLSession(
            acc_id=acc_id,
            acc_name=str(acc.get("name") or acc_id),
            owner_uid=int(acc.get("owner_id") or 0),
            started_by=int(actor_uid),
            mode=clean_mode,
            viewport=init_vp,
        )
        _sessions[acc_id] = sess

    t = threading.Thread(target=_hitl_worker, args=(sess, acc), daemon=True, name=f"HITL-{acc_id}")
    t.start()
    return {"ok": True, **sess.snapshot_dict()}


def get_hitl_state(acc_id: str) -> dict[str, Any] | None:
    with _hitl_lock:
        sess = _sessions.get(acc_id)
        if not sess:
            return None
        sess.touch()
        return sess.snapshot_dict()


def send_hitl_input(acc_id: str, payload: dict[str, Any], wait_sec: float = 4.0) -> dict[str, Any]:
    with _hitl_lock:
        sess = _sessions.get(acc_id)
    if not sess or not sess.running:
        return {"ok": False, "error": "جلسة الشاشة الحية غير مفتوحة لهذا الحساب."}

    action = str(payload.get("action") or "").strip().lower()
    ev = threading.Event()
    cmd: dict[str, Any] = {"event": ev}

    if action == "click":
        vw, vh = sess.viewport
        try:
            nx = float(payload.get("x_norm"))
            ny = float(payload.get("y_norm"))
            x = nx * vw
            y = ny * vh
        except Exception:
            x = float(payload.get("x") or 0)
            y = float(payload.get("y") or 0)
        cmd.update({"cmd": "click", "x": x, "y": y})
    elif action == "set_mode":
        cmd.update({"cmd": "set_mode", "mode": str(payload.get("mode") or "mobile")})
    elif action == "type":
        cmd.update({"cmd": "type", "text": str(payload.get("text") or ""), "submit": bool(payload.get("submit"))})
    elif action == "otp":
        cmd.update({"cmd": "otp", "code": str(payload.get("code") or "")})
    elif action == "key":
        k = str(payload.get("key") or "")
        if k not in ALLOWED_KEYS:
            return {"ok": False, "error": "مفتاح غير مدعوم."}
        cmd.update({"cmd": "key", "key": k})
    elif action == "scroll":
        cmd.update({"cmd": "scroll", "dy": int(payload.get("dy") or 300)})
    elif action == "reload":
        cmd.update({"cmd": "reload"})
    elif action == "prefill_creds":
        cmd.update({"cmd": "prefill_creds"})
    elif action == "close":
        cmd.update({"cmd": "close"})
    else:
        return {"ok": False, "error": f"أمر غير معروف: {action}"}

    sess.touch()
    sess.cmd_queue.put(cmd)
    ev.wait(timeout=max(0.5, min(10.0, wait_sec)))
    return {"ok": True, **sess.snapshot_dict()}


def stop_hitl_session(acc_id: str) -> bool:
    with _hitl_lock:
        sess = _sessions.get(acc_id)
    if not sess:
        return False
    sess._stop_event.set()
    ev = threading.Event()
    sess.cmd_queue.put({"cmd": "close", "event": ev})
    ev.wait(timeout=3.0)
    return True


def submit_telegram_otp_for_account(acc_id: str, code: str, actor_uid: int) -> dict[str, Any]:
    """إدخال رمز تحقق 2FA/OTP مُرسل من تليجرام إلى جلسة الشاشة الحية (أو فتح متصفح لإدخاله والتحقق فوراً)."""
    clean_code = "".join(ch for ch in str(code or "") if ch.isalnum())[:16]
    if not clean_code:
        return {"ok": False, "error": "الرمز غير صالح."}

    with _hitl_lock:
        existing = _sessions.get(acc_id)
    if existing and existing.running:
        return send_hitl_input(acc_id, {"action": "otp", "code": clean_code}, wait_sec=5.0)

    # إذا لم تكن جلسة مفتوحة، نفتح جلسة قصيرة على خيط HITL، ننتظر جاهزيتها أو دخولها عبر الإيميل/الباسورد ثم نرسل الرمز
    res = start_hitl_session(acc_id, actor_uid)
    if not res.get("ok"):
        return res
    deadline = time.time() + 18.0
    while time.time() < deadline:
        st = get_hitl_state(acc_id)
        if not st or not st.get("running"):
            break
        if st.get("completed"):
            return {"ok": True, **st}
        if st.get("ready"):
            if st.get("challenge_code") in ("full_login", "password_only") and st.get("has_credentials"):
                send_hitl_input(acc_id, {"action": "prefill_creds"}, wait_sec=8.0)
            out = send_hitl_input(acc_id, {"action": "otp", "code": clean_code}, wait_sec=5.0)
            # مهلة قصيرة للتحقق من قبول الرمز
            time.sleep(2.5)
            latest = get_hitl_state(acc_id) or out
            return {"ok": True, **latest}
        time.sleep(0.5)
    latest = get_hitl_state(acc_id)
    return {"ok": False, "error": (latest or {}).get("error") or "تعذر توصيل رمز التحقق في الوقت المحدد.", **(latest or {})}
