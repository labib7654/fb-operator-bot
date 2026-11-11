"""
إدارة تشغيل المتصفح، محاكاة السلوك البشري، وتسجيل الدخول التلقائي
مدعوم ببيئة سطح المكتب الافتراضية (Xvfb Virtual Display) وحقن التخفي الكامل (Stealth Anti-Detection)
لتشغيل متصفح حقيقي 100% كما لو كان يعمل على شاشة لابتوب حقيقية بدقة 1920x1080.
"""

import os
import re
import sys
import json
import time
import random
import threading
from pathlib import Path
from playwright.sync_api import sync_playwright, BrowserContext, Page
from fb_operator.config import DEFAULT_MIN_DELAY, DEFAULT_MAX_DELAY, PROFILES_DIR, SESSIONS_DIR

_LOGIN_ERROR_LOCK = threading.Lock()
_LOGIN_ERRORS: dict[int, str] = {}
_CTX_PROFILES: dict[int, Path] = {}

_PROFILE_LOCKS_GUARD = threading.Lock()
_PROFILE_LOCKS: dict[str, threading.RLock] = {}


def get_profile_lock(account_id: str) -> threading.RLock:
    """إرجاع قفل مشترك موحّد لكل حساب لمنع تعارض Chromium بين مهام البوت وواجهة التدخل البشري"""
    key = str(account_id or "").strip() or "_default"
    with _PROFILE_LOCKS_GUARD:
        if key not in _PROFILE_LOCKS:
            _PROFILE_LOCKS[key] = threading.RLock()
        return _PROFILE_LOCKS[key]


def _get_profiles_dir() -> Path:
    try:
        from fb_operator import account_manager as _acc_mgr
        return Path(_acc_mgr.PROFILES_DIR)
    except Exception:
        return Path(PROFILES_DIR)


def _get_sessions_dir() -> Path:
    try:
        from fb_operator import account_manager as _acc_mgr
        return Path(_acc_mgr.SESSIONS_DIR)
    except Exception:
        return Path(SESSIONS_DIR)


def set_login_error(context, reason: str) -> None:
    """تخزين سبب فشل تسجيل الدخول الأخير بشكل آمن لكل متصفح"""
    with _LOGIN_ERROR_LOCK:
        if reason:
            _LOGIN_ERRORS[id(context)] = reason
        else:
            _LOGIN_ERRORS.pop(id(context), None)


def get_login_error(context) -> str:
    """استرجاع سبب فشل تسجيل الدخول الأخير"""
    with _LOGIN_ERROR_LOCK:
        return _LOGIN_ERRORS.get(id(context), "")


def _cleanup_stale_profile_locks(profile_path: Path) -> None:
    """تنظيف ملفات القفل العالقة بعد إعادة تشغيل الحاوية لمنع تعليق كروميوم"""
    for lock_name in ("SingletonLock", "SingletonCookie", "SingletonSocket"):
        lp = profile_path / lock_name
        try:
            if lp.is_symlink() or lp.exists():
                lp.unlink(missing_ok=True)
        except Exception:
            pass


def resolve_cross_platform_profile(profile_dir: str | Path) -> Path:
    """توحيد مسار مجلد البروفايل ليعمل على ويندوز ولينكس السحابي بسلاسة دون أخطاء المسارات"""
    s = str(profile_dir)
    norm = s.replace("\\", "/").rstrip("/")
    acc_folder = norm.split("/")[-1]
    base_profiles = _get_profiles_dir()
    target = (base_profiles / acc_folder).resolve()
    raw_path = Path(s)
    if os.name == "nt" and raw_path.exists():
        raw_has_cookies = (raw_path / "Default" / "Network" / "Cookies").exists() or (raw_path / "Default" / "Cookies").exists()
        target_has_cookies = (target / "Default" / "Network" / "Cookies").exists() or (target / "Default" / "Cookies").exists()
        if raw_has_cookies and not target_has_cookies:
            return raw_path.resolve()
    if (os.name != "nt" and (":" in s or "\\" in s)) or (
        acc_folder.startswith("acc_") and "/fb_operator/profiles/" in norm
    ):
        return target
    return raw_path.resolve()


def _resolve_session_file(profile_dir_or_id: str | Path) -> Path:
    """تحديد مسار ملف الجلسة المحمول storage_state بصيغة آمنة"""
    raw = str(profile_dir_or_id).replace("\\", "/").rstrip("/")
    name = raw.split("/")[-1] or "default"
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", name):
        name = re.sub(r"[^A-Za-z0-9_.-]", "_", name) or "default"
    return (_get_sessions_dir() / f"{name}.json").resolve()


