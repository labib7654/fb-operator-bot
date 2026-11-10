"""
إدارة تشغيل المتصفح، محاكاة السلوك البشري، وتسجيل الدخول التلقائي
"""

import time
import random
from pathlib import Path
from playwright.sync_api import sync_playwright, BrowserContext, Page
from fb_operator.config import DEFAULT_MIN_DELAY, DEFAULT_MAX_DELAY

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
    يحفظ الكوكيز والتسجيل الدائم ويعزل كل حساب في مجلد خاص.
    """
    profile_path = Path(profile_dir).resolve()
    profile_path.mkdir(parents=True, exist_ok=True)

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
        "--disable-notifications"
    ]

    context = playwright_instance.chromium.launch_persistent_context(
        user_data_dir=str(profile_path),
        channel="chrome",
        headless=not visible,
        args=args,
        no_viewport=True,
        locale="ar-EG"
    )

    # إخفاء معلم الأتمتة وتعطيل نوافذ اقتراح الحسابات السابقة (FedCM / Credential Manager)
    context.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined
        });
        if (navigator.credentials) {
            navigator.credentials.get = () => Promise.resolve(null);
            navigator.credentials.store = () => Promise.resolve();
            navigator.credentials.create = () => Promise.resolve(null);
            navigator.credentials.preventSilentAccess = () => Promise.resolve();
        }
    """)

    return context

def auto_login_facebook(context: BrowserContext, page: Page, email: str, password: str, status_callback=None) -> bool:
    """
    تسجيل الدخول التلقائي في فيسبوك باستخدام الإيميل وكلمة السر المحفوظين
    مع كتابة بشرية والتعامل مع رمز التحقق (2FA) وتثبيت الجلسة
    """
    def log(msg: str):
        if status_callback:
            status_callback(msg)
        print(f"[Login] {msg}")

    # 1. التحقق أولاً: هل الجلسة مسجلة مسبقاً؟
    is_logged, fb_id = check_facebook_login_cookies(context)
    if is_logged:
        log("الجلسة نشطة ومسجلة مسبقاً بنجاح.")
        return True

    log("جاري التوجه إلى موقع فيسبوك...")
    try:
        page.goto("https://www.facebook.com/", wait_until="domcontentloaded", timeout=60000)
    except Exception as e:
        log(f"تنبيه بالشبكة أثناء الفتح: {e}")

    time.sleep(2.0)
    dismiss_dialogs(page)

    # فحص مجدداً بعد فتح الصفحة
    is_logged, fb_id = check_facebook_login_cookies(context)
    if is_logged:
        log("تم التحقق من الجلسة، الحساب مسجل دخوله بالفعل.")
        return True

    if not email or not password:
        log("تنبيه: لم يتم العثور على بريد أو كلمة مرور مسجلة لهذا الحساب.")
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

    while time.time() - start_time < 90:
        if len(context.pages) == 0:
            log("تم إغلاق المتصفح من قبل المستخدم.")
            return False

        # فحص نجاح الدخول عبر الكوكيز
        is_logged, fb_id = check_facebook_login_cookies(context)
        if is_logged:
            time.sleep(3.0)  # مهلة لتثبيت الجلسة على القرص
            log("تم تسجيل الدخول وتثبيت الجلسة الدائمة بنجاح!")
            return True

        # فحص إذا ظهرت صفحة رمز التحقق 2FA
        curr_url = page.url
        if ("checkpoint" in curr_url or "two_step_verification" in curr_url) and not warned_2fa:
            log("تنبيه: فيسبوك يطلب رمز الأمان (2FA). يرجى إدخال الرمز في المتصفح الآن...")
            warned_2fa = True

        # فحص إذا ظهرت رسالة خطأ صريحة في كلمة المرور
        try:
            error_msg = page.locator('#error_box, div[role="alert"]').first
            if error_msg.is_visible(timeout=500):
                txt = error_msg.inner_text()
                if "incorrect" in txt.lower() or "غير صحيحة" in txt:
                    log("تنبيه: كلمة المرور أو البريد الإلكتروني غير صحيحين!")
                    return False
        except Exception:
            pass

        time.sleep(1.5)

    # فحص أخير
    is_logged, fb_id = check_facebook_login_cookies(context)
    if is_logged:
        log("تم تسجيل الدخول بنجاح.")
        return True

    log("انتهت مهلة الانتظار دون اكتمال تسجيل الدخول.")
    return False

def dismiss_dialogs(page: Page) -> None:
    """إغلاق النوافذ المنبثقة الشائعة في فيسبوك"""
    dismiss_selectors = [
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
            if elem.is_visible(timeout=800):
                elem.click()
                time.sleep(0.5)
        except Exception:
            pass

def smooth_scroll(page: Page, scrolls: int = 2) -> None:
    """تمرير الصفحة بسلاسة بشرية لتحميل المنشورات والتفاعل معها"""
    for _ in range(scrolls):
        delta = random.randint(350, 650)
        page.mouse.wheel(0, delta)
        time.sleep(random.uniform(0.8, 1.8))
