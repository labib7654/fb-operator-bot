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
import threading
try:
    from patchright.sync_api import Page, Locator
except Exception:
    from playwright.sync_api import Page, Locator
from fb_operator.browser_manager import (
    human_delay,
    human_click,
    human_type_text,
    _curved_mouse_move,
    dismiss_dialogs,
    smooth_scroll,
    check_facebook_page_access,
)

_DIAG_LOCK = threading.Lock()
_PAGE_DIAGS: dict[int, str] = {}


def _human_act_click(page: Page, locator, timeout: int = 4000, force: bool = False) -> bool:
    """نقر بشري موحّد بمسار بيزيه منحنٍ وضغط وإفلات طبيعي بدلاً من النقرات الفورية أو الاصطناعية"""
    try:
        if hasattr(locator, "scroll_into_view_if_needed"):
            locator.scroll_into_view_if_needed(timeout=min(timeout, 2500))
    except Exception:
        pass
    try:
        if human_click(page, locator, timeout=timeout):
            return True
    except Exception:
        pass
    try:
        locator.click(timeout=timeout, force=force)
        return True
    except Exception:
        if force:
            return False
        try:
            locator.click(timeout=min(timeout, 3000), force=True)
            return True
        except Exception:
            return False


def _human_hover(page: Page, locator) -> None:
    """تحريك المؤشر بمنحنى بيزيه فوق العنصر قبل التفاعل أو إظهار قائمة التفاعلات"""
    try:
        if hasattr(locator, "scroll_into_view_if_needed"):
            locator.scroll_into_view_if_needed(timeout=1800)
        box = locator.bounding_box()
        if box and box.get("width", 0) > 2 and box.get("height", 0) > 2:
            tx = box["x"] + box["width"] * random.uniform(0.32, 0.68)
            ty = box["y"] + box["height"] * random.uniform(0.32, 0.68)
            _curved_mouse_move(page, tx, ty)
            human_delay(0.15, 0.35)
        locator.hover()
    except Exception:
        pass


def set_page_diag(page, reason: str) -> None:
    """تسجيل سبب الفشل التشخيصي للصفحة الحالية دون تعديل خصائص Playwright الداخلية"""
    with _DIAG_LOCK:
        if reason:
            _PAGE_DIAGS[id(page)] = reason
        else:
            _PAGE_DIAGS.pop(id(page), None)


def get_page_diag(page) -> str:
    """استرجاع آخر رسالة تشخيصية مسجلة للصفحة"""
    with _DIAG_LOCK:
        return _PAGE_DIAGS.get(id(page), "")

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
    """الانتقال لرابط الحساب المستهدف والتأكد من اكتمال التحميل وتوفر المحتوى"""
    set_page_diag(page, "")
    clean_url = target_url.replace("://m.facebook.com", "://www.facebook.com")
    clean_url = clean_url.replace("://mobile.facebook.com", "://www.facebook.com")
    clean_url = clean_url.replace("://web.facebook.com", "://www.facebook.com")
    clean_url = clean_url.replace("://mbasic.facebook.com", "://www.facebook.com")

    print(f"\n[+] جاري التوجه إلى الرابط المستهدف: {clean_url}")
    try:
        try:
            page.goto(clean_url, wait_until="domcontentloaded", timeout=45000)
        except Exception:
            page.goto(clean_url, wait_until="commit", timeout=45000)
        human_delay(1.8, 3.2)
        dismiss_dialogs(page)
        close_floating_chats(page)
        try:
            vp = getattr(page, "viewport_size", None) or {}
            vw = float(vp.get("width", 1280))
            vh = float(vp.get("height", 800))
            _curved_mouse_move(page, random.uniform(vw * 0.25, vw * 0.72), random.uniform(vh * 0.22, vh * 0.58))
            if hasattr(page, "mouse") and hasattr(page.mouse, "wheel"):
                page.mouse.wheel(0, random.randint(140, 320))
                human_delay(0.8, 1.6)
        except Exception:
            pass

        ok, reason = check_facebook_page_access(page)
        if not ok:
            set_page_diag(page, reason)
            print(f"[-] تم إيقاف الصفحة بسبب: {reason}")
            return False
        return True
    except Exception as e:
        try:
            from fb_operator.browser_manager import detect_and_report_proxy_error
            detect_and_report_proxy_error(getattr(page, "context", None), e)
        except Exception:
            pass
        set_page_diag(page, f"خطأ أثناء فتح الرابط: {e}")
        print(f"[-] تعذر فتح الرابط المستهدف: {e}")
        return False


def _is_nested_comment_article(elem) -> bool:
    """التحقق مما إذا كان العنصر تعليقاً متداخلاً داخل منشور وليس منشوراً مستقلاً"""
    try:
        res = elem.evaluate("el => !!(el && el.parentElement && el.parentElement.closest('[role=\"article\"]'))")
        return res is True
    except Exception:
        return False


