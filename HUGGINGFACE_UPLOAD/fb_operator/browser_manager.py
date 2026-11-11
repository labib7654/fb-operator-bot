"""
إدارة تشغيل المتصفح، محاكاة السلوك البشري، وتسجيل الدخول التلقائي
مدعوم ببيئة سطح المكتب الافتراضية (Xvfb Virtual Display) وحقن التخفي الكامل (Stealth Anti-Detection)
لتشغيل متصفح حقيقي 100% كما لو كان يعمل على شاشة لابتوب حقيقية بدقة 1920x1080.
"""

import os
import re
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
    """استعادة الجلسة المحفوظة (storage_state) إلى المتصفح قبل التوجه إلى فيسبوك"""
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
        return True
    except Exception:
        return False


def _detect_arkose_captcha(page: Page) -> str:
    """الكشف السلبي عن تحدي Arkose MatchKey أو تحقق الإنسان للتوقف الآمن دون التفاعل معه"""
    curr_url = (getattr(page, "url", "") or "").lower()
    if any(k in curr_url for k in ("arkoselabs", "funcaptcha", "/challenge")):
        return "لغز تحقق من الإنسان Arkose Labs CAPTCHA — يتطلب استيراد جلسة صالحة من متصفحك"
    try:
        iframe_loc = page.locator('iframe[src*="arkose"], iframe[src*="funcaptcha"], iframe[src*="captcha"]')
        if iframe_loc.count() > 0:
            return "لغز تحقق من الإنسان Arkose Labs CAPTCHA — يتطلب استيراد جلسة صالحة من متصفحك"
    except Exception:
        pass
    try:
        snippet = page.evaluate("() => (document.body && document.body.innerText ? document.body.innerText.slice(0, 1800) : '')")
        if isinstance(snippet, str) and snippet:
            low = snippet.lower()
            if any(k in low for k in (
                "arkose labs",
                "matchkey",
                "أكمل تحدي",
                "تحقق من أنك إنسان",
                "verify that you're human",
                "complete a challenge",
                "confirm you're human",
                "solve a puzzle",
            )):
                return "لغز تحقق من الإنسان Arkose Labs CAPTCHA — يتطلب استيراد جلسة صالحة من متصفحك"
    except Exception:
        pass
    return ""


def check_facebook_page_access(page: Page) -> tuple[bool, str]:
    """
    فحص حالة الصفحة الحية في فيسبوك لاكتشاف الحجب أو انتهاء الجلسة أو تحدي CAPTCHA أو عدم توفر المحتوى فوراً
    بدلاً من إهدار الوقت في البحث عن أزرار غير موجودة.
    """
    arkose_msg = _detect_arkose_captcha(page)
    if arkose_msg:
        return False, arkose_msg

    curr_url = (getattr(page, "url", "") or "").lower()
    if any(x in curr_url for x in ("checkpoint", "two_step_verification", "/recover/")):
        return False, "الحساب يطلب تحقق أمان (Checkpoint / 2FA)"
    if any(x in curr_url for x in ("suspended", "disabled", "/account_status")):
        return False, "الحساب مقيد أو معطل من فيسبوك"
    if any(x in curr_url for x in ("login.php", "/login/", "login/?next=")):
        return False, "انتهت صلاحية الجلسة والحساب غير مسجل دخوله"

    try:
        has_email = page.locator('input[name="email"]').first.is_visible(timeout=350)
        has_pass = page.locator('input[name="pass"]').first.is_visible(timeout=350)
        if has_email and has_pass:
            return False, "ظهرت صفحة تسجيل الدخول (الجلسة غير نشطة)"
    except Exception:
        pass

    try:
        snippet = page.evaluate("() => (document.body && document.body.innerText ? document.body.innerText.slice(0, 1500) : '')")
        if isinstance(snippet, str) and snippet:
            low = snippet.lower()
            if any(k in low for k in (
                "هذا المحتوى غير متوفر", "content isn't available",
                "page isn't available", "الصفحة غير متوفرة", "broken link"
            )):
                return False, "الرابط أو المحتوى المستهدف غير متاح أو خاص أو محذوف"
            if any(k in low for k in ("تم تعليق حسابك", "your account has been suspended", "تم تعطيل حسابك", "account has been disabled")):
                return False, "الحساب معطل أو موقوف من إدارة فيسبوك"
    except Exception:
        pass

    return True, ""

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

