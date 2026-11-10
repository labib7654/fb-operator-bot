"""
محرك تنفيذ العمليات والإجراءات على حسابات فيسبوك المستهدفة
"""

import sys
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

import time
import random
import re
from playwright.sync_api import Page, Locator
from fb_operator.browser_manager import human_delay, dismiss_dialogs, smooth_scroll

def close_floating_chats(page: Page) -> None:
    """إغلاق وتطهير أي نافذة دردشة ماسنجر عائمة في أسفل الصفحة لمنع اعتراض النقرات والتركيز"""
    try:
        page.evaluate("""() => {
            document.querySelectorAll('[data-pagelet="ChatTabs"], [role="complementary"]').forEach(el => {
                const closeBtn = el.querySelector('div[aria-label*="إغلاق"], div[aria-label*="Close"], div[aria-label*="تصغير"]');
                if (closeBtn) closeBtn.click();
                else el.remove();
            });
            document.querySelectorAll('div[aria-label="إغلاق الدردشة"], div[aria-label="Close chat"], div[aria-label="إغلاق"][role="button"]').forEach(btn => {
                try { btn.click(); } catch(e) {}
            });
        }""")
    except Exception:
        pass

    chat_close_selectors = [
        'div[aria-label*="إغلاق الدردشة"]',
        'div[aria-label*="Close chat"]',
        'div[aria-label*="تصغير الدردشة"]',
        'div[aria-label*="إغلاق"][role="button"]',
        'div[aria-label="Close"][role="button"]'
    ]
    for sel in chat_close_selectors:
        try:
            for btn in page.locator(sel).all():
                if btn.is_visible():
                    btn.dispatch_event('click')
                    time.sleep(0.2)
        except Exception:
            pass

def navigate_to_target(page: Page, target_url: str) -> bool:
    """الانتقال لرابط الحساب المستهدف والتأكد من اكتمال التحميل"""
    # توحيد الرابط لسطح المكتب
    clean_url = target_url.replace("://m.facebook.com", "://www.facebook.com")
    clean_url = clean_url.replace("://mobile.facebook.com", "://www.facebook.com")
    clean_url = clean_url.replace("://web.facebook.com", "://www.facebook.com")

    print(f"\n[+] جاري التوجه إلى الرابط المستهدف: {clean_url}")
    try:
        try:
            page.goto(clean_url, wait_until="domcontentloaded", timeout=45000)
        except Exception:
            page.goto(clean_url, wait_until="commit", timeout=45000)
        human_delay(2.0, 3.5)
        dismiss_dialogs(page)
        close_floating_chats(page)
        return True
    except Exception as e:
        print(f"[-] تعذر فتح الرابط المستهدف: {e}")
        return False

def _find_posts(page: Page) -> list[Locator]:
    """العثور على كتل المنشورات الظاهرة في صفحة الحساب بسلاسة وثبات ودون قفزات عشوائية"""
    post_selectors = [
        'div[role="feed"] > div:has(div[role="button"][aria-label*="أعجبني"])',
        'div[role="feed"] > div:has(div[role="button"][aria-label*="Like" i])',
        'div[role="article"]',
        'div[data-pagelet*="ProfileTimeline"] div[role="article"]',
        'div[role="feed"] > div'
    ]

    for sel in post_selectors:
        locators = page.locator(sel).all()
        if locators and len(locators) > 0:
            return locators

    # إذا لم نجد منشورات بعد، نمرر تمريرة واحدة خفيفة
    page.evaluate("window.scrollBy({top: 400, behavior: 'smooth'})")
    human_delay(1.5, 2.0)

    for sel in post_selectors:
        locators = page.locator(sel).all()
        if locators and len(locators) > 0:
            return locators

    return page.locator('div[role="article"]').all()

def like_posts(page: Page, mode: str = "latest", count: int = 1) -> int:
    """
    التفاعل والإعجاب بمنشورات الحساب المستهدف بدقة تامة وبدون أي خبط أو إلغاء سابق.
    """
    dismiss_dialogs(page)
    close_floating_chats(page)
    posts = _find_posts(page)

    if not posts:
        print("[-] لم يتم العثور على أي منشورات ظاهرة في هذا الحساب للتفاعل معها.")
        return 0

    print(f"[i] تم رصد {len(posts)} منشوراً في الصفحة.")

    target_posts = posts[:1] if mode == "latest" else (posts[:count] if mode == "count" else posts)
    liked_count = 0

    for idx, post in enumerate(target_posts, start=1):
        try:
            # فحص زر الإعجاب داخل هذا المنشور تحديداً
            like_btn = post.locator(
                'div[role="button"][aria-label*="أعجبني"], '
                'div[role="button"][aria-label*="Like" i], '
                'div[role="button"]:has-text("أعجبني"), '
                'div[role="button"]:has-text("Like")'
            ).first

            if not like_btn.is_visible(timeout=3000):
                like_btn.scroll_into_view_if_needed(timeout=2000)

            if not like_btn.is_visible(timeout=2500):
                print(f"[-] المنشور رقم {idx}: لم يتم العثور على زر الإعجاب.")
                continue

            # التحقق إذا كان المنشور معجباً به مسبقاً لمنع إلغاء الإعجاب نهائياً
            aria_label = (like_btn.get_attribute("aria-label") or "").strip().lower()
            btn_text = (like_btn.inner_text() or "").strip().lower()
            is_pressed = like_btn.get_attribute("aria-pressed") == "true"

            is_already_liked = (
                is_pressed or
                any(word in aria_label for word in ["إزالة", "أعجبك", "تراجع", "إلغاء", "unlike", "remove"]) or
                any(word in btn_text for word in ["أعجبك", "إلغاء", "unlike"])
            )

            if is_already_liked:
                print(f"[+] المنشور رقم {idx}: معجب به مسبقاً، تم تخطيه حفاظاً على اللايك ومنع إزالته.")
                continue

            like_btn.click()
            liked_count += 1
            print(f"[+] المنشور رقم {idx}: تم الإعجاب بنجاح ودقة.")
            human_delay(2.0, 3.5)

        except Exception as e:
            print(f"[-] خطأ أثناء التفاعل مع المنشور {idx}: {e}")

    return liked_count

