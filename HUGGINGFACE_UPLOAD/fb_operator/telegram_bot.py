"""
بوت تلغرام المتطور للتحكم الكامل بأتمتة حسابات فيسبوك (FB Operator Telegram Bot)
يدعم بوابة الموافقة الصارمة (Strict Two-Tier Approval Gate)،
نظام الصلاحيات الدقيق لـ 10 أدوات مستقلة (كل ميزة مغلقة افتراضياً حتى يفتحها المطور)،
رادار المراقبة الشامل والإشعارات الفورية للمطور عن كل حساب نشط أو فاشل يتم إضافته،
منع تكرار الحسابات نهائياً، وعزل الخيوط للتنفيذ المتوازي الآمن 24/7.
"""

import sys
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

import os
import re
import html
import time
import tempfile
import threading
from datetime import datetime
import telebot
from telebot import types
from playwright.sync_api import sync_playwright

from fb_operator.account_manager import (
    load_accounts, add_account, update_account, delete_account,
    purge_broken_accounts, get_accounts_by_owner, get_accounts_breakdown_by_owner,
    delete_accounts_by_owner, get_account_by_id, git_sync_save
)
from fb_operator.admin_manager import (
    is_super_admin, is_authorized_user, has_permission, get_user_permissions,
    register_or_update_user, approve_user, ban_user, unban_user,
    toggle_user_permission, revoke_all_permissions, delete_user_and_data,
    load_users, record_user_operation, record_account_result_for_user,
    record_audit_log, load_audit_logs, SUPER_ADMIN_ID, PERMISSION_LABELS
)
from fb_operator.browser_manager import (
    launch_account_browser, auto_login_facebook, check_facebook_login_cookies, human_delay
)
from fb_operator.actions import (
    navigate_to_target, comment_on_posts, react_to_posts,
    send_friend_request, cancel_friend_request, follow_profile, unfollow_profile,
    send_direct_message, block_profile, report_profile, report_post,
    interact_with_specific_comment
)
from fb_operator.webapp_server import (
    start_webapp_and_tunnel, get_public_webapp_url, update_menu_button_for_user
)
from fb_operator.state_events import publish_event, register_listener
from fb_operator.economy_manager import (
    OP_COST_LABELS_AR, load_economy_settings, update_economy_settings,
    is_points_enforced_for_user, can_user_invite, ensure_public_access_if_enabled,
    load_points_ledger, adjust_user_points, reward_account_activation,
    estimate_mission_account_count, calculate_mission_cost, debit_points_for_mission,
    get_user_wallet, get_or_create_personal_ref_code, create_invite_code,
    list_invite_codes_by_owner, revoke_invite_code, looks_like_invite_token,
    redeem_invite_code, build_user_settlement_snapshot, create_support_ticket,
    reply_support_ticket, settle_payout, list_support_tickets, get_ticket_by_id,
)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "8798272294:AAEY_LIYnVRIY2T-WUP63duCn5V7VFgGsCE")

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")
_bot_username_cache = ""


def get_bot_username() -> str:
    global _bot_username_cache
    if _bot_username_cache:
        return _bot_username_cache
    try:
        me = bot.get_me()
        uname = getattr(me, "username", "") or ""
        if uname:
            _bot_username_cache = uname
    except Exception:
        pass
    return _bot_username_cache


def _format_reward_notice(rew: dict, acc_name: str, is_dev_owner: bool = False) -> str:
    if not rew or is_dev_owner or int(rew.get("owner_awarded", 0) or 0) <= 0:
        return ""
    pts = int(rew.get("owner_awarded", 0))
    bal = int(rew.get("owner_balance", 0))
    rate = int(rew.get("yer_per_point", 10))
    yer = bal * rate
    return (
        f"\n\n🪙 <b>مكافأة التفعيل:</b> +{pts} نقطة للحساب ({esc(acc_name)})\n"
        f"💰 <b>رصيدك الآن:</b> {bal} نقطة (≈ <b>{yer:,} ريال يمني</b>)"
    )

# مجلد لقطات الشاشة المؤقت خارج المستودع لمنع تراكم الصور في Git
SHOTS_TEMP_DIR = Path(tempfile.gettempdir()) / "fb_operator_shots"
SHOTS_TEMP_DIR.mkdir(parents=True, exist_ok=True)

# ----------------- أدوات الأمان وحماية المخرجات والتوازي -----------------

def esc(val) -> str:
    """تنظيف وتشفير كافة المدخلات لمنع حقن HTML أو تعطل رسائل تلغرام"""
    return html.escape(str(val or ""), quote=True)


def _prompt_back_markup(back_to: str = "back_to_main") -> types.InlineKeyboardMarkup:
    """لوحة رجوع فورية تُرفق مع كل طلب إدخال نصي لمنع احتجاز المستخدم داخل أي عملية"""
    markup = types.InlineKeyboardMarkup(row_width=2)
    if back_to != "back_to_main":
        markup.row(
            types.InlineKeyboardButton("🔙 رجوع", callback_data=f"cancel_to:{back_to}"),
            types.InlineKeyboardButton("🏠 الرئيسية", callback_data="cancel_to:back_to_main")
        )
    else:
        markup.row(
            types.InlineKeyboardButton("🔙 إلغاء والرجوع للرئيسية", callback_data="cancel_to:back_to_main")
        )
    return markup


def _back_home_markup(back_to: str = "back_to_main") -> types.InlineKeyboardMarkup:
    """لوحة عودة سريعة بعد انتهاء العمليات"""
    markup = types.InlineKeyboardMarkup(row_width=2)
    if back_to != "back_to_main":
        markup.row(
            types.InlineKeyboardButton("🔙 رجوع", callback_data=back_to),
            types.InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="back_to_main")
        )
    else:
        markup.row(
            types.InlineKeyboardButton("🔙 العودة للقائمة الرئيسية", callback_data="back_to_main")
        )
    return markup


def safe_answer(call_id: str, text: str | None = None, show_alert: bool = False) -> None:
    try:
        if text is not None:
            bot.answer_callback_query(call_id, text, show_alert=show_alert)
        else:
            bot.answer_callback_query(call_id)
    except Exception:
        pass


def safe_edit_message(text: str, chat_id: int, message_id: int | None, reply_markup=None) -> None:
    if message_id is None:
        safe_send(chat_id, text, reply_markup=reply_markup)
        return
    try:
        bot.edit_message_text(text, chat_id, message_id, reply_markup=reply_markup)
    except Exception as e:
        if "message is not modified" in str(e).lower():
            return
        try:
            bot.send_message(chat_id, text, reply_markup=reply_markup)
        except Exception:
            pass


def safe_edit_reply_markup(chat_id: int, message_id: int, reply_markup) -> None:
    try:
        bot.edit_message_reply_markup(chat_id, message_id, reply_markup=reply_markup)
    except Exception:
        pass


def safe_send(chat_id: int, text: str, reply_markup=None):
    try:
        return bot.send_message(chat_id, text, reply_markup=reply_markup)
    except Exception:
        return None


# متتبع الرسائل التفاعلية النشطة لتحديث لوحات تلغرام تلقائياً فور وقوع أي حدث (بدون Polling)
_active_views: dict[int, dict] = {}
_active_views_lock = threading.Lock()
_live_sync_cond = threading.Condition()
_live_sync_pending_uids: set[int] = set()
_live_sync_started = False


def _track_view(user_id: int, chat_id: int, msg_id: int | None, view: str, target_id: int = 0, ticket_id: str = "") -> None:
    if not msg_id:
        return
    with _active_views_lock:
        _active_views[int(user_id)] = {
            "chat_id": int(chat_id),
            "msg_id": int(msg_id),
            "view": view,
            "target_id": int(target_id),
            "ticket_id": str(ticket_id or ""),
            "last_push": 0.0,
        }


# أقفال عزل بروفايلات المتصفح ومنع تشغيل نفس البروفايل في خيطين متزامنين
_profile_locks: dict[str, threading.Lock] = {}
_profile_locks_guard = threading.Lock()
_browser_semaphore = threading.BoundedSemaphore(4)


def get_profile_lock(account_id: str) -> threading.Lock:
    with _profile_locks_guard:
        if account_id not in _profile_locks:
            _profile_locks[account_id] = threading.Lock()
        return _profile_locks[account_id]


# ----------------- إدارة الجلسات المتعددة وعزل المستخدمين (Multi-Tenant Engine) -----------------

user_states: dict[int, dict] = {}
state_lock = threading.Lock()


def default_user_state() -> dict:
    return {
        "target_url": "https://www.facebook.com/profile.php?id=61595626255487",
        "selected_acc": "all",
        "acc_count_limit": 0,
        "like": False,
        "reaction_type": "like",
        "react_post_index": 1,
        "react_post_url": "",
        "react_acc_count": 0,
        "comment": False,
        "comment_text": "بالتوفيق يا غالي",
        "comment_post_index": 1,
        "comment_post_url": "",
        "comment_acc_count": 0,
        "interact_cmt": False,
        "cmt_target_mode": "first",
        "cmt_target_val": "Marwan",
        "cmt_reaction": "like",
        "cmt_reply": "صحيح كلامك 100%",
        "friend": False,
        "cancel_friend": False,
        "follow": False,
        "unfollow": False,
        "message": False,
        "message_text": "السلام عليكم",
        "report_post": False,
        "report_profile": False,
        "rep_reason": "harassment",
        "rep_victim": "me",
        "block": False,
        "input_mode": None,
        "temp_acc_data": {},
        "is_running": False,
        "live_status_text": ""
    }


def get_user_state(user_id: int) -> dict:
    with state_lock:
        if user_id not in user_states:
            user_states[user_id] = default_user_state()
        return user_states[user_id]


def user_has_any_action_perm(user_id: int) -> bool:
    if is_super_admin(user_id):
        return True
    action_keys = (
        "can_react", "can_comment", "can_interact_comments",
        "can_friend_follow", "can_message", "can_report"
    )
    return any(has_permission(user_id, k) for k in action_keys)


def get_usable_accounts_for_user(user_id: int) -> list[dict]:
    """
    حسابات التنفيذ المصرح بها للمستخدم بدقة أمنية:
    - المطور الأكبر يرى كل الحسابات.
    - من يملك صلاحية 'can_use_accounts' يستخدم كافة حسابات البوت.
    - من لا يملك 'can_use_accounts' لا يمكنه المساس بحسابات البوت المشتركة نهائياً
      (يُحصر فقط في حساباته التي أضافها هو إن فُعّلت له ميزة التنفيذ).
    """
    accs = load_accounts()
    if is_super_admin(user_id) or has_permission(user_id, "can_use_accounts"):
        return accs
    return [a for a in accs if a.get("owner_id") == int(user_id)]


def get_manageable_accounts_for_user(user_id: int) -> list[dict]:
    """قائمة الحسابات الظاهرة في إدارة الحسابات: المطور يرى الكل، والمستخدم يرى ما أضافه فقط"""
    if is_super_admin(user_id):
        return load_accounts()
    return get_accounts_by_owner(user_id)


def require_perm_or_deny(call: types.CallbackQuery, perm_key: str, error_msg: str) -> bool:
    """فحص صارم لصلاحية الزر داخل الخلفية وتسجيل محاولة التجاوز إن حدثت"""
    uid = call.from_user.id
    if is_super_admin(uid) or has_permission(uid, perm_key):
        return True
    name = f"{call.from_user.first_name or ''} {call.from_user.last_name or ''}".strip()
    record_audit_log(uid, name, "SECURITY_BLOCK", f"محاولة استخدام غير مصرح لـ {perm_key} عبر {call.data}")
    safe_answer(call.id, error_msg, show_alert=True)
    safe_edit_message(get_dashboard_text(uid), call.message.chat.id, call.message.message_id, reply_markup=get_main_dashboard_markup(uid))
    return False


# ----------------- بوابة التحقق الصارمة من الوصول (Strict Access Gate) -----------------

def notify_new_pending_user(user_id: int, full_name: str, username: str = "") -> None:
    """إرسال تنبيه فوري للمطور الرئيسي عند دخول مستخدم جديد مع أزرار الموافقة أو الحظر"""
    if is_super_admin(user_id):
        return
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("✅ قبول (بدون صلاحيات)", callback_data=f"gate_app_{user_id}"),
        types.InlineKeyboardButton("🚫 رفض وحظر نهائي", callback_data=f"gate_ban_{user_id}")
    )
    markup.add(
        types.InlineKeyboardButton("🛰️ فتح بطاقة المستخدم بالرادار", callback_data=f"surv_user_{user_id}")
    )
    user_tag = f"@{esc(username)}" if username else "بدون معرف"
    alert_text = (
        "🚨 <b>رادار الأمان: مستخدم جديد دخل للبوت!</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>الاسم:</b> {esc(full_name)}\n"
        f"🆔 <b>الآيدي:</b> <code>{user_id}</code>\n"
        f"🌐 <b>المعرف:</b> {user_tag}\n"
        f"📅 <b>التوقيت:</b> {datetime.now().strftime('%Y-%m-%d %I:%M %p')}\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "⚠️ <b>الحالة الآن:</b> محجوب بالكامل. عند القبول تبقى كل الميزات مغلقة حتى تحددها بنفسك:"
    )
    safe_send(SUPER_ADMIN_ID, alert_text, reply_markup=markup)


def check_user_access_gate(user, chat_id: int, notify_blocked: bool = True) -> bool:
    """
    بوابة الأمان والتحقق الصارمة:
    1. المطور الأكبر يمر فوراً بصلاحيات مطلقة لا تمس.
    2. أي مستخدم جديد يُسجل كـ 'pending' وكافة الأدوات مغلقة (False)، ويُرسل إشعار فوري للمطور.
    3. يمنع أي مستخدم غير معتمد أو محظور من لمس أي زر أو نص.
    """
    user_id = user.id
    full_name = f"{user.first_name or ''} {user.last_name or ''}".strip() or f"مستخدم_{user_id}"
    username = user.username or ""

    u_data, is_new = register_or_update_user(user_id, full_name, username)

    if is_super_admin(user_id):
        return True

    status = u_data.get("status", "pending")
    if status == "banned":
        if notify_blocked:
            safe_send(
                chat_id,
                "⛔ <b>تم حظر وصولك إلى هذا البوت من قبل المطور الرئيسي.</b>"
            )
        return False

    # وضع الفتح للعامة: انضمام تلقائي بصلاحية إضافة الحسابات ونظام النقاط
    if status == "pending" and ensure_public_access_if_enabled(user_id):
        update_menu_button_for_user(bot, user_id, is_allowed=True)
        if is_new:
            safe_send(
                SUPER_ADMIN_ID,
                f"🌐 <b>وضع العامة | مستخدم جديد دخل تلقائياً:</b> {esc(full_name)} (<code>{user_id}</code>)\n"
                "🔐 الصلاحية الابتدائية: إضافة حسابات فيسبوك فقط (+ نظام النقاط)."
            )
        return True

    inv_markup = types.InlineKeyboardMarkup()
    inv_markup.add(types.InlineKeyboardButton("🎟️ لدي كود دعوة / تفعيل", callback_data="enter_invite_code"))

    if is_new:
        notify_new_pending_user(user_id, full_name, username)
        update_menu_button_for_user(bot, user_id, is_allowed=False)

        if notify_blocked:
            safe_send(
                chat_id,
                "🔒 <b>منظومة FB Operator | الوصول مقفل</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "⚠️ لا يمكن استخدام النظام إلا بعد موافقة المطور الرئيسي أو إدخال <b>كود دعوة / رابط إحالة</b> من عضو مصرح.\n\n"
                "📩 <b>تم إرسال طلبك للمطور للمراجعة.</b>\n"
                "💡 إن كان لديك كود تفعيل (مثل <code>FB-XXXX-XXXX</code>) يمكنك إرساله مباشرة أو الضغط على الزر أدناه:",
                reply_markup=inv_markup
            )
        return False

    if status == "pending":
        if notify_blocked:
            safe_send(
                chat_id,
                "⏳ <b>طلبك قيد المراجعة لدى المطور الرئيسي.</b>\n"
                "سيتم إشعارك فور الموافقة، أو يمكنك فتح ميزة إضافة الحسابات فوراً عبر <b>كود الدعوة</b>:",
                reply_markup=inv_markup
            )
        return False

    return True


# ----------------- لوحات المفاتيح والأزرار التفاعلية المعزولة -----------------

REACTION_ICONS = {
    "like": "👍 إعجاب",
    "love": "❤️ أحببته",
    "care": "🤗 أدعمه",
    "haha": "😂 هاها",
    "wow": "😮 واو",
    "sad": "😢 أحزنني",
    "angry": "😡 أغضبني",
    "unlike": "👎 إلغاء الإعجاب"
}

REPORT_REASONS_AR = {
    "harassment": "مضايقة أو إساءة",
    "fake": "حساب مزيف / انتحال",
    "hate_violence": "عنف أو خطاب كراهية",
    "fraud": "احتيال وخداع",
    "adult": "محتوى غير لائق",
    "spam": "سبام / رسائل مزعجة"
}

REPORT_VICTIMS_AR = {
    "me": "أنا الشخص المتضرر",
    "not_real": "ليس شخصاً حقيقياً",
    "friend": "أحد أصدقائي"
}


