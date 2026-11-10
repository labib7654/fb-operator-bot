"""
بوت تلغرام المتطور للتحكم الكامل بأتمتة حسابات فيسبوك (FB Operator Telegram Bot)
يدعم التحكم الكامل من الهاتف، التنفيذ في الخلفية (Headless)، الأزرار التفاعلية الحديثة، والتقارير المباشرة.
"""

import sys
from pathlib import Path

# ضمان استيراد حزمة fb_operator
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

import os
import time
import threading
import telebot
from telebot import types
from playwright.sync_api import sync_playwright

from fb_operator.account_manager import (
    load_accounts, add_account, update_account, delete_account, save_accounts
)
from fb_operator.browser_manager import (
    launch_account_browser, auto_login_facebook, check_facebook_login_cookies, human_delay
)
from fb_operator.actions import (
    navigate_to_target, like_posts, comment_on_posts,
    send_friend_request, cancel_friend_request, follow_profile,
    send_direct_message, block_profile, report_profile, report_post,
    interact_with_specific_comment
)

BOT_TOKEN = "8798272294:AAEY_LIYnVRIY2T-WUP63duCn5V7VFgGsCE"
ADMIN_ID = 7411444902

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

# حالة المستخدم وإعدادات المهام التفاعلية
user_state = {
    "target_url": "https://www.facebook.com/profile.php?id=61595626255487",
    "selected_acc": "all",  # "all" أو معرف حساب محدد مثل "acc_4"
    "like": True,
    "like_scope": "latest",  # "latest", "2", "all"
    "comment": False,
    "comment_text": "بالتوفيق يا غالي",
    "interact_cmt": False,
    "cmt_target_mode": "first",  # "first", "author", "keyword", "index"
    "cmt_target_val": "Marwan",
    "cmt_reaction": "like",      # "like", "love", "care", "haha", "wow", "sad", "angry", "none"
    "cmt_reply": "صحيح كلامك 100%",
    "friend": False,
    "cancel_friend": False,
    "follow": False,
    "message": False,
    "message_text": "السلام عليكم",
    "report_post": False,
    "report_profile": False,
    "rep_reason": "harassment",
    "rep_victim": "me",
    "block": False,
    "loops": 1,
    "input_mode": None,          # "waiting_url", "waiting_comment", "waiting_msg", "add_acc_name", "add_acc_email", "add_acc_pass", etc.
    "temp_acc_data": {},
    "is_running": False
}

def is_admin(user_id: int) -> bool:
    return str(user_id) == str(ADMIN_ID)

# ----------------- لوحات المفاتيح والأزرار التفاعلية المتطورة -----------------

