"""
محرك الشاشة الحية التفاعلية لحل التحقق البشري يدوياً (Interactive Human-in-the-Loop Live View)
يعرض شاشة المتصفح الحية للمستخدم المصرح فقط داخل لوحة Mini App ويتيح له النقر والكتابة وإرسال رمز 2FA بنفسه.
سياسة صارمة: لا يحل أي CAPTCHA آلياً — يقتصر على بث الشاشة وتمرير نقرات الإنسان الحقيقي على خيط واحد مالك للمتصفح (Single-Thread Owner).
"""

from __future__ import annotations

import base64
import hashlib
import queue
import re
import threading
import time
import urllib.parse
from dataclasses import dataclass, field
from typing import Any, Callable
import requests

import fb_operator.account_manager as acc_mgr
from fb_operator.browser_manager import (
    sync_playwright,
    auto_login_facebook,
    check_facebook_login_cookies,
    diagnose_facebook_challenge,
    dismiss_dialogs,
    get_profile_lock,
    launch_account_browser,
    resolve_cross_platform_profile,
    save_account_storage_state,
)
from fb_operator.proxy_manager import proxy_execution_guard, resolve_proxy_for_account

HITL_VIEWPORT = (1280, 800)
HITL_DESKTOP_VIEWPORT = (1280, 800)
HITL_MOBILE_VIEWPORT = (430, 780)
HITL_INACTIVITY_TTL_SEC = 600.0
HITL_MAX_TTL_SEC = 1800.0
HITL_HARD_CAP_SEC = 7200.0
MAX_CONCURRENT_HITL = 2

_AR_TRANSLATE_CACHE_LOCK = threading.Lock()
_AR_TRANSLATE_CACHE: dict[str, str] = {}

_EN_AR_PHRASES: tuple[tuple[str, str], ...] = (
    ("use the arrows to move the character on the tiles which have the same icons as shown on the left",
     "استخدم الأسهم لتحريك الشخصية فوق المربعات التي تحمل نفس الرموز الظاهرة على اليسار، ثم اضغط إرسال (Submit)."),
    ("use the arrows to rotate the animal to face in the direction of the hand",
     "استخدم الأسهم لتدوير الشكل حتى يواجه نفس اتجاه اليد، ثم اضغط إرسال (Submit)."),
    ("use the arrows to",
     "استخدم الأسهم الظاهرة أسفل الصورة للتوجيه ثم اضغط إرسال (Submit)."),
    ("pick the dice pair", "اختر حجر النرد الذي يطابق المطلوب."),
    ("match this", "طابق هذا الشكل/الرمز"),
    ("can't see this challenge? generate new or try audio challenge instead",
     "إن لم يظهر التحدي بوضوح يمكنك توليد تحدٍ جديد بالضغط على الرابط أسفله."),
    ("check your notifications on another device",
     "راجع إشعارات فيسبوك على جهاز آخر مسجل فيه الحساب ووافق على تسجيل الدخول."),
    ("enter the 6-digit code", "أدخل رمز التحقق المكون من 6 أرقام في خانة النص بالأسفل."),
    ("confirm your identity", "فيسبوك يطلب تأكيد الهوية لهذا الحساب."),
    ("forgotten password", "هل نسيت كلمة السر؟"),
    ("create new account", "إنشاء حساب جديد"),
    ("try another way", "جرّب طريقة تحقق أخرى"),
    ("log in", "تسجيل الدخول"),
    ("submit", "إرسال / تأكيد"),
    ("continue", "متابعة"),
)


def _quick_glossary_ar(text: str) -> str:
    low = " ".join(str(text or "").lower().split())
    hits: list[str] = []
    for en_key, ar_val in _EN_AR_PHRASES:
        if en_key in low and ar_val not in hits:
            hits.append(ar_val)
    return " • ".join(hits[:2])