def get_main_dashboard_markup(user_id: int) -> types.InlineKeyboardMarkup:
    markup = types.InlineKeyboardMarkup(row_width=2)
    st = get_user_state(user_id)

    is_dev = is_super_admin(user_id)
    p_use = is_dev or has_permission(user_id, "can_use_accounts")
    p_add = is_dev or has_permission(user_id, "can_add_accounts")
    p_react = is_dev or has_permission(user_id, "can_react")
    p_cmt = is_dev or has_permission(user_id, "can_comment")
    p_int = is_dev or has_permission(user_id, "can_interact_comments")
    p_fr = is_dev or has_permission(user_id, "can_friend_follow")
    p_msg = is_dev or has_permission(user_id, "can_message")
    p_rep = is_dev or has_permission(user_id, "can_report")
    p_del = is_dev or has_permission(user_id, "can_delete_accounts")
    p_exec = is_dev or has_permission(user_id, "can_execute")
    p_inv = can_user_invite(user_id)

    wallet = get_user_wallet(user_id)
    has_any_action = any((p_react, p_cmt, p_int, p_fr, p_msg, p_rep))
    has_any_feature = any((is_dev, p_use, p_add, p_del, p_exec, has_any_action, p_inv))
    usable_accs = get_usable_accounts_for_user(user_id) if (p_use or p_exec) else []
    manageable_accs = get_manageable_accounts_for_user(user_id)

    # 1. صف تحديد المنفذ والرابط المستهدف (فقط لمن لديه صلاحيات تشغيل/أدوات)
    top_btns = []
    if p_use or (p_exec and len(usable_accs) > 0 and has_any_action):
        sel_acc_name = "جميع الحسابات المتاحة"
        if st["selected_acc"] != "all":
            matched = next((a for a in usable_accs if a["id"] == st["selected_acc"]), None)
            if matched:
                sel_acc_name = matched["name"]
            else:
                st["selected_acc"] = "all"
        top_btns.append(types.InlineKeyboardButton(f"👤 المنفذ: {sel_acc_name}", callback_data="menu_select_acc"))

    if has_any_action:
        top_btns.append(types.InlineKeyboardButton("🔗 تعديل الرابط المستهدف", callback_data="menu_set_url"))

    if len(top_btns) == 2:
        markup.row(*top_btns)
    elif len(top_btns) == 1:
        markup.row(top_btns[0])

    # 2. التفاعلات
    if p_react:
        like_st = "✅" if st["like"] else "❌"
        react_lbl = REACTION_ICONS.get(st["reaction_type"], "👍 إعجاب")
        p_tag = "رابط مخصص" if st.get("react_post_url") else f"منشور {st['react_post_index']}"
        markup.row(
            types.InlineKeyboardButton(f"{react_lbl} [{like_st}] ({p_tag})", callback_data="menu_wizard_react")
        )

    # 3. التعليقات
    if p_cmt:
        cmt_st = "✅" if st["comment"] else "❌"
        c_tag = "رابط مخصص" if st.get("comment_post_url") else f"منشور {st['comment_post_index']}"
        markup.row(
            types.InlineKeyboardButton(f"💬 تعليق [{cmt_st}] ({c_tag})", callback_data="menu_wizard_comment")
        )

    # 4. التفاعل والرد على تعليق محدد
    if p_int:
        cmt_int_tag = "✅ نشط" if st["interact_cmt"] else "❌ معطل"
        markup.row(
            types.InlineKeyboardButton(f"🎯 تفاعل/رد على تعليق محدد [{cmt_int_tag}]", callback_data="menu_cmt_interact")
        )

    # 5. الصداقة والمتابعة والإلغاء
    if p_fr:
        fr_tag = "✅" if st["friend"] else "❌"
        fl_tag = "✅" if st["follow"] else "❌"
        markup.row(
            types.InlineKeyboardButton(f"➕ طلب صداقة [{fr_tag}]", callback_data="toggle_friend"),
            types.InlineKeyboardButton(f"🔔 متابعة [{fl_tag}]", callback_data="toggle_follow")
        )
        cfr_tag = "✅" if st["cancel_friend"] else "❌"
        unfl_tag = "✅" if st["unfollow"] else "❌"
        markup.row(
            types.InlineKeyboardButton(f"❌ إلغاء الصداقة [{cfr_tag}]", callback_data="toggle_cancel_friend"),
            types.InlineKeyboardButton(f"🔕 إلغاء المتابعة [{unfl_tag}]", callback_data="toggle_unfollow")
        )

    # 6. رسائل الماسنجر الخاصة
    if p_msg:
        msg_tag = "✅ نشط" if st["message"] else "❌ معطل"
        markup.row(
            types.InlineKeyboardButton(f"✉️ رسالة خاصة [{msg_tag}]", callback_data="toggle_message"),
            types.InlineKeyboardButton("✏️ تعديل نص الرسالة", callback_data="menu_msg_config")
        )

    # 7. البلاغات والحظر
    if p_rep:
        rep_p_tag = "✅" if st["report_post"] else "❌"
        rep_u_tag = "✅" if st["report_profile"] else "❌"
        markup.row(
            types.InlineKeyboardButton(f"🛡️ بلاغ منشور [{rep_p_tag}]", callback_data="toggle_rep_post"),
            types.InlineKeyboardButton(f"🛡️ بلاغ حساب [{rep_u_tag}]", callback_data="toggle_rep_profile")
        )
        blk_tag = "✅" if st["block"] else "❌"
        markup.row(
            types.InlineKeyboardButton(f"🚫 حظر الحساب [{blk_tag}]", callback_data="toggle_block"),
            types.InlineKeyboardButton("⚙️ تفاصيل البلاغ والسبب", callback_data="menu_rep_config")
        )

    # 8. إدارة وإضافة الحسابات (معزولة حسب الصلاحية)
    if is_dev or p_add or p_del:
        if p_add and not has_any_action and not p_use and not is_dev:
            # واجهة نظيفة لوضع "إضافة حسابات للبوت فقط"
            markup.row(types.InlineKeyboardButton("➕ إضافة حساب فيسبوك جديد للبوت", callback_data="act_add_acc"))
            markup.row(
                types.InlineKeyboardButton(f"📋 حساباتي المضافة ({len(manageable_accs)})", callback_data="menu_manage_accs"),
                types.InlineKeyboardButton("🔄 فحص جلساتي", callback_data="act_check_sessions")
            )
        else:
            row_acc = [types.InlineKeyboardButton(f"👥 إدارة الحسابات ({len(manageable_accs)})", callback_data="menu_manage_accs")]
            if p_add:
                row_acc.append(types.InlineKeyboardButton("➕ إضافة حساب", callback_data="act_add_acc"))
            markup.row(*row_acc)
            if is_dev or len(manageable_accs) > 0:
                markup.row(types.InlineKeyboardButton("🔄 فحص حالة الجلسات", callback_data="act_check_sessions"))

    # 9. قسم المحفظة والإحالات والدعم/البيع (يظهر عند امتلاك أي صلاحية أو رصيد)
    if is_dev:
        all_users = load_users()
        user_count = max(0, len(all_users) - 1)
        markup.row(
            types.InlineKeyboardButton(f"🛰️ رادار المستخدمين ({user_count})", callback_data="menu_surveillance_radar"),
            types.InlineKeyboardButton("⚙️ إعدادات النقاط والعامة", callback_data="menu_admin_economy")
        )
        markup.row(
            types.InlineKeyboardButton("📜 سجل الرقابة والأحداث", callback_data="menu_audit_logs"),
            types.InlineKeyboardButton("📩 تذاكر البيع والدعم", callback_data="menu_support")
        )
        markup.row(
            types.InlineKeyboardButton("💰 محفظتي وسجلي", callback_data="menu_wallet"),
            types.InlineKeyboardButton("🔗 روابط وأكواد الدعوة", callback_data="menu_referral")
        )
    elif has_any_feature or wallet["points"] > 0:
        eco_row = [types.InlineKeyboardButton(f"🪙 نقاطي ({wallet['points']} = {wallet['yer_value']:,} ر.ي)", callback_data="menu_wallet")]
        if p_inv:
            eco_row.append(types.InlineKeyboardButton("🎁 دعوة صديق (+4)", callback_data="menu_referral"))
        markup.row(*eco_row)
        markup.row(
            types.InlineKeyboardButton("💵 طلب بيع الحسابات / مراسلة المطور", callback_data="menu_support")
        )

    # 10. فتح لوحة التحكم التفاعلية داخل تلغرام فقط (WebApp داخل التطبيق بدون متصفح خارجي)
    webapp_url = get_public_webapp_url()
    if webapp_url and has_any_feature:
        markup.row(
            types.InlineKeyboardButton("📱 فتح لوحة التحكم داخل تلغرام", web_app=types.WebAppInfo(url=webapp_url))
        )

    # 11. زر الإطلاق الميداني (يظهر فقط إذا مُنح can_execute ولدى المستخدم أداة واحدة على الأقل)
    if p_exec and has_any_action and (p_use or len(usable_accs) > 0):
        markup.row(
            types.InlineKeyboardButton("🚀 بدء تنفيذ المهام الآن", callback_data="action_launch")
        )

    # 12. إذا كان المستخدم معتمداً لكن لم تُفتح له أي صلاحية بعد ولم يكن لديه رصيد
    if not has_any_feature and wallet["points"] <= 0:
        markup.row(types.InlineKeyboardButton("🔄 تحديث الصلاحيات والحالة", callback_data="back_to_main"))

    return markup


def get_dashboard_text(user_id: int) -> str:
    is_dev = is_super_admin(user_id)
    st = get_user_state(user_id)

    p_use = is_dev or has_permission(user_id, "can_use_accounts")
    p_add = is_dev or has_permission(user_id, "can_add_accounts")
    p_react = is_dev or has_permission(user_id, "can_react")
    p_cmt = is_dev or has_permission(user_id, "can_comment")
    p_int = is_dev or has_permission(user_id, "can_interact_comments")
    p_fr = is_dev or has_permission(user_id, "can_friend_follow")
    p_msg = is_dev or has_permission(user_id, "can_message")
    p_rep = is_dev or has_permission(user_id, "can_report")
    p_del = is_dev or has_permission(user_id, "can_delete_accounts")
    p_exec = is_dev or has_permission(user_id, "can_execute")
    p_inv = can_user_invite(user_id)

    has_any_action = any((p_react, p_cmt, p_int, p_fr, p_msg, p_rep))
    has_any_feature = any((is_dev, p_use, p_add, p_del, p_exec, has_any_action, p_inv))
    wallet = get_user_wallet(user_id)
    eco_cfg = load_economy_settings()

    if is_dev:
        all_accs = load_accounts()
        active_count = sum(1 for a in all_accs if "نشط" in a.get("status", ""))
        inactive_count = len(all_accs) - active_count
        role_title = "👑 المطور الرئيسي (Super Admin)"
        mode_tag = "🌐 مفتوح للعامة" if eco_cfg.get("public_mode") else "🔒 بموافقة / دعوة"
        acc_summary = (
            f"📊 <b>إجمالي حسابات النظام:</b> {len(all_accs)} ({active_count} نشط | {inactive_count} غير نشط)\n"
            f"⚙️ <b>وضع البوت:</b> {mode_tag} | <b>القيمة:</b> 1 نقطة = {wallet['yer_per_point']} ر.ي"
        )
    else:
        role_title = "🛡️ حساب معتمد بصلاحيات مخصصة"
        parts = []
        if p_use:
            pool_accs = load_accounts()
            active_pool = sum(1 for a in pool_accs if "نشط" in a.get("status", ""))
            parts.append(f"• <b>حسابات البوت المتاحة للتنفيذ:</b> {active_pool} حساب نشط")
        if p_add or p_del:
            bd = get_accounts_breakdown_by_owner(user_id)
            parts.append(
                f"• <b>حساباتك المضافة للبوت:</b> {len(bd['all'])} "
                f"(🟢 {len(bd['active'])} نشط | 🔴 {len(bd['inactive'])} غير نشط)"
            )
        if has_any_feature or wallet["points"] > 0:
            parts.append(
                f"• 🪙 <b>رصيد نقاطك:</b> {wallet['points']} نقطة "
                f"(≈ <b>{wallet['yer_value']:,} ريال يمني</b> | تم تسليم {wallet['total_yer_settled']:,} ر.ي)"
            )
        acc_summary = "\n".join(parts)

    if not is_dev:
        granted_list = [label for key, label in PERMISSION_LABELS.items() if has_permission(user_id, key)]
        perms_line = f"🔐 <b>صلاحياتك الحالية:</b> {', '.join(granted_list)}" if granted_list else "🔒 <b>صلاحياتك الحالية:</b> لا توجد ميزات مفعلة بعد"
    else:
        perms_line = "🔐 <b>صلاحياتك الحالية:</b> تحكم سيادي كامل 100%"

    lines = [
        "⚡ <b>منظومة FB Operator | لوحة التحكم السحابية</b>",
        "━━━━━━━━━━━━━━━━━━━━",
        f"👤 <b>الرتبة:</b> {role_title}",
        perms_line
    ]
    if acc_summary:
        lines.append(acc_summary)

    if has_any_action:
        lines.append(f"🎯 <b>الرابط المستهدف:</b> <code>{esc(st['target_url'][:55])}</code>")
        if p_exec and is_points_enforced_for_user(user_id):
            usable_accs = get_usable_accounts_for_user(user_id)
            op_cnt = estimate_mission_account_count(usable_accs, st)
            est_cost, _ = calculate_mission_cost(st, op_cnt)
            lines.append(f"💸 <b>تكلفة التنفيذ الحالية:</b> {est_cost} نقطة (على {op_cnt} حساب)")
    if p_react:
        react_info = REACTION_ICONS.get(st["reaction_type"], "👍 إعجاب")
        post_info = "رابط مخصص" if st.get("react_post_url") else f"المنشور {st['react_post_index']}"
        lines.append(f"💖 <b>التفاعل المحدد:</b> {react_info} ({post_info})")
    if p_cmt:
        lines.append(f"💬 <b>التعليق المجهز:</b> <i>'{esc(st['comment_text'][:35])}'</i> (منشور {st['comment_post_index']})")

    lines.append("━━━━━━━━━━━━━━━━━━━━")
    if not has_any_feature and wallet["points"] <= 0:
        lines.append("⏳ <b>حسابك معتمد الآن، يرجى انتظار قيام المطور بفتح الميزات المسموحة لك من رادار الصلاحيات.</b>")
    elif p_add and not has_any_action and not p_use and not is_dev:
        act_rew = int(eco_cfg.get("active_account_reward", 1) or 1)
        lines.append(
            f"👇 <b>وضع التوريد والربح: كل حساب فيسبوك نشط يمنحك +{act_rew} نقطة ({act_rew * wallet['yer_per_point']} ريال يمني):</b>"
        )
    else:
        lines.append("👇 <b>اختر الأداة أو عدّل الإعدادات من الأزرار أدناه:</b>")

    return "\n".join(lines)


# ----------------- عرض بطاقة المراقبة وسجل الرقابة للمطور -----------------

def render_surveillance_radar_text_and_markup():
    users = load_users()
    accs = load_accounts()
    markup = types.InlineKeyboardMarkup(row_width=1)

    pending_users = [u for u in users.values() if u.get("status") == "pending"]
    approved_users = [u for u in users.values() if u.get("status") == "approved" and not is_super_admin(u.get("id"))]
    banned_users = [u for u in users.values() if u.get("status") == "banned"]

    if pending_users:
        markup.add(types.InlineKeyboardButton("⏳ --- طلبات انضمام قيد الانتظار ---", callback_data="noop"))
        for pu in pending_users:
            uid = pu["id"]
            markup.row(
                types.InlineKeyboardButton(f"👤 {pu['name']} ({uid})", callback_data=f"surv_user_{uid}"),
                types.InlineKeyboardButton("✅ قبول", callback_data=f"gate_app_{uid}"),
                types.InlineKeyboardButton("🚫 حظر", callback_data=f"gate_ban_{uid}")
            )

    markup.add(types.InlineKeyboardButton("👥 --- المستخدمون المعتمدون وسجلاتهم ---", callback_data="noop"))
    if not approved_users:
        markup.add(types.InlineKeyboardButton("لا يوجد مستخدمون معتمدون غير المطور حالياً", callback_data="noop"))
    eco_cfg = load_economy_settings()
    rate = int(eco_cfg.get("yer_per_point", 10) or 10)
    total_perms = max(1, len(PERMISSION_LABELS))
    for u in approved_users:
        bd = get_accounts_breakdown_by_owner(u["id"])
        u_name = u.get("name", f"مستخدم_{u['id']}")
        active_n = len(bd["active"])
        inactive_n = len(bd["inactive"])
        enabled_perms = sum(1 for v in u.get("permissions", {}).values() if v)
        pts = int(u.get("points", 0) or 0)
        markup.add(
            types.InlineKeyboardButton(
                f"👤 {u_name} | 🪙{pts}ن ({pts * rate:,}ر.ي) | 🟢{active_n} 🔴{inactive_n} | {enabled_perms}/{total_perms}",
                callback_data=f"surv_user_{u['id']}"
            )
        )

    if banned_users:
        markup.add(types.InlineKeyboardButton("🚫 --- المستخدمون المحظورون ---", callback_data="noop"))
        for bu in banned_users:
            markup.add(types.InlineKeyboardButton(f"🚫 {bu['name']} (محظور)", callback_data=f"surv_user_{bu['id']}"))

    markup.add(types.InlineKeyboardButton("📜 عرض سجل الرقابة والأحداث الكامل", callback_data="menu_audit_logs"))
    markup.add(types.InlineKeyboardButton("🔙 العودة للوحة الرئيسية", callback_data="back_to_main"))

    active_total = sum(1 for a in accs if "نشط" in a.get("status", ""))
    inactive_total = len(accs) - active_total

    txt = (
        "🛰️ <b>رادار المراقبة الشامل والتحكم بالصلاحيات:</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"👑 <b>المطور الرئيسي الحصين:</b> <code>{SUPER_ADMIN_ID}</code>\n"
        f"👥 <b>إجمالي المسجلين بالرادار:</b> {max(0, len(users) - 1)}\n"
        f"🟢 <b>المعتمدون:</b> {len(approved_users)} | ⏳ <b>المعلقون:</b> {len(pending_users)} | 🚫 <b>المحظورون:</b> {len(banned_users)}\n"
        f"📊 <b>الحسابات بالنظام:</b> {len(accs)} (🟢 {active_total} نشط | 🔴 {inactive_total} غير نشط)\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "👇 <b>اختر أي مستخدم لعرض حساباته (النشطة والفاشلة + كلمات السر) وتحديد صلاحياته بدقة:</b>"
    )
    return txt, markup


def render_user_dossier(t_id: int):
    users = load_users()
    u = users.get(str(t_id))
    if not u or is_super_admin(t_id):
        return None, None

    bd = get_accounts_breakdown_by_owner(t_id)
    p = u.get("permissions", {})
    wallet = get_user_wallet(t_id)

    markup = types.InlineKeyboardMarkup(row_width=2)
    # 11 زر تحكم دقيق لكل ميزة بشكل منفصل تماماً
    perm_pairs = [
        ("can_use_accounts", "🔑 استخدام حسابات البوت", "can_add_accounts", "➕ إضافة حسابات فقط/جديدة"),
        ("can_react", "💖 التفاعلات والإعجاب", "can_comment", "💬 كتابة التعليقات"),
        ("can_interact_comments", "🎯 الرد ع تعليق محدد", "can_friend_follow", "👥 الصداقة والمتابعة"),
        ("can_message", "✉️ الرسائل الخاصة", "can_report", "🛡️ البلاغات والحظر"),
        ("can_delete_accounts", "🗑️ حذف حساباته", "can_execute", "🚀 زر التشغيل والتنفيذ")
    ]
    for k1, l1, k2, l2 in perm_pairs:
        s1 = "✅" if p.get(k1) else "❌"
        s2 = "✅" if p.get(k2) else "❌"
        markup.row(
            types.InlineKeyboardButton(f"{l1}: {s1}", callback_data=f"surv_perm_{t_id}_{k1}"),
            types.InlineKeyboardButton(f"{l2}: {s2}", callback_data=f"surv_perm_{t_id}_{k2}")
        )

    s_inv = "✅" if p.get("can_invite") else "❌"
    markup.row(
        types.InlineKeyboardButton(f"🔗 روابط وأكواد الإحالة: {s_inv}", callback_data=f"surv_perm_{t_id}_can_invite")
    )

    markup.row(
        types.InlineKeyboardButton("➕ إضافة +5 نقاط", callback_data=f"surv_pts_add5_{t_id}"),
        types.InlineKeyboardButton("➖ خصم -5 نقاط", callback_data=f"surv_pts_sub5_{t_id}"),
        types.InlineKeyboardButton("✏️ تعديل/خصم رقم", callback_data=f"surv_pts_custom_{t_id}")
    )
    markup.row(
        types.InlineKeyboardButton("💸 تسوية ودفع كل المستحقات", callback_data=f"surv_pts_settle_{t_id}"),
        types.InlineKeyboardButton("📩 التذاكر والمحادثة", callback_data="menu_support")
    )
    markup.row(types.InlineKeyboardButton("🔒 تصفير وإغلاق كافة الصلاحيات", callback_data=f"surv_revoke_all_{t_id}"))

    if u.get("status") == "banned":
        markup.row(types.InlineKeyboardButton("✅ فك الحظر عن المستخدم", callback_data=f"surv_unban_{t_id}"))
    elif u.get("status") == "pending":
        markup.row(
            types.InlineKeyboardButton("✅ اعتماد المستخدم", callback_data=f"gate_app_{t_id}"),
            types.InlineKeyboardButton("🚫 حظر المستخدم", callback_data=f"surv_ban_{t_id}")
        )
    else:
        markup.row(types.InlineKeyboardButton("🚫 حظر هذا المستخدم", callback_data=f"surv_ban_{t_id}"))

    markup.row(
        types.InlineKeyboardButton("🗑️ حذف المستخدم وحساباته", callback_data=f"surv_del_{t_id}"),
        types.InlineKeyboardButton("🔙 رجوع للرادار", callback_data="menu_surveillance_radar")
    )

    st_map = {"approved": "معتمد ومصرح ✅", "pending": "قيد الانتظار ⏳", "banned": "محظور نهائياً 🚫"}
    uname = f"@{esc(u.get('username'))}" if u.get("username") else "بدون معرف"
    ref_line = f" | مدعو من: <code>{wallet['referred_by']}</code>" if wallet.get("referred_by") else ""
    header = (
        f"👤 <b>بطاقة المراقبة الشاملة: {esc(u.get('name'))}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"🆔 <b>الآيدي:</b> <code>{t_id}</code> | <b>المعرف:</b> {uname}\n"
        f"🛡️ <b>الحالة:</b> {st_map.get(u.get('status'), esc(u.get('status')))}\n"
        f"🪙 <b>الرصيد المالي:</b> {wallet['points']} نقطة = <b>{wallet['yer_value']:,} ريال يمني</b>\n"
        f"💵 <b>المكتسب:</b> {wallet['total_points_earned']}ن | <b>المخصوم:</b> {wallet['total_points_spent']}ن | <b>المُسلّم:</b> {wallet['total_yer_settled']:,} ر.ي\n"
        f"🤝 <b>الإحالات الناجحة:</b> {wallet['referred_count']}{ref_line}\n"
        f"📅 <b>أول دخول:</b> {esc(u.get('first_seen'))} | ⏱️ <b>آخر نشاط:</b> {esc(u.get('last_seen'))}\n"
        f"🔄 <b>الدخول:</b> {u.get('total_logins', 1)} | ⚡ <b>العمليات:</b> {u.get('operations_count', 0)}\n"
        f"📈 <b>السجل التاريخي الدائم للمضافات:</b> 🟢 {u.get('active_accounts_added', 0)} نشط | 🔴 {u.get('inactive_accounts_added', 0)} غير نشط\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
    )

    body_lines = []
    body_lines.append(f"🟢 <b>الحسابات النشطة المسجلة حالياً ({len(bd['active'])}):</b>")
    if bd["active"]:
        for idx, a in enumerate(bd["active"][-10:], 1):
            fb_id = f" | FB:<code>{esc(a.get('fb_id'))}</code>" if a.get("fb_id") else ""
            body_lines.append(
                f"<b>{idx}. {esc(a['name'])}</b> (<code>{esc(a['id'])}</code>){fb_id}\n"
                f"   📧 <code>{esc(a['email'])}</code> | 🔑 <code>{esc(a['password'])}</code>\n"
                f"   📅 {esc(a.get('added_at', 'سابقاً'))}"
            )
    else:
        body_lines.append("<i>لا توجد حسابات نشطة مسجلة من هذا المستخدم حالياً.</i>")

    body_lines.append(f"\n🔴 <b>الحسابات غير النشطة / الفاشلة ({len(bd['inactive'])}):</b>")
    if bd["inactive"]:
        for idx, a in enumerate(bd["inactive"][-10:], 1):
            reason = esc(a.get("diagnostic_reason") or a.get("status") or "يتطلب تسجيل الدخول")
            body_lines.append(
                f"<b>{idx}. {esc(a['name'])}</b> (<code>{esc(a['id'])}</code>)\n"
                f"   📧 <code>{esc(a['email'])}</code> | 🔑 <code>{esc(a['password'])}</code>\n"
                f"   ⚠️ السبب: {reason} | 📅 {esc(a.get('added_at', 'سابقاً'))}"
            )
    else:
        body_lines.append("<i>لا توجد حسابات فاشلة أو غير نشطة لهذا المستخدم.</i>")

    footer = "\n\n👇 <b>حدّد الصلاحيات الفردية لهذا المستخدم أدناه (كل ميزة منفصلة):</b>"
    txt = header + "\n".join(body_lines) + footer
    # حماية صارمة من حد 4096 حرفاً في تلغرام
    if len(txt) > 3950:
        cutoff = 3900 - len(header) - len(footer)
        body_str = "\n".join(body_lines)[:max(200, cutoff)] + "\n... (تم اختصار البقية للالتزام بحد الرسالة)"
        txt = header + body_str + footer
    return txt, markup