def launch_account_browser(playwright_instance, profile_dir: str | Path, visible: bool = True) -> BrowserContext:
    """
    تشغيل متصفح جوجل كروم الحقيقي ببروفايل مستمر للحساب.
    إذا كان النظام يحتوي على شاشة عرض افتراضية (Xvfb في السيرفر أو شاشة محلية)،
    يتم تشغيل المتصفح بوضع Headless=False ليعمل تماماً كأنه حاسوب مكتبي حقيقي.
    """
    profile_path = resolve_cross_platform_profile(profile_dir)
    profile_path.mkdir(parents=True, exist_ok=True)
    _cleanup_stale_profile_locks(profile_path)

    # التحقق من وجود شاشة عرض افتراضية (Xvfb أو خادم X11)
    has_display = bool(os.environ.get("DISPLAY"))
    
    # إذا كانت هناك شاشة عرض متاحة (مثل سيرفر جيت هب مع Xvfb)، نلغي وضع الهيدلس ليعمل المتصفح كسطح مكتب حقيقي
    use_headless = not visible and not has_display

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
        "--start-maximized",
        "--window-size=1920,1080",
        "--disable-notifications",
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-dev-shm-usage",
        "--lang=ar-EG,ar,en-US,en"
    ]

    real_user_agent = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    )

    launch_kwargs = {
        "user_data_dir": str(profile_path),
        "headless": use_headless,
        "args": args,
        "viewport": {"width": 1920, "height": 1080},
        "screen": {"width": 1920, "height": 1080},
        "device_scale_factor": 1,
        "user_agent": real_user_agent,
        "locale": "ar-EG"
    }

    try:
        # محاولة فتح القناة الرسمية لمتصفح كروم المثبت بالنظام
        context = playwright_instance.chromium.launch_persistent_context(
            channel="chrome", **launch_kwargs
        )
    except Exception:
        # في حال عدم توفر قناة كروم، استخدام كروميوم مع كامل الخصائص
        context = playwright_instance.chromium.launch_persistent_context(**launch_kwargs)

    # حقن سكريبت التخفي المتقدم المضاد لكشف الروبوتات وفلاتر فيسبوك (Stealth Shield)
    stealth_script = """
        // 1. مسح مؤشر الأتمتة navigator.webdriver
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined
        });

        // 2. محاكاة كائن نافذة كروم الطبيعية window.chrome
        window.chrome = {
            app: {
                isInstalled: false,
                InstallState: { DISABLED: 'disabled', INSTALLED: 'installed', NOT_INSTALLED: 'not_installed' },
                RunningState: { CANNOT_RUN: 'cannot_run', READY_TO_RUN: 'ready_to_run', RUNNING: 'running' }
            },
            runtime: {
                OnInstalledReason: { CHROME_UPDATE: 'chrome_update', INSTALL: 'install', SHARED_MODULE_UPDATE: 'shared_module_update', UPDATE: 'update' },
                OnRestartRequiredReason: { APP_UPDATE: 'app_update', OS_UPDATE: 'os_update', PERIODIC: 'periodic' },
                PlatformArch: { ARM: 'arm', ARM64: 'arm64', MIPS: 'mips', MIPS64: 'mips64', X86_32: 'x86-32', X86_64: 'x86-64' },
                PlatformNaclArch: { ARM: 'arm', MIPS: 'mips', MIPS64: 'mips64', X86_32: 'x86-32', X86_64: 'x86-64' },
                PlatformOs: { ANDROID: 'android', CROS: 'cros', LINUX: 'linux', MAC: 'mac', OPENBSD: 'openbsd', WIN: 'win' }
            },
            csi: function() {},
            loadTimes: function() {}
        };

        // 3. محاكاة مكونات إضافات المتصفح Plugins الطبيعية
        Object.defineProperty(navigator, 'plugins', {
            get: () => {
                const plugins = [
                    { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
                    { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: '' },
                    { name: 'Native Client', filename: 'internal-nacl-plugin', description: '' }
                ];
                plugins.item = (i) => plugins[i];
                plugins.namedItem = (name) => plugins.find(p => p.name === name);
                plugins.refresh = () => {};
                return plugins;
            }
        });

        // 4. محاكاة كارت الشاشة الطبيعي (Intel UHD Graphics) بدلاً من SwiftShader الخاص بالبوتات
        const getParameterProto = WebGLRenderingContext.prototype.getParameter;
        WebGLRenderingContext.prototype.getParameter = function(param) {
            if (param === 37445) return 'Intel Inc.'; // UNMASKED_VENDOR_WEBGL
            if (param === 37446) return 'ANGLE (Intel, Intel(R) UHD Graphics 630 Direct3D11 vs_5_0 ps_5_0, D3D11)'; // UNMASKED_RENDERER_WEBGL
            return getParameterProto.apply(this, arguments);
        };
        if (typeof WebGL2RenderingContext !== 'undefined') {
            const getParameterProto2 = WebGL2RenderingContext.prototype.getParameter;
            WebGL2RenderingContext.prototype.getParameter = function(param) {
                if (param === 37445) return 'Intel Inc.';
                if (param === 37446) return 'ANGLE (Intel, Intel(R) UHD Graphics 630 Direct3D11 vs_5_0 ps_5_0, D3D11)';
                return getParameterProto2.apply(this, arguments);
            };
        }

        // 5. محاكاة اللغات والإشعارات
        Object.defineProperty(navigator, 'languages', {
            get: () => ['ar-EG', 'ar', 'en-US', 'en']
        });

        if (navigator.credentials) {
            navigator.credentials.get = () => Promise.resolve(null);
            navigator.credentials.store = () => Promise.resolve();
            navigator.credentials.create = () => Promise.resolve(null);
            navigator.credentials.preventSilentAccess = () => Promise.resolve();
        }
    """
    context.add_init_script(stealth_script)
    _CTX_PROFILES[id(context)] = profile_path
    restore_account_storage_state(context, profile_path)
    return context