def comment_on_posts(page: Page, comment_text: str, mode: str = "latest", count: int = 1) -> int:
    """كتابة تعليق مباشر داخل حقل تعليقات المنشور بدقة تامة ودعم النوافذ المنبثقة دون إلغاء مبكر"""
    dismiss_dialogs(page)
    close_floating_chats(page)
    posts = _find_posts(page)

    if not posts:
        print("[-] لم يتم العثور على منشورات للتعليق عليها.")
        return 0

    target_posts = posts[:1] if mode == "latest" else (posts[:count] if mode == "count" else posts)
    commented_count = 0

    for idx, post in enumerate(target_posts, start=1):
        try:
            # 1. النقر على زر التعليق لفتح صندوق التعليق
            comment_btn = post.locator(
                'div[role="button"][aria-label*="Comment" i], '
                'div[role="button"][aria-label*="تعليق"], '
                'div[role="button"]:has-text("تعليق"), '
                'div[role="button"]:has-text("Comment")'
            ).first

            if comment_btn.is_visible(timeout=3000):
                comment_btn.click()
                human_delay(1.5, 2.5)

            # 2. تحديد حقل كتابة التعليق (يدعم وضع النافذة المنبثقة والوضع المضمن)
            input_box_selectors = [
                'div[aria-label*="اكتب تعليق"][role="textbox"]',
                'div[aria-label*="Write a comment"][role="textbox"]',
                'div[role="dialog"] div[role="textbox"][contenteditable="true"]',
                'div[role="article"] div[role="textbox"][contenteditable="true"]',
                'div[role="textbox"][contenteditable="true"]'
            ]

            input_box = None
            for i_sel in input_box_selectors:
                loc = page.locator(i_sel).first
                if loc.is_visible(timeout=3000):
                    input_box = loc
                    break

            if input_box:
                try:
                    input_box.scroll_into_view_if_needed(timeout=2000)
                except Exception:
                    pass
                human_delay(0.5, 1.0)
                try:
                    input_box.focus()
                except Exception:
                    try:
                        input_box.click(force=True, timeout=2000)
                    except Exception:
                        pass
                human_delay(0.4, 0.8)
                page.keyboard.type(comment_text, delay=random.randint(45, 85))
                human_delay(1.0, 1.8)
                page.keyboard.press("Enter")
                print(f"[+] المنشور رقم {idx}: تم إرسال التعليق بنجاح: '{comment_text}'")
                
                # انتظار 4.5 ثوانٍ ريثما ينتهي فيسبوك من نشر التعليق على السيرفر دون ضغط Escape
                human_delay(4.5, 6.0)
                commented_count += 1
            else:
                print(f"[-] المنشور رقم {idx}: تعذر الوصول لصندوق كتابة التعليق.")

        except Exception as e:
            print(f"[-] خطأ أثناء كتابة التعليق على المنشور {idx}: {e}")

    return commented_count

def _ensure_post_comments_expanded(page: Page, target_post) -> list:
    """فتح وتوسيع درج التعليقات في المنشور إذا كانت مطوية أو مخفية دون إعادة إغلاقها"""
    # 1. إذا كانت أزرار الرد ظاهرة بالفعل، فالتعليقات مفتوحة وموسعة مسبقاً!
    existing_replies = [r for r in page.locator('div[role="button"]:has-text("رد")').all() if r.is_visible()]
    if existing_replies:
        return existing_replies

    # 2. إذا كانت مخفية، ننقر لفتحها
    expand_selectors = [
        'div[role="button"]:has-text("عرض المزيد من التعليقات")',
        'span:has-text("عرض المزيد من التعليقات")',
        'span:has-text("عرض رد واحد")',
        'span:has-text("عرض ردين")',
        'div[role="button"][aria-label*="Comment" i]',
        'div[role="button"][aria-label*="تعليق"]'
    ]
    for sel in expand_selectors:
        try:
            btn = target_post.locator(sel).first
            if btn.is_visible(timeout=1500):
                btn.dispatch_event('click')
                human_delay(2.0, 3.0)
                break
        except Exception:
            continue

    reply_elements = [r for r in page.locator('div[role="button"]:has-text("رد")').all() if r.is_visible()]
    return reply_elements

def like_comment_on_post(page: Page, post_index: int = 1, comment_index: int = 1) -> bool:
    """
    الإعجاب بتعليق محدد داخل منشور:
    - post_index: رقم المنشور (افتراضياً 1 أحدث منشور)
    - comment_index: رقم التعليق داخل المنشور (افتراضياً 1 أول تعليق)
    """
    dismiss_dialogs(page)
    close_floating_chats(page)
    posts = _find_posts(page)
    if not posts:
        print("[-] لم يتم العثور على أي منشور.")
        return False

    target_post = posts[post_index - 1] if len(posts) >= post_index else posts[0]
    try:
        target_post.scroll_into_view_if_needed(timeout=3000)
        human_delay(1.0, 2.0)

        # 1. التأكد من فتح وتوسيع التعليقات
        _ensure_post_comments_expanded(page, target_post)

        # البحث عن أزرار الإعجاب الخاصة بالتعليقات (أزرار داخلية)
        like_btns = page.locator('div[role="button"][aria-label*="أعجبني"]').all()
        comment_likes = [b for b in like_btns if b.is_visible()]
        if len(comment_likes) > 1:
            target_like = comment_likes[comment_index] if len(comment_likes) > comment_index else comment_likes[1]
            target_like.dispatch_event('click')
            print(f"[+] تم وضع إعجاب بنجاح على التعليق رقم {comment_index} في المنشور {post_index}!")
            human_delay(2.0, 3.5)
            return True

        # طريقة بديلة: البحث عن نص "أعجبني" الصغير بجوار زر "رد"
        alt_likes = page.locator('span:has-text("أعجبني"), div[role="button"]:has-text("أعجبني")').all()
        for al in alt_likes:
            if al.is_visible():
                al.dispatch_event('click')
                print("[+] تم الإعجاب بالتعليق بنجاح عبر الخيار البديل!")
                human_delay(2.0, 3.5)
                return True

        print("[-] لم يتم العثور على زر إعجاب التعليق.")
        return False

    except Exception as e:
        print(f"[-] خطأ أثناء الإعجاب بالتعليق: {e}")
        return False