def _find_posts(page: Page) -> list[Locator]:
    """العثور على كتل المنشورات الظاهرة في صفحة الحساب بسلاسة دون احتساب التعليقات المتداخلة"""
    post_selectors = [
        'div[role="feed"] > div:has(div[role="button"][aria-label*="أعجبني"])',
        'div[role="feed"] > div:has(div[role="button"][aria-label*="Like" i])',
        'div[data-pagelet*="ProfileTimeline"] div[role="article"]',
        'div[role="feed"] > div',
        'div[role="article"]'
    ]

    for attempt in range(2):
        for sel in post_selectors:
            try:
                locators = page.locator(sel).all()
                top_level = [loc for loc in locators if not _is_nested_comment_article(loc)]
                if top_level:
                    return top_level
            except Exception:
                continue
        if attempt == 0:
            try:
                page.evaluate("window.scrollBy({top: 400, behavior: 'smooth'})")
            except Exception:
                pass
            human_delay(1.5, 2.0)

    return []


def get_target_post(page: Page, post_index: int = 1):
    """الوصول إلى المنشور المستهدف بالرقم المحدد (الأول، الثاني، الثالث، ...) بدقة وسلاسة"""
    dismiss_dialogs(page)
    close_floating_chats(page)

    url = (getattr(page, "url", "") or "").lower()
    if any(k in url for k in ["/posts/", "/permalink/", "/photo", "fbid=", "/videos/", "/reel/", "/share/", "story_fbid=", "pfbid"]):
        action_probe_sel = (
            'div[role="button"][aria-label*="أعجبني"], '
            'div[role="button"][aria-label*="اعجبني"], '
            'div[role="button"][aria-label*="إعجبني"], '
            'div[role="button"][aria-label*="Like" i], '
            'div[role="button"][aria-label*="تعليق"], '
            'div[role="button"][aria-label*="Comment" i]'
        )
        article = page.locator('div[role="article"]').first
        try:
            if article.is_visible(timeout=2500) and article.locator(action_probe_sel).count() > 0:
                return article
        except Exception:
            pass
        dialog = page.locator('div[role="dialog"]').first
        try:
            if dialog.is_visible(timeout=2000) and dialog.locator(action_probe_sel).count() > 0:
                return dialog
        except Exception:
            pass
        main_el = page.locator('div[role="main"]').first
        try:
            if main_el.is_visible(timeout=2000):
                return main_el
        except Exception:
            pass
        return article

    attempts = 0
    while attempts < 6:
        raw_posts = page.locator('div[role="feed"] > div, div[role="article"]').all()
        valid = []
        for p in raw_posts:
            try:
                if _is_nested_comment_article(p):
                    continue
                cnt = p.locator(
                    'div[role="button"][aria-label*="أعجبني"], '
                    'div[role="button"][aria-label*="Like" i], '
                    'div[role="button"][aria-label*="تعليق"], '
                    'div[role="button"][aria-label*="Comment" i]'
                ).count()
                if cnt > 0:
                    valid.append(p)
            except Exception:
                pass

        if len(valid) >= post_index:
            target = valid[post_index - 1]
            try:
                target.scroll_into_view_if_needed(timeout=2500)
            except Exception:
                pass
            return target

        try:
            page.evaluate(f"window.scrollBy({{top: {random.randint(420, 740)}, behavior: 'smooth'}})")
        except Exception:
            pass
        human_delay(1.4, 2.6)
        attempts += 1

    all_p = _find_posts(page)
    if all_p:
        idx = min(post_index - 1, len(all_p) - 1)
        return all_p[idx]
    return None