def _render_audit_logs_view() -> tuple[str, types.InlineKeyboardMarkup]:
    logs = load_audit_logs(limit=22)
    lines = [
        "📜 <b>سجل الرقابة والأحداث الكامل (Audit Log):</b>",
        "━━━━━━━━━━━━━━━━━━━━"
    ]
    if not logs:
        lines.append("<i>لا توجد أحداث مسجلة حتى الآن.</i>")
    else:
        for lg in reversed(logs):
            ev = esc(lg.get("event"))
            ts = esc(lg.get("timestamp", ""))[5:]
            uname = esc(lg.get("user_name") or lg.get("user_id"))
            uid = esc(lg.get("user_id"))
            det = esc(lg.get("details", ""))
            lines.append(f"• <code>{ts}</code> | <b>[{ev}]</b>\n  👤 {uname} (<code>{uid}</code>)\n  📝 {det}")

    txt = "\n".join(lines)
    if len(txt) > 3950:
        txt = txt[:3920] + "\n..."
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(
        types.InlineKeyboardButton("🔄 تحديث السجل", callback_data="menu_audit_logs"),
        types.InlineKeyboardButton("🛰️ رادار المستخدمين", callback_data="menu_surveillance_radar")
    )
    markup.row(types.InlineKeyboardButton("🔙 اللوحة الرئيسية", callback_data="back_to_main"))
    return txt, markup


def _render_manage_accs_view(user_id: int) -> tuple[str, types.InlineKeyboardMarkup]:
    is_dev = is_super_admin(user_id)
    accs = get_manageable_accounts_for_user(user_id)
    can_del = is_dev or has_permission(user_id, "can_delete_accounts")
    can_add = is_dev or has_permission(user_id, "can_add_accounts")

    markup = types.InlineKeyboardMarkup(row_width=2)
    for a in accs[-20:]:
        st_icon = "🟢" if "نشط" in a.get("status", "") else "🔴"
        if can_del:
            markup.row(
                types.InlineKeyboardButton(f"{st_icon} {a['name']}", callback_data="noop"),
                types.InlineKeyboardButton("🗑️ حذف", callback_data=f"del_acc_{a['id']}")
            )
        else:
            markup.row(types.InlineKeyboardButton(f"{st_icon} {a['name']}", callback_data="noop"))

    if can_add:
        markup.row(types.InlineKeyboardButton("➕ إضافة حساب جديد للبوت", callback_data="act_add_acc"))
    if can_del:
        markup.row(types.InlineKeyboardButton("🧹 تنظيف وحذف الحسابات التالفة", callback_data="act_purge_broken"))
    markup.row(
        types.InlineKeyboardButton("🔄 فحص الجلسات", callback_data="act_check_sessions"),
        types.InlineKeyboardButton("🔙 رجوع", callback_data="back_to_main")
    )

    title = "👥 <b>إدارة كافة حسابات النظام:</b>\n\n" if is_dev else "📋 <b>حساباتك التي قمت بإضافتها للبوت:</b>\n\n"
    txt = title
    for i, a in enumerate(accs, 1):
        st_text = "🟢 نشط ومسجل" if "نشط" in a.get("status", "") else f"🔴 غير نشط ({esc(a.get('diagnostic_reason') or 'يتطلب تسجيل دخول')})"
        owner_lbl = a.get("owner_name") or a.get("owner_id") or "المطور الرئيسي"
        owner_badge = f" | المضيف: {esc(owner_lbl)}" if is_dev else ""
        txt += f"{i}. <b>{esc(a['name'])}</b> (<code>{esc(a['id'])}</code>){owner_badge}\n   📧 <code>{esc(a['email'])}</code> | {st_text}\n"
    if not accs:
        txt += "<i>لا توجد حسابات مسجلة في هذا السجل حتى الآن.</i>"
    if len(txt) > 3950:
        txt = txt[:3920] + "\n..."
    return txt, markup


def _render_wallet_view(uid: int) -> tuple[str, types.InlineKeyboardMarkup]:
    wallet = get_user_wallet(uid)
    ledger = load_points_ledger(user_id=uid, limit=12)
    eco_cfg = load_economy_settings()
    lines = [
        "🪙 <b>محفظة النقاط والتقييم المالي</b>",
        "━━━━━━━━━━━━━━━━━━━━",
        f"💰 <b>الرصيد الحالي:</b> <b>{wallet['points']}</b> نقطة (≈ <b>{wallet['yer_value']:,} ريال يمني</b>)",
        f"💵 <b>سعر الصرف:</b> 1 نقطة = <b>{wallet['yer_per_point']} ريال يمني</b>",
        f"🎁 <b>مكافأة تفعيل الحساب:</b> +{eco_cfg.get('active_account_reward', 1)} نقطة | 🤝 <b>الإحالة:</b> +{eco_cfg.get('referral_reward', 4)} نقاط",
        f"📈 <b>إجمالي المكتسب:</b> {wallet['total_points_earned']}ن | <b>المستخدم/المسحوب:</b> {wallet['total_points_spent']}ن | <b>المُسلّم:</b> {wallet['total_yer_settled']:,} ر.ي",
        "━━━━━━━━━━━━━━━━━━━━",
        "📜 <b>آخر الحركات في السجل الفيزيائي للنقاط:</b>"
    ]
    if not ledger:
        lines.append("<i>لا توجد حركات مسجلة في محفظتك بعد.</i>")
    else:
        for tx in ledger[:10]:
            d = int(tx.get("delta", 0) or 0)
            sign = f"+{d}" if d > 0 else str(d)
            lines.append(
                f"• <code>{esc(tx.get('timestamp', '')[5:])}</code> | <b>{sign} نقطة</b> (الرصيد: {tx.get('balance_after', 0)})\n"
                f"  📝 {esc(tx.get('reason', tx.get('tx_type', '')))}"
            )
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(
        types.InlineKeyboardButton("🔄 تحديث الرصيد", callback_data="menu_wallet"),
        types.InlineKeyboardButton("💵 بيع / دعم المطور", callback_data="menu_support")
    )
    if can_user_invite(uid):
        markup.row(types.InlineKeyboardButton("🎁 رابط وأكواد الدعوة (+4)", callback_data="menu_referral"))
    markup.row(types.InlineKeyboardButton("🔙 اللوحة الرئيسية", callback_data="back_to_main"))
    return "\n".join(lines), markup


def _render_referral_view(uid: int) -> tuple[str, types.InlineKeyboardMarkup]:
    wallet = get_user_wallet(uid)
    eco_cfg = load_economy_settings()
    personal_code = get_or_create_personal_ref_code(uid)
    bot_uname = get_bot_username()
    ref_link = f"https://t.me/{bot_uname}?start=ref_{personal_code}" if bot_uname else f"/start ref_{personal_code}"
    codes = list_invite_codes_by_owner(uid)
    trig_ar = "فوراً عند أول تفعيل حساب نشط للصديق" if eco_cfg.get("referral_trigger") != "instant" else "فوراً عند إدخال الصديق للكود/الرابط"
    lines = [
        "🎁 <b>نظام الدعوات والأكواد (+4 نقاط لكل صديق)</b>",
        "━━━━━━━━━━━━━━━━━━━━",
        f"🔗 <b>رابط الإحالة الخاص بك:</b>\n<code>{esc(ref_link)}</code>",
        f"🔑 <b>كودك الدائم للاستخدام المباشر:</b> <code>{esc(personal_code)}</code>",
        f"⚙️ <b>شرط المكافأة (+{eco_cfg.get('referral_reward', 4)} نقاط):</b> {trig_ar}",
        "🛡️ <i>ملاحظة أمنية: الكود يفتح للصديق ميزة إضافة حسابات فيسبوك فقط دون المساس بحسابات الآخرين.</i>",
        "━━━━━━━━━━━━━━━━━━━━",
        f"🤝 <b>أصدقاؤك المنضمون عبرك:</b> {wallet['referred_count']} | 🎟️ <b>أكواد التفعيل الفردية:</b>"
    ]
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(
        types.InlineKeyboardButton("🎟️ توليد كود تفعيل فردي (لمرة واحدة)", callback_data="ref_gen_code")
    )
    shown = 0
    for c in reversed(codes):
        code_s = c.get("code", "")
        active_c = c.get("status") == "active" and int(c.get("uses", 0)) < int(c.get("max_uses", 1))
        st_lbl = "🟢 جاهز" if active_c else f"⚪ {c.get('status', 'مستخدم')} ({c.get('uses', 0)}/{c.get('max_uses', 1)})"
        lines.append(f"• <code>{esc(code_s)}</code> — {st_lbl}")
        if active_c and shown < 5:
            safe_cb_code = code_s.replace("-", "_")
            markup.row(
                types.InlineKeyboardButton(f"❌ إبطال {code_s}", callback_data=f"ref_rev_{safe_cb_code}")
            )
            shown += 1
    if not codes:
        lines.append("<i>اضغط 'توليد كود تفعيل فردي' أعلاه لإنشاء كود جاهز للإرسال لأي شخص.</i>")
    markup.row(
        types.InlineKeyboardButton("🔄 تحديث", callback_data="menu_referral"),
        types.InlineKeyboardButton("🔙 اللوحة الرئيسية", callback_data="back_to_main")
    )
    return "\n".join(lines), markup


def _render_support_view(uid: int) -> tuple[str, types.InlineKeyboardMarkup]:
    is_dev = is_super_admin(uid)
    snap = build_user_settlement_snapshot(uid)
    tickets = list_support_tickets(uid, is_dev=is_dev, limit=12)
    lines = [
        "📩 <b>الدعم الفني واتفاقية بيع الحسابات للمطور</b>" if not is_dev else "📩 <b>صندوق تذاكر البيع والدعم الواردة للمطور</b>",
        "━━━━━━━━━━━━━━━━━━━━"
    ]
    if not is_dev:
        lines.append(
            f"📊 <b>كشفك المالي الموثق:</b> {snap['active_added']} حساب نشط | "
            f"🪙 {snap['points']} نقطة = <b>{snap['yer_value']:,} ريال يمني</b>\n"
            f"💵 <b>المُسلّم سابقاً:</b> {snap['total_yer_settled']:,} ر.ي"
        )
        lines.append("━━━━━━━━━━━━━━━━━━━━")

    markup = types.InlineKeyboardMarkup(row_width=2)
    if not is_dev:
        markup.row(
            types.InlineKeyboardButton("💵 أوافق على بيع حساباتي للمطور", callback_data="sup_sell_start"),
            types.InlineKeyboardButton("💬 رسالة / استفسار للمطور", callback_data="sup_msg_start")
        )

    if not tickets:
        lines.append("<i>لا توجد تذاكر أو محادثات مسجلة حتى الآن.</i>")
    else:
        for t in tickets[:10]:
            tid = t.get("id", "")
            kind_lbl = "💵 بيع حسابات" if t.get("kind") == "sell_accounts" else "💬 دعم"
            st_lbl = {
                "open": "🟢 مفتوحة",
                "replied_by_dev": "🔵 رد المطور",
                "replied_by_user": "🟡 رد المستخدم",
                "settled": "✅ تم الدفع والتسوية",
            }.get(t.get("status"), t.get("status", ""))
            u_info = f" | {esc(t.get('user_name'))} ({t.get('user_id')})" if is_dev else ""
            lines.append(f"• <code>{esc(tid)}</code> | {kind_lbl}{u_info} — {st_lbl}")
            btn_lbl = f"📬 فتح #{tid} ({t.get('user_name', '')[:12]})" if is_dev else f"📬 فتح المحادثة #{tid}"
            markup.row(types.InlineKeyboardButton(btn_lbl, callback_data=f"sup_view_{tid}"))

    markup.row(
        types.InlineKeyboardButton("🔄 تحديث", callback_data="menu_support"),
        types.InlineKeyboardButton("🔙 اللوحة الرئيسية", callback_data="back_to_main")
    )
    return "\n".join(lines), markup


def _render_ticket_detail_view(viewer_uid: int, ticket_id: str) -> tuple[str, types.InlineKeyboardMarkup]:
    t = get_ticket_by_id(ticket_id)
    if not t:
        return "⚠️ التذكرة غير موجودة.", _back_home_markup("menu_support")
    is_dev = is_super_admin(viewer_uid)
    if not is_dev and int(t.get("user_id", 0)) != int(viewer_uid):
        return "⛔ غير مصرح لك بعرض هذه التذكرة.", _back_home_markup("back_to_main")

    snap = t.get("snapshot", {})
    live_snap = t.get("live_snapshot") or build_user_settlement_snapshot(int(t.get("user_id", 0)))
    st_lbl = {
        "open": "🟢 مفتوحة",
        "replied_by_dev": "🔵 رد المطور",
        "replied_by_user": "🟡 رد المستخدم",
        "settled": "✅ مسددة ومُغلقة",
    }.get(t.get("status"), t.get("status", ""))
    uname = f"@{esc(live_snap.get('username'))}" if live_snap.get("username") else "بدون معرف"
    lines = [
        f"📬 <b>تذكرة #{esc(t['id'])}</b> | {st_lbl}",
        "━━━━━━━━━━━━━━━━━━━━",
        f"👤 <b>المستخدم:</b> {esc(live_snap.get('name'))} ({uname}) | <code>{live_snap.get('user_id')}</code>",
        f"📊 <b>الحسابات الفعلية الآن:</b> 🟢 {live_snap.get('active_added', 0)} نشط | 🔴 {live_snap.get('inactive_added', 0)} غير نشط (إجمالي {live_snap.get('total_added', 0)})",
        f"🪙 <b>الرصيد الحالي:</b> {live_snap.get('points', 0)} نقطة = <b>{live_snap.get('yer_value', 0):,} ريال يمني</b> (عند الطلب: {snap.get('points', 0)}ن)",
        f"💵 <b>المسدد سابقاً:</b> {live_snap.get('total_yer_settled', 0):,} ر.ي",
        "━━━━━━━━━━━━━━━━━━━━",
        "💬 <b>سجل المحادثة المتبادل:</b>"
    ]
    for m in t.get("messages", [])[-12:]:
        role = "👑 المطور" if m.get("sender") == "developer" else f"👤 {esc(m.get('sender_name') or 'المستخدم')}"
        lines.append(f"<b>{role}</b> (<code>{esc(m.get('timestamp', '')[5:])}</code>):\n{esc(m.get('text', ''))}")

    markup = types.InlineKeyboardMarkup(row_width=2)
    if is_dev:
        markup.row(
            types.InlineKeyboardButton("↩️ الرد على المستخدم", callback_data=f"tkt_reply_{t['id']}"),
            types.InlineKeyboardButton("💸 اعتماد الدفع وتسوية النقاط", callback_data=f"tkt_settle_{t['id']}")
        )
        markup.row(types.InlineKeyboardButton("👤 بطاقة المستخدم", callback_data=f"surv_user_{t.get('user_id')}"))
    else:
        markup.row(types.InlineKeyboardButton("↩️ الرد على المطور", callback_data=f"user_reply_tkt_{t['id']}"))
    markup.row(types.InlineKeyboardButton("🔙 كل التذاكر", callback_data="menu_support"))
    txt = "\n".join(lines)
    if len(txt) > 3950:
        txt = txt[:3920] + "\n..."
    return txt, markup


def _render_admin_economy_view() -> tuple[str, types.InlineKeyboardMarkup]:
    cfg = load_economy_settings()
    costs = cfg.get("operation_costs", {})
    lines = [
        "⚙️ <b>لوحة سياسة الاقتصاد والنقاط والوضع العام (للمطور)</b>",
        "━━━━━━━━━━━━━━━━━━━━",
        f"🌐 <b>وضع العامّة (انضمام تلقائي للإضافة):</b> {'🟢 مفعّل' if cfg.get('public_mode') else '🔴 معطّل (بموافقة/كود فقط)'}",
        f"🛡️ <b>فرض خصم النقاط عند التنفيذ:</b> {'🟢 مفعّل' if cfg.get('enforce_points_on_actions') else '🔴 معطّل (للعامة فقط أو مجاني)'}",
        f"🤝 <b>السماح للموردين بدعوة أصدقاء:</b> {'🟢 نعم' if cfg.get('suppliers_can_invite') else '🔴 لا'}",
        f"♻️ <b>توريث الدعوة للمدعوّين الجدد:</b> {'🟢 نعم' if cfg.get('invited_suppliers_can_invite') else '🔴 لا'}",
        f"🎯 <b>استحقاق مكافأة الإحالة (+{cfg.get('referral_reward', 4)}):</b> {'عند أول حساب نشط 🛡️' if cfg.get('referral_trigger') != 'instant' else 'فوراً عند الدخول ⚡'}",
        "━━━━━━━━━━━━━━━━━━━━",
        f"💵 <b>قيمة النقطة:</b> 1 نقطة = <b>{cfg.get('yer_per_point', 10)} ريال يمني</b>",
        f"➕ <b>مكافأة تفعيل الحساب:</b> +{cfg.get('active_account_reward', 1)} نقطة",
        f"🎁 <b>مكافأة الإحالة:</b> +{cfg.get('referral_reward', 4)} نقاط",
        "💸 <b>تكاليف التنفيذ بالعمليات (لكل حساب):</b>"
    ]
    for ck, clbl in OP_COST_LABELS_AR.items():
        lines.append(f"• {clbl}: <b>{costs.get(ck, 1)}</b> نقطة")

    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(
        types.InlineKeyboardButton(f"🌐 وضع العامة: {'🟢' if cfg.get('public_mode') else '🔴'}", callback_data="eco_tog_public_mode"),
        types.InlineKeyboardButton(f"🛡️ فرض النقاط: {'🟢' if cfg.get('enforce_points_on_actions') else '🔴'}", callback_data="eco_tog_enforce_points_on_actions")
    )
    markup.row(
        types.InlineKeyboardButton(f"🤝 دعوات الموردين: {'🟢' if cfg.get('suppliers_can_invite') else '🔴'}", callback_data="eco_tog_suppliers_can_invite"),
        types.InlineKeyboardButton(f"♻️ توريث الدعوة: {'🟢' if cfg.get('invited_suppliers_can_invite') else '🔴'}", callback_data="eco_tog_invited_suppliers_can_invite")
    )
    markup.row(
        types.InlineKeyboardButton("🎯 شرط الإحالة (فوري/أول حساب)", callback_data="eco_tog_referral_trigger"),
        types.InlineKeyboardButton(f"💵 سعر النقطة ({cfg.get('yer_per_point', 10)} ر.ي)", callback_data="eco_set_yer_per_point")
    )
    markup.row(
        types.InlineKeyboardButton(f"➕ مكافأة الحساب ({cfg.get('active_account_reward', 1)})", callback_data="eco_set_active_account_reward"),
        types.InlineKeyboardButton(f"🎁 مكافأة الإحالة ({cfg.get('referral_reward', 4)})", callback_data="eco_set_referral_reward")
    )
    markup.row(
        types.InlineKeyboardButton(f"👍 تكلفة إعجاب ({costs.get('like', 1)})", callback_data="eco_set_like"),
        types.InlineKeyboardButton(f"💬 تكلفة تعليق ({costs.get('comment', 2)})", callback_data="eco_set_comment")
    )
    markup.row(
        types.InlineKeyboardButton(f"✉️ تكلفة رسالة ({costs.get('message', 3)})", callback_data="eco_set_message"),
        types.InlineKeyboardButton(f"🛡️ تكلفة بلاغ ({costs.get('report_post', 5)})", callback_data="eco_set_report_post")
    )
    markup.row(
        types.InlineKeyboardButton("🔄 تحديث", callback_data="menu_admin_economy"),
        types.InlineKeyboardButton("🔙 اللوحة الرئيسية", callback_data="back_to_main")
    )
    return "\n".join(lines), markup


