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
import hashlib
import threading
from pathlib import Path
try:
    from patchright.sync_api import sync_playwright, BrowserContext, Page
    USING_PATCHRIGHT = True
except Exception:
    from playwright.sync_api import sync_playwright, BrowserContext, Page
    USING_PATCHRIGHT = False
from fb_operator.config import DEFAULT_MIN_DELAY, DEFAULT_MAX_DELAY, PROFILES_DIR, SESSIONS_DIR

_LOGIN_ERROR_LOCK = threading.Lock()
_LOGIN_ERRORS: dict[int, str] = {}
_CTX_PROFILES: dict[int, Path] = {}
_CURSOR_POS: dict[int, tuple[float, float]] = {}

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


def save_account_storage_state(
    context: BrowserContext,
    profile_dir_or_id: str | Path | None = None,
    save_pending: bool = True,
) -> bool:
    """حفظ حالة الجلسة كاملة (Cookies + LocalStorage) خارج مجلد الكود مع حفظ الكوكيز المعلقة للتحقق دون مساس بالجلسات النشطة"""
    target = profile_dir_or_id or _CTX_PROFILES.get(id(context))
    if not target:
        return False
    session_file = _resolve_session_file(target)
    pending_file = session_file.with_suffix(".pending.json")
    try:
        if hasattr(context, "storage_state"):
            state = context.storage_state()
        else:
            state = {"cookies": list(context.cookies()), "origins": []}
        cookies = state.get("cookies", []) if isinstance(state, dict) else []
        has_c_user = any(str(c.get("name", "")) == "c_user" and str(c.get("value", "")).strip() for c in cookies)
        if not has_c_user:
            # نحفظ الكوكيز الوسيطة (checkpoint/datr/fr) في ملف معلق منفصل فقط دون استبدال أي جلسة نشطة سابقة
            if save_pending and cookies:
                pending_file.parent.mkdir(parents=True, exist_ok=True)
                tmp_p = pending_file.with_suffix(".pending.tmp")
                tmp_p.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
                os.replace(tmp_p, pending_file)
            return False
        session_file.parent.mkdir(parents=True, exist_ok=True)
        tmp_file = session_file.with_suffix(".tmp")
        tmp_file.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp_file, session_file)
        if pending_file.exists():
            try:
                pending_file.unlink()
            except Exception:
                pass
        try:
            from fb_operator import persistence_manager as _pm
            _pm.notify_data_changed("session_saved")
        except Exception:
            pass
        return True
    except Exception:
        return False