def save_account_storage_state(context: BrowserContext, profile_dir_or_id: str | Path | None = None) -> bool:
    """حفظ حالة الجلسة كاملة (Cookies + LocalStorage) خارج مجلد الكود لاستعادة الدخول الفوري بعد التحديثات"""
    target = profile_dir_or_id or _CTX_PROFILES.get(id(context))
    if not target:
        return False
    session_file = _resolve_session_file(target)
    try:
        if hasattr(context, "storage_state"):
            state = context.storage_state()
        else:
            state = {"cookies": list(context.cookies()), "origins": []}
        cookies = state.get("cookies", []) if isinstance(state, dict) else []
        has_c_user = any(str(c.get("name", "")) == "c_user" and str(c.get("value", "")).strip() for c in cookies)
        if not has_c_user:
            return False
        session_file.parent.mkdir(parents=True, exist_ok=True)
        tmp_file = session_file.with_suffix(".tmp")
        tmp_file.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp_file, session_file)
        try:
            from fb_operator import persistence_manager as _pm
            _pm.notify_data_changed("session_saved")
        except Exception:
            pass
        return True
    except Exception:
        return False


def restore_account_storage_state(context: BrowserContext, profile_dir_or_id: str | Path) -> bool:
    """استعادة الجلسة المحفوظة (cookies + localStorage origins) إلى المتصفح قبل التوجه إلى فيسبوك"""
    session_file = _resolve_session_file(profile_dir_or_id)
    if not session_file.exists():
        return False
    try:
        data = json.loads(session_file.read_text(encoding="utf-8"))
        cookies = data.get("cookies", []) if isinstance(data, dict) else []
        valid_cookies = []
        for c in cookies:
            if not isinstance(c, dict) or not c.get("name") or c.get("value") is None:
                continue
            item = {
                "name": str(c["name"]),
                "value": str(c["value"]),
                "domain": str(c.get("domain") or ".facebook.com"),
                "path": str(c.get("path") or "/"),
            }
            if c.get("expires") is not None:
                try:
                    item["expires"] = float(c["expires"])
                except Exception:
                    pass
            for flag in ("httpOnly", "secure"):
                if flag in c:
                    item[flag] = bool(c[flag])
            if c.get("sameSite") in ("Strict", "Lax", "None"):
                item["sameSite"] = c["sameSite"]
            valid_cookies.append(item)
        if not valid_cookies:
            return False
        context.add_cookies(valid_cookies)

        # استعادة localStorage لجميع النطاقات المسجلة بالجلسة لتفادي ظهور "جهاز جديد" في فيسبوك
        origins = data.get("origins", []) if isinstance(data, dict) else []
        origin_map: dict[str, dict[str, str]] = {}
        for orig in origins:
            if not isinstance(orig, dict):
                continue
            o_url = str(orig.get("origin") or "").strip()
            ls_list = orig.get("localStorage", [])
            if not o_url or not isinstance(ls_list, list):
                continue
            kv_pairs = {}
            for kv in ls_list:
                if isinstance(kv, dict) and kv.get("name") is not None and kv.get("value") is not None:
                    kv_pairs[str(kv["name"])] = str(kv["value"])
            if kv_pairs:
                origin_map[o_url] = kv_pairs

        if origin_map:
            init_js = (
                "(() => {"
                f"const _m = {json.dumps(origin_map, ensure_ascii=False)};"
                "const items = _m[window.location.origin];"
                "if (!items) return;"
                "for (const [k, v] of Object.entries(items)) {"
                "  try { if (!window.localStorage.getItem(k)) window.localStorage.setItem(k, v); } catch (e) {}"
                "}"
                "})();"
            )
            try:
                context.add_init_script(init_js)
            except Exception:
                pass
        return True
    except Exception:
        return False