def _refresh_tracked_inline_view(uid: int) -> None:
    if not hasattr(bot, "edit_message_text"):
        return
    with _active_views_lock:
        entry = dict(_active_views.get(uid) or {})
    if not entry:
        return

    now = time.monotonic()
    elapsed = now - entry.get("last_push", 0.0)
    if elapsed < 1.2:
        # انتظر باقي مهلة منع التشبع بدلاً من إسقاط آخر تحديث حي (Trailing-Edge Coalescing)
        time.sleep(1.2 - elapsed)
        now = time.monotonic()
    with _active_views_lock:
        latest = _active_views.get(uid)
        if not latest:
            return
        latest["last_push"] = now
        entry = dict(latest)

    view = entry["view"]
    chat_id = entry["chat_id"]
    msg_id = entry["msg_id"]
    target_id = entry.get("target_id", 0)

    if view == "main":
        txt = get_dashboard_text(uid)
        markup = get_main_dashboard_markup(uid)
    elif view == "radar" and is_super_admin(uid):
        txt, markup = render_surveillance_radar_text_and_markup()
    elif view == "dossier" and is_super_admin(uid) and target_id:
        txt, markup = render_user_dossier(target_id)
        if not txt:
            txt, markup = render_surveillance_radar_text_and_markup()
    elif view == "audit" and is_super_admin(uid):
        txt, markup = _render_audit_logs_view()
    elif view == "manage_accs":
        txt, markup = _render_manage_accs_view(uid)
    elif view == "wallet":
        txt, markup = _render_wallet_view(uid)
    elif view == "referral" and can_user_invite(uid):
        txt, markup = _render_referral_view(uid)
    elif view == "support":
        txt, markup = _render_support_view(uid)
    elif view == "ticket" and entry.get("ticket_id"):
        txt, markup = _render_ticket_detail_view(uid, str(entry.get("ticket_id")))
    elif view == "economy" and is_super_admin(uid):
        txt, markup = _render_admin_economy_view()
    else:
        return

    try:
        bot.edit_message_text(txt, chat_id, msg_id, reply_markup=markup)
    except Exception:
        pass


def _live_inline_sync_worker() -> None:
    while True:
        with _live_sync_cond:
            while not _live_sync_pending_uids:
                _live_sync_cond.wait(timeout=30.0)
            uids = list(_live_sync_pending_uids)
            _live_sync_pending_uids.clear()
        time.sleep(0.35)  # دمج التحديثات المتتالية السريعة في ضغطة واحدة
        for uid in uids:
            try:
                _refresh_tracked_inline_view(uid)
            except Exception:
                pass


def _on_state_event(scope: str, target_uid: int, reason: str) -> None:
    """مستمع فوري لتحديث الرسائل النشطة في تلغرام فور حدوث أي عملية أو تسجيل جديد"""
    with _active_views_lock:
        tracked_uids = list(_active_views.keys())
    if not tracked_uids:
        return

    to_wake: list[int] = []
    for uid in tracked_uids:
        if is_super_admin(uid):
            to_wake.append(uid)
        elif target_uid == uid or (target_uid == 0 and scope == "economy") or (scope == "accounts" and has_permission(uid, "can_use_accounts")):
            to_wake.append(uid)

    if to_wake:
        with _live_sync_cond:
            _live_sync_pending_uids.update(to_wake)
            _live_sync_cond.notify_all()


# ----------------- معالجات الأوامر والقوائم -----------------

@bot.message_handler(commands=['start', 'menu', 'cancel'])
def cmd_start(message: types.Message):
    uid = message.from_user.id
    full_name = f"{message.from_user.first_name or ''} {message.from_user.last_name or ''}".strip() or f"مستخدم_{uid}"
    username = message.from_user.username or ""
    raw_parts = (message.text or "").strip().split(maxsplit=1)
    if len(raw_parts) > 1 and raw_parts[1].strip():
        payload = raw_parts[1].strip()
        u_data, _ = register_or_update_user(uid, full_name, username)
        if not is_super_admin(uid) and u_data.get("status") != "banned":
            if payload.lower().startswith("ref_") or looks_like_invite_token(payload):
                res = redeem_invite_code(uid, payload, user_name=full_name, username=username)
                if res.get("ok"):
                    rw = int(res.get("referral_reward", 4) or 4)
                    ib = int(res.get("instant_bonus", 0) or 0)
                    safe_send(
                        message.chat.id,
                        "🎉 <b>تم تفعيل دعوتك بنجاح عبر الرابط/الكود!</b>\n"
                        "🔓 تم فتح ميزة <b>إضافة حسابات فيسبوك</b> لك فقط (مع نظام النقاط والتسوية المالية).\n"
                        f"🤝 {('حصل من دعاك على مكافأة +' + str(ib) + ' نقاط فوراً!' if ib > 0 else 'تُحسب مكافأة الإحالة للداعي (+' + str(rw) + ' نقاط) تلقائياً عند تفعيل أول حساب نشط تضيفه.')}"
                    )
                    if res.get("inviter_id"):
                        safe_send(
                            res["inviter_id"],
                            f"🤝 <b>انضمام جديد عبر دعوتك!</b>\n👤 {esc(full_name)} (<code>{uid}</code>)"
                            + (f"\n🪙 تم إضافة <b>+{ib}</b> نقاط لرصيدك!" if ib > 0 else f"\n⏳ ستضاف مكافأة (+{rw} نقاط) فور تفعيل أول حساب نشط يضيفه.")
                        )
                elif res.get("error"):
                    safe_send(message.chat.id, f"⚠️ <b>ملاحظة حول كود الدعوة:</b> {esc(res['error'])}")

    if not check_user_access_gate(message.from_user, message.chat.id):
        update_menu_button_for_user(bot, uid, is_allowed=False)
        return

    update_menu_button_for_user(bot, uid, is_allowed=True)
    st = get_user_state(uid)
    st["input_mode"] = None
    st["temp_acc_data"] = {}
    sent = safe_send(
        message.chat.id,
        get_dashboard_text(uid),
        reply_markup=get_main_dashboard_markup(uid)
    )
    if sent and hasattr(sent, "message_id"):
        _track_view(uid, message.chat.id, sent.message_id, "main")