def get_main_dashboard_markup() -> types.InlineKeyboardMarkup:
    """بناء لوحة التحكم الرئيسية بأزرار تفاعلية مصفوفة بأناقة وتحديث فوري"""
    markup = types.InlineKeyboardMarkup(row_width=2)

    # 1. حالة الحساب المستهدف وزر تغييره
    accs = load_accounts()
    sel_acc_name = "جميع الحسابات (All)"
    if user_state["selected_acc"] != "all":
        matched = next((a for a in accs if a["id"] == user_state["selected_acc"]), None)
        if matched:
            sel_acc_name = f"{matched['name']}"

    btn_acc = types.InlineKeyboardButton(f"👤 المنفذ: {sel_acc_name}", callback_data="menu_select_acc")
    btn_url = types.InlineKeyboardButton("🔗 تعديل الرابط المستهدف", callback_data="menu_set_url")
    markup.row(btn_acc, btn_url)

    # 2. أزرار المهام التفاعلية مع مؤشرات واضحة [✅ ON] و [❌ OFF]
    like_tag = "✅ ON" if user_state["like"] else "❌ OFF"
    cmt_tag = "✅ ON" if user_state["comment"] else "❌ OFF"
    markup.row(
        types.InlineKeyboardButton(f"👍 إعجاب [{like_tag}]", callback_data="toggle_like"),
        types.InlineKeyboardButton(f"💬 تعليق [{cmt_tag}]", callback_data="toggle_comment")
    )

    # 3. استهداف التعليق المخصص (تفاعل و رد)
    cmt_int_tag = "✅ ON" if user_state["interact_cmt"] else "❌ OFF"
    markup.row(
        types.InlineKeyboardButton(f"🎯 تفاعل/رد على تعليق [{cmt_int_tag}]", callback_data="menu_cmt_interact")
    )

    # 4. طلب الصداقة والمتابعة
    fr_tag = "✅ ON" if user_state["friend"] else "❌ OFF"
    fl_tag = "✅ ON" if user_state["follow"] else "❌ OFF"
    markup.row(
        types.InlineKeyboardButton(f"➕ طلب صداقة [{fr_tag}]", callback_data="toggle_friend"),
        types.InlineKeyboardButton(f"🔔 متابعة [{fl_tag}]", callback_data="toggle_follow")
    )

    # 5. رسائل الماسنجر
    msg_tag = "✅ ON" if user_state["message"] else "❌ OFF"
    markup.row(
        types.InlineKeyboardButton(f"✉️ رسالة ماسنجر [{msg_tag}]", callback_data="toggle_message")
    )

    # 6. إجراءات الحماية والردع (بلاغات وحظر)
    rep_p_tag = "✅ ON" if user_state["report_post"] else "❌ OFF"
    rep_u_tag = "✅ ON" if user_state["report_profile"] else "❌ OFF"
    markup.row(
        types.InlineKeyboardButton(f"🛡️ بلاغ منشور [{rep_p_tag}]", callback_data="toggle_rep_post"),
        types.InlineKeyboardButton(f"🛡️ بلاغ حساب [{rep_u_tag}]", callback_data="toggle_rep_profile")
    )

    blk_tag = "✅ ON" if user_state["block"] else "❌ OFF"
    markup.row(
        types.InlineKeyboardButton(f"🚫 حظر الحساب [{blk_tag}]", callback_data="toggle_block"),
        types.InlineKeyboardButton("⚙️ إعدادات البلاغ والسبب", callback_data="menu_rep_config")
    )

    # 7. إدارة الحسابات وفحص الجلسات
    markup.row(
        types.InlineKeyboardButton(f"👥 إدارة الحسابات ({len(accs)})", callback_data="menu_manage_accs"),
        types.InlineKeyboardButton("🔄 فحص الجلسات", callback_data="act_check_sessions")
    )

    # 8. زر الإطلاق الميداني السحابي
    markup.row(
        types.InlineKeyboardButton("🚀 بدء تنفيذ المهام بالخلفية الآن 🚀", callback_data="action_launch")
    )

    return markup

def get_dashboard_text() -> str:
    accs = load_accounts()
    active_count = sum(1 for a in accs if "نشط" in a.get("status", ""))
    
    txt = (
        "⚡ <b>منظومة التحكم والحماية FB Operator | لوحة العمليات السحابية</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 <b>إحصائيات الحسابات:</b> {len(accs)} حساب ({active_count} نشط ومسجل)\n"
        f"🎯 <b>الرابط المستهدف:</b> <code>{user_state['target_url'][:48]}...</code>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "👇 <b>حدد العمليات المطلوبة بنقرة واحدة على الأزرار أدناه:</b>"
    )
    return txt

# ----------------- معالجات الأوامر الرئيسية -----------------

