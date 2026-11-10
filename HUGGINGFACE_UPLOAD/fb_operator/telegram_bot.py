"""
بوت تلغرام المتطور للتحكم الكامل بأتمتة حسابات فيسبوك (FB Operator Telegram Bot)
يدعم التحكم الكامل من الهاتف، بوابة الموافقة الصارمة (Strict Two-Tier Approval Gate)،
رادار المراقبة الشامل للمطور الأكبر (User Surveillance & Analytics Radar)،
منع تكرار الحسابات نهائياً، لوحة الويب التفاعلية (Web App Dashboard)،
والتنفيذ المتوازي لـ 1000+ مستخدم دون تداخل داخل بيئة الديسكتوب الافتراضية 24/7.
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
import time
import threading
from datetime import datetime
import telebot
from telebot import types
from playwright.sync_api import sync_playwright

from fb_operator.account_manager import (
    load_accounts, add_account, update_account, delete_account, save_accounts,
    purge_broken_accounts, get_accounts_by_owner, delete_accounts_by_owner
)
from fb_operator.admin_manager import (
    is_super_admin, is_authorized_user, has_permission, register_or_update_user,
    get_user_status, approve_user, ban_user, unban_user, toggle_user_permission,
    delete_user_and_data, load_users, record_user_operation, SUPER_ADMIN_ID
)
from fb_operator.browser_manager import (
    launch_account_browser, auto_login_facebook, check_facebook_login_cookies, human_delay
)
from fb_operator.actions import (
    navigate_to_target, like_posts, comment_on_posts, react_to_posts, unlike_posts,
    send_friend_request, cancel_friend_request, follow_profile, unfollow_profile,
    send_direct_message, block_profile, report_profile, report_post,
    interact_with_specific_comment
)

BOT_TOKEN = "8798272294:AAEY_LIYnVRIY2T-WUP63duCn5V7VFgGsCE"

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

# ----------------- إدارة الجلسات المتعددة وعزل المستخدمين (Multi-Tenant Engine) -----------------
user_states: dict[int, dict] = {}
state_lock = threading.Lock()

def default_user_state() -> dict:
    return {
        "target_url": "https://www.facebook.com/profile.php?id=61595626255487",
        "selected_acc": "all",
        "acc_count_limit": 0,
        "like": True,
        "reaction_type": "like",
        "react_post_index": 1,
        "react_post_url": "",
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
        "is_running": False
    }

def get_user_state(user_id: int) -> dict:
    with state_lock:
        if user_id not in user_states:
            user_states[user_id] = default_user_state()
        return user_states[user_id]

# ----------------- بوابة التحقق الصارمة من الوصول (Strict Access Gate) -----------------

def check_user_access_gate(user, chat_id: int) -> bool:
    """
    بوابة الأمان والتحقق الصارمة:
    1. المطور الأكبر يمر فوراً.
    2. أي مستخدم جديد يُسجل كـ 'pending' ويُرسل إشعار فوري للمطور للموافقة عليه أو حظره.
    3. يمنع أي مستخدم غير معتمد من لمس أي ميزة.
    """
    user_id = user.id
    full_name = f"{user.first_name or ''} {user.last_name or ''}".strip()
    username = user.username or ""

    u_data, is_new = register_or_update_user(user_id, full_name, username)

    if is_super_admin(user_id):
        return True

    if is_new:
        # إشعار المطور الرئيسي فوراً عبر تلغرام
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("✅ موافقة وتفعيل", callback_data=f"gate_app_{user_id}"),
            types.InlineKeyboardButton("🚫 رفض وحظر نهائي", callback_data=f"gate_ban_{user_id}")
        )
        alert_text = (
            "🚨 <b>رادار الأمان: مستخدم جديد دخل للبوت ويطلب الإذن!</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 <b>الاسم:</b> {full_name}\n"
            f"🆔 <b>الآيدي:</b> <code>{user_id}</code>\n"
            f"🌐 <b>المعرف:</b> @{username}\n"
            f"📅 <b>التوقيت:</b> {datetime.now().strftime('%Y-%m-%d %I:%M %p')}\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "⚠️ <b>المستخدم محجوب تماماً الآن حتى تقرر:</b>"
        )
        try:
            bot.send_message(SUPER_ADMIN_ID, alert_text, reply_markup=markup)
        except Exception:
            pass

        bot.send_message(
            chat_id,
            "🔒 <b>منظومة FB Operator المشفرة | الوصول مقفل</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "⚠️ <b>تنبيه أمني:</b> لا يمكن لأي شخص استخدام هذا البوت إلا بعد اعتماده رسمياً من قبل المطور الرئيسي ومنحه الصلاحيات.\n\n"
            "📩 <b>تم إرسال طلب انضمامك للمطور الرئيسي للمراجعة.</b>\n"
            "يرجى الانتظار ريثما تتم مراجعة حسابك والموافقة عليك."
        )
        return False

    status = u_data.get("status", "pending")
    if status == "pending":
        bot.send_message(
            chat_id,
            "⏳ <b>طلبك لا يزال قيد المراجعة لدى المطور الرئيسي.</b>\n"
            "سيتم إشعارك فور الموافقة عليك وتحديد الصلاحيات المسموحة لك."
        )
        return False

    if status == "banned":
        bot.send_message(
            chat_id,
            "⛔ <b>تم حظر وصولك إلى هذه المنظومة بشكل دائم من قبل المطور الرئيسي.</b>"
        )
        return False

    return True

# ----------------- لوحات المفاتيح والأزرار التفاعلية -----------------

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

def get_main_dashboard_markup(user_id: int) -> types.InlineKeyboardMarkup:
    markup = types.InlineKeyboardMarkup(row_width=2)
    accs = load_accounts()
    st = get_user_state(user_id)

    # 1. السطر الأول: الحساب المنفذ + تعديل الرابط المستهدف
    sel_acc_name = "جميع الحسابات (All)"
    if st["selected_acc"] != "all":
        matched = next((a for a in accs if a["id"] == st["selected_acc"]), None)
        if matched:
            sel_acc_name = f"{matched['name']}"

    btn_acc = types.InlineKeyboardButton(f"👤 المنفذ: {sel_acc_name}", callback_data="menu_select_acc")
    btn_url = types.InlineKeyboardButton("🔗 تعديل الرابط المستهدف", callback_data="menu_set_url")
    markup.row(btn_acc, btn_url)

    # 2. السطر الثاني: معالج التفاعلات ومعالج التعليقات
    like_st = "✅" if st["like"] else "❌"
    react_lbl = REACTION_ICONS.get(st["reaction_type"], "👍 إعجاب")
    btn_react = types.InlineKeyboardButton(f"{react_lbl} [{like_st}] (منشور {st['react_post_index']})", callback_data="menu_wizard_react")

    cmt_st = "✅" if st["comment"] else "❌"
    btn_comment = types.InlineKeyboardButton(f"💬 تعليق [{cmt_st}] (منشور {st['comment_post_index']})", callback_data="menu_wizard_comment")
    markup.row(btn_react)
    markup.row(btn_comment)

    # 3. السطر الثالث: التفاعل والرد على تعليق محدد
    cmt_int_tag = "✅ نشط" if st["interact_cmt"] else "❌ معطل"
    markup.row(
        types.InlineKeyboardButton(f"🎯 تفاعل/رد على تعليق محدد [{cmt_int_tag}]", callback_data="menu_cmt_interact")
    )

    # 4. السطر الرابع: طلب الصداقة والمتابعة
    fr_tag = "✅" if st["friend"] else "❌"
    fl_tag = "✅" if st["follow"] else "❌"
    markup.row(
        types.InlineKeyboardButton(f"➕ طلب صداقة [{fr_tag}]", callback_data="toggle_friend"),
        types.InlineKeyboardButton(f"🔔 متابعة [{fl_tag}]", callback_data="toggle_follow")
    )

    # 5. السطر الخامس: ميزات الإلغاء والتراجع
    cfr_tag = "✅" if st["cancel_friend"] else "❌"
    unfl_tag = "✅" if st["unfollow"] else "❌"
    markup.row(
        types.InlineKeyboardButton(f"❌ إلغاء طلب الصداقة [{cfr_tag}]", callback_data="toggle_cancel_friend"),
        types.InlineKeyboardButton(f"🔕 إلغاء المتابعة [{unfl_tag}]", callback_data="toggle_unfollow")
    )

    # 6. السطر السادس: رسائل الماسنجر
    msg_tag = "✅ نشط" if st["message"] else "❌ معطل"
    markup.row(
        types.InlineKeyboardButton(f"✉️ رسالة خاصة [{msg_tag}]", callback_data="toggle_message")
    )

    # 7. السطر السابع: البلاغات والحظر (إذا كان مصرحاً له)
    if has_permission(user_id, "can_report"):
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

    # 8. السطر الثامن: إدارة الحسابات وفحص الجلسات
    markup.row(
        types.InlineKeyboardButton(f"👥 إدارة الحسابات ({len(accs)})", callback_data="menu_manage_accs"),
        types.InlineKeyboardButton("🔄 فحص الجلسات", callback_data="act_check_sessions")
    )

    # 9. الأزرار الخارقة الخاصة بالمطور الأكبر فقط: رادار المراقبة الشامل ولوحة التحكم
    if is_super_admin(user_id):
        all_users = load_users()
        user_count = len(all_users) - 1
        markup.row(
            types.InlineKeyboardButton(f"🛰️ رادار مراقبة المستخدمين والحسابات ({user_count})", callback_data="menu_surveillance_radar")
        )
        markup.row(
            types.InlineKeyboardButton("🌐 لوحة التحكم التفاعلية السحابية (Web Dashboard)", url="https://github.com/labib7654/fb-operator-bot/actions")
        )

    # 10. زر الإطلاق الميداني الكبير
    markup.row(
        types.InlineKeyboardButton("🚀 بدء تنفيذ المهام بالخلفية الآن 🚀", callback_data="action_launch")
    )

    return markup

def get_dashboard_text(user_id: int) -> str:
    accs = load_accounts()
    active_count = sum(1 for a in accs if "نشط" in a.get("status", ""))
    role_title = "👑 المطور الرئيسي (Super Admin)" if is_super_admin(user_id) else "🛡️ عضو معتمد (Approved User)"
    st = get_user_state(user_id)

    react_info = REACTION_ICONS.get(st["reaction_type"], "👍 إعجاب")
    post_info = f"المنشور رقم {st['react_post_index']}" if not st["react_post_url"] else "رابط مخصص"

    txt = (
        "⚡ <b>منظومة التحكم والحماية FB Operator | السحاب 24/7</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>رتبتك:</b> {role_title}\n"
        f"📊 <b>إحصائيات الحسابات:</b> {len(accs)} حساب ({active_count} نشط ومسجل)\n"
        f"🎯 <b>الرابط المستهدف:</b> <code>{st['target_url'][:48]}...</code>\n"
        f"💖 <b>التفاعل المحدد:</b> {react_info} ({post_info})\n"
        f"💬 <b>التعليق المجهز:</b> <i>'{st['comment_text'][:30]}...'</i> (منشور {st['comment_post_index']})\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "👇 <b>حدد العمليات المطلوبة أو ادخل للمعالجات بنقرة زر أدناه:</b>"
    )
    return txt

# ----------------- معالجات الأوامر والقوائم -----------------

@bot.message_handler(commands=['start', 'menu'])
def cmd_start(message: types.Message):
    if not check_user_access_gate(message.from_user, message.chat.id):
        return

    st = get_user_state(message.from_user.id)
    st["input_mode"] = None
    bot.send_message(
        message.chat.id,
        get_dashboard_text(message.from_user.id),
        reply_markup=get_main_dashboard_markup(message.from_user.id)
    )

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call: types.CallbackQuery):
    user_id = call.from_user.id
    data = call.data

    # 1. فحص طلبات البوابة (موافقة / حظر فوري من المطور)
    if data.startswith("gate_app_"):
        if not is_super_admin(user_id):
            bot.answer_callback_query(call.id, "⛔ خاص بالمطور الأكبر فقط.", show_alert=True)
            return
        target_uid = int(data.replace("gate_app_", ""))
        approve_user(target_uid)
        bot.answer_callback_query(call.id, "✅ تمت الموافقة على المستخدم بنجاح!", show_alert=True)
        bot.edit_message_text(
            f"✅ <b>تم اعتماد المستخدم (<code>{target_uid}</code>) بنجاح!</b>\nيمكنك الآن تخصيص صلاحياته من رادار المراقبة.",
            call.message.chat.id, call.message.message_id
        )
        try:
            bot.send_message(target_uid, "🎉 <b>تهانينا! تمت الموافقة على حسابك من قبل المطور الرئيسي.</b>\nأرسل /start الآن لفتح لوحة التحكم!")
        except Exception:
            pass
        return

    elif data.startswith("gate_ban_"):
        if not is_super_admin(user_id):
            bot.answer_callback_query(call.id, "⛔ خاص بالمطور الأكبر فقط.", show_alert=True)
            return
        target_uid = int(data.replace("gate_ban_", ""))
        ban_user(target_uid)
        bot.answer_callback_query(call.id, "🚫 تم حظر المستخدم بنجاح!", show_alert=True)
        bot.edit_message_text(
            f"🚫 <b>تم حظر المستخدم (<code>{target_uid}</code>) ومنعه نهائياً.</b>",
            call.message.chat.id, call.message.message_id
        )
        return

    # فحص صلاحية الدخول العامة
    if not check_user_access_gate(call.from_user, call.message.chat.id):
        bot.answer_callback_query(call.id, "⛔ غير مصرح لك.", show_alert=True)
        return

    st = get_user_state(user_id)

    # ----------------- رادار المراقبة الشامل للمطور الأكبر -----------------
    if data == "menu_surveillance_radar":
        if not is_super_admin(user_id):
            bot.answer_callback_query(call.id, "⛔ خاص بالمطور الأكبر فقط.", show_alert=True)
            return

        users = load_users()
        accs = load_accounts()
        markup = types.InlineKeyboardMarkup(row_width=1)

        pending_users = [u for u in users.values() if u.get("status") == "pending"]
        approved_users = [u for u in users.values() if u.get("status") == "approved" and str(u["id"]) != str(SUPER_ADMIN_ID)]
        banned_users = [u for u in users.values() if u.get("status") == "banned"]

        # طلبات معلقة تنتظر الموافقة
        if pending_users:
            markup.add(types.InlineKeyboardButton("⏳ --- طلبات انضمام قيد الانتظار ---", callback_data="noop"))
            for pu in pending_users:
                markup.row(
                    types.InlineKeyboardButton(f"👤 {pu['name']} (@{pu.get('username','')})", callback_data=f"surv_user_{pu['id']}"),
                    types.InlineKeyboardButton("✅ قبول", callback_data=f"gate_app_{pu['id']}"),
                    types.InlineKeyboardButton("🚫 حظر", callback_data=f"gate_ban_{pu['id']}")
                )

        # المستخدمون المعتمدون
        markup.add(types.InlineKeyboardButton("👥 --- المستخدمون المعتمدون وسجلاتهم ---", callback_data="noop"))
        for u in approved_users:
            u_accs = get_accounts_by_owner(u["id"])
            u_name = u.get("name", f"مستخدم_{u['id']}")
            u_user = f"@{u.get('username')}" if u.get("username") else "بدون معرف"
            markup.add(types.InlineKeyboardButton(f"👤 {u_name} ({u_user}) | {len(u_accs)} حسابات", callback_data=f"surv_user_{u['id']}"))

        # المستخدمون المحظورون
        if banned_users:
            markup.add(types.InlineKeyboardButton("🚫 --- المستخدمون المحظورون ---", callback_data="noop"))
            for bu in banned_users:
                markup.add(types.InlineKeyboardButton(f"🚫 {bu['name']} (محظور)", callback_data=f"surv_user_{bu['id']}"))

        markup.add(types.InlineKeyboardButton("🔙 العودة للوحة الرئيسية", callback_data="back_to_main"))

        txt = (
            "🛰️ <b>رادار المراقبة الشامل لجميع المستخدمين والحسابات:</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"👑 <b>المطور الرئيسي:</b> <code>{SUPER_ADMIN_ID}</code>\n"
            f"👥 <b>إجمالي المستخدمين بالرادار:</b> {len(users) - 1}\n"
            f"🟢 <b>المعتمدون:</b> {len(approved_users)} | ⏳ <b>المعلقون:</b> {len(pending_users)} | 🚫 <b>المحظورون:</b> {len(banned_users)}\n"
            f"📊 <b>إجمالي حسابات فيسبوك بالنظام:</b> {len(accs)} حساب\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "👇 <b>انقر على أي مستخدم لعرض بطاقة المراقبة الشاملة بحساباته وكلمات سره:</b>"
        )
        bot.edit_message_text(txt, call.message.chat.id, call.message.message_id, reply_markup=markup)

    elif data.startswith("surv_user_"):
        if not is_super_admin(user_id):
            return
        t_id = int(data.replace("surv_user_", ""))
        users = load_users()
        u = users.get(str(t_id))
        if not u:
            bot.answer_callback_query(call.id, "المستخدم غير موجود.", show_alert=True)
            return

        u_accs = get_accounts_by_owner(t_id)
        p = u.get("permissions", {})

        markup = types.InlineKeyboardMarkup(row_width=2)
        # أزرار الصلاحيات بنقرة زر
        markup.add(
            types.InlineKeyboardButton(f"🚀 تنفيذ: {'✅' if p.get('can_execute') else '❌'}", callback_data=f"surv_perm_{t_id}_can_execute"),
            types.InlineKeyboardButton(f"👤 حسابات: {'✅' if p.get('can_add_accounts') else '❌'}", callback_data=f"surv_perm_{t_id}_can_add_accounts")
        )
        markup.add(
            types.InlineKeyboardButton(f"🛡️ بلاغات: {'✅' if p.get('can_report') else '❌'}", callback_data=f"surv_perm_{t_id}_can_report"),
            types.InlineKeyboardButton(f"💬 تعليقات: {'✅' if p.get('can_interact_comments') else '❌'}", callback_data=f"surv_perm_{t_id}_can_interact_comments")
        )

        # الحظر والحذف
        if u.get("status") == "banned":
            markup.row(types.InlineKeyboardButton("✅ فك الحظر عن المستخدم", callback_data=f"surv_unban_{t_id}"))
        else:
            markup.row(types.InlineKeyboardButton("🚫 حظر هذا المستخدم", callback_data=f"surv_ban_{t_id}"))

        markup.row(
            types.InlineKeyboardButton("🗑️ حذف المستخدم وكافة حساباته", callback_data=f"surv_del_{t_id}"),
            types.InlineKeyboardButton("🔙 رجوع للرادار", callback_data="menu_surveillance_radar")
        )

        st_map = {"approved": "معتمد ومصرح ✅", "pending": "قيد المراجعة ⏳", "banned": "محظور نهائياً 🚫"}
        txt = (
            f"👤 <b>بطاقة المراقبة الشاملة: {u.get('name')}</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"🆔 <b>الآيدي:</b> <code>{t_id}</code>\n"
            f"🌐 <b>المعرف:</b> @{u.get('username') or 'بدون معرف'}\n"
            f"🛡️ <b>الحالة:</b> {st_map.get(u.get('status'), u.get('status'))}\n"
            f"📅 <b>أول دخول:</b> {u.get('first_seen')}\n"
            f"⏱️ <b>آخر تواجد ونشاط:</b> {u.get('last_seen')}\n"
            f"🔄 <b>مرات الدخول:</b> {u.get('total_logins', 1)} مرة\n"
            f"⚡ <b>العمليات المنفذة:</b> {u.get('operations_count', 0)} عملية\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"🔑 <b>الحسابات التي أضافها ({len(u_accs)} حساب):</b>\n"
        )

        if u_accs:
            for idx, a in enumerate(u_accs, 1):
                txt += (
                    f"<b>{idx}. {a['name']}</b> (<code>{a['id']}</code>)\n"
                    f"   📧 <code>{a['email']}</code>\n"
                    f"   🔑 كلمة السر: <code>{a['password']}</code>\n"
                    f"   📊 الحالة: {a.get('status', 'غير معروف')} | 📅 أضيف: {a.get('added_at', 'سابقاً')}\n\n"
                )
        else:
            txt += "<i>لم يقم هذا المستخدم بإضافة أي حسابات بعد.</i>\n\n"

        txt += "👇 <b>تحكم بصلاحيات وحالة المستخدم فوراً من الأزرار:</b>"
        bot.edit_message_text(txt, call.message.chat.id, call.message.message_id, reply_markup=markup)

    elif data.startswith("surv_perm_"):
        if not is_super_admin(user_id):
            return
        parts = data.split("_")
        t_id = int(parts[2])
        perm_key = "_".join(parts[3:])
        toggle_user_permission(t_id, perm_key)
        bot.answer_callback_query(call.id, "تم تحديث الصلاحية فوراً!")
        call.data = f"surv_user_{t_id}"
        handle_callbacks(call)

    elif data.startswith("surv_ban_"):
        if not is_super_admin(user_id):
            return
        t_id = int(data.replace("surv_ban_", ""))
        ban_user(t_id)
        bot.answer_callback_query(call.id, "تم حظر المستخدم بنجاح!", show_alert=True)
        call.data = f"surv_user_{t_id}"
        handle_callbacks(call)

    elif data.startswith("surv_unban_"):
        if not is_super_admin(user_id):
            return
        t_id = int(data.replace("surv_unban_", ""))
        unban_user(t_id)
        bot.answer_callback_query(call.id, "تم فك الحظر عن المستخدم بنجاح!", show_alert=True)
        call.data = f"surv_user_{t_id}"
        handle_callbacks(call)

    elif data.startswith("surv_del_"):
        if not is_super_admin(user_id):
            return
        t_id = int(data.replace("surv_del_", ""))
        acc_deleted = delete_accounts_by_owner(t_id)
        delete_user_and_data(t_id)
        bot.answer_callback_query(call.id, f"تم حذف المستخدم ومسح {acc_deleted} حساب تابعة له!", show_alert=True)
        call.data = "menu_surveillance_radar"
        handle_callbacks(call)

    # ----------------- معالجات التفاعلات والتعليقات -----------------
    elif data == "menu_wizard_react":
        markup = types.InlineKeyboardMarkup(row_width=3)
        r_btns = [
            types.InlineKeyboardButton("👍 Like", callback_data="set_react_like"),
            types.InlineKeyboardButton("❤️ Love", callback_data="set_react_love"),
            types.InlineKeyboardButton("🤗 Care", callback_data="set_react_care")
        ]
        markup.row(*r_btns)
        r_btns2 = [
            types.InlineKeyboardButton("😂 Haha", callback_data="set_react_haha"),
            types.InlineKeyboardButton("😮 Wow", callback_data="set_react_wow"),
            types.InlineKeyboardButton("😢 Sad", callback_data="set_react_sad")
        ]
        markup.row(*r_btns2)
        markup.row(
            types.InlineKeyboardButton("😡 Angry", callback_data="set_react_angry"),
            types.InlineKeyboardButton("👎 Unlike (إلغاء الإعجاب)", callback_data="set_react_unlike")
        )

        p_row = [
            types.InlineKeyboardButton("🥇 الأول", callback_data="set_react_post_1"),
            types.InlineKeyboardButton("🥈 الثاني", callback_data="set_react_post_2"),
            types.InlineKeyboardButton("🥉 الثالث", callback_data="set_react_post_3"),
            types.InlineKeyboardButton("🔢 مخصص", callback_data="set_react_post_custom")
        ]
        markup.row(*p_row)

        markup.row(
            types.InlineKeyboardButton(f"الحالة: [{'مفعل ✅' if st['like'] else 'معطل ❌'}]", callback_data="toggle_react_active")
        )
        markup.row(types.InlineKeyboardButton("🔙 العودة للوحة التحكم", callback_data="back_to_main"))

        curr_react = REACTION_ICONS.get(st["reaction_type"], "👍 إعجاب")
        bot.edit_message_text(
            f"💖 <b>معالج التفاعلات والإعجابات المتطور:</b>\n\n"
            f"• <b>التفاعل الحالي:</b> {curr_react}\n"
            f"• <b>المنشور المستهدف:</b> منشور رقم {st['react_post_index']}\n"
            f"• <b>الحالة:</b> {'مفعل ✅' if st['like'] else 'معطل ❌'}\n\n"
            f"اختر التفاعل والمنشور المطلوب بنقرة زر:",
            call.message.chat.id, call.message.message_id, reply_markup=markup
        )

    elif data.startswith("set_react_post_"):
        val = data.replace("set_react_post_", "")
        if val == "custom":
            st["input_mode"] = "waiting_react_post_num"
            bot.send_message(call.message.chat.id, "🔢 <b>أرسل الآن رقم المنشور المستهدف للتفاعل (مثال: 4 أو 5):</b>")
        else:
            st["react_post_index"] = int(val)
            bot.answer_callback_query(call.id, f"تم تحديد المنشور رقم {val}")
            call.data = "menu_wizard_react"
            handle_callbacks(call)

    elif data.startswith("set_react_"):
        r_type = data.replace("set_react_", "")
        st["reaction_type"] = r_type
        st["like"] = True
        bot.answer_callback_query(call.id, f"تم اختيار: {REACTION_ICONS.get(r_type, r_type)}")
        call.data = "menu_wizard_react"
        handle_callbacks(call)

    elif data == "toggle_react_active":
        st["like"] = not st["like"]
        bot.answer_callback_query(call.id, f"التفاعل: {'مفعل ✅' if st['like'] else 'معطل ❌'}")
        call.data = "menu_wizard_react"
        handle_callbacks(call)

    # معالج التعليقات الذكي
    elif data == "menu_wizard_comment":
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.row(types.InlineKeyboardButton("✏️ كتابة/تعديل نص التعليق", callback_data="edit_comment_text"))

        p_row = [
            types.InlineKeyboardButton("🥇 الأول", callback_data="set_cmt_post_1"),
            types.InlineKeyboardButton("🥈 الثاني", callback_data="set_cmt_post_2"),
            types.InlineKeyboardButton("🥉 الثالث", callback_data="set_cmt_post_3")
        ]
        markup.row(*p_row)
        markup.row(
            types.InlineKeyboardButton("🔢 رقم مخصص", callback_data="set_cmt_post_custom"),
            types.InlineKeyboardButton("🔗 رابط منشور مباشر", callback_data="set_cmt_post_url")
        )

        acc_row = [
            types.InlineKeyboardButton("🔥 جميع الحسابات", callback_data="set_cmt_acc_0"),
            types.InlineKeyboardButton("1️⃣ حساب واحد", callback_data="set_cmt_acc_1"),
            types.InlineKeyboardButton("2️⃣ حسابين", callback_data="set_cmt_acc_2")
        ]
        markup.row(*acc_row)

        markup.row(
            types.InlineKeyboardButton(f"الحالة: [{'مفعل ✅' if st['comment'] else 'معطل ❌'}]", callback_data="toggle_comment_active")
        )
        markup.row(types.InlineKeyboardButton("🔙 العودة للوحة التحكم", callback_data="back_to_main"))

        post_desc = f"منشور رقم {st['comment_post_index']}" if not st["comment_post_url"] else f"رابط مباشر ({st['comment_post_url'][:25]}...)"
        acc_desc = "جميع الحسابات" if st["comment_acc_count"] == 0 else f"{st['comment_acc_count']} حسابات"

        bot.edit_message_text(
            f"💬 <b>معالج التعليقات واصطياد المنشورات بدقة:</b>\n\n"
            f"📝 <b>نص التعليق:</b> <i>'{st['comment_text']}'</i>\n"
            f"🎯 <b>المنشور المستهدف:</b> {post_desc}\n"
            f"👥 <b>عدد الحسابات:</b> {acc_desc}\n"
            f"🔘 <b>الحالة:</b> {'مفعل ✅' if st['comment'] else 'معطل ❌'}\n\n"
            f"حدد خياراتك بالأسفل:",
            call.message.chat.id, call.message.message_id, reply_markup=markup
        )

    elif data == "edit_comment_text":
        st["input_mode"] = "waiting_comment_text"
        bot.send_message(call.message.chat.id, "💬 <b>أرسل الآن نص التعليق الجديد الذي ترغب بنشره:</b>")

    elif data.startswith("set_cmt_post_"):
        val = data.replace("set_cmt_post_", "")
        if val == "custom":
            st["input_mode"] = "waiting_cmt_post_num"
            bot.send_message(call.message.chat.id, "🔢 <b>أرسل الآن رقم المنشور المطلوب التعليق عليه (مثال: 4 أو 5):</b>")
        elif val == "url":
            st["input_mode"] = "waiting_cmt_post_url"
            bot.send_message(call.message.chat.id, "🔗 <b>أرسل رابط المنشور المباشر الذي تريد التعليق عليه:</b>")
        else:
            st["comment_post_index"] = int(val)
            st["comment_post_url"] = ""
            bot.answer_callback_query(call.id, f"تم تحديد المنشور رقم {val}")
            call.data = "menu_wizard_comment"
            handle_callbacks(call)

    elif data.startswith("set_cmt_acc_"):
        val = int(data.replace("set_cmt_acc_", ""))
        st["comment_acc_count"] = val
        bot.answer_callback_query(call.id, f"تم تحديد عدد الحسابات: {'الكل' if val == 0 else val}")
        call.data = "menu_wizard_comment"
        handle_callbacks(call)

    elif data == "toggle_comment_active":
        st["comment"] = not st["comment"]
        bot.answer_callback_query(call.id, f"التعليق: {'مفعل ✅' if st['comment'] else 'معطل ❌'}")
        call.data = "menu_wizard_comment"
        handle_callbacks(call)

    # تبديل العمليات بنقرة واحدة
    elif data == "toggle_friend":
        st["friend"] = not st["friend"]
        if st["friend"]:
            st["cancel_friend"] = False
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=get_main_dashboard_markup(user_id))
        bot.answer_callback_query(call.id, f"طلب الصداقة: {'مفعل ✅' if st['friend'] else 'معطل ❌'}")

    elif data == "toggle_cancel_friend":
        st["cancel_friend"] = not st["cancel_friend"]
        if st["cancel_friend"]:
            st["friend"] = False
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=get_main_dashboard_markup(user_id))
        bot.answer_callback_query(call.id, f"إلغاء طلب الصداقة: {'مفعل ✅' if st['cancel_friend'] else 'معطل ❌'}")

    elif data == "toggle_follow":
        st["follow"] = not st["follow"]
        if st["follow"]:
            st["unfollow"] = False
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=get_main_dashboard_markup(user_id))
        bot.answer_callback_query(call.id, f"المتابعة: {'مفعل ✅' if st['follow'] else 'معطل ❌'}")

    elif data == "toggle_unfollow":
        st["unfollow"] = not st["unfollow"]
        if st["unfollow"]:
            st["follow"] = False
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=get_main_dashboard_markup(user_id))
        bot.answer_callback_query(call.id, f"إلغاء المتابعة: {'مفعل ✅' if st['unfollow'] else 'معطل ❌'}")

    elif data == "toggle_message":
        st["message"] = not st["message"]
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=get_main_dashboard_markup(user_id))
        bot.answer_callback_query(call.id, f"الرسائل الخاصة: {'مفعل ✅' if st['message'] else 'معطل ❌'}")

    elif data == "toggle_rep_post":
        if not has_permission(user_id, "can_report"):
            bot.answer_callback_query(call.id, "⛔ ليس لديك صلاحية تقديم البلاغات.", show_alert=True)
            return
        st["report_post"] = not st["report_post"]
        if st["report_post"]:
            st["report_profile"] = False
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=get_main_dashboard_markup(user_id))
        bot.answer_callback_query(call.id, f"بلاغ المنشور: {'مفعل ✅' if st['report_post'] else 'معطل ❌'}")

    elif data == "toggle_rep_profile":
        if not has_permission(user_id, "can_report"):
            bot.answer_callback_query(call.id, "⛔ ليس لديك صلاحية تقديم البلاغات.", show_alert=True)
            return
        st["report_profile"] = not st["report_profile"]
        if st["report_profile"]:
            st["report_post"] = False
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=get_main_dashboard_markup(user_id))
        bot.answer_callback_query(call.id, f"بلاغ الحساب: {'مفعل ✅' if st['report_profile'] else 'معطل ❌'}")

    elif data == "toggle_block":
        if not has_permission(user_id, "can_report"):
            bot.answer_callback_query(call.id, "⛔ ليس لديك صلاحية الحظر.", show_alert=True)
            return
        st["block"] = not st["block"]
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=get_main_dashboard_markup(user_id))
        bot.answer_callback_query(call.id, f"حظر الحساب: {'مفعل ✅' if st['block'] else 'معطل ❌'}")

    elif data == "menu_set_url":
        st["input_mode"] = "waiting_url"
        bot.send_message(
            call.message.chat.id,
            "🔗 <b>أرسل الآن الرابط المستهدف الجديد (منشور أو حساب فيسبوك):</b>\n\n"
            "<i>مثال: https://www.facebook.com/profile.php?id=...</i>"
        )

    elif data == "menu_select_acc":
        accs = load_accounts()
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(types.InlineKeyboardButton("🚀 (All) تنفيذ بجميع الحسابات", callback_data="sel_acc_all"))
        for a in accs:
            st_icon = "🟢" if "نشط" in a.get("status", "") else "🔴"
            markup.add(types.InlineKeyboardButton(f"{st_icon} {a['name']}", callback_data=f"sel_acc_{a['id']}"))
        markup.add(types.InlineKeyboardButton("🔙 رجوع للرئيسية", callback_data="back_to_main"))
        bot.edit_message_text(
            "👤 <b>اختر الحساب المطلوب لتنفيذ العمليات:</b>",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )

    elif data.startswith("sel_acc_"):
        chosen = data.replace("sel_acc_", "")
        st["selected_acc"] = chosen
        bot.answer_callback_query(call.id, "تم اختيار الحساب بنجاح!")
        bot.edit_message_text(
            get_dashboard_text(user_id),
            call.message.chat.id,
            call.message.message_id,
            reply_markup=get_main_dashboard_markup(user_id)
        )

    elif data == "menu_cmt_interact":
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

        bot.edit_message_text(
            "🎯 <b>إعدادات التفاعل والرد على تعليق محدد:</b>\n"
            "يمكنك استهداف التعليق بالاسم أو بنص الكلمة واختيار أي نوع رياكشن وكتابة الرد المخصص له.",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )

    elif data == "toggle_cmt_int_active":
        st["interact_cmt"] = not st["interact_cmt"]
        bot.answer_callback_query(call.id, f"الميزة: {'مفعلة ✅' if st['interact_cmt'] else 'معطلة ❌'}")
        call.data = "menu_cmt_interact"
        handle_callbacks(call)

    elif data == "cycle_cmt_mode":
        modes = ["first", "author", "keyword", "index"]
        curr_idx = modes.index(st["cmt_target_mode"]) if st["cmt_target_mode"] in modes else 0
        st["cmt_target_mode"] = modes[(curr_idx + 1) % len(modes)]
        call.data = "menu_cmt_interact"
        handle_callbacks(call)

    elif data == "cycle_cmt_reaction":
        reactions = ["like", "love", "care", "haha", "wow", "sad", "angry", "none"]
        curr_idx = reactions.index(st["cmt_reaction"]) if st["cmt_reaction"] in reactions else 0
        st["cmt_reaction"] = reactions[(curr_idx + 1) % len(reactions)]
        call.data = "menu_cmt_interact"
        handle_callbacks(call)

    elif data == "edit_cmt_target_val":
        st["input_mode"] = "waiting_cmt_val"
        bot.send_message(call.message.chat.id, "✏️ <b>أرسل الآن اسم كاتب التعليق، أو الكلمة المفتاحية، أو رقم الترتيب:</b>")

    elif data == "edit_cmt_reply_text":
        st["input_mode"] = "waiting_cmt_reply"
        bot.send_message(call.message.chat.id, "✏️ <b>أرسل الآن نص الرد الذي ترغب بنشره على التعليق:</b>")

    # إدارة الحسابات مع منع التكرار والحذف الفوري
    elif data == "menu_manage_accs":
        accs = load_accounts()
        markup = types.InlineKeyboardMarkup(row_width=2)
        
        for a in accs:
            st_icon = "🟢" if "نشط" in a.get("status", "") else "🔴"
            btn_info = types.InlineKeyboardButton(f"{st_icon} {a['name']}", callback_data=f"sel_acc_{a['id']}")
            btn_del = types.InlineKeyboardButton("🗑️ حذف", callback_data=f"del_acc_{a['id']}")
            markup.row(btn_info, btn_del)

        if has_permission(user_id, "can_add_accounts"):
            markup.row(types.InlineKeyboardButton("➕ إضافة حساب جديد", callback_data="act_add_acc"))
        
        markup.row(types.InlineKeyboardButton("🧹 تنظيف وحذف كافة الحسابات التالفة", callback_data="act_purge_broken"))
        markup.row(
            types.InlineKeyboardButton("🔄 فحص حالة الجلسات", callback_data="act_check_sessions"),
            types.InlineKeyboardButton("🔙 رجوع", callback_data="back_to_main")
        )

        txt = "👥 <b>قائمة وإدارة الحسابات:</b>\n\n"
        for i, a in enumerate(accs, 1):
            st_text = "🟢 نشط ومسجل" if "نشط" in a.get("status", "") else "🔴 يتطلب تسجيل الدخول"
            txt += f"{i}. <b>{a['name']}</b> (<code>{a['id']}</code>)\n   📧 <code>{a['email']}</code> | {st_text}\n"

        if not accs:
            txt += "<i>لا توجد حسابات مسجلة حالياً.</i>"

        bot.edit_message_text(txt, call.message.chat.id, call.message.message_id, reply_markup=markup)

    elif data.startswith("del_acc_"):
        acc_id = data.replace("del_acc_", "")
        if delete_account(acc_id):
            bot.answer_callback_query(call.id, f"تم حذف الحساب {acc_id} وجلسته بنجاح!", show_alert=True)
        else:
            bot.answer_callback_query(call.id, "تعذر حذف الحساب.", show_alert=True)
        call.data = "menu_manage_accs"
        handle_callbacks(call)

    elif data == "act_purge_broken":
        count, purged = purge_broken_accounts()
        if count > 0:
            bot.answer_callback_query(call.id, f"🧹 تم بنجاح حذف {count} حساب تالف وتنظيف ملفاتهم!", show_alert=True)
        else:
            bot.answer_callback_query(call.id, "✨ لا توجد أي حسابات تالفة حالياً، كافة الحسابات نشطة!", show_alert=True)
        call.data = "menu_manage_accs"
        handle_callbacks(call)

    elif data == "act_add_acc":
        if not has_permission(user_id, "can_add_accounts"):
            bot.answer_callback_query(call.id, "⛔ ليس لديك صلاحية إضافة حسابات. اطلب الإذن من المطور الرئيسي.", show_alert=True)
            return
        st["input_mode"] = "add_acc_name"
        st["temp_acc_data"] = {}
        bot.send_message(call.message.chat.id, "➕ <b>أرسل اسم الحساب أولاً (مثال: حسابي الجديد):</b>")

    elif data == "act_check_sessions":
        bot.answer_callback_query(call.id, "🔄 جاري فحص وتحديث جلسات كافة الحسابات...")
        threading.Thread(target=check_all_sessions_worker, args=(call.message.chat.id,), daemon=True).start()

    elif data == "back_to_main":
        bot.edit_message_text(
            get_dashboard_text(user_id),
            call.message.chat.id,
            call.message.message_id,
            reply_markup=get_main_dashboard_markup(user_id)
        )

    # تشغيل العمليات الميدانية بالخلفية
    elif data == "action_launch":
        if not has_permission(user_id, "can_execute"):
            bot.answer_callback_query(call.id, "⛔ ليس لديك صلاحية تنفيذ العمليات. اطلب الإذن من المطور الرئيسي.", show_alert=True)
            return

        if st["is_running"]:
            bot.answer_callback_query(call.id, "⚠️ هناك مهمة قيد التشغيل بالفعل حالياً!", show_alert=True)
            return

        record_user_operation(user_id)
        bot.answer_callback_query(call.id, "🚀 تم استلام الأمر! بدء التنفيذ في الخلفية...")
        threading.Thread(target=execute_mission_worker, args=(call.message.chat.id, user_id), daemon=True).start()

# ----------------- معالجة فحص الجلسات بالخلفية -----------------

def check_all_sessions_worker(chat_id: int):
    status_msg = bot.send_message(chat_id, "⏳ <b>بدء فحص حالة الجلسات لحسابات فيسبوك في المتصفح الخلفي...</b>")
    accs = load_accounts()
    active_cnt = 0
    total = len(accs)

    with sync_playwright() as p:
        for idx, a in enumerate(accs, 1):
            try:
                bot.edit_message_text(
                    f"🔄 <b>جاري فحص الحساب ({idx}/{total}):</b> {a['name']}...",
                    chat_id, status_msg.message_id
                )
                ctx = launch_account_browser(p, a["profile_dir"], visible=False)
                page = ctx.pages[0] if ctx.pages else ctx.new_page()
                page.goto("https://www.facebook.com/", timeout=25000, wait_until="commit")
                human_delay(1.5, 2.5)
                is_logged = check_facebook_login_cookies(ctx)
                ctx.close()

                if is_logged:
                    update_account(a["id"], {"status": "نشط ومسجل"})
                    active_cnt += 1
                else:
                    update_account(a["id"], {"status": "يتطلب تسجيل الدخول"})
            except Exception:
                pass

    bot.edit_message_text(
        f"✅ <b>اكتمل فحص الجلسات بنجاح!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🟢 <b>الحسابات النشطة:</b> {active_cnt}\n"
        f"🔴 <b>بحاجة لتسجيل دخول:</b> {total - active_cnt}\n"
        f"━━━━━━━━━━━━━━━━━━━━",
        chat_id, status_msg.message_id
    )

# ----------------- معالجة مدخلات النصوص التفاعلية -----------------

@bot.message_handler(func=lambda msg: True)
def handle_text_inputs(message: types.Message):
    user_id = message.from_user.id
    if not check_user_access_gate(message.from_user, message.chat.id):
        return

    st = get_user_state(user_id)
    mode = st.get("input_mode")
    text = message.text.strip()

    if mode == "waiting_url":
        st["target_url"] = text
        st["input_mode"] = None
        bot.reply_to(message, f"✅ تم تحديث الرابط بنجاح إلى:\n<code>{text}</code>")
        cmd_start(message)

    elif mode == "waiting_comment_text":
        st["comment_text"] = text
        st["comment"] = True
        st["input_mode"] = None
        bot.reply_to(message, f"✅ تم حفظ وتفعيل نص التعليق بنجاح:\n<i>'{text}'</i>")
        cmd_start(message)

    elif mode == "waiting_cmt_post_num":
        if text.isdigit() and int(text) > 0:
            st["comment_post_index"] = int(text)
            st["comment_post_url"] = ""
            st["input_mode"] = None
            bot.reply_to(message, f"✅ تم تحديد التعليق على المنشور رقم: <b>{text}</b>")
        else:
            bot.reply_to(message, "❌ يرجى إرسال رقم صحيح (مثال: 4).")
        cmd_start(message)

    elif mode == "waiting_cmt_post_url":
        st["comment_post_url"] = text
        st["input_mode"] = None
        bot.reply_to(message, f"✅ تم حفظ رابط المنشور المباشر للتعليق بنجاح:\n<code>{text}</code>")
        cmd_start(message)

    elif mode == "waiting_react_post_num":
        if text.isdigit() and int(text) > 0:
            st["react_post_index"] = int(text)
            st["input_mode"] = None
            bot.reply_to(message, f"✅ تم تحديد التفاعل مع المنشور رقم: <b>{text}</b>")
        else:
            bot.reply_to(message, "❌ يرجى إرسال رقم صحيح (مثال: 4).")
        cmd_start(message)

    elif mode == "waiting_cmt_val":
        st["cmt_target_val"] = text
        st["input_mode"] = None
        bot.reply_to(message, f"✅ تم حفظ هدف التعليق: <b>{text}</b>")
        cmd_start(message)

    elif mode == "waiting_cmt_reply":
        st["cmt_reply"] = text
        st["input_mode"] = None
        bot.reply_to(message, f"✅ تم حفظ نص الرد: <b>{text}</b>")
        cmd_start(message)

    elif mode == "add_acc_name":
        st["temp_acc_data"]["name"] = text
        st["input_mode"] = "add_acc_email"
        bot.reply_to(message, "📧 <b>الآن أرسل البريد الإلكتروني أو رقم الهاتف للحساب:</b>")

    elif mode == "add_acc_email":
        st["temp_acc_data"]["email"] = text
        st["input_mode"] = "add_acc_pass"
        bot.reply_to(message, "🔑 <b>الآن أرسل كلمة المرور الخاصة بالحساب:</b>")

    elif mode == "add_acc_pass":
        st["temp_acc_data"]["pass"] = text
        st["input_mode"] = None
        name = st["temp_acc_data"]["name"]
        email = st["temp_acc_data"]["email"]
        password = st["temp_acc_data"]["pass"]

        # فحص ومنع تكرار الحسابات نهائياً
        acc = add_account(name, email, password, owner_id=user_id)
        if "error" in acc:
            bot.reply_to(message, acc["message"])
            cmd_start(message)
            return

        wait_msg = bot.reply_to(message, f"⏳ <b>جاري فحص وتسجيل دخول الحساب '{name}' وتثبيت الجلسة بالمتصفح الخلفي...</b>")
        threading.Thread(target=async_login_account_worker, args=(message.chat.id, wait_msg.message_id, acc), daemon=True).start()

def async_login_account_worker(chat_id: int, msg_id: int, acc: dict):
    """محرك تسجيل وتثبيت الجلسة بالخلفية للحسابات الجديدة مع التشخيص بلقطة شاشة حية"""
    scratch_dir = WORKSPACE_ROOT / "scratch"
    scratch_dir.mkdir(parents=True, exist_ok=True)
    shot_path = str(scratch_dir / f"login_{acc['id']}.png")

    try:
        with sync_playwright() as p:
            ctx = launch_account_browser(p, acc["profile_dir"], visible=False)
            page = ctx.pages[0] if ctx.pages else ctx.new_page()

            logged = auto_login_facebook(ctx, page, acc["email"], acc["password"])
            
            try:
                page.screenshot(path=shot_path)
            except Exception:
                pass

            page_content = page.content().lower()
            page_url = page.url.lower()

            if logged:
                update_account(acc["id"], {"status": "نشط ومسجل"})
                bot.edit_message_text(
                    f"🎉 <b>تم بنجاح تسجيل دخول وتثبيت جلسة الحساب:</b>\n"
                    f"👤 <b>الاسم:</b> {acc['name']}\n"
                    f"📧 <b>البريد:</b> <code>{acc['email']}</code>\n"
                    f"🛡️ <b>الحالة:</b> نشط ومسجل للأبد بدون الحاجة لكلمة المرور مجدداً!",
                    chat_id, msg_id
                )
                try:
                    with open(shot_path, "rb") as sf:
                        bot.send_photo(chat_id, sf, caption="📸 <b>لقطة شاشة من داخل الحساب بعد تسجيل الدخول بنجاح!</b>")
                except Exception:
                    pass
            else:
                update_account(acc["id"], {"status": "يتطلب تسجيل الدخول"})
                diag_msg = "⚠️ <b>لم تكتمل الجلسة تلقائياً.</b>\n"
                if "arkose" in page_content or "matchkey" in page_content or "captcha" in page_url:
                    diag_msg += "🧩 <b>السبب:</b> فيسبوك يطلب حل لغز أمني تفاعلي (Arkose Labs CAPTCHA) لأن البريد مؤقت أو حساب جديد لمنع الروبوتات."
                elif "checkpoint" in page_url or "two_step_verification" in page_url:
                    diag_msg += "🔐 <b>السبب:</b> فيسبوك يطلب رمز تحقق أمان (2FA) أو تأكيد تسجيل الدخول من جهاز آخر."
                elif "incorrect" in page_content or "غير صحيحة" in page_content:
                    diag_msg += "❌ <b>السبب:</b> كلمة المرور أو البريد الإلكتروني غير صحيحين!"
                else:
                    diag_msg += "🔍 يرجى مراجعة لقطة الشاشة المرفقة لمعرفة ما طلبه فيسبوك تحديداً."

                bot.edit_message_text(diag_msg, chat_id, msg_id)
                try:
                    with open(shot_path, "rb") as sf:
                        bot.send_photo(chat_id, sf, caption="📸 <b>لقطة شاشة حية من متصفح فيسبوك لما ظهر أثناء محاولة الدخول:</b>")
                except Exception:
                    pass

            ctx.close()
    except Exception as e:
        bot.edit_message_text(f"❌ حدث خطأ أثناء التسجيل: {e}", chat_id, msg_id)

# ----------------- المحرك الميداني الرئيسي للتنفيذ بالخلفية -----------------

def execute_mission_worker(chat_id: int, user_id: int):
    """المحرك الميداني الذي ينفذ كافة العمليات بالمتصفح المخفي ويرسل التحديثات الحية ولحظات الإثبات"""
    st = get_user_state(user_id)
    st["is_running"] = True
    status_msg = bot.send_message(chat_id, "⏳ <b>بدء تهيئة محرك العمليات وتشغيل المتصفح بالخلفية...</b>")

    def update_live_status(text: str):
        try:
            bot.edit_message_text(text, chat_id, status_msg.message_id)
        except Exception:
            pass

    try:
        accounts = load_accounts()
        target_accounts = []
        if st["selected_acc"] == "all":
            target_accounts = accounts
        else:
            target_accounts = [a for a in accounts if a["id"] == st["selected_acc"]]

        if not target_accounts:
            update_live_status("❌ <b>خطأ:</b> لم يتم العثور على أي حساب مسجل للتنفيذ.")
            st["is_running"] = False
            return

        actions_done = 0
        total_accounts = len(target_accounts)
        target_url = st["target_url"]

        scratch_dir = WORKSPACE_ROOT / "scratch"
        scratch_dir.mkdir(parents=True, exist_ok=True)

        for idx, acc in enumerate(target_accounts, 1):
            update_live_status(
                f"🚀 <b>جاري تشغيل الحساب ({idx}/{total_accounts}):</b>\n"
                f"👤 <b>{acc['name']}</b> (<code>{acc['email']}</code>)\n"
                f"🔗 <b>الهدف:</b> <code>{target_url[:40]}...</code>"
            )

            with sync_playwright() as p:
                try:
                    ctx = launch_account_browser(p, acc["profile_dir"], visible=False)
                    page = ctx.pages[0] if ctx.pages else ctx.new_page()

                    # 1. التحقق من الجلسة
                    logged = auto_login_facebook(ctx, page, acc.get("email", ""), acc.get("password", ""))
                    if not logged:
                        update_live_status(f"⚠️ <b>الحساب {acc['name']} غير مسجل دخوله، تم تخطيه.</b>")
                        ctx.close()
                        continue

                    # 2. التوجه للهدف
                    if not navigate_to_target(page, target_url):
                        update_live_status(f"❌ <b>تعذر فتح الرابط بالحساب {acc['name']}.</b>")
                        ctx.close()
                        continue

                    # 3. تنفيذ العمليات المختارة
                    if st["friend"]:
                        if send_friend_request(page):
                            actions_done += 1
                            bot.send_message(chat_id, f"➕ <b>تم إرسال طلب صداقة بنجاح بالحساب {acc['name']}.</b>")

                    elif st["cancel_friend"]:
                        if cancel_friend_request(page):
                            actions_done += 1
                            bot.send_message(chat_id, f"❌ <b>تم إلغاء طلب الصداقة المعلق بالحساب {acc['name']}.</b>")

                    if st["follow"]:
                        if follow_profile(page):
                            actions_done += 1
                            bot.send_message(chat_id, f"🔔 <b>تمت متابعة الحساب بنجاح بـ {acc['name']}.</b>")

                    elif st["unfollow"]:
                        if unfollow_profile(page):
                            actions_done += 1
                            bot.send_message(chat_id, f"🔕 <b>تم إلغاء متابعة الحساب بنجاح بـ {acc['name']}.</b>")

                    if st["message"] and st["message_text"]:
                        if send_direct_message(page, st["message_text"], target_url=target_url):
                            actions_done += 1
                            bot.send_message(chat_id, f"✉️ <b>تم إرسال الرسالة الخاصة بالماسنجر بـ {acc['name']}.</b>")

                    # التفاعل المحدد
                    if st["like"]:
                        react_ok = react_to_posts(page, reaction=st["reaction_type"], post_index=st["react_post_index"])
                        if react_ok:
                            actions_done += 1
                            r_name = REACTION_ICONS.get(st["reaction_type"], st["reaction_type"])
                            bot.send_message(chat_id, f"💖 <b>تم وضع التفاعل ({r_name}) بنجاح على المنشور {st['react_post_index']} بـ {acc['name']}.</b>")

                    # التعليق المخصص الذكي
                    if st["comment"] and st["comment_text"]:
                        c_cnt = comment_on_posts(
                            page,
                            comment_text=st["comment_text"],
                            post_index=st["comment_post_index"],
                            post_url=st.get("comment_post_url", "")
                        )
                        if c_cnt > 0:
                            actions_done += c_cnt
                            bot.send_message(chat_id, f"💬 <b>تم نشر التعليق بنجاح بـ {acc['name']}:</b>\n<i>'{st['comment_text']}'</i>")

                    if st["interact_cmt"]:
                        ok_int = interact_with_specific_comment(
                            page,
                            post_index=1,
                            target_mode=st["cmt_target_mode"],
                            target_value=st["cmt_target_val"],
                            reaction=st["cmt_reaction"],
                            reply_text=st["cmt_reply"]
                        )
                        if ok_int:
                            actions_done += 1
                            bot.send_message(chat_id, f"🎯 <b>تم التفاعل والرد على التعليق المحدد بنجاح بـ {acc['name']}!</b>")

                    if st["report_post"]:
                        update_live_status(f"🛡️ <b>جاري تنفيذ معالج البلاغ الرسمي ضد المنشور بـ {acc['name']}...</b>")
                        if report_post(page, reason=st["rep_reason"], victim=st["rep_victim"]):
                            actions_done += 1
                            bot.send_message(chat_id, f"🛡️ <b>تم تأكيد استلام البلاغ رسمياً من فيسبوك ضد المنشور بـ {acc['name']}!</b>")

                    if st["report_profile"]:
                        update_live_status(f"🛡️ <b>جاري تنفيذ معالج البلاغ الرسمي ضد الحساب كاملاً بـ {acc['name']}...</b>")
                        if report_profile(page, reason=st["rep_reason"], victim=st["rep_victim"]):
                            actions_done += 1
                            bot.send_message(chat_id, f"🛡️ <b>تم تأكيد استلام البلاغ رسمياً من فيسبوك ضد الحساب كاملاً بـ {acc['name']}!</b>")

                    if st["block"]:
                        if block_profile(page):
                            actions_done += 1
                            bot.send_message(chat_id, f"🚫 <b>تم حظر الحساب بنجاح بـ {acc['name']}.</b>")

                    try:
                        shot_path = str(scratch_dir / f"bot_shot_{acc['id']}.png")
                        page.screenshot(path=shot_path)
                        with open(shot_path, "rb") as shot_file:
                            bot.send_photo(chat_id, shot_file, caption=f"📸 <b>لقطة شاشة إثبات التنفيذ بالحساب:</b> {acc['name']}")
                    except Exception:
                        pass

                    human_delay(2.0, 3.5)
                    ctx.close()

                except Exception as err:
                    bot.send_message(chat_id, f"❌ <b>خطأ بالحساب {acc['name']}:</b> {err}")

            if idx < total_accounts:
                time.sleep(4)

        final_txt = (
            "🎉 <b>اكتملت كافة العمليات المطلوبة بنجاح!</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"✅ <b>إجمالي الإجراءات المنفذة:</b> {actions_done}\n"
            f"👥 <b>الحسابات المشاركة:</b> {total_accounts}\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "يمكنك إرسال أي مهمة جديدة في أي وقت!"
        )
        update_live_status(final_txt)

    except Exception as e:
        update_live_status(f"❌ حدث خطأ عام أثناء التنفيذ: {e}")
    finally:
        st["is_running"] = False

# ----------------- خادم لوحة التحكم الويبية التفاعلية السحابية (Web Dashboard) -----------------

WEB_DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>FB Operator Command Center | 24/7 Cloud</title>
    <link href="https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;900&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-base: #0a0e17;
            --bg-card: rgba(18, 26, 43, 0.85);
            --border: rgba(0, 240, 255, 0.2);
            --accent-cyan: #00f0ff;
            --accent-green: #00ff88;
            --accent-purple: #9d00ff;
            --text-main: #f0f4f8;
            --text-muted: #8a99ad;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Cairo', sans-serif; }
        body {
            background-color: var(--bg-base);
            color: var(--text-main);
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            align-items: center;
            padding: 20px 15px;
            background-image: radial-gradient(circle at 50% 10%, rgba(0, 240, 255, 0.1) 0%, transparent 60%);
        }
        .container { max-width: 900px; width: 100%; }
        header {
            text-align: center;
            margin-bottom: 25px;
            padding: 20px;
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 16px;
            backdrop-filter: blur(10px);
            box-shadow: 0 8px 32px rgba(0,0,0,0.4);
        }
        h1 { font-size: 26px; font-weight: 900; color: #fff; margin-bottom: 8px; }
        h1 span { color: var(--accent-cyan); text-shadow: 0 0 15px rgba(0,240,255,0.6); }
        .badge {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            background: rgba(0, 255, 136, 0.1);
            color: var(--accent-green);
            padding: 5px 14px;
            border-radius: 20px;
            font-size: 13px;
            font-weight: 700;
            border: 1px solid rgba(0, 255, 136, 0.3);
        }
        .dot { width: 8px; height: 8px; background: var(--accent-green); border-radius: 50%; box-shadow: 0 0 8px var(--accent-green); animation: pulse 1.5s infinite; }
        @keyframes pulse { 0% { opacity: 1; } 50% { opacity: 0.3; } 100% { opacity: 1; } }
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 16px; margin-bottom: 25px; }
        .card {
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 14px;
            padding: 18px;
            backdrop-filter: blur(8px);
            transition: transform 0.2s, border-color 0.2s;
        }
        .card:hover { transform: translateY(-3px); border-color: var(--accent-cyan); }
        .card-title { font-size: 14px; color: var(--text-muted); font-weight: 600; margin-bottom: 6px; }
        .card-value { font-size: 24px; font-weight: 900; color: #fff; }
        .console-box {
            background: #05080f;
            border: 1px solid var(--border);
            border-radius: 14px;
            padding: 20px;
            font-family: monospace;
            font-size: 13px;
            color: #7ef29d;
            height: 220px;
            overflow-y: auto;
            line-height: 1.6;
            margin-bottom: 20px;
            box-shadow: inset 0 2px 10px rgba(0,0,0,0.6);
        }
        .btn-action {
            display: block;
            width: 100%;
            padding: 16px;
            background: linear-gradient(135deg, #00f0ff 0%, #0077ff 100%);
            color: #000;
            font-weight: 900;
            font-size: 17px;
            text-align: center;
            border-radius: 12px;
            text-decoration: none;
            border: none;
            cursor: pointer;
            box-shadow: 0 4px 20px rgba(0, 240, 255, 0.4);
            transition: all 0.2s;
        }
        .btn-action:hover { opacity: 0.9; transform: scale(1.01); }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>⚡ منظومة <span>FB Operator</span> السحابية 24/7</h1>
            <div class="badge"><div class="dot"></div> بيئة الديسكتوب الافتراضية Xvfb 1080p تعمل بأعلى كفاءة</div>
        </header>

        <div class="grid">
            <div class="card">
                <div class="card-title">🛡️ حالة المتصفح السحابي</div>
                <div class="card-value" style="color: var(--accent-cyan);">Google Chrome الرسمي</div>
            </div>
            <div class="card">
                <div class="card-title">🖥️ دقة شاشة العرض</div>
                <div class="card-value" style="color: var(--accent-green);">1920x1080 (24-bit)</div>
            </div>
            <div class="card">
                <div class="card-title">👥 نظام الأمان والوصول</div>
                <div class="card-value" style="color: var(--accent-purple);">Strict Access Gate</div>
            </div>
        </div>

        <div class="console-box">
[SYSTEM 24/7] FB Operator Cloud Bot Initialized Successfully.
[DISPLAY] Xvfb Virtual Framebuffer Display :99 active (1920x1080x24).
[STEALTH] Anti-fingerprint WebGL Intel UHD Graphics & navigator.webdriver spoof injected.
[GATEWAY] Super Admin ID 7411444902 verified with root authority.
[STATUS] Ready to receive automated Facebook actions via Telegram Bot @Labib_Dev_Service_bot.
        </div>

        <a href="https://t.me/Labib_Dev_Service_bot" class="btn-action">📱 فتح البوت والتحكم الكامل في تلغرام</a>
    </div>
</body>
</html>
"""