def react_to_posts(page: Page, reaction: str = "like", post_index: int = 1) -> bool:
    """التفاعل مع منشور محدد (إعجاب، أحببته، أدعمه، هاها، واو، أحزنني، أغضبني، أو إلغاء الإعجاب)"""
    set_page_diag(page, "")
    dismiss_dialogs(page)
    close_floating_chats(page)

    target_post = get_target_post(page, post_index)
    if not target_post:
        set_page_diag(page, f"لم يتم العثور على المنشور رقم {post_index} في الصفحة المستهدفة")
        print(f"[-] لم يتم العثور على المنشور رقم {post_index}.")
        return False

    like_btn_sel = (
        'div[role="button"][aria-label*="أعجبني"], '
        'div[role="button"][aria-label*="اعجبني"], '
        'div[role="button"][aria-label*="إعجبني"], '
        'div[role="button"][aria-label*="Like" i], '
        'div[role="button"]:has-text("أعجبني"), '
        'div[role="button"]:has-text("اعجبني"), '
        'div[role="button"]:has-text("Like")'
    )
    like_btn = target_post.locator(like_btn_sel).first
    try:
        if not like_btn.is_visible(timeout=2000):
            for fallback_sel in ('div[role="dialog"]', 'div[role="main"]'):
                fb_cont = page.locator(fallback_sel).first
                if fb_cont.is_visible(timeout=1000):
                    cand = fb_cont.locator(like_btn_sel).first
                    if cand.is_visible(timeout=1500):
                        target_post = fb_cont
                        like_btn = cand
                        break
    except Exception:
        pass

    if not like_btn.is_visible(timeout=3000):
        try:
            like_btn.scroll_into_view_if_needed(timeout=2000)
        except Exception:
            pass

    if not like_btn.is_visible(timeout=2500):
        set_page_diag(page, f"المنشور رقم {post_index} لا يحتوي على زر تفاعل متاح")
        print(f"[-] المنشور رقم {post_index}: لم يتم العثور على زر التفاعل/الإعجاب.")
        return False

    def _safe_click_btn(btn) -> None:
        _human_act_click(page, btn, timeout=4000, force=True)

    aria_label = (like_btn.get_attribute("aria-label") or "").strip().lower()
    btn_text = (like_btn.inner_text() or "").strip().lower()
    is_pressed = like_btn.get_attribute("aria-pressed") == "true"
    is_already_reacted = is_pressed or any(w in aria_label for w in ["إزالة", "أعجبك", "تراجع", "إلغاء", "unlike", "remove"]) or any(w in btn_text for w in ["أعجبك", "unlike"])

    reaction = reaction.lower().strip()

    if reaction in ["unlike", "remove", "cancel"]:
        if is_already_reacted:
            _safe_click_btn(like_btn)
            print(f"[+] المنشور {post_index}: تم إلغاء الإعجاب بنجاح.")
            human_delay(2.0, 3.5)
            return True
        else:
            print(f"[i] المنشور {post_index}: غير معجب به مسبقاً.")
            return True

    if reaction == "like":
        if is_already_reacted:
            print(f"[+] المنشور {post_index}: معجب به مسبقاً.")
            return True
        _safe_click_btn(like_btn)
        print(f"[+] المنشور {post_index}: تم الإعجاب بنجاح (Like).")
        human_delay(2.0, 3.5)
        return True

    reaction_map = {
        "love": ["أحببته", "Love"],
        "care": ["أدعمه", "Care"],
        "haha": ["هاهاها", "هاها", "Haha"],
        "wow": ["واااو", "واو", "Wow"],
        "sad": ["أحزنني", "Sad"],
        "angry": ["أغضبني", "Angry"]
    }
    keywords = reaction_map.get(reaction, ["أحببته", "Love"])

    try:
        _human_hover(page, like_btn)
        human_delay(1.1, 1.7)

        for attempt in range(2):
            for kw in keywords:
                react_btn = page.locator(f'div[role="toolbar"] div[aria-label*="{kw}" i], div[aria-label*="{kw}" i][role="button"]').first
                if react_btn.is_visible(timeout=1800):
                    _safe_click_btn(react_btn)
                    print(f"[+] المنشور {post_index}: تم وضع التفاعل بنجاح ({reaction}).")
                    human_delay(2.0, 3.5)
                    return True
            if attempt == 0:
                try:
                    like_btn.dispatch_event("mouseover")
                    like_btn.dispatch_event("mouseenter")
                except Exception:
                    pass
                human_delay(0.8, 1.2)

        _safe_click_btn(like_btn)
        print(f"[+] المنشور {post_index}: تم وضع الإعجاب الافتراضي.")
        human_delay(2.0, 3.0)
        return True
    except Exception as e:
        set_page_diag(page, f"خطأ أثناء النقر على التفاعل: {e}")
        print(f"[-] خطأ أثناء وضع التفاعل: {e}")
        return False

def unlike_posts(page: Page, post_index: int = 1) -> bool:
    """إلغاء التفاعل أو الإعجاب عن المنشور المحدد"""
    return react_to_posts(page, reaction="unlike", post_index=post_index)