@bot.message_handler(commands=['start', 'menu'])
def cmd_start(message: types.Message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "⛔ <b>عذراً:</b> هذا البوت مشفر وخاص بالمطور فقط.")
        return

    user_state["input_mode"] = None
    bot.send_message(
        message.chat.id,
        get_dashboard_text(),
        reply_markup=get_main_dashboard_markup()
    )

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call: types.CallbackQuery):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "⛔ غير مصرح لك.", show_alert=True)
        return

    data = call.data

    # --- تبديل العمليات بنقرة واحدة (Toggle Checkboxes) ---
    if data == "toggle_like":
        user_state["like"] = not user_state["like"]
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=get_main_dashboard_markup())
        bot.answer_callback_query(call.id, f"الإعجاب: {'ON ✅' if user_state['like'] else 'OFF ❌'}")

    elif data == "toggle_comment":
        user_state["comment"] = not user_state["comment"]
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=get_main_dashboard_markup())
        bot.answer_callback_query(call.id, f"التعليق: {'ON ✅' if user_state['comment'] else 'OFF ❌'}")

    elif data == "toggle_friend":
        user_state["friend"] = not user_state["friend"]
        if user_state["friend"]:
            user_state["cancel_friend"] = False
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=get_main_dashboard_markup())
        bot.answer_callback_query(call.id, f"طلب الصداقة: {'ON ✅' if user_state['friend'] else 'OFF ❌'}")

    elif data == "toggle_follow":
        user_state["follow"] = not user_state["follow"]
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=get_main_dashboard_markup())
        bot.answer_callback_query(call.id, f"المتابعة: {'ON ✅' if user_state['follow'] else 'OFF ❌'}")

    elif data == "toggle_message":
        user_state["message"] = not user_state["message"]
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=get_main_dashboard_markup())
        bot.answer_callback_query(call.id, f"الرسائل الخاصة: {'ON ✅' if user_state['message'] else 'OFF ❌'}")

    elif data == "toggle_rep_post":
        user_state["report_post"] = not user_state["report_post"]
        if user_state["report_post"]:
            user_state["report_profile"] = False
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=get_main_dashboard_markup())
        bot.answer_callback_query(call.id, f"بلاغ المنشور: {'ON ✅' if user_state['report_post'] else 'OFF ❌'}")

    elif data == "toggle_rep_profile":
        user_state["report_profile"] = not user_state["report_profile"]
        if user_state["report_profile"]:
            user_state["report_post"] = False
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=get_main_dashboard_markup())
        bot.answer_callback_query(call.id, f"بلاغ الحساب: {'ON ✅' if user_state['report_profile'] else 'OFF ❌'}")

    elif data == "toggle_block":
        user_state["block"] = not user_state["block"]
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=get_main_dashboard_markup())
        bot.answer_callback_query(call.id, f"حظر الحساب: {'ON ✅' if user_state['block'] else 'OFF ❌'}")

    # --- القوائم الفرعية والتعديل ---
    elif data == "menu_set_url":
        user_state["input_mode"] = "waiting_url"
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
            st = "🟢" if "نشط" in a.get("status", "") else "🔴"
            markup.add(types.InlineKeyboardButton(f"{st} {a['name']}", callback_data=f"sel_acc_{a['id']}"))
        markup.add(types.InlineKeyboardButton("🔙 رجوع للرئيسية", callback_data="back_to_main"))
        bot.edit_message_text(
            "👤 <b>اختر الحساب المطلوب لتنفيذ العمليات:</b>",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )

    elif data.startswith("sel_acc_"):
        chosen = data.replace("sel_acc_", "")
        user_state["selected_acc"] = chosen
        bot.answer_callback_query(call.id, "تم اختيار الحساب بنجاح!")
        bot.edit_message_text(
            get_dashboard_text(),
            call.message.chat.id,
            call.message.message_id,
            reply_markup=get_main_dashboard_markup()
        )

    elif data == "menu_cmt_interact":
        markup = types.InlineKeyboardMarkup(row_width=2)
        int_st = "ON ✅" if user_state["interact_cmt"] else "OFF ❌"
        markup.add(types.InlineKeyboardButton(f"حالة الميزة: [{int_st}]", callback_data="toggle_cmt_int_active"))

        mode_names = {
            "first": "أول تعليق ظاهر",
            "author": f"باسم الكاتب ({user_state['cmt_target_val']})",
            "keyword": f"بكلمة ({user_state['cmt_target_val']})",
            "index": f"بالترتيب ({user_state['cmt_target_val']})"
        }
        markup.add(types.InlineKeyboardButton(f"🎯 الهدف: {mode_names.get(user_state['cmt_target_mode'], 'أول تعليق')}", callback_data="cycle_cmt_mode"))
        markup.add(types.InlineKeyboardButton("✏️ تعديل اسم/كلمة الهدف", callback_data="edit_cmt_target_val"))

        react_names = {
            "like": "أعجبني 👍", "love": "أحببته ❤️", "care": "أدعمه 🤗",
            "haha": "هاهاها 😂", "wow": "واو 😮", "sad": "أحزنني 😢",
            "angry": "أغضبني 😡", "none": "بدون تفاعل"
        }
        markup.add(types.InlineKeyboardButton(f"💖 التفاعل: {react_names.get(user_state['cmt_reaction'], 'أعجبني')}", callback_data="cycle_cmt_reaction"))
        markup.add(types.InlineKeyboardButton(f"💬 نص الرد: {user_state['cmt_reply'][:20]}...", callback_data="edit_cmt_reply_text"))
        markup.add(types.InlineKeyboardButton("🔙 حفظ والعودة للرئيسية", callback_data="back_to_main"))

        bot.edit_message_text(
            "🎯 <b>إعدادات التفاعل والرد على تعليق محدد:</b>\n"
            "يمكنك استهداف التعليق بالاسم أو بنص الكلمة واختيار أي نوع رياكشن وكتابة الرد المخصص له.",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )

    elif data == "toggle_cmt_int_active":
        user_state["interact_cmt"] = not user_state["interact_cmt"]
        bot.answer_callback_query(call.id, f"الميزة: {'ON ✅' if user_state['interact_cmt'] else 'OFF ❌'}")
        call.data = "menu_cmt_interact"
        handle_callbacks(call)

    elif data == "cycle_cmt_mode":
        modes = ["first", "author", "keyword", "index"]
        curr_idx = modes.index(user_state["cmt_target_mode"]) if user_state["cmt_target_mode"] in modes else 0
        user_state["cmt_target_mode"] = modes[(curr_idx + 1) % len(modes)]
        call.data = "menu_cmt_interact"
        handle_callbacks(call)

    elif data == "cycle_cmt_reaction":
        reactions = ["like", "love", "care", "haha", "wow", "sad", "angry", "none"]
        curr_idx = reactions.index(user_state["cmt_reaction"]) if user_state["cmt_reaction"] in reactions else 0
        user_state["cmt_reaction"] = reactions[(curr_idx + 1) % len(reactions)]
        call.data = "menu_cmt_interact"
        handle_callbacks(call)

    elif data == "edit_cmt_target_val":
        user_state["input_mode"] = "waiting_cmt_val"
        bot.send_message(call.message.chat.id, "✏️ <b>أرسل الآن اسم كاتب التعليق، أو الكلمة المفتاحية، أو رقم الترتيب:</b>")

    elif data == "edit_cmt_reply_text":
        user_state["input_mode"] = "waiting_cmt_reply"
        bot.send_message(call.message.chat.id, "✏️ <b>أرسل الآن نص الرد الذي ترغب بنشره على التعليق:</b>")

    elif data == "menu_rep_config":
        markup = types.InlineKeyboardMarkup(row_width=2)
        reasons = [
            ("مضايقة أو تنمر", "harassment"),
            ("ملف شخصي مزيف", "fake"),
            ("عنف وكراهية", "hate_violence"),
            ("خداع واحتيال", "fraud"),
            ("محتوى للبالغين", "adult"),
            ("سبام", "spam"),
            ("انتحار", "suicide")
        ]
        for name, val in reasons:
            tag = "✅ " if user_state["rep_reason"] == val else ""
            markup.add(types.InlineKeyboardButton(f"{tag}{name}", callback_data=f"set_reason_{val}"))

        victims = [("أنا شخصياً", "me"), ("صديق لي", "friend"), ("حساب وهمي", "not_real")]
        v_row = []
        for v_name, v_val in victims:
            tag = "✅ " if user_state["rep_victim"] == v_val else ""
            v_row.append(types.InlineKeyboardButton(f"{tag}{v_name}", callback_data=f"set_vic_{v_val}"))
        markup.row(*v_row)

        markup.add(types.InlineKeyboardButton("🔙 حفظ والعودة", callback_data="back_to_main"))
        bot.edit_message_text(
            "🛡️ <b>تخصيص سبب البلاغ والطرف المتضرر:</b>",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )

    elif data.startswith("set_reason_"):
        user_state["rep_reason"] = data.replace("set_reason_", "")
        call.data = "menu_rep_config"
        handle_callbacks(call)

    elif data.startswith("set_vic_"):
        user_state["rep_victim"] = data.replace("set_vic_", "")
        call.data = "menu_rep_config"
        handle_callbacks(call)

    elif data == "menu_manage_accs":
        accs = load_accounts()
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(types.InlineKeyboardButton("➕ إضافة حساب جديد", callback_data="act_add_acc"))
        markup.add(types.InlineKeyboardButton("🔄 فحص حالة الجلسات", callback_data="act_check_sessions"))
        markup.add(types.InlineKeyboardButton("🔙 رجوع", callback_data="back_to_main"))

        txt = "👥 <b>قائمة الحسابات المسجلة:</b>\n\n"
        for i, a in enumerate(accs, 1):
            st = "🟢 نشط ومسجل" if "نشط" in a.get("status", "") else "🔴 يتطلب تسجيل الدخول"
            txt += f"{i}. <b>{a['name']}</b> ({a['id']})\n   📧 <code>{a['email']}</code> | {st}\n"

        bot.edit_message_text(txt, call.message.chat.id, call.message.message_id, reply_markup=markup)

    elif data == "act_add_acc":
        user_state["input_mode"] = "add_acc_name"
        user_state["temp_acc_data"] = {}
        bot.send_message(call.message.chat.id, "➕ <b>أرسل اسم الحساب أولاً (مثال: حسابي الجديد):</b>")

    elif data == "act_check_sessions":
        bot.answer_callback_query(call.id, "🔄 جاري فحص وتحديث جلسات كافة الحسابات...")
        threading.Thread(target=check_all_sessions_worker, args=(call.message.chat.id,), daemon=True).start()

    elif data == "back_to_main":
        bot.edit_message_text(
            get_dashboard_text(),
            call.message.chat.id,
            call.message.message_id,
            reply_markup=get_main_dashboard_markup()
        )

    # --- تشغيل العمليات الميدانية بالخلفية ---
    elif data == "action_launch":
        if user_state["is_running"]:
            bot.answer_callback_query(call.id, "⚠️ هناك مهمة قيد التشغيل بالفعل حالياً!", show_alert=True)
            return

        bot.answer_callback_query(call.id, "🚀 تم استلام الأمر! بدء التنفيذ في الخلفية...")
        threading.Thread(target=execute_mission_worker, args=(call.message.chat.id,), daemon=True).start()

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
    if not is_admin(message.from_user.id):
        return

    mode = user_state.get("input_mode")
    text = message.text.strip()

    if mode == "waiting_url":
        user_state["target_url"] = text
        user_state["input_mode"] = None
        bot.reply_to(message, f"✅ تم تحديث الرابط بنجاح إلى:\n<code>{text}</code>")
        cmd_start(message)

    elif mode == "waiting_cmt_val":
        user_state["cmt_target_val"] = text
        user_state["input_mode"] = None
        bot.reply_to(message, f"✅ تم حفظ هدف التعليق: <b>{text}</b>")
        cmd_start(message)

    elif mode == "waiting_cmt_reply":
        user_state["cmt_reply"] = text
        user_state["input_mode"] = None
        bot.reply_to(message, f"✅ تم حفظ نص الرد: <b>{text}</b>")
        cmd_start(message)

    elif mode == "add_acc_name":
        user_state["temp_acc_data"]["name"] = text
        user_state["input_mode"] = "add_acc_email"
        bot.reply_to(message, "📧 <b>الآن أرسل البريد الإلكتروني أو رقم الهاتف للحساب:</b>")

    elif mode == "add_acc_email":
        user_state["temp_acc_data"]["email"] = text
        user_state["input_mode"] = "add_acc_pass"
        bot.reply_to(message, "🔑 <b>الآن أرسل كلمة المرور الخاصة بالحساب:</b>")

    elif mode == "add_acc_pass":
        user_state["temp_acc_data"]["pass"] = text
        user_state["input_mode"] = None
        name = user_state["temp_acc_data"]["name"]
        email = user_state["temp_acc_data"]["email"]
        password = user_state["temp_acc_data"]["pass"]

        wait_msg = bot.reply_to(message, f"⏳ <b>جاري إضافة الحساب '{name}' والتحقق من الجلسة في المتصفح الخلفي...</b>")
        
        acc = add_account(name, email, password)
        threading.Thread(target=async_login_account_worker, args=(message.chat.id, wait_msg.message_id, acc), daemon=True).start()