def diagnose_facebook_challenge(page: Page) -> dict:
    """
    تشخيص دقيق لحالة الصفحة الحية في فيسبوك لتصنيف العائق بدقة تامة:
    (reCAPTCHA، Arkose، رمز 2FA/OTP، موافقة جهاز، فحص هوية، حساب معطل، نموذج كلمة مرور فقط، أو دخول كامل).
    تنبيه صارم: لا يتفاعل تلقائياً مع أي CAPTCHA مطلقاً — للتصنيف وإشعار المستخدم/الشاشة الحية فقط.
    """
    curr_url = (getattr(page, "url", "") or "").lower()

    # قراءة آمنة لنصوص الصفحة وإطاراتها
    snippet = ""
    has_recaptcha_dom = False
    has_arkose_dom = False
    has_otp_input = False
    has_email_input = False
    has_pass_input = False
    try:
        dom_info = page.evaluate(
            """() => {
                const txt = (document.body && document.body.innerText ? document.body.innerText.slice(0, 2600) : '');
                const iframes = Array.from(document.querySelectorAll('iframe')).map(f => (f.src || '') + ' ' + (f.title || '')).join(' ');
                const rec = !!document.querySelector('.g-recaptcha, [data-sitekey], iframe[src*="recaptcha"], #recaptcha');
                const ark = !!document.querySelector('iframe[src*="arkose"], iframe[src*="funcaptcha"]');
                const otp = !!document.querySelector('input[name="approvals_code"], input#approvals_code, input[autocomplete="one-time-code"]');
                const em = Array.from(document.querySelectorAll('input[name="email"], input#email')).some(el => el.offsetParent !== null);
                const pw = Array.from(document.querySelectorAll('input[name="pass"], input#pass, input[type="password"]')).some(el => el.offsetParent !== null);
                return { txt: txt + ' ' + iframes, rec, ark, otp, em, pw };
            }"""
        )
        if isinstance(dom_info, dict):
            snippet = str(dom_info.get("txt") or "").lower()
            has_recaptcha_dom = bool(dom_info.get("rec"))
            has_arkose_dom = bool(dom_info.get("ark"))
            has_otp_input = bool(dom_info.get("otp"))
            has_email_input = bool(dom_info.get("em"))
            has_pass_input = bool(dom_info.get("pw"))
        elif isinstance(dom_info, str):
            snippet = dom_info.lower()
    except Exception:
        pass

    # Fallback سريع عبر locators إن تعذر evaluate أو في حال اختلفت صيغة الإرجاع
    if not snippet:
        try:
            raw_txt = page.evaluate("() => (document.body && document.body.innerText) ? document.body.innerText.slice(0, 2600) : ''")
            if isinstance(raw_txt, str):
                snippet = raw_txt.lower()
        except Exception:
            pass
    if not has_arkose_dom:
        try:
            if page.locator('iframe[src*="arkose"], iframe[src*="funcaptcha"]').count() > 0:
                has_arkose_dom = True
        except Exception:
            pass
    if not has_recaptcha_dom:
        try:
            if page.locator('iframe[src*="recaptcha"], .g-recaptcha, [data-sitekey]').count() > 0:
                has_recaptcha_dom = True
        except Exception:
            pass
    if not has_email_input:
        try:
            if page.locator('input[name="email"], input#email').first.is_visible(timeout=200):
                has_email_input = True
        except Exception:
            pass
    if not has_pass_input:
        try:
            if page.locator('input[name="pass"], input#pass, input[type="password"]').first.is_visible(timeout=200):
                has_pass_input = True
        except Exception:
            pass

    if (
        has_recaptcha_dom
        or "recaptcha" in curr_url
        or any(k in snippet for k in (
            "أنا لست برنامج روبوت", "لست برنامج روبوت", "i'm not a robot", "i am not a robot",
            "recaptcha", "تأكيد أنك لست روبوت", "اختر كل المربعات"
        ))
    ):
        return {
            "code": "recaptcha",
            "is_ok": False,
            "is_challenge": True,
            "can_otp": False,
            "can_hitl": True,
            "message": "يطلب تحقق أمان (أنا لست برنامج روبوت - reCAPTCHA) — افتح الشاشة الحية لإكماله بنفسك",
        }

    if (
        has_arkose_dom
        or any(k in curr_url for k in ("arkoselabs", "funcaptcha", "/challenge"))
        or any(k in snippet for k in (
            "arkose labs", "matchkey", "أكمل تحدي", "تحقق من أنك إنسان",
            "verify that you're human", "complete a challenge", "confirm you're human", "solve a puzzle"
        ))
    ):
        return {
            "code": "arkose",
            "is_ok": False,
            "is_challenge": True,
            "can_otp": False,
            "can_hitl": True,
            "message": "لغز تحقق من الإنسان (Arkose Labs CAPTCHA) — افتح الشاشة الحية لإكماله بنفسك",
        }

    if any(x in curr_url for x in ("suspended", "disabled", "/account_status")) or any(
        k in snippet for k in ("تم تعليق حسابك", "your account has been suspended", "تم تعطيل حسابك", "account has been disabled")
    ):
        return {
            "code": "suspended",
            "is_ok": False,
            "is_challenge": False,
            "can_otp": False,
            "can_hitl": True,
            "message": "الحساب معطل أو موقوف من إدارة فيسبوك",
        }

    if any(k in snippet for k in (
        "كلمة السر التي أدخلتها غير صحيحة", "the password you've entered is incorrect",
        "wrong credentials", "invalid username or password", "البريد الإلكتروني أو كلمة المرور غير صحيحة"
    )):
        return {
            "code": "wrong_password",
            "is_ok": False,
            "is_challenge": False,
            "can_otp": False,
            "can_hitl": True,
            "message": "البريد الإلكتروني أو كلمة المرور غير صحيحة",
        }

    if has_otp_input or (
        ("two_step_verification" in curr_url or "checkpoint" in curr_url)
        and any(k in snippet for k in (
            "أدخل الرمز", "enter code", "login code", "authentication app", "رمز الأمان",
            "المصادقة الثنائية", "تطبيق المصادقة", "sms", "6-digit", "أرقام"
        ))
    ):
        return {
            "code": "2fa_otp",
            "is_ok": False,
            "is_challenge": True,
            "can_otp": True,
            "can_hitl": True,
            "message": "الحساب يطلب رمز أمان 2FA / OTP — أرسل الرمز عبر البوت أو افتح الشاشة الحية",
        }

    if any(k in snippet for k in (
        "تحقق من إشعاراتك", "check your notifications", "approve", "جهاز آخر", "تم إرسال إشعار"
    )) and ("checkpoint" in curr_url or "two_step_verification" in curr_url or "approv" in curr_url):
        return {
            "code": "device_approval",
            "is_ok": False,
            "is_challenge": True,
            "can_otp": False,
            "can_hitl": True,
            "message": "ينتظر الموافقة من جهاز آخر مسجل (أو افتح الشاشة الحية لاختيار طريقة أخرى)",
        }

    if any(x in curr_url for x in ("checkpoint", "two_step_verification", "/recover/")):
        return {
            "code": "identity_check",
            "is_ok": False,
            "is_challenge": True,
            "can_otp": True,
            "can_hitl": True,
            "message": "الحساب يطلب فحص أمان وهوية (Checkpoint) — افتح الشاشة الحية لمعاينة خطوات فيسبوك",
        }

    if has_pass_input and not has_email_input:
        return {
            "code": "password_only",
            "is_ok": False,
            "is_challenge": False,
            "can_otp": False,
            "can_hitl": True,
            "message": "جلسة محفوظة تطلب إعادة إدخال كلمة المرور",
        }

    if any(x in curr_url for x in ("login.php", "/login/", "login/?next=")) or (has_email_input and has_pass_input):
        return {
            "code": "full_login",
            "is_ok": False,
            "is_challenge": False,
            "can_otp": False,
            "can_hitl": True,
            "message": "انتهت صلاحية الجلسة والحساب غير مسجل — يطلب تسجيل الدخول",
        }

    if any(k in snippet for k in (
        "هذا المحتوى غير متوفر", "content isn't available",
        "page isn't available", "الصفحة غير متوفرة", "broken link"
    )):
        return {
            "code": "content_unavailable",
            "is_ok": False,
            "is_challenge": False,
            "can_otp": False,
            "can_hitl": False,
            "message": "الرابط أو المحتوى المستهدف غير متاح أو خاص أو محذوف",
        }

    return {"code": "ok", "is_ok": True, "is_challenge": False, "can_otp": False, "can_hitl": False, "message": ""}