def like_posts(page: Page, mode: str = "latest", count: int = 1, post_index: int = 1) -> int:
    """التفاعل والإعجاب بمنشورات الحساب المستهدف بدقة تامة"""
    if mode == "index":
        return 1 if react_to_posts(page, reaction="like", post_index=post_index) else 0

    dismiss_dialogs(page)
    close_floating_chats(page)
    posts = _find_posts(page)

    if not posts:
        print("[-] لم يتم العثور على أي منشورات ظاهرة في هذا الحساب للتفاعل معها.")
        return 0

    target_posts = posts[:1] if mode == "latest" else (posts[:count] if mode == "count" else posts)
    liked_count = 0

    for idx, post in enumerate(target_posts, start=1):
        try:
            like_btn = post.locator(
                'div[role="button"][aria-label*="أعجبني"], '
                'div[role="button"][aria-label*="Like" i], '
                'div[role="button"]:has-text("أعجبني"), '
                'div[role="button"]:has-text("Like")'
            ).first

            if not like_btn.is_visible(timeout=3000):
                like_btn.scroll_into_view_if_needed(timeout=2000)

            if not like_btn.is_visible(timeout=2500):
                continue

            aria_label = (like_btn.get_attribute("aria-label") or "").strip().lower()
            btn_text = (like_btn.inner_text() or "").strip().lower()
            is_pressed = like_btn.get_attribute("aria-pressed") == "true"
            is_already_liked = (
                is_pressed or
                any(word in aria_label for word in ["إزالة", "أعجبك", "تراجع", "إلغاء", "unlike", "remove"]) or
                any(word in btn_text for word in ["أعجبك", "إلغاء", "unlike"])
            )

            if is_already_liked:
                continue

            _human_act_click(page, like_btn)
            liked_count += 1
            human_delay(2.0, 3.5)
        except Exception:
            pass

    return liked_count

def _is_status_composer_textbox(loc) -> bool:
    """استبعاد صندوق كتابة منشور جديد ('بم تفكر؟') عند البحث عن حقل التعليق"""
    try:
        aria = (loc.get_attribute("aria-label") or "").lower()
        ph = (loc.get_attribute("aria-placeholder") or loc.get_attribute("placeholder") or "").lower()
        combined = f"{aria} {ph}"
        return any(bad in combined for bad in ("بم تفكر", "what's on your mind", "إنشاء منشور", "create a post", "write something to"))
    except Exception:
        return False