def reply_to_comment_on_post(page: Page, reply_text: str, post_index: int = 1, comment_index: int = 1) -> bool:
    """
    الرد المباشر على تعليق محدد داخل منشور:
    - reply_text: نص الرد
    - post_index: رقم المنشور (افتراضياً 1)
    - comment_index: رقم التعليق للرد عليه (افتراضياً 1)
    """
    if not reply_text:
        return False

    dismiss_dialogs(page)
    close_floating_chats(page)
    posts = _find_posts(page)
    if not posts:
        print("[-] لم يتم العثور على أي منشور.")
        return False

    target_post = posts[post_index - 1] if len(posts) >= post_index else posts[0]
    try:
        target_post.scroll_into_view_if_needed(timeout=3000)
        human_delay(1.0, 2.0)

        # 1. فتح درج التعليقات أولاً
        reply_btns = _ensure_post_comments_expanded(page, target_post)

        if not reply_btns:
            reply_btns = [r for r in page.locator('div[role="button"]:has-text("رد"), span:has-text("رد")').all() if r.is_visible()]

        if not reply_btns:
            print(f"[-] المنشور رقم {post_index} لا يحتوي على أي تعليقات مفتوحة للرد عليها.")
            return False

        target_reply = reply_btns[comment_index - 1] if len(reply_btns) >= comment_index else reply_btns[0]
        
        # النقر البرمجي لتفادي اعتراض مؤشر الفأرة
        target_reply.dispatch_event('click')
        human_delay(1.5, 2.5)

        # 2. تحديد صندوق الرد المتولد حديثاً
        reply_box_selectors = [
            'div[aria-label*="رد على"][role="textbox"]',
            'div[aria-placeholder*="رد على"][role="textbox"]',
            'div[aria-label*="اكتب ردًا"][role="textbox"]',
            'div[aria-placeholder*="اكتب ردًا"][role="textbox"]',
            'div[aria-label*="ردًا على"][role="textbox"]',
            'div[aria-label*="Reply to"][role="textbox"]'
        ]

        reply_box = None
        for sel in reply_box_selectors:
            loc = page.locator(sel).first
            if loc.is_visible(timeout=2500):
                reply_box = loc
                break

        if not reply_box:
            all_tbs = page.locator('div[role="textbox"][contenteditable="true"]').all()
            for tb in reversed(all_tbs):
                if tb.is_visible():
                    reply_box = tb
                    break

        if reply_box:
            try:
                reply_box.focus()
            except Exception:
                reply_box.click(force=True, timeout=2000)
            human_delay(0.5, 1.0)
            page.keyboard.type(reply_text, delay=random.randint(45, 85))
            human_delay(1.0, 1.8)
            page.keyboard.press("Enter")
            print(f"[+] تم إرسال الرد بنجاح على التعليق رقم {comment_index}: '{reply_text}'")
            human_delay(4.5, 6.0)
            return True
        else:
            print("[-] تعذر الوصول لصندوق كتابة الرد على التعليق.")
            return False

    except Exception as e:
        print(f"[-] خطأ أثناء الرد على التعليق: {e}")
        return False

def find_target_comment_element(post, target_mode: str = "first", target_value: str = ""):
    """البحث الذكي عن التعليق المستهدف داخل المنشور حسب الاسم، الكلمة، أو الترتيب عبر استراتيجيات متعددة"""
    comments = []
    for sel in [
        'div[role="article"]',
        'div[aria-label*="تعليق"]',
        'div[aria-label*="Comment"]',
        'ul > li:has(div[role="button"]:has-text("رد"))',
        'div[role="listitem"]:has(div[role="button"]:has-text("رد"))'
    ]:
        try:
            found = post.locator(sel).all()
            if found:
                comments = [c for c in found if c != post]
                if comments:
                    break
        except Exception:
            continue

    if not comments:
        try:
            reply_btns = [b for b in post.locator('div[role="button"]:has-text("رد"), span:has-text("رد")').all() if b.is_visible()]
            if reply_btns:
                for rb in reply_btns:
                    try:
                        parent_cmt = rb.locator('xpath=ancestor::div[contains(., "رد") and (contains(., "أعجبني") or contains(., "Like"))][1]')
                        if parent_cmt.count() > 0:
                            comments.append(parent_cmt)
                        else:
                            comments.append(rb)
                    except Exception:
                        comments.append(rb)
        except Exception:
            pass

    if not comments:
        print("[-] لم يتم العثور على أي عناصر تعليقات داخل المنشور.")
        return None

    if target_mode == "author" and target_value.strip():
        val = target_value.strip().lower()
        for c in comments:
            try:
                txt = c.inner_text().lower()
                aria = (c.get_attribute("aria-label") or "").lower()
                if val in txt or val in aria:
                    print(f"[+] تم العثور على التعليق بحسب اسم صاحبه: '{target_value}'")
                    return c
            except Exception:
                continue

    elif target_mode == "keyword" and target_value.strip():
        val = target_value.strip().lower()
        for c in comments:
            try:
                txt = c.inner_text().lower()
                if val in txt:
                    print(f"[+] تم العثور على التعليق بحسب الكلمة المفتاحية: '{target_value}'")
                    return c
            except Exception:
                continue

    elif target_mode == "index":
        try:
            idx = int(target_value) - 1
            if 0 <= idx < len(comments):
                print(f"[+] تم اختيار التعليق برقم الترتيب: {idx + 1}")
                return comments[idx]
        except Exception:
            pass

    print("[+] تم اختيار أول تعليق ظاهر في المنشور بنجاح.")
    return comments[0]