def _detect_arkose_captcha(page: Page) -> str:
    """الكشف السلبي عن تحدي التحقق البشري للتوقف الآمن دون التفاعل معه تلقائياً"""
    d = diagnose_facebook_challenge(page)
    if d.get("code") in ("arkose", "recaptcha"):
        return d["message"]
    return ""


def check_facebook_page_access(page: Page) -> tuple[bool, str]:
    """
    فحص حالة الصفحة الحية في فيسبوك لاكتشاف الحجب أو انتهاء الجلسة أو تحدي reCAPTCHA/Arkose أو عدم توفر المحتوى فوراً.
    """
    d = diagnose_facebook_challenge(page)
    return bool(d.get("is_ok")), str(d.get("message") or "")

def human_delay(min_seconds: float = DEFAULT_MIN_DELAY, max_seconds: float = DEFAULT_MAX_DELAY) -> None:
    """توقف عشوائي لمحاكاة التردد البشري وتجنب كشف الروبوتات"""
    jitter = random.uniform(min_seconds, max_seconds)
    time.sleep(jitter)

def check_facebook_login_cookies(context: BrowserContext) -> tuple[bool, str]:
    """
    فحص كوكيز فيسبوك:
    وجود كوكيز c_user يثبت بنسبة 100% أن الحساب مسجل دخوله بنجاح.
    c_user هو المعرّف الرقمي للحساب.
    """
    try:
        cookies = context.cookies()
        c_user = next((c["value"] for c in cookies if c.get("name") == "c_user"), None)
        if c_user:
            return True, str(c_user)
    except Exception:
        pass
    return False, ""

