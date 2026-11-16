# -*- coding: utf-8 -*-
"""
أداة التجديد التلقائي الفوري لكوكيز Smailpro
-------------------------------------------
تفتح نافذة كروم حقيقية أمامك، تقوم بتسجيل الدخول في Smailpro،
وتقوم الأداة بسحب الكوكي وتحديث البوت فوراً واختبار إنشاء بريد جيميل.
"""
import os
import sys
import time
from playwright.sync_api import sync_playwright

CHROME_PATHS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expanduser(r"~\AppData\Local\Google\Chrome\Application\chrome.exe")
]
CHROME_BIN = next((p for p in CHROME_PATHS if os.path.exists(p)), None)

TARGET_PATHS = [
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "smailpro_cookie.txt"),
    r"C:\Users\XPRISTO\Downloads\LikeStory_TempMail_Project\mail_engines\smailpro_cookie.txt",
    r"d:\platform-tools\api\smailpro_cookie.txt",
    r"d:\platform-tools\fb_operator\mail_engines\smailpro_cookie.txt",
    r"C:\Users\XPRISTO\Desktop\HUGGINGFACE_UPLOAD\smailpro_cookie.txt",
    r"C:\Users\XPRISTO\Desktop\HUGGINGFACE_UPLOAD\fb_operator\mail_engines\smailpro_cookie.txt",
    os.path.expanduser(r"~\.fb_operator_data\smailpro_cookie.txt")
]

def main():
    print("=" * 65)
    print("🔑 أداة التجديد الذكي لكوكيز Smailpro (جيميل وأوتلوك)")
    print("=" * 65)
    print("🚀 جاري فتح متصفح كروم أمامك الآن...")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=CHROME_BIN,
            headless=False,
            args=["--disable-blink-features=AutomationControlled"]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        print("🌐 جاري التوجيه إلى صفحة Smailpro...")
        page.goto("https://smailpro.com/temporary-email", wait_until="domcontentloaded")
        
        print("\n" + "🟢" * 25)
        print("👉 نافذة المتصفح مفتوحة أمامك الآن على الشاشة.")
        print("👉 اضغط على زر (Sign in / Login) في أعلى الصفحة وسجل دخولك بحسابك.")
        print("👉 بمجرد اكتمال تسجيل الدخول في الموقع، ارجع هنا واضغط [Enter].")
        print("🟢" * 25 + "\n")
        
        try:
            input("⌨️ اضغط [Enter] بعد تسجيل دخولك في الموقع لحفظ الكوكي وتحديث البوت... ")
        except KeyboardInterrupt:
            print("\n❌ تم الإلغاء.")
            browser.close()
            return
            
        cookies = context.cookies()
        cookie_str = "; ".join([f"{c['name']}={c['value']}" for c in cookies if 'xsrf' in c['name'].lower() or 'session' in c['name'].lower() or 'sonjj' in c['name'].lower()])
        if not cookie_str:
            cookie_str = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
            
        browser.close()
        
    print(f"\n🍪 تم استخراج الكوكي الجديد بنجاح (الطول: {len(cookie_str)})")
    
    # حفظ الكوكي في كافة مسارات المشروع
    for path in set(TARGET_PATHS):
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(cookie_str)
            print(f"✔️ تم تحديث الكوكي في: {path}")
        except Exception as e:
            print(f"⚠️ تعذر التحديث في {path}: {e}")
            
    # اختبار فوري
    print("\n🧪 جاري اختبار إنشاء بريد جيميل الآن بالكوكي الجديد...")
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    from smailpro_api import SmailProAPI
    api = SmailProAPI(cookie=cookie_str)
    res = api.create_mailbox("gmail.com")
    
    if res.get("success"):
        print("\n" + "🎉" * 25)
        print(f"✅ نجاح ساحق! تم إنشاء بريد جيميل بنجاح:")
        print(f"📧 البريد: {res.get('address')}")
        print("🚀 البوت عاد للعمل الآن بكامل قوته لجميع المستخدمين!")
        print("🎉" * 25)
    else:
        print(f"⚠️ نتيجة الاختبار: {res.get('error')}")
        print("💡 تأكد من أنك قمت بتسجيل الدخول الفعلي في الموقع قبل الضغط على Enter.")

if __name__ == "__main__":
    main()