def comment_on_posts(page: Page, comment_text: str, mode: str = "latest", count: int = 1, post_index: int = 1, post_url: str = "") -> int:
    """كتابة ونشر تعليق مباشر وموثق على المنشور المستهدف بدقة تامة"""
    set_page_diag(page, "")
    dismiss_dialogs(page)
    close_floating_chats(page)

    if post_url and post_url.strip():
        if not navigate_to_target(page, post_url.strip()):
            return 0
        human_delay(1.5, 2.5)
        post_index = 1

    target_post = get_target_post(page, post_index)
    if not target_post:
        set_page_diag(page, f"لم يتم العثور على المنشور رقم {post_index} للتعليق")
        print("[-] لم يتم العثور على منشورات للتعليق عليها.")
        return 0

    try:
        comment_btn = target_post.locator(
            'div[role="button"][aria-label*="Comment" i], '
            'div[role="button"][aria-label*="تعليق"], '
            'div[role="button"]:has-text("تعليق"), '
            'div[role="button"]:has-text("Comment")'
        ).first

        if comment_btn.is_visible(timeout=2500):
            try:
                _human_act_click(page, comment_btn, timeout=3000)
                human_delay(1.5, 2.5)
            except Exception:
                pass

        input_box = None
        comment_specific_selectors = [
            'div[aria-label*="اكتب تعليق"][role="textbox"]',
            'div[aria-placeholder*="اكتب تعليق"][role="textbox"]',
            'div[aria-label*="Write a comment"][role="textbox"]',
            'div[aria-placeholder*="Write a comment"][role="textbox"]',
            'div[aria-label*="أضف تعليق"][role="textbox"]',
            'div[aria-label*="Add a comment"][role="textbox"]',
            'div[role="textbox"][contenteditable="true"]',
            'div[role="dialog"] div[role="textbox"][contenteditable="true"]'
        ]

        for s in comment_specific_selectors:
            loc = target_post.locator(s).first
            if loc.is_visible(timeout=1500) and not _is_status_composer_textbox(loc):
                input_box = loc
                break

        if not input_box:
            for s in comment_specific_selectors:
                for loc in page.locator(s).all()[:5]:
                    try:
                        if loc.is_visible(timeout=1200) and not _is_status_composer_textbox(loc):
                            input_box = loc
                            break
                    except Exception:
                        continue
                if input_box:
                    break

        if input_box:
            try:
                input_box.scroll_into_view_if_needed(timeout=2000)
            except Exception:
                pass
            human_delay(0.5, 1.1)
            human_type_text(page, input_box, comment_text, clear_existing=False, fast=True)
            human_delay(0.9, 1.8)
            typed_ok = False
            try:
                cur_val = (input_box.inner_text(timeout=1000) or "").strip()
                if not cur_val:
                    cur_val = (input_box.input_value(timeout=1000) or "").strip()
                typed_ok = len(cur_val) > 0
            except Exception:
                typed_ok = False

            if not typed_ok:
                set_page_diag(page, "تعذر إدخال نص التعليق داخل مربع الكتابة")
                return 0

            page.keyboard.press("Enter")
            human_delay(1.2, 1.8)

            # إذا بقي النص داخل الصندوق بعد Enter، نحاول النقر على زر الإرسال المحدود بنفس المنشور/الحوار فقط
            still_has_text = False
            try:
                rem = (input_box.inner_text(timeout=800) or "").strip()
                if not rem:
                    rem = (input_box.input_value(timeout=800) or "").strip()
                still_has_text = len(rem) > 0
            except Exception:
                still_has_text = False

            if still_has_text:
                send_btns = [
                    'div[role="button"][aria-label*="إرسال تعليق"]',
                    'div[role="button"][aria-label*="Submit comment" i]',
                    'div[role="button"][aria-label*="إرسال"]',
                    'div[role="button"][aria-label*="نشر"]',
                    'div[role="button"][aria-label*="Post" i]',
                    'div[role="button"][aria-label*="تعليق"][tabindex="0"]',
                    'div[role="button"][aria-label*="Comment" i][tabindex="0"]'
                ]
                dlg = page.locator('div[role="dialog"]').first
                scope_root = dlg if (dlg.is_visible(timeout=500) and dlg.locator('div[role="textbox"]').count() > 0) else target_post
                clicked_submit = False
                for sb in send_btns:
                    try:
                        b = scope_root.locator(sb).first
                        if b.is_visible(timeout=800):
                            _human_act_click(page, b, timeout=1200)
                            clicked_submit = True
                            break
                    except Exception:
                        pass
                if clicked_submit:
                    human_delay(1.5, 2.2)

            human_delay(2.5, 4.0)
            print(f"[+] تم إرسال ونشر التعليق بنجاح: '{comment_text}'")
            return 1
        else:
            set_page_diag(page, "التعليقات مغلقة أو تعذر الوصول لصندوق كتابة التعليق في هذا المنشور")
            print("[-] تعذر الوصول لصندوق كتابة التعليق.")
            return 0
    except Exception as e:
        set_page_diag(page, f"خطأ أثناء كتابة التعليق: {e}")
        print(f"[-] خطأ أثناء كتابة التعليق: {e}")
        return 0

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
                _human_act_click(page, btn, timeout=2500)
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
            _human_act_click(page, target_like, timeout=2500)
            print(f"[+] تم وضع إعجاب بنجاح على التعليق رقم {comment_index} في المنشور {post_index}!")
            human_delay(2.0, 3.5)
            return True

        # طريقة بديلة: البحث عن نص "أعجبني" الصغير بجوار زر "رد"
        alt_likes = page.locator('span:has-text("أعجبني"), div[role="button"]:has-text("أعجبني")').all()
        for al in alt_likes:
            if al.is_visible():
                _human_act_click(page, al, timeout=2500)
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
        _human_act_click(page, target_reply, timeout=3000)
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
            human_type_text(page, reply_box, reply_text, clear_existing=False, fast=True)
            human_delay(0.9, 1.8)
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
        "like": ("أعجبني", "Like"),
        "love": ("أحببته", "Love"),
        "care": ("أدعمه", "Care"),
        "haha": ("هاهاها", "هاها", "Haha"),
        "wow": ("واااو", "واو", "Wow"),
        "sad": ("أحزنني", "Sad"),
        "angry": ("أغضبني", "Angry")
    }
    target_labels = reaction_map.get(reaction.lower(), ("أعجبني", "Like"))

    like_btn = comment_elem.locator(
        'span:has-text("أعجبني"), span:has-text("Like"), '
        'div[role="button"]:has-text("أعجبني"), div[role="button"]:has-text("Like"), '
        'div[role="button"][aria-label*="أعجبني"], div[role="button"][aria-label*="Like" i]'
    ).first
    if not like_btn.is_visible(timeout=2500):
        print("[-] لم يتم العثور على زر التفاعل في هذا التعليق.")
        return False

    try:
        if reaction.lower() == "like":
            _human_act_click(page, like_btn, timeout=2500)
            print("[+] تم وضع إعجاب (Like) على التعليق بنجاح.")
            human_delay(1.5, 2.5)
            return True
        else:
            _human_hover(page, like_btn)
            human_delay(1.0, 1.8)

            for lbl in target_labels:
                r_btn = page.locator(f'div[role="toolbar"] div[role="button"][aria-label*="{lbl}" i], div[role="button"][aria-label="{lbl}"]').first
                if r_btn.is_visible(timeout=1500):
                    _human_act_click(page, r_btn, timeout=2500)
                    print(f"[+] تم اختيار تفاعل '{lbl}' على التعليق بنجاح!")
                    human_delay(1.5, 2.5)
                    return True

            _human_act_click(page, like_btn, timeout=2500)
            print(f"[+] تم وضع إعجاب عادي كبديل لتفاعل '{target_labels[0]}'.")
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
        _human_act_click(page, reply_btn, timeout=3000)
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
            human_type_text(page, reply_box, reply_text, clear_existing=False, fast=True)
            human_delay(0.9, 1.8)
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
                _human_act_click(page, btn, timeout=3000)
                print("[+] تم إرسال طلب الصداقة بنجاح.")
                human_delay(2.0, 4.0)
                return True
        except Exception:
            continue

    print("[-] لم يتم العثور على زر إضافة صديق (ربما تم إرساله مسبقاً أو الحساب صديقك أو ملغي للعامة).")
    return False