@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call: types.CallbackQuery):
    user_id = call.from_user.id
    data = call.data or ""

    if data == "noop":
        safe_answer(call.id)
        return

    if data == "enter_invite_code":
        u_data, _ = register_or_update_user(
            user_id,
            f"{call.from_user.first_name or ''} {call.from_user.last_name or ''}".strip() or f"مستخدم_{user_id}",
            call.from_user.username or ""
        )
        if u_data.get("status") == "banned":
            safe_answer(call.id, "⛔ حسابك محظور من استخدام البوت.", show_alert=True)
            return
        st = get_user_state(user_id)
        st["input_mode"] = "waiting_invite_code"
        safe_answer(call.id)
        safe_send(
            call.message.chat.id,
            "🎟️ <b>أرسل كود الدعوة / التفعيل الآن</b> (مثال: <code>FB-XXXX-XXXX</code>):",
            reply_markup=_prompt_back_markup("back_to_main")
        )
        return

    if data.startswith("cancel_to:"):
        dest = data.split(":", 1)[1].strip()
        allowed_dests = {
            "back_to_main", "menu_wizard_react", "menu_wizard_comment", "menu_cmt_interact",
            "menu_manage_accs", "menu_wallet", "menu_referral", "menu_support",
            "menu_admin_economy", "menu_surveillance_radar"
        }
        if dest not in allowed_dests:
            dest = "back_to_main"
        st = get_user_state(user_id)
        st["input_mode"] = None
        st["temp_acc_data"] = {}
        safe_answer(call.id, "تم الإلغاء والرجوع")
        call.data = dest
        handle_callbacks(call)
        return

    # 1. بوابة موافقة / حظر المطور الأكبر (حصرياً لـ SUPER_ADMIN_ID)
    if data.startswith("gate_app_"):
        if not is_super_admin(user_id):
            record_audit_log(user_id, call.from_user.first_name or "", "SECURITY_BLOCK", f"محاولة غير مصرحة لتنفيذ {data}")
            safe_answer(call.id, "⛔ خاص بالمطور الأكبر فقط.", show_alert=True)
            return
        try:
            target_uid = int(data.replace("gate_app_", ""))
        except ValueError:
            return
        if is_super_admin(target_uid):
            safe_answer(call.id, "👑 المطور الأكبر معتمد تلقائياً دوماً.")
            return
        approve_user(target_uid)
        update_menu_button_for_user(bot, target_uid, is_allowed=True)
        safe_answer(call.id, "✅ تم قبول المستخدم! كافة الأدوات مغلقة حتى تفتحها له بنفسك.", show_alert=True)
        m = types.InlineKeyboardMarkup(row_width=1)
        m.add(
            types.InlineKeyboardButton("⚙️ تخصيص صلاحيات هذا المستخدم الآن", callback_data=f"surv_user_{target_uid}"),
            types.InlineKeyboardButton("🛰️ فتح رادار المراقبة", callback_data="menu_surveillance_radar")
        )
        safe_edit_message(
            f"✅ <b>تم اعتماد المستخدم (<code>{target_uid}</code>) بنجاح!</b>\n"
            "🔒 <i>ملاحظة أمنية: كافة الأدوات والصلاحيات لا تزال مغلقة عنه حتى تفتح له الميزات التي تريدها من بطاقته:</i>",
            call.message.chat.id, call.message.message_id, reply_markup=m
        )
        safe_send(
            target_uid,
            "🎉 <b>تمت الموافقة المبدئية على حسابك من قبل المطور الرئيسي.</b>\n"
            "🔒 بانتظار قيام المطور بتحديد الميزات المسموحة لك. أرسل /start لعرض لوحتك."
        )
        return

    elif data.startswith("gate_ban_"):
        if not is_super_admin(user_id):
            record_audit_log(user_id, call.from_user.first_name or "", "SECURITY_BLOCK", f"محاولة غير مصرحة لتنفيذ {data}")
            safe_answer(call.id, "⛔ خاص بالمطور الأكبر فقط.", show_alert=True)
            return
        try:
            target_uid = int(data.replace("gate_ban_", ""))
        except ValueError:
            return
        if is_super_admin(target_uid):
            safe_answer(call.id, "🛡️ محظور برمجياً: لا يمكن حظر المطور الأكبر أبداً!", show_alert=True)
            return
        ban_user(target_uid)
        update_menu_button_for_user(bot, target_uid, is_allowed=False)
        safe_answer(call.id, "🚫 تم حظر المستخدم نهائياً وتصفير صلاحياته!", show_alert=True)
        safe_edit_message(
            f"🚫 <b>تم حظر المستخدم (<code>{target_uid}</code>) ومنعه نهائياً.</b>",
            call.message.chat.id, call.message.message_id,
            reply_markup=_back_home_markup("menu_surveillance_radar")
        )
        return

    # 2. التحقق الصارم من صلاحية الوصول العامة
    if not check_user_access_gate(call.from_user, call.message.chat.id, notify_blocked=False):
        safe_answer(call.id, "⛔ غير مصرح لك باستخدام البوت أو حسابك محظور/معلق.", show_alert=True)
        return

    st = get_user_state(user_id)

    # ----------------- رادار المراقبة الشامل وسجل الرقابة للمطور الأكبر فقط -----------------
    if data == "menu_surveillance_radar":
        if not is_super_admin(user_id):
            record_audit_log(user_id, call.from_user.first_name or "", "SECURITY_BLOCK", "محاولة فتح رادار المطور")
            safe_answer(call.id, "⛔ خاص بالمطور الأكبر فقط.", show_alert=True)
            return
        txt, markup = render_surveillance_radar_text_and_markup()
        _track_view(user_id, call.message.chat.id, call.message.message_id, "radar")
        safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=markup)
        return

    elif data == "menu_audit_logs":
        if not is_super_admin(user_id):
            record_audit_log(user_id, call.from_user.first_name or "", "SECURITY_BLOCK", "محاولة فتح سجل الرقابة")
            safe_answer(call.id, "⛔ خاص بالمطور الأكبر فقط.", show_alert=True)
            return
        txt, markup = _render_audit_logs_view()
        _track_view(user_id, call.message.chat.id, call.message.message_id, "audit")
        safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=markup)
        return

    elif data.startswith("surv_user_"):
        if not is_super_admin(user_id):
            record_audit_log(user_id, call.from_user.first_name or "", "SECURITY_BLOCK", f"محاولة وصول {data}")
            safe_answer(call.id, "⛔ خاص بالمطور الأكبر فقط.", show_alert=True)
            return
        try:
            t_id = int(data.replace("surv_user_", ""))
        except ValueError:
            return
        txt, markup = render_user_dossier(t_id)
        if not txt:
            safe_answer(call.id, "المستخدم غير موجود أو هو المطور الرئيسي.", show_alert=True)
            return
        _track_view(user_id, call.message.chat.id, call.message.message_id, "dossier", target_id=t_id)
        safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=markup)
        return

    elif data.startswith("surv_perm_"):
        if not is_super_admin(user_id):
            record_audit_log(user_id, call.from_user.first_name or "", "SECURITY_BLOCK", f"محاولة تعديل صلاحية {data}")
            safe_answer(call.id, "⛔ خاص بالمطور الأكبر فقط.", show_alert=True)
            return
        parts = data.split("_")
        try:
            t_id = int(parts[2])
        except (IndexError, ValueError):
            return
        if is_super_admin(t_id):
            safe_answer(call.id, "🛡️ صلاحيات المطور الأكبر مطلقة ولا تعدّل.", show_alert=True)
            return
        perm_key = "_".join(parts[3:])
        new_val = toggle_user_permission(t_id, perm_key)
        perm_ar = PERMISSION_LABELS.get(perm_key, perm_key)
        safe_answer(call.id, f"{'✅ تم تفعيل' if new_val else '❌ تم إغلاق'}: {perm_ar}")
        txt, markup = render_user_dossier(t_id)
        if txt:
            safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=markup)
        return

    elif data.startswith("surv_revoke_all_"):
        if not is_super_admin(user_id):
            return
        try:
            t_id = int(data.replace("surv_revoke_all_", ""))
        except ValueError:
            return
        revoke_all_permissions(t_id)
        safe_answer(call.id, "🔒 تم سحب وإغلاق كافة الصلاحيات عن هذا المستخدم!", show_alert=True)
        txt, markup = render_user_dossier(t_id)
        if txt:
            safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=markup)
        return

    elif data.startswith("surv_ban_"):
        if not is_super_admin(user_id):
            return
        try:
            t_id = int(data.replace("surv_ban_", ""))
        except ValueError:
            return
        if is_super_admin(t_id):
            safe_answer(call.id, "🛡️ محظور برمجياً: لا يمكن حظر المطور الأكبر!", show_alert=True)
            return
        ban_user(t_id)
        update_menu_button_for_user(bot, t_id, is_allowed=False)
        safe_answer(call.id, "🚫 تم حظر المستخدم وتصفير صلاحياته!", show_alert=True)
        txt, markup = render_user_dossier(t_id)
        if txt:
            safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=markup)
        return

    elif data.startswith("surv_unban_"):
        if not is_super_admin(user_id):
            return
        try:
            t_id = int(data.replace("surv_unban_", ""))
        except ValueError:
            return
        unban_user(t_id)
        update_menu_button_for_user(bot, t_id, is_allowed=True)
        safe_answer(call.id, "✅ تم فك الحظر (كافة الصلاحيات مغلقة للأمان)!", show_alert=True)
        txt, markup = render_user_dossier(t_id)
        if txt:
            safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=markup)
        return

    elif data.startswith("surv_del_"):
        if not is_super_admin(user_id):
            return
        try:
            t_id = int(data.replace("surv_del_", ""))
        except ValueError:
            return
        if is_super_admin(t_id):
            safe_answer(call.id, "🛡️ محظور برمجياً: لا يمكن حذف المطور الأكبر!", show_alert=True)
            return
        acc_deleted = delete_accounts_by_owner(t_id)
        delete_user_and_data(t_id)
        update_menu_button_for_user(bot, t_id, is_allowed=False)
        safe_answer(call.id, f"🗑️ تم حذف المستخدم ومسح {acc_deleted} حساب تابعة له!", show_alert=True)
        txt, markup = render_surveillance_radar_text_and_markup()
        safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=markup)
        return

    elif data.startswith("surv_pts_"):
        if not is_super_admin(user_id):
            record_audit_log(user_id, call.from_user.first_name or "", "SECURITY_BLOCK", f"محاولة تعديل نقاط {data}")
            safe_answer(call.id, "⛔ خاص بالمطور الأكبر فقط.", show_alert=True)
            return
        rest = data[len("surv_pts_"):]
        action_k, _, uid_s = rest.partition("_")
        try:
            t_id = int(uid_s)
        except ValueError:
            return
        if action_k == "add5":
            res = adjust_user_points(t_id, 5, "ADMIN_GRANT", "إضافة +5 نقاط من لوحة المطور", actor_uid=user_id)
            safe_answer(call.id, f"✅ تم إضافة +5 نقاط! الرصيد: {res.get('balance', 0)}")
            safe_send(t_id, f"🎁 <b>منحة نقاط من المطور الرئيسي:</b> +5 نقاط!\n💰 رصيدك الآن: <b>{res.get('balance', 0)}</b> نقطة ({res.get('yer_value', 0):,} ر.ي)")
        elif action_k == "sub5":
            res = adjust_user_points(t_id, -5, "ADMIN_DEDUCT", "سحب/خصم 5 نقاط من المطور", actor_uid=user_id, allow_partial_zero=True)
            safe_answer(call.id, f"✅ تم خصم النقاط! الرصيد: {res.get('balance', 0)}")
            safe_send(t_id, f"➖ <b>تحديث الرصيد من المطور:</b> تم خصم/سحب {abs(res.get('delta', 0))} نقطة.\n💰 رصيدك الآن: <b>{res.get('balance', 0)}</b> نقطة")
        elif action_k == "settle":
            res = settle_payout(t_id, None, actor_uid=user_id, note="تسوية شاملة من بطاقة المستخدم")
            if res.get("ok"):
                safe_answer(call.id, f"💸 تم تسوية {res['points_settled']} نقطة ({res['yer_paid']:,} ر.ي)!", show_alert=True)
                safe_send(
                    t_id,
                    f"💸 <b>إشعار محاسبة رسمي | تم اعتماد الدفع وتسوية النقاط!</b>\n"
                    f"🪙 النقاط المُسلّمة: <b>{res['points_settled']}</b> نقطة\n"
                    f"💵 المبلغ: <b>{res['yer_paid']:,} ريال يمني</b>\n"
                    f"💰 رصيدك المتبقي: <b>{res['remaining_points']}</b> نقطة"
                )
            else:
                safe_answer(call.id, f"⚠️ {res.get('error', 'لا توجد نقاط للتسوية')}", show_alert=True)
                return
        elif action_k == "custom":
            st["input_mode"] = f"waiting_admin_pts_{t_id}"
            safe_answer(call.id)
            safe_send(
                call.message.chat.id,
                f"✏️ <b>تعديل نقاط المستخدم (<code>{t_id}</code>) يدوياً:</b>\n"
                "أرسل رقماً موجباً للإضافة (مثال: <code>25</code>) أو سالباً للخصم/السحب (مثال: <code>-10</code>):",
                reply_markup=_prompt_back_markup("menu_surveillance_radar")
            )
            return
        txt, markup = render_user_dossier(t_id)
        if txt:
            safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=markup)
        return

    elif data == "menu_admin_economy":
        if not is_super_admin(user_id):
            record_audit_log(user_id, call.from_user.first_name or "", "SECURITY_BLOCK", "محاولة فتح إعدادات الاقتصاد بدون صلاحية")
            safe_answer(call.id, "⛔ خاص بالمطور الأكبر فقط.", show_alert=True)
            return
        txt, markup = _render_admin_economy_view()
        _track_view(user_id, call.message.chat.id, call.message.message_id, "economy")
        safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=markup)
        return

    elif data.startswith("eco_tog_"):
        if not is_super_admin(user_id):
            record_audit_log(user_id, call.from_user.first_name or "", "SECURITY_BLOCK", f"محاولة تبديل إعداد اقتصادي {data}")
            safe_answer(call.id, "⛔ خاص بالمطور الأكبر فقط.", show_alert=True)
            return
        field = data[len("eco_tog_"):]
        cfg = load_economy_settings()
        if field == "referral_trigger":
            new_trig = "instant" if cfg.get("referral_trigger") != "instant" else "first_active"
            update_economy_settings({"referral_trigger": new_trig}, actor_uid=user_id)
        elif field in ("public_mode", "enforce_points_on_actions", "suppliers_can_invite", "invited_suppliers_can_invite"):
            update_economy_settings({field: not bool(cfg.get(field))}, actor_uid=user_id)
        else:
            safe_answer(call.id, "إعداد غير معروف.")
            return
        safe_answer(call.id, "✅ تم تحديث سياسة النظام الفيزيائية فوراً!")
        txt, markup = _render_admin_economy_view()
        safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=markup)
        return

    elif data.startswith("eco_set_"):
        if not is_super_admin(user_id):
            record_audit_log(user_id, call.from_user.first_name or "", "SECURITY_BLOCK", f"محاولة تعديل تسعيرة {data}")
            safe_answer(call.id, "⛔ خاص بالمطور الأكبر فقط.", show_alert=True)
            return
        key = data[len("eco_set_"):]
        valid_keys = {"yer_per_point", "active_account_reward", "referral_reward"} | set(OP_COST_LABELS_AR.keys())
        if key not in valid_keys:
            safe_answer(call.id, "بند غير معروف.")
            return
        st["input_mode"] = f"waiting_eco_rate_{key}"
        safe_answer(call.id)
        safe_send(
            call.message.chat.id,
            f"🔢 <b>أرسل القيمة الرقمية الجديدة لبند (<code>{esc(key)}</code>):</b>",
            reply_markup=_prompt_back_markup("menu_admin_economy")
        )
        return

    # ----------------- المحفظة والإحالات والدعم والمحاسبة -----------------
    elif data == "menu_wallet":
        txt, markup = _render_wallet_view(user_id)
        _track_view(user_id, call.message.chat.id, call.message.message_id, "wallet")
        safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=markup)
        return

    elif data == "menu_referral":
        if not can_user_invite(user_id):
            safe_answer(call.id, "⛔ ميزة روابط وأكواد الإحالة غير مفعلة لحسابك حالياً.", show_alert=True)
            return
        txt, markup = _render_referral_view(user_id)
        _track_view(user_id, call.message.chat.id, call.message.message_id, "referral")
        safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=markup)
        return

    elif data == "ref_gen_code":
        if not can_user_invite(user_id):
            safe_answer(call.id, "⛔ ميزة الإحالة غير مفعلة لحسابك.", show_alert=True)
            return
        res = create_invite_code(user_id, max_uses=1, label="كود تفعيل")
        if not res.get("ok"):
            safe_answer(call.id, f"⚠️ {res.get('error', 'تعذر التوليد')}", show_alert=True)
            return
        safe_answer(call.id, f"🎟️ تم توليد الكود: {res['invite']['code']}", show_alert=True)
        txt, markup = _render_referral_view(user_id)
        safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=markup)
        return

    elif data.startswith("ref_rev_"):
        if not can_user_invite(user_id):
            safe_answer(call.id, "⛔ غير مصرح لك بهذا الإجراء.", show_alert=True)
            return
        raw_c = data[len("ref_rev_"):].replace("_", "-")
        if revoke_invite_code(user_id, raw_c, is_dev=is_super_admin(user_id)):
            safe_answer(call.id, f"✅ تم إبطال الكود {raw_c}")
        else:
            safe_answer(call.id, "⚠️ تعذر إبطال الكود أو لا تملكه.", show_alert=True)
        txt, markup = _render_referral_view(user_id)
        safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=markup)
        return

    elif data == "menu_support":
        txt, markup = _render_support_view(user_id)
        _track_view(user_id, call.message.chat.id, call.message.message_id, "support")
        safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=markup)
        return

    elif data == "sup_sell_start":
        snap = build_user_settlement_snapshot(user_id)
        st["input_mode"] = "waiting_sell_msg"
        safe_answer(call.id)
        safe_send(
            call.message.chat.id,
            "💵 <b>تأكيد اتفاقية بيع الحسابات للمطور</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"🟢 <b>حساباتك النشطة حالياً:</b> {snap['active_added']} | 💰 <b>رصيدك:</b> {snap['points']} نقطة ({snap['yer_value']:,} ر.ي)\n\n"
            "✍️ <b>اكتب الآن رسالتك وتفاصيل استلام المبلغ (مثل رقم المحفظة/الهاتف) واضغط إرسال:</b>\n"
            "<i>سيصل للمطور تقريرك الرقمي الكامل تلقائياً مع إمكانية الرد المباشر عليك.</i>",
            reply_markup=_prompt_back_markup("menu_support")
        )
        return

    elif data == "sup_msg_start":
        st["input_mode"] = "waiting_sup_msg"
        safe_answer(call.id)
        safe_send(
            call.message.chat.id,
            "💬 <b>أرسل رسالتك أو استفسارك الآن لتصل مباشرة إلى المطور الرئيسي:</b>",
            reply_markup=_prompt_back_markup("menu_support")
        )
        return

    elif data.startswith("sup_view_"):
        tid = data[len("sup_view_"):]
        t = get_ticket_by_id(tid)
        if not t or (not is_super_admin(user_id) and int(t.get("user_id", 0)) != user_id):
            record_audit_log(user_id, call.from_user.first_name or "", "SECURITY_BLOCK", f"محاولة عرض تذكرة غير مصرحة {tid}")
            safe_answer(call.id, "⛔ غير مصرح لك بعرض هذه التذكرة.", show_alert=True)
            return
        txt, markup = _render_ticket_detail_view(user_id, tid)
        _track_view(user_id, call.message.chat.id, call.message.message_id, "ticket", ticket_id=tid)
        safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=markup)
        return

    elif data.startswith("tkt_reply_"):
        if not is_super_admin(user_id):
            record_audit_log(user_id, call.from_user.first_name or "", "SECURITY_BLOCK", f"محاولة رد مطور مزيف {data}")
            safe_answer(call.id, "⛔ خاص بالمطور الأكبر فقط.", show_alert=True)
            return
        tid = data[len("tkt_reply_"):]
        st["input_mode"] = f"waiting_tkt_reply_{tid}"
        safe_answer(call.id)
        safe_send(
            call.message.chat.id,
            f"↩️ <b>اكتب ردك الآن على التذكرة <code>#{esc(tid)}</code>:</b>\n"
            "<i>مثال: طيب أرسل رقم حسابك/محفظتك لأودع لك المبلغ المتفق عليه...</i>",
            reply_markup=_prompt_back_markup("menu_support")
        )
        return

    elif data.startswith("user_reply_tkt_"):
        tid = data[len("user_reply_tkt_"):]
        t = get_ticket_by_id(tid)
        if not t or (not is_super_admin(user_id) and int(t.get("user_id", 0)) != user_id):
            record_audit_log(user_id, call.from_user.first_name or "", "SECURITY_BLOCK", f"محاولة رد على تذكرة لا تخصه {tid}")
            safe_answer(call.id, "⛔ غير مصرح لك بالرد على هذه التذكرة.", show_alert=True)
            return
        st["input_mode"] = f"waiting_user_tkt_reply_{tid}"
        safe_answer(call.id)
        safe_send(
            call.message.chat.id,
            f"↩️ <b>أرسل ردك الآن للمطور على التذكرة <code>#{esc(tid)}</code></b> (مثل رقم المحفظة أو الاستفسار):",
            reply_markup=_prompt_back_markup("menu_support")
        )
        return

    elif data.startswith("tkt_settle_"):
        if not is_super_admin(user_id):
            record_audit_log(user_id, call.from_user.first_name or "", "SECURITY_BLOCK", f"محاولة تسوية مالية مزيفة {data}")
            safe_answer(call.id, "⛔ خاص بالمطور الأكبر فقط.", show_alert=True)
            return
        tid = data[len("tkt_settle_"):]
        t = get_ticket_by_id(tid)
        if not t:
            safe_answer(call.id, "التذكرة غير موجودة.", show_alert=True)
            return
        target_uid = int(t.get("user_id", 0))
        res = settle_payout(target_uid, None, actor_uid=user_id, ticket_id=tid)
        if res.get("ok"):
            safe_answer(call.id, f"💸 تم اعتماد تسوية {res['points_settled']} نقطة ({res['yer_paid']:,} ر.ي)!", show_alert=True)
            user_m = types.InlineKeyboardMarkup()
            user_m.add(types.InlineKeyboardButton("📬 فتح التذكرة", callback_data=f"sup_view_{tid}"))
            safe_send(
                target_uid,
                f"✅ <b>تم اعتماد المحاسبة وتسوية حسابك للتذكرة <code>#{esc(tid)}</code>!</b>\n"
                f"🪙 النقاط المُسلّمة: <b>{res['points_settled']}</b> نقطة\n"
                f"💵 المبلغ المعتمد: <b>{res['yer_paid']:,} ريال يمني</b>\n"
                f"💰 رصيدك المتبقي: <b>{res['remaining_points']}</b> نقطة",
                reply_markup=user_m
            )
            txt, markup = _render_ticket_detail_view(user_id, tid)
            safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=markup)
        else:
            safe_answer(call.id, f"⚠️ {res.get('error', 'لا توجد نقاط موجبة للتسوية.')}", show_alert=True)
        return

    # ----------------- معالجات الميزات المحمية بالصلاحيات الفردية -----------------

    # A) التفاعلات (can_react)
    elif data == "menu_wizard_react":
        if not require_perm_or_deny(call, "can_react", "⛔ صلاحية التفاعلات والإعجاب غير مفعلة لحسابك."):
            return
        markup = types.InlineKeyboardMarkup(row_width=3)
        markup.row(
            types.InlineKeyboardButton("👍 Like", callback_data="set_react_like"),
            types.InlineKeyboardButton("❤️ Love", callback_data="set_react_love"),
            types.InlineKeyboardButton("🤗 Care", callback_data="set_react_care")
        )
        markup.row(
            types.InlineKeyboardButton("😂 Haha", callback_data="set_react_haha"),
            types.InlineKeyboardButton("😮 Wow", callback_data="set_react_wow"),
            types.InlineKeyboardButton("😢 Sad", callback_data="set_react_sad")
        )
        markup.row(
            types.InlineKeyboardButton("😡 Angry", callback_data="set_react_angry"),
            types.InlineKeyboardButton("👎 إلغاء الإعجاب", callback_data="set_react_unlike")
        )
        markup.row(
            types.InlineKeyboardButton("🥇 الأول", callback_data="set_react_post_1"),
            types.InlineKeyboardButton("🥈 الثاني", callback_data="set_react_post_2"),
            types.InlineKeyboardButton("🥉 الثالث", callback_data="set_react_post_3")
        )
        markup.row(
            types.InlineKeyboardButton("🔢 رقم منشور مخصص", callback_data="set_react_post_custom"),
            types.InlineKeyboardButton("🔗 رابط منشور مباشر", callback_data="set_react_post_url")
        )
        markup.row(
            types.InlineKeyboardButton("🔥 جميع الحسابات", callback_data="set_react_acc_0"),
            types.InlineKeyboardButton("1️⃣ حساب 1", callback_data="set_react_acc_1"),
            types.InlineKeyboardButton("2️⃣ حسابين", callback_data="set_react_acc_2"),
            types.InlineKeyboardButton("3️⃣ ثلاث", callback_data="set_react_acc_3")
        )
        markup.row(
            types.InlineKeyboardButton(f"الحالة: [{'مفعل ✅' if st['like'] else 'معطل ❌'}]", callback_data="toggle_react_active")
        )
        markup.row(types.InlineKeyboardButton("🔙 العودة للوحة التحكم", callback_data="back_to_main"))

        curr_react = REACTION_ICONS.get(st["reaction_type"], "👍 إعجاب")
        p_desc = f"منشور رقم {st['react_post_index']}" if not st.get("react_post_url") else f"رابط مباشر ({esc(st['react_post_url'][:28])}...)"
        acc_lim = "جميع الحسابات" if st.get("react_acc_count", 0) == 0 else f"{st['react_acc_count']} حسابات"
        safe_edit_message(
            f"💖 <b>معالج التفاعلات والإعجابات:</b>\n\n"
            f"• <b>التفاعل:</b> {curr_react}\n"
            f"• <b>الهدف:</b> {p_desc}\n"
            f"• <b>عدد الحسابات:</b> {acc_lim}\n"
            f"• <b>الحالة:</b> {'مفعل ✅' if st['like'] else 'معطل ❌'}",
            call.message.chat.id, call.message.message_id, reply_markup=markup
        )

    elif data.startswith("set_react_acc_"):
        if not require_perm_or_deny(call, "can_react", "⛔ صلاحية التفاعلات غير مفعلة لحسابك."):
            return
        try:
            st["react_acc_count"] = int(data.replace("set_react_acc_", ""))
        except ValueError:
            return
        safe_answer(call.id, f"عدد حسابات التفاعل: {'الكل' if st['react_acc_count'] == 0 else st['react_acc_count']}")
        call.data = "menu_wizard_react"
        handle_callbacks(call)

    elif data.startswith("set_react_post_"):
        if not require_perm_or_deny(call, "can_react", "⛔ صلاحية التفاعلات غير مفعلة لحسابك."):
            return
        val = data.replace("set_react_post_", "")
        if val == "custom":
            st["input_mode"] = "waiting_react_post_num"
            safe_send(
                call.message.chat.id,
                "🔢 <b>أرسل الآن رقم المنشور المستهدف للتفاعل:</b>",
                reply_markup=_prompt_back_markup("menu_wizard_react")
            )
        elif val == "url":
            st["input_mode"] = "waiting_react_post_url"
            safe_send(
                call.message.chat.id,
                "🔗 <b>أرسل رابط المنشور المباشر للتفاعل عليه:</b>",
                reply_markup=_prompt_back_markup("menu_wizard_react")
            )
        else:
            try:
                st["react_post_index"] = int(val)
                st["react_post_url"] = ""
            except ValueError:
                return
            safe_answer(call.id, f"تم تحديد المنشور رقم {val}")
            call.data = "menu_wizard_react"
            handle_callbacks(call)

    elif data.startswith("set_react_"):
        if not require_perm_or_deny(call, "can_react", "⛔ صلاحية التفاعلات غير مفعلة لحسابك."):
            return
        r_type = data.replace("set_react_", "")
        if r_type not in REACTION_ICONS:
            return
        st["reaction_type"] = r_type
        st["like"] = True
        safe_answer(call.id, f"تم اختيار: {REACTION_ICONS.get(r_type, r_type)}")
        call.data = "menu_wizard_react"
        handle_callbacks(call)

    elif data == "toggle_react_active":
        if not require_perm_or_deny(call, "can_react", "⛔ صلاحية التفاعلات غير مفعلة لحسابك."):
            return
        st["like"] = not st["like"]
        safe_answer(call.id, f"التفاعل: {'مفعل ✅' if st['like'] else 'معطل ❌'}")
        call.data = "menu_wizard_react"
        handle_callbacks(call)

    # B) التعليقات (can_comment)
    elif data == "menu_wizard_comment":
        if not require_perm_or_deny(call, "can_comment", "⛔ صلاحية كتابة التعليقات غير مفعلة لحسابك."):
            return
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.row(types.InlineKeyboardButton("✏️ كتابة/تعديل نص التعليق", callback_data="edit_comment_text"))
        markup.row(
            types.InlineKeyboardButton("🥇 الأول", callback_data="set_cmt_post_1"),
            types.InlineKeyboardButton("🥈 الثاني", callback_data="set_cmt_post_2"),
            types.InlineKeyboardButton("🥉 الثالث", callback_data="set_cmt_post_3")
        )
        markup.row(
            types.InlineKeyboardButton("🔢 رقم مخصص", callback_data="set_cmt_post_custom"),
            types.InlineKeyboardButton("🔗 رابط منشور مباشر", callback_data="set_cmt_post_url")
        )
        markup.row(
            types.InlineKeyboardButton("🔥 جميع الحسابات", callback_data="set_cmt_acc_0"),
            types.InlineKeyboardButton("1️⃣ حساب 1", callback_data="set_cmt_acc_1"),
            types.InlineKeyboardButton("2️⃣ حسابين", callback_data="set_cmt_acc_2"),
            types.InlineKeyboardButton("3️⃣ ثلاث", callback_data="set_cmt_acc_3")
        )
        markup.row(
            types.InlineKeyboardButton(f"الحالة: [{'مفعل ✅' if st['comment'] else 'معطل ❌'}]", callback_data="toggle_comment_active")
        )
        markup.row(types.InlineKeyboardButton("🔙 العودة للوحة التحكم", callback_data="back_to_main"))

        post_desc = f"منشور رقم {st['comment_post_index']}" if not st["comment_post_url"] else f"رابط مباشر ({esc(st['comment_post_url'][:28])}...)"
        acc_desc = "جميع الحسابات" if st["comment_acc_count"] == 0 else f"{st['comment_acc_count']} حسابات"
        safe_edit_message(
            f"💬 <b>معالج التعليقات واصطياد المنشورات:</b>\n\n"
            f"📝 <b>نص التعليق:</b> <i>'{esc(st['comment_text'])}'</i>\n"
            f"🎯 <b>المنشور المستهدف:</b> {post_desc}\n"
            f"👥 <b>عدد الحسابات:</b> {acc_desc}\n"
            f"🔘 <b>الحالة:</b> {'مفعل ✅' if st['comment'] else 'معطل ❌'}",
            call.message.chat.id, call.message.message_id, reply_markup=markup
        )

    elif data == "edit_comment_text":
        if not require_perm_or_deny(call, "can_comment", "⛔ صلاحية التعليقات غير مفعلة لحسابك."):
            return
        st["input_mode"] = "waiting_comment_text"
        safe_send(
            call.message.chat.id,
            "💬 <b>أرسل الآن نص التعليق الجديد الذي ترغب بنشره:</b>",
            reply_markup=_prompt_back_markup("menu_wizard_comment")
        )

    elif data.startswith("set_cmt_post_"):
        if not require_perm_or_deny(call, "can_comment", "⛔ صلاحية التعليقات غير مفعلة لحسابك."):
            return
        val = data.replace("set_cmt_post_", "")
        if val == "custom":
            st["input_mode"] = "waiting_cmt_post_num"
            safe_send(
                call.message.chat.id,
                "🔢 <b>أرسل الآن رقم المنشور المطلوب التعليق عليه:</b>",
                reply_markup=_prompt_back_markup("menu_wizard_comment")
            )
        elif val == "url":
            st["input_mode"] = "waiting_cmt_post_url"
            safe_send(
                call.message.chat.id,
                "🔗 <b>أرسل رابط المنشور المباشر للتعليق عليه:</b>",
                reply_markup=_prompt_back_markup("menu_wizard_comment")
            )
        else:
            try:
                st["comment_post_index"] = int(val)
                st["comment_post_url"] = ""
            except ValueError:
                return
            safe_answer(call.id, f"تم تحديد المنشور رقم {val}")
            call.data = "menu_wizard_comment"
            handle_callbacks(call)

    elif data.startswith("set_cmt_acc_"):
        if not require_perm_or_deny(call, "can_comment", "⛔ صلاحية التعليقات غير مفعلة لحسابك."):
            return
        try:
            val = int(data.replace("set_cmt_acc_", ""))
        except ValueError:
            return
        st["comment_acc_count"] = val
        safe_answer(call.id, f"عدد الحسابات: {'الكل' if val == 0 else val}")
        call.data = "menu_wizard_comment"
        handle_callbacks(call)

    elif data == "toggle_comment_active":
        if not require_perm_or_deny(call, "can_comment", "⛔ صلاحية التعليقات غير مفعلة لحسابك."):
            return
        st["comment"] = not st["comment"]
        safe_answer(call.id, f"التعليق: {'مفعل ✅' if st['comment'] else 'معطل ❌'}")
        call.data = "menu_wizard_comment"
        handle_callbacks(call)

    # C) الصداقة والمتابعة (can_friend_follow)
    elif data == "toggle_friend":
        if not require_perm_or_deny(call, "can_friend_follow", "⛔ صلاحية الصداقة والمتابعة غير مفعلة لحسابك."):
            return
        st["friend"] = not st["friend"]
        if st["friend"]:
            st["cancel_friend"] = False
        safe_edit_reply_markup(call.message.chat.id, call.message.message_id, get_main_dashboard_markup(user_id))
        safe_answer(call.id, f"طلب الصداقة: {'مفعل ✅' if st['friend'] else 'معطل ❌'}")

    elif data == "toggle_cancel_friend":
        if not require_perm_or_deny(call, "can_friend_follow", "⛔ صلاحية الصداقة والمتابعة غير مفعلة لحسابك."):
            return
        st["cancel_friend"] = not st["cancel_friend"]
        if st["cancel_friend"]:
            st["friend"] = False
        safe_edit_reply_markup(call.message.chat.id, call.message.message_id, get_main_dashboard_markup(user_id))
        safe_answer(call.id, f"إلغاء طلب الصداقة: {'مفعل ✅' if st['cancel_friend'] else 'معطل ❌'}")

    elif data == "toggle_follow":
        if not require_perm_or_deny(call, "can_friend_follow", "⛔ صلاحية الصداقة والمتابعة غير مفعلة لحسابك."):
            return
        st["follow"] = not st["follow"]
        if st["follow"]:
            st["unfollow"] = False
        safe_edit_reply_markup(call.message.chat.id, call.message.message_id, get_main_dashboard_markup(user_id))
        safe_answer(call.id, f"المتابعة: {'مفعل ✅' if st['follow'] else 'معطل ❌'}")

    elif data == "toggle_unfollow":
        if not require_perm_or_deny(call, "can_friend_follow", "⛔ صلاحية الصداقة والمتابعة غير مفعلة لحسابك."):
            return
        st["unfollow"] = not st["unfollow"]
        if st["unfollow"]:
            st["follow"] = False
        safe_edit_reply_markup(call.message.chat.id, call.message.message_id, get_main_dashboard_markup(user_id))
        safe_answer(call.id, f"إلغاء المتابعة: {'مفعل ✅' if st['unfollow'] else 'معطل ❌'}")

    # D) الرسائل الخاصة (can_message)
    elif data == "toggle_message":
        if not require_perm_or_deny(call, "can_message", "⛔ صلاحية الرسائل الخاصة غير مفعلة لحسابك."):
            return
        st["message"] = not st["message"]
        safe_edit_reply_markup(call.message.chat.id, call.message.message_id, get_main_dashboard_markup(user_id))
        safe_answer(call.id, f"الرسائل الخاصة: {'مفعل ✅' if st['message'] else 'معطل ❌'}")

    elif data == "menu_msg_config":
        if not require_perm_or_deny(call, "can_message", "⛔ صلاحية الرسائل الخاصة غير مفعلة لحسابك."):
            return
        st["input_mode"] = "waiting_msg_text"
        safe_send(
            call.message.chat.id,
            f"✉️ <b>النص الحالي للرسالة الخاصة:</b>\n<i>'{esc(st['message_text'])}'</i>\n\n"
            "أرسل الآن النص الجديد للرسالة الخاصة:",
            reply_markup=_prompt_back_markup("back_to_main")
        )

    # E) البلاغات والحظر (can_report)
    elif data == "toggle_rep_post":
        if not require_perm_or_deny(call, "can_report", "⛔ صلاحية البلاغات غير مفعلة لحسابك."):
            return
        st["report_post"] = not st["report_post"]
        if st["report_post"]:
            st["report_profile"] = False
        safe_edit_reply_markup(call.message.chat.id, call.message.message_id, get_main_dashboard_markup(user_id))
        safe_answer(call.id, f"بلاغ المنشور: {'مفعل ✅' if st['report_post'] else 'معطل ❌'}")

    elif data == "toggle_rep_profile":
        if not require_perm_or_deny(call, "can_report", "⛔ صلاحية البلاغات غير مفعلة لحسابك."):
            return
        st["report_profile"] = not st["report_profile"]
        if st["report_profile"]:
            st["report_post"] = False
        safe_edit_reply_markup(call.message.chat.id, call.message.message_id, get_main_dashboard_markup(user_id))
        safe_answer(call.id, f"بلاغ الحساب: {'مفعل ✅' if st['report_profile'] else 'معطل ❌'}")

    elif data == "toggle_block":
        if not require_perm_or_deny(call, "can_report", "⛔ صلاحية الحظر غير مفعلة لحسابك."):
            return
        st["block"] = not st["block"]
        safe_edit_reply_markup(call.message.chat.id, call.message.message_id, get_main_dashboard_markup(user_id))
        safe_answer(call.id, f"حظر الحساب: {'مفعل ✅' if st['block'] else 'معطل ❌'}")

    elif data == "menu_rep_config":
        if not require_perm_or_deny(call, "can_report", "⛔ صلاحية البلاغات غير مفعلة لحسابك."):
            return
        markup = types.InlineKeyboardMarkup(row_width=2)
        for rk, rl in REPORT_REASONS_AR.items():
            mark = "✅ " if st["rep_reason"] == rk else ""
            markup.add(types.InlineKeyboardButton(f"{mark}{rl}", callback_data=f"set_rep_reason_{rk}"))
        markup.row(types.InlineKeyboardButton("👤 --- الطرف المتضرر ---", callback_data="noop"))
        vic_btns = []
        for vk, vl in REPORT_VICTIMS_AR.items():
            mark = "✅ " if st["rep_victim"] == vk else ""
            vic_btns.append(types.InlineKeyboardButton(f"{mark}{vl}", callback_data=f"set_rep_victim_{vk}"))
        markup.row(*vic_btns)
        markup.row(types.InlineKeyboardButton("🔙 حفظ والعودة للرئيسية", callback_data="back_to_main"))
        safe_edit_message(
            "⚙️ <b>تفاصيل معالج البلاغات الرسمي:</b>\n\n"
            f"• <b>السبب المحدد:</b> {REPORT_REASONS_AR.get(st['rep_reason'], st['rep_reason'])}\n"
            f"• <b>الطرف المتضرر:</b> {REPORT_VICTIMS_AR.get(st['rep_victim'], st['rep_victim'])}",
            call.message.chat.id, call.message.message_id, reply_markup=markup
        )

    elif data.startswith("set_rep_reason_"):
        if not require_perm_or_deny(call, "can_report", "⛔ صلاحية البلاغات غير مفعلة لحسابك."):
            return
        rk = data.replace("set_rep_reason_", "")
        if rk in REPORT_REASONS_AR:
            st["rep_reason"] = rk
            safe_answer(call.id, f"تم اختيار السبب: {REPORT_REASONS_AR[rk]}")
        call.data = "menu_rep_config"
        handle_callbacks(call)

    elif data.startswith("set_rep_victim_"):
        if not require_perm_or_deny(call, "can_report", "⛔ صلاحية البلاغات غير مفعلة لحسابك."):
            return
        vk = data.replace("set_rep_victim_", "")
        if vk in REPORT_VICTIMS_AR:
            st["rep_victim"] = vk
            safe_answer(call.id, f"تم تحديد المتضرر: {REPORT_VICTIMS_AR[vk]}")
        call.data = "menu_rep_config"
        handle_callbacks(call)

    # F) التفاعل والرد على تعليق محدد (can_interact_comments)
    elif data == "menu_cmt_interact":
        if not require_perm_or_deny(call, "can_interact_comments", "⛔ صلاحية الرد والتفاعل مع التعليقات غير مفعلة لحسابك."):
            return
        markup = types.InlineKeyboardMarkup(row_width=2)
        int_st = "مفعل ✅" if st["interact_cmt"] else "معطل ❌"
        markup.add(types.InlineKeyboardButton(f"حالة الميزة: [{int_st}]", callback_data="toggle_cmt_int_active"))
        mode_names = {
            "first": "أول تعليق ظاهر",
            "author": f"باسم الكاتب ({st['cmt_target_val']})",
            "keyword": f"بكلمة ({st['cmt_target_val']})",
            "index": f"بالترتيب ({st['cmt_target_val']})"
        }
        markup.add(types.InlineKeyboardButton(f"🎯 الهدف: {mode_names.get(st['cmt_target_mode'], 'أول تعليق')}", callback_data="cycle_cmt_mode"))
        markup.add(types.InlineKeyboardButton("✏️ تعديل اسم/كلمة الهدف", callback_data="edit_cmt_target_val"))
        react_names = {
            "like": "أعجبني 👍", "love": "أحببته ❤️", "care": "أدعمه 🤗",
            "haha": "هاهاها 😂", "wow": "واو 😮", "sad": "أحزنني 😢",
            "angry": "أغضبني 😡", "none": "بدون تفاعل"
        }
        markup.add(types.InlineKeyboardButton(f"💖 التفاعل: {react_names.get(st['cmt_reaction'], 'أعجبني')}", callback_data="cycle_cmt_reaction"))
        markup.add(types.InlineKeyboardButton(f"💬 نص الرد: {st['cmt_reply'][:20]}...", callback_data="edit_cmt_reply_text"))
        markup.add(types.InlineKeyboardButton("🔙 حفظ والعودة للرئيسية", callback_data="back_to_main"))
        safe_edit_message(
            "🎯 <b>إعدادات التفاعل والرد على تعليق محدد:</b>\n"
            "يمكنك استهداف التعليق بالاسم أو بكلمة مفتاحية واختيار الرياكشن ونص الرد.",
            call.message.chat.id, call.message.message_id, reply_markup=markup
        )

    elif data == "toggle_cmt_int_active":
        if not require_perm_or_deny(call, "can_interact_comments", "⛔ صلاحية التفاعل مع التعليقات غير مفعلة."):
            return
        st["interact_cmt"] = not st["interact_cmt"]
        safe_answer(call.id, f"الميزة: {'مفعلة ✅' if st['interact_cmt'] else 'معطلة ❌'}")
        call.data = "menu_cmt_interact"
        handle_callbacks(call)

    elif data == "cycle_cmt_mode":
        if not require_perm_or_deny(call, "can_interact_comments", "⛔ صلاحية التفاعل مع التعليقات غير مفعلة."):
            return
        modes = ["first", "author", "keyword", "index"]
        curr_idx = modes.index(st["cmt_target_mode"]) if st["cmt_target_mode"] in modes else 0
        st["cmt_target_mode"] = modes[(curr_idx + 1) % len(modes)]
        call.data = "menu_cmt_interact"
        handle_callbacks(call)

    elif data == "cycle_cmt_reaction":
        if not require_perm_or_deny(call, "can_interact_comments", "⛔ صلاحية التفاعل مع التعليقات غير مفعلة."):
            return
        reactions = ["like", "love", "care", "haha", "wow", "sad", "angry", "none"]
        curr_idx = reactions.index(st["cmt_reaction"]) if st["cmt_reaction"] in reactions else 0
        st["cmt_reaction"] = reactions[(curr_idx + 1) % len(reactions)]
        call.data = "menu_cmt_interact"
        handle_callbacks(call)

    elif data == "edit_cmt_target_val":
        if not require_perm_or_deny(call, "can_interact_comments", "⛔ صلاحية التفاعل مع التعليقات غير مفعلة."):
            return
        st["input_mode"] = "waiting_cmt_val"
        safe_send(
            call.message.chat.id,
            "✏️ <b>أرسل الآن اسم كاتب التعليق أو الكلمة المفتاحية أو الترتيب:</b>",
            reply_markup=_prompt_back_markup("menu_cmt_interact")
        )

    elif data == "edit_cmt_reply_text":
        if not require_perm_or_deny(call, "can_interact_comments", "⛔ صلاحية التفاعل مع التعليقات غير مفعلة."):
            return
        st["input_mode"] = "waiting_cmt_reply"
        safe_send(
            call.message.chat.id,
            "✏️ <b>أرسل الآن نص الرد على التعليق:</b>",
            reply_markup=_prompt_back_markup("menu_cmt_interact")
        )

    # G) الرابط المستهدف واختيار الحساب المنفذ
    elif data == "menu_set_url":
        if not user_has_any_action_perm(user_id):
            safe_answer(call.id, "⛔ لا توجد أدوات تنفيذ مفعلة لحسابك حالياً.", show_alert=True)
            return
        st["input_mode"] = "waiting_url"
        safe_send(
            call.message.chat.id,
            "🔗 <b>أرسل الآن الرابط المستهدف الجديد (منشور أو حساب فيسبوك):</b>",
            reply_markup=_prompt_back_markup("back_to_main")
        )

    elif data == "menu_select_acc":
        usable = get_usable_accounts_for_user(user_id)
        if not (is_super_admin(user_id) or has_permission(user_id, "can_use_accounts") or (has_permission(user_id, "can_execute") and usable)):
            record_audit_log(user_id, call.from_user.first_name or "", "SECURITY_BLOCK", "محاولة استعراض حسابات التنفيذ دون صلاحية can_use_accounts")
            safe_answer(call.id, "⛔ ليس لديك صلاحية استخدام حسابات البوت.", show_alert=True)
            return

        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(types.InlineKeyboardButton("🚀 (All) تنفيذ بجميع الحسابات المتاحة", callback_data="sel_acc_all"))
        for a in usable:
            st_icon = "🟢" if "نشط" in a.get("status", "") else "🔴"
            # نعرض الاسم فقط بدون كشف البريد الإلكتروني لحماية حسابات المطور
            markup.add(types.InlineKeyboardButton(f"{st_icon} {a['name']}", callback_data=f"sel_acc_{a['id']}"))
        markup.add(types.InlineKeyboardButton("🔙 رجوع للرئيسية", callback_data="back_to_main"))
        safe_edit_message(
            "👤 <b>اختر الحساب المطلوب لتنفيذ العمليات:</b>",
            call.message.chat.id, call.message.message_id, reply_markup=markup
        )

    elif data.startswith("sel_acc_"):
        chosen = data.replace("sel_acc_", "")
        usable = get_usable_accounts_for_user(user_id)
        if not (is_super_admin(user_id) or has_permission(user_id, "can_use_accounts") or (has_permission(user_id, "can_execute") and usable)):
            safe_answer(call.id, "⛔ ليس لديك صلاحية استخدام الحسابات.", show_alert=True)
            return
        if chosen != "all" and not any(a["id"] == chosen for a in usable):
            record_audit_log(user_id, call.from_user.first_name or "", "SECURITY_BLOCK", f"محاولة اختيار حساب غير مصرح {chosen}")
            safe_answer(call.id, "⛔ غير مسموح لك باختيار هذا الحساب!", show_alert=True)
            return
        st["selected_acc"] = chosen
        safe_answer(call.id, "تم تحديد الحساب المنفذ بنجاح!")
        safe_edit_message(get_dashboard_text(user_id), call.message.chat.id, call.message.message_id, reply_markup=get_main_dashboard_markup(user_id))

    # H) إدارة الحسابات (معزولة الملكية: المطور يرى الكل، والمستخدم يرى حساباته المضافة فقط)
    elif data == "menu_manage_accs":
        is_dev = is_super_admin(user_id)
        if not (is_dev or has_permission(user_id, "can_add_accounts") or has_permission(user_id, "can_delete_accounts")):
            record_audit_log(user_id, call.from_user.first_name or "", "SECURITY_BLOCK", "محاولة فتح إدارة الحسابات بدون صلاحية")
            safe_answer(call.id, "⛔ ليس لديك صلاحية إدارة أو إضافة الحسابات.", show_alert=True)
            return

        txt, markup = _render_manage_accs_view(user_id)
        safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=markup)
        _track_view(user_id, call.message.chat.id, call.message.message_id, "manage_accs")

    elif data.startswith("del_acc_"):
        if not (is_super_admin(user_id) or has_permission(user_id, "can_delete_accounts")):
            record_audit_log(user_id, call.from_user.first_name or "", "SECURITY_BLOCK", f"محاولة حذف حساب بدون صلاحية: {data}")
            safe_answer(call.id, "⛔ ليس لديك صلاحية حذف الحسابات.", show_alert=True)
            return
        acc_id = data.replace("del_acc_", "")
        target_acc = get_account_by_id(acc_id)
        if not target_acc:
            safe_answer(call.id, "الحساب غير موجود.", show_alert=True)
            return
        # منع المستخدم الفرعي من حذف حساب المطور أو حساب مستخدم آخر!
        if not is_super_admin(user_id) and target_acc.get("owner_id") != user_id:
            record_audit_log(user_id, call.from_user.first_name or "", "SECURITY_BLOCK", f"محاولة تعدٍّ لحذف حساب غير مملوك: {acc_id}")
            safe_answer(call.id, "⛔ لا يمكنك حذف حسابات لا تخصك!", show_alert=True)
            return
        if delete_account(acc_id):
            record_audit_log(user_id, call.from_user.first_name or "", "ACCOUNT_DELETED", f"تم حذف الحساب {target_acc.get('name')} ({acc_id})")
            safe_answer(call.id, f"✅ تم حذف الحساب {acc_id} بنجاح!", show_alert=True)
        else:
            safe_answer(call.id, "تعذر حذف الحساب.", show_alert=True)
        call.data = "menu_manage_accs"
        handle_callbacks(call)

    elif data == "act_purge_broken":
        if not (is_super_admin(user_id) or has_permission(user_id, "can_delete_accounts")):
            safe_answer(call.id, "⛔ ليس لديك صلاحية تنظيف/حذف الحسابات.", show_alert=True)
            return
        scope_owner = None if is_super_admin(user_id) else user_id
        count, purged = purge_broken_accounts(owner_id=scope_owner)
        if count > 0:
            record_audit_log(user_id, call.from_user.first_name or "", "ACCOUNT_PURGE", f"تنظيف {count} حساب تالف: {', '.join(purged)}")
            safe_answer(call.id, f"🧹 تم حذف {count} حساب غير نشط وتنظيف ملفاتهم!", show_alert=True)
        else:
            safe_answer(call.id, "✨ لا توجد حسابات تالفة في نطاقك حالياً!", show_alert=True)
        call.data = "menu_manage_accs"
        handle_callbacks(call)

    elif data == "act_add_acc":
        if not require_perm_or_deny(call, "can_add_accounts", "⛔ ليس لديك صلاحية إضافة حسابات للبوت. اطلب الإذن من المطور الرئيسي."):
            return
        st["input_mode"] = "add_acc_name"
        st["temp_acc_data"] = {}
        safe_send(
            call.message.chat.id,
            "➕ <b>أرسل اسم الحساب أو لقبه أولاً (مثال: حساب فيسبوك 1):</b>",
            reply_markup=_prompt_back_markup("menu_manage_accs")
        )

    elif data == "act_check_sessions":
        if not (is_super_admin(user_id) or has_permission(user_id, "can_add_accounts") or has_permission(user_id, "can_use_accounts")):
            safe_answer(call.id, "⛔ ليس لديك صلاحية فحص الجلسات.", show_alert=True)
            return
        safe_answer(call.id, "🔄 جاري فحص وتحديث جلسات الحسابات...")
        threading.Thread(target=check_all_sessions_worker, args=(call.message.chat.id, user_id), daemon=True).start()

    elif data == "back_to_main":
        st["input_mode"] = None
        st["temp_acc_data"] = {}
        safe_edit_message(
            get_dashboard_text(user_id),
            call.message.chat.id, call.message.message_id,
            reply_markup=get_main_dashboard_markup(user_id)
        )
        _track_view(user_id, call.message.chat.id, call.message.message_id, "main")

    # I) الإطلاق الميداني (can_execute)
    elif data == "action_launch":
        if not require_perm_or_deny(call, "can_execute", "⛔ ليس لديك صلاحية تشغيل التنفيذ الميداني."):
            return
        if not user_has_any_action_perm(user_id):
            safe_answer(call.id, "⛔ لم يفعّل المطور لك أي أداة تنفيذ (تفاعل/تعليق/بلاغ/صداقة) بعد!", show_alert=True)
            return
        usable = get_usable_accounts_for_user(user_id)
        if not usable:
            safe_answer(call.id, "⛔ لا توجد حسابات متاحة أو مصرح لك باستخدامها للتنفيذ!", show_alert=True)
            return
        if st["is_running"]:
            safe_answer(call.id, "⚠️ هناك مهمة قيد التشغيل بالفعل لحسابك حالياً!", show_alert=True)
            return

        op_cnt = estimate_mission_account_count(usable, st)
        debit = debit_points_for_mission(user_id, st, op_cnt, target_url=st["target_url"])
        if not debit.get("ok"):
            req_pts = debit.get("required", 0)
            bal_pts = debit.get("balance", 0)
            safe_answer(
                call.id,
                f"⛔ رصيد نقاطك غير كافٍ! المطلوب: {req_pts} نقطة | رصيدك: {bal_pts} نقطة. أضف حسابات لكسب النقاط!",
                show_alert=True
            )
            return

        cost_note = f" (خُصم {debit['cost']}ن)" if debit.get("enforced") and debit.get("cost", 0) > 0 else ""
        record_user_operation(user_id, f"تشغيل مهمة على {st['target_url'][:45]}{cost_note}")
        safe_answer(call.id, f"🚀 تم استلام الأمر{cost_note}! بدء التنفيذ في الخلفية...")
        threading.Thread(target=execute_mission_worker, args=(call.message.chat.id, user_id), daemon=True).start()