def auto_login_facebook(context: BrowserContext, page: Page, email: str, password: str, status_callback=None, max_wait: int = 90) -> bool:
    """
    تسجيل الدخول التلقائي في فيسبوك باستخدام الإيميل وكلمة السر المحفوظين
    مع كتابة بشرية والتعامل مع رمز التحقق (2FA) وتثبيت الجلسة
    """
    def log(msg: str):
        if status_callback:
            status_callback(msg)
        print(f"[Login] {msg}")

    set_login_error(context, "")

    # 1. التحقق الحي من الجلسة (عدم الاكتفاء بوجود كوكي c_user لتجنب الكوكيز المنتهية)
    is_logged, fb_id = check_facebook_login_cookies(context)
    if is_logged:
        curr_now = (getattr(page, "url", "") or "").lower()
        if "facebook.com" not in curr_now:
            try:
                page.goto("https://www.facebook.com/", wait_until="domcontentloaded", timeout=35000)
                time.sleep(1.5)
                dismiss_dialogs(page)
            except Exception as e:
                log(f"تنبيه شبكة أثناء التحقق من الجلسة: {e}")

        ok_live, live_reason = check_facebook_page_access(page)
        is_still_logged, _ = check_facebook_login_cookies(context)
        if is_still_logged and ok_live:
            save_account_storage_state(context)
            log("تم التحقق من الجلسة الحية: الحساب نشط ومسجل دخوله بنجاح.")
            return True

        if any(tag in live_reason for tag in ("Checkpoint", "2FA", "معطل", "مقيد", "Arkose", "CAPTCHA")):
            set_login_error(context, live_reason)
            log(f"[-] {live_reason}")
            return False

        log(f"تنبيه: الجلسة المحفوظة منتهية ({live_reason or 'يتطلب دخول'})، جاري محاولة إعادة الدخول...")

    log("جاري التوجه إلى موقع فيسبوك...")
    try:
        page.goto("https://www.facebook.com/", wait_until="domcontentloaded", timeout=60000)
    except Exception as e:
        log(f"تنبيه بالشبكة أثناء الفتح: {e}")

    time.sleep(2.0)
    dismiss_dialogs(page)

    # فحص مجدداً بعد فتح الصفحة
    ok_after, after_reason = check_facebook_page_access(page)
    is_logged, fb_id = check_facebook_login_cookies(context)
    if is_logged and ok_after:
        save_account_storage_state(context)
        log("تم التحقق من الجلسة، الحساب مسجل دخوله بالفعل.")
        return True

    if any(tag in after_reason for tag in ("Arkose", "CAPTCHA", "معطل", "مقيد")):
        set_login_error(context, after_reason)
        log(f"[-] {after_reason}")
        return False

    if not email or not password:
        reason = after_reason or "لا توجد بيانات دخول محفوظة والجلسة غير نشطة"
        set_login_error(context, reason)
        log(f"تنبيه: {reason}")
        return False

    # 2. تعبئة الإيميل وكلمة السر بمحاكاة نقرات الكيبورد والأحداث الحقيقية
    try:
        log("كتابة البريد الإلكتروني...")
        email_selectors = [
            'input[name="email"]',
            'input#email',
            'input[data-testid="royal_email"]',
            'input[aria-label*="البريد"]',
            'input[placeholder*="البريد"]',
            'input[type="text"]',
            'input[type="email"]'
        ]
        email_input = None
        for _ in range(12):
            for sel in email_selectors:
                loc = page.locator(sel).first
                if loc.is_visible(timeout=1000):
                    email_input = loc
                    break
            if email_input:
                break
            time.sleep(1.0)

        if email_input:
            email_input.click()
            time.sleep(random.uniform(0.3, 0.7))
            email_input.fill("")
            time.sleep(0.2)
            email_input.press_sequentially(email, delay=random.randint(65, 120))
            time.sleep(random.uniform(0.6, 1.3))
        else:
            set_login_error(context, "تعذر العثور على حقل البريد الإلكتروني بصفحة الدخول")
            log("[-] تعذر العثور على حقل إدخال البريد الإلكتروني بعد الانتظار.")
            return False

        log("كتابة كلمة المرور بمحاكاة بشرية...")
        pass_selectors = [
            'input[name="pass"]',
            'input#pass',
            'input[data-testid="royal_pass"]',
            'input[aria-label*="كلمة"]',
            'input[placeholder*="كلمة"]',
            'input[type="password"]'
        ]
        pass_input = None
        for _ in range(8):
            for sel in pass_selectors:
                loc = page.locator(sel).first
                if loc.is_visible(timeout=1000):
                    pass_input = loc
                    break
            if pass_input:
                break
            time.sleep(1.0)

        if pass_input:
            pass_input.click()
            time.sleep(random.uniform(0.3, 0.6))
            pass_input.fill("")
            time.sleep(0.2)
            pass_input.press_sequentially(password, delay=random.randint(60, 115))
            time.sleep(random.uniform(0.8, 1.6))
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
            'button:has-text("تسجيل الدخول")'
        ]

        btn_clicked = False
        for sel in btn_selectors:
            loc = page.locator(sel).first
            if loc.is_visible(timeout=2000):
                loc.click()
                btn_clicked = True
                break

        if not btn_clicked:
            page.keyboard.press("Enter")

    except Exception as e:
        log(f"تعذر كتابة البيانات في حقول الدخول: {e}")
        return False

    # 3. مراقبة النتيجة حتى 90 ثانية (لكل السيناريوهات: دخول مباشر أو طلب 2FA)
    log("بانتظار استجابة فيسبوك وتثبيت الجلسة...")
    start_time = time.time()
    warned_2fa = False

    while time.time() - start_time < max_wait:
        if len(context.pages) == 0:
            log("تم إغلاق المتصفح من قبل المستخدم.")
            return False

        # فحص نجاح الدخول عبر الكوكيز مع استبعاد صفحات التحقق أو التجميد
        curr_url = (page.url or "").lower()
        blocked_state = any(x in curr_url for x in ("checkpoint", "two_step_verification", "login.php", "suspended", "disabled"))
        is_logged, fb_id = check_facebook_login_cookies(context)
        if is_logged and not blocked_state:
            time.sleep(3.0)  # مهلة لتثبيت الجلسة على القرص
            save_account_storage_state(context)
            log("تم تسجيل الدخول وتثبيت الجلسة الدائمة بنجاح!")
            return True

        # التوقف الآمن الفوري إذا ظهر لغز Arkose CAPTCHA أو حساب موقوف
        arkose_reason = _detect_arkose_captcha(page)
        if arkose_reason:
            set_login_error(context, arkose_reason)
            log(f"[-] {arkose_reason}")
            return False

        # فحص إذا ظهرت صفحة رمز التحقق 2FA
        if ("checkpoint" in curr_url or "two_step_verification" in curr_url) and not warned_2fa:
            log("تنبيه: فيسبوك يطلب رمز الأمان (2FA). يرجى إدخال الرمز في المتصفح الآن...")
            warned_2fa = True

        # فحص إذا ظهرت رسالة خطأ صريحة في كلمة المرور
        try:
            error_msg = page.locator('#error_box, div[role="alert"]').first
            if error_msg.is_visible(timeout=500):
                txt = error_msg.inner_text()
                if "incorrect" in txt.lower() or "غير صحيحة" in txt:
                    set_login_error(context, "كلمة المرور أو البريد الإلكتروني غير صحيحين")
                    log("تنبيه: كلمة المرور أو البريد الإلكتروني غير صحيحين!")
                    return False
        except Exception:
            pass

        time.sleep(1.5)

    # فحص أخير
    curr_final = (page.url or "").lower()
    blocked_final = any(x in curr_final for x in ("checkpoint", "two_step_verification", "login.php", "suspended", "disabled"))
    is_logged, fb_id = check_facebook_login_cookies(context)
    if is_logged and not blocked_final:
        save_account_storage_state(context)
        log("تم تسجيل الدخول بنجاح.")
        return True

    ok_f, f_reason = check_facebook_page_access(page)
    set_login_error(context, f_reason or "انتهت مهلة انتظار تسجيل الدخول (تحقق من كلمة السر أو 2FA)")
    log("انتهت مهلة الانتظار دون اكتمال تسجيل الدخول.")
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