def _translate_text_to_arabic(text: str) -> str:
    clean = " ".join(str(text or "").split())[:420]
    if not clean or not re.search(r"[A-Za-z]{3,}", clean):
        return ""
    key = hashlib.sha256(clean.encode("utf-8")).hexdigest()[:24]
    with _AR_TRANSLATE_CACHE_LOCK:
        cached = _AR_TRANSLATE_CACHE.get(key)
    if cached is not None:
        return cached

    glossary = _quick_glossary_ar(clean)
    translated = glossary
    try:
        url = (
            "https://translate.googleapis.com/translate_a/single"
            f"?client=gtx&sl=en&tl=ar&dt=t&q={urllib.parse.quote(clean[:320])}"
        )
        resp = requests.get(url, timeout=2.5)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list) and data and isinstance(data[0], list):
                parts = [str(seg[0]) for seg in data[0] if isinstance(seg, list) and seg and seg[0]]
                g_ar = " ".join(parts).strip()
                if g_ar:
                    translated = f"{glossary} | {g_ar}" if (glossary and len(g_ar) > 8 and glossary not in g_ar) else g_ar
    except Exception:
        pass

    with _AR_TRANSLATE_CACHE_LOCK:
        if len(_AR_TRANSLATE_CACHE) >= 256:
            _AR_TRANSLATE_CACHE.clear()
        _AR_TRANSLATE_CACHE[key] = translated
    return translated


def _extract_visible_challenge_text(page) -> str:
    chunks: list[str] = []
    try:
        frames = list(getattr(page, "frames", []) or [])
    except Exception:
        frames = [page]
    for target in [page] + frames[:4]:
        try:
            txt = target.evaluate(
                """() => {
                    const el = document.querySelector('h1, h2, [role="heading"], .challenge-instructions, #FunCaptcha, form') || document.body;
                    return el && el.innerText ? el.innerText.slice(0, 320) : '';
                }"""
            )
            if isinstance(txt, str) and txt.strip():
                clean = " ".join(txt.split())[:300]
                if clean and clean not in chunks:
                    chunks.append(clean)
        except Exception:
            continue
    return " | ".join(chunks)[:360]

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
_mission_waiters_lock = threading.Lock()
_mission_waiters: dict[str, dict[str, Any]] = {}
_challenge_urls_lock = threading.Lock()
_challenge_urls: dict[str, tuple[float, str]] = {}


def record_hitl_challenge_url(acc_id: str, url: str) -> None:
    """حفظ آخر رابط تحدٍ/تحقق وصل له الحساب لاستكماله فوراً داخل الشاشة الحية"""
    clean = str(url or "").strip()
    low = clean.lower()
    if not acc_id or "facebook.com" not in low:
        return
    if any(x in low for x in ("login.php", "/login/", "login/?next=")):
        return
    with _challenge_urls_lock:
        _challenge_urls[str(acc_id)] = (time.time(), clean[:400])


def pop_hitl_challenge_url(acc_id: str, max_age_sec: float = 600.0) -> str:
    with _challenge_urls_lock:
        item = _challenge_urls.pop(str(acc_id), None)
    if not item:
        return ""
    ts, url = item
    if (time.time() - ts) <= max_age_sec:
        return url
    return ""


def register_mission_hitl_waiter(acc_id: str, owner_uid: int, reason: str = "") -> threading.Event:
    ev = threading.Event()
    with _mission_waiters_lock:
        _mission_waiters[str(acc_id)] = {
            "acc_id": str(acc_id),
            "owner_uid": int(owner_uid or 0),
            "reason": str(reason or "يتطلب تحقيقاً بشرياً من فيسبوك")[:160],
            "event": ev,
            "decision": "",
            "fb_id": "",
            "created_at": time.time(),
        }
    return ev


def signal_mission_hitl_decision(acc_id: str, decision: str, fb_id: str = "") -> bool:
    clean_dec = str(decision or "").strip().lower()
    if clean_dec not in ("verified", "skip", "abort"):
        return False
    with _mission_waiters_lock:
        w = _mission_waiters.get(str(acc_id))
        if not w:
            return False
        w["decision"] = clean_dec
        if fb_id:
            w["fb_id"] = str(fb_id)
        ev = w.get("event")
        if ev:
            ev.set()
        return True


def wait_for_mission_hitl(acc_id: str, timeout: float = 300.0) -> dict[str, Any]:
    with _mission_waiters_lock:
        w = _mission_waiters.get(str(acc_id))
        if not w:
            return {"decision": "skip", "fb_id": ""}
        ev = w["event"]
    signaled = ev.wait(timeout=max(1.0, float(timeout or 300.0)))
    with _mission_waiters_lock:
        w_after = _mission_waiters.pop(str(acc_id), {})
    if not signaled:
        return {"decision": "timeout", "fb_id": str(w_after.get("fb_id") or "")}
    return {
        "decision": str(w_after.get("decision") or "skip"),
        "fb_id": str(w_after.get("fb_id") or ""),
    }