def apply_comment_reaction(page: Page, comment_elem, reaction: str = "like") -> bool:
    """تطبيق التفاعل المطلوب على التعليق (أعجبني، أحببته، أدعمه، هاهاها، واو، أحزنني، أغضبني)"""
    if not reaction or reaction.lower() in ["none", "بدون تفاعل", "لا شيء"]:
        return True

    reaction_map = {
        "like": "أعجبني",
        "love": "أحببته",
        "care": "أدعمه",
        "haha": "هاهاها",
        "wow": "واااو",
        "sad": "أحزنني",
        "angry": "أغضبني"
    }
    target_label = reaction_map.get(reaction.lower(), "أعجبني")

    like_btn = comment_elem.locator('span:has-text("أعجبني"), div[role="button"]:has-text("أعجبني"), div[role="button"][aria-label*="أعجبني"]').first
    if not like_btn.is_visible(timeout=2500):
        print("[-] لم يتم العثور على زر التفاعل في هذا التعليق.")
        return False

    try:
        if reaction.lower() == "like":
            like_btn.dispatch_event('click')
            print(f"[+] تم وضع إعجاب (Like) على التعليق بنجاح.")
            human_delay(1.5, 2.5)
            return True
        else:
            like_btn.hover()
            human_delay(1.0, 1.8)

            r_btn = page.locator(f'div[role="toolbar"] div[role="button"][aria-label*="{target_label}"], div[role="button"][aria-label="{target_label}"]').first
            if r_btn.is_visible(timeout=2000):
                r_btn.click()
                print(f"[+] تم اختيار تفاعل '{target_label}' على التعليق بنجاح!")
                human_delay(1.5, 2.5)
                return True
            else:
                like_btn.dispatch_event('click')
                print(f"[+] تم وضع إعجاب عادي كبديل لتفاعل '{target_label}'.")
                human_delay(1.5, 2.5)
                return True
    except Exception as e:
        print(f"[-] خطأ أثناء التفاعل مع التعليق: {e}")
        return False

def post_reply_to_comment_elem(page: Page, comment_elem, reply_text: str) -> bool:
    """كتابة ونشر الرد على عنصر التعليق المحدد"""
    if not reply_text.strip():
        return True

    reply_btn = comment_elem.locator('div[role="button"]:has-text("رد"), span:has-text("رد")').first
    if not reply_btn.is_visible(timeout=2500):
        print("[-] لم يتم العثور على زر 'رد' في هذا التعليق.")
        return False

    try:
        reply_btn.dispatch_event('click')
        human_delay(1.5, 2.5)

        reply_box_selectors = [
            'div[aria-label*="رد على"][role="textbox"]',
            'div[aria-placeholder*="رد على"][role="textbox"]',
            'div[aria-label*="اكتب ردًا"][role="textbox"]',
            'div[aria-placeholder*="اكتب ردًا"][role="textbox"]',
            'div[aria-label*="ردًا على"][role="textbox"]',
            'div[aria-label*="Reply to"][role="textbox"]'
        ]

        reply_box = None
        for sel in reply_box_selectors:
            loc = page.locator(sel).first
            if loc.is_visible(timeout=2500):
                reply_box = loc
                break

        if not reply_box:
            all_tbs = page.locator('div[role="textbox"][contenteditable="true"]').all()
            for tb in reversed(all_tbs):
                if tb.is_visible():
                    reply_box = tb
                    break

        if reply_box:
            try:
                reply_box.focus()
            except Exception:
                reply_box.click(force=True, timeout=2000)
            human_delay(0.5, 1.0)
            page.keyboard.type(reply_text, delay=random.randint(45, 85))
            human_delay(1.0, 1.8)
            page.keyboard.press("Enter")
            print(f"[+] تم إرسال الرد بنجاح على التعليق المحدد: '{reply_text}'")
            human_delay(4.5, 6.0)
            return True
        else:
            print("[-] تعذر الوصول لصندوق كتابة الرد على التعليق.")
            return False
    except Exception as e:
        print(f"[-] خطأ أثناء كتابة الرد على التعليق: {e}")
        return False