def restore_account_storage_state(context: BrowserContext, profile_dir_or_id: str | Path) -> bool:
    """استعادة الجلسة المحفوظة (أو الكوكيز المعلقة أثناء التحدي) إلى المتصفح قبل التوجه إلى فيسبوك"""
    session_file = _resolve_session_file(profile_dir_or_id)
    pending_file = session_file.with_suffix(".pending.json")
    src_file = session_file if session_file.exists() else (pending_file if pending_file.exists() else None)
    if src_file is None:
        return False
    try:
        data = json.loads(src_file.read_text(encoding="utf-8"))
        cookies = data.get("cookies", []) if isinstance(data, dict) else []
        if not cookies and src_file is session_file and pending_file.exists():
            data = json.loads(pending_file.read_text(encoding="utf-8"))
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
            "يرجى تأكيد أنك إنسان", "تأكيد أنك إنسان",
            "verify that you're human", "complete a challenge", "confirm you're human",
            "confirm that you're human", "confirm you are human", "solve a puzzle"
        ))
    ):
        return {
            "code": "arkose",
            "is_ok": False,
            "is_challenge": True,
            "can_otp": False,
            "can_hitl": True,
            "message": "تحدي تحقق من الإنسان (يرجى تأكيد أنك إنسان / Arkose Labs CAPTCHA) — افتح الشاشة الحية لإكماله بنفسك",
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

def _get_account_fingerprint(profile_path: Path, is_linux: bool) -> dict:
    """توليد بصمة عتاد متماسكة وثابتة لكل حساب حسب معرّفه عبر إعادة تشغيل السيرفر"""
    seed = hashlib.sha256((profile_path.name or "acc_default").encode("utf-8")).digest()
    desktop_viewports = [(1366, 768), (1440, 900), (1536, 864), (1600, 900), (1280, 800)]
    cores_pool = [4, 6, 8]
    mem_pool = [8, 8, 16]
    webgl_linux = [
        "Mesa Intel(R) UHD Graphics 620 (KBL GT2)",
        "Mesa Intel(R) Iris(R) Xe Graphics (TGL GT2)",
        "Mesa DRI Intel(R) UHD Graphics 630 (CFL GT2)",
    ]
    webgl_win = [
        "ANGLE (Intel, Intel(R) UHD Graphics 620 Direct3D11 vs_5_0 ps_5_0, D3D11)",
        "ANGLE (Intel, Intel(R) Iris(R) Xe Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)",
        "ANGLE (NVIDIA, NVIDIA GeForce GTX 1650 Direct3D11 vs_5_0 ps_5_0, D3D11)",
    ]
    return {
        "viewport": desktop_viewports[seed[0] % len(desktop_viewports)],
        "cores": cores_pool[seed[1] % len(cores_pool)],
        "memory": mem_pool[seed[2] % len(mem_pool)],
        "webgl_vendor": "Intel Open Source Technology Center" if is_linux else "Intel Inc.",
        "webgl_renderer": (webgl_linux if is_linux else webgl_win)[seed[3] % 3],
    }


def launch_account_browser(
    playwright_instance,
    profile_dir: str | Path,
    visible: bool = True,
    viewport_size: tuple[int, int] | None = None,
    mobile: bool = False,
    proxy: str | None = None,
) -> BrowserContext:
    """
    تشغيل متصفح كروم حقيقي ببروفايل مستمر وبصمة متسقة لكل حساب
    مع إخفاء كامل لمؤشرات الأتمتة، دعم البروكسي الاختياري (FB_PROXY)، ووضع الجوال التفاعلي.
    """
    profile_path = resolve_cross_platform_profile(profile_dir)
    profile_path.mkdir(parents=True, exist_ok=True)
    _cleanup_stale_profile_locks(profile_path)

    is_linux = sys.platform.startswith("linux")
    fp = _get_account_fingerprint(profile_path, is_linux)
    has_display = bool(os.environ.get("DISPLAY"))
    use_headless = not visible and not has_display
    if viewport_size:
        vw, vh = int(viewport_size[0]), int(viewport_size[1])
    elif mobile:
        vw, vh = 430, 780
    else:
        vw, vh = fp["viewport"]

    try:
        from fb_operator import proxy_manager

        proxy_res = proxy_manager.resolve_proxy_for_account(
            account_id=profile_path.name,
            explicit_proxy=proxy,
        )
    except Exception:
        fallback_srv = (proxy or os.environ.get("FB_PROXY") or "").strip()
        proxy_res = {
            "raw_uri": fallback_srv,
            "playwright_proxy": {"server": fallback_srv} if fallback_srv else None,
            "geo_hints": {},
        }

    proxy_srv = str(proxy_res.get("raw_uri") or "").strip()
    pw_proxy = proxy_res.get("playwright_proxy")
    geo_hints = proxy_res.get("geo_hints") or {}

    is_auto_linux_no_proxy = bool(is_linux and not proxy_srv and not os.environ.get("FB_TIMEZONE"))
    default_locale = (
        os.environ.get("FB_LOCALE")
        or geo_hints.get("locale")
        or ("en-US" if is_auto_linux_no_proxy else "ar-EG")
    ).strip() or "en-US"
    default_tz = (
        os.environ.get("FB_TIMEZONE")
        or geo_hints.get("timezone")
        or ("America/New_York" if is_auto_linux_no_proxy else "Asia/Riyadh")
    ).strip() or "America/New_York"
    langs_list = list(
        geo_hints.get("languages")
        or (
            ["en-US", "en", "ar-EG", "ar"]
            if default_locale.lower().startswith("en")
            else ["ar-EG", "ar", "en-US", "en"]
        )
    )
    use_js_fp_shims = not USING_PATCHRIGHT

    args = [
        "--no-first-run",
        "--no-default-browser-check",
        "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
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
        f"--lang={default_locale},en-US,en,ar",
    ]
    if not USING_PATCHRIGHT:
        args.append("--disable-blink-features=AutomationControlled")

    launch_kwargs = {
        "user_data_dir": str(profile_path),
        "headless": use_headless,
        "args": args,
        "viewport": {"width": vw, "height": vh},
        "screen": {"width": vw, "height": vh},
        "device_scale_factor": 1.5 if mobile else 1,
        "is_mobile": bool(mobile),
        "has_touch": bool(mobile),
        "locale": default_locale,
        "timezone_id": default_tz,
    }

    if pw_proxy:
        launch_kwargs["proxy"] = pw_proxy
    elif proxy_srv:
        launch_kwargs["proxy"] = {"server": proxy_srv}

    try:
        context = playwright_instance.chromium.launch_persistent_context(
            channel="chrome", **launch_kwargs
        )
    except Exception:
        try:
            context = playwright_instance.chromium.launch_persistent_context(**launch_kwargs)
        except Exception as exc:
            if proxy_srv:
                detect_and_report_proxy_error(proxy_srv, exc)
            raise

    stealth_template = """
    (() => {
        const useShims = __USE_SHIMS__;
        if (useShims) {
            try {
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined, configurable: true });
            } catch (e) {}

            // استكمال كائن window.chrome وبنية الإضافات (Plugins) الحقيقية عند غياب Patchright
            try {
                if (!window.chrome) window.chrome = {};
                if (!window.chrome.runtime) window.chrome.runtime = {};
                if (!window.chrome.loadTimes) window.chrome.loadTimes = function() { return {}; };
                if (!window.chrome.csi) window.chrome.csi = function() { return {}; };
                if (!window.chrome.app) {
                    window.chrome.app = { isInstalled: false, InstallState: { DISABLED: 'disabled', INSTALLED: 'installed', NOT_INSTALLED: 'not_installed' } };
                }
            } catch (e) {}

            try {
                if (!navigator.plugins || navigator.plugins.length === 0) {
                    const fakePlugins = [
                        { name: 'PDF Viewer', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
                        { name: 'Chrome PDF Viewer', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
                        { name: 'Chromium PDF Viewer', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
                        { name: 'Microsoft Edge PDF Viewer', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
                        { name: 'WebKit built-in PDF', filename: 'internal-pdf-viewer', description: 'Portable Document Format' }
                    ];
                    const plugArr = {
                        length: fakePlugins.length,
                        item: (i) => fakePlugins[i] || null,
                        namedItem: (n) => fakePlugins.find((p) => p.name === n) || null,
                        refresh: () => {},
                        [Symbol.iterator]: function* () { for (const p of fakePlugins) yield p; }
                    };
                    fakePlugins.forEach((p, idx) => { plugArr[idx] = p; });
                    Object.defineProperty(navigator, 'plugins', { get: () => plugArr, configurable: true });
                }
            } catch (e) {}

            try {
                Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => __CORES__, configurable: true });
                Object.defineProperty(navigator, 'deviceMemory', { get: () => __MEMORY__, configurable: true });
                Object.defineProperty(navigator, 'languages', { get: () => __LANGS__, configurable: true });
            } catch (e) {}

            try {
                const _v = __VENDOR__;
                const _r = __RENDERER__;
                const getParameterProto = WebGLRenderingContext.prototype.getParameter;
                WebGLRenderingContext.prototype.getParameter = function(param) {
                    if (param === 37445) return _v;
                    if (param === 37446) return _r;
                    return getParameterProto.apply(this, arguments);
                };
                    if (typeof WebGL2RenderingContext !== 'undefined') {
                        const getParameterProto2 = WebGL2RenderingContext.prototype.getParameter;
                        WebGL2RenderingContext.prototype.getParameter = function(param) {
                            if (param === 37445) return _v;
                            if (param === 37446) return _r;
                            return getParameterProto2.apply(this, arguments);
                        };
                    }
            } catch (e) {}

            try {
                if (navigator.permissions && navigator.permissions.query) {
                    const origQuery = navigator.permissions.query.bind(navigator.permissions);
                    navigator.permissions.query = (params) => (
                        params && params.name === 'notifications'
                            ? Promise.resolve({ state: Notification.permission === 'denied' ? 'prompt' : Notification.permission })
                            : origQuery(params)
                    );
                }
            } catch (e) {}
        }

        // تنظيف HeadlessChrome إن وُجد دون تغيير رقم الإصدار الفعلي لمنع تعارض بصمة TLS
        try {
            const rawUa = String(navigator.userAgent || '');
            if (rawUa.includes('HeadlessChrome')) {
                const cleanUa = rawUa.replace(/HeadlessChrome/g, 'Chrome');
                Object.defineProperty(navigator, 'userAgent', { get: () => cleanUa, configurable: true });
                Object.defineProperty(navigator, 'appVersion', { get: () => cleanUa.replace(/^Mozilla\\//, ''), configurable: true });
            }
        } catch (e) {}

        // ضبط أبعاد النافذة الخارجية لتفادي كشف النوافذ المخفية
        try {
            if (!window.outerHeight || window.outerHeight <= window.innerHeight) {
                Object.defineProperty(window, 'outerWidth', { get: () => __VW__, configurable: true });
                Object.defineProperty(window, 'outerHeight', { get: () => __VH__ + 82, configurable: true });
            }
        } catch (e) {}

        try {
            if (navigator.credentials) {
                navigator.credentials.get = () => Promise.resolve(null);
                navigator.credentials.store = () => Promise.resolve();
                navigator.credentials.create = () => Promise.resolve(null);
                navigator.credentials.preventSilentAccess = () => Promise.resolve();
            }
        } catch (e) {}
    })();
    """
    stealth_script = (
        stealth_template
        .replace("__USE_SHIMS__", "true" if use_js_fp_shims else "false")
        .replace("__CORES__", str(fp["cores"]))
        .replace("__MEMORY__", str(fp["memory"]))
        .replace("__LANGS__", json.dumps(langs_list))
        .replace("__VW__", str(vw))
        .replace("__VH__", str(vh))
        .replace("__VENDOR__", json.dumps(fp["webgl_vendor"]))
        .replace("__RENDERER__", json.dumps(fp["webgl_renderer"]))
    )
    context.add_init_script(stealth_script)
    _CTX_PROFILES[id(context)] = profile_path
    if proxy_srv:
        _CTX_PROXIES[id(context)] = proxy_srv
    restore_account_storage_state(context, profile_path)
    return context


_CTX_PROXIES: dict[int, str] = {}
_PROXY_ERR_TOKENS = (
    "ERR_PROXY_CONNECTION_FAILED",
    "ERR_TUNNEL_CONNECTION_FAILED",
    "ERR_SOCKS_CONNECTION_FAILED",
    "ERR_NO_SUPPORTED_PROXIES",
    "ERR_PROXY_AUTH_REQUESTED",
    "ERR_PROXY_CERTIFICATE_INVALID",
    "ERR_PROXY_",
)


def get_context_proxy_uri(context) -> str:
    if not context:
        return ""
    return str(_CTX_PROXIES.get(id(context), "") or "").strip()


def detect_and_report_proxy_error(context_or_proxy, err_or_text: object, account_id: str = "") -> bool:
    txt = str(err_or_text or "")
    up = txt.upper()
    is_proxy_err = any(tok in up for tok in _PROXY_ERR_TOKENS) or (
        "PROXY" in up and any(w in up for w in ("FAIL", "TIMEOUT", "REFUSED", "RESET", "TIMED OUT"))
    )
    if not is_proxy_err:
        return False
    proxy_uri = ""
    if isinstance(context_or_proxy, str):
        proxy_uri = context_or_proxy.strip()
    elif context_or_proxy is not None:
        proxy_uri = get_context_proxy_uri(context_or_proxy)
    if not proxy_uri and account_id:
        try:
            from fb_operator import proxy_manager
            proxy_uri = str(proxy_manager.resolve_proxy_for_account(account_id=account_id).get("raw_uri") or "")
        except Exception:
            proxy_uri = ""
    if not proxy_uri:
        return False
    try:
        from fb_operator import proxy_manager
        proxy_manager.report_proxy_network_error(proxy_uri, txt[:160])
        return True
    except Exception:
        return False


def _bezier_curve_points(x0: float, y0: float, x1: float, y1: float, steps: int = 16) -> list[tuple[float, float]]:
    """توليد مسار منحنى بيزيه ثلاثي (Cubic Bezier) يحاكي حركة مفصل اليد البشرية نحو الهدف"""
    dx = x1 - x0
    dy = y1 - y0
    spread = max(25.0, min(140.0, (dx * dx + dy * dy) ** 0.5 * 0.35))
    c1x = x0 + dx * random.uniform(0.20, 0.42) + random.uniform(-spread, spread)
    c1y = y0 + dy * random.uniform(0.15, 0.45) + random.uniform(-spread * 0.65, spread * 0.65)
    c2x = x0 + dx * random.uniform(0.58, 0.85) + random.uniform(-spread * 0.5, spread * 0.5)
    c2y = y0 + dy * random.uniform(0.55, 0.88) + random.uniform(-spread * 0.4, spread * 0.4)
    pts: list[tuple[float, float]] = []
    n = max(6, int(steps))
    for i in range(1, n + 1):
        u = i / n
        # تباطؤ وتنعيم طبيعي عند البداية والنهاية (Ease-in-out)
        t = u * u * (3.0 - 2.0 * u)
        omt = 1.0 - t
        px = (omt ** 3) * x0 + 3.0 * (omt ** 2) * t * c1x + 3.0 * omt * (t ** 2) * c2x + (t ** 3) * x1
        py = (omt ** 3) * y0 + 3.0 * (omt ** 2) * t * c1y + 3.0 * omt * (t ** 2) * c2y + (t ** 3) * y1
        if i < n:
            px += random.uniform(-1.2, 1.2)
            py += random.uniform(-1.2, 1.2)
        pts.append((px, py))
    return pts


def _curved_mouse_move(page: Page, tx: float, ty: float) -> None:
    """تحريك المؤشر على منحنى بيزيه طبيعي متدرج من موضع اليد السابق"""
    try:
        vp = getattr(page, "viewport_size", None) or {}
        vw = float(vp.get("width", 1280))
        vh = float(vp.get("height", 800))
        sx, sy = _CURSOR_POS.get(id(page), (random.uniform(vw * 0.15, vw * 0.45), random.uniform(vh * 0.15, vh * 0.45)))
        tx_c = max(6.0, min(vw - 6.0, float(tx)))
        ty_c = max(6.0, min(vh - 6.0, float(ty)))
        steps = random.randint(12, 20)
        for px, py in _bezier_curve_points(sx, sy, tx_c, ty_c, steps=steps):
            page.mouse.move(max(2.0, min(vw - 2.0, px)), max(2.0, min(vh - 2.0, py)))
            time.sleep(random.uniform(0.008, 0.026))
        _CURSOR_POS[id(page)] = (tx_c, ty_c)
    except Exception:
        pass


def human_type_text(page: Page, locator, text: str, clear_existing: bool = False, fast: bool = False) -> None:
    """كتابة بشرية متدرجة الإيقاع على الحقول العادية ومربعات contenteditable مع إزاحة بصرية طبيعية"""
    human_click(page, locator, timeout=3000)
    time.sleep(random.uniform(0.22, 0.52) if fast else random.uniform(0.28, 0.65))
    if clear_existing:
        existing = ""
        try:
            existing = locator.input_value(timeout=600)
        except Exception:
            try:
                existing = (locator.inner_text(timeout=600) or "").strip()
            except Exception:
                existing = ""
        if existing:
            try:
                page.keyboard.press("Control+a")
                time.sleep(random.uniform(0.08, 0.18))
                page.keyboard.press("Backspace")
                time.sleep(random.uniform(0.15, 0.35))
            except Exception:
                try:
                    locator.fill("")
                except Exception:
                    pass

    chunk_pause = random.randint(5, 9)
    for idx, ch in enumerate(str(text or "")):
        page.keyboard.type(ch)
        if ch in ("@", ".", "_", "-", "+", "،", "؟", "!", "\n"):
            time.sleep(random.uniform(0.10, 0.22) if fast else random.uniform(0.15, 0.30))
        elif ch == " ":
            time.sleep(random.uniform(0.06, 0.14) if fast else random.uniform(0.09, 0.18))
        elif idx > 0 and idx % chunk_pause == 0:
            chunk_pause = random.randint(5, 9)
            time.sleep(random.uniform(0.09, 0.19) if fast else random.uniform(0.12, 0.25))
        else:
            time.sleep(random.uniform(0.028, 0.095) if fast else random.uniform(0.045, 0.145))


def _human_type_text(page: Page, locator, text: str) -> None:
    """الاسم الداخلي المحفوظ للتوافق مع نموذج تسجيل الدخول"""
    human_type_text(page, locator, text, clear_existing=True, fast=False)


def _warmup_human_presence(page: Page, feed_browse: bool = False) -> None:
    """تمهيد حركي وتصفح طبيعي للخلاصة قبل الدخول أو تنفيذ أي إجراء"""
    try:
        if not hasattr(page, "mouse") or not hasattr(page.mouse, "wheel"):
            return
        vp = getattr(page, "viewport_size", None) or {}
        vw = float(vp.get("width", 1280))
        vh = float(vp.get("height", 800))
        _curved_mouse_move(page, random.uniform(vw * 0.22, vw * 0.68), random.uniform(vh * 0.20, vh * 0.55))
        time.sleep(random.uniform(0.35, 0.75))
        if feed_browse:
            for _ in range(random.randint(2, 3)):
                page.mouse.wheel(0, random.randint(220, 460))
                time.sleep(random.uniform(0.55, 1.15))
                if random.random() < 0.4:
                    _curved_mouse_move(page, random.uniform(vw * 0.20, vw * 0.72), random.uniform(vh * 0.24, vh * 0.65))
            if random.random() < 0.5:
                page.mouse.wheel(0, -random.randint(90, 190))
                time.sleep(random.uniform(0.35, 0.75))
        else:
            page.mouse.wheel(0, random.randint(50, 130))
            time.sleep(random.uniform(0.45, 0.9))
            page.mouse.wheel(0, -random.randint(50, 130))
            time.sleep(random.uniform(0.35, 0.7))
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
            _warmup_human_presence(page, feed_browse=True)
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
        _warmup_human_presence(page, feed_browse=True)
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
            _human_type_text(page, email_input, clean_email)
            time.sleep(random.uniform(0.75, 1.45))
        elif not pass_input:
            diag_miss = diagnose_facebook_challenge(page)
            msg = diag_miss["message"] or "تعذر العثور على حقول تسجيل الدخول في الصفحة"
            set_login_error(context, msg)
            log(f"[-] {msg}")
            return False

        if pass_input:
            log("كتابة كلمة المرور بمحاكاة بشرية...")
            _human_type_text(page, pass_input, clean_pass)
            time.sleep(random.uniform(0.85, 1.65))
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
            try:
                dismiss_dialogs(page)
            except Exception:
                pass
            save_account_storage_state(context)
            log("تم تسجيل الدخول وتثبيت الجلسة الدائمة بنجاح!")
            return True

        if diag["code"] in ("recaptcha", "arkose", "suspended", "wrong_password"):
            save_account_storage_state(context)
            set_login_error(context, diag["message"])
            log(f"[-] {diag['message']}")
            return False

        if diag["code"] in ("2fa_otp", "device_approval", "identity_check"):
            if not warned_2fa:
                log(f"تنبيه: {diag['message']}")
                warned_2fa = True
            # بعد مرور 6 ثوانٍ على شاشة التحقق في السحابة بدون حل، نتوقف فوراً ليتمكن المستخدم من حله عبر الشاشة الحية/OTP
            if time.time() - start_time >= 6.0 and not visible_page_has_live_human(context):
                save_account_storage_state(context)
                set_login_error(context, diag["message"])
                return False

        time.sleep(1.3)

    diag_final = diagnose_facebook_challenge(page)
    is_logged, _ = check_facebook_login_cookies(context)
    if is_logged and diag_final["is_ok"]:
        try:
            dismiss_dialogs(page)
        except Exception:
            pass
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
    """إغلاق النوافذ المنبثقة ولافتات الموافقة على الكوكيز وحجب الشاشات الشائعة في فيسبوك بنقر بشري"""
    dismiss_selectors = [
        'button[data-cookiebanner="accept_button"]',
        'button[data-cookiebanner="accept_only_essential_button"]',
        'div[aria-label*="السماح بكل ملفات"]',
        'div[aria-label*="Allow all cookies" i]',
        'button:has-text("السماح بكل ملفات")',
        'button:has-text("Allow all cookies")',
        'button:has-text("Allow essential and optional cookies")',
        'div[role="dialog"] div[role="button"]:has-text("ليس الآن")',
        'div[role="dialog"] button:has-text("ليس الآن")',
        'div[role="button"]:has-text("ليس الآن")',
        'div[role="button"]:has-text("Not Now")',
        'button:has-text("ليس الآن")',
        'button:has-text("Not Now")',
        'a[role="button"]:has-text("ليس الآن")',
        'a[role="button"]:has-text("Not Now")',
        'div[role="button"]:has-text("إلغاء")',
        'button:has-text("إلغاء")',
        'div[role="button"]:has-text("إغلاق")',
        'div[role="button"]:has-text("Close")',
        'div[aria-label="إغلاق"]',
        'div[aria-label="Close"]',
    ]

    for sel in dismiss_selectors:
        try:
            elem = page.locator(sel).first
            if elem.is_visible(timeout=400):
                if not human_click(page, elem, timeout=1000):
                    elem.click(timeout=1000)
                time.sleep(random.uniform(0.3, 0.7))
        except Exception:
            pass

def smooth_scroll(page: Page, scrolls: int = 2) -> None:
    """تمرير الصفحة بسلاسة بشرية لتحميل المنشورات والتفاعل معها"""
    for _ in range(scrolls):
        delta = random.randint(350, 650)
        page.mouse.wheel(0, delta)
        time.sleep(random.uniform(0.8, 1.6))


def human_click(page: Page, locator, timeout: int = 4000) -> bool:
    """نقر بشري سلس بمسار بيزيه منحنٍ وتوقيت ضغط وإفلات طبيعي للإصبع/المؤشر"""
    try:
        if hasattr(locator, "scroll_into_view_if_needed"):
            locator.scroll_into_view_if_needed(timeout=timeout)
        box = locator.bounding_box()
        if box and box.get("width", 0) > 2 and box.get("height", 0) > 2:
            tx = box["x"] + box["width"] * random.uniform(0.28, 0.72)
            ty = box["y"] + box["height"] * random.uniform(0.28, 0.72)
            _curved_mouse_move(page, tx, ty)
            time.sleep(random.uniform(0.08, 0.22))
            if hasattr(page.mouse, "down") and hasattr(page.mouse, "up"):
                page.mouse.down()
                time.sleep(random.uniform(0.065, 0.145))
                page.mouse.up()
                return True
            if hasattr(page.mouse, "click"):
                page.mouse.click(tx, ty)
                return True
        locator.click(timeout=timeout)
        return True
    except Exception:
        try:
            locator.click(timeout=timeout)
            return True
        except Exception:
            return False


_PROFILE_REQUIREMENT_LABELS = {
    "arabic_name": "اسم عربي طبيعي ومناسب",
    "avatar": "صورة شخصية حقيقية",
    "cover": "صورة خلفية (غلاف)",
    "bio": "سيرة ذاتية (نبذة)",
    "university": "الجامعة / التعليم",
    "relationship": "الحالة الاجتماعية",
    "posts": "منشور أو منشورين على الأقل",
}

_EMPTY_PROMPT_RE = re.compile(
    r"(إضافة|أضف)\s+(سيرة ذاتية|نبذة|مدرسة|كلية|جامعة|مكان عمل|حالة اجتماعية)|"
    r"\b(Add\s+(bio|a\s+bio|high\s+school|college|workplace|relationship\s+status))\b|"
    r"(لا توجد\s+(مدارس|بيانات|معلومات)\s+لعرضها|No\s+(schools|workplaces|relationship)\s+to\s+show)",
    re.IGNORECASE,
)
_EDU_RE = re.compile(
    r"(جامعة|كلية|معهد|أكاديمية|درس(?:ت)?\s+في|يدرس\s+في|تدرس\s+في|طالب(?:ة)?\s+في|"
    r"\b(?:University|College|Institute|Academy|Studied\s+at|Studies\s+at)\b)",
    re.IGNORECASE,
)
_REL_RE = re.compile(
    r"(أعزب|عزباء|متزوج(?:ة)?|مرتبط(?:ة)?|مخطوب(?:ة)?|أرمل(?:ة)?|منفصل(?:ة)?|في علاقة|"
    r"\b(?:Single|Married|In\s+a\s+relationship|Engaged|Widowed|Divorced|Separated)\b)",
    re.IGNORECASE,
)


def _is_good_arabic_profile_name(name: str) -> bool:
    clean = re.sub(r"\s+", " ", str(name or "")).strip()
    if not clean or len(clean) < 4:
        return False
    lowered = clean.lower()
    if any(bad in lowered for bad in ("facebook", "test", "bot", "spam", "user", "account")):
        return False
    ar_chars = re.findall(r"[\u0600-\u06FF]", clean)
    lat_chars = re.findall(r"[A-Za-z0-9]", clean)
    # يشترط وجود حروف عربية حقيقية تغلب على الاسم، وكلمتين على الأقل (الاسم الأول + اللقب)
    words = [w for w in clean.split(" ") if len(re.findall(r"[\u0600-\u06FF]", w)) >= 2]
    return len(ar_chars) >= 5 and len(words) >= 2 and len(lat_chars) <= 2


def _extract_profile_dom_metrics(page: Page) -> dict:
    return page.evaluate("""
        () => {
            const root = document.querySelector('div[role="main"]') || document.body;
            const h1s = Array.from(root.querySelectorAll('h1'));
            let name = '';
            for (const h of h1s) {
                const t = (h.innerText || h.textContent || '').trim();
                if (t && !/^(facebook|فيسبوك|الإشعارات|notifications)$/i.test(t)) {
                    name = t;
                    break;
                }
            }

            const isRealImg = (src) => {
                if (!src) return false;
                const s = String(src).toLowerCase();
                if (!s.startsWith('http') && !s.startsWith('data:image')) return false;
                if (s.includes('rsrc.php') || s.includes('default') || s.includes('silhouette') || s.includes('blank')) return false;
                return true;
            };

            let hasAvatar = false;
            const avatarSels = [
                'a[aria-label*="صورة الملف الشخصي"] image, a[aria-label*="صورة الملف الشخصي"] img',
                'a[aria-label*="Profile picture"] image, a[aria-label*="Profile picture"] img',
                '[aria-label*="إجراءات الملف الشخصي"] image, [aria-label*="Profile photo"] img',
                'svg image',
                'img.profile-avatar, img[data-testid="profile_avatar"]'
            ];
            for (const sel of avatarSels) {
                const els = Array.from(root.querySelectorAll(sel));
                for (const el of els) {
                    const src = el.getAttribute('src') || el.getAttribute('xlink:href') || el.getAttribute('href') || '';
                    if (isRealImg(src)) {
                        const rect = el.getBoundingClientRect ? el.getBoundingClientRect() : {width: 80, height: 80};
                        if ((rect.width || 80) >= 40 && (rect.height || 80) >= 40) {
                            hasAvatar = true;
                            break;
                        }
                    }
                }
                if (hasAvatar) break;
            }

            let hasCover = false;
            const coverSels = [
                'img[data-imgperflogname="profileCoverPhoto"]',
                'a[aria-label*="صورة الغلاف"] img, a[aria-label*="Cover photo"] img',
                'div[aria-label*="صورة الغلاف"] img, div[aria-label*="Cover photo"] img',
                'img.profile-cover'
            ];
            for (const sel of coverSels) {
                const els = Array.from(root.querySelectorAll(sel));
                for (const el of els) {
                    const src = el.getAttribute('src') || '';
                    if (isRealImg(src)) {
                        hasCover = true;
                        break;
                    }
                }
                if (hasCover) break;
            }
            if (!hasCover) {
                const topImgs = Array.from(root.querySelectorAll('img'));
                for (const img of topImgs) {
                    const src = img.getAttribute('src') || '';
                    if (!isRealImg(src)) continue;
                    const rect = img.getBoundingClientRect ? img.getBoundingClientRect() : {width: 0, height: 0, top: 9999};
                    if (rect.width >= 320 && rect.height >= 110 && rect.top >= 0 && rect.top <= 420) {
                        hasCover = true;
                        break;
                    }
                }
            }

            const bioEl = root.querySelector('[data-testid="profile_bio"], .profile-bio');
            const bioExplicitText = bioEl ? (bioEl.innerText || '').trim() : '';

            const rawText = (root.innerText || document.body.innerText || '').slice(0, 7000);
            const articles = Array.from(root.querySelectorAll('[role="article"], .profile-post'));
            let postsCount = 0;
            for (const art of articles) {
                const txt = (art.innerText || '').trim();
                if (!txt || txt.length < 4) continue;
                if (/لا توجد منشورات|no posts available/i.test(txt)) continue;
                postsCount += 1;
            }
            return {
                name,
                hasAvatar,
                hasCover,
                bioExplicitText,
                rawText,
                postsCount,
            };
        }
    """)


def human_warmup_after_login(page: Page) -> None:
    """محاكاة تصفح بشري طبيعي قصير فور تسجيل الدخول قبل فحص البروفايل"""
    try:
        dismiss_dialogs(page)
    except Exception:
        pass
    try:
        smooth_scroll(page, scrolls=1)
    except Exception:
        pass
    try:
        _curved_mouse_move(page, random.uniform(280, 760), random.uniform(220, 520))
    except Exception:
        pass
    try:
        human_delay(0.9, 1.7)
    except Exception:
        pass


def inspect_facebook_profile_quality(
    page: Page,
    navigate: bool = True,
    on_profile_loaded=None,
) -> dict:
    """
    فحص اكتمال وجودة البروفايل الشخصي لحساب فيسبوك بعد تسجيل الدخول:
    1) اسم عربي مناسب
    2) صورة شخصية
    3) صورة خلفية (غلاف)
    4) سيرة ذاتية (نبذة)
    5) الجامعة / الدراسة
    6) الحالة الاجتماعية
    7) منشور أو منشوران على الأقل
    """
    try:
        if navigate:
            try:
                dismiss_dialogs(page)
            except Exception:
                pass
            page.goto("https://www.facebook.com/me", wait_until="domcontentloaded", timeout=25000)
            human_delay(1.4, 2.3)
            try:
                dismiss_dialogs(page)
            except Exception:
                pass
            # انتظار اكتمال تحميل شجرة React للاسم/المحتوى الرئيسي قبل القراءة (حتى ~5.5 ث)
            for _ in range(5):
                try:
                    hydrated = page.evaluate("""
                        () => {
                            const main = document.querySelector('div[role="main"]') || document.body;
                            const h1 = main ? main.querySelector('h1') : null;
                            const txt = (main && main.innerText) ? main.innerText.trim() : '';
                            return Boolean((h1 && h1.innerText.trim().length >= 2) || txt.length > 260);
                        }
                    """)
                    if hydrated:
                        break
                except Exception:
                    break
                time.sleep(0.9)
            try:
                smooth_scroll(page, scrolls=2)
            except Exception:
                pass
            try:
                _curved_mouse_move(page, random.uniform(320, 820), random.uniform(200, 480))
            except Exception:
                pass
            human_delay(0.8, 1.5)
            if callable(on_profile_loaded):
                try:
                    on_profile_loaded(page)
                except Exception:
                    pass

        m = _extract_profile_dom_metrics(page)
        raw_text = str(m.get("rawText") or "")
        filtered_lines = [
            ln.strip() for ln in raw_text.splitlines()
            if ln.strip() and not _EMPTY_PROMPT_RE.search(ln)
        ]
        clean_text = "\n".join(filtered_lines)

        has_edit_bio = bool(re.search(r"تعديل (?:السيرة الذاتية|النبذة المختصرة)|Edit\s+bio", clean_text, re.IGNORECASE))
        has_add_bio = bool(re.search(r"(?:إضافة|أضف)\s+(?:سيرة ذاتية|نبذة)|Add\s+(?:a\s+)?bio", raw_text, re.IGNORECASE))
        bio_explicit = str(m.get("bioExplicitText") or "").strip()

        has_edu = bool(_EDU_RE.search(clean_text))
        has_rel = bool(_REL_RE.search(clean_text))
        has_bio = bool(bio_explicit or (has_edit_bio and not has_add_bio))

        # إذا لم تظهر النبذة/الجامعة/الحالة الاجتماعية في الواجهة الرئيسية، نفحص تبويب "حول" /me/about
        if navigate and not (has_edu and has_rel):
            try:
                page.goto("https://www.facebook.com/me/about", wait_until="domcontentloaded", timeout=20000)
                human_delay(1.0, 1.8)
                about_text = page.evaluate("""
                    () => (document.querySelector('div[role="main"]')?.innerText || document.body.innerText || '').slice(0, 7000)
                """)
                about_clean = "\n".join(
                    ln.strip() for ln in str(about_text or "").splitlines()
                    if ln.strip() and not _EMPTY_PROMPT_RE.search(ln)
                )
                if not has_edu:
                    has_edu = bool(_EDU_RE.search(about_clean))
                if not has_rel:
                    has_rel = bool(_REL_RE.search(about_clean))
                if not has_bio and re.search(r"تعديل (?:السيرة الذاتية|النبذة)|Edit\s+bio", about_clean, re.IGNORECASE):
                    has_bio = True
            except Exception:
                pass

        profile_name = str(m.get("name") or "").strip()
        posts_count = int(m.get("postsCount") or 0)

        checks = {
            "arabic_name": _is_good_arabic_profile_name(profile_name),
            "avatar": bool(m.get("hasAvatar")),
            "cover": bool(m.get("hasCover")),
            "bio": bool(has_bio),
            "university": bool(has_edu),
            "relationship": bool(has_rel),
            "posts": posts_count >= 1,
        }
        missing_keys = [k for k, ok in checks.items() if not ok]
        missing_labels = [_PROFILE_REQUIREMENT_LABELS[k] for k in missing_keys]
        passed_cnt = sum(1 for ok in checks.values() if ok)

        return {
            "checked": True,
            "passed": len(missing_keys) == 0,
            "score": passed_cnt,
            "total": len(checks),
            "profile_name": profile_name,
            "posts_count": posts_count,
            "checks": checks,
            "missing_keys": missing_keys,
            "missing_labels": missing_labels,
        }
    except Exception as e:
        return {
            "checked": False,
            "passed": False,
            "score": 0,
            "total": len(_PROFILE_REQUIREMENT_LABELS),
            "profile_name": "",
            "posts_count": 0,
            "checks": {},
            "missing_keys": [],
            "missing_labels": [],
            "error": str(e)[:120],
        }