def cancel_friend_request(page: Page) -> bool:
    """إلغاء طلب صداقة معلق أو إلغاء الصداقة مع الحساب المستهدف"""
    set_page_diag(page, "")
    dismiss_dialogs(page)
    close_floating_chats(page)
    human_delay(1.5, 3.0)

    cancel_btn_selectors = [
        'div[role="button"]:has-text("إلغاء الطلب")',
        'div[role="button"]:has-text("Cancel request")',
        'div[aria-label*="إلغاء الطلب"]',
        'div[aria-label*="Cancel request" i]',
        'span:has-text("إلغاء الطلب")',
        'span:has-text("Cancel request")'
    ]

    for sel in cancel_btn_selectors:
        try:
            btn = page.locator(sel).first
            if btn.is_visible(timeout=2500):
                _human_act_click(page, btn, timeout=3000)
                print("[+] تم إلغاء طلب الصداقة بنجاح.")
                human_delay(2.0, 4.0)
                return True
        except Exception:
            continue

    # دعم إلغاء صداقة قائمة بالفعل (الأصدقاء -> إلغاء الصداقة -> تأكيد)
    friends_selectors = [
        'div[role="main"] div[role="button"][aria-label*="أصدقاء"]',
        'div[role="main"] div[role="button"][aria-label*="Friends" i]',
        'div[role="button"]:has-text("أصدقاء")',
        'div[role="button"]:has-text("Friends")'
    ]
    for fs in friends_selectors:
        try:
            f_btn = page.locator(fs).first
            if f_btn.is_visible(timeout=2000):
                _human_act_click(page, f_btn, timeout=2500)
                human_delay(1.0, 1.8)
                unfriend_btn = page.locator(
                    'div[role="menuitem"]:has-text("إلغاء الصداقة"), '
                    'div[role="menuitem"]:has-text("Unfriend"), '
                    'span:has-text("إلغاء الصداقة"), span:has-text("Unfriend")'
                ).first
                if unfriend_btn.is_visible(timeout=2000):
                    _human_act_click(page, unfriend_btn, timeout=2500)
                    human_delay(0.8, 1.5)
                    confirm = page.locator(
                        'div[role="dialog"] div[role="button"]:has-text("تأكيد"), '
                        'div[role="dialog"] div[role="button"]:has-text("Confirm")'
                    ).first
                    if confirm.is_visible(timeout=2000):
                        _human_act_click(page, confirm, timeout=2500)
                    print("[+] تم إلغاء الصداقة بنجاح.")
                    human_delay(2.0, 3.5)
                    return True
                page.keyboard.press("Escape")
        except Exception:
            continue

    set_page_diag(page, "لا يوجد طلب صداقة معلق أو علاقة صداقة لإلغائها")
    print("[-] لم يتم العثور على زر إلغاء الطلب أو إلغاء الصداقة.")
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
                _human_act_click(page, btn, timeout=3000)
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
                _human_act_click(page, more_menu, timeout=2500)
                human_delay(1.0, 2.0)
                inner_follow = page.locator(
                    'div[role="menuitem"]:has-text("متابعة"), '
                    'div[role="menuitem"]:has-text("Follow"), '
                    'span:has-text("متابعة"), '
                    'span:has-text("Follow")'
                ).first
                if inner_follow.is_visible(timeout=2000):
                    _human_act_click(page, inner_follow, timeout=2500)
                    print("[+] تمت متابعة الحساب عبر القائمة الجانبية بنجاح.")
                    human_delay(2.0, 4.0)
                    return True
                page.keyboard.press("Escape")
        except Exception:
            continue

    print("[-] زر المتابعة غير متوفر (قد تكون تتابعه بالفعل أو الإعدادات مغلقة).")
    return False