def launch_account_browser(
    playwright_instance,
    profile_dir: str | Path,
    visible: bool = True,
    viewport_size: tuple[int, int] = (1920, 1080),
) -> BrowserContext:
    """
    تشغيل متصفح جوجل كروم الحقيقي ببروفايل مستمر للحساب مع اتساق كامل للبصمة
    (عدم تزوير Windows UA فوق خادم Linux لتفادي إطلاق فحص الروبوت reCAPTCHA من Meta).
    """
    profile_path = resolve_cross_platform_profile(profile_dir)
    profile_path.mkdir(parents=True, exist_ok=True)
    _cleanup_stale_profile_locks(profile_path)

    has_display = bool(os.environ.get("DISPLAY"))
    use_headless = not visible and not has_display
    vw, vh = int(viewport_size[0]), int(viewport_size[1])

    args = [
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-blink-features=AutomationControlled",
        "--disable-features=FedCm,CredentialManagement,AutofillServerCommunication,PasswordManager,PasswordGeneration,PasswordImport,OneClickSignin",
        "--disable-save-password-bubble",
        "--password-store=basic",
        "--disable-single-click-autofill",
        "--disable-autofill-keyboard-accessory-view",
        "--disable-infobars",
        f"--window-size={vw},{vh}",
        "--disable-notifications",
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-dev-shm-usage",
        "--lang=ar-EG,ar,en-US,en"
    ]

    launch_kwargs = {
        "user_data_dir": str(profile_path),
        "headless": use_headless,
        "args": args,
        "viewport": {"width": vw, "height": vh},
        "screen": {"width": vw, "height": vh},
        "device_scale_factor": 1,
        "locale": "ar-EG",
        "timezone_id": "Asia/Riyadh",
    }

    try:
        context = playwright_instance.chromium.launch_persistent_context(
            channel="chrome", **launch_kwargs
        )
    except Exception:
        context = playwright_instance.chromium.launch_persistent_context(**launch_kwargs)

    is_linux = sys.platform.startswith("linux")
    webgl_vendor = "Intel Open Source Technology Center" if is_linux else "Intel Inc."
    webgl_renderer = (
        "Mesa DRI Intel(R) UHD Graphics 630 (CFL GT2)"
        if is_linux
        else "ANGLE (Intel, Intel(R) UHD Graphics 630 Direct3D11 vs_5_0 ps_5_0, D3D11)"
    )

    stealth_script = f"""
        // 1. إزالة مؤشر الأتمتة webdriver بدون تعارض مع نظام التشغيل الفعلي
        Object.defineProperty(navigator, 'webdriver', {{
            get: () => undefined
        }});

        // 2. توحيد WebGL بما ينسجم طبيعياً مع نظام التشغيل الفعلي ({'Linux' if is_linux else 'Windows'})
        const _v = {json.dumps(webgl_vendor)};
        const _r = {json.dumps(webgl_renderer)};
        const getParameterProto = WebGLRenderingContext.prototype.getParameter;
        WebGLRenderingContext.prototype.getParameter = function(param) {{
            if (param === 37445) return _v;
            if (param === 37446) return _r;
            return getParameterProto.apply(this, arguments);
        }};
        if (typeof WebGL2RenderingContext !== 'undefined') {{
            const getParameterProto2 = WebGL2RenderingContext.prototype.getParameter;
            WebGL2RenderingContext.prototype.getParameter = function(param) {{
                if (param === 37445) return _v;
                if (param === 37446) return _r;
                return getParameterProto2.apply(this, arguments);
            }};
        }}

        // 3. تناسق اللغات وتعطيل نوافذ مدير كلمات المرور
        Object.defineProperty(navigator, 'languages', {{
            get: () => ['ar-EG', 'ar', 'en-US', 'en']
        }});

        if (navigator.credentials) {{
            navigator.credentials.get = () => Promise.resolve(null);
            navigator.credentials.store = () => Promise.resolve();
            navigator.credentials.create = () => Promise.resolve(null);
            navigator.credentials.preventSilentAccess = () => Promise.resolve();
        }}
    """
    context.add_init_script(stealth_script)
    _CTX_PROFILES[id(context)] = profile_path
    restore_account_storage_state(context, profile_path)
    return context