def get_mission_hitl_waiter(owner_uid: int | None = None, acc_id: str | None = None) -> dict[str, Any] | None:
    with _mission_waiters_lock:
        if acc_id and str(acc_id) in _mission_waiters:
            w = _mission_waiters[str(acc_id)]
            return {k: v for k, v in w.items() if k != "event"}
        for w in _mission_waiters.values():
            if owner_uid is None or int(w.get("owner_uid") or 0) == int(owner_uid):
                return {k: v for k, v in w.items() if k != "event"}
    return None


def clear_mission_hitl_waiter(acc_id: str) -> None:
    with _mission_waiters_lock:
        w = _mission_waiters.pop(str(acc_id), None)
        if w and w.get("event"):
            w["event"].set()


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
    max_deadline: float = 0.0
    running: bool = True
    ready: bool = False
    completed: bool = False
    fb_id: str = ""
    challenge_code: str = "starting"
    challenge_message: str = "جاري تشغيل متصفح الحساب وفتح فيسبوك..."
    page_url: str = ""
    can_otp: bool = False
    has_credentials: bool = False
    auto_paused: bool = False
    auto_login_active: bool = False
    ar_translate_enabled: bool = True
    screen_text_orig: str = ""
    screen_text_ar: str = ""
    error: str = ""
    frame_b64: str = ""
    frame_seq: int = 0
    mode: str = "mobile"
    viewport: tuple[int, int] = HITL_MOBILE_VIEWPORT
    frame_cond: threading.Condition = field(default_factory=lambda: threading.Condition(threading.Lock()))
    _stop_event: threading.Event = field(default_factory=threading.Event)

    def __post_init__(self) -> None:
        if not self.max_deadline:
            self.max_deadline = self.created_at + HITL_MAX_TTL_SEC

    def notify_frame(self) -> None:
        with self.frame_cond:
            self.frame_cond.notify_all()

    def touch(self, active_input: bool = False, extra_sec: float = 0.0) -> None:
        now = time.time()
        self.last_activity = now
        cap_end = self.created_at + HITL_HARD_CAP_SEC
        if extra_sec > 0.0:
            self.max_deadline = min(cap_end, max(self.max_deadline, now) + float(extra_sec))
        elif active_input:
            self.max_deadline = min(cap_end, max(self.max_deadline, now + 300.0))

    def ttl_remaining_sec(self, now: float | None = None) -> int:
        t = float(now if now is not None else time.time())
        rem_max = max(0.0, self.max_deadline - t)
        rem_idle = max(0.0, HITL_INACTIVITY_TTL_SEC - (t - self.last_activity))
        return max(0, int(min(rem_max, rem_idle)))

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
                "auto_paused": self.auto_paused,
                "auto_login_active": self.auto_login_active,
                "ar_translate_enabled": self.ar_translate_enabled,
                "screen_text_ar": self.screen_text_ar if self.ar_translate_enabled else "",
                "error": self.error,
                "frame_b64": self.frame_b64,
                "frame_seq": self.frame_seq,
                "mode": self.mode,
                "viewport": {"width": int(self.viewport[0]), "height": int(self.viewport[1])},
                "ttl_remaining": self.ttl_remaining_sec(),
            }


def _safe_capture_jpeg_b64(page) -> str:
    try:
        raw = page.screenshot(type="jpeg", quality=88)
        return "data:image/jpeg;base64," + base64.b64encode(raw).decode("ascii")
    except Exception:
        return ""


def _dispatch_real_click(page, x: float, y: float) -> None:
    """تمرير نقرة حقيقية عابرة لإطارات التحقق (OOPIF مثل Arkose/reCAPTCHA) وعناصر React"""
    try:
        if hasattr(page.mouse, "move") and hasattr(page.mouse, "down") and hasattr(page.mouse, "up"):
            page.mouse.move(x, y, steps=4)
            page.mouse.down()
            time.sleep(0.055)
            page.mouse.up()
            return
    except Exception:
        pass
    page.mouse.click(x, y)