def start_health_server():
    """خادم ويب خفيف للاستجابة لفحوصات السيرفر وعرض لوحة التحكم التفاعلية WebApp"""
    from http.server import HTTPServer, BaseHTTPRequestHandler
    class HealthHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(WEB_DASHBOARD_HTML.encode('utf-8'))
        def log_message(self, format, *args):
            pass
    try:
        port = int(os.environ.get("PORT", 7860))
        server = HTTPServer(('0.0.0.0', port), HealthHandler)
        server.serve_forever()
    except Exception:
        pass

def run_telegram_bot():
    print("=" * 60)
    print("🚀 بدء تشغيل بوت تلغرام FB Operator في السحاب 24/7...")
    print(f"🤖 معرف البوت: @{bot.get_me().username}")
    print(f"👑 معرف المطور الرئيسي المسؤول: {SUPER_ADMIN_ID}")
    print("=" * 60)
    
    threading.Thread(target=start_health_server, daemon=True).start()
    
    while True:
        try:
            bot.infinity_polling(timeout=25, long_polling_timeout=25)
        except Exception as e:
            print(f"[Bot Warning] خطأ بالاتصال، إعادة المحاولة بعد 5 ثوانٍ: {e}")
            time.sleep(5)

if __name__ == "__main__":
    run_telegram_bot()