def interact_with_specific_comment(
    page: Page,
    post_index: int = 1,
    target_mode: str = "first",
    target_value: str = "",
    reaction: str = "none",
    reply_text: str = ""
) -> bool:
    """
    المنظومة الشاملة للتفاعل والرد على تعليق محدد بدقة عالية:
    - post_index: رقم المنشور (افتراضياً 1)
    - target_mode: 'first' (أول تعليق) أو 'author' (اسم المعلق) أو 'keyword' (كلمة في التعليق) أو 'index' (رقم التعليق)
    - target_value: القيمة المقابلة للبحث
    - reaction: نوع التفاعل (none, like, love, care, haha, wow, sad, angry)
    - reply_text: نص الرد إذا كان مطلوباً
    """
    dismiss_dialogs(page)
    close_floating_chats(page)
    posts = _find_posts(page)
    if not posts:
        print("[-] لم يتم العثور على أي منشور.")
        return False

    target_post = posts[post_index - 1] if len(posts) >= post_index else posts[0]
    try:
        target_post.scroll_into_view_if_needed(timeout=3000)
        human_delay(1.0, 2.0)

        # فتح وتوسيع التعليقات
        _ensure_post_comments_expanded(page, target_post)
        human_delay(1.5, 2.5)

        target_cmt = find_target_comment_element(target_post, target_mode=target_mode, target_value=target_value)
        if not target_cmt:
            print("[-] تعذر العثور على التعليق المطابق للمواصفات المطلوبة.")
            return False

        success_any = False
        # 1. التفاعل بالرياكشن
        if reaction and reaction.lower() not in ["none", "بدون تفاعل", "لا شيء"]:
            if apply_comment_reaction(page, target_cmt, reaction=reaction):
                success_any = True

        # 2. الرد على التعليق
        if reply_text and reply_text.strip():
            if post_reply_to_comment_elem(page, target_cmt, reply_text=reply_text):
                success_any = True

        return success_any

    except Exception as e:
        print(f"[-] خطأ أثناء التفاعل مع التعليق المحدد: {e}")
        return False

def send_friend_request(page: Page) -> bool:
    """إرسال طلب صداقة للحساب المستهدف"""
    dismiss_dialogs(page)
    close_floating_chats(page)
    human_delay(1.5, 3.0)

    friend_btn_selectors = [
        'div[role="button"]:has-text("إضافة صديق")',
        'div[role="button"]:has-text("Add friend")',
        'div[aria-label*="إضافة صديق"]',
        'div[aria-label*="Add friend"]',
        'span:has-text("إضافة صديق")',
        'span:has-text("Add friend")'
    ]

    for sel in friend_btn_selectors:
        try:
            btn = page.locator(sel).first
            if btn.is_visible(timeout=3000):
                btn.click()
                print("[+] تم إرسال طلب الصداقة بنجاح.")
                human_delay(2.0, 4.0)
                return True
        except Exception:
            continue

    print("[-] لم يتم العثور على زر إضافة صديق (ربما تم إرساله مسبقاً أو الحساب صديقك أو ملغي للعامة).")
    return False

def cancel_friend_request(page: Page) -> bool:
    """إلغاء طلب صداقة معلق للحساب المستهدف"""
    dismiss_dialogs(page)
    close_floating_chats(page)
    human_delay(1.5, 3.0)

    cancel_btn_selectors = [
        'div[role="button"]:has-text("إلغاء الطلب")',
        'div[role="button"]:has-text("Cancel request")',
        'div[aria-label*="إلغاء الطلب"]',
        'div[aria-label*="Cancel request"]',
        'span:has-text("إلغاء الطلب")',
        'span:has-text("Cancel request")'
    ]

    for sel in cancel_btn_selectors:
        try:
            btn = page.locator(sel).first
            if btn.is_visible(timeout=3000):
                btn.click()
                print("[+] تم إلغاء طلب الصداقة بنجاح.")
                human_delay(2.0, 4.0)
                return True
        except Exception:
            continue

    print("[-] لم يتم العثور على زر إلغاء الطلب (لا يوجد طلب معلق).")
    return False

def follow_profile(page: Page) -> bool:
    """متابعة الحساب المستهدف"""
    dismiss_dialogs(page)
    close_floating_chats(page)
    human_delay(1.5, 3.0)

    follow_selectors = [
        'div[role="button"]:has-text("متابعة")',
        'div[role="button"]:has-text("Follow")',
        'div[aria-label*="متابعة"]',
        'div[aria-label*="Follow"]',
        'span:has-text("متابعة")',
        'span:has-text("Follow")'
    ]

    for sel in follow_selectors:
        try:
            btn = page.locator(sel).first
            if btn.is_visible(timeout=2500):
                btn.click()
                print("[+] تمت متابعة الحساب بنجاح.")
                human_delay(2.0, 4.0)
                return True
        except Exception:
            continue

    more_selectors = [
        'div[aria-label*="إعدادات الملف الشخصي"]',
        'div[role="button"][aria-label*="المزيد"]',
        'div[role="button"][aria-label*="More"]'
    ]
    for m_sel in more_selectors:
        try:
            more_menu = page.locator(m_sel).first
            if more_menu.is_visible(timeout=1500):
                more_menu.click()
                human_delay(1.0, 2.0)
                inner_follow = page.locator(
                    'div[role="menuitem"]:has-text("متابعة"), '
                    'div[role="menuitem"]:has-text("Follow"), '
                    'span:has-text("متابعة"), '
                    'span:has-text("Follow")'
                ).first
                if inner_follow.is_visible(timeout=2000):
                    inner_follow.click()
                    print("[+] تمت متابعة الحساب عبر القائمة الجانبية بنجاح.")
                    human_delay(2.0, 4.0)
                    return True
                page.keyboard.press("Escape")
        except Exception:
            continue

    print("[-] زر المتابعة غير متوفر (قد تكون تتابعه بالفعل أو الإعدادات مغلقة).")
    return False

def extract_facebook_target_id(url: str) -> str:
    """استخراج المعرف الرقمي أو اسم المستخدم من رابط الحساب بدقة فائقة"""
    if not url:
        return ""
    m = re.search(r"[?&]id=(\d+)", url)
    if m:
        return m.group(1)
    m = re.search(r"facebook\.com/([a-zA-Z0-9\._\-]+)", url)
    if m:
        slug = m.group(1).lower()
        reserved = ("profile.php", "messages", "groups", "pages", "home.php", "watch", "marketplace", "gaming", "events", "notifications", "settings")
        if slug not in reserved:
            return m.group(1)
    return ""