def _hitl_worker(session: HITLSession, acc: dict) -> None:
    """الخيط الوحيد المالك لـ Playwright لهذه الجلسة (يبث الإطارات حياً عبر CDP Screencast بدون Cross-Thread Error)."""
    acc_id = session.acc_id
    lock = get_profile_lock(acc_id)
    email = str(acc.get("email") or "").strip()
    raw_pass = str(acc.get("password") or "")
    real_pass = "" if raw_pass in ("", "[SESSION_COOKIES]") else raw_pass
    session.has_credentials = bool(email and real_pass)

    try:
        prof_name = resolve_cross_platform_profile(acc["profile_dir"]).name
        proxy_res = resolve_proxy_for_account(account_id=prof_name, explicit_proxy=acc.get("proxy"))
        proxy_uri = str(proxy_res.get("raw_uri") or "")
        with lock, proxy_execution_guard(proxy_uri, min_gap_sec=0.0):
            with sync_playwright() as p:
                # نحافظ على بصمة Desktop Chrome المتطابقة مع تسجيل الدخول والمهام لتفادي إبطال فيسبوك للجلسة
                ctx = launch_account_browser(
                    p,
                    acc["profile_dir"],
                    visible=False,
                    viewport_size=session.viewport,
                    mobile=False,
                    proxy=acc.get("proxy"),
                )
                cdp = None
                last_cdp_frame_ts = [0.0]
                try:
                    page = ctx.pages[0] if ctx.pages else ctx.new_page()
                    def _restart_cdp_screencast(vw: int, vh: int) -> None:
                        if cdp is None:
                            return
                        try:
                            cdp.send("Page.stopScreencast")
                        except Exception:
                            pass
                        try:
                            cdp.send(
                                "Page.startScreencast",
                                {
                                    "format": "jpeg",
                                    "quality": 88,
                                    "maxWidth": int(vw),
                                    "maxHeight": int(vh),
                                    "everyNthFrame": 1,
                                },
                            )
                        except Exception:
                            pass

                    try:
                        cdp = ctx.new_cdp_session(page)

                        def _on_screencast_frame(params):
                            b64 = params.get("data") or ""
                            sid = params.get("sessionId")
                            if b64:
                                with session.state_lock:
                                    session.frame_b64 = "data:image/jpeg;base64," + b64
                                    session.frame_seq += 1
                                    session.ready = True
                                last_cdp_frame_ts[0] = time.time()
                                session.notify_frame()
                            if sid is not None and cdp is not None:
                                try:
                                    cdp.send("Page.screencastFrameAck", {"sessionId": sid})
                                except Exception:
                                    pass

                        cdp.on("Page.screencastFrame", _on_screencast_frame)
                        _restart_cdp_screencast(session.viewport[0], session.viewport[1])
                    except Exception:
                        cdp = None

                    resume_url = pop_hitl_challenge_url(acc_id)
                    target_url = resume_url if resume_url else "https://www.facebook.com/"
                    try:
                        page.goto(target_url, wait_until="domcontentloaded", timeout=45000)
                    except Exception:
                        if target_url != "https://www.facebook.com/":
                            page.goto("https://www.facebook.com/", wait_until="domcontentloaded", timeout=45000)
                    time.sleep(1.2)
                    dismiss_dialogs(page)

                    def _schedule_translate_async(raw_txt: str) -> None:
                        if not raw_txt or not session.ar_translate_enabled:
                            return
                        quick = _quick_glossary_ar(raw_txt)
                        if quick:
                            with session.state_lock:
                                if raw_txt == session.screen_text_orig and not session.screen_text_ar:
                                    session.screen_text_ar = quick
                        def _tr_worker():
                            ar_out = _translate_text_to_arabic(raw_txt)
                            if ar_out:
                                with session.state_lock:
                                    if raw_txt == session.screen_text_orig:
                                        session.screen_text_ar = ar_out
                                session.notify_frame()
                        threading.Thread(target=_tr_worker, daemon=True).start()

                    def _refresh_state(force_shot: bool = False) -> bool:
                        diag = diagnose_facebook_challenge(page)
                        is_logged, fb_id = check_facebook_login_cookies(ctx)
                        cdp_recent = (time.time() - last_cdp_frame_ts[0]) < 1.2
                        frame = _safe_capture_jpeg_b64(page) if (force_shot or not cdp_recent) else ""
                        curr_url = ""
                        try:
                            curr_url = str(page.url or "")[:180]
                        except Exception:
                            pass
                        vis_txt = _extract_visible_challenge_text(page) if (force_shot or session.ar_translate_enabled) else ""
                        need_tr = False

                        with session.state_lock:
                            session.ready = True
                            if frame:
                                session.frame_b64 = frame
                                session.frame_seq += 1
                            session.page_url = curr_url
                            session.challenge_code = str(diag.get("code") or "unknown")
                            if not session.auto_paused:
                                session.challenge_message = str(diag.get("message") or "")
                            session.can_otp = bool(diag.get("can_otp"))
                            if vis_txt and vis_txt != session.screen_text_orig:
                                session.screen_text_orig = vis_txt
                                need_tr = True

                            if is_logged and diag.get("is_ok"):
                                session.completed = True
                                session.fb_id = fb_id
                                session.challenge_code = "ok"
                                session.challenge_message = "تم تسجيل الدخول وتثبيت الجلسة بنجاح!"
                                session.notify_frame()
                                return True
                        if need_tr:
                            _schedule_translate_async(vis_txt)
                        session.notify_frame()
                        return False

                    if _refresh_state(force_shot=True):
                        save_account_storage_state(ctx, acc["profile_dir"])
                        if _on_verified_callback:
                            _on_verified_callback(acc_id, session.fb_id, session.started_by)
                        time.sleep(1.5)
                        return

                    # دخول تلقائي حي ومباشر أمام المستخدم مع التوقف التلقائي عند أي عائق ليتمكن المستخدم من إصلاحه
                    if session.has_credentials and session.challenge_code in ("full_login", "password_only") and not session.auto_paused:
                        def _on_auto_step(step_msg: str) -> None:
                            with session.state_lock:
                                if not session.auto_paused:
                                    session.challenge_message = f"🔑 {step_msg}"
                            _refresh_state(force_shot=True)

                        with session.state_lock:
                            session.auto_login_active = True
                            session.challenge_message = "🔑 جاري تسجيل الدخول التلقائي أمامك (أوقفه في أي لحظة للتحكم اليدوي)..."
                        session.notify_frame()
                        try:
                            auto_login_facebook(ctx, page, email, real_pass, status_callback=_on_auto_step, max_wait=24)
                        except Exception:
                            pass
                        finally:
                            with session.state_lock:
                                session.auto_login_active = False
                        if _refresh_state(force_shot=True):
                            save_account_storage_state(ctx, acc["profile_dir"])
                            if _on_verified_callback:
                                _on_verified_callback(acc_id, session.fb_id, session.started_by)
                            time.sleep(1.5)
                            return

                    last_capture = time.time()
                    while not session._stop_event.is_set():
                        now = time.time()
                        if now >= session.max_deadline:
                            with session.state_lock:
                                session.error = "انتهى الوقت الممدد لجلسة الشاشة الحية. أعد فتحها لمتابعة التحدي من نفس النقطة."
                            session.notify_frame()
                            break
                        if (now - session.last_activity) >= HITL_INACTIVITY_TTL_SEC:
                            with session.state_lock:
                                session.error = "أُغلقت الشاشة الحية تلقائياً لعدم التفاعل لمدة 10 دقائق."
                            session.notify_frame()
                            break
                        if len(ctx.pages) == 0:
                            break

                        try:
                            cmd_obj = session.cmd_queue.get_nowait()
                        except queue.Empty:
                            cmd_obj = None

                        if cmd_obj is not None:
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
                                    with session.state_lock:
                                        session.auto_paused = True
                                    vw, vh = session.viewport
                                    x = max(1.0, min(float(vw - 1), float(cmd_obj.get("x") or 0)))
                                    y = max(1.0, min(float(vh - 1), float(cmd_obj.get("y") or 0)))
                                    _dispatch_real_click(page, x, y)
                                    try:
                                        page.wait_for_timeout(250)
                                    except Exception:
                                        time.sleep(0.25)
                                elif ctype == "drag":
                                    with session.state_lock:
                                        session.auto_paused = True
                                    vw, vh = session.viewport
                                    x1 = max(1.0, min(float(vw - 1), float(cmd_obj.get("x1") or 0)))
                                    y1 = max(1.0, min(float(vh - 1), float(cmd_obj.get("y1") or 0)))
                                    x2 = max(1.0, min(float(vw - 1), float(cmd_obj.get("x2") or 0)))
                                    y2 = max(1.0, min(float(vh - 1), float(cmd_obj.get("y2") or 0)))
                                    try:
                                        page.mouse.move(x1, y1, steps=2)
                                        page.mouse.down()
                                        page.mouse.move(x2, y2, steps=10)
                                        time.sleep(0.05)
                                        page.mouse.up()
                                    except Exception:
                                        pass
                                    try:
                                        page.wait_for_timeout(250)
                                    except Exception:
                                        time.sleep(0.25)
                                elif ctype == "check_now":
                                    with session.state_lock:
                                        session.auto_paused = False
                                    save_account_storage_state(ctx, acc["profile_dir"], save_pending=True)
                                elif ctype == "set_mode":
                                    new_mode = "desktop" if str(cmd_obj.get("mode") or "") == "desktop" else "mobile"
                                    new_vp = HITL_DESKTOP_VIEWPORT if new_mode == "desktop" else HITL_MOBILE_VIEWPORT
                                    with session.state_lock:
                                        session.mode = new_mode
                                        session.viewport = new_vp
                                    page.set_viewport_size({"width": new_vp[0], "height": new_vp[1]})
                                    _restart_cdp_screencast(new_vp[0], new_vp[1])
                                    try:
                                        page.wait_for_timeout(350)
                                    except Exception:
                                        time.sleep(0.35)
                                elif ctype == "pause_auto":
                                    with session.state_lock:
                                        session.auto_paused = True
                                        session.auto_login_active = False
                                        session.challenge_message = "⏸️ التحكم اليدوي مفعّل — الشاشة بيدك الآن لتصلح أي خطوة بنفسك."
                                elif ctype == "extend_ttl":
                                    with session.state_lock:
                                        rem_m = max(1, int(round(session.ttl_remaining_sec() / 60.0)))
                                        session.challenge_message = f"⏳ تم تمديد وقت الجلسة الحية (+5 دقائق إضافية — المتبقي ~{rem_m}د)."
                                elif ctype == "toggle_translate":
                                    need_bg_tr = ""
                                    with session.state_lock:
                                        if "enabled" in cmd_obj and cmd_obj.get("enabled") is not None:
                                            session.ar_translate_enabled = bool(cmd_obj.get("enabled"))
                                        else:
                                            session.ar_translate_enabled = not session.ar_translate_enabled
                                        if not session.ar_translate_enabled:
                                            session.challenge_message = "🌐 تم إيقاف الترجمة الفورية للشاشة."
                                        else:
                                            session.challenge_message = "🌐 تم تفعيل الترجمة الفورية إلى العربية."
                                            if session.screen_text_orig and not session.screen_text_ar:
                                                need_bg_tr = session.screen_text_orig
                                    if need_bg_tr:
                                        _schedule_translate_async(need_bg_tr)
                                elif ctype == "type":
                                    with session.state_lock:
                                        session.auto_paused = True
                                    txt = str(cmd_obj.get("text") or "")[:300]
                                    if txt:
                                        page.keyboard.insert_text(txt)
                                        if cmd_obj.get("submit"):
                                            time.sleep(0.2)
                                            page.keyboard.press("Enter")
                                        try:
                                            page.wait_for_timeout(350)
                                        except Exception:
                                            time.sleep(0.35)
                                elif ctype == "otp":
                                    with session.state_lock:
                                        session.auto_paused = True
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
                                        time.sleep(0.3)
                                elif ctype == "scroll":
                                    dy = max(-900, min(900, int(cmd_obj.get("dy") or 300)))
                                    page.mouse.wheel(0, dy)
                                    time.sleep(0.25)
                                elif ctype == "reload":
                                    page.reload(wait_until="domcontentloaded", timeout=30000)
                                    time.sleep(0.9)
                                elif ctype == "prefill_creds":
                                    if email and real_pass:
                                        def _on_live_step(step_msg: str) -> None:
                                            with session.state_lock:
                                                if not session.auto_paused:
                                                    session.challenge_message = f"🔑 {step_msg}"
                                            _refresh_state(force_shot=True)

                                        with session.state_lock:
                                            session.auto_paused = False
                                            session.auto_login_active = True
                                            session.challenge_message = "🔑 جاري إدخال بيانات الحساب أمامك مباشرة..."
                                        session.notify_frame()
                                        try:
                                            auto_login_facebook(
                                                ctx,
                                                page,
                                                email,
                                                real_pass,
                                                status_callback=_on_live_step,
                                                max_wait=24,
                                            )
                                        except Exception:
                                            pass
                                        finally:
                                            with session.state_lock:
                                                session.auto_login_active = False
                            except Exception as ce:
                                with session.state_lock:
                                    session.error = f"تعذر تنفيذ الإجراء: {str(ce)[:120]}"
                            finally:
                                try:
                                    last_capture = time.time()
                                    did_complete = _refresh_state(force_shot=True)
                                except Exception:
                                    did_complete = False
                                if ev:
                                    ev.set()

                            if did_complete:
                                save_account_storage_state(ctx, acc["profile_dir"])
                                if _on_verified_callback:
                                    _on_verified_callback(acc_id, session.fb_id, session.started_by)
                                time.sleep(1.5)
                                break
                            continue

                        # ضخ حلقة أحداث Playwright لاستقبال إطارات CDP Screencast لحظياً بدون حجب الخيط
                        try:
                            page.wait_for_timeout(110)
                        except Exception:
                            time.sleep(0.11)

                        if (time.time() - last_capture) >= 1.2:
                            last_capture = time.time()
                            if _refresh_state(force_shot=False):
                                save_account_storage_state(ctx, acc["profile_dir"])
                                if _on_verified_callback:
                                    _on_verified_callback(acc_id, session.fb_id, session.started_by)
                                time.sleep(1.5)
                                break
                finally:
                    try:
                        if cdp is not None:
                            try:
                                cdp.send("Page.stopScreencast")
                            except Exception:
                                pass
                        save_account_storage_state(ctx, acc["profile_dir"], save_pending=True)
                        ctx.close()
                    except Exception:
                        pass
    except Exception as e:
        with session.state_lock:
            session.error = f"خطأ أثناء فتح الشاشة الحية: {str(e)[:160]}"
        session.notify_frame()
    finally:
        with session.state_lock:
            session.running = False
            session.ready = True
            completed_flag = bool(session.completed)
            verified_fb_id = str(session.fb_id or "")
        session.notify_frame()
        with _hitl_lock:
            if _sessions.get(acc_id) is session:
                _sessions.pop(acc_id, None)
        if completed_flag:
            signal_mission_hitl_decision(acc_id, "verified", verified_fb_id)


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
    """قراءة الحالة اللحظية للشاشة الحية دون تمديد مؤقت الخمول التلقائي"""
    with _hitl_lock:
        sess = _sessions.get(acc_id)
        if not sess:
            return None
        return sess.snapshot_dict()