def async_login_account_worker(chat_id: int, msg_id: int, acc: dict):
    """محرك تسجيل وتثبيت الجلسة بالخلفية للحسابات الجديدة"""
    try:
        with sync_playwright() as p:
            ctx = launch_account_browser(p, acc["profile_dir"], visible=False)
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            
            def log_callback(msg):
                pass

            logged = auto_login_facebook(ctx, page, acc["email"], acc["password"], status_callback=log_callback)
            if logged:
                update_account(acc["id"], {"status": "نشط ومسجل"})
                bot.edit_message_text(
                    f"🎉 <b>تم بنجاح تسجيل دخول وتثبيت جلسة الحساب:</b>\n"
                    f"👤 <b>الاسم:</b> {acc['name']}\n"
                    f"📧 <b>البريد:</b> <code>{acc['email']}</code>\n"
                    f"🛡️ <b>الحالة:</b> نشط ومسجل للأبد بدون الحاجة لكلمة المرور مجدداً!",
                    chat_id, msg_id
                )
            else:
                update_account(acc["id"], {"status": "يتطلب تسجيل الدخول"})
                bot.edit_message_text(
                    f"⚠️ <b>تم حفظ بيانات الحساب '{acc['name']}' ولكن لم تكتمل الجلسة تلقائياً.</b>\n"
                    f"قد يطلب الحساب كود أمان 2FA.",
                    chat_id, msg_id
                )
            ctx.close()
    except Exception as e:
        bot.edit_message_text(f"❌ حدث خطأ أثناء التسجيل: {e}", chat_id, msg_id)