def send_direct_message(page: Page, message_text: str, target_url: str = "") -> bool:
    """إرسال رسالة خاصة إلى الحساب المستهدف عبر ماسنجر باستقرار تام وبدون أي تداخل مع التعليقات أو الشريط العلوي"""
    dismiss_dialogs(page)
    close_floating_chats(page)
    human_delay(0.5, 1.0)

    # التأكد من التواجد بأعلى الصفحة حيث يتواجد زر المراسلة في ترويسة الحساب
    page.evaluate("window.scrollTo({top: 0, behavior: 'smooth'})")
    human_delay(1.5, 2.5)

    msg_btn_selectors = [
        'div[role="main"] div[role="button"][aria-label="مراسلة"]',
        'div[role="main"] div[role="button"][aria-label="Message"]',
        'div[role="main"] div[role="button"]:has-text("مراسلة")',
        'div[role="main"] div[role="button"]:has-text("Message")',
        'div[role="button"][aria-label="مراسلة"]',
        'div[role="button"][aria-label="Message"]'
    ]

    msg_btn = None
    for sel in msg_btn_selectors:
        try:
            btn = page.locator(sel).first
            if btn.is_visible(timeout=2500):
                msg_btn = btn
                break
        except Exception:
            continue

    if not msg_btn:
        print("[-] تعذر العثور على زر المراسلة في الصفحة الشخصية.")
        return False

    try:
        msg_btn.click()
        print("[+] تم النقر على زر المراسلة في ترويسة الحساب، بانتظار فتح المحادثة...")
        human_delay(2.5, 4.0)

        chat_input_selectors = [
            'div[aria-label*="اكتب إلى"][role="textbox"]',
            'div[aria-label*="Message"][role="textbox"]',
            'div[aria-label*="رسالة"][role="textbox"]',
            'div[role="dialog"] div[role="textbox"][contenteditable="true"]',
            'div[data-pagelet*="ChatTab"] div[role="textbox"][contenteditable="true"]'
        ]

        chat_input = None
        for c_sel in chat_input_selectors:
            try:
                inp = page.locator(c_sel).first
                if inp.is_visible(timeout=2500):
                    lbl = inp.get_attribute("aria-label") or ""
                    if "تعليق" not in lbl:
                        chat_input = inp
                        break
            except Exception:
                continue

        if not chat_input:
            all_tbs = page.locator('div[role="textbox"][contenteditable="true"]').all()
            for tb in reversed(all_tbs):
                lbl = tb.get_attribute("aria-label") or ""
                if "تعليق" not in lbl and tb.is_visible():
                    chat_input = tb
                    break

        if chat_input:
            try:
                chat_input.focus()
            except Exception:
                chat_input.click(force=True, timeout=2000)
            human_delay(0.5, 1.2)
            page.keyboard.type(message_text, delay=random.randint(45, 85))
            human_delay(1.0, 2.0)
            page.keyboard.press("Enter")
            print(f"[+] تم إرسال الرسالة الخاصة بنجاح عبر ماسنجر: '{message_text}'")
            human_delay(3.0, 4.5)

            # إغلاق نافذة المحادثة العائمة بهدوء
            close_floating_chats(page)

            if target_url:
                page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
                human_delay(2.0, 3.5)

            return True
        else:
            print("[-] لم يتم العثور على صندوق كتابة الرسالة في نافذة ماسنجر.")
            return False

    except Exception as e:
        print(f"[-] خطأ أثناء محاولة إرسال الرسالة بالماسنجر: {e}")
        return False

def block_profile(page: Page) -> bool:
    """حظر الحساب المستهدف لمنعه من الوصول إليك أو رؤية محتواك نهائياً"""
    dismiss_dialogs(page)
    close_floating_chats(page)
    human_delay(1.5, 2.5)
    print("\n[+] محاولة حظر الحساب المستهدف...")

    more_selectors = [
        'div[aria-label*="إعدادات الملف الشخصي"]',
        'div[role="main"] div[aria-haspopup="menu"]',
        'div[role="button"][aria-label*="المزيد"]'
    ]

    more_btn = None
    for sel in more_selectors:
        for elem in page.locator(sel).all():
            if elem.is_visible():
                more_btn = elem
                break
        if more_btn:
            break

    if not more_btn:
        print("[-] تعذر العثور على زر الخيارات (...) في الحساب.")
        return False

    try:
        more_btn.click()
        human_delay(1.5, 2.5)

        block_item_selectors = [
            'div[role="menuitem"]:has-text("حظر")',
            'div[role="menuitem"]:has-text("Block")',
            'span:has-text("حظر")',
            'span:has-text("Block")'
        ]

        clicked_block = False
        for sel in block_item_selectors:
            item = page.locator(sel).first
            if item.is_visible(timeout=2000):
                item.click()
                clicked_block = True
                print("[+] تم النقر على خيار 'حظر'. بانتظار نافذة التأكيد...")
                human_delay(1.5, 3.0)
                break

        if not clicked_block:
            print("[-] لم يتم العثور على خيار 'حظر' في القائمة.")
            return False

        confirm_selectors = [
            'div[role="dialog"] div[role="button"]:has-text("تأكيد")',
            'div[role="dialog"] div[role="button"]:has-text("Confirm")',
            'div[role="dialog"] div[role="button"]:has-text("حظر")',
            'div[role="dialog"] div[role="button"]:has-text("Block")',
            'div[role="dialog"] button:has-text("تأكيد")',
            'div[role="dialog"] button:has-text("Confirm")'
        ]

        for sel in confirm_selectors:
            confirm_btn = page.locator(sel).first
            if confirm_btn.is_visible(timeout=3000):
                confirm_btn.click()
                print("[+] تم تأكيد حظر الحساب بنجاح!")
                human_delay(2.0, 4.0)
                return True

        print("[-] لم يتم العثور على زر تأكيد الحظر في النافذة المنبثقة.")
        return False

    except Exception as e:
        print(f"[-] خطأ أثناء تنفيذ الحظر: {e}")
        return False