def _warmup_human_presence(page: Page) -> None:
    """تمهيد حركي بشري خفيف قبل إدخال البيانات لتجنب السلوك الآلي الجامد"""
    try:
        vw = (page.viewport_size or {}).get("width", 1280)
        vh = (page.viewport_size or {}).get("height", 800)
        page.mouse.move(random.uniform(vw * 0.25, vw * 0.65), random.uniform(vh * 0.2, vh * 0.55), steps=random.randint(8, 15))
        time.sleep(random.uniform(0.35, 0.75))
    except Exception:
        pass


def auto_login_facebook(context: BrowserContext, page: Page, email: str, password: str, status_callback=None, max_wait: int = 90) -> bool:
    """
    تسجيل الدخول وإعادة الدخول التلقائي في فيسبوك بمحاكاة بشرية متدرجة،
    مع دعم نماذج (البريد + كلمة المرور) أو (إعادة إدخال كلمة المرور للحساب المحفوظ) أو (المتابعة بحساب مسجل).
    """
    def log(msg: str):
        if status_callback:
            status_callback(msg)
        print(f"[Login] {msg}")

    set_login_error(context, "")
    clean_email = str(email or "").strip()
    clean_pass = "" if str(password or "").strip() == "[SESSION_COOKIES]" else str(password or "")

    # 1. التحقق الحي من الجلسة الحالية
    is_logged, _ = check_facebook_login_cookies(context)
    if is_logged:
        curr_now = (getattr(page, "url", "") or "").lower()
        if "facebook.com" not in curr_now:
            try:
                page.goto("https://www.facebook.com/", wait_until="domcontentloaded", timeout=35000)
                time.sleep(random.uniform(1.2, 2.0))
                dismiss_dialogs(page)
            except Exception as e:
                log(f"تنبيه شبكة أثناء التحقق من الجلسة: {e}")

        diag = diagnose_facebook_challenge(page)
        is_still_logged, _ = check_facebook_login_cookies(context)
        if is_still_logged and diag["is_ok"]:
            save_account_storage_state(context)
            log("تم التحقق من الجلسة الحية: الحساب نشط ومسجل دخوله بنجاح.")
            return True

        if diag["code"] in ("recaptcha", "arkose", "suspended", "2fa_otp", "device_approval", "identity_check"):
            set_login_error(context, diag["message"])
            log(f"[-] {diag['message']}")
            return False

        log(f"تنبيه: الجلسة المحفوظة منتهية ({diag['message'] or 'يتطلب إعادة دخول'})، جاري محاولة إعادة الدخول التلقائية...")

    log("جاري التوجه إلى موقع فيسبوك...")
    try:
        page.goto("https://www.facebook.com/", wait_until="domcontentloaded", timeout=60000)
    except Exception as e:
        log(f"تنبيه بالشبكة أثناء الفتح: {e}")

    time.sleep(random.uniform(1.8, 2.8))
    dismiss_dialogs(page)

    diag_after = diagnose_facebook_challenge(page)
    is_logged, _ = check_facebook_login_cookies(context)
    if is_logged and diag_after["is_ok"]:
        save_account_storage_state(context)
        log("تم التحقق من الجلسة، الحساب مسجل دخوله بالفعل.")
        return True

    if diag_after["code"] in ("recaptcha", "arkose", "suspended", "2fa_otp", "device_approval", "identity_check"):
        set_login_error(context, diag_after["message"])
        log(f"[-] {diag_after['message']}")
        return False

    if not clean_pass:
        reason = diag_after["message"] or "انتهت جلسة الكوكيز ولا توجد كلمة مرور محفوظة لإعادة الدخول"
        set_login_error(context, reason)
        log(f"تنبيه: {reason}")
        return False

    # دعم بطاقة "المتابعة باسم ..." في حال ظهورها قبل النموذج
    try:
        for cont_sel in (
            'div[role="button"]:has-text("متابعة")',
            'button:has-text("متابعة")',
            'div[role="button"]:has-text("Continue")',
            'button:has-text("Continue")',
        ):
            cloc = page.locator(cont_sel).first
            if cloc.is_visible(timeout=450):
                human_click(page, cloc, timeout=2500)
                time.sleep(random.uniform(1.5, 2.5))
                dismiss_dialogs(page)
                d_cont = diagnose_facebook_challenge(page)
                logged_now, _ = check_facebook_login_cookies(context)
                if logged_now and d_cont["is_ok"]:
                    save_account_storage_state(context)
                    log("تم تسجيل الدخول عبر بطاقة المتابعة المحفوظة.")
                    return True
                break
    except Exception:
        pass

    _warmup_human_presence(page)

    # 2. تعبئة الحقول (نموذج كامل بالبريد + كلمة المرور، أو نموذج كلمة المرور فقط للحساب المحفوظ)
    try:
        email_selectors = [
            'input[name="email"]',
            'input#email',
            'input[data-testid="royal_email"]',
            'input[aria-label*="البريد"]',
            'input[placeholder*="البريد"]',
            'input[type="email"]',
        ]
        pass_selectors = [
            'input[name="pass"]',
            'input#pass',
            'input[data-testid="royal_pass"]',
            'input[aria-label*="كلمة"]',
            'input[placeholder*="كلمة"]',
            'input[type="password"]',
        ]

        email_input = None
        pass_input = None
        for _ in range(10):
            for sel in email_selectors:
                loc = page.locator(sel).first
                if loc.is_visible(timeout=500):
                    email_input = loc
                    break
            for sel in pass_selectors:
                loc = page.locator(sel).first
                if loc.is_visible(timeout=500):
                    pass_input = loc
                    break
            if pass_input and (email_input or not clean_email or diag_after["code"] == "password_only"):
                break
            if email_input and pass_input:
                break
            time.sleep(0.9)

        # في حال ظهور صفحة اختيار حساب فقط بلا حقل بريد وكلمة سر، نبحث عن "استخدام حساب آخر"
        if not pass_input and not email_input:
            for other_sel in ('a:has-text("تسجيل الدخول إلى حساب آخر")', 'div[role="button"]:has-text("حساب آخر")', 'a:has-text("Log into another account")'):
                try:
                    oloc = page.locator(other_sel).first
                    if oloc.is_visible(timeout=800):
                        human_click(page, oloc, timeout=2500)
                        time.sleep(1.5)
                        break
                except Exception:
                    pass
            for sel in email_selectors:
                loc = page.locator(sel).first
                if loc.is_visible(timeout=800):
                    email_input = loc
                    break
            for sel in pass_selectors:
                loc = page.locator(sel).first
                if loc.is_visible(timeout=800):
                    pass_input = loc
                    break

        if email_input and clean_email:
            log("كتابة البريد الإلكتروني/الهاتف بمحاكاة بشرية...")
            human_click(page, email_input, timeout=3000)
            time.sleep(random.uniform(0.35, 0.75))
            email_input.fill("")
            time.sleep(random.uniform(0.15, 0.35))
            email_input.press_sequentially(clean_email, delay=random.randint(60, 125))
            time.sleep(random.uniform(0.65, 1.35))
        elif not pass_input:
            diag_miss = diagnose_facebook_challenge(page)
            msg = diag_miss["message"] or "تعذر العثور على حقول تسجيل الدخول في الصفحة"
            set_login_error(context, msg)
            log(f"[-] {msg}")
            return False

        if pass_input:
            log("كتابة كلمة المرور بمحاكاة بشرية...")
            human_click(page, pass_input, timeout=3000)
            time.sleep(random.uniform(0.3, 0.7))
            pass_input.fill("")
            time.sleep(random.uniform(0.15, 0.3))
            pass_input.press_sequentially(clean_pass, delay=random.randint(65, 120))
            time.sleep(random.uniform(0.75, 1.45))
        else:
            set_login_error(context, "تعذر العثور على حقل كلمة المرور بصفحة الدخول")
            log("[-] تعذر العثور على حقل إدخال كلمة المرور.")
            return False

        log("إرسال بيانات الدخول...")
        btn_selectors = [
            'div[role="button"][aria-label="تسجيل الدخول"]',
            'div[role="button"]:has-text("تسجيل الدخول")',
            'div[role="button"]:has-text("Log in")',
            'button[name="login"]',
            'button[type="submit"]',
            'button:has-text("تسجيل الدخول")',
        ]

        btn_clicked = False
        for sel in btn_selectors:
            loc = page.locator(sel).first
            if loc.is_visible(timeout=1500):
                btn_clicked = human_click(page, loc, timeout=3000)
                if btn_clicked:
                    break

        if not btn_clicked:
            page.keyboard.press("Enter")

    except Exception as e:
        set_login_error(context, f"تعذر كتابة البيانات في حقول الدخول: {e}")
        log(f"تعذر كتابة البيانات في حقول الدخول: {e}")
        return False

    # 3. مراقبة الاستجابة الفورية دون إضاعة وقت عند ظهور reCAPTCHA / 2FA / خطأ كلمة سر
    log("بانتظار استجابة فيسبوك وتثبيت الجلسة...")
    start_time = time.time()
    warned_2fa = False

    while time.time() - start_time < max_wait:
        if len(context.pages) == 0:
            log("تم إغلاق المتصفح.")
            return False

        diag = diagnose_facebook_challenge(page)
        is_logged, _ = check_facebook_login_cookies(context)
        if is_logged and diag["is_ok"]:
            time.sleep(2.5)
            save_account_storage_state(context)
            log("تم تسجيل الدخول وتثبيت الجلسة الدائمة بنجاح!")
            return True

        if diag["code"] in ("recaptcha", "arkose", "suspended", "wrong_password"):
            set_login_error(context, diag["message"])
            log(f"[-] {diag['message']}")
            return False

        if diag["code"] in ("2fa_otp", "device_approval", "identity_check"):
            if not warned_2fa:
                log(f"تنبيه: {diag['message']}")
                warned_2fa = True
            # بعد مرور 6 ثوانٍ على شاشة التحقق في السحابة بدون حل، نتوقف فوراً ليتمكن المستخدم من حله عبر الشاشة الحية/OTP
            if time.time() - start_time >= 6.0 and not visible_page_has_live_human(context):
                set_login_error(context, diag["message"])
                return False

        time.sleep(1.3)

    diag_final = diagnose_facebook_challenge(page)
    is_logged, _ = check_facebook_login_cookies(context)
    if is_logged and diag_final["is_ok"]:
        save_account_storage_state(context)
        log("تم تسجيل الدخول بنجاح.")
        return True

    set_login_error(context, diag_final["message"] or "انتهت مهلة انتظار تسجيل الدخول")
    log("انتهت مهلة الانتظار دون اكتمال تسجيل الدخول.")
    return False