# ----------------- المحرك الميداني الرئيسي للتنفيذ بالخلفية -----------------

def execute_mission_worker(chat_id: int):
    """المحرك الميداني الذي ينفذ كافة العمليات بالمتصفح المخفي ويرسل التحديثات الحية ولحظات الإثبات"""
    user_state["is_running"] = True
    status_msg = bot.send_message(chat_id, "⏳ <b>بدء تهيئة محرك العمليات وتشغيل المتصفح بالخلفية...</b>")

    def update_live_status(text: str):
        try:
            bot.edit_message_text(text, chat_id, status_msg.message_id)
        except Exception:
            pass

    try:
        accounts = load_accounts()
        target_accounts = []
        if user_state["selected_acc"] == "all":
            target_accounts = accounts
        else:
            target_accounts = [a for a in accounts if a["id"] == user_state["selected_acc"]]

        if not target_accounts:
            update_live_status("❌ <b>خطأ:</b> لم يتم العثور على أي حساب مسجل للتنفيذ.")
            user_state["is_running"] = False
            return

        actions_done = 0
        total_accounts = len(target_accounts)
        target_url = user_state["target_url"]

        # إنشاء مجلد scratch لحفظ لقطات الشاشة
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
                    # أ. طلب الصداقة / الإلغاء
                    if user_state["friend"]:
                        if send_friend_request(page):
                            actions_done += 1
                            bot.send_message(chat_id, f"➕ <b>تم إرسال طلب صداقة بنجاح بالحساب {acc['name']}.</b>")

                    elif user_state["cancel_friend"]:
                        if cancel_friend_request(page):
                            actions_done += 1
                            bot.send_message(chat_id, f"↩️ <b>تم إلغاء طلب الصداقة بالحساب {acc['name']}.</b>")

                    # ب. المتابعة
                    if user_state["follow"]:
                        if follow_profile(page):
                            actions_done += 1
                            bot.send_message(chat_id, f"🔔 <b>تمت متابعة الحساب بنجاح بـ {acc['name']}.</b>")

                    # ج. الرسالة الخاصة
                    if user_state["message"] and user_state["message_text"]:
                        if send_direct_message(page, user_state["message_text"], target_url=target_url):
                            actions_done += 1
                            bot.send_message(chat_id, f"✉️ <b>تم إرسال الرسالة الخاصة بالماسنجر بـ {acc['name']}.</b>")

                    # د. الإعجاب بالمنشور
                    if user_state["like"]:
                        cnt = like_posts(page, mode=user_state["like_scope"], count=1)
                        if cnt > 0:
                            actions_done += cnt
                            bot.send_message(chat_id, f"👍 <b>تم الإعجاب بالمنشور بالحساب {acc['name']}.</b>")

                    # هـ. التعليق على المنشور
                    if user_state["comment"] and user_state["comment_text"]:
                        c_cnt = comment_on_posts(page, comment_text=user_state["comment_text"], mode="latest", count=1)
                        if c_cnt > 0:
                            actions_done += c_cnt
                            bot.send_message(chat_id, f"💬 <b>تم نشر التعليق بنجاح بـ {acc['name']}:</b>\n<i>'{user_state['comment_text']}'</i>")

                    # و. التفاعل والرد على تعليق محدد
                    if user_state["interact_cmt"]:
                        ok_int = interact_with_specific_comment(
                            page,
                            post_index=1,
                            target_mode=user_state["cmt_target_mode"],
                            target_value=user_state["cmt_target_val"],
                            reaction=user_state["cmt_reaction"],
                            reply_text=user_state["cmt_reply"]
                        )
                        if ok_int:
                            actions_done += 1
                            bot.send_message(chat_id, f"🎯 <b>تم التفاعل والرد على التعليق المحدد بنجاح بـ {acc['name']}!</b>")

                    # ز. تقديم بلاغ ضد المنشور
                    if user_state["report_post"]:
                        update_live_status(f"🛡️ <b>جاري تنفيذ معالج البلاغ الرسمي ضد المنشور بـ {acc['name']}...</b>")
                        if report_post(page, reason=user_state["rep_reason"], victim=user_state["rep_victim"]):
                            actions_done += 1
                            bot.send_message(chat_id, f"🛡️ <b>تم تأكيد استلام البلاغ رسمياً من فيسبوك ضد المنشور بـ {acc['name']}!</b>")

                    # ح. تقديم بلاغ ضد الحساب بالكامل
                    if user_state["report_profile"]:
                        update_live_status(f"🛡️ <b>جاري تنفيذ معالج البلاغ الرسمي ضد الحساب كاملاً بـ {acc['name']}...</b>")
                        if report_profile(page, reason=user_state["rep_reason"], victim=user_state["rep_victim"]):
                            actions_done += 1
                            bot.send_message(chat_id, f"🛡️ <b>تم تأكيد استلام البلاغ رسمياً من فيسبوك ضد الحساب كاملاً بـ {acc['name']}!</b>")

                    # ط. حظر الحساب
                    if user_state["block"]:
                        if block_profile(page):
                            actions_done += 1
                            bot.send_message(chat_id, f"🚫 <b>تم حظر الحساب بنجاح بـ {acc['name']}.</b>")

                    # التقاط صورة ختامية
                    try:
                        shot_path = str(scratch_dir / f"bot_shot_{acc['id']}.png")
                        page.screenshot(path=shot_path)
                        with open(shot_path, "rb") as shot_file:
                            bot.send_photo(chat_id, shot_file, caption=f"📸 <b>لقطة شاشة للهدف بعد التنفيذ بالحساب:</b> {acc['name']}")
                    except Exception:
                        pass

                    human_delay(2.0, 3.5)
                    ctx.close()

                except Exception as err:
                    bot.send_message(chat_id, f"❌ <b>خطأ بالحساب {acc['name']}:</b> {err}")

            if idx < total_accounts:
                time.sleep(4)

        # التقرير الختامي
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
        user_state["is_running"] = False

# ----------------- تشغيل البوت المستمر وخادم الفحص السحابي -----------------

def start_health_server():
    """خادم ويب خفيف جداً للاستجابة لفحوصات المنصات السحابية (Hugging Face / Render / Koyeb)"""
    from http.server import HTTPServer, BaseHTTPRequestHandler
    class HealthHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header('Content-type', 'text/plain; charset=utf-8')
            self.end_headers()
            self.wfile.write(b"FB Operator Bot is Running 24/7 in Cloud!")
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
    print("🚀 بدء تشغيل بوت تلغرام FB Operator في السحاب/الخلفية 24/7...")
    print(f"🤖 معرف البوت: @{bot.get_me().username}")
    print(f"👑 معرف المطور المسؤول: {ADMIN_ID}")
    print("=" * 60)
    
    # تشغيل خادم الصحة السحابي بالخلفية
    threading.Thread(target=start_health_server, daemon=True).start()
    
    while True:
        try:
            bot.infinity_polling(timeout=25, long_polling_timeout=25)
        except Exception as e:
            print(f"[Bot Warning] خطأ بالاتصال، إعادة المحاولة بعد 5 ثوانٍ: {e}")
            time.sleep(5)

if __name__ == "__main__":
    run_telegram_bot()