def _execute_report_wizard(page: Page, reason: str = "harassment", victim: str = "me") -> bool:
    """
    محرك الويزارد الديناميكي التفاعلي للبلاغات (حساب أو منشور):
    يتحرك خطوة بخطوة ويتفحص الشاشة ويتفاعل مع أي عدد من الخطوات حتى يرى تأكيد الاستلام الصريح من إدارة فيسبوك.
    """
    category_map = {
        "harassment": ["مضايقة أو إساءة أو استغلال", "مضايقة أو إساءة", "مضايقة", "تنمر", "Harassment"],
        "fake": ["ملف شخصي مزيف", "حساب زائف", "انتحال شخصية", "حساب مزيف", "Fake profile", "Fake account"],
        "hate_violence": ["محتوى ينطوي على عنف أو كراهية أو إزعاج", "عنف أو كراهية", "خطاب يحث على الكراهية", "Hate speech"],
        "fraud": ["خداع أو احتيال أو معلومات زائفة", "احتيال", "معلومات زائفة", "Fraud"],
        "adult": ["محتوى للبالغين", "عري", "Nudity", "Adult"],
        "spam": ["شيء آخر", "رسائل غير مرغوب فيها", "سبام", "Spam", "Something else"],
        "suicide": ["انتحار أو إيذاء للذات", "Suicide"]
    }
    victim_map = {
        "not_real": ["هو ليس شخصًا حقيقيَا", "ليس شخصاً حقيقياً", "حساب غير حقيقي"],
        "me": ["أنا", "Me"],
        "friend": ["صديق", "صديقي", "A friend"]
    }

    cat_texts = category_map.get(reason, ["مضايقة أو إساءة أو استغلال", "مضايقة"])
    vic_texts = victim_map.get(victim, ["هو ليس شخصًا حقيقيَا", "أنا"])

    confirmation_indicators = [
        "تم الإرسال إلى فيسبوك للمراجعة",
        "لقد قدمت بلاغًا",
        "تم استلام بلاغك",
        "شكراً لإبلاغنا",
        "شكراً لك على إبلاغنا",
        "تم إرسال البلاغ",
        "Report submitted",
        "Thanks for reporting"
    ]

    print("[*] جاري تنفيذ خطوات البلاغ التفاعلية عبر المعالج الذكي...")
    for step in range(1, 12):
        human_delay(1.5, 2.5)
        dialog = page.locator('div[role="dialog"]').last
        if not dialog.is_visible(timeout=2000):
            print(f"[-] أُغلقت نافذة البلاغ في الخطوة {step}.")
            break

        txt = dialog.inner_text()

        # 1. التحقق الحاسم من شاشة التأكيد النهائية
        if any(h in txt for h in confirmation_indicators):
            print(f"[+] نجاح قطعي: تم الوصول لشاشة تأكيد البلاغ الرسمية في الخطوة {step}!")
            done_btn = dialog.locator('div[role="button"]:has-text("تم"), div[role="button"][aria-label="تم"], div[role="button"]:has-text("Done")').last
            if done_btn.is_visible(timeout=2000):
                done_btn.click()
                print("[+] تم النقر على زر 'تم' وإغلاق البلاغ بنجاح.")
                human_delay(1.5, 2.5)
            return True

        # 2. هل البلاغ قيد الإرسال الشبكي حالياً؟
        if "جارٍ إرسال البلاغ" in txt or "Submitting" in txt:
            print(f"[*] الخطوة {step}: جاري إرسال البلاغ لفيسبوك، بانتظار التأكيد...")
            human_delay(3.0, 4.0)
            continue

        # 3. فحص زر الإرسال النهائي (Submit)
        submit_btn = dialog.locator('div[role="button"]:has-text("إرسال"), div[role="button"]:has-text("Submit")').last
        if submit_btn.is_visible(timeout=1000):
            print(f"[*] الخطوة {step}: النقر على زر 'إرسال' البلاغ...")
            submit_btn.click()
            human_delay(3.0, 4.5)
            continue

        # 4. فحص خيار الخطوة الأولى في بلاغات الحساب (شيء ما حول هذا الملف الشخصي)
        s1 = dialog.locator('div[role="button"]:has-text("شيء ما حول هذا الملف الشخصي"), span:has-text("شيء ما حول هذا الملف الشخصي")').first
        if s1.is_visible(timeout=1000):
            print(f"[*] الخطوة {step}: تحديد 'شيء ما حول هذا الملف الشخصي'...")
            s1.click()
            human_delay(2.0, 3.0)
            continue

        # 5. فحص سبب / فئة البلاغ
        cat_clicked = False
        for ct in cat_texts:
            c_btn = dialog.locator(f'div[role="button"]:has-text("{ct}"), span:has-text("{ct}")').first
            if c_btn.is_visible(timeout=1000):
                print(f"[*] الخطوة {step}: اختيار سبب البلاغ: '{ct}'...")
                c_btn.click()
                cat_clicked = True
                human_delay(2.0, 3.0)
                break
        if cat_clicked:
            continue

        # 6. فحص الطرف المتضرر / التفصيل الفرعي
        vic_clicked = False
        for vt in vic_texts:
            v_btn = dialog.locator(f'div[role="button"]:has-text("{vt}"), span:has-text("{vt}")').first
            if v_btn.is_visible(timeout=1000):
                print(f"[*] الخطوة {step}: تحديد الطرف المتضرر: '{vt}'...")
                v_btn.click()
                vic_clicked = True
                human_delay(2.0, 3.0)
                break
        if vic_clicked:
            continue

        # 7. فحص زر 'التالي' (Next)
        next_btn = dialog.locator('div[role="button"]:has-text("التالي"), div[role="button"]:has-text("Next")').last
        if next_btn.is_visible(timeout=1000):
            print(f"[*] الخطوة {step}: النقر على 'التالي' للمتابعة...")
            next_btn.click()
            human_delay(2.0, 3.0)
            continue

        # 8. فحص خيارات بديلة إذا كانت قائمة أزرار عامة
        action_btns = dialog.locator('div[role="button"][tabindex="0"]').all()
        filtered = [b for b in action_btns if b.is_visible() and b.get_attribute("aria-label") not in ["إغلاق", "Close", "عودة", "Back"]]
        if filtered:
            print(f"[*] الخطوة {step}: تقدم عبر الخيار التلقائي: '{filtered[0].inner_text().strip()[:30]}'...")
            filtered[0].click()
            human_delay(2.0, 3.0)
            continue

        print(f"[*] الخطوة {step}: بانتظار استجابة فيسبوك...")
        human_delay(2.0, 3.0)

    print("[-] انتهت جولات الويزارد دون استلام شاشة التأكيد النهائية.")
    return False