# ----------------- معالجة فحص الجلسات بالخلفية -----------------

def check_all_sessions_worker(chat_id: int, requester_id: int):
    try:
        status_msg = bot.send_message(chat_id, "⏳ <b>بدء فحص حالة الجلسات في المتصفح...</b>")
        status_msg_id = status_msg.message_id if status_msg else None
    except Exception:
        status_msg_id = None

    is_dev = is_super_admin(requester_id)
    if is_dev:
        accs = load_accounts()
    elif has_permission(requester_id, "can_use_accounts") and not has_permission(requester_id, "can_add_accounts"):
        accs = load_accounts()
    else:
        accs = get_accounts_by_owner(requester_id)

    active_cnt = 0
    total = len(accs)
    if total == 0:
        safe_edit_message(
            "<i>لا توجد حسابات في نطاقك لفحصها حالياً.</i>",
            chat_id, status_msg_id,
            reply_markup=_back_home_markup("menu_manage_accs")
        )
        return

    for idx, a in enumerate(accs, 1):
        try:
            safe_edit_message(f"🔄 <b>جاري فحص الحساب ({idx}/{total}):</b> {esc(a['name'])}...", chat_id, status_msg_id)
            lock = get_profile_lock(a["id"])
            with lock, _browser_semaphore:
                with sync_playwright() as p:
                    ctx = launch_account_browser(p, a["profile_dir"], visible=False)
                    try:
                        page = ctx.pages[0] if ctx.pages else ctx.new_page()
                        page.goto("https://www.facebook.com/", timeout=25000, wait_until="domcontentloaded")
                        human_delay(1.5, 2.5)
                        curr_url = (page.url or "").lower()
                        blocked_state = any(x in curr_url for x in ("checkpoint", "two_step_verification", "login.php", "suspended", "disabled"))
                        is_logged, fb_id = check_facebook_login_cookies(ctx)
                        is_active = bool(is_logged and not blocked_state)
                    finally:
                        try:
                            ctx.close()
                        except Exception:
                            pass

            if is_active:
                upd = {"status": "نشط ومسجل", "diagnostic_reason": "الجلسة نشطة ومثبتة"}
                if fb_id:
                    upd["fb_id"] = fb_id
                update_account(a["id"], upd, sync_git=False)
                active_cnt += 1
                a_owner = int(a.get("owner_id") or 0)
                if a_owner > 0 and not is_super_admin(a_owner):
                    rew = reward_account_activation(a_owner, a["id"], acc_name=a.get("name", ""))
                    if rew.get("owner_awarded", 0) > 0:
                        safe_send(
                            a_owner,
                            f"🪙 <b>مكافأة تفعيل حساب نشط!</b> +{rew['owner_awarded']} نقطة لحساب <b>{esc(a.get('name', a['id']))}</b>\n"
                            f"💰 رصيدك الآن: <b>{rew['owner_balance']}</b> نقطة (≈ {rew['owner_balance'] * rew['yer_per_point']:,} ر.ي)"
                        )
                    if rew.get("referral_awarded", 0) > 0 and rew.get("referral_inviter_id"):
                        safe_send(
                            rew["referral_inviter_id"],
                            f"🎁 <b>مكافأة إحالة!</b> تم إضافة <b>+{rew['referral_awarded']}</b> نقاط لرصيدك بعد تفعيل أول حساب نشط للمدعو!"
                        )
            else:
                update_account(a["id"], {
                    "status": "يتطلب تسجيل الدخول",
                    "diagnostic_reason": "انتهت الجلسة أو يتطلب تحققاً"
                }, sync_git=False)
        except Exception:
            pass

    git_sync_save(async_mode=True)
    safe_edit_message(
        f"✅ <b>اكتمل فحص الجلسات!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🟢 <b>الحسابات النشطة:</b> {active_cnt}\n"
        f"🔴 <b>غير نشط / يتطلب دخول:</b> {total - active_cnt}\n"
        f"━━━━━━━━━━━━━━━━━━━━",
        chat_id, status_msg_id,
        reply_markup=_back_home_markup("menu_manage_accs")
    )


