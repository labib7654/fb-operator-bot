# -*- coding: utf-8 -*-
"""
أداة تحديث كوكيز Smailpro الآمنة والخفيفة (بدون لمس ملفات المتصفح أو البروفايل)
-------------------------------------------------------------------------------
تفتح صفحة Smailpro في متصفحك الطبيعي بدون أي استنساخ أو تشغيل نوافذ إضافية.
بمجرد نسخ الكوكي ولصقه هنا، تقوم الأداة بتحديث كافة ملفات البوت وفحصه فوراً.
"""
import os
import sys
import webbrowser

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
    print("🔑 أداة تحديث كوكيز Smailpro الآمنة (جيميل وأوتلوك)")
    print("=" * 65)
    print("1. سيتم فتح صفحة Smailpro في متصفحك الحالي المفتوح طبيعياً.")
    print("2. بعد تسجيل دخولك بحسابك، الصق الكوكي هنا واضغط [Enter].")
    print("=" * 65)
    
    webbrowser.open("https://smailpro.com/temporary-email")
    
    print("\n👉 الصق نص الكوكي هنا (أو اضغط Enter للإلغاء):")
    cookie_val = input("🍪 الكوكي: ").strip()
    
    if not cookie_val:
        print("❌ لم يتم إدخال أي كوكي. تم الإلغاء بأمان.")
        return
        
    updated = 0
    for p in TARGET_PATHS:
        try:
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w", encoding="utf-8") as f:
                f.write(cookie_val)
            print(f"✔️ تم التحديث في: {p}")
            updated += 1
        except Exception as e:
            print(f"⚠️ تعذر التحديث في {p}: {e}")
            
    print(f"\n✅ اكتمل التحديث بنجاح في {updated} مواقع.")

if __name__ == "__main__":
    main()