def report_post(page: Page, reason: str = "harassment", victim: str = "me") -> bool:
    """
    تقديم بلاغ دقيق ضد أحدث منشور مسيء في صفحة الحساب مع تتبع كافة الشاشات حتى تأكيد الاستلام الرسمي.
    """
    dismiss_dialogs(page)
    close_floating_chats(page)
    human_delay(1.5, 2.5)
    print(f"\n[+] محاولة تقديم بلاغ رسمي ضد المنشور (السبب: {reason} | المتضرر: {victim})...")

    posts = _find_posts(page)
    if not posts:
        print("[-] لم يتم العثور على أي منشور للإبلاغ عنه.")
        return False

    target_post = posts[0]
    try:
        target_post.scroll_into_view_if_needed(timeout=3000)
        human_delay(1.0, 2.0)

        # البحث عن زر الخيارات الثلاثية (...) للمنشور
        post_more_selectors = [
            'div[aria-label*="الإجراءات لهذا المنشور"]',
            'div[aria-label*="Actions for this post" i]',
            'div[role="button"][aria-haspopup="menu"]'
        ]

        post_more = None
        for sel in post_more_selectors:
            elem = target_post.locator(sel).first
            if elem.is_visible(timeout=2000):
                post_more = elem
                break

        if not post_more:
            all_menus = target_post.locator('div[aria-haspopup="menu"]').all()
            for m in all_menus:
                if m.is_visible():
                    post_more = m
                    break

        if not post_more:
            print("[-] تعذر العثور على زر خيارات المنشور (...).")
            return False

        post_more.click()
        human_delay(1.5, 2.5)

        # النقر على الإبلاغ عن المنشور
        report_selectors = [
            'div[role="menuitem"]:has-text("الإبلاغ عن المنشور")',
            'span:has-text("الإبلاغ عن المنشور")',
            'div[role="menuitem"]:has-text("البحث عن دعم أو إبلاغ")',
            'div[role="menuitem"]:has-text("إبلاغ")',
            'div[role="menuitem"]:has-text("Report post")'
        ]

        clicked_rep = False
        for sel in report_selectors:
            item = page.locator(sel).first
            if item.is_visible(timeout=2000):
                item.click()
                clicked_rep = True
                human_delay(2.5, 3.5)
                break

        if not clicked_rep:
            print("[-] لم يتم العثور على خيار إبلاغ المنشور في القائمة.")
            return False

        return _execute_report_wizard(page, reason=reason, victim=victim)

    except Exception as e:
        print(f"[-] خطأ أثناء الإبلاغ عن المنشور: {e}")
        return False

def report_profile(page: Page, reason: str = "fake", victim: str = "me") -> bool:
    """
    تقديم بلاغ دقيق ضد الحساب بالكامل لإدارة فيسبوك مع تتبع كافة الشاشات حتى تأكيد الاستلام الرسمي.
    """
    dismiss_dialogs(page)
    close_floating_chats(page)
    human_delay(1.5, 2.5)
    print(f"\n[+] محاولة تقديم بلاغ رسمي ضد الحساب بالكامل (السبب: {reason} | المتضرر: {victim})...")

    more_selectors = [
        'div[aria-label*="إعدادات الملف الشخصي"]',
        'div[role="main"] div[aria-haspopup="menu"][aria-label*="المزيد"]',
        'div[role="main"] div[aria-haspopup="menu"]',
        'div[role="main"] div[role="button"][aria-label*="More" i]'
    ]

    more_btn = None
    for sel in more_selectors:
        for elem in page.locator(sel).all():
            if elem.is_visible():
                more_btn = elem
                break
        if more_btn:
            break

    if not more_btn:
        print("[-] تعذر العثور على زر خيارات الملف الشخصي (...) في الصفحة.")
        return False

    try:
        more_btn.click()
        human_delay(1.5, 2.5)

        rep_selectors = [
            'div[role="menuitem"]:has-text("الإبلاغ عن ملف شخصي")',
            'span:has-text("الإبلاغ عن ملف شخصي")',
            'div[role="menuitem"]:has-text("إبلاغ")',
            'div[role="menuitem"]:has-text("البحث عن دعم أو إبلاغ")',
            'div[role="menuitem"]:has-text("Report profile")'
        ]

        clicked_rep = False
        for sel in rep_selectors:
            item = page.locator(sel).first
            if item.is_visible(timeout=2000):
                item.click()
                clicked_rep = True
                human_delay(2.5, 3.5)
                break

        if not clicked_rep:
            print("[-] لم يتم العثور على خيار الإبلاغ في القائمة.")
            return False

        return _execute_report_wizard(page, reason=reason, victim=victim)

    except Exception as e:
        print(f"[-] خطأ أثناء الإبلاغ عن الحساب: {e}")
        return False