def visible_page_has_live_human(context: BrowserContext) -> bool:
    """التمييز بين التشغيل الآلي بالخلفية وجلسة الشاشة الحية التفاعلية (HITL)"""
    return False

def dismiss_dialogs(page: Page) -> None:
    """إغلاق النوافذ المنبثقة ولافتات الموافقة على الكوكيز وحجب الشاشات الشائعة في فيسبوك"""
    dismiss_selectors = [
        'button[data-cookiebanner="accept_button"]',
        'button[data-cookiebanner="accept_only_essential_button"]',
        'div[aria-label*="السماح بكل ملفات"]',
        'div[aria-label*="Allow all cookies" i]',
        'button:has-text("السماح بكل ملفات")',
        'button:has-text("Allow all cookies")',
        'button:has-text("Allow essential and optional cookies")',
        'div[role="button"]:has-text("إلغاء")',
        'button:has-text("إلغاء")',
        'div[role="button"]:has-text("ليس الآن")',
        'div[role="button"]:has-text("Not Now")',
        'div[role="button"]:has-text("إغلاق")',
        'div[role="button"]:has-text("Close")',
        'div[aria-label="إغلاق"]',
        'div[aria-label="Close"]',
        'button:has-text("ليس الآن")',
        'button:has-text("Not Now")'
    ]

    for sel in dismiss_selectors:
        try:
            elem = page.locator(sel).first
            if elem.is_visible(timeout=500):
                elem.click(timeout=1000)
                time.sleep(0.3)
        except Exception:
            pass

def smooth_scroll(page: Page, scrolls: int = 2) -> None:
    """تمرير الصفحة بسلاسة بشرية لتحميل المنشورات والتفاعل معها"""
    for _ in range(scrolls):
        delta = random.randint(350, 650)
        page.mouse.wheel(0, delta)
        time.sleep(random.uniform(0.8, 1.6))


def human_click(page: Page, locator, timeout: int = 4000) -> bool:
    """نقر بشري سلس مع حركة مؤشر طبيعية داخل بيئة سطح المكتب 1920x1080"""
    try:
        locator.scroll_into_view_if_needed(timeout=timeout)
        box = locator.bounding_box(timeout=timeout)
        if box:
            tx = box["x"] + box["width"] * random.uniform(0.32, 0.68)
            ty = box["y"] + box["height"] * random.uniform(0.32, 0.68)
            page.mouse.move(tx, ty, steps=random.randint(6, 12))
            time.sleep(random.uniform(0.08, 0.22))
        locator.click(timeout=timeout)
        return True
    except Exception:
        return False