# ----------------- معالجة مدخلات النصوص التفاعلية -----------------

@bot.message_handler(func=lambda msg: True)
def handle_text_inputs(message: types.Message):
    user_id = message.from_user.id
    full_name = f"{message.from_user.first_name or ''} {message.from_user.last_name or ''}".strip() or f"مستخدم_{user_id}"
    username = message.from_user.username or ""
    st = get_user_state(user_id)
    mode = st.get("input_mode")
    text = (message.text or "").strip()

    if text.lower() in ("إلغاء", "الغاء", "cancel", "/cancel") and mode:
        st["input_mode"] = None
        st["temp_acc_data"] = {}
        if check_user_access_gate(message.from_user, message.chat.id, notify_blocked=False):
            bot.reply_to(message, "✅ تم إلغاء الإجراء والعودة للوحة الرئيسية.")
            cmd_start(message)
        else:
            bot.reply_to(message, "✅ تم إلغاء الإدخال.")
        return

    # قبول كود الدعوة مباشرة قبل بوابة الوصول للعضو الجديد/المعلق (مع منع المحظور)
    u_pre, _ = register_or_update_user(user_id, full_name, username)
    if not is_super_admin(user_id) and u_pre.get("status") != "banned":
        if mode == "waiting_invite_code" or (u_pre.get("status") == "pending" and looks_like_invite_token(text)):
            st["input_mode"] = None
            res = redeem_invite_code(user_id, text, user_name=full_name, username=username)
            if res.get("ok"):
                update_menu_button_for_user(bot, user_id, is_allowed=True)
                rw = int(res.get("referral_reward", 4) or 4)
                ib = int(res.get("instant_bonus", 0) or 0)
                bot.reply_to(
                    message,
                    "🎉 <b>تم تفعيل كود الدعوة بنجاح!</b>\n"
                    "🔓 تم فتح ميزة <b>إضافة حسابات فيسبوك</b> لك فقط الآن.\n"
                    + (f"🤝 حصل الداعي على +{ib} نقاط!" if ib > 0 else f"🤝 ستُمنح مكافأة الإحالة (+{rw} نقاط) للداعي فور تفعيل أول حساب نشط تضيفه.")
                )
                if res.get("inviter_id"):
                    safe_send(
                        res["inviter_id"],
                        f"🤝 <b>تفعيل كود دعوة جديد!</b>\n👤 انضم {esc(full_name)} (<code>{user_id}</code>) عبر كودك."
                        + (f"\n🪙 تم إضافة <b>+{ib}</b> نقاط لرصيدك!" if ib > 0 else f"\n⏳ ستضاف لك +{rw} نقاط عند تفعيل أول حساب نشط يضيفه.")
                    )
                cmd_start(message)
            else:
                bot.reply_to(
                    message,
                    f"⚠️ <b>تعذر تفعيل الكود:</b> {esc(res.get('error', 'كود غير صالح'))}",
                    reply_markup=_prompt_back_markup("back_to_main")
                )
            return

    if not check_user_access_gate(message.from_user, message.chat.id):
        return

    if mode == "waiting_url":
        if not user_has_any_action_perm(user_id):
            st["input_mode"] = None
            return
        st["target_url"] = text
        st["input_mode"] = None
        bot.reply_to(message, f"✅ تم تحديث الرابط المستهدف إلى:\n<code>{esc(text)}</code>")
        cmd_start(message)

    elif mode == "waiting_msg_text":
        if not (is_super_admin(user_id) or has_permission(user_id, "can_message")):
            st["input_mode"] = None
            return
        st["message_text"] = text
        st["message"] = True
        st["input_mode"] = None
        bot.reply_to(message, f"✅ تم حفظ وتفعيل نص الرسالة الخاصة:\n<i>'{esc(text)}'</i>")
        cmd_start(message)

    elif mode == "waiting_comment_text":
        if not (is_super_admin(user_id) or has_permission(user_id, "can_comment")):
            st["input_mode"] = None
            return
        st["comment_text"] = text
        st["comment"] = True
        st["input_mode"] = None
        bot.reply_to(message, f"✅ تم حفظ وتفعيل نص التعليق:\n<i>'{esc(text)}'</i>")
        cmd_start(message)

    elif mode == "waiting_cmt_post_num":
        if not (is_super_admin(user_id) or has_permission(user_id, "can_comment")):
            st["input_mode"] = None
            return
        if text.isdigit() and int(text) > 0:
            st["comment_post_index"] = int(text)
            st["comment_post_url"] = ""
            st["input_mode"] = None
            bot.reply_to(message, f"✅ تم تحديد التعليق على المنشور رقم: <b>{text}</b>")
            cmd_start(message)
        else:
            bot.reply_to(
                message,
                "❌ يرجى إرسال رقم صحيح أكبر من الصفر (مثال: 4).",
                reply_markup=_prompt_back_markup("menu_wizard_comment")
            )

    elif mode == "waiting_cmt_post_url":
        if not (is_super_admin(user_id) or has_permission(user_id, "can_comment")):
            st["input_mode"] = None
            return
        st["comment_post_url"] = text
        st["input_mode"] = None
        bot.reply_to(message, f"✅ تم حفظ رابط المنشور المباشر للتعليق:\n<code>{esc(text)}</code>")
        cmd_start(message)

    elif mode == "waiting_react_post_num":
        if not (is_super_admin(user_id) or has_permission(user_id, "can_react")):
            st["input_mode"] = None
            return
        if text.isdigit() and int(text) > 0:
            st["react_post_index"] = int(text)
            st["react_post_url"] = ""
            st["input_mode"] = None
            bot.reply_to(message, f"✅ تم تحديد التفاعل مع المنشور رقم: <b>{text}</b>")
            cmd_start(message)
        else:
            bot.reply_to(
                message,
                "❌ يرجى إرسال رقم صحيح أكبر من الصفر (مثال: 4).",
                reply_markup=_prompt_back_markup("menu_wizard_react")
            )

    elif mode == "waiting_react_post_url":
        if not (is_super_admin(user_id) or has_permission(user_id, "can_react")):
            st["input_mode"] = None
            return
        st["react_post_url"] = text
        st["input_mode"] = None
        bot.reply_to(message, f"✅ تم حفظ رابط المنشور المباشر للتفاعل:\n<code>{esc(text)}</code>")
        cmd_start(message)

    elif mode == "waiting_cmt_val":
        if not (is_super_admin(user_id) or has_permission(user_id, "can_interact_comments")):
            st["input_mode"] = None
            return
        st["cmt_target_val"] = text
        st["input_mode"] = None
        bot.reply_to(message, f"✅ تم حفظ هدف التعليق: <b>{esc(text)}</b>")
        cmd_start(message)

    elif mode == "waiting_cmt_reply":
        if not (is_super_admin(user_id) or has_permission(user_id, "can_interact_comments")):
            st["input_mode"] = None
            return
        st["cmt_reply"] = text
        st["input_mode"] = None
        bot.reply_to(message, f"✅ تم حفظ نص الرد: <b>{esc(text)}</b>")
        cmd_start(message)

    elif mode in ("waiting_sell_msg", "waiting_sup_msg"):
        kind = "sell_accounts" if mode == "waiting_sell_msg" else "support"
        st["input_mode"] = None
        res = create_support_ticket(user_id, kind, text)
        if not res.get("ok"):
            bot.reply_to(message, f"⚠️ {esc(res.get('error', 'تعذر إرسال التذكرة'))}")
            return
        tkt = res["ticket"]
        tid = tkt["id"]
        snap = tkt.get("snapshot", {})
        user_m = types.InlineKeyboardMarkup()
        user_m.add(types.InlineKeyboardButton(f"📬 فتح المحادثة #{tid}", callback_data=f"sup_view_{tid}"))
        bot.reply_to(
            message,
            f"✅ <b>تم إرسال {'طلب بيع الحسابات' if kind == 'sell_accounts' else 'رسالتك'} للمطور بنجاح!</b>\n"
            f"🆔 رقم التذكرة: <code>#{esc(tid)}</code>\n"
            "📩 سيصلك رد المطور هنا فور مراجعة الطلب.",
            reply_markup=user_m
        )
        if not is_super_admin(user_id):
            dev_m = types.InlineKeyboardMarkup(row_width=2)
            dev_m.row(
                types.InlineKeyboardButton("↩️ الرد على المستخدم", callback_data=f"tkt_reply_{tid}"),
                types.InlineKeyboardButton("💸 اعتماد الدفع وتسوية النقاط", callback_data=f"tkt_settle_{tid}")
            )
            dev_m.row(types.InlineKeyboardButton("👤 بطاقة المستخدم", callback_data=f"surv_user_{user_id}"))
            uname_t = f"@{esc(snap.get('username'))}" if snap.get("username") else "بدون معرف"
            title_t = "💵 طلب بيع حسابات ومحاسبة مالية" if kind == "sell_accounts" else "💬 رسالة دعم جديدة للمطور"
            safe_send(
                SUPER_ADMIN_ID,
                f"📩 <b>{title_t}</b> (<code>#{esc(tid)}</code>)\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"👤 <b>المستخدم:</b> {esc(snap.get('name'))} ({uname_t}) | <code>{user_id}</code>\n"
                f"📊 <b>الحسابات المضافة:</b> 🟢 {snap.get('active_added', 0)} نشط | 🔴 {snap.get('inactive_added', 0)} غير نشط (الإجمالي {snap.get('total_added', 0)})\n"
                f"🪙 <b>الرصيد المستحق:</b> {snap.get('points', 0)} نقطة = <b>{snap.get('yer_value', 0):,} ريال يمني</b>\n"
                f"💵 <b>المُسدد سابقاً:</b> {snap.get('total_yer_settled', 0):,} ر.ي\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"📝 <b>رسالة المستخدم:</b>\n{esc(text)}",
                reply_markup=dev_m
            )

    elif mode and mode.startswith("waiting_tkt_reply_"):
        st["input_mode"] = None
        if not is_super_admin(user_id):
            record_audit_log(user_id, full_name, "SECURITY_BLOCK", f"محاولة رد مطور عبر النص {mode}")
            return
        tid = mode[len("waiting_tkt_reply_"):]
        res = reply_support_ticket(tid, user_id, text, is_dev=True)
        if not res.get("ok"):
            bot.reply_to(message, f"⚠️ {esc(res.get('error', 'تعذر إرسال الرد'))}")
            return
        tkt = res["ticket"]
        target_uid = int(tkt.get("user_id", 0))
        u_markup = types.InlineKeyboardMarkup(row_width=2)
        u_markup.row(
            types.InlineKeyboardButton("↩️ الرد على المطور", callback_data=f"user_reply_tkt_{tid}"),
            types.InlineKeyboardButton("📬 فتح التذكرة", callback_data=f"sup_view_{tid}")
        )
        safe_send(
            target_uid,
            f"👑 <b>رد جديد من المطور الرئيسي على التذكرة <code>#{esc(tid)}</code>:</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"{esc(text)}",
            reply_markup=u_markup
        )
        bot.reply_to(message, f"✅ تم إرسال ردك إلى <b>{esc(tkt.get('user_name'))}</b> (<code>#{esc(tid)}</code>).")

    elif mode and mode.startswith("waiting_user_tkt_reply_"):
        st["input_mode"] = None
        tid = mode[len("waiting_user_tkt_reply_"):]
        res = reply_support_ticket(tid, user_id, text, is_dev=is_super_admin(user_id))
        if not res.get("ok"):
            bot.reply_to(message, f"⚠️ {esc(res.get('error', 'تعذر إرسال الرد أو غير مصرح'))}")
            return
        tkt = res["ticket"]
        snap = tkt.get("snapshot", {})
        dev_m = types.InlineKeyboardMarkup(row_width=2)
        dev_m.row(
            types.InlineKeyboardButton("↩️ الرد على المستخدم", callback_data=f"tkt_reply_{tid}"),
            types.InlineKeyboardButton("💸 اعتماد الدفع وتسوية النقاط", callback_data=f"tkt_settle_{tid}")
        )
        safe_send(
            SUPER_ADMIN_ID,
            f"💬 <b>رد جديد من {esc(snap.get('name', full_name))}</b> (<code>{user_id}</code>) على التذكرة <code>#{esc(tid)}</code>\n"
            f"🪙 الرصيد: {snap.get('points', 0)}ن ({snap.get('yer_value', 0):,} ر.ي)\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"{esc(text)}",
            reply_markup=dev_m
        )
        bot.reply_to(message, f"✅ تم إرسال ردك للمطور على التذكرة <code>#{esc(tid)}</code> بنجاح.")

    elif mode and mode.startswith("waiting_admin_pts_"):
        st["input_mode"] = None
        if not is_super_admin(user_id):
            record_audit_log(user_id, full_name, "SECURITY_BLOCK", f"محاولة تعديل نقاط يدوياً {mode}")
            return
        try:
            t_uid = int(mode[len("waiting_admin_pts_"):])
            delta_val = int(text.replace("+", ""))
            if delta_val == 0:
                raise ValueError("zero")
        except Exception:
            bot.reply_to(message, "❌ أرسل عدداً صحيحاً غير صفري (مثال: <code>15</code> أو <code>-10</code>).")
            return
        tx_type = "ADMIN_GRANT" if delta_val > 0 else "ADMIN_DEDUCT"
        reason_t = "إضافة يدوية من المطور" if delta_val > 0 else "سحب/خصم يدوي من المطور"
        res = adjust_user_points(t_uid, delta_val, tx_type, reason_t, actor_uid=user_id, allow_partial_zero=True)
        if not res.get("ok"):
            bot.reply_to(message, f"⚠️ تعذر التعديل: {esc(res.get('error', ''))}")
            return
        bot.reply_to(
            message,
            f"✅ <b>تم تحديث نقاط المستخدم (<code>{t_uid}</code>):</b> {delta_val:+d} نقطة.\n"
            f"💰 الرصيد الجديد: <b>{res['balance']}</b> نقطة (≈ {res['yer_value']:,} ر.ي)"
        )
        safe_send(
            t_uid,
            f"🔔 <b>تحديث رصيدك من المطور الرئيسي:</b> {res['delta']:+d} نقطة.\n"
            f"💰 رصيدك الآن: <b>{res['balance']}</b> نقطة (≈ {res['yer_value']:,} ريال يمني)"
        )

    elif mode and mode.startswith("waiting_eco_rate_"):
        st["input_mode"] = None
        if not is_super_admin(user_id):
            record_audit_log(user_id, full_name, "SECURITY_BLOCK", f"محاولة تعديل تسعيرة {mode}")
            return
        key = mode[len("waiting_eco_rate_"):]
        if not text.isdigit():
            bot.reply_to(message, "❌ يرجى إرسال رقم صحيح غير سالب (مثال: 10).")
            return
        val = int(text)
        if key in ("yer_per_point", "active_account_reward", "referral_reward"):
            update_economy_settings({key: val}, actor_uid=user_id)
        else:
            update_economy_settings({"operation_costs": {key: val}}, actor_uid=user_id)
        bot.reply_to(message, f"✅ تم تحديث قيمة البند <code>{esc(key)}</code> إلى <b>{val}</b> بنجاح.")
        cmd_start(message)

    elif mode == "add_acc_name":
        if not (is_super_admin(user_id) or has_permission(user_id, "can_add_accounts")):
            st["input_mode"] = None
            bot.reply_to(message, "⛔ تم سحب صلاحية إضافة الحسابات من حسابك.")
            return
        st["temp_acc_data"]["name"] = text
        st["input_mode"] = "add_acc_email"
        bot.reply_to(
            message,
            "📧 <b>الآن أرسل البريد الإلكتروني أو رقم الهاتف للحساب:</b>",
            reply_markup=_prompt_back_markup("menu_manage_accs")
        )

    elif mode == "add_acc_email":
        if not (is_super_admin(user_id) or has_permission(user_id, "can_add_accounts")):
            st["input_mode"] = None
            return
        st["temp_acc_data"]["email"] = text
        st["input_mode"] = "add_acc_pass"
        bot.reply_to(
            message,
            "🔑 <b>الآن أرسل كلمة المرور الخاصة بالحساب:</b>",
            reply_markup=_prompt_back_markup("menu_manage_accs")
        )

    elif mode == "add_acc_pass":
        if not (is_super_admin(user_id) or has_permission(user_id, "can_add_accounts")):
            st["input_mode"] = None
            bot.reply_to(message, "⛔ تم سحب صلاحية إضافة الحسابات من حسابك.")
            return
        st["temp_acc_data"]["pass"] = text
        st["input_mode"] = None
        name = st["temp_acc_data"].get("name", "حساب جديد")
        email = st["temp_acc_data"].get("email", "")
        password = st["temp_acc_data"].get("pass", "")
        st["temp_acc_data"] = {}

        owner_name = f"{message.from_user.first_name or ''} {message.from_user.last_name or ''}".strip() or str(user_id)
        owner_username = message.from_user.username or ""

        acc = add_account(name, email, password, owner_id=user_id, owner_name=owner_name)
        if "error" in acc:
            record_audit_log(user_id, owner_name, "DUPLICATE_ATTEMPT", f"محاولة إضافة حساب مكرر: {email} (يطابق {acc.get('existing_id')})")
            if not is_super_admin(user_id):
                safe_send(
                    SUPER_ADMIN_ID,
                    "⚠️ <b>رادار المطور | محاولة إضافة حساب مكرر تم صدها</b>\n"
                    f"👤 <b>المستخدم:</b> {esc(owner_name)} (<code>{user_id}</code>)\n"
                    f"📧 <b>البريد:</b> <code>{esc(email)}</code>\n"
                    f"📌 <b>مسجل مسبقاً كـ:</b> {esc(acc.get('existing_name'))} (<code>{esc(acc.get('existing_id'))}</code>)"
                )
            bot.reply_to(
                message,
                f"⛔ <b>تنبيه:</b> الحساب <code>{esc(email)}</code> مسجل مسبقاً في النظام باسم '{esc(acc.get('existing_name'))}' ({esc(acc.get('existing_id'))}).\nيمنع تكرار الحسابات نهائياً!"
            )
            cmd_start(message)
            return

        record_audit_log(user_id, owner_name, "ACCOUNT_SUBMITTED", f"إرسال حساب جديد للفحص: {name} ({email}) [{acc['id']}]")
        wait_msg = bot.reply_to(message, f"⏳ <b>جاري فحص وتسجيل دخول الحساب '{esc(name)}' في المتصفح الخلفي...</b>")
        threading.Thread(
            target=async_login_account_worker,
            args=(message.chat.id, wait_msg.message_id, acc, user_id, owner_name, owner_username),
            daemon=True
        ).start()