def unfollow_profile(page: Page) -> bool:
    """إلغاء متابعة الحساب المستهدف"""
    dismiss_dialogs(page)
    close_floating_chats(page)
    human_delay(1.5, 3.0)

    unfollow_selectors = [
        'div[role="button"]:has-text("متابَع")',
        'div[role="button"]:has-text("Following")',
        'div[aria-label*="متابَع"]',
        'div[aria-label*="Following" i]',
        'span:has-text("متابَع")',
        'span:has-text("Following")'
    ]

    for sel in unfollow_selectors:
        try:
            btn = page.locator(sel).first
            if btn.is_visible(timeout=2500):
                _human_act_click(page, btn, timeout=3000)
                human_delay(1.0, 2.0)
                menu_unfollow = page.locator(
                    'div[role="menuitem"]:has-text("إلغاء المتابعة"), '
                    'div[role="menuitem"]:has-text("Unfollow"), '
                    'span:has-text("إلغاء المتابعة"), '
                    'span:has-text("Unfollow")'
                ).first
                if menu_unfollow.is_visible(timeout=2000):
                    _human_act_click(page, menu_unfollow, timeout=2500)
                print("[+] تم إلغاء متابعة الحساب بنجاح.")
                human_delay(2.0, 3.5)
                return True
        except Exception:
            continue

    more_selectors = [
        'div[aria-label*="إعدادات الملف الشخصي"]',
        'div[role="button"][aria-label*="المزيد"]',
        'div[role="button"][aria-label*="More" i]'
    ]
    for m_sel in more_selectors:
        try:
            more_menu = page.locator(m_sel).first
            if more_menu.is_visible(timeout=1500):
                _human_act_click(page, more_menu, timeout=2500)
                human_delay(1.0, 2.0)
                inner_unfollow = page.locator(
                    'div[role="menuitem"]:has-text("إلغاء المتابعة"), '
                    'div[role="menuitem"]:has-text("Unfollow"), '
                    'span:has-text("إلغاء المتابعة"), '
                    'span:has-text("Unfollow")'
                ).first
                if inner_unfollow.is_visible(timeout=2000):
                    _human_act_click(page, inner_unfollow, timeout=2500)
                    print("[+] تم إلغاء متابعة الحساب عبر القائمة الجانبية بنجاح.")
                    human_delay(2.0, 3.5)
                    return True
        except Exception:
            continue

    print("[-] لم يتم العثور على زر المتابَع لإلغائها.")
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
    """إرسال رسالة خاصة إلى الحساب المستهدف عبر ماسنجر مع بديل رابط المحادثة المباشر"""
    set_page_diag(page, "")
    dismiss_dialogs(page)
    close_floating_chats(page)
    human_delay(0.5, 1.0)

    # التأكد من التواجد بأعلى الصفحة حيث يتواجد زر المراسلة في ترويسة الحساب
    try:
        page.evaluate("window.scrollTo({top: 0, behavior: 'smooth'})")
    except Exception:
        pass
    human_delay(1.5, 2.5)

    msg_btn_selectors = [
        'div[role="main"] div[role="button"][aria-label="مراسلة"]',
        'div[role="main"] div[role="button"][aria-label="Message"]',
        'div[role="main"] a[href*="/messages/t/"]',
        'div[role="main"] a[aria-label*="مراسلة"]',
        'div[role="main"] a[aria-label*="Message" i]',
        'div[role="main"] div[role="button"]:has-text("مراسلة")',
        'div[role="main"] div[role="button"]:has-text("Message")',
        'div[role="button"][aria-label="مراسلة"]',
        'div[role="button"][aria-label="Message"]'
    ]

    msg_btn = None
    for sel in msg_btn_selectors:
        try:
            btn = page.locator(sel).first
            if btn.is_visible(timeout=2000):
                msg_btn = btn
                break
        except Exception:
            continue

    opened_via_direct_url = False
    if msg_btn:
        try:
            _human_act_click(page, msg_btn, timeout=3000)
            print("[+] تم النقر على زر المراسلة في ترويسة الحساب، بانتظار فتح المحادثة...")
            human_delay(2.5, 4.0)
        except Exception:
            msg_btn = None

    if not msg_btn:
        fid = extract_facebook_target_id(target_url or getattr(page, "url", ""))
        if fid:
            try:
                page.goto(f"https://www.facebook.com/messages/t/{fid}", wait_until="domcontentloaded", timeout=35000)
                human_delay(2.5, 4.0)
                ok_msg, reason_msg = check_facebook_page_access(page)
                if not ok_msg:
                    set_page_diag(page, reason_msg)
                    return False
                opened_via_direct_url = True
                print(f"[+] تم التوجه مباشرة لرابط المراسلة /messages/t/{fid}")
            except Exception as nav_e:
                print(f"[-] تعذر فتح رابط الماسنجر المباشر: {nav_e}")

    if not msg_btn and not opened_via_direct_url:
        set_page_diag(page, "زر المراسلة غير متاح في هذا الحساب (قد يكون خاصاً أو يمنع الرسائل)")
        print("[-] تعذر العثور على زر المراسلة في الصفحة الشخصية.")
        return False

    try:
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
                    lbl = (inp.get_attribute("aria-label") or "").lower()
                    if "تعليق" not in lbl and "بحث" not in lbl and "search" not in lbl:
                        chat_input = inp
                        break
            except Exception:
                continue

        if not chat_input:
            all_tbs = page.locator('div[role="textbox"][contenteditable="true"]').all()
            for tb in reversed(all_tbs):
                try:
                    lbl = (tb.get_attribute("aria-label") or "").lower()
                    if "تعليق" not in lbl and "بحث" not in lbl and "search" not in lbl and tb.is_visible():
                        chat_input = tb
                        break
                except Exception:
                    continue

        if chat_input:
            human_type_text(page, chat_input, message_text, clear_existing=False, fast=True)
            human_delay(0.9, 1.8)
            page.keyboard.press("Enter")
            print(f"[+] تم إرسال الرسالة الخاصة بنجاح عبر ماسنجر: '{message_text}'")
            human_delay(3.0, 4.5)

            close_floating_chats(page)

            if target_url:
                page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
                human_delay(2.0, 3.5)

            return True
        else:
            set_page_diag(page, "تعذر العثور على صندوق كتابة الرسالة داخل محادثة ماسنجر (قد يمنع المستلم الرسائل)")
            print("[-] لم يتم العثور على صندوق كتابة الرسالة في نافذة ماسنجر.")
            if opened_via_direct_url and target_url:
                try:
                    page.goto(target_url, wait_until="domcontentloaded", timeout=25000)
                except Exception:
                    pass
            return False

    except Exception as e:
        set_page_diag(page, f"خطأ أثناء إرسال الرسالة بالماسنجر: {e}")
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
        _human_act_click(page, more_btn, timeout=3000)
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
                _human_act_click(page, item, timeout=2500)
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
                _human_act_click(page, confirm_btn, timeout=3000)
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
                _human_act_click(page, done_btn, timeout=2500)
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
            _human_act_click(page, submit_btn, timeout=2500)
            human_delay(3.0, 4.5)
            continue

        # 4. فحص خيار الخطوة الأولى في بلاغات الحساب (شيء ما حول هذا الملف الشخصي)
        s1 = dialog.locator('div[role="button"]:has-text("شيء ما حول هذا الملف الشخصي"), span:has-text("شيء ما حول هذا الملف الشخصي")').first
        if s1.is_visible(timeout=1000):
            print(f"[*] الخطوة {step}: تحديد 'شيء ما حول هذا الملف الشخصي'...")
            _human_act_click(page, s1, timeout=2500)
            human_delay(2.0, 3.0)
            continue

        # 5. فحص سبب / فئة البلاغ
        cat_clicked = False
        for ct in cat_texts:
            c_btn = dialog.locator(f'div[role="button"]:has-text("{ct}"), span:has-text("{ct}")').first
            if c_btn.is_visible(timeout=1000):
                print(f"[*] الخطوة {step}: اختيار سبب البلاغ: '{ct}'...")
                _human_act_click(page, c_btn, timeout=2500)
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
                _human_act_click(page, v_btn, timeout=2500)
                vic_clicked = True
                human_delay(2.0, 3.0)
                break
        if vic_clicked:
            continue

        # 7. فحص زر 'التالي' (Next)
        next_btn = dialog.locator('div[role="button"]:has-text("التالي"), div[role="button"]:has-text("Next")').last
        if next_btn.is_visible(timeout=1000):
            print(f"[*] الخطوة {step}: النقر على 'التالي' للمتابعة...")
            _human_act_click(page, next_btn, timeout=2500)
            human_delay(2.0, 3.0)
            continue

        # 8. فحص خيارات بديلة إذا كانت قائمة أزرار عامة
        action_btns = dialog.locator('div[role="button"][tabindex="0"]').all()
        filtered = [b for b in action_btns if b.is_visible() and b.get_attribute("aria-label") not in ["إغلاق", "Close", "عودة", "Back"]]
        if filtered:
            print(f"[*] الخطوة {step}: تقدم عبر الخيار التلقائي: '{filtered[0].inner_text().strip()[:30]}'...")
            _human_act_click(page, filtered[0], timeout=2500)
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

        _human_act_click(page, post_more, timeout=3000)
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
                _human_act_click(page, item, timeout=2500)
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
        _human_act_click(page, more_btn, timeout=3000)
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
                _human_act_click(page, item, timeout=2500)
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