def wait_for_hitl_frame(acc_id: str, since_seq: int = -1, timeout: float = 12.0) -> dict[str, Any] | None:
    """انتظار وصول إطار CDP جديد أو انتهاء الجلسة بآلية Event-Driven دون استهلاك معالج"""
    with _hitl_lock:
        sess = _sessions.get(acc_id)
    if not sess:
        return None
    deadline = time.time() + max(0.5, min(20.0, float(timeout or 12.0)))
    with sess.frame_cond:
        while True:
            with sess.state_lock:
                changed = (sess.frame_seq != since_seq) or (not sess.running) or sess.completed or bool(sess.error)
            if changed:
                break
            rem = deadline - time.time()
            if rem <= 0:
                break
            sess.frame_cond.wait(timeout=rem)
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
    elif action == "drag":
        vw, vh = sess.viewport
        try:
            x1 = float(payload.get("x1_norm")) * vw
            y1 = float(payload.get("y1_norm")) * vh
            x2 = float(payload.get("x2_norm")) * vw
            y2 = float(payload.get("y2_norm")) * vh
        except Exception:
            x1 = float(payload.get("x1") or 0)
            y1 = float(payload.get("y1") or 0)
            x2 = float(payload.get("x2") or 0)
            y2 = float(payload.get("y2") or 0)
        cmd.update({"cmd": "drag", "x1": x1, "y1": y1, "x2": x2, "y2": y2})
    elif action == "check_now":
        cmd.update({"cmd": "check_now"})
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
    elif action == "pause_auto":
        cmd.update({"cmd": "pause_auto"})
    elif action == "extend_ttl":
        cmd.update({"cmd": "extend_ttl"})
    elif action == "toggle_translate":
        cmd.update({"cmd": "toggle_translate", "enabled": payload.get("enabled")})
    elif action == "close":
        cmd.update({"cmd": "close"})
    else:
        return {"ok": False, "error": f"أمر غير معروف: {action}"}

    sess.touch(
        active_input=(action != "close"),
        extra_sec=(300.0 if action == "extend_ttl" else 0.0),
    )
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