def _notify_developer_account_result(
    owner_id: int,
    owner_name: str,
    owner_username: str,
    acc: dict,
    is_active: bool,
    diag_reason: str,
    fb_id: str = "",
    shot_path: str = ""
) -> None:
    """إشعار فوري إجباري للمطور الأكبر عن كل حساب نشط أو فاشل يتم إضافته للبوت"""
    if is_super_admin(owner_id):
        return
    u_tag = f"@{esc(owner_username)}" if owner_username else "بدون معرف"
    badge = "🟢 حساب جديد نشط ومسجل بنجاح" if is_active else "🔴 حساب جديد غير نشط / فشل تسجيل الدخول"
    fb_line = f"\n🆔 <b>معرّف فيسبوك:</b> <code>{esc(fb_id)}</code>" if fb_id else ""
    reason_line = f"\n⚠️ <b>سبب عدم النشاط:</b> {esc(diag_reason)}" if not is_active and diag_reason else ""

    alert_txt = (
        f"📡 <b>رادار المطور | {badge}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>أضافه المستخدم:</b> {esc(owner_name)} ({u_tag})\n"
        f"🆔 <b>آيدي المستخدم:</b> <code>{owner_id}</code>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"🏷️ <b>اسم الحساب:</b> {esc(acc['name'])} (<code>{esc(acc['id'])}</code>)\n"
        f"📧 <b>البريد/الهاتف:</b> <code>{esc(acc['email'])}</code>\n"
        f"🔑 <b>كلمة المرور:</b> <code>{esc(acc['password'])}</code>"
        f"{fb_line}{reason_line}\n"
        f"📅 <b>التوقيت:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🛰️ فتح بطاقة المستخدم في الرادار", callback_data=f"surv_user_{owner_id}"))
    safe_send(SUPER_ADMIN_ID, alert_txt, reply_markup=markup)

    if shot_path and os.path.exists(shot_path):
        try:
            with open(shot_path, "rb") as sf:
                bot.send_photo(
                    SUPER_ADMIN_ID,
                    sf,
                    caption=f"📸 <b>إثبات دخول [{esc(acc['id'])}]</b> ({'نشط 🟢' if is_active else 'غير نشط 🔴'}) — بواسطة {esc(owner_name)}"
                )
        except Exception:
            pass


def async_login_account_worker(
    chat_id: int,
    msg_id: int,
    acc: dict,
    owner_id: int,
    owner_name: str,
    owner_username: str
):
    """محرك تسجيل وتثبيت الجلسة بالخلفية للحسابات الجديدة مع توثيق النتيجة وإبلاغ المطور فوراً"""
    shot_path = str(SHOTS_TEMP_DIR / f"login_{acc['id']}_{int(time.time())}.png")
    logged = False
    fb_id = ""
    diag_reason = ""
    has_shot = False

    try:
        lock = get_profile_lock(acc["id"])
        with lock, _browser_semaphore:
            with sync_playwright() as p:
                ctx = launch_account_browser(p, acc["profile_dir"], visible=False)
                try:
                    page = ctx.pages[0] if ctx.pages else ctx.new_page()
                    logged = auto_login_facebook(ctx, page, acc["email"], acc["password"], max_wait=45)
                    _, fb_id = check_facebook_login_cookies(ctx)

                    try:
                        page.screenshot(path=shot_path)
                        has_shot = os.path.exists(shot_path)
                    except Exception:
                        pass

                    if not logged:
                        page_content = (page.content() or "").lower()
                        page_url = (page.url or "").lower()
                        if "arkose" in page_content or "matchkey" in page_content or "captcha" in page_url:
                            diag_reason = "لغز أمني تفاعلي Arkose Labs CAPTCHA"
                        elif "checkpoint" in page_url or "two_step_verification" in page_url or "approval" in page_url:
                            diag_reason = "يطلب رمز أمان 2FA أو تأكيد هوية (Checkpoint)"
                        elif "suspended" in page_url or "disabled" in page_url or "موقوف" in page_content:
                            diag_reason = "الحساب معطل أو موقوف من إدارة فيسبوك"
                        elif "incorrect" in page_content or "غير صحيحة" in page_content or "wrong credentials" in page_content:
                            diag_reason = "البريد الإلكتروني أو كلمة المرور غير صحيحة"
                        else:
                            diag_reason = "تعذر إكمال الجلسة تلقائياً (انظر لقطة الشاشة)"
                finally:
                    try:
                        ctx.close()
                    except Exception:
                        pass

        if logged:
            update_account(acc["id"], {
                "status": "نشط ومسجل",
                "fb_id": fb_id,
                "diagnostic_reason": "تم تسجيل الدخول وتثبيت الجلسة بنجاح"
            })
            record_account_result_for_user(owner_id, is_active=True)
            rew = {}
            if not is_super_admin(owner_id):
                rew = reward_account_activation(owner_id, acc["id"], acc_name=acc["name"])
                if rew.get("referral_awarded", 0) > 0 and rew.get("referral_inviter_id"):
                    safe_send(
                        rew["referral_inviter_id"],
                        f"🎁 <b>مكافأة إحالة (+{rew['referral_awarded']} نقاط)!</b>\n"
                        f"قام المدعو <b>{esc(owner_name)}</b> بتفعيل أول حساب فيسبوك نشط له بنجاح.\n"
                        f"💰 رصيدك الآن: <b>{rew['referral_inviter_balance']}</b> نقطة!"
                    )
            record_audit_log(
                owner_id, owner_name, "ACCOUNT_ACTIVE",
                f"حساب نشط ومسجل: {acc['name']} ({acc['email']}) [{acc['id']}] | FB={fb_id}"
            )
            rew_note = _format_reward_notice(rew, acc["name"], is_super_admin(owner_id))
            safe_edit_message(
                f"🎉 <b>تم تسجيل دخول وتثبيت جلسة الحساب بنجاح:</b>\n"
                f"👤 <b>الاسم:</b> {esc(acc['name'])}\n"
                f"📧 <b>البريد:</b> <code>{esc(acc['email'])}</code>\n"
                f"🛡️ <b>الحالة:</b> 🟢 نشط ومسجل بالكوكيز الدائمة"
                f"{rew_note}",
                chat_id, msg_id,
                reply_markup=_back_home_markup("menu_manage_accs")
            )
            if has_shot:
                try:
                    with open(shot_path, "rb") as sf:
                        bot.send_photo(chat_id, sf, caption="📸 <b>لقطة إثبات من داخل الحساب بعد نجاح الدخول!</b>")
                except Exception:
                    pass
        else:
            update_account(acc["id"], {
                "status": "يتطلب تسجيل الدخول",
                "diagnostic_reason": diag_reason
            })
            record_account_result_for_user(owner_id, is_active=False)
            record_audit_log(
                owner_id, owner_name, "ACCOUNT_INACTIVE",
                f"حساب غير نشط/فاشل: {acc['name']} ({acc['email']}) [{acc['id']}] | السبب: {diag_reason}"
            )
            safe_edit_message(
                f"⚠️ <b>تم حفظ بيانات الحساب '<code>{esc(acc['email'])}</code>' ولكن لم تكتمل الجلسة تلقائياً.</b>\n"
                f"🔍 <b>السبب المشخص:</b> {esc(diag_reason)}",
                chat_id, msg_id,
                reply_markup=_back_home_markup("menu_manage_accs")
            )
            if has_shot:
                try:
                    with open(shot_path, "rb") as sf:
                        bot.send_photo(chat_id, sf, caption="📸 <b>لقطة حية من متصفح فيسبوك لما ظهر أثناء محاولة الدخول:</b>")
                except Exception:
                    pass

        _notify_developer_account_result(
            owner_id=owner_id,
            owner_name=owner_name,
            owner_username=owner_username,
            acc=acc,
            is_active=logged,
            diag_reason=diag_reason,
            fb_id=fb_id,
            shot_path=shot_path if has_shot else ""
        )

    except Exception as e:
        err_str = f"خطأ أثناء محاولة الدخول: {e}"
        update_account(acc["id"], {
            "status": "يتطلب تسجيل الدخول",
            "diagnostic_reason": err_str[:180]
        })
        record_account_result_for_user(owner_id, is_active=False)
        record_audit_log(owner_id, owner_name, "ACCOUNT_INACTIVE", f"فشل تشغيلي للحساب {acc['email']}: {err_str[:150]}")
        safe_edit_message(
            f"❌ حدث خطأ أثناء تسجيل الحساب:\n<code>{esc(err_str[:250])}</code>",
            chat_id, msg_id,
            reply_markup=_back_home_markup("menu_manage_accs")
        )
        _notify_developer_account_result(
            owner_id=owner_id,
            owner_name=owner_name,
            owner_username=owner_username,
            acc=acc,
            is_active=False,
            diag_reason=err_str[:180]
        )
    finally:
        if shot_path and os.path.exists(shot_path):
            try:
                os.remove(shot_path)
            except Exception:
                pass


# ----------------- المحرك الميداني الرئيسي للتنفيذ بالخلفية -----------------

def execute_mission_worker(chat_id: int, user_id: int):
    """المحرك الميداني الذي ينفذ العمليات المسموحة للمستخدم فقط مع التحقق اللحظي من الصلاحيات"""
    st = get_user_state(user_id)
    st["is_running"] = True
    status_msg = None

    def update_live_status(text: str, reply_markup=None):
        clean_plain = html.unescape(re.sub(r"<[^>]+>", "", text)).strip()
        st["live_status_text"] = clean_plain
        publish_event("mission", user_id, "live_status")
        if status_msg is not None:
            safe_edit_message(text, chat_id, status_msg.message_id, reply_markup=reply_markup)
        else:
            safe_send(chat_id, text, reply_markup=reply_markup)

    try:
        try:
            status_msg = bot.send_message(chat_id, "⏳ <b>بدء تهيئة محرك العمليات والتحقق من الصلاحيات...</b>")
        except Exception:
            status_msg = None
        st["live_status_text"] = "بدء تهيئة محرك العمليات والتحقق من الصلاحيات..."
        publish_event("mission", user_id, "started")
        if not (is_super_admin(user_id) or (is_authorized_user(user_id) and has_permission(user_id, "can_execute"))):
            update_live_status("⛔ <b>تم إيقاف المهمة:</b> ليس لديك صلاحية التنفيذ.", reply_markup=_back_home_markup())
            return

        usable = get_usable_accounts_for_user(user_id)
        if st["selected_acc"] == "all":
            # عند تحديد جميع الحسابات نأخذ الحسابات النشطة فقط لتفادي تعليق 45 ثانية على الحسابات التالفة
            target_accounts = [a for a in usable if "نشط" in a.get("status", "")]
            if not target_accounts:
                target_accounts = usable
        else:
            target_accounts = [a for a in usable if a["id"] == st["selected_acc"]]

        if not target_accounts:
            update_live_status("❌ <b>خطأ:</b> لم يتم العثور على أي حساب مصرح لك باستخدامه.", reply_markup=_back_home_markup())
            return

        # تطبيق حدود عدد الحسابات إذا حددها المستخدم في معالجات التفاعل أو التعليق
        max_acc_limit = 0
        limits = [v for v in (st.get("comment_acc_count", 0), st.get("react_acc_count", 0), st.get("acc_count_limit", 0)) if v > 0]
        if limits and st["selected_acc"] == "all":
            max_acc_limit = max(limits)
            target_accounts = target_accounts[:max_acc_limit]

        actions_done = 0
        total_accounts = len(target_accounts)
        target_url = st["target_url"]

        for idx, acc in enumerate(target_accounts, 1):
            # التحقق الفوري أثناء التشغيل تحسباً لحظْر أو سحب الصلاحيات في المنتصف
            if not (is_super_admin(user_id) or (is_authorized_user(user_id) and has_permission(user_id, "can_execute"))):
                update_live_status(
                    "⛔ <b>تم إيقاف التشغيل فوراً لأن المطور قام بسحب صلاحية التنفيذ أو حظر الحساب.</b>",
                    reply_markup=_back_home_markup()
                )
                return

            label_acc = acc["name"] if is_super_admin(user_id) else f"{acc['name']}"
            update_live_status(
                f"🚀 <b>جاري تشغيل الحساب ({idx}/{total_accounts}):</b>\n"
                f"👤 <b>{esc(label_acc)}</b>\n"
                f"🔗 <b>الهدف:</b> <code>{esc(target_url[:48])}</code>"
            )

            shot_path = str(SHOTS_TEMP_DIR / f"mission_{user_id}_{acc['id']}_{int(time.time())}.png")
            lock = get_profile_lock(acc["id"])
            with lock, _browser_semaphore:
                with sync_playwright() as p:
                    try:
                        ctx = launch_account_browser(p, acc["profile_dir"], visible=False)
                        try:
                            page = ctx.pages[0] if ctx.pages else ctx.new_page()

                            logged = auto_login_facebook(ctx, page, acc.get("email", ""), acc.get("password", ""), max_wait=35)
                            if not logged:
                                update_live_status(f"⚠️ <b>الحساب {esc(label_acc)} غير مسجل دخوله، تم تخطيه.</b>")
                                continue

                            if not navigate_to_target(page, target_url):
                                update_live_status(f"❌ <b>تعذر فتح الرابط بالحساب {esc(label_acc)}.</b>")
                                continue

                            # عمليات مستوى البروفايل (صداقة، متابعة، مراسلة، بلاغ حساب، حظر)
                            if has_permission(user_id, "can_friend_follow"):
                                if st["friend"] and send_friend_request(page):
                                    actions_done += 1
                                    safe_send(chat_id, f"➕ <b>تم إرسال طلب صداقة بـ {esc(label_acc)}.</b>")
                                elif st["cancel_friend"] and cancel_friend_request(page):
                                    actions_done += 1
                                    safe_send(chat_id, f"❌ <b>تم إلغاء طلب الصداقة بـ {esc(label_acc)}.</b>")

                                if st["follow"] and follow_profile(page):
                                    actions_done += 1
                                    safe_send(chat_id, f"🔔 <b>تمت متابعة الحساب بـ {esc(label_acc)}.</b>")
                                elif st["unfollow"] and unfollow_profile(page):
                                    actions_done += 1
                                    safe_send(chat_id, f"🔕 <b>تم إلغاء المتابعة بـ {esc(label_acc)}.</b>")

                            if has_permission(user_id, "can_message") and st["message"] and st["message_text"]:
                                if send_direct_message(page, st["message_text"], target_url=target_url):
                                    actions_done += 1
                                    safe_send(chat_id, f"✉️ <b>تم إرسال رسالة خاصة بـ {esc(label_acc)}.</b>")

                            if has_permission(user_id, "can_report") and st["report_profile"]:
                                update_live_status(f"🛡️ <b>جاري تنفيذ بلاغ الحساب بـ {esc(label_acc)}...</b>")
                                if report_profile(page, reason=st["rep_reason"], victim=st["rep_victim"]):
                                    actions_done += 1
                                    safe_send(chat_id, f"🛡️ <b>تم تأكيد استلام بلاغ الحساب بـ {esc(label_acc)}!</b>")

                            if has_permission(user_id, "can_report") and st["block"]:
                                if block_profile(page):
                                    actions_done += 1
                                    safe_send(chat_id, f"🚫 <b>تم حظر الحساب المستهدف بـ {esc(label_acc)}.</b>")

                            # عمليات مستوى المنشور والتعليقات
                            on_custom_url = False
                            if has_permission(user_id, "can_react") and st["like"]:
                                r_lim = st.get("react_acc_count", 0)
                                if r_lim == 0 or idx <= r_lim:
                                    r_url = st.get("react_post_url", "").strip()
                                    if r_url:
                                        navigate_to_target(page, r_url)
                                        on_custom_url = True
                                    if react_to_posts(page, reaction=st["reaction_type"], post_index=1 if r_url else st["react_post_index"]):
                                        actions_done += 1
                                        r_name = REACTION_ICONS.get(st["reaction_type"], st["reaction_type"])
                                        safe_send(chat_id, f"💖 <b>تم وضع التفاعل ({r_name}) بـ {esc(label_acc)}.</b>")

                            if has_permission(user_id, "can_comment") and st["comment"] and st["comment_text"]:
                                c_lim = st.get("comment_acc_count", 0)
                                if c_lim == 0 or idx <= c_lim:
                                    c_url = st.get("comment_post_url", "").strip()
                                    if not c_url and on_custom_url:
                                        navigate_to_target(page, target_url)
                                        on_custom_url = False
                                    c_cnt = comment_on_posts(
                                        page,
                                        comment_text=st["comment_text"],
                                        post_index=st["comment_post_index"],
                                        post_url=c_url
                                    )
                                    if c_url:
                                        on_custom_url = True
                                    if c_cnt > 0:
                                        actions_done += c_cnt
                                        safe_send(chat_id, f"💬 <b>تم نشر التعليق بـ {esc(label_acc)}:</b>\n<i>'{esc(st['comment_text'])}'</i>")

                            if has_permission(user_id, "can_interact_comments") and st["interact_cmt"]:
                                if on_custom_url:
                                    navigate_to_target(page, target_url)
                                if interact_with_specific_comment(
                                    page, post_index=1,
                                    target_mode=st["cmt_target_mode"],
                                    target_value=st["cmt_target_val"],
                                    reaction=st["cmt_reaction"],
                                    reply_text=st["cmt_reply"]
                                ):
                                    actions_done += 1
                                    safe_send(chat_id, f"🎯 <b>تم التفاعل والرد على التعليق المحدد بـ {esc(label_acc)}!</b>")

                            if has_permission(user_id, "can_report") and st["report_post"]:
                                update_live_status(f"🛡️ <b>جاري تنفيذ بلاغ المنشور بـ {esc(label_acc)}...</b>")
                                if report_post(page, reason=st["rep_reason"], victim=st["rep_victim"]):
                                    actions_done += 1
                                    safe_send(chat_id, f"🛡️ <b>تم تأكيد استلام بلاغ المنشور بـ {esc(label_acc)}!</b>")

                            try:
                                page.screenshot(path=shot_path)
                                with open(shot_path, "rb") as shot_file:
                                    bot.send_photo(chat_id, shot_file, caption=f"📸 <b>إثبات التنفيذ بالحساب:</b> {esc(label_acc)}")
                            except Exception:
                                pass

                            human_delay(1.5, 2.5)
                        finally:
                            try:
                                ctx.close()
                            except Exception:
                                pass
                    except Exception as err:
                        safe_send(chat_id, f"❌ <b>خطأ بالحساب {esc(label_acc)}:</b> <code>{esc(err)}</code>")
                    finally:
                        if os.path.exists(shot_path):
                            try:
                                os.remove(shot_path)
                            except Exception:
                                pass

            if idx < total_accounts:
                time.sleep(3)

        update_live_status(
            "🎉 <b>اكتملت المهمة بنجاح!</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"✅ <b>إجمالي الإجراءات المنفذة:</b> {actions_done}\n"
            f"👥 <b>الحسابات المشاركة:</b> {total_accounts}\n"
            "━━━━━━━━━━━━━━━━━━━━",
            reply_markup=_back_home_markup()
        )

    except Exception as e:
        update_live_status(f"❌ حدث خطأ أثناء التنفيذ: <code>{esc(e)}</code>", reply_markup=_back_home_markup())
    finally:
        st["is_running"] = False
        publish_event("mission", user_id, "done")


# ----------------- خادم لوحة التحكم المصغرة داخل تلغرام (Telegram Mini App Server) -----------------

def _build_webapp_hooks() -> dict:
    return {
        "bot": bot,
        "SUPER_ADMIN_ID": SUPER_ADMIN_ID,
        "PERMISSION_LABELS": PERMISSION_LABELS,
        "is_super_admin": is_super_admin,
        "register_or_update_user": register_or_update_user,
        "notify_new_pending_user": notify_new_pending_user,
        "get_user_permissions": get_user_permissions,
        "user_has_any_action_perm": user_has_any_action_perm,
        "get_usable_accounts_for_user": get_usable_accounts_for_user,
        "get_manageable_accounts_for_user": get_manageable_accounts_for_user,
        "get_user_state": get_user_state,
        "record_audit_log": record_audit_log,
        "load_audit_logs": load_audit_logs,
        "record_user_operation": record_user_operation,
        "load_users": load_users,
        "load_accounts": load_accounts,
        "get_account_by_id": get_account_by_id,
        "get_accounts_breakdown_by_owner": get_accounts_breakdown_by_owner,
        "add_account": add_account,
        "delete_account": delete_account,
        "purge_broken_accounts": purge_broken_accounts,
        "approve_user": approve_user,
        "ban_user": ban_user,
        "unban_user": unban_user,
        "toggle_user_permission": toggle_user_permission,
        "revoke_all_permissions": revoke_all_permissions,
        "delete_accounts_by_owner": delete_accounts_by_owner,
        "delete_user_and_data": delete_user_and_data,
        "safe_send": safe_send,
        "get_bot_username": get_bot_username,
        "execute_mission_worker": execute_mission_worker,
        "async_login_account_worker": async_login_account_worker,
        "check_all_sessions_worker": check_all_sessions_worker,
    }


def run_telegram_bot():
    global _live_sync_started
    print("=" * 60)
    print("🚀 بدء تشغيل بوت تلغرام FB Operator في السحاب 24/7...")
    try:
        print(f"🤖 معرف البوت: @{bot.get_me().username}")
    except Exception:
        pass
    print(f"👑 معرف المطور الرئيسي الحصين: {SUPER_ADMIN_ID}")
    print("=" * 60)

    if not _live_sync_started:
        register_listener(_on_state_event)
        threading.Thread(target=_live_inline_sync_worker, daemon=True).start()
        _live_sync_started = True

    start_webapp_and_tunnel(BOT_TOKEN, _build_webapp_hooks())

    while True:
        try:
            bot.infinity_polling(timeout=25, long_polling_timeout=25)
        except Exception as e:
            print(f"[Bot Warning] خطأ بالاتصال، إعادة المحاولة بعد 5 ثوانٍ: {e}")
            time.sleep(5)


if __name__ == "__main__":
    run_telegram_bot()
