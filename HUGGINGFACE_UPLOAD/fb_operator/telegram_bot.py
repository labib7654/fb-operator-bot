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
import io
import re
import html
import time
import atexit
import signal
import secrets
import hashlib
import tempfile
import threading
from datetime import datetime
import telebot
from telebot import types
from collections import deque

from fb_operator.config import BROKEN_ACCOUNT_TTL_HOURS
from fb_operator.account_manager import (
    load_accounts, add_account, update_account, delete_account,
    purge_broken_accounts, purge_expired_broken_accounts,
    get_accounts_by_owner, get_accounts_breakdown_by_owner,
    delete_accounts_by_owner, get_account_by_id, git_sync_save,
    parse_cookies_payload, save_account_cookies_session
)
from fb_operator.admin_manager import (
    is_super_admin, is_authorized_user, has_permission, get_user_permissions,
    register_or_update_user, approve_user, ban_user, unban_user,
    toggle_user_permission, revoke_all_permissions, grant_all_user_permissions,
    delete_user_and_data, load_users, record_user_operation, record_account_result_for_user,
    record_audit_log, load_audit_logs, reset_user_profile_warnings,
    safe_nonneg_points, SUPER_ADMIN_ID, PERMISSION_LABELS,
    ADMIN_TIERS, ADMIN_TIER_LABELS, ADMIN_RESTRICTION_LABELS,
    get_admin_tier, get_admin_restrictions, is_admin_delegate,
    has_admin_capability, get_user_admin_capabilities, can_manage_target_user,
    get_admin_notification_recipients, set_admin_tier, toggle_admin_restriction,
)
from fb_operator.announcement_manager import (
    BADGE_OPTIONS, STYLE_OPTIONS, DURATION_PRESETS, REPEAT_PRESETS,
    DELIVERY_MODES, REPEAT_BEHAVIORS, EFFECT_PRESETS, DEFAULT_THEME_EMOJIS,
    create_announcement, list_announcements, get_announcement_by_id,
    toggle_announcement_active, update_announcement_timing, update_announcement_delivery,
    delete_announcement, record_announcement_sent_chats, mark_announcement_repushed,
    pop_expired_pinned_announcements, get_announcements_due_for_repeat,
    format_announcement_telegram_html, format_duration_ar,
    get_theme_config, update_theme_config,
)
from fb_operator.banner_renderer import render_announcement_media
from fb_operator.browser_manager import (
    sync_playwright, USING_PATCHRIGHT,
    launch_account_browser, auto_login_facebook, check_facebook_login_cookies,
    human_delay, human_warmup_after_login, get_login_error, check_facebook_page_access,
    diagnose_facebook_challenge, inspect_facebook_profile_quality,
    save_account_storage_state, clear_account_storage_state, _resolve_session_file,
    dismiss_dialogs, get_profile_lock, detect_and_report_proxy_error,
)
try:
    dismiss_dialogs
except NameError:
    def dismiss_dialogs(page) -> None:
        pass
from fb_operator.proxy_manager import (
    add_proxies_bulk,
    bind_existing_accounts,
    check_all_proxies,
    check_single_proxy,
    clear_all_proxies,
    clear_dead_proxies,
    delete_single_proxy,
    fetch_and_check_github_free_proxies,
    get_4g_bridge_status,
    get_proxy_detailed_report,
    get_proxy_lock,
    get_proxy_summary,
    load_proxy_state,
    mask_proxy_uri,
    proxy_execution_guard,
    rebind_proxy_accounts,
    record_proxy_use,
    refresh_4g_client_geo,
    register_proxy_alert_callback,
    resolve_proxy_for_account,
    run_scheduled_proxy_watchdog,
    seed_env_proxies,
    set_max_per_proxy,
    set_proxy_mode,
    start_gost_4g_bridge,
    stop_gost_4g_bridge,
    toggle_auto_check,
)
from fb_operator.actions import (
    navigate_to_target, comment_on_posts, react_to_posts,
    send_friend_request, cancel_friend_request, follow_profile, unfollow_profile,
    send_direct_message, block_profile, report_profile, report_post,
    interact_with_specific_comment, get_page_diag
)
from fb_operator.webapp_server import (
    start_webapp_and_tunnel, get_public_webapp_url, update_menu_button_for_user
)
from fb_operator.state_events import publish_event, register_listener
from fb_operator.persistence_manager import (
    bootstrap_persistence, export_backup_zip_bytes, restore_backup_zip_bytes,
    inspect_backup_zip_bytes, merge_backup_zip_bytes, merge_legacy_json_bytes,
    hf_dataset_sync_upload, flush_cloud_backups, get_persistence_status,
    cloud_db_sync_upload, cloud_db_sync_download,
    load_backup_settings, save_backup_settings, parse_backup_interval,
    format_backup_interval, send_backup_to_channel, load_ui_states_data,
    save_ui_states_data, register_pre_backup_callback, register_restore_callback,
    MIN_BACKUP_INTERVAL_SEC, MAX_BACKUP_INTERVAL_SEC
)
from fb_operator.cloud_db import (
    load_cloud_db_config, save_cloud_db_config, clear_cloud_db_config,
    test_cloud_db_connection, get_cloud_db_status_summary, get_provider_setup_guide
)
from fb_operator.hitl_manager import (
    register_hitl_verified_callback,
    submit_telegram_otp_for_account,
    register_mission_hitl_waiter,
    signal_mission_hitl_decision,
    wait_for_mission_hitl,
    get_mission_hitl_waiter,
    clear_mission_hitl_waiter,
    record_hitl_challenge_url,
)
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
from fb_operator.feature_gates import (
    load_feature_gates, get_feature, list_features, is_feature_accessible,
    get_feature_cost, update_feature_gate, register_custom_feature,
    add_allowed_user, remove_allowed_user, is_feature_enabled,
)
import fb_operator.tempmail_manager as tm_m
from fb_operator.yemen_caller_id import YemenCallerIDAPI

BOT_TOKEN = (os.environ.get("BOT_TOKEN") or "").strip() or "9257479294:AAGFsE7uOQX_CoazLDrkAnbZaN4IQ6DB9Xg"

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML", threaded=True, num_threads=32)
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
    if not rew or is_dev_owner or float(rew.get("owner_awarded", 0) or 0) <= 0:
        return ""
    pts = rew.get("owner_awarded", 0)
    bal = rew.get("owner_balance", 0)
    rate = int(rew.get("yer_per_point", 10))
    yer_got = int(rew.get("owner_awarded_yer") or round(float(pts) * rate))
    yer_bal = int(rew.get("owner_yer_value") or round(float(bal) * rate))

    base = (
        f"\n\n🪙 <b>مكافأة التفعيل:</b> +{pts} نقطة (<b>{yer_got:,} ر.ي</b>) للحساب ({esc(acc_name)})\n"
        f"💰 <b>رصيدك الآن:</b> {bal} نقطة (≈ <b>{yer_bal:,} ريال يمني</b>)"
    )

    w_status = rew.get("warning_status", "none")
    missing = list(rew.get("missing_labels") or [])
    missing_str = "، ".join(esc(x) for x in missing)
    w_num = int(rew.get("warning_num", 0))
    w_lim = int(rew.get("warning_limit", 5))
    rem = int(rew.get("warnings_remaining", max(0, w_lim - w_num)))
    full_yer = int(rew.get("full_reward_yer", rate))
    inc_yer = int(rew.get("incomplete_reward_yer", 5))

    if w_status == "complete":
        return base + "\n✅ <b>جودة البروفايل:</b> مكتمل الشروط السبعة — احتُسب بالسعر الكامل!"
    elif w_status == "warned":
        return (
            base
            + f"\n\n⚠️ <b>تنبيه جودة البروفايل (الإنذار {w_num} من {w_lim}):</b>\n"
            + (f"❌ <b>ينقص الحساب:</b> {missing_str}\n" if missing_str else "")
            + "📌 عند إضافة الحسابات القادمة تأكد من إكمال: <b>اسم عربي طبيعي مناسب، صورة شخصية، غلاف (خلفية)، سيرة ذاتية، الجامعة، الحالة الاجتماعية، ومنشور أو منشورين</b>.\n"
            + f"⏳ متبقي لك <b>{rem}</b> إنذار(ات) — عند نفاد الـ {w_lim} إنذارات سيُحتسب الحساب الناقص بـ <b>{inc_yer} ر.ي فقط</b> بدلاً من {full_yer} ر.ي (بينما يظل الكامل بـ {full_yer} ر.ي)."
        )
    elif w_status == "penalized":
        return (
            base
            + f"\n\n🔻 <b>تم استنفاد الإنذارات ({w_lim}/{w_lim}) — احتساب نصف السعر ({inc_yer} ر.ي):</b>\n"
            + (f"❌ <b>الحساب ناقص:</b> {missing_str}\n" if missing_str else "")
            + f"💡 لإستلام <b>{full_yer} ر.ي كاملة</b> في المرات القادمة، أكمل كافة شروط البروفايل والمنشورات قبل الإضافة."
        )
    return base

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


_BOT_CAP_CUSTOM_EMOJI_OK = True
_BOT_CAP_STYLE_OK = True


def _resolve_custom_emoji_id(icon_key: str | None = None, explicit_id: str | None = None) -> str | None:
    if not _BOT_CAP_CUSTOM_EMOJI_OK:
        return None
    if explicit_id and str(explicit_id).strip().isdigit():
        return str(explicit_id).strip()
    if not icon_key:
        return None
    try:
        tcfg = get_theme_config()
        if not tcfg.get("custom_emojis_enabled", True):
            return None
        val = str((tcfg.get("emojis") or {}).get(icon_key) or "").strip()
        if val.isdigit() and 15 <= len(val) <= 24:
            return val
    except Exception:
        pass
    return None


def _btn(
    text: str,
    *,
    style: str | None = None,
    icon_key: str | None = None,
    icon_custom_emoji_id: str | None = None,
    **kwargs,
) -> types.InlineKeyboardButton:
    """بناء زر Inline بألوان Bot API 9.4 (success/primary/danger) وأيقونة اختيارية مع تراجع آمن"""
    params = dict(kwargs)
    if _BOT_CAP_STYLE_OK and style in ("primary", "success", "danger"):
        params["style"] = style
    ce_id = _resolve_custom_emoji_id(icon_key, icon_custom_emoji_id)
    if ce_id:
        params["icon_custom_emoji_id"] = ce_id
    try:
        return types.InlineKeyboardButton(text, **params)
    except TypeError:
        params.pop("style", None)
        params.pop("icon_custom_emoji_id", None)
        return types.InlineKeyboardButton(text, **params)


def _kbtn(
    text: str,
    *,
    style: str | None = None,
    icon_key: str | None = None,
    **kwargs,
) -> types.KeyboardButton:
    params = dict(kwargs)
    if _BOT_CAP_STYLE_OK and style in ("primary", "success", "danger"):
        params["style"] = style
    ce_id = _resolve_custom_emoji_id(icon_key, None)
    if ce_id:
        params["icon_custom_emoji_id"] = ce_id
    try:
        return types.KeyboardButton(text, **params)
    except TypeError:
        params.pop("style", None)
        params.pop("icon_custom_emoji_id", None)
        return types.KeyboardButton(text, **params)


def _strip_markup_cosmetics(reply_markup, drop_style: bool = False, drop_icon: bool = True):
    if reply_markup is None or not hasattr(reply_markup, "keyboard"):
        return reply_markup
    try:
        if isinstance(reply_markup, types.InlineKeyboardMarkup):
            new_mk = types.InlineKeyboardMarkup(row_width=getattr(reply_markup, "row_width", 2))
            for row in reply_markup.keyboard:
                new_row = []
                for btn in row:
                    d = btn.to_dict() if hasattr(btn, "to_dict") else {}
                    t = d.get("text") or getattr(btn, "text", "")
                    kw = {k: v for k, v in d.items() if k != "text"}
                    if drop_icon:
                        kw.pop("icon_custom_emoji_id", None)
                    if drop_style:
                        kw.pop("style", None)
                    if "web_app" in kw and isinstance(kw["web_app"], dict):
                        kw["web_app"] = types.WebAppInfo(url=kw["web_app"].get("url", ""))
                    new_row.append(types.InlineKeyboardButton(t, **kw))
                new_mk.row(*new_row)
            return new_mk
    except Exception:
        pass
    return reply_markup


def _strip_tg_emoji_tags(html_text: str) -> str:
    return re.sub(r"</?tg-emoji\b[^>]*>", "", str(html_text or ""))


def _safe_bot_send(fn, *args, **kwargs):
    """مُرسل مرن يحافظ على ألوان الأزرار ويتجاوز تلقائياً فقط الميزات التي يرفضها السيرفر مع حماية 429"""
    global _BOT_CAP_CUSTOM_EMOJI_OK, _BOT_CAP_STYLE_OK
    try:
        return fn(*args, **kwargs)
    except Exception as exc:
        err_s = str(exc).lower()
        if "429" in err_s or "too many requests" in err_s or "retry after" in err_s:
            m = re.search(r"retry after (\d+)", err_s)
            wait_s = int(m.group(1)) if m else 2
            if wait_s <= 3:
                time.sleep(wait_s)
                try:
                    return fn(*args, **kwargs)
                except Exception:
                    return None
            return None

        retry_kw = dict(kwargs)
        changed = False
        if "effect" in err_s and "message_effect_id" in retry_kw:
            retry_kw.pop("message_effect_id", None)
            changed = True
        if ("emoji" in err_s or "custom_emoji" in err_s or "icon" in err_s or "premium" in err_s):
            _BOT_CAP_CUSTOM_EMOJI_OK = False
            if "text" in retry_kw:
                retry_kw["text"] = _strip_tg_emoji_tags(retry_kw["text"])
            elif args and isinstance(args[1] if len(args) > 1 else None, str):
                args = (args[0], _strip_tg_emoji_tags(args[1]), *args[2:])
            if "caption" in retry_kw:
                retry_kw["caption"] = _strip_tg_emoji_tags(retry_kw["caption"])
            if retry_kw.get("reply_markup") is not None:
                retry_kw["reply_markup"] = _strip_markup_cosmetics(retry_kw["reply_markup"], drop_style=False, drop_icon=True)
            changed = True
        if "style" in err_s and retry_kw.get("reply_markup") is not None:
            _BOT_CAP_STYLE_OK = False
            retry_kw["reply_markup"] = _strip_markup_cosmetics(retry_kw["reply_markup"], drop_style=True, drop_icon=True)
            changed = True
        if changed:
            try:
                return fn(*args, **retry_kw)
            except Exception:
                return None
        return None


def safe_edit_message(text: str, chat_id: int, message_id: int | None, reply_markup=None) -> None:
    if message_id is None:
        safe_send(chat_id, text, reply_markup=reply_markup)
        return
    try:
        bot.edit_message_text(text, chat_id, message_id, reply_markup=reply_markup)
    except Exception as e:
        err_l = str(e).lower()
        if "message is not modified" in err_l:
            return
        if "429" in err_l or "too many requests" in err_l or "retry after" in err_l:
            return
        if "style" in err_l or "emoji" in err_l or "icon" in err_l:
            try:
                clean_mk = _strip_markup_cosmetics(reply_markup, drop_style=("style" in err_l), drop_icon=True)
                bot.edit_message_text(_strip_tg_emoji_tags(text), chat_id, message_id, reply_markup=clean_mk)
                return
            except Exception:
                pass
        safe_send(chat_id, text, reply_markup=reply_markup)


def safe_edit_reply_markup(chat_id: int, message_id: int, reply_markup) -> None:
    try:
        bot.edit_message_reply_markup(chat_id, message_id, reply_markup=reply_markup)
    except Exception:
        pass


def safe_send(chat_id: int, text: str, reply_markup=None, **extra):
    return _safe_bot_send(bot.send_message, chat_id, text, reply_markup=reply_markup, **extra)


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


def _detect_browser_concurrency() -> int:
    """تحديد أقصى عدد متصفحات متزامنة تلقائياً حسب الذاكرة المتاحة لمنع الانهيار تحت الضغط"""
    raw_env = (os.environ.get("FB_MAX_BROWSERS") or "").strip()
    if raw_env.isdigit():
        return max(1, min(20, int(raw_env)))
    avail_mb = 0
    try:
        meminfo = Path("/proc/meminfo")
        if meminfo.exists():
            txt = meminfo.read_text(encoding="utf-8", errors="ignore")
            m = re.search(r"MemTotal:\s+(\d+)\s+kB", txt)
            if m:
                avail_mb = int(m.group(1)) // 1024
    except Exception:
        avail_mb = 0
    if avail_mb <= 0 and os.name == "nt":
        try:
            import ctypes
            class _MEMSTAT(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]
            ms = _MEMSTAT()
            ms.dwLength = ctypes.sizeof(_MEMSTAT)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(ms)):
                avail_mb = int(ms.ullTotalPhys // (1024 * 1024))
        except Exception:
            pass
    if avail_mb > 0:
        return max(2, min(12, avail_mb // 900))
    return 4


# أقفال عزل بروفايلات المتصفح مستوردة بشكل موحد من browser_manager (get_profile_lock)
_browser_semaphore = threading.BoundedSemaphore(_detect_browser_concurrency())


def _account_proxy_guard_uri(acc: dict) -> str:
    """استخراج عنوان البروكسي المربوط للحساب لتطبيق قفل منع التزامن على نفس الـ IP."""
    try:
        explicit_proxy = str(acc.get("proxy") or "").strip()
        prof_dir = str(acc.get("profile_dir") or acc.get("id") or "").replace("\\", "/").rstrip("/")
        acc_key = os.path.basename(prof_dir) or str(acc.get("id") or "").strip()
        res = resolve_proxy_for_account(account_id=acc_key, explicit_proxy=explicit_proxy)
        return str(res.get("raw_uri") or "")
    except Exception:
        return str(acc.get("proxy") or "").strip()

_RATE_LOCK = threading.Lock()
_USER_RATE_BUCKETS: dict[int, deque[float]] = {}


def _check_user_rate_limit(user_id: int, max_ops: int = 35, window_sec: float = 5.0) -> bool:
    """حارس انزلاق زمني ضد الإغراق لحماية البوت من التهنيج عند الضغط العالي"""
    if is_super_admin(user_id):
        return True
    now = time.monotonic()
    with _RATE_LOCK:
        dq = _USER_RATE_BUCKETS.get(user_id)
        if dq is None:
            dq = deque()
            _USER_RATE_BUCKETS[user_id] = dq
        while dq and (now - dq[0]) > window_sec:
            dq.popleft()
        if len(dq) >= max_ops:
            return False
        dq.append(now)
        return True


# ----------------- إدارة الجلسات المتعددة وعزل المستخدمين (Multi-Tenant Engine) -----------------

user_states: dict[int, dict] = {}
state_lock = threading.Lock()


def default_user_state() -> dict:
    return {
        "target_url": "https://www.facebook.com/profile.php?id=61595626255487",
        "selected_acc": "all",
        "selected_accs": [],
        "acc_count_limit": 0,
        "wait_for_hitl": True,
        "waiting_hitl_acc_id": "",
        "waiting_hitl_reason": "",
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
        st = user_states.get(user_id)
        if st is not None:
            return st
    saved = load_ui_states_data().get(user_id, {})
    with state_lock:
        if user_id not in user_states:
            base = default_user_state()
            if isinstance(saved, dict):
                base.update(saved)
            user_states[user_id] = base
        return user_states[user_id]


def persist_user_states(mark_dirty: bool = True) -> None:
    with state_lock:
        snapshot = {uid: dict(st) for uid, st in user_states.items()}
    save_ui_states_data(snapshot, mark_dirty=mark_dirty)


def reload_user_states_from_disk() -> None:
    loaded = load_ui_states_data()
    with state_lock:
        user_states.clear()
        for uid, saved in loaded.items():
            base = default_user_state()
            base.update(saved)
            user_states[uid] = base


register_pre_backup_callback(lambda: persist_user_states(mark_dirty=False))
register_restore_callback(reload_user_states_from_disk)


def user_has_any_action_perm(user_id: int) -> bool:
    if is_super_admin(user_id):
        return True
    action_keys = (
        "can_react", "can_comment", "can_interact_comments",
        "can_friend_follow", "can_message", "can_report"
    )
    return any(has_permission(user_id, k) for k in action_keys)


def _has_any_enabled_mission_action(user_id: int, st: dict) -> tuple[bool, str]:
    """التحقق الفعلي قبل الإطلاق من تفعيل أداة واحدة على الأقل واكتمال مدخلاتها"""
    is_dev = is_super_admin(user_id)
    has_p = lambda k: is_dev or has_permission(user_id, k)

    url_val = (st.get("target_url") or "").strip()
    has_post_url = bool((st.get("react_post_url") or "").strip() or (st.get("comment_post_url") or "").strip())
    if not url_val.startswith("http") and not has_post_url:
        return False, "⚠️ الرابط المستهدف غير صالح! اضغط (🔗 تعديل الرابط المستهدف) وأرسل رابط فيسبوك الصحيح أولاً."

    enabled = []
    if has_p("can_react") and st.get("like"):
        enabled.append("تفاعل")
    if has_p("can_comment") and st.get("comment"):
        if not (st.get("comment_text") or "").strip():
            return False, "⚠️ فعّلت التعليق بدون نص! افتح معالج التعليق وأرسل نص التعليق أولاً."
        enabled.append("تعليق")
    if has_p("can_interact_comments") and st.get("interact_cmt"):
        enabled.append("تفاعل/رد على تعليق")
    if has_p("can_friend_follow") and any(st.get(k) for k in ("friend", "cancel_friend", "follow", "unfollow")):
        enabled.append("صداقة/متابعة")
    if has_p("can_message") and st.get("message"):
        if not (st.get("message_text") or "").strip():
            return False, "⚠️ فعّلت الرسالة الخاصة بدون نص! افتح زر الرسالة واكتب نص الرسالة أولاً."
        enabled.append("رسالة خاصة")
    if has_p("can_report") and any(st.get(k) for k in ("report_post", "report_profile", "block")):
        enabled.append("بلاغ/حظر")

    if not enabled:
        return False, "⚠️ لم تفعّل أي إجراء للتنفيذ بعد! اختر التفاعل أو التعليق أو الرسالة أو الصداقة أولاً ثم أطلق المهمة."
    return True, ""


def get_usable_accounts_for_user(user_id: int) -> list[dict]:
    """
    حسابات التنفيذ المصرح بها للمستخدم بدقة أمنية:
    - المطور الأكبر (أو النائب غير المقيد على الحسابات) يرى كل الحسابات.
    - من يملك صلاحية 'can_use_accounts' يستخدم كافة حسابات البوت.
    - من لا يملك 'can_use_accounts' يقتصر فقط على حساباته التي أضافها هو.
    """
    accs = load_accounts()
    if has_admin_capability(user_id, "accounts_pool") or has_permission(user_id, "can_use_accounts"):
        return accs
    return [a for a in accs if a.get("owner_id") == int(user_id)]


def get_manageable_accounts_for_user(user_id: int) -> list[dict]:
    """قائمة الحسابات الظاهرة في إدارة الحسابات: المطور/النائب المصرح يرى الكل، والمستخدم يرى ما أضافه فقط"""
    if has_admin_capability(user_id, "accounts_pool"):
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
    """إرسال تنبيه فوري للمطور والمدراء/النواب غير المقيدين عند دخول مستخدم جديد مع أزرار الموافقة أو الحظر"""
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
    for rec_uid in get_admin_notification_recipients("new_user_notices"):
        safe_send(rec_uid, alert_text, reply_markup=markup)


def check_user_access_gate(user, chat_id: int, notify_blocked: bool = True) -> bool:
    """
    بوابة الأمان والتحقق الصارمة:
    1. المطور الأكبر يمر فوراً بصلاحيات مطلقة لا تمس.
    2. أي مستخدم جديد يُسجل كـ 'pending' وكافة الأدوات مغلقة (False)، ويُرسل إشعار فوري للمطور والمدراء.
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
            for rec_uid in get_admin_notification_recipients("new_user_notices"):
                safe_send(
                    rec_uid,
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


def _build_announcement_markup(ann: dict, include_ack: bool = True) -> types.InlineKeyboardMarkup:
    mk = types.InlineKeyboardMarkup(row_width=2)
    ann_id = str(ann.get("id") or "")
    cta_lbl = str(ann.get("cta_label") or "استعراض الميزة الآن").strip()[:36]
    w_url = get_public_webapp_url()
    if w_url:
        sep = "&" if "?" in w_url else "?"
        tab_arg = f"&tab={ann.get('cta_tab')}" if ann.get("cta_tab") else ""
        mk.row(
            _btn(
                f"🚀 {cta_lbl[:28]}",
                style="success",
                icon_key="rocket",
                web_app=types.WebAppInfo(url=f"{w_url}{sep}promo={ann_id}{tab_arg}"),
            )
        )
    else:
        mk.row(
            _btn(
                f"✨ {cta_lbl[:28]}",
                style="success",
                icon_key="spark",
                callback_data=f"promo_view_{ann_id}",
            )
        )
    if include_ack:
        mk.row(
            _btn("📋 التفاصيل السريعة", style="primary", callback_data=f"promo_view_{ann_id}"),
            _btn("✅ إخفاء", callback_data=f"promo_ack_{ann_id}"),
        )
    return mk


def _unpin_announcement_chats(ann: dict) -> int:
    """إزالة تثبيت الإعلان العائم من دردشات جميع المستخدمين فوراً عند انتهاء مدته أو حذفه"""
    if not isinstance(ann, dict):
        return 0
    sent_chats = ann.get("sent_chats") or {}
    unpinned = 0
    for cid_s, mid in sent_chats.items():
        try:
            bot.unpin_chat_message(chat_id=int(cid_s), message_id=int(mid))
            unpinned += 1
        except Exception:
            pass
    return unpinned


def _send_announcement_to_chat(
    cid: int,
    ann: dict,
    *,
    is_repeat: bool = False,
    rendered_media: dict | None = None,
) -> tuple[int | None, bool]:
    """إرسال أو تحديث بطاقة الإعلان لدردشة واحدة بأسلوب نظيف خالٍ من سبام التثبيت"""
    ann_id = str(ann.get("id") or "")
    d_mode = str(ann.get("delivery_mode") or "animated_card")
    rep_beh = str(ann.get("repeat_behavior") or "replace")
    pin_flag = bool(ann.get("pin_in_chat", False))
    eff_preset = str(ann.get("effect_preset") or "none")
    effect_id = (EFFECT_PRESETS.get(eff_preset) or ("", ""))[1]

    html_txt = format_announcement_telegram_html(
        ann, esc_fn=esc, is_repeat=is_repeat, use_custom_emojis=_BOT_CAP_CUSTOM_EMOJI_OK
    )
    markup = _build_announcement_markup(ann, include_ack=True)
    old_mid = None
    try:
        raw_mid = (ann.get("sent_chats") or {}).get(str(int(cid)))
        old_mid = int(raw_mid) if raw_mid else None
    except Exception:
        old_mid = None
    had_media_before = str(int(cid)) in set(str(x) for x in (ann.get("media_chat_ids") or []))

    # 1) وضع التحديث الحي بنفس الرسالة: لا يرسل رسالة مكررة ولا يعيد التثبيت إطلاقاً
    if is_repeat and rep_beh == "edit_live" and old_mid:
        try:
            if had_media_before:
                _safe_bot_send(
                    bot.edit_message_caption,
                    caption=html_txt[:1000],
                    chat_id=cid,
                    message_id=old_mid,
                    reply_markup=markup,
                )
            else:
                safe_edit_message(html_txt, cid, old_mid, reply_markup=markup)
            return old_mid, False
        except Exception:
            pass

    # 2) وضع الاستبدال النظيف (افتراضي للإعلان العائم): يحذف البطاقة غير المثبّتة القديمة قبل إرسال الجديدة
    if is_repeat and rep_beh == "replace" and old_mid and not pin_flag:
        try:
            bot.delete_message(cid, old_mid)
        except Exception:
            pass

    msg = None
    is_media_msg = False
    media_bytes = rendered_media.get("bytes") if isinstance(rendered_media, dict) else None
    media_kind = rendered_media.get("kind") if isinstance(rendered_media, dict) else ""

    if media_bytes and d_mode in ("animated_card", "photo_card"):
        bio = io.BytesIO(media_bytes)
        bio.name = f"promo_{ann_id}.{rendered_media.get('ext', 'png')}"
        cap = html_txt[:1000]
        send_kw: dict = {"caption": cap, "reply_markup": markup, "show_caption_above_media": False}
        if effect_id and not is_repeat:
            send_kw["message_effect_id"] = effect_id
        if media_kind == "gif" and d_mode == "animated_card":
            msg = _safe_bot_send(bot.send_animation, cid, bio, **send_kw)
        else:
            msg = _safe_bot_send(bot.send_photo, cid, bio, **send_kw)
        if msg and hasattr(msg, "message_id"):
            is_media_msg = True

    if not msg:
        if effect_id and not is_repeat:
            msg = safe_send(cid, html_txt, reply_markup=markup, message_effect_id=effect_id)
        else:
            msg = safe_send(cid, html_txt, reply_markup=markup)

    new_mid = int(msg.message_id) if (msg and hasattr(msg, "message_id")) else None
    if new_mid and pin_flag and (not is_repeat or not old_mid):
        # يُثبّت مرة واحدة فقط إذا فعّل المطور التثبيت صراحةً؛ ولا يعاد التثبيت أبداً عند التكرار
        try:
            bot.pin_chat_message(cid, new_mid, disable_notification=True)
        except Exception:
            pass
    return new_mid, is_media_msg


def _broadcast_announcement_to_users(ann: dict, is_repeat: bool = False) -> dict:
    """دفع الإعلان العائم المتطور لجميع المستخدمين المعتمدين والمطور بدون سبام"""
    if not isinstance(ann, dict) or not ann.get("id"):
        return {"sent": 0, "pinned": 0}
    users = load_users()
    targets: set[int] = {SUPER_ADMIN_ID}
    for uid_s, u in users.items():
        if isinstance(u, dict) and u.get("status") == "approved":
            try:
                targets.add(int(u.get("id") or uid_s))
            except Exception:
                pass

    d_mode = str(ann.get("delivery_mode") or "animated_card")
    rep_beh = str(ann.get("repeat_behavior") or "replace")
    need_media = (
        d_mode in ("animated_card", "photo_card")
        and not (is_repeat and rep_beh == "edit_live")
    )
    rendered_media = None
    if need_media:
        try:
            rendered_media = render_announcement_media(
                ann, animated=(d_mode == "animated_card"), allow_browser=True
            )
        except Exception:
            rendered_media = None

    sent_map: dict[int, int] = {}
    media_cids: set[int] = set()
    pinned = 0
    for cid in targets:
        try:
            mid, is_m = _send_announcement_to_chat(
                cid, ann, is_repeat=is_repeat, rendered_media=rendered_media
            )
            if mid:
                sent_map[int(cid)] = int(mid)
                if is_m:
                    media_cids.add(int(cid))
                if ann.get("pin_in_chat") and not is_repeat:
                    pinned += 1
        except Exception:
            pass
    if sent_map:
        record_announcement_sent_chats(ann["id"], sent_map, media_cids=media_cids)
    return {"sent": len(sent_map), "pinned": pinned, "media": bool(rendered_media)}


def _render_theme_config_view() -> tuple[str, types.InlineKeyboardMarkup]:
    tcfg = get_theme_config()
    ce_on = bool(tcfg.get("custom_emojis_enabled", True))
    ems = tcfg.get("emojis") or {}
    slot_labels = {
        "rocket": "🚀 أيقونة الميزة / الإطلاق",
        "spark": "✨ أيقونة التوقيت / التمييز",
        "check": "✅ أيقونة التأكيد",
        "shield": "🛡️ أيقونة الحماية / الأمان",
        "fb": "📘 أيقونة فيسبوك",
        "proxy": "🌐 أيقونة البروكسي",
        "alert": "⚡ أيقونة التنبيه",
    }
    lines = [
        "🎨 <b>مظهر البوت وأيقونات Custom Emoji (Bot API 9.4)</b>",
        "<blockquote>تعمل الألوان المدمجة (أخضر/أزرق/أحمر) والبطاقات المتحركة لجميع البوتات مجاناً.\n"
        "أما أيقونات <code>custom_emoji_id</code> فتعمل تلقائياً إذا كان لدى مالك البوت Telegram Premium أو اسم مستخدم Fragment (ويتراجع البوت بأمان عند عدم توفرها).</blockquote>",
        f"🧩 <b>الحالة:</b> {'🟢 مفعّلة' if ce_on else '⏸️ معطّلة'}",
    ]
    mk = types.InlineKeyboardMarkup(row_width=2)
    mk.row(
        _btn(
            f"🧩 Custom Emoji: {'مفعّل ✅' if ce_on else 'معطّل ❌'}",
            style="success" if ce_on else "primary",
            callback_data="ann_ce_tog",
        )
    )
    for k, lbl in slot_labels.items():
        val = ems.get(k) or "غير مضبوط"
        lines.append(f"• {lbl}: <code>{esc(val)}</code>")
        mk.row(_btn(f"{lbl} ({'✅' if ems.get(k) else '➕'})", callback_data=f"ann_ce_set_{k}"))
    mk.row(_btn("🔙 مركز الإعلانات", style="primary", callback_data="menu_announcements"))
    return "\n".join(lines), mk


def _render_announcements_view() -> tuple[str, types.InlineKeyboardMarkup]:
    items = list_announcements(only_active=False)
    active_cnt = sum(1 for a in items if a.get("is_effectively_active"))
    lines = [
        "📢 <b>مركز الإعلانات العائمة والبطاقات المتطورة</b>",
        f"<blockquote>✨ <b>النشطة:</b> {active_cnt} · <b>المحفوظة:</b> {len(items)}\n"
        "🎞️ يدعم GIF المتحركة (Chromium+HTML5) وأزرار Bot API 9.4 الملونة بدون سبام تثبيت.</blockquote>",
    ]
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(
        _btn("➕ إنشاء إعلان جديد", style="success", icon_key="rocket", callback_data="ann_new"),
        _btn("🎨 الأيقونات والمظهر", style="primary", callback_data="ann_theme_menu"),
    )
    if not items:
        lines.append("<i>لا توجد إعلانات مسجلة بعد. اضغط إنشاء إعلان جديد.</i>")
    else:
        for a in items[:10]:
            st_ico = "🟢" if a.get("is_effectively_active") else ("⌛" if a.get("is_expired") else "⏸️")
            dm_lbl = {"animated_card": "🎞️ GIF", "photo_card": "🖼️ HD", "smart_text": "💬 ذكي"}.get(a.get("delivery_mode"), "🎞️")
            lines.append(
                f"{st_ico} <b>[{esc(a.get('badge'))}] {esc(a.get('title'))}</b> · {dm_lbl} · ⏳ {esc(a.get('remaining_label'))}"
            )
            markup.row(
                _btn(
                    f"{st_ico} {str(a.get('title') or '')[:20]}",
                    style="success" if a.get("is_effectively_active") else None,
                    callback_data=f"ann_view_{a['id']}",
                ),
                _btn("🗑️ حذف", style="danger", callback_data=f"ann_del_{a['id']}"),
            )
    markup.row(
        _btn("🔄 تحديث", style="primary", callback_data="menu_announcements"),
        _btn("🔙 الرئيسية", callback_data="back_to_main"),
    )
    txt = "\n".join(lines)
    if len(txt) > 3950:
        txt = txt[:3920] + "\n..."
    return txt, markup


def _render_announcement_detail_view(ann_id: str) -> tuple[str, types.InlineKeyboardMarkup]:
    a = get_announcement_by_id(ann_id)
    if not a:
        return "⚠️ الإعلان غير موجود أو تم حذفه.", _back_home_markup("menu_announcements")
    st_lbl = "🟢 نشط" if a.get("is_effectively_active") else ("⌛ منتهي" if a.get("is_expired") else "⏸️ متوقف")
    dm_lbl = DELIVERY_MODES.get(a.get("delivery_mode"), "🎞️ بطاقة GIF متحركة")
    rb_lbl = REPEAT_BEHAVIORS.get(a.get("repeat_behavior"), "♻️ استبدال نظيف")
    eff_lbl = (EFFECT_PRESETS.get(a.get("effect_preset")) or ("بدون تأثير", ""))[0]
    pin_lbl = "📌 مفعّل (مرة واحدة)" if a.get("pin_in_chat") else "🪟 معطّل (بطاقة عائمة نظيفة)"
    txt = (
        f"📢 <b>{esc(a.get('title'))}</b> · {st_lbl}\n"
        f"<blockquote>{esc(a.get('body'))}</blockquote>\n"
        f"🎨 <b>العرض:</b> {esc(dm_lbl)}\n"
        f"🔁 <b>التكرار ({esc(a.get('repeat_label'))}):</b> {esc(rb_lbl)}\n"
        f"📌 <b>التثبيت:</b> {pin_lbl} ({len(a.get('sent_chats') or {})} محادثة) | 🎆 <b>التأثير:</b> {eff_lbl}\n"
        f"⏳ <b>المتبقي:</b> {esc(a.get('remaining_label'))} | 📣 <b>البث:</b> {a.get('push_count', 1)}x"
    )
    if len(txt) > 3950:
        txt = txt[:3920] + "\n..."
    mk = types.InlineKeyboardMarkup(row_width=2)
    tog_lbl = "⏸️ إيقاف" if a.get("active") else "▶️ تفعيل"
    mk.row(
        _btn(tog_lbl, style="primary" if a.get("active") else "success", callback_data=f"ann_tog_{ann_id}"),
        _btn("🚀 بث مباشر الآن", style="success", icon_key="rocket", callback_data=f"ann_push_{ann_id}"),
    )
    mk.row(
        _btn("🎨 تبديل نوع البطاقة", style="primary", callback_data=f"ann_dm_{ann_id}"),
        _btn("🔁 تبديل سلوك التكرار", style="primary", callback_data=f"ann_rb_{ann_id}"),
    )
    mk.row(
        _btn(f"📌 التثبيت: {'نعم' if a.get('pin_in_chat') else 'لا (أنظف)'}", callback_data=f"ann_pin_{ann_id}"),
        _btn(f"🎆 التأثير: {eff_lbl[:14]}", callback_data=f"ann_eff_{ann_id}"),
    )
    mk.row(
        _btn("⏱️ 1 ساعة", callback_data=f"ann_dur_{ann_id}_3600"),
        _btn("⏱️ 24 ساعة", callback_data=f"ann_dur_{ann_id}_86400"),
        _btn("♾️ دائم", callback_data=f"ann_dur_{ann_id}_0"),
    )
    mk.row(
        _btn("🔁 كل 5د", callback_data=f"ann_rep_{ann_id}_300"),
        _btn("🔁 كل ساعة", callback_data=f"ann_rep_{ann_id}_3600"),
        _btn(f"🚪 عند الفتح: {'✅' if a.get('repeat_on_open') else '❌'}", callback_data=f"ann_rop_{ann_id}"),
    )
    mk.row(
        _btn("🗑️ حذف الإعلان", style="danger", callback_data=f"ann_del_{ann_id}"),
        _btn("🔙 الإعلانات", callback_data="menu_announcements"),
    )
    return txt, mk


# ----------------- قسم أدوات فيسبوك المجمعة ودليل الأرباح وبوابات الميزات -----------------

def render_fb_tools_text(user_id: int) -> str:
    """واجهة مجمعة لجميع تفاعلات وأدوات فيسبوك لتقليل الزحام والتشويش في القائمة الرئيسية"""
    st = get_user_state(user_id)
    lines = [
        "📘 <b>أدوات ومهام تفاعل فيسبوك | Facebook Tools</b>",
        "━━━━━━━━━━━━━━━━━━━━",
        f"🎯 <b>الرابط المستهدف:</b> <code>{esc(st.get('target_url', '')[:55])}</code>",
    ]
    p_use = is_super_admin(user_id) or has_permission(user_id, "can_use_accounts")
    usable_accs = get_usable_accounts_for_user(user_id) if p_use else []
    sel_name = "جميع الحسابات المتاحة"
    if st.get("selected_acc") == "multi":
        sel_name = f"{len(st.get('selected_accs') or [])} حسابات محددة"
    elif st.get("selected_acc") != "all":
        matched = next((a for a in usable_accs if a["id"] == st.get("selected_acc")), None)
        sel_name = matched["name"] if matched else "جميع الحسابات"
    lines.append(f"👤 <b>الحساب المنفذ:</b> {esc(sel_name)}")

    react_ico = "✅" if st.get("like") else "❌"
    react_type = REACTION_ICONS.get(st.get("reaction_type"), "👍 إعجاب")
    p_tag = "رابط مخصص" if st.get("react_post_url") else f"منشور {st.get('react_post_index', 1)}"
    lines.append(f"💖 <b>التفاعل:</b> {react_type} [{react_ico}] ({p_tag})")

    cmt_ico = "✅" if st.get("comment") else "❌"
    c_snip = esc((st.get("comment_text") or "").strip()[:30]) or "بدون نص"
    lines.append(f"💬 <b>التعليق:</b> '{c_snip}' [{cmt_ico}] (منشور {st.get('comment_post_index', 1)})")

    int_ico = "✅" if st.get("interact_cmt") else "❌"
    lines.append(f"🎯 <b>الرد على تعليق محدد:</b> [{int_ico}]")

    fr_ico = "✅" if st.get("friend") else "❌"
    fl_ico = "✅" if st.get("follow") else "❌"
    lines.append(f"👥 <b>طلب صداقة:</b> [{fr_ico}] | 🔔 <b>متابعة:</b> [{fl_ico}]")

    msg_ico = "✅" if st.get("message") else "❌"
    m_snip = esc((st.get("message_text") or "").strip()[:20]) or "بدون نص"
    lines.append(f"✉️ <b>رسالة خاصة:</b> '{m_snip}' [{msg_ico}]")

    rep_p = "✅" if st.get("report_post") else "❌"
    rep_u = "✅" if st.get("report_profile") else "❌"
    blk = "✅" if st.get("block") else "❌"
    lines.append(f"🛡️ <b>بلاغ منشور:</b> [{rep_p}] | 🛡️ <b>بلاغ حساب:</b> [{rep_u}] | 🚫 <b>حظر:</b> [{blk}]")
    lines.append("━━━━━━━━━━━━━━━━━━━━")
    lines.append("🎛️ <i>اضغط على أي أداة لتفعيلها [✅] أو تعديل نصها وخياراتها:</i>")
    return "\n".join(lines)


def render_fb_tools_markup(user_id: int) -> types.InlineKeyboardMarkup:
    markup = types.InlineKeyboardMarkup(row_width=2)
    st = get_user_state(user_id)
    is_dev = is_super_admin(user_id)

    p_use = is_dev or has_permission(user_id, "can_use_accounts")
    p_react = is_dev or has_permission(user_id, "can_react")
    p_cmt = is_dev or has_permission(user_id, "can_comment")
    p_int = is_dev or has_permission(user_id, "can_interact_comments")
    p_fr = is_dev or has_permission(user_id, "can_friend_follow")
    p_msg = is_dev or has_permission(user_id, "can_message")
    p_rep = is_dev or has_permission(user_id, "can_report")
    p_exec = is_dev or has_permission(user_id, "can_execute")

    usable_accs = get_usable_accounts_for_user(user_id) if p_use else []
    sel_name = "جميع الحسابات"
    if st.get("selected_acc") == "multi":
        sel_name = f"{len(st.get('selected_accs') or [])} محددة"
    elif st.get("selected_acc") != "all":
        matched = next((a for a in usable_accs if a["id"] == st.get("selected_acc")), None)
        sel_name = matched["name"] if matched else "جميع الحسابات"

    markup.row(
        types.InlineKeyboardButton(f"👤 المنفذ: {sel_name}", callback_data="menu_select_acc"),
        types.InlineKeyboardButton("🔗 تعديل الرابط المستهدف", callback_data="menu_set_url")
    )
    if p_react:
        like_st = "✅" if st.get("like") else "❌"
        react_lbl = REACTION_ICONS.get(st.get("reaction_type"), "👍 إعجاب")
        p_tag = "رابط مخصص" if st.get("react_post_url") else f"منشور {st.get('react_post_index', 1)}"
        markup.row(
            types.InlineKeyboardButton(f"{react_lbl} [{like_st}]", callback_data="toggle_react_main"),
            types.InlineKeyboardButton(f"⚙️ خيارات ({p_tag})", callback_data="menu_wizard_react")
        )
    if p_cmt:
        cmt_st = "✅" if st.get("comment") else "❌"
        c_tag = "رابط مخصص" if st.get("comment_post_url") else f"منشور {st.get('comment_post_index', 1)}"
        markup.row(
            types.InlineKeyboardButton(f"💬 تعليق [{cmt_st}]", callback_data="toggle_comment_main"),
            types.InlineKeyboardButton(f"✏️ نص ومنشور ({c_tag})", callback_data="menu_wizard_comment")
        )
    if p_int:
        cmt_int_tag = "✅" if st.get("interact_cmt") else "❌"
        markup.row(
            types.InlineKeyboardButton(f"🎯 رد على تعليق [{cmt_int_tag}]", callback_data="toggle_cmt_int_main"),
            types.InlineKeyboardButton("⚙️ هدف الرد", callback_data="menu_cmt_interact")
        )
    if p_fr:
        fr_tag = "✅" if st.get("friend") else "❌"
        fl_tag = "✅" if st.get("follow") else "❌"
        markup.row(
            types.InlineKeyboardButton(f"➕ طلب صداقة [{fr_tag}]", callback_data="toggle_friend"),
            types.InlineKeyboardButton(f"🔔 متابعة [{fl_tag}]", callback_data="toggle_follow")
        )
        cfr_tag = "✅" if st.get("cancel_friend") else "❌"
        unfl_tag = "✅" if st.get("unfollow") else "❌"
        markup.row(
            types.InlineKeyboardButton(f"❌ إلغاء الصداقة [{cfr_tag}]", callback_data="toggle_cancel_friend"),
            types.InlineKeyboardButton(f"🔕 إلغاء المتابعة [{unfl_tag}]", callback_data="toggle_unfollow")
        )
    if p_msg:
        msg_st = "✅" if st.get("message") else "❌"
        raw_m = (st.get("message_text") or "").strip()
        msg_snip = (raw_m[:12] + "..") if len(raw_m) > 12 else (raw_m or "بدون نص")
        markup.row(
            types.InlineKeyboardButton(f"✉️ رسالة خاصة [{msg_st}]", callback_data="toggle_msg_main"),
            types.InlineKeyboardButton(f"✏️ النص ({msg_snip})", callback_data="menu_wizard_message")
        )
    if p_rep:
        rep_p_tag = "✅" if st.get("report_post") else "❌"
        rep_u_tag = "✅" if st.get("report_profile") else "❌"
        markup.row(
            types.InlineKeyboardButton(f"🛡️ بلاغ منشور [{rep_p_tag}]", callback_data="toggle_rep_post"),
            types.InlineKeyboardButton(f"🛡️ بلاغ حساب [{rep_u_tag}]", callback_data="toggle_rep_profile")
        )
        blk_tag = "✅" if st.get("block") else "❌"
        markup.row(
            types.InlineKeyboardButton(f"🚫 حظر الحساب [{blk_tag}]", callback_data="toggle_block"),
            types.InlineKeyboardButton("⚙️ تفاصيل البلاغ والسبب", callback_data="menu_rep_config")
        )
    if p_exec:
        wait_ico = "✅" if st.get("wait_for_hitl", True) else "❌"
        markup.row(
            _btn("🚀 بدء تنفيذ المهام الآن", style="success", icon_key="rocket", callback_data="action_launch"),
            _btn(f"⏳ انتظار التحقق [{wait_ico}]", style="primary" if st.get("wait_for_hitl", True) else None, callback_data="toggle_wait_hitl"),
        )
    markup.row(types.InlineKeyboardButton("🔙 العودة للوحة الرئيسية", callback_data="back_to_main"))
    return markup


def render_fb_tools_text_and_markup(user_id: int) -> tuple[str, types.InlineKeyboardMarkup]:
    return render_fb_tools_text(user_id), render_fb_tools_markup(user_id)


def render_earn_guide_text(user_id: int) -> str:
    """دليل مبسط بشري يشرح فكرة التوريد والربح بالريال اليمني بوضوح تام"""
    eco = load_economy_settings()
    act_rew = int(eco.get("active_account_reward", 1) or 1)
    y_per_pt = int(eco.get("yer_per_point", 10) or 10)
    ref_rew = int(eco.get("referral_reward", 4) or 4)
    inc_yer = int(eco.get("incomplete_account_yer", 5) or 5)

    return (
        "💡 <b>دليل إنشاء حسابات فيسبوك وكسب الأرباح | Guide & Earnings</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "👋 <b>أهلاً بك يا بطل! الفكرة بكل بساطة:</b>\n"
        "البوت يشتري منك حسابات فيسبوك صالحة لاستخدامها في التفاعل والمهام، ويدفع لك فوراً بالريال اليمني أو النقاط لكل حساب تضيفه ويعمل بنجاح.\n\n"
        "💰 <b>جدول الأرباح والأسعار:</b>\n"
        f"• 🌟 <b>الحساب المكتمل عالي الجودة:</b> <b>{act_rew * y_per_pt} ريال يمني</b> (+{act_rew} نقطة) فوراً!\n"
        "  <i>(المواصفات: اسم عربي ثلاثي، صورة شخصية، غلاف، سيرة ذاتية، ومنشورين على الأقل).</i>\n"
        f"• ⚠️ <b>الحسابات المنشأة حديثاً:</b> تحتسب بـ <b>{inc_yer} ر.ي</b> بعد 5 إنذارات، ويمكنك إكمال بروفايلها لرفع سعرك إلى {act_rew * y_per_pt} ر.ي دائماً.\n"
        f"• 🎁 <b>أرباح دعوة الأصدقاء:</b> تكسب <b>+{ref_rew * y_per_pt} ريال</b> (+{ref_rew} نقاط) عند أول حساب نشط يضيفه كل شخص تدعوه عبر كودك!\n\n"
        "🛠️ <b>خطوات إنشاء حسابات مقبولة وسريعة:</b>\n"
        "1. افتح تطبيق فيسبوك أو المتصفح.\n"
        "2. أنشئ حساباً باسم ثلاثي عربي طبيعي (مثال: أحمد عبد الله، محمد غالب).\n"
        "3. ضع صورة شخصية عادية وصورة غلاف من هاتفك.\n"
        "4. انشر منشورين بسيطين (أدعية، صور طبيعية، تحية).\n"
        "5. احفظ الإيميل أو رقم الهاتف وكلمة المرور.\n\n"
        "📥 <b>طريقة إضافة الحساب واستلام أرباحك:</b>\n"
        "1. اضغط زر <b>[➕ إضافة حساب فيسبوك]</b> أدناه.\n"
        "2. أدخل اسماً للحساب، ثم الإيميل، ثم كلمة المرور.\n"
        "3. سيفحص البوت الحساب؛ فإذا كان مباشراً يُضاف لرصيدك فوراً!\n"
        "4. إذا طلب فيسبوك تأكيد لغز إنسان، سيفتح لك البوت <b>[الشاشة الحية]</b> على جوالك لتحله بيدك بوضوح، وفور نجاحه يُسجل الحساب وتكسب أرباحك!\n\n"
        "💵 <b>كيف تستلم فلوسك؟</b>\n"
        "• اضغط <b>[💰 محفظتي وسجل أرباحي]</b> لمعاينة رصيدك.\n"
        "• اضغط <b>[💵 سحب الأرباح والتواصل مع المطور]</b> لتحديد طريقة التحويل (الكريمي، النجم، أو محفظة جوال) ويتم تحويل فلوسك فوراً!"
    )


def render_earn_guide_markup(user_id: int) -> types.InlineKeyboardMarkup:
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(
        types.InlineKeyboardButton("➕ إضافة حساب فيسبوك الآن", callback_data="act_add_acc"),
        types.InlineKeyboardButton("💰 محفظتي وسجل أرباحي", callback_data="menu_wallet")
    )
    markup.row(
        types.InlineKeyboardButton("💵 سحب الأرباح والتواصل مع المطور", callback_data="menu_support"),
        types.InlineKeyboardButton("🎁 روابط الدعوة وكسب الأرباح", callback_data="menu_referral")
    )
    markup.row(types.InlineKeyboardButton("🔙 العودة للوحة الرئيسية", callback_data="back_to_main"))
    return markup


def render_earn_guide_text_and_markup(user_id: int) -> tuple[str, types.InlineKeyboardMarkup]:
    return render_earn_guide_text(user_id), render_earn_guide_markup(user_id)


def render_feature_gates_text(user_id: int) -> str:
    """عرض لوحة التحكم المركزية ببوابات الميزات للمطور والأدمن"""
    gates = load_feature_gates()
    lines = [
        "🎛️ <b>إدارة وبوابات الميزات (Feature Gates)</b>",
        "━━━━━━━━━━━━━━━━━━━━",
        "تحكم سيادي كامل بظهور وتسعير وصلاحية كل ميزة حالية أو مستقبلية:",
        "• 🌍 <b>عامة:</b> متاحة ومفتوحة لجميع المستخدمين.",
        "• 👑 <b>إدارة:</b> مقتصرة على المطور الرئيسي ونوابه فقط.",
        "• 👥 <b>محددين:</b> مقيدة بأرقام معرفات (User IDs) تختارها بنفسك.",
        "• 💰 <b>التسعير:</b> مجانية أو تخصم نقاطاً بالريال اليمني عند الاستخدام.",
        "━━━━━━━━━━━━━━━━━━━━",
        f"📦 <b>عدد الميزات المسجلة:</b> {len(gates)} ميزة"
    ]
    return "\n".join(lines)


def render_feature_gates_markup(user_id: int) -> types.InlineKeyboardMarkup:
    markup = types.InlineKeyboardMarkup(row_width=1)
    gates = load_feature_gates()
    scope_labels = {"public": "🌍 عامة", "admins": "👑 إدارة", "specific": "👥 محددين"}
    for fid, f in gates.items():
        sc = scope_labels.get(f.get("access_scope"), "👑 إدارة")
        pr = f"💰 {f.get('points_cost', 0)}ن" if f.get("pricing_type") == "points" else "🆓 مجاني"
        st_ico = "🟢" if f.get("status") == "active" else ("⏳" if f.get("status") == "coming_soon" else "🔴")
        lbl = f"{st_ico} {f.get('title', fid)[:26]} [{sc} | {pr}]"
        markup.add(types.InlineKeyboardButton(lbl, callback_data=f"fg_view_{fid}"))

    markup.add(types.InlineKeyboardButton("➕ تسجيل ميزة جديدة للمستقبل", callback_data="fg_new_custom"))
    markup.add(types.InlineKeyboardButton("🔙 العودة للوحة الرئيسية", callback_data="back_to_main"))
    return markup


def render_feature_gates_text_and_markup(user_id: int) -> tuple[str, types.InlineKeyboardMarkup]:
    return render_feature_gates_text(user_id), render_feature_gates_markup(user_id)


def render_feature_detail_view(user_id: int, feature_id: str) -> tuple[str, types.InlineKeyboardMarkup]:
    f = get_feature(feature_id)
    if not f:
        return "⚠️ الميزة غير موجودة.", types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 رجوع", callback_data="menu_feature_gates"))

    scope_labels = {"public": "🌍 مفتوحة للعامة", "admins": "👑 للإدارة والمطور فقط", "specific": "👥 لأشخاص محددين بالمعرف"}
    status_labels = {"active": "🟢 نشطة ومتاحة", "disabled": "🔴 معطلة مؤقتاً", "beta": "🧪 تجريبية", "coming_soon": "⏳ قيد التطوير وقريباً"}
    pricing_labels = {"free": "🆓 مجانية بالكامل", "points": f"💰 مدفوعة ({f.get('points_cost', 1)} نقطة لكل استخدام)"}

    allowed = f.get("allowed_user_ids") or []
    allowed_snip = ", ".join(f"<code>{u}</code>" for u in allowed[:8]) if allowed else "لا يوجد مستخدمون محددون بعد"

    txt = (
        f"🎛️ <b>بوابة ميزة: {esc(f.get('title', feature_id))}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"🏷️ <b>المعرف البرمجي:</b> <code>{feature_id}</code>\n"
        f"📁 <b>التصنيف:</b> {esc(f.get('category', 'عام'))}\n"
        f"📝 <b>الوصف:</b> <i>{esc(f.get('description', ''))}</i>\n\n"
        f"⚡ <b>الحالة الحالية:</b> {status_labels.get(f.get('status'), f.get('status'))}\n"
        f"🔀 <b>نطاق الوصول:</b> {scope_labels.get(f.get('access_scope'), f.get('access_scope'))}\n"
        f"💸 <b>التسعير:</b> {pricing_labels.get(f.get('pricing_type'), f.get('pricing_type'))}\n"
        f"👥 <b>المستخدمون المصرح لهم:</b> {allowed_snip}\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "<i>اضغط على الخيارات أدناه لتعديل البوابة فوراً:</i>"
    )

    mk = types.InlineKeyboardMarkup(row_width=2)
    next_scope_label = "تبديل الوصول (عامة/إدارة/محددين)"
    mk.row(types.InlineKeyboardButton(f"🔀 {next_scope_label}", callback_data=f"fg_scope_{feature_id}"))
    mk.row(
        types.InlineKeyboardButton(f"💸 تبديل التسعير ({'مجاني' if f.get('pricing_type') == 'points' else 'نقاط'})", callback_data=f"fg_price_{feature_id}"),
        types.InlineKeyboardButton(f"⚡ تبديل الحالة ({status_labels.get(f.get('status'), '')[:8]})", callback_data=f"fg_status_{feature_id}")
    )
    mk.row(
        types.InlineKeyboardButton("👤 إضافة مستخدم بالمعرف (ID)", callback_data=f"fg_adduser_{feature_id}"),
        types.InlineKeyboardButton("🔙 قائمة الميزات", callback_data="menu_feature_gates")
    )
    return txt, mk


# ----------------- مركز البريد المؤقت والدائم وخزنة الاسترجاع -----------------
def render_tempmail_main_view(user_id: int) -> tuple[str, types.InlineKeyboardMarkup]:
    active = tm_m.get_user_active_mailbox(user_id)
    history = tm_m.get_user_history(user_id, limit=20)
    trash = tm_m.list_trash_emails_admin(user_id) if (is_super_admin(user_id) or has_admin_capability(user_id, "radar_users")) else []
    is_dev = is_super_admin(user_id) or has_admin_capability(user_id, "radar_users")

    if active and active.get("email"):
        em = active["email"]
        prov = active.get("provider", "1timetech")
        dom = active.get("domain", em.split("@")[-1] if "@" in em else "")
        created = str(active.get("created_at", ""))[:19].replace("T", " ")
        txt = (
            f"📧 <b>مركز البريد السحابي واستخراج أكواد التحقق</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📬 <b>البريد النشط الحالي:</b>\n"
            f"<code>{esc(em)}</code> <i>(اضغط عليه للنسخ 📋)</i>\n\n"
            f"🏢 <b>المزود:</b> <code>{esc(prov)}</code> | 🌐 <b>النطاق:</b> <code>{esc(dom)}</code>\n"
            f"⏱️ <b>تاريخ الإنشاء:</b> {created}\n"
            f"🔔 <b>المراقبة واستخراج OTP:</b> 🟢 مفعّل ومؤتمت\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"💡 انسخ هذا البريد لتسجيل حسابات فيسبوك أو المنصات الأخرى، ثم اضغط <b>فحص الوارد</b> لجلب كود الـ OTP ورابط التفعيل فوراً."
        )
    else:
        txt = (
            f"📧 <b>مركز البريد السحابي واستخراج أكواد التحقق</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"⚪ <b>لا يوجد بريد نشط حالياً.</b>\n\n"
            f"اختر <b>إنشاء بريد عشوائي</b> أو <b>إنشاء بريد مخصص</b> من الأزرار أدناه لتوليد بريدك فوراً واستلام الأكواد عليه."
        )

    mk = types.InlineKeyboardMarkup(row_width=2)
    mk.row(
        _btn("🎲 إنشاء بريد عشوائي", style="primary", icon_key="spark", callback_data="tm_new_rand"),
        _btn("✏️ إنشاء بريد مخصص", style="primary", icon_key="spark", callback_data="tm_pick_dom")
    )
    if active and active.get("email"):
        mk.row(
            _btn("🔄 فحص الوارد الآن", style="success", icon_key="spark", callback_data="tm_inbox"),
            _btn(f"📜 أرشيفي المحفوظ ({len(history)})", callback_data="tm_history")
        )
        mk.row(
            _btn("🗑️ حذف البريد الحالي (للسلة)", callback_data="tm_del_active")
        )
    else:
        if history:
            mk.row(_btn(f"📜 أرشيفي المحفوظ ({len(history)})", callback_data="tm_history"))

    if is_dev:
        mk.row(
            _btn("🛰️ رادار بريد المستخدمين (للمطور)", callback_data="tm_admin_all"),
            _btn(f"♻️ سلة المحذوفات والاسترجاع ({len(trash)})", callback_data="tm_admin_trash")
        )

    mk.row(types.InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="back_to_main"))
    return txt, mk


def render_tempmail_pick_domain_view(user_id: int, page: int = 0) -> tuple[str, types.InlineKeyboardMarkup]:
    domains = tm_m.get_available_domains()
    per_page = 8
    total_pages = max(1, (len(domains) + per_page - 1) // per_page)
    page = max(0, min(page, total_pages - 1))

    start_idx = page * per_page
    page_domains = domains[start_idx:start_idx + per_page]

    txt = (
        f"✏️ <b>إنشاء بريد مخصص (Custom Mailbox)</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🌐 اختر النطاق (Domain) الذي تريده من القائمة أدناه:\n"
        f"الصفحة: {page + 1} من {total_pages} | إجمالي النطاقات: {len(domains)}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💡 بعد اختيار النطاق سيُطلب منك إدخال الاسم الذي تريده قبل @."
    )

    mk = types.InlineKeyboardMarkup(row_width=2)
    dom_btns = []
    for item in page_domains:
        d = item["domain"]
        dom_btns.append(types.InlineKeyboardButton(f"@{d}", callback_data=f"tm_seldom_{d}"))

    for i in range(0, len(dom_btns), 2):
        mk.row(*dom_btns[i:i+2])

    nav_row = []
    if page > 0:
        nav_row.append(types.InlineKeyboardButton("⬅️ السابق", callback_data=f"tm_dompage_{page - 1}"))
    if page < total_pages - 1:
        nav_row.append(types.InlineKeyboardButton("التالي ➡️", callback_data=f"tm_dompage_{page + 1}"))
    if nav_row:
        mk.row(*nav_row)

    mk.row(types.InlineKeyboardButton("🔙 رجوع لإدارة البريد", callback_data="menu_tempmail"))
    return txt, mk


def render_tempmail_inbox_view(user_id: int, email: str | None = None) -> tuple[str, types.InlineKeyboardMarkup]:
    active = tm_m.get_user_active_mailbox(user_id)
    target_email = email or (active.get("email") if active else None)
    if not target_email:
        return render_tempmail_main_view(user_id)

    messages = tm_m.check_inbox(user_id, target_email)
    em_hash = hashlib.sha1(target_email.encode()).hexdigest()[:8]
    is_active_box = active and (active.get("email", "").lower() == target_email.lower())

    mk = types.InlineKeyboardMarkup(row_width=1)

    status_tag = "🟢 <b>(البريد النشط حالياً)</b>" if is_active_box else "⚪ <b>(بريد مؤرشف)</b>"

    if not messages:
        txt = (
            f"📭 <b>صندوق الوارد:</b> <code>{esc(target_email)}</code>\n"
            f"{status_tag}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"⚪ لا توجد رسائل واردة حالياً.\n"
            f"بانتظار وصول رسائل التحقق والتفعيل...\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"💡 اضغط <b>تحديث وفحص الآن</b> بعد طلب الكود من فيسبوك أو أي منصة."
        )
    else:
        txt = (
            f"📬 <b>صندوق الوارد:</b> <code>{esc(target_email)}</code>\n"
            f"{status_tag}\n"
            f"عدد الرسائل المؤرشفة: <b>{len(messages)}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
        )
        for idx, m in enumerate(messages[:10], start=1):
            sender = esc(m.get("sender") or "مجهول")
            subj = esc(m.get("subject") or "بدون عنوان")
            otp = m.get("otp_code")
            links = m.get("links") or []
            date = esc(str(m.get("date") or ""))

            txt += f"<b>[{idx}] من:</b> {sender}\n"
            txt += f"📌 <b>الموضوع:</b> {subj}\n"
            if date:
                txt += f"⏱️ <b>الوقت:</b> {date}\n"
            if otp:
                txt += f"🔑 <b>كود التحقق (OTP):</b> <code>{esc(otp)}</code> <i>(اضغط للنسخ)</i>\n"
            if links:
                txt += f"🔗 <b>رابط التفعيل:</b> <a href=\"{esc(links[0])}\">اضغط للتأكيد المباشر</a>\n"
            txt += "━━━━━━━━━━━━━━━━━━━━\n"

            if otp:
                mk.row(types.InlineKeyboardButton(f"📋 نسخ كود OTP: {otp}", callback_data=f"tm_copyotp_{otp}"))
            if links:
                mk.row(types.InlineKeyboardButton("🌐 فتح رابط التفعيل", url=links[0]))

    action_row = [
        _btn("🔄 تحديث وفحص الآن", style="primary", icon_key="spark", callback_data=f"tm_inbox_{em_hash}")
    ]
    if not is_active_box:
        action_row.append(_btn("🟢 جعله البريد النشط", callback_data=f"tm_switch_{em_hash}"))
    mk.row(*action_row)
    mk.row(
        types.InlineKeyboardButton("📜 أرشيف كافة الإيميلات", callback_data="menu_tm_history"),
        types.InlineKeyboardButton("🔙 إدارة البريد", callback_data="menu_tempmail")
    )
    return txt, mk


def render_tempmail_history_view(user_id: int) -> tuple[str, types.InlineKeyboardMarkup]:
    history = tm_m.get_user_history(user_id, limit=15)
    active = tm_m.get_user_active_mailbox(user_id)
    active_email = (active.get("email") or "").lower() if active else ""

    txt = (
        f"📜 <b>أرشيف وسجل كافة إيميلاتي المحفوظة</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💡 لكل إيميل صندوق بريد دائم ومستقل لحفظ رسائل التحقق وأكواد OTP إلى الأبد:\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
    )

    mk = types.InlineKeyboardMarkup(row_width=3)
    if not history:
        txt += "⚪ لا يوجد أي بريد محفوظ في أرشيفك حتى الآن."
    else:
        for idx, item in enumerate(history, start=1):
            em = item.get("email", "")
            msg_cnt = item.get("msg_count", 0)
            is_cur = em.lower() == active_email
            ico = "🟢 نشط" if is_cur else "⚪ سابق"
            cnt_str = f" | 📩 <b>{msg_cnt} رسائل</b>" if msg_cnt > 0 else " | 📭 فارغ"
            txt += f"{idx}. <code>{esc(em)}</code> ({ico}){cnt_str}\n"
            em_hash = hashlib.sha1(em.encode()).hexdigest()[:8]

            row_btns = [
                types.InlineKeyboardButton(f"📬 صندوق #{idx}" + (f" ({msg_cnt})" if msg_cnt else ""), callback_data=f"tm_viewbox_{em_hash}")
            ]
            if not is_cur:
                row_btns.append(types.InlineKeyboardButton(f" تفعيل #{idx}", callback_data=f"tm_switch_{em_hash}"))
            row_btns.append(types.InlineKeyboardButton(f"🗑️ حذف #{idx}", callback_data=f"tm_del_{em_hash}"))
            mk.row(*row_btns)

    mk.row(types.InlineKeyboardButton("🔙 رجوع لإدارة البريد", callback_data="menu_tempmail"))
    return txt, mk


def render_tempmail_admin_all_view(user_id: int) -> tuple[str, types.InlineKeyboardMarkup]:
    if not (is_super_admin(user_id) or has_admin_capability(user_id, "radar_users")):
        return "⛔ غير مصرح لك.", types.InlineKeyboardMarkup()
    emails = tm_m.list_all_emails_admin(user_id)

    txt = (
        f"🛰️ <b>رادار المطور لبريد المستخدمين الشامل</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"إجمالي الإيميلات المسجلة بالنظام: <b>{len(emails)}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
    )
    mk = types.InlineKeyboardMarkup(row_width=1)
    if not emails:
        txt += "⚪ لا توجد أي إيميلات مسجلة بعد."
    else:
        for idx, item in enumerate(emails[:15], start=1):
            em = item.get("email", "")
            uid = item.get("user_id", 0)
            is_act = item.get("is_active", False)
            status_ico = "🟢 نشط" if is_act else "⚪ محفوظ"
            txt += f"<b>{idx}.</b> <code>{esc(em)}</code>\n"
            txt += f"   👤 المستخدم ID: <code>{uid}</code> | {status_ico}\n"
            em_hash = hashlib.sha1(em.encode()).hexdigest()[:8]
            mk.row(types.InlineKeyboardButton(f"🔍 فحص وارد [{em[:18]}...]", callback_data=f"tm_admbox_{em_hash}"))

    mk.row(types.InlineKeyboardButton("🔙 رجوع لإدارة البريد", callback_data="menu_tempmail"))
    return txt, mk


def render_tempmail_admin_trash_view(user_id: int) -> tuple[str, types.InlineKeyboardMarkup]:
    if not (is_super_admin(user_id) or has_admin_capability(user_id, "radar_users")):
        return "⛔ غير مصرح لك.", types.InlineKeyboardMarkup()
    trash = tm_m.list_trash_emails_admin(user_id)

    txt = (
        f"♻️ <b>خزنة الاسترجاع وسلة المحذوفات (Recovery Vault)</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🛡️ <b>حماية كاملة من الضياع:</b> أي إيميل يحذفه المستخدم بالغلط يُحفظ هنا ويمكنك استرجاعه فوراً بضغطة واحدة!\n"
        f"عدد الإيميلات في السلة: <b>{len(trash)}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
    )
    mk = types.InlineKeyboardMarkup(row_width=1)
    if not trash:
        txt += "🟢 سلة المحذوفات نظيفة ولا توجد إيميلات محذوفة حالياً."
    else:
        for idx, item in enumerate(trash[:15], start=1):
            em = item.get("email", "")
            orig_uid = item.get("original_user_id", 0)
            del_at = str(item.get("deleted_at", ""))[:19].replace("T", " ")
            txt += f"<b>{idx}.</b> <code>{esc(em)}</code>\n"
            txt += f"   👤 المالك: <code>{orig_uid}</code> | ⏱️ حُذف في: {del_at}\n"
            em_hash = hashlib.sha1(em.encode()).hexdigest()[:8]
            mk.row(types.InlineKeyboardButton(f"♻️ استرجاع فوري [{em[:18]}...]", callback_data=f"tm_restore_{em_hash}"))

    mk.row(types.InlineKeyboardButton("🔙 رجوع لإدارة البريد", callback_data="menu_tempmail"))
    return txt, mk


def render_caller_id_view(user_id: int, result: dict | None = None) -> tuple[str, types.InlineKeyboardMarkup]:
    txt = (
        "📞 <b>كاشف الأرقام اليمنية 967 (معرفة هوية المتصل والشبكة)</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🔍 ابحث عن أي رقم يمني (يمن موبايل، يو، سبأفون، واي، الهاتف الثابت) لمعرفة اسم صاحبه والشبكة فوراً.\n"
        "⚡ يعتمد على تدوير متوازٍ بين سيرفرات سحابية فائقة السرعة مع تخزين محلي دائم.\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
    )
    if result:
        phone = result.get("phone", "")
        carrier = result.get("carrier", "شبكة اتصالات يمنية")
        carrier_type = result.get("carrier_type", "اتصالات محلية")
        region = result.get("region", "عموم الجمهورية اليمنية")
        names = result.get("names", [])
        is_valid = result.get("is_valid", True)
        source = result.get("source", "الدليل السحابي 🌐")

        if is_valid:
            primary_name = result.get("primary_name")
            records_count = result.get("records_count") or len(names)
            txt += (
                f"📱 <b>الرقم المستعلم عنه:</b> <code>{esc(phone)}</code>\n"
                f"🌐 <b>الشركة والشبكة:</b> <b>{esc(carrier)}</b> ({esc(carrier_type)})\n"
                f"📍 <b>النطاق الجغرافي:</b> <b>{esc(region)}</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
            )
            if primary_name and primary_name not in ("غير مسجل", "لم يتم العثور على اسم مسجل لهذا الرقم في قاعدة البيانات."):
                txt += f"👑 <b>الاسم الأكثر شهرة:</b> <b>{esc(primary_name)}</b>\n"
                if records_count > 0:
                    txt += f"📊 <b>عدد السجلات المكتشفة:</b> {records_count} اسماً مسجلاً\n"
                txt += "━━━━━━━━━━━━━━━━━━━━\n"
                txt += "📋 <b>أبرز الأسماء المسجلة لهذا الرقم:</b>\n"
                shown_count = 0
                for n in names:
                    if n and n != primary_name and shown_count < 12:
                        txt += f"• <code>{esc(n)}</code>\n"
                        shown_count += 1
                txt += f"\n⚡ <i>المصدر: {esc(source)}</i>\n"
            elif names and names[0] not in ("لم يتم العثور على اسم مسجل لهذا الرقم في قاعدة البيانات.", ""):
                txt += (
                    f"👤 <b>الأسماء المسجلة بالدليل ({len(names)}):</b>\n"
                )
                for n in names[:12]:
                    txt += f"• <code>{esc(n)}</code>\n"
                txt += f"\n⚡ <i>المصدر: {esc(source)}</i>\n"
            else:
                note = result.get("note") or f"الرقم صالح ويتبع شبكة {carrier}. لم يُعلن اسم مسجل له في السجلات السحابية العامة حتى الآن."
                txt += (
                    f"ℹ️ <b>حالة السجل:</b> <b>رقم يمني موثق وصالح 100%</b>\n"
                    f"<i>{esc(note)}</i>\n"
                )
            txt += "\n💡 <i>أرسل رقماً آخر للبحث عنه مباشرة، أو اضغط بحث جديد.</i>"
        else:
            txt += (
                f"❌ <b>تنبيه في صيغة الإدخال:</b> {esc(result.get('error', 'صيغة الرقم غير معتمدة'))}\n\n"
                f"💡 <i>أمثلة صحيحة:</i> <code>777123456</code> (يمن موبايل) أو <code>733123456</code> (يو) أو <code>01234567</code> (ثابت صنعاء)."
            )
    else:
        txt += (
            "👇 <b>طريقة الاستخدام:</b>\n"
            "اضغط على زر <b>🔍 بحث برقم جديد</b> أو اكتب الأمر مباشرة في الشات:\n"
            "<code>/num 777123456</code>\n"
            "أو أرسل الرقم اليمني فقط في الرسالة وسيتم الكشف عنه فوراً."
        )

    mk = types.InlineKeyboardMarkup(row_width=2)
    mk.row(
        _btn("🔍 بحث برقم جديد", style="primary", icon_key="spark", callback_data="caller_id_prompt"),
        _btn("🏠 القائمة الرئيسية", callback_data="back_to_main")
    )
    return txt, mk


def get_main_dashboard_markup(user_id: int) -> types.InlineKeyboardMarkup:
    markup = types.InlineKeyboardMarkup(row_width=2)
    st = get_user_state(user_id)

    is_dev = is_super_admin(user_id)
    cap_radar = has_admin_capability(user_id, "radar_users")
    cap_eco = has_admin_capability(user_id, "points_economy")
    cap_audit = has_admin_capability(user_id, "audit_logs")
    cap_pay = has_admin_capability(user_id, "payment_notices")
    cap_prox = has_admin_capability(user_id, "proxies")
    cap_bkp = has_admin_capability(user_id, "backups")
    cap_ann = has_admin_capability(user_id, "announcements")
    cap_pool = has_admin_capability(user_id, "accounts_pool")
    is_admin_any = is_dev or cap_radar or cap_eco or cap_audit or cap_pay or cap_prox or cap_bkp or cap_ann or cap_pool

    p_use = is_dev or cap_pool or has_permission(user_id, "can_use_accounts")
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

    active_anns = list_announcements(only_active=True)
    if active_anns:
        top_ann = active_anns[0]
        markup.row(
            _btn(
                f"✨ [{top_ann.get('badge', 'إعلان')}] {str(top_ann.get('title') or '')[:30]}",
                style="primary",
                icon_key="spark",
                callback_data=f"promo_view_{top_ann['id']}"
            )
        )

    wallet = get_user_wallet(user_id)
    has_any_action = any((p_react, p_cmt, p_int, p_fr, p_msg, p_rep))
    has_any_feature = any((is_admin_any, p_use, p_add, p_del, p_exec, has_any_action, p_inv))
    usable_accs = get_usable_accounts_for_user(user_id) if (p_use or p_exec) else []
    manageable_accs = get_manageable_accounts_for_user(user_id)

    # 1. صف تحديد المنفذ والرابط المستهدف (فقط لمن لديه صلاحيات تشغيل/أدوات)
    top_btns = []
    if p_use or (p_exec and len(usable_accs) > 0 and has_any_action):
        usable_ids = {a["id"] for a in usable_accs}
        sel_acc_name = "جميع الحسابات المتاحة"
        if st["selected_acc"] == "multi":
            valid_multi = [x for x in (st.get("selected_accs") or []) if x in usable_ids]
            st["selected_accs"] = valid_multi
            if valid_multi:
                sel_acc_name = f"{len(valid_multi)} حسابات محددة"
            else:
                st["selected_acc"] = "all"
        elif st["selected_acc"] != "all":
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

    # 2. قسم فيسبوك الموحد (تجميع كل الأدوات والتفاعلات تحت مسمى واحد لتقليل التشويش وسرعة التصفح)
    if has_any_action:
        active_tools = []
        if p_react and st.get("like"):
            active_tools.append(REACTION_ICONS.get(st.get("reaction_type"), "إعجاب"))
        if p_cmt and st.get("comment"):
            active_tools.append("تعليق")
        if p_int and st.get("interact_cmt"):
            active_tools.append("رد")
        if p_fr and st.get("friend"):
            active_tools.append("صداقة")
        if p_fr and st.get("follow"):
            active_tools.append("متابعة")
        if p_fr and st.get("cancel_friend"):
            active_tools.append("إلغاء صداقة")
        if p_fr and st.get("unfollow"):
            active_tools.append("إلغاء متابعة")
        if p_msg and st.get("message"):
            active_tools.append("رسالة")
        if p_rep and st.get("report_post"):
            active_tools.append("بلاغ منشور")
        if p_rep and st.get("report_profile"):
            active_tools.append("بلاغ حساب")
        if p_rep and st.get("block"):
            active_tools.append("حظر")

        if active_tools:
            fb_badge = f"🟢 ({len(active_tools)} نشط: {', '.join(active_tools[:2])}{'..' if len(active_tools) > 2 else ''})"
            fb_style = "primary"
        else:
            fb_badge = "⚪ (الكل معطل)"
            fb_style = None

        markup.row(
            _btn(
                f"📘 أدوات وتفاعلات فيسبوك {fb_badge}",
                style=fb_style,
                icon_key="shield",
                callback_data="menu_fb_tools"
            )
        )

    # 8. إدارة وإضافة الحسابات (معزولة حسب الصلاحية)
    if is_dev or cap_pool or p_add or p_del:
        if p_add and not has_any_action and not p_use and not is_dev and not cap_pool:
            # واجهة نظيفة لوضع "إضافة حسابات للبوت فقط"
            markup.row(
                types.InlineKeyboardButton("➕ إضافة حساب", callback_data="act_add_acc"),
                types.InlineKeyboardButton("🍪 استيراد جلسة/كوكيز", callback_data="act_import_cookies")
            )
            markup.row(
                types.InlineKeyboardButton(f"📋 حساباتي المضافة ({len(manageable_accs)})", callback_data="menu_manage_accs"),
                types.InlineKeyboardButton("🔄 فحص جلساتي", callback_data="act_check_sessions")
            )
        else:
            row_acc = [types.InlineKeyboardButton(f"👥 إدارة الحسابات ({len(manageable_accs)})", callback_data="menu_manage_accs")]
            if p_add:
                row_acc.append(types.InlineKeyboardButton("➕ إضافة حساب", callback_data="act_add_acc"))
            markup.row(*row_acc)
            sub_acc_row = []
            if p_add:
                sub_acc_row.append(types.InlineKeyboardButton("🍪 استيراد جلسة/كوكيز", callback_data="act_import_cookies"))
            if is_dev or cap_pool or len(manageable_accs) > 0:
                sub_acc_row.append(types.InlineKeyboardButton("🔄 فحص الجلسات", callback_data="act_check_sessions"))
            if sub_acc_row:
                markup.row(*sub_acc_row)

    # 9. قسم المحفظة والإحالات والدعم/البيع + صلاحيات الإدارة المفوضة والمطور
    if is_admin_any:
        row_a = []
        if cap_radar:
            all_users = load_users()
            user_count = sum(1 for u in all_users.values() if can_manage_target_user(user_id, u.get("id", 0)))
            row_a.append(types.InlineKeyboardButton(f"🛰️ رادار المستخدمين ({user_count})", callback_data="menu_surveillance_radar"))
        if cap_eco:
            row_a.append(types.InlineKeyboardButton("⚙️ إعدادات النقاط والعامة", callback_data="menu_admin_economy"))
        if row_a:
            markup.row(*row_a)

        row_b = []
        if cap_audit:
            row_b.append(types.InlineKeyboardButton("📜 سجل الرقابة والأحداث", callback_data="menu_audit_logs"))
        if cap_pay:
            row_b.append(types.InlineKeyboardButton("📩 تذاكر البيع والدعم", callback_data="menu_support"))
        else:
            row_b.append(types.InlineKeyboardButton("💵 طلب بيع الحسابات / مراسلة المطور", callback_data="menu_support"))
        if row_b:
            markup.row(*row_b)

        row_c = [types.InlineKeyboardButton("💰 محفظتي وسجلي", callback_data="menu_wallet")]
        if p_inv:
            row_c.append(types.InlineKeyboardButton("🔗 روابط وأكواد الدعوة", callback_data="menu_referral"))
        markup.row(*row_c)

        row_d = []
        if cap_prox:
            row_d.append(_btn("🌐 البروكسيات ونفق 4G", style="primary", icon_key="proxy", callback_data="menu_proxies"))
        if cap_bkp:
            row_d.append(_btn("💾 الحفظ والنسخ الاحتياطي", callback_data="menu_backup_vault"))
        if row_d:
            markup.row(*row_d)

        if cap_ann:
            markup.row(
                _btn(
                    f"📢 الإعلانات العائمة ({len(active_anns)} نشط)",
                    style="primary" if active_anns else None,
                    icon_key="rocket",
                    callback_data="menu_announcements"
                )
            )
        markup.row(
            _btn("🎛️ إدارة وبوابات الميزات", style="primary", icon_key="shield", callback_data="menu_feature_gates")
        )
    elif has_any_feature or wallet["points"] > 0:
        eco_row = [_btn(f"🪙 نقاطي ({wallet['points']} = {wallet['yer_value']:,} ر.ي)", style="primary", callback_data="menu_wallet")]
        if p_inv:
            eco_row.append(_btn("🎁 دعوة صديق (+4)", style="success", callback_data="menu_referral"))
        markup.row(*eco_row)
        markup.row(
            _btn("💵 طلب بيع الحسابات / مراسلة المطور", callback_data="menu_support")
        )

    # دليل إنشاء الحسابات والربح للعامة والموردين
    pub_gate = get_feature("public_account_addition")
    if (has_any_feature or wallet["points"] > 0) and (is_dev or pub_gate.get("status") == "active"):
        markup.row(
            _btn(
                "💡 دليل إنشاء الحسابات والربح (10 ر.ي / حساب)",
                style="success" if not has_any_action else None,
                icon_key="spark",
                callback_data="menu_earn_guide"
            )
        )

    # مركز إنشاء البريد واستقبال الأكواد
    tm_gate = get_feature("tempmail")
    if (has_any_feature or wallet["points"] > 0) and (is_dev or tm_gate.get("status") == "active"):
        markup.row(
            _btn(
                "📧 إنشاء واستقبال الإيميلات (المؤقت والدائم)",
                style="primary",
                icon_key="spark",
                callback_data="menu_tempmail"
            )
        )

    # كاشف الأرقام اليمنية 967
    cid_gate = get_feature("yemen_caller_id")
    if (has_any_feature or wallet["points"] > 0) and (is_dev or cid_gate.get("status") == "active"):
        markup.row(
            _btn(
                "📞 كاشف الأرقام اليمنية 967 (معرفة اسم المتصل)",
                style="primary",
                icon_key="spark",
                callback_data="menu_caller_id"
            )
        )

    # 10. فتح لوحة التحكم التفاعلية داخل تلغرام فقط (WebApp داخل التطبيق بدون متصفح خارجي)
    webapp_url = get_public_webapp_url()
    if webapp_url and has_any_feature:
        markup.row(
            _btn("📱 فتح لوحة التحكم داخل تلغرام", style="primary", icon_key="shield", web_app=types.WebAppInfo(url=webapp_url))
        )

    # 11. زر الإطلاق الميداني وميزة انتظار التحقق البشري (HITL)
    if p_exec and has_any_action and (p_use or len(usable_accs) > 0):
        wait_ico = "✅" if st.get("wait_for_hitl", True) else "❌"
        markup.row(
            _btn("🚀 بدء تنفيذ المهام الآن", style="success", icon_key="rocket", callback_data="action_launch"),
            _btn(f"⏳ انتظار التحقق [{wait_ico}]", style="primary" if st.get("wait_for_hitl", True) else None, callback_data="toggle_wait_hitl"),
        )

    # 12. إذا كان المستخدم معتمداً لكن لم تُفتح له أي صلاحية بعد ولم يكن لديه رصيد
    if not has_any_feature and wallet["points"] <= 0:
        markup.row(types.InlineKeyboardButton("🔄 تحديث الصلاحيات والحالة", callback_data="back_to_main"))

    return markup


def get_dashboard_text(user_id: int) -> str:
    is_dev = is_super_admin(user_id)
    tier = get_admin_tier(user_id)
    cap_pool = has_admin_capability(user_id, "accounts_pool")
    st = get_user_state(user_id)

    p_use = is_dev or cap_pool or has_permission(user_id, "can_use_accounts")
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

    has_admin_any = is_dev or is_admin_delegate(user_id, include_manager=True)
    has_any_action = any((p_react, p_cmt, p_int, p_fr, p_msg, p_rep))
    has_any_feature = any((has_admin_any, p_use, p_add, p_del, p_exec, has_any_action, p_inv))
    wallet = get_user_wallet(user_id)
    eco_cfg = load_economy_settings()

    if is_dev or cap_pool:
        all_accs = load_accounts()
        active_count = sum(1 for a in all_accs if "نشط" in a.get("status", ""))
        inactive_count = len(all_accs) - active_count
        role_title = "👑 المطور الرئيسي (Super Admin)" if is_dev else ADMIN_TIER_LABELS.get(tier, "👑 نائب المطور")
        mode_tag = "🌐 مفتوح للعامة" if eco_cfg.get("public_mode") else "🔒 بموافقة / دعوة"
        acc_summary = (
            f"📊 <b>إجمالي حسابات النظام:</b> {len(all_accs)} ({active_count} نشط | {inactive_count} غير نشط)\n"
            f"⚙️ <b>وضع البوت:</b> {mode_tag} | <b>القيمة:</b> 1 نقطة = {wallet['yer_per_point']} ر.ي"
        )
    else:
        role_title = ADMIN_TIER_LABELS.get(tier, "🛡️ حساب معتمد بصلاحيات مخصصة") if tier in ("manager", "super_delegate") else "🛡️ حساب معتمد بصلاحيات مخصصة"
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

    if is_dev:
        perms_line = "🔐 <b>صلاحياتك الحالية:</b> تحكم سيادي كامل 100%"
    elif tier == "super_delegate":
        restr = get_admin_restrictions(user_id)
        blocked_cnt = sum(1 for v in restr.values() if v)
        perms_line = (
            "🔐 <b>صلاحياتك الحالية:</b> تفويض كامل على النظام"
            + (f" (مقيد عن {blocked_cnt} بنود)" if blocked_cnt else " (بلا قيود)")
        )
    elif tier == "manager":
        perms_line = "🔐 <b>صلاحياتك الحالية:</b> إدارة المستخدمين والطلبات + صلاحياتك الممنوحة"
    else:
        granted_list = [label for key, label in PERMISSION_LABELS.items() if has_permission(user_id, key)]
        perms_line = f"🔐 <b>صلاحياتك الحالية:</b> {', '.join(granted_list)}" if granted_list else "🔒 <b>صلاحياتك الحالية:</b> لا توجد ميزات مفعلة بعد"

    lines = [
        "⚡ <b>منظومة FB Operator | لوحة التحكم السحابية</b>",
        "━━━━━━━━━━━━━━━━━━━━",
        f"👤 <b>الرتبة:</b> {role_title}",
        perms_line
    ]
    active_anns = list_announcements(only_active=True)
    if active_anns:
        a0 = active_anns[0]
        lines.append(
            f"📌 <b>إعلان عائم [{esc(a0.get('badge'))}]:</b> {esc(a0.get('title'))} "
            f"<i>({esc(a0.get('remaining_label'))})</i>"
        )
    if acc_summary:
        lines.append(acc_summary)

    if has_any_action:
        lines.append(f"🎯 <b>الرابط المستهدف:</b> <code>{esc(st['target_url'][:55])}</code>")
        if p_exec and is_points_enforced_for_user(user_id):
            usable_accs = get_usable_accounts_for_user(user_id)
            op_cnt = estimate_mission_account_count(usable_accs, st)
            est_cost, _ = calculate_mission_cost(st, op_cnt)
            lines.append(f"💸 <b>تكلفة التنفيذ الحالية:</b> {est_cost} نقطة (على {op_cnt} حساب)")
    if has_any_action:
        active_tools_labels = []
        if p_react and st.get("like"):
            active_tools_labels.append(f"إعجاب ({REACTION_ICONS.get(st.get('reaction_type'), '👍')})")
        if p_cmt and st.get("comment"):
            active_tools_labels.append(f"تعليق ('{esc(st['comment_text'][:18])}..')")
        if p_int and st.get("interact_cmt"):
            active_tools_labels.append("رد")
        if p_fr and st.get("friend"):
            active_tools_labels.append("صداقة")
        if p_fr and st.get("follow"):
            active_tools_labels.append("متابعة")
        if p_msg and st.get("message"):
            active_tools_labels.append("رسالة")
        if p_rep and (st.get("report_post") or st.get("report_profile") or st.get("block")):
            active_tools_labels.append("بلاغات")

        if active_tools_labels:
            lines.append(f"📘 <b>أدوات فيسبوك النشطة:</b> 🟢 {', '.join(active_tools_labels)}")
        else:
            lines.append("📘 <b>أدوات فيسبوك:</b> ⚪ غير مفعلة (اضغط زر فيسبوك أدناه لتفعيلها)")

    lines.append("━━━━━━━━━━━━━━━━━━━━")
    if not has_any_feature and wallet["points"] <= 0:
        lines.append("⏳ <b>حسابك معتمد الآن، بانتظار فتح الميزات من المطور.</b>")
    elif p_add and not has_any_action and not p_use and not is_dev:
        act_rew = int(eco_cfg.get("active_account_reward", 1) or 1)
        lines.append(f"🪙 <b>مكافأة التوريد:</b> +{act_rew} نقطة ({act_rew * wallet['yer_per_point']} ر.ي) لكل حساب نشط.")
    else:
        lines.append("🎛️ <i>تحكم بكل الميزات والحسابات والبروكسيات من الأزرار أدناه:</i>")

    return "\n".join(lines)


# ----------------- عرض بطاقة المراقبة وسجل الرقابة للمطور -----------------

def render_surveillance_radar_text_and_markup(viewer_id: int = SUPER_ADMIN_ID):
    users = load_users()
    accs = load_accounts()
    markup = types.InlineKeyboardMarkup(row_width=1)

    pending_users = [
        u for u in users.values()
        if u.get("status") == "pending" and can_manage_target_user(viewer_id, u.get("id", 0))
    ]
    approved_users = [
        u for u in users.values()
        if u.get("status") == "approved" and not is_super_admin(u.get("id")) and can_manage_target_user(viewer_id, u.get("id", 0))
    ]
    banned_users = [
        u for u in users.values()
        if u.get("status") == "banned" and can_manage_target_user(viewer_id, u.get("id", 0))
    ]

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
        markup.add(types.InlineKeyboardButton("لا يوجد مستخدمون متاحون في نطاق رتبتك حالياً", callback_data="noop"))
    eco_cfg = load_economy_settings()
    rate = int(eco_cfg.get("yer_per_point", 10) or 10)
    total_perms = max(1, len(PERMISSION_LABELS))
    for u in approved_users:
        bd = get_accounts_breakdown_by_owner(u["id"])
        u_name = u.get("name", f"مستخدم_{u['id']}")
        active_n = len(bd["active"])
        inactive_n = len(bd["inactive"])
        t_val = str(u.get("admin_tier") or "none")
        tier_ico = "👑" if t_val == "super_delegate" else ("🛡️" if t_val == "manager" else "👤")
        enabled_perms = len(PERMISSION_LABELS) if t_val == "super_delegate" else sum(1 for v in u.get("permissions", {}).values() if v)
        pts = safe_nonneg_points(u.get("points", 0) or 0)
        yer_btn = int(round(float(pts) * rate))
        markup.add(
            types.InlineKeyboardButton(
                f"{tier_ico} {u_name} | 🪙{pts}ن ({yer_btn:,}ر.ي) | 🟢{active_n} 🔴{inactive_n} | {enabled_perms}/{total_perms}",
                callback_data=f"surv_user_{u['id']}"
            )
        )

    if banned_users:
        markup.add(types.InlineKeyboardButton("🚫 --- المستخدمون المحظورون ---", callback_data="noop"))
        for bu in banned_users:
            markup.add(types.InlineKeyboardButton(f"🚫 {bu['name']} (محظور)", callback_data=f"surv_user_{bu['id']}"))

    if has_admin_capability(viewer_id, "audit_logs"):
        markup.add(types.InlineKeyboardButton("📜 عرض سجل الرقابة والأحداث الكامل", callback_data="menu_audit_logs"))
    markup.add(types.InlineKeyboardButton("🔙 العودة للوحة الرئيسية", callback_data="back_to_main"))

    active_total = sum(1 for a in accs if "نشط" in a.get("status", ""))
    inactive_total = len(accs) - active_total
    pool_line = (
        f"📊 <b>الحسابات بالنظام:</b> {len(accs)} (🟢 {active_total} نشط | 🔴 {inactive_total} غير نشط)\n"
        if has_admin_capability(viewer_id, "accounts_pool")
        else ""
    )

    txt = (
        "🛰️ <b>رادار المراقبة الشامل والتحكم بالصلاحيات:</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"👑 <b>المطور الرئيسي الحصين:</b> <code>{SUPER_ADMIN_ID}</code>\n"
        f"👥 <b>إجمالي المسجلين بالرادار:</b> {max(0, len(users) - 1)}\n"
        f"🟢 <b>المعتمدون:</b> {len(approved_users)} | ⏳ <b>المعلقون:</b> {len(pending_users)} | 🚫 <b>المحظورون:</b> {len(banned_users)}\n"
        f"{pool_line}"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "👇 <b>اختر أي مستخدم لعرض حساباته (النشطة والفاشلة + كلمات السر) وتحديد صلاحياته أو رتبته بدقة:</b>"
    )
    return txt, markup


def _render_user_restrictions_view(t_id: int) -> tuple[str | None, types.InlineKeyboardMarkup | None]:
    users = load_users()
    u = users.get(str(t_id))
    if not u or is_super_admin(t_id):
        return None, None
    t_val = str(u.get("admin_tier") or "none")
    restr = get_admin_restrictions(t_id)
    mk = types.InlineKeyboardMarkup(row_width=1)
    for rkey, rlabel in ADMIN_RESTRICTION_LABELS.items():
        blocked = bool(restr.get(rkey, False))
        badge = "🔒 محجوب عنه" if blocked else "✅ مسموح له"
        mk.add(types.InlineKeyboardButton(f"{badge} | {rlabel}", callback_data=f"surv_restr_{t_id}_{rkey}"))
    mk.add(types.InlineKeyboardButton("🔙 العودة لبطاقة المستخدم", callback_data=f"surv_user_{t_id}"))
    txt = (
        f"🚧 <b>تقييد صلاحيات وإشعارات الرتبة الإدارية: {esc(u.get('name'))}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"🎖️ <b>الرتبة الحالية:</b> {esc(ADMIN_TIER_LABELS.get(t_val, t_val))}\n"
        "💡 <i>اضغط على أي بند لحجبه (🔒) أو إتاحته (✅) لهذا الأدمن فوراً — مثلاً حجب رسائل الدفع والمحاسبة مع إبقاء بقية صلاحيات النظام مفتوحة له.</i>"
    )
    return txt, mk


def render_user_dossier(t_id: int, viewer_id: int = SUPER_ADMIN_ID):
    users = load_users()
    u = users.get(str(t_id))
    if not u or not can_manage_target_user(viewer_id, t_id):
        return None, None

    bd = get_accounts_breakdown_by_owner(t_id)
    p = u.get("permissions", {})
    wallet = get_user_wallet(t_id)
    u_tier = str(u.get("admin_tier") or "none")
    can_tiers = is_super_admin(viewer_id)
    cap_pts = has_admin_capability(viewer_id, "points_economy")
    cap_pay = has_admin_capability(viewer_id, "payment_notices")

    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(types.InlineKeyboardButton("🌟 منح كافة المميزات (تشغيل كامل بضغطة)", callback_data=f"surv_grant_all_{t_id}"))

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

    if can_tiers:
        markup.row(
            types.InlineKeyboardButton(f"{'🔘 ' if u_tier == 'none' else ''}👤 عادي", callback_data=f"surv_tier_{t_id}_none"),
            types.InlineKeyboardButton(f"{'🔘 ' if u_tier == 'manager' else ''}🛡️ مدير", callback_data=f"surv_tier_{t_id}_manager"),
            types.InlineKeyboardButton(f"{'🔘 ' if u_tier == 'super_delegate' else ''}👑 فوق الأدمن", callback_data=f"surv_tier_{t_id}_super_delegate"),
        )
        if u_tier in ("manager", "super_delegate"):
            restr = get_admin_restrictions(t_id)
            blk_n = sum(1 for v in restr.values() if v)
            markup.row(
                types.InlineKeyboardButton(
                    f"🚧 قيود الرتبة وحجب الإشعارات ({blk_n} محجوب)",
                    callback_data=f"surv_restr_menu_{t_id}"
                )
            )

    if cap_pts:
        markup.row(
            types.InlineKeyboardButton("➕ إضافة +5 نقاط", callback_data=f"surv_pts_add5_{t_id}"),
            types.InlineKeyboardButton("➖ خصم -5 نقاط", callback_data=f"surv_pts_sub5_{t_id}"),
            types.InlineKeyboardButton("✏️ تعديل/خصم رقم", callback_data=f"surv_pts_custom_{t_id}")
        )
    row_tools = []
    if cap_pay and cap_pts:
        row_tools.append(types.InlineKeyboardButton("💸 تسوية ودفع المستحقات", callback_data=f"surv_pts_settle_{t_id}"))
    row_tools.append(types.InlineKeyboardButton("🔄 تصفير الإنذارات", callback_data=f"surv_rst_warn_{t_id}"))
    if cap_pay:
        row_tools.append(types.InlineKeyboardButton("📩 التذاكر", callback_data="menu_support"))
    markup.row(*row_tools)
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
    tier_lbl = ADMIN_TIER_LABELS.get(u_tier, "👤 مستخدم عادي")
    header = (
        f"👤 <b>بطاقة المراقبة الشاملة: {esc(u.get('name'))}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"🆔 <b>الآيدي:</b> <code>{t_id}</code> | <b>المعرف:</b> {uname}\n"
        f"🎖️ <b>الرتبة الإدارية:</b> {esc(tier_lbl)}\n"
        f"🛡️ <b>الحالة:</b> {st_map.get(u.get('status'), esc(u.get('status')))}\n"
        f"🪙 <b>الرصيد المالي:</b> {wallet['points']} نقطة = <b>{wallet['yer_value']:,} ريال يمني</b>\n"
        f"⚠️ <b>إنذارات جودة البروفايل:</b> <b>{wallet.get('profile_warnings_used', 0)}/{wallet.get('profile_warning_limit', 5)}</b>\n"
        f"💵 <b>المكتسب:</b> {wallet['total_points_earned']}ن | <b>المخصوم:</b> {wallet['total_points_spent']}ن | <b>المُسلّم:</b> {wallet['total_yer_settled']:,} ر.ي\n"
        f"🤝 <b>الإحالات الناجحة:</b> {wallet['referred_count']}{ref_line}\n"
        f"📅 <b>أول دخول:</b> {esc(u.get('first_seen'))} | ⏱️ <b>آخر نشاط:</b> {esc(u.get('last_seen'))}\n"
        f"🔄 <b>الدخول:</b> {u.get('total_logins', 1)} | ⚡ <b>العمليات:</b> {u.get('operations_count', 0)}\n"
        f"📈 <b>السجل التاريخي الدائم للمضافات:</b> 🟢 {u.get('active_accounts_added', 0)} نشط | 🔴 {u.get('inactive_accounts_added', 0)} غير نشط\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
    )

    body_lines = []
    _px_binds = load_proxy_state().get("bindings") or {}
    body_lines.append(f"🟢 <b>الحسابات النشطة المسجلة حالياً ({len(bd['active'])}):</b>")
    if bd["active"]:
        for idx, a in enumerate(bd["active"][-10:], 1):
            fb_id = f" | FB:<code>{esc(a.get('fb_id'))}</code>" if a.get("fb_id") else ""
            raw_b = _px_binds.get(str(a.get("id") or ""))
            px_lbl = mask_proxy_uri(raw_b) if raw_b else str(a.get("bound_proxy") or "")
            px_part = f" | 🌐 <code>{esc(px_lbl)}</code>" if px_lbl else ""
            body_lines.append(
                f"<b>{idx}. {esc(a['name'])}</b> (<code>{esc(a['id'])}</code>){fb_id}\n"
                f"   📧 <code>{esc(a['email'])}</code> | 🔑 <code>{esc(a['password'])}</code>\n"
                f"   📅 {esc(a.get('added_at', 'سابقاً'))}{px_part}"
            )
    else:
        body_lines.append("<i>لا توجد حسابات نشطة مسجلة من هذا المستخدم حالياً.</i>")

    body_lines.append(f"\n🔴 <b>الحسابات غير النشطة / الفاشلة ({len(bd['inactive'])}):</b>")
    if bd["inactive"]:
        for idx, a in enumerate(bd["inactive"][-10:], 1):
            reason = esc(a.get("diagnostic_reason") or a.get("status") or "يتطلب تسجيل الدخول")
            raw_b = _px_binds.get(str(a.get("id") or ""))
            px_lbl = mask_proxy_uri(raw_b) if raw_b else str(a.get("bound_proxy") or "")
            px_part = f" | 🌐 <code>{esc(px_lbl)}</code>" if px_lbl else ""
            body_lines.append(
                f"<b>{idx}. {esc(a['name'])}</b> (<code>{esc(a['id'])}</code>)\n"
                f"   📧 <code>{esc(a['email'])}</code> | 🔑 <code>{esc(a['password'])}</code>\n"
                f"   ⚠️ السبب: {reason} | 📅 {esc(a.get('added_at', 'سابقاً'))}{px_part}"
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


def _user_can_inspect_account(user_id: int, acc: dict) -> tuple[bool, bool, bool]:
    """فحص صلاحية (الاطلاع/الفحص، الحذف، التنفيذ) لحساب محدد وفق عزل الملكية."""
    is_pool = has_admin_capability(user_id, "accounts_pool")
    uid = int(user_id)
    is_owner = int(acc.get("owner_id") or 0) == uid
    can_del = is_pool or (is_owner and has_permission(uid, "can_delete_accounts"))
    usable_list = get_usable_accounts_for_user(uid)
    in_usable = any(x.get("id") == acc.get("id") for x in usable_list)
    can_inspect = (
        is_pool
        or (is_owner and (has_permission(uid, "can_add_accounts") or has_permission(uid, "can_delete_accounts") or has_permission(uid, "can_use_accounts")))
        or (in_usable and has_permission(uid, "can_use_accounts") and not has_permission(uid, "can_add_accounts"))
    )
    can_use = in_usable and (is_super_admin(uid) or has_permission(uid, "can_use_accounts") or has_permission(uid, "can_execute"))
    return can_inspect, can_del, can_use


def _render_account_detail_view(user_id: int, acc: dict) -> tuple[str, types.InlineKeyboardMarkup]:
    """بطاقة إدارة الحساب الفردية: عرض التفاصيل الكاملة للمطور، فحص، حذف الجلسة وإعادة الدخول، الشاشة الحية، وتنفيذ مباشر."""
    acc_id = str(acc.get("id") or "")
    _, can_del, can_use = _user_can_inspect_account(user_id, acc)
    is_dev_view = is_super_admin(user_id) or has_admin_capability(user_id, "accounts_pool")
    is_act = "نشط" in str(acc.get("status") or "")
    raw_pwd = str(acc.get("password") or "")
    has_creds = bool(acc.get("email") and raw_pwd and raw_pwd != "[SESSION_COOKIES]")
    st_badge = "🟢 نشط ومسجل" if is_act else "🔴 غير نشط / يتطلب دخول"
    cred_badge = "🔑 محفوظة ومؤمّنة على السيرفر (جاهز لإعادة الدخول)" if has_creds else "🍪 جلسة كوكيز فقط"
    reason = str(acc.get("diagnostic_reason") or ("الجلسة مثبتة" if is_act else "انتهت الجلسة أو يتطلب تحققاً"))

    proxy_txt = str(acc.get("bound_proxy") or "افتراضي / مباشر")
    if is_super_admin(user_id):
        try:
            raw_bind = str((load_proxy_state().get("bindings") or {}).get(acc_id) or "").strip()
            if not raw_bind:
                prof_key = os.path.basename(str(acc.get("profile_dir") or acc_id).replace("\\", "/").rstrip("/")) or acc_id
                raw_bind = str((load_proxy_state().get("bindings") or {}).get(prof_key) or "").strip()
            if raw_bind:
                proxy_txt = raw_bind
        except Exception:
            pass
    cc_txt = f" [{acc.get('bound_proxy_country')}]" if acc.get("bound_proxy_country") else ""
    pq = acc.get("profile_quality") if isinstance(acc.get("profile_quality"), dict) else {}
    pq_txt = f"{pq.get('score', 0)}/7 ✅" if pq.get("checked") else "لم يُفحص بعد"

    sess_badge = "❌ لا يوجد ملف جلسة"
    try:
        sf = _resolve_session_file(acc.get("profile_dir") or acc_id)
        if sf.exists():
            sess_badge = "✅ ملف جلسة محفوظ"
        elif sf.with_suffix(".pending.json").exists():
            sess_badge = "⏳ كوكيز تحقق معلقة"
    except Exception:
        pass

    lines = [
        f"📱 <b>بطاقة الحساب: {esc(acc.get('name') or acc_id)}</b>",
        "━━━━━━━━━━━━━━━━━━━━",
        f"🆔 <b>المعرّف:</b> <code>{esc(acc_id)}</code> | <b>الحالة:</b> {st_badge}",
        f"📧 <b>البريد/الهاتف:</b> <code>{esc(acc.get('email') or '—')}</code>",
    ]
    if is_dev_view:
        pwd_disp = (
            f"<code>{esc(raw_pwd)}</code>"
            if has_creds
            else ("🍪 جلسة كوكيز فقط (بدون كلمة مرور)" if raw_pwd == "[SESSION_COOKIES]" else "غير محفوظة")
        )
        owner_lbl = f"{acc.get('owner_name') or 'النظام'} ({acc.get('owner_id') or '0'})"
        lines.append(f"🔑 <b>كلمة المرور:</b> {pwd_disp}")
        lines.append(f"👤 <b>أضافه:</b> {esc(owner_lbl)} | 📅 <b>بتاريخ:</b> <code>{esc(acc.get('added_at') or 'سابقاً')}</code>")
    else:
        lines.append(f"🔐 <b>بيانات الدخول:</b> {cred_badge}")

    lines.extend([
        f"🍪 <b>الجلسة:</b> {sess_badge}",
        f"🌐 <b>البروكسي المثبت:</b> <code>{esc(proxy_txt)}{esc(cc_txt)}</code>",
        f"🧬 <b>معرّف فيسبوك:</b> <code>{esc(acc.get('fb_id') or 'غير مستخرج بعد')}</code> | <b>البروفايل:</b> {esc(pq_txt)}",
        f"🩺 <b>آخر تشخيص:</b> {esc(reason)}",
    ])

    markup = types.InlineKeyboardMarkup(row_width=2)
    if has_creds:
        markup.row(
            types.InlineKeyboardButton("🔍 فحص الجلسة الآن", callback_data=f"acc_check_{acc_id}"),
            types.InlineKeyboardButton("🔑 حذف الجلسة وإعادة الدخول", callback_data=f"acc_relogin_{acc_id}"),
        )
    else:
        markup.row(types.InlineKeyboardButton("🔍 فحص الجلسة الآن", callback_data=f"acc_check_{acc_id}"))

    w_url = get_public_webapp_url()
    if w_url:
        sep = "&" if "?" in w_url else "?"
        markup.row(types.InlineKeyboardButton("🖥️ الشاشة الحية (حل التحقق وحفظ الجلسة)", web_app=types.WebAppInfo(url=f"{w_url}{sep}hitl={acc_id}")))
    else:
        markup.row(types.InlineKeyboardButton("🖥️ كيف أفتح الشاشة الحية؟", callback_data=f"hitl_help_{acc_id}"))

    if can_use:
        markup.row(types.InlineKeyboardButton("⚡ التفاعل / تنفيذ مهمة بهذا الحساب فقط", callback_data=f"acc_mission_{acc_id}"))
    if can_del:
        markup.row(types.InlineKeyboardButton("🗑️ حذف الحساب الآن", callback_data=f"del_acc_{acc_id}"))
    markup.row(
        types.InlineKeyboardButton("🔙 قائمة الحسابات", callback_data="menu_manage_accs"),
        types.InlineKeyboardButton("🏠 الرئيسية", callback_data="back_to_main"),
    )
    return "\n".join(lines), markup


def _render_manage_accs_view(user_id: int) -> tuple[str, types.InlineKeyboardMarkup]:
    is_dev = has_admin_capability(user_id, "accounts_pool")
    accs = get_manageable_accounts_for_user(user_id)
    can_del = is_dev or has_permission(user_id, "can_delete_accounts")
    can_add = is_dev or has_permission(user_id, "can_add_accounts")

    markup = types.InlineKeyboardMarkup(row_width=2)
    for a in accs[-20:]:
        st_icon = "🟢" if "نشط" in a.get("status", "") else "🔴"
        if can_del:
            markup.row(
                types.InlineKeyboardButton(f"{st_icon} {a['name']}", callback_data=f"acc_view_{a['id']}"),
                types.InlineKeyboardButton("🔍 فحص/تحكم", callback_data=f"acc_view_{a['id']}"),
                types.InlineKeyboardButton("🗑️ حذف", callback_data=f"del_acc_{a['id']}")
            )
        else:
            markup.row(
                types.InlineKeyboardButton(f"{st_icon} {a['name']}", callback_data=f"acc_view_{a['id']}"),
                types.InlineKeyboardButton("🔍 فحص/تحكم", callback_data=f"acc_view_{a['id']}"),
            )

    if can_add:
        markup.row(
            types.InlineKeyboardButton("➕ إضافة حساب جديد", callback_data="act_add_acc"),
            types.InlineKeyboardButton("🍪 استيراد جلسة/كوكيز", callback_data="act_import_cookies")
        )
    if can_del:
        markup.row(types.InlineKeyboardButton("🧹 تنظيف وحذف الحسابات التالفة", callback_data="act_purge_broken"))
    markup.row(
        types.InlineKeyboardButton("🔄 فحص كل الجلسات", callback_data="act_check_sessions"),
        types.InlineKeyboardButton("🔙 رجوع", callback_data="back_to_main")
    )

    title = "👥 <b>إدارة كافة حسابات النظام:</b>\n" if is_dev else "📋 <b>حساباتك التي قمت بإضافتها للبوت:</b>\n"
    txt = title + "💡 <i>اضغط على اسم أي حساب لإدارته منفرداً (فحص / إعادة دخول بالبيانات المحفوظة / الشاشة الحية / تنفيذ مهمة به فقط).</i>\n\n"
    now_ts = time.time()
    for i, a in enumerate(accs, 1):
        is_act = "نشط" in a.get("status", "")
        if is_act:
            st_text = "🟢 نشط ومسجل"
        else:
            ttl_note = ""
            try:
                f_ts = float(a.get("failed_at") or a.get("added_at") or 0)
                if f_ts > 0:
                    rem_h = max(0.0, BROKEN_ACCOUNT_TTL_HOURS - (now_ts - f_ts) / 3600.0)
                    ttl_note = f" | ⏳ حذف تلقائي خلال {rem_h:.1f}س"
            except Exception:
                pass
            st_text = f"🔴 غير نشط ({esc(a.get('diagnostic_reason') or 'يتطلب تسجيل دخول')}{ttl_note})"
        owner_lbl = a.get("owner_name") or a.get("owner_id") or "المطور الرئيسي"
        owner_badge = f" | المضيف: {esc(owner_lbl)}" if is_dev else ""
        txt += f"{i}. <b>{esc(a['name'])}</b> (<code>{esc(a['id'])}</code>){owner_badge}\n   📧 <code>{esc(a['email'])}</code> | {st_text}\n"
    if not accs:
        txt += "<i>لا توجد حسابات مسجلة في هذا السجل حتى الآن.</i>"
    else:
        txt += f"\nℹ️ <i>تنبيه: يتم حذف الحسابات غير النشطة تلقائياً بعد مرور {BROKEN_ACCOUNT_TTL_HOURS} ساعة لبقاء السجل نظيفاً.</i>"
    if len(txt) > 3950:
        txt = txt[:3920] + "\n..."
    return txt, markup


def _extract_backup_channel_target(message) -> tuple[int | str | None, str, str]:
    """استخراج معرف القناة المستهدفة من رسالة معاد توجيهها أو نص (@channel / رابط / ID رقمي)"""
    origin = getattr(message, "forward_origin", None)
    fwd_chat = getattr(origin, "chat", None) if origin is not None else None
    if fwd_chat is None:
        fwd_chat = getattr(message, "forward_from_chat", None)
    if fwd_chat is not None and getattr(fwd_chat, "id", None) is not None:
        title = getattr(fwd_chat, "title", "") or getattr(fwd_chat, "username", "") or str(fwd_chat.id)
        return fwd_chat.id, title, ""

    raw = (getattr(message, "text", None) or getattr(message, "caption", None) or "").strip()
    if not raw:
        return None, "", "أعد توجيه أي منشور من القناة إلى هنا أو أرسل معرف القناة (مثل @MyChannel أو -1001234567890)."

    low = raw.lower()
    if low.startswith("https://t.me/+") or low.startswith("http://t.me/+") or low.startswith("t.me/+") or "joinchat" in low:
        return (
            None,
            "",
            "روابط الدعوة الخاصة (+...) لا تكشف المعرف الرقمي للقناة؛ أعد توجيه أي رسالة من القناة إلى هنا أو أرسل معرفها الرقمي (-100...).",
        )

    cleaned = re.sub(r"^https?://(?:t\.me|telegram\.me)/", "", raw, flags=re.IGNORECASE).split("?")[0].strip("/")
    if cleaned.lower().startswith("t.me/"):
        cleaned = cleaned[5:].strip("/")
    if "/" in cleaned and not cleaned.startswith("-"):
        cleaned = cleaned.split("/", 1)[0]

    if re.fullmatch(r"-?\d{5,20}", cleaned):
        ch_num = int(cleaned)
        return ch_num, str(ch_num), ""
    if re.fullmatch(r"@?[A-Za-z][A-Za-z0-9_]{3,64}", cleaned):
        handle = "@" + cleaned.lstrip("@")
        return handle, handle, ""
    return None, "", "صيغة القناة غير صحيحة. أرسل @username أو -100... أو أعد توجيه رسالة من القناة مباشرة."


def _handle_backup_channel_binding(message, user_id: int) -> None:
    st = get_user_state(user_id)
    if not has_admin_capability(user_id, "backups"):
        st["input_mode"] = None
        return
    target_ch, title_hint, err = _extract_backup_channel_target(message)
    if err or target_ch is None:
        bot.reply_to(
            message,
            f"⚠️ <b>تعذر قراءة القناة:</b> {esc(err)}\n<i>حاول مجدداً أو اضغط إلغاء للعودة.</i>",
            reply_markup=_prompt_back_markup("menu_backup_vault"),
        )
        return

    resolved_id = target_ch
    resolved_title = title_hint or str(target_ch)
    try:
        if hasattr(bot, "get_chat"):
            chat_obj = bot.get_chat(target_ch)
            if chat_obj is not None and getattr(chat_obj, "id", None) is not None:
                resolved_id = chat_obj.id
                resolved_title = getattr(chat_obj, "title", "") or getattr(chat_obj, "username", "") or str(resolved_id)
        bot.send_message(
            resolved_id,
            "✅ <b>تم ربط هذه القناة بنجاح كخزنة نسخ احتياطي شاملة!</b>\n"
            "سيتم إرسال النسخ الكاملة هنا تلقائياً حسب التوقيت المجدول وبكامل البيانات والإعدادات.",
            parse_mode="HTML",
        )
    except Exception as e:
        bot.reply_to(
            message,
            "⚠️ <b>تعذر النشر في القناة!</b>\n"
            "تأكد من إضافة البوت كـ <b>مشرف (Admin)</b> داخل القناة مع صلاحية <b>نشر الرسائل</b> ثم أعد إرسال المعرف أو التوجيه.\n"
            f"<code>{esc(e)}</code>",
            reply_markup=_prompt_back_markup("menu_backup_vault"),
        )
        return

    st["input_mode"] = None
    save_backup_settings(
        {"channel_id": resolved_id, "channel_title": str(resolved_title), "enabled": True, "last_error": ""},
        mark_dirty=True,
    )
    first_res = send_backup_to_channel(bot, channel_id=resolved_id, trigger_label="النسخة التأسيسية بعد ربط القناة")
    record_audit_log(user_id, "المطور", "BACKUP_CHANNEL_LINKED", f"ربط قناة النسخ الاحتياطي: {resolved_title} ({resolved_id})")

    bkp_note = (
        f"🚀 وتم إرسال أول نسخة احتياطية شاملة للقناة بنجاح (#{first_res.get('backup_number', 1)})."
        if first_res.get("ok")
        else f"⚠️ رُبطت القناة ولكن تعذر إرسال أول نسخة تلقائياً: {esc(first_res.get('error', ''))}"
    )
    bot.reply_to(
        message,
        f"✅ <b>تم ربط قناة النسخ الاحتياطي بنجاح!</b>\n"
        f"📡 <b>القناة:</b> {esc(resolved_title)} (<code>{esc(resolved_id)}</code>)\n"
        f"{bkp_note}",
        reply_markup=_back_home_markup("menu_backup_vault"),
    )


def _render_backup_schedule_view() -> tuple[str, types.InlineKeyboardMarkup]:
    bkp = load_backup_settings()
    en_flag = bool(bkp.get("enabled", True))
    dm_flag = bool(bkp.get("dm_enabled", True))
    lines = [
        "⏱️ <b>جدولة النسخ الاحتياطي التلقائي (للقناة والخاص)</b>",
        "━━━━━━━━━━━━━━━━━━━━",
        f"🕒 <b>التكرار الحالي:</b> {esc(bkp.get('interval_label', 'كل 1 ساعة'))} (<code>{bkp.get('interval_seconds', 3600)}</code> ثانية)",
        f"🔄 <b>الجدولة التلقائية بالوقت:</b> {'🟢 مفعلة' if en_flag else '🔴 متوقفة'}",
        f"📬 <b>إرسال ملف ZIP للخاص تلقائياً:</b> {'🟢 مفعل' if (en_flag and dm_flag) else '🔴 متوقف'}",
        f"⚡ <b>نسخ إضافي عند أي تعديل:</b> {'🟢 مفعل' if bkp.get('on_change') else '⚪ معطل'}",
        "━━━━━━━━━━━━━━━━━━━━",
        "اختر من الأوقات الجاهزة أو اضغط <b>وقت مخصص</b> لكتابة أي مدة (ثانية / دقيقة / ساعة / يوم / أسبوع / شهر / سنة):",
    ]
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(
        types.InlineKeyboardButton("⚡ كل 10 ثوانٍ", callback_data="bkp_iv_10"),
        types.InlineKeyboardButton("⚡ كل 30 ثانية", callback_data="bkp_iv_30"),
    )
    markup.row(
        types.InlineKeyboardButton("⏱️ كل 5 دقائق", callback_data="bkp_iv_300"),
        types.InlineKeyboardButton("🕐 كل 1 ساعة", callback_data="bkp_iv_3600"),
    )
    markup.row(
        types.InlineKeyboardButton("📅 يومياً (24س)", callback_data="bkp_iv_86400"),
        types.InlineKeyboardButton("🗓️ أسبوعياً (7ي)", callback_data="bkp_iv_604800"),
    )
    markup.row(
        types.InlineKeyboardButton("🌙 شهرياً (30ي)", callback_data="bkp_iv_2592000"),
        types.InlineKeyboardButton("🌍 سنوياً (1 سنة)", callback_data="bkp_iv_31536000"),
    )
    markup.row(types.InlineKeyboardButton("✏️ إدخال وقت مخصص (ثانية..سنة)", callback_data="bkp_set_interval_custom"))
    markup.row(types.InlineKeyboardButton("🛑 إيقاف النسخ التلقائي بالكامل (يدوي فقط)", callback_data="bkp_stop_auto"))
    markup.row(types.InlineKeyboardButton("🔙 العودة لخزنة النسخ", callback_data="menu_backup_vault"))
    return "\n".join(lines), markup


_pending_upload_lock = threading.Lock()
_pending_restore_uploads: dict[str, dict] = {}


def _stage_pending_backup(uid: int, raw_bytes: bytes, fname: str) -> str:
    now = time.time()
    with _pending_upload_lock:
        for k, v in list(_pending_restore_uploads.items()):
            if (now - v.get("ts", 0)) > 600:
                _pending_restore_uploads.pop(k, None)
        while len(_pending_restore_uploads) >= 5:
            oldest_k = min(_pending_restore_uploads.keys(), key=lambda x: _pending_restore_uploads[x].get("ts", 0))
            _pending_restore_uploads.pop(oldest_k, None)
        tok = secrets.token_hex(5)
        _pending_restore_uploads[tok] = {"uid": int(uid), "raw": raw_bytes, "fname": fname, "ts": now}
        return tok


def _pop_pending_backup(tok: str, uid: int) -> dict | None:
    with _pending_upload_lock:
        rec = _pending_restore_uploads.get(tok)
        if not rec or int(rec.get("uid", 0)) != int(uid):
            return None
        if (time.time() - rec.get("ts", 0)) > 600:
            _pending_restore_uploads.pop(tok, None)
            return None
        return _pending_restore_uploads.pop(tok, None)


def _format_external_vault_summary(st_info: dict | None = None) -> tuple[str, str]:
    info = st_info if isinstance(st_info, dict) else get_persistence_status()
    ext_v = info.get("external_vault") or {}
    fname = str(ext_v.get("filename") or "fb_operator_vault.json")
    configured = bool(ext_v.get("configured"))
    exists = bool(ext_v.get("exists"))
    encrypted = bool(ext_v.get("encrypted"))
    status_txt = str(ext_v.get("status") or "-")

    if exists:
        enc_label = "مشفّر (FB_VAULT_KEY)" if encrypted else "نص عادي"
        badge = f"🟢 {fname} ({enc_label} — {status_txt})"
    elif configured:
        badge = f"🟡 {fname} (مهيّأ وسيُكتب تلقائياً بجانب المجلد)"
    else:
        badge = f"⚪ غير مكتشف — أنشئ {fname} بجانب HUGGINGFACE_UPLOAD"

    warn = ""
    if exists and not encrypted and os.environ.get("GITHUB_REPOSITORY"):
        warn = "⚠️ تنبيه أمان: أضف FB_VAULT_KEY في GitHub Secrets أو اجعل المستودع Private لحماية الجلسات وكلمات المرور."
    return badge, warn


def _render_cloud_db_view() -> tuple[str, types.InlineKeyboardMarkup]:
    st_db = get_cloud_db_status_summary()
    cfg = st_db.get("config_masked") or {}
    prov = (st_db.get("provider") or "none").lower()
    prov_names = {
        "turso": "Turso Cloud (libSQL مجاني 9GB — بلا فيزا)",
        "supabase": "Supabase PostgreSQL (مجاني 500MB — بلا فيزا)",
        "firebase": "Firebase Realtime DB (Spark مجاني — بلا فيزا)",
        "none": "غير مربوطة (تعتمد على SQLite المحلي + HF/Telegram الآن)",
    }
    sql_ok = "✅ نشطة" if st_db.get("sqlite_mirror_exists") else "⏳ ستُنشأ تلقائياً"
    lines = [
        "🗄️ <b>ربط قاعدة بيانات سحابية خارجية مجانية (بلا فيزا)</b>",
        "━━━━━━━━━━━━━━━━━━━━",
        f"💾 <b>مرآة SQLite WAL المحلية:</b> {sql_ok}",
        f"☁️ <b>المزود السحابي الحالي:</b> {esc(prov_names.get(prov, prov))}",
        f"📡 <b>حالة المزامنة:</b> {esc(st_db.get('last_status', '-'))}",
    ]
    if prov == "turso":
        lines.append(f"🔗 <b>رابط Turso:</b> <code>{esc(cfg.get('turso_url', '-'))}</code>")
        lines.append(f"🔑 <b>التوكن:</b> <code>{esc(cfg.get('turso_token', '-'))}</code>")
    elif prov == "supabase":
        lines.append(f"🔗 <b>رابط Supabase:</b> <code>{esc(cfg.get('supabase_url', '-'))}</code>")
        lines.append(f"🔑 <b>المفتاح:</b> <code>{esc(cfg.get('supabase_key', '-'))}</code>")
    elif prov == "firebase":
        lines.append(f"🔗 <b>رابط Firebase:</b> <code>{esc(cfg.get('firebase_url', '-'))}</code>")
    ext_badge, ext_warn = _format_external_vault_summary()
    lines.append(f"📦 <b>الملف الخارجي الشقيق:</b> {esc(ext_badge)}")
    if ext_warn:
        lines.append(esc(ext_warn))
    if st_db.get("last_error"):
        lines.append(f"⚠️ <b>آخر تنبيه:</b> <code>{esc(st_db.get('last_error', ''))}</code>")
    lines.extend([
        "━━━━━━━━━━━━━━━━━━━━",
        "💡 <i>اربط أي قاعدة مجانية من الأسفل (كلها 100% بلا بطاقة بنكية) لتبقى جميع الحسابات، الجلسات، النقاط، المستخدمين، وسجلات البوت محفوظة حتى لو حُذفت الاستضافة أو تغيّرت!</i>",
    ])

    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(types.InlineKeyboardButton("🟢 ربط Turso المجاني (موصى به — بلا إعداد جدول)", callback_data="cdb_pick_turso"))
    markup.row(
        types.InlineKeyboardButton("🟣 ربط Supabase PostgreSQL", callback_data="cdb_pick_supabase"),
        types.InlineKeyboardButton("🟡 ربط Firebase RTDB", callback_data="cdb_pick_firebase"),
    )
    if st_db.get("enabled"):
        markup.row(
            types.InlineKeyboardButton("📤 رفع ومزامنة الكل للقاعدة الآن", callback_data="cdb_sync_push"),
            types.InlineKeyboardButton("🔀 سحب ودمج من القاعدة السحابية", callback_data="cdb_sync_pull_merge"),
        )
        markup.row(
            types.InlineKeyboardButton("🧪 فحص الاتصال", callback_data="cdb_test"),
            types.InlineKeyboardButton("🗑️ فصل القاعدة السحابية", callback_data="cdb_clear"),
        )
    markup.row(
        types.InlineKeyboardButton("🔄 تحديث", callback_data="menu_cloud_db"),
        types.InlineKeyboardButton("🔙 العودة لخزنة النسخ", callback_data="menu_backup_vault"),
    )
    return "\n".join(lines), markup


def _build_hitl_action_markup(acc_id: str, can_otp: bool = True, can_del: bool = False, include_back: bool = False) -> types.InlineKeyboardMarkup:
    mk = types.InlineKeyboardMarkup(row_width=2)
    w_url = get_public_webapp_url()
    if w_url:
        sep = "&" if "?" in w_url else "?"
        mk.row(types.InlineKeyboardButton("🖥️ الشاشة الحية لحل التحقق بنفسي", web_app=types.WebAppInfo(url=f"{w_url}{sep}hitl={acc_id}")))
    else:
        mk.row(types.InlineKeyboardButton("🖥️ كيف أفتح الشاشة الحية؟", callback_data=f"hitl_help_{acc_id}"))
    if can_otp:
        mk.row(types.InlineKeyboardButton("🔐 إرسال رمز 2FA / OTP الآن", callback_data=f"hitl_otp_{acc_id}"))
    if can_del:
        mk.row(types.InlineKeyboardButton("🗑️ حذف الحساب التالف الآن", callback_data=f"del_acc_{acc_id}"))
    if include_back:
        mk.row(types.InlineKeyboardButton("🔙 إدارة الحسابات", callback_data="menu_manage_accs"))
    return mk


def _on_hitl_account_verified(acc_id: str, fb_id: str, actor_uid: int) -> None:
    acc = get_account_by_id(acc_id)
    if not acc:
        return
    owner_id = int(acc.get("owner_id") or 0)
    owner_name = str(acc.get("owner_name") or f"مستخدم_{owner_id}")
    upd = {
        "status": "نشط ومسجل",
        "diagnostic_reason": "تم إكمال التحقق وتثبيت الجلسة عبر الشاشة الحية",
    }
    if fb_id:
        upd["fb_id"] = fb_id
    update_account(acc_id, upd)
    if owner_id > 0:
        record_account_result_for_user(owner_id, is_active=True)
    rew = {}
    if owner_id > 0 and not is_super_admin(owner_id):
        rew = reward_account_activation(owner_id, acc_id, acc_name=acc.get("name", ""))
        if rew.get("referral_awarded", 0) > 0 and rew.get("referral_inviter_id"):
            safe_send(
                rew["referral_inviter_id"],
                f"🎁 <b>مكافأة إحالة (+{rew['referral_awarded']} نقاط)!</b>\n"
                f"قام المدعو <b>{esc(owner_name)}</b> بتفعيل أول حساب فيسبوك نشط له بنجاح.\n"
                f"💰 رصيدك الآن: <b>{rew['referral_inviter_balance']}</b> نقطة!"
            )
    record_audit_log(
        actor_uid or owner_id,
        owner_name,
        "HITL_VERIFIED",
        f"تفعيل الحساب عبر الشاشة الحية: {acc.get('name')} ({acc_id}) | FB={fb_id}",
    )
    notify_uid = actor_uid or owner_id
    if notify_uid:
        rew_note = _format_reward_notice(rew, acc.get("name", acc_id), is_super_admin(owner_id))
        safe_send(
            notify_uid,
            f"✅ <b>تم إكمال التحقق وتثبيت جلسة '{esc(acc.get('name', acc_id))}' بنجاح!</b>\n"
            f"🆔 <b>معرّف فيسبوك:</b> <code>{esc(fb_id or '-')}</code>\n"
            f"🍪 تم حفظ الجلسة الدائمة ومزامنتها بالكامل.{rew_note}",
            reply_markup=_back_home_markup("menu_manage_accs"),
        )
    if owner_id > 0 and not is_super_admin(owner_id):
        u_rec = load_users().get(str(owner_id), {})
        _notify_developer_account_result(
            owner_id=owner_id,
            owner_name=owner_name,
            owner_username=str(u_rec.get("username") or ""),
            acc=acc,
            is_active=True,
            diag_reason="تم إكمال التحقق يدوياً في الشاشة الحية",
            fb_id=fb_id,
        )


def _render_backup_vault_view() -> tuple[str, types.InlineKeyboardMarkup]:
    st_info = get_persistence_status()
    bkp = st_info.get("backup_channel") or {}
    ch_id = bkp.get("channel_id")
    ch_title = bkp.get("channel_title") or (str(ch_id) if ch_id else "")
    ch_badge = f"🟢 مرتبطة: <b>{esc(ch_title)}</b> (<code>{esc(ch_id)}</code>)" if ch_id else "🔴 غير مرتبطة بعد"

    en_flag = bool(bkp.get("enabled", True))
    dm_flag = bool(bkp.get("dm_enabled", True))
    och_flag = bool(bkp.get("on_change", False))
    iv_sec = int(bkp.get("interval_seconds") or 3600)
    last_ts = float(bkp.get("last_channel_backup_ts") or 0.0)
    if not en_flag:
        eta_txt = "متوقفة مؤقتاً"
    elif not ch_id and not dm_flag:
        eta_txt = "إرسال الخاص متوقف (يدوي فقط)"
    elif not ch_id:
        eta_txt = f"للخاص حسب التوقيت ({bkp.get('interval_label', 'كل 1 ساعة')})"
    elif last_ts <= 0:
        eta_txt = "مستحقة الآن"
    else:
        rem = int(iv_sec - (time.time() - last_ts))
        eta_txt = "مستحقة الآن" if rem <= 0 else format_backup_interval(rem).replace("كل ", "بعد ", 1)

    hf_badge = "🟢 مفعّل تلقائياً" if st_info.get("hf_enabled") else "⚪ غير مضبوط (اختياري عبر HF_TOKEN)"
    cdb_info = st_db = st_info.get("cloud_db") or {}
    cdb_badge = (
        f"🟢 {str(cdb_info.get('provider', '')).upper()} ({cdb_info.get('last_status', 'متصل')})"
        if cdb_info.get("enabled")
        else "⚪ غير مربوطة بعد (SQLite محلي نشط)"
    )
    ext_badge, ext_warn = _format_external_vault_summary(st_info)
    ext_line = f"📦 <b>القاعدة الخارجية المستقلة:</b> {esc(ext_badge)}" + (f"\n{esc(ext_warn)}" if ext_warn else "")
    has_vol = Path("/data").exists() and os.access("/data", os.W_OK)
    lines = [
        "💾 <b>خزنة النسخ الاحتياطي الشاملة والاستعادة الفورية</b>",
        "━━━━━━━━━━━━━━━━━━━━",
        ext_line,
        f"📡 <b>قناة النسخ الاحتياطي:</b> {ch_badge}",
        f"🗄️ <b>قاعدة البيانات السحابية (بلا فيزا):</b> {esc(cdb_badge)}",
        f"⏱️ <b>التوقيت المجدول (القناة والخاص):</b> {esc(bkp.get('interval_label', 'كل 1 ساعة'))} | {'🟢 مفعّل' if en_flag else '🔴 متوقف'} ({esc(eta_txt)})",
        f"📬 <b>نسخ ZIP التلقائي للخاص (DM):</b> {'🟢 مفعّل' if (en_flag and dm_flag) else '🔴 متوقف'} | ⚡ <b>عند التعديل:</b> {'🟢' if och_flag else '⚪'} | <b>للقناة:</b> {bkp.get('channel_backup_count', 0)}",
        f"🕒 <b>آخر نسخة/استعادة:</b> {esc(st_info.get('last_backup_iso'))}",
    ]
    if bkp.get("last_error"):
        lines.append(f"⚠️ <b>آخر تنبيه إرسال:</b> <code>{esc(bkp.get('last_error'))}</code>")
    lines.extend([
        "━━━━━━━━━━━━━━━━━━━━",
        "📦 <b>المشمول في كل نسخة (بدون أي استثناء):</b>",
        f"• 👥 المستخدمون والصلاحيات: <b>{st_info.get('users_count', 0)}</b> | 📱 الحسابات والإيميلات: <b>{st_info.get('accounts_count', 0)}</b> (🟢 {st_info.get('active_accounts', 0)})",
        f"• 🍪 الجلسات: <b>{st_info.get('sessions_count', 0)}</b> | 💰 القيود المالية والتحويلات: <b>{st_info.get('ledger_count', 0)}</b>",
        f"• 🎟️ الإحالات والتقديمات: <b>{st_info.get('invites_count', 0)}</b> | 💬 تذاكر الدعم والبيع: <b>{st_info.get('tickets_count', 0)}</b>",
        f"• 🎛️ حالات الضبط والواجهة والأزرار: <b>{st_info.get('ui_states_count', 0)}</b> | 📜 السجل الأمني: <b>{st_info.get('audit_count', 0)}</b>",
        f"☁️ <b>مزامنة HF:</b> {hf_badge} | 💾 <b>التخزين:</b> {'/data' if has_vol else 'معزول'}",
        "━━━━━━━━━━━━━━━━━━━━",
        "📥 <b>لاسترجاع أو دمج أي نسخة (.zip أو JSON قديم):</b> أرسل الملف هنا أو أعد توجيهه، وإذا وُجدت بيانات حالية سيخيرك البوت بين <b>الدمج الذكي بدون حذف/تكرار</b> أو الاستبدال الكامل.",
    ])
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(types.InlineKeyboardButton("🗄️ ربط قاعدة بيانات مجانية (بلا فيزا)", callback_data="menu_cloud_db"))
    if ch_id:
        markup.row(
            types.InlineKeyboardButton("📡 تغيير قناة النسخ", callback_data="bkp_set_channel"),
            types.InlineKeyboardButton("🗑️ فصل القناة", callback_data="bkp_clear_channel"),
        )
    else:
        markup.row(types.InlineKeyboardButton("📡 ربط قناة نسخ احتياطي الآن", callback_data="bkp_set_channel"))
    markup.row(
        types.InlineKeyboardButton(f"⏱️ التوقيت: {bkp.get('interval_label', 'كل 1 ساعة')[:20]}", callback_data="menu_bkp_schedule"),
        types.InlineKeyboardButton("🚀 إرسال للقناة الآن", callback_data="act_backup_channel_now"),
    )
    markup.row(
        types.InlineKeyboardButton(f"🔄 تلقائي بالوقت: {'✅' if en_flag else '❌'}", callback_data="bkp_tog_enabled"),
        types.InlineKeyboardButton(f"📬 إرسال للخاص تلقائياً: {'✅' if dm_flag else '❌'}", callback_data="bkp_tog_dm"),
    )
    markup.row(
        types.InlineKeyboardButton(f"⚡ عند التعديل: {'✅' if och_flag else '❌'}", callback_data="bkp_tog_onchange"),
        types.InlineKeyboardButton("🛑 إيقاف التلقائي الآن", callback_data="bkp_stop_auto"),
    )
    markup.row(
        types.InlineKeyboardButton("📦 تصدير نسخة هنا (.zip)", callback_data="act_export_backup"),
        types.InlineKeyboardButton("📥 استعادة فورية من ملف", callback_data="bkp_restore_help"),
    )
    markup.row(
        types.InlineKeyboardButton("☁️ مزامنة HF الآن", callback_data="act_hf_sync_now"),
        types.InlineKeyboardButton(f"🧹 تنظيف التالفة > {BROKEN_ACCOUNT_TTL_HOURS}س", callback_data="act_purge_24h"),
    )
    markup.row(
        types.InlineKeyboardButton("🔄 تحديث الحالة", callback_data="menu_backup_vault"),
        types.InlineKeyboardButton("🔙 اللوحة الرئيسية", callback_data="back_to_main"),
    )
    return "\n".join(lines), markup


def _render_proxies_view(page: int = 0) -> tuple[str, types.InlineKeyboardMarkup]:
    report = get_proxy_detailed_report()
    summary = report["summary"]
    items = report["items"]
    mode = summary["mode"]
    mode_labels = {
        "sticky": "📌 تثبيت ذكي (Sticky)",
        "4g_bridge": "📱 نفق 4G عكسي",
        "direct": "🌐 مباشر بدون بروكسي",
    }
    b4g = summary["bridge_4g"]
    b4g_badge = (
        f"🟢 متصل ({b4g['exit_port']})"
        if b4g.get("client_connected")
        else ("🟡 بانتظار الهاتف" if b4g.get("running") else "⚪ متوقف")
    )
    cfg_cap = int(summary.get("configured_max_per_proxy", 3) or 0)
    safe_cap = int(summary.get("safe_capacity", 0) or 0)
    cap_btn_lbl = f"{cfg_cap} (آمن)" if cfg_cap == 3 else (f"{cfg_cap} (أقصى)" if cfg_cap > 0 else "مفتوح")
    watch_on = bool(summary.get("auto_check_enabled", True))
    watch_iv = int(summary.get("auto_check_interval_sec") or 120)
    watch_lbl = f"🟢 {watch_iv}ث" if watch_on else "⏸️ متوقف"

    lines = [
        "🌐 <b>لوحة البروكسيات والمراقبة الحية</b>",
        "━━━━━━━━━━━━━━━━━━━━",
        f"⚙️ <b>الوضع:</b> {mode_labels.get(mode, mode)} | 📱 <b>4G:</b> {b4g_badge}",
        f"📡 <b>الحالة:</b> <b>{summary['total']}</b> إجمالي (🟢 {summary['alive']} | 🔴 {summary['dead']} | ⏳ {summary['untested']})",
        f"🔗 <b>الربط:</b> {summary['bindings_count']}{f'/{safe_cap}' if safe_cap > 0 else ''} حساب | 🔁 <b>الاستخدامات:</b> {summary.get('total_uses', 0)} | 👁️ <b>الفحص التلقائي:</b> {watch_lbl}",
    ]
    if summary.get("is_overloaded") or (cfg_cap > 0 and summary.get("max_accounts_per_proxy", 0) > cfg_cap):
        lines.append("⚠️ <i>بعض البروكسيات تجاوزت الحد الآمن — اضغط أي IP للتفاصيل أو إعادة التوزيع.</i>")

    markup = types.InlineKeyboardMarkup(row_width=2)
    per_page = 8
    total_pages = max(1, (len(items) + per_page - 1) // per_page)
    page = max(0, min(page, total_pages - 1))
    slice_items = items[page * per_page : (page + 1) * per_page]

    if slice_items:
        lines.append("👇 <i>اضغط على أي IP لعرض استخداماته وأسماء الحسابات المربوطة به:</i>")
        for it in slice_items:
            st_ic = "🟢" if it.get("alive") is True else ("🔴" if it.get("alive") is False else "⚪")
            cc = f"[{it['country_code']}] " if it.get("country_code") else ""
            host_port = f"{it.get('host') or it.get('masked_uri')}:{it.get('port')}" if it.get("port") else it.get("masked_uri", "")
            lbl = f"{st_ic} {cc}{host_port[:22]} | 🔁{it['uses_count']} | 👥{it['bound_count']}"
            markup.row(types.InlineKeyboardButton(lbl, callback_data=f"prx_item_{it['idx']}"))
        if total_pages > 1:
            nav_row = []
            if page > 0:
                nav_row.append(types.InlineKeyboardButton("◀️ السابق", callback_data=f"prx_page_{page - 1}"))
            nav_row.append(types.InlineKeyboardButton(f"📄 {page + 1}/{total_pages}", callback_data="menu_proxies"))
            if page + 1 < total_pages:
                nav_row.append(types.InlineKeyboardButton("التالي ▶️", callback_data=f"prx_page_{page + 1}"))
            markup.row(*nav_row)
    else:
        lines.append("<i>أضف بروكسيات أو شغّل نفق 4G أو اسحب من GitHub من الأزرار:</i>")

    markup.row(
        _btn("➕ إضافة بروكسيات", style="success", callback_data="prx_add_prompt"),
        _btn("🩺 فحص الكل الآن", style="primary", callback_data="prx_check_all"),
    )
    markup.row(
        _btn("🔗 توزيع وربط الحسابات", style="primary", callback_data="prx_bind_existing"),
        _btn("📥 جلب من GitHub", callback_data="prx_fetch_github"),
    )
    markup.row(
        _btn(f"👁️ فحص تلقائي [{'✅' if watch_on else '⏸️'}]", style="success" if watch_on else None, callback_data="prx_toggle_watch"),
        _btn(f"⚖️ حد/IP: {cap_btn_lbl}", callback_data="prx_cycle_cap"),
    )
    markup.row(
        _btn("📱 نفق 4G (بدون VPS)", style="primary", callback_data="prx_4g_menu"),
        _btn("🔀 تبديل الوضع", callback_data="prx_cycle_mode"),
    )
    markup.row(
        _btn("🧹 حذف الميتة", style="danger", callback_data="prx_clear_dead"),
        _btn("🗑️ مسح الكل", style="danger", callback_data="prx_clear_all"),
    )
    markup.row(
        _btn("🔄 تحديث", style="primary", callback_data="menu_proxies"),
        _btn("🔙 الرئيسية", callback_data="back_to_main"),
    )
    return "\n".join(lines), markup


def _render_proxy_detail_view(idx: int) -> tuple[str, types.InlineKeyboardMarkup]:
    report = get_proxy_detailed_report()
    items = report["items"]
    if idx < 0 or idx >= len(items):
        return _render_proxies_view()
    it = items[idx]
    st_badge = "🟢 يعمل بثبات" if it.get("alive") is True else ("🔴 متعطل / ميت" if it.get("alive") is False else "⚪ لم يُفحص بعد")
    lat = f"{it['latency_ms']} ms" if it.get("latency_ms") is not None else "-"
    geo = f"{it.get('country_name') or it.get('country_code') or '-'} | Exit: {it.get('exit_ip') or '-'}"
    cap_txt = f"{it['bound_count']}/{it['max_per_proxy']}" if it.get("max_per_proxy") else str(it["bound_count"])
    lines = [
        f"🛰️ <b>بطاقة البروكسي #{idx + 1}</b>",
        "━━━━━━━━━━━━━━━━━━━━",
        f"🌐 <b>العنوان:</b> <code>{esc(it['masked_uri'])}</code>",
        f"⚡ <b>الحالة:</b> {st_badge} | ⏱️ {lat}",
        f"🌍 <b>الموقع:</b> {esc(geo)}",
        f"🔁 <b>الاستخدامات:</b> <b>{it['uses_count']}</b> (✅ نجح: {it['success_count']} | ❌ فشل: {it['total_fail_count']})",
        f"👥 <b>الحمولة:</b> <b>{cap_txt}</b> حساب | 🕒 آخر استخدام: {esc(it.get('last_used_at') or '-')}",
    ]
    if it.get("last_error"):
        lines.append(f"⚠️ <b>آخر خطأ:</b> <code>{esc(it['last_error'])}</code>")
    lines.append("━━━━━━━━━━━━━━━━━━━━")
    bound_accs = it.get("bound_accounts") or []
    if bound_accs:
        lines.append(f"📱 <b>الحسابات المربوطة بهذا الـ IP ({len(bound_accs)}):</b>")
        for b in bound_accs[:15]:
            b_ico = "🟢" if "نشط" in str(b.get("status", "")) else "🔴"
            lines.append(f"  {b_ico} <b>{esc(b['name'])}</b> (<code>{esc(b['id'])}</code>)")
        if len(bound_accs) > 15:
            lines.append(f"  <i>... و {len(bound_accs) - 15} حساب إضافي</i>")
    else:
        lines.append("<i>لا توجد حسابات مربوطة بهذا الـ IP حالياً.</i>")

    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(
        _btn("🩺 فحص هذا الـ IP", style="primary", callback_data=f"prx_chk_{idx}"),
        _btn("🔁 نقل حساباته لـ IP سليم", style="success", callback_data=f"prx_rebind_{idx}"),
    )
    markup.row(
        _btn("🗑️ حذف هذا الـ IP", style="danger", callback_data=f"prx_del_{idx}"),
        _btn("🔙 قائمة البروكسيات", callback_data="menu_proxies"),
    )
    return "\n".join(lines), markup


def _on_proxy_alert_event(payload: dict) -> None:
    """تنبيه فوري للمطور والأدمن غير المقيد عند سقوط أي IP مع أزرار الإصلاح السريع."""
    try:
        newly_dead = payload.get("newly_dead") or []
        recovered = payload.get("recovered") or []
        if not newly_dead and not recovered:
            return
        acc_by_id = {str(a.get("id")): a for a in load_accounts() if a.get("id")}
        lines = ["🚨 <b>تنبيه مراقب البروكسيات التلقائي</b>", "━━━━━━━━━━━━━━━━━━━━"]
        for d in newly_dead[:5]:
            b_names = [str((acc_by_id.get(aid) or {}).get("name") or aid) for aid in (d.get("bound_account_ids") or [])[:6]]
            acc_txt = ", ".join(b_names) if b_names else "لا توجد حسابات مربوطة"
            lines.append(
                f"🔴 <b>تعطل IP:</b> <code>{esc(d.get('masked_uri') or d.get('host'))}</code>\n"
                f"   ⚠️ السبب: <code>{esc(d.get('error') or 'فشل الاتصال')}</code>\n"
                f"   👥 المتأثرة ({len(d.get('bound_account_ids') or [])}): {esc(acc_txt)}"
            )
        if recovered:
            lines.append(f"🟢 <b>استعاد الاتصال:</b> {len(recovered)} بروكسي عاد للعمل.")
        markup = types.InlineKeyboardMarkup(row_width=2)
        if newly_dead and newly_dead[0].get("idx") is not None:
            i0 = newly_dead[0]["idx"]
            markup.row(
                types.InlineKeyboardButton("🔁 نقل الحسابات لـ IP سليم", callback_data=f"prx_rebind_{i0}"),
                types.InlineKeyboardButton("🩺 إعادة الفحص", callback_data=f"prx_chk_{i0}"),
            )
        markup.row(
            types.InlineKeyboardButton("🧹 حذف الميتة", callback_data="prx_clear_dead"),
            types.InlineKeyboardButton("🌐 غرفة البروكسيات", callback_data="menu_proxies"),
        )
        txt = "\n".join(lines)
        for admin_uid in get_admin_notification_recipients("proxies"):
            safe_send(admin_uid, txt, reply_markup=markup)
    except Exception:
        pass


def _render_4g_bridge_view() -> tuple[str, types.InlineKeyboardMarkup]:
    st = get_4g_bridge_status(include_secrets=True)
    lines = [
        "📱 <b>نفق الفورجي 4G المباشر من هاتفك (go-gost v3 + cloudflared)</b>",
        "━━━━━━━━━━━━━━━━━━━━",
    ]
    markup = types.InlineKeyboardMarkup(row_width=1)
    if not st.get("running"):
        lines.extend([
            "🛰️ <b>الحالة:</b> متوقف حالياً.",
            "",
            "تُحوّل هذه الميزة شريحة هاتفك الأندرويد (4G/5G) إلى بروكسي سكني حقيقي",
            "تخرج منه كل متصفحات البوت السحابي بنفس عنوان IP بلدك دون شراء VPS.",
            "",
            "<i>اضغط تشغيل بالأسفل لاستخراج أمر الربط الفوري لتطبيق Termux أو الكمبيوتر.</i>",
        ])
        markup.row(types.InlineKeyboardButton("🚀 تشغيل خادم نفق 4G الآن", callback_data="prx_4g_start"))
    else:
        conn_txt = "🟢 الهاتف متصل الآن والبوابة جاهزة!" if st.get("client_connected") else "🟡 البوابة جاهزة — شغّل الأمر في Termux بالهاتف للربط"
        lines.extend([
            f"🛰️ <b>الحالة:</b> {conn_txt}",
            f"🌐 <b>بوابة النفق الآمن:</b> <code>{esc(st.get('tunnel_url') or 'جاري التجهيز...')}</code>",
            f"🔌 <b>منفذ الخروج المحلي:</b> <code>127.0.0.1:{st.get('exit_port')}</code>",
        ])
        if st.get("exit_ip"):
            lines.append(f"📍 <b>IP الفورجي المرصود:</b> <code>{esc(st['exit_ip'])}</code> ({esc(st.get('country_code') or '-')})")
        if st.get("termux_cmd"):
            lines.extend([
                "",
                "📲 <b>أمر الربط لهاتف أندرويد (انسخه في Termux):</b>",
                f"<code>{esc(st['termux_cmd'])}</code>",
            ])
        if st.get("pc_cmd"):
            lines.extend([
                "",
                "💻 <b>أمر الربط من ويندوز/لينكس (إن وُجد gost مثبت):</b>",
                f"<code>{esc(st['pc_cmd'])}</code>",
            ])
        markup.row(
            types.InlineKeyboardButton("🔄 فحص اتصال الهاتف والـ IP", callback_data="prx_4g_check_geo"),
            types.InlineKeyboardButton("✅ تفعيل وضع الفورجي للحسابات", callback_data="prx_4g_activate_mode"),
        )
        markup.row(types.InlineKeyboardButton("🛑 إيقاف نفق الفورجي 4G", callback_data="prx_4g_stop"))

    markup.row(types.InlineKeyboardButton("🔙 العودة لقائمة البروكسيات", callback_data="menu_proxies"))
    return "\n".join(lines), markup


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
    is_dev = has_admin_capability(uid, "payment_notices")
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
    is_dev = has_admin_capability(viewer_uid, "payment_notices")
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
        types.InlineKeyboardButton(f"👥 إضافة حسابات للعامة: {'🟢 مفعّل' if cfg.get('public_account_addition', True) else '🔴 معطّل'}", callback_data="toggle_public_acc_add"),
        types.InlineKeyboardButton("🎛️ بوابات الميزات كاملة", callback_data="menu_feature_gates")
    )
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


def _refresh_after_toggle(call: types.CallbackQuery, user_id: int) -> None:
    """إعادة رسم فورية بدون تشويش أو قفز للشاشة الرئيسية عند الضغط على أي خيار تفاعل"""
    with _active_views_lock:
        cur_v = (_active_views.get(user_id) or {}).get("view", "main")
    if cur_v == "fb_tools":
        txt, mk = render_fb_tools_text_and_markup(user_id)
        safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=mk)
    else:
        safe_edit_reply_markup(call.message.chat.id, call.message.message_id, get_main_dashboard_markup(user_id))


def _refresh_tracked_inline_view(uid: int) -> None:
    if not hasattr(bot, "edit_message_text"):
        return
    with _active_views_lock:
        entry = dict(_active_views.get(uid) or {})
    if not entry:
        return

    # لا تعبث بالواجهة إذا كان المستخدم يكتب نصاً أو في وضع إدخال
    st = get_user_state(uid)
    if st.get("input_mode"):
        return

    now = time.monotonic()
    elapsed = now - entry.get("last_push", 0.0)
    if elapsed < 1.0:
        return

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
    elif view == "fb_tools":
        txt, markup = render_fb_tools_text_and_markup(uid)
    elif view == "earn_guide":
        txt, markup = render_earn_guide_text_and_markup(uid)
    elif view == "tempmail":
        txt, markup = render_tempmail_main_view(uid)
    elif view == "feature_gates" and (is_super_admin(uid) or is_admin_delegate(uid, include_manager=True)):
        txt, markup = render_feature_gates_text_and_markup(uid)
    elif view == "feature_detail" and entry.get("feature_id"):
        txt, markup = render_feature_detail_view(uid, entry["feature_id"])
    elif view == "radar" and has_admin_capability(uid, "radar_users"):
        txt, markup = render_surveillance_radar_text_and_markup(viewer_id=uid)
    elif view == "dossier" and has_admin_capability(uid, "radar_users") and target_id:
        txt, markup = render_user_dossier(target_id, viewer_id=uid)
        if not txt:
            txt, markup = render_surveillance_radar_text_and_markup(viewer_id=uid)
    elif view == "audit" and has_admin_capability(uid, "audit_logs"):
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
    elif view == "economy" and has_admin_capability(uid, "points_economy"):
        txt, markup = _render_admin_economy_view()
    elif view == "backup_vault" and has_admin_capability(uid, "backups"):
        txt, markup = _render_backup_vault_view()
    elif view == "proxies" and has_admin_capability(uid, "proxies"):
        txt, markup = _render_proxies_view()
    elif view == "proxies_4g" and has_admin_capability(uid, "proxies"):
        txt, markup = _render_4g_bridge_view()
    elif view == "announcements" and has_admin_capability(uid, "announcements"):
        txt, markup = _render_announcements_view()
    elif view == "ann_detail" and entry.get("ann_id") and has_admin_capability(uid, "announcements"):
        txt, markup = _render_announcement_detail_view(entry["ann_id"])
    elif view == "caller_id":
        txt, markup = render_caller_id_view(uid)
    else:
        return

    # منع تكرار طلب تعديل الرسالة إذا لم يتغير المحتوى لتجنب اختناق واستهلاك حصة تيليجرام
    _cache = getattr(_refresh_tracked_inline_view, "_cache", None)
    if _cache is None:
        _cache = {}
        _refresh_tracked_inline_view._cache = _cache
    ck = f"{uid}_{view}_{chat_id}_{msg_id}"
    cur_hash = hashlib.md5((txt or "").encode("utf-8", errors="ignore")).hexdigest()
    if _cache.get(ck) == cur_hash:
        return
    _cache[ck] = cur_hash

    try:
        bot.edit_message_text(txt, chat_id, msg_id, reply_markup=markup)
    except Exception as exc:
        err_l = str(exc).lower()
        if "message is not modified" in err_l:
            return
        pass


def _live_inline_sync_worker() -> None:
    while True:
        with _live_sync_cond:
            while not _live_sync_pending_uids:
                _live_sync_cond.wait(timeout=30.0)
            uids = list(_live_sync_pending_uids)
            _live_sync_pending_uids.clear()
        time.sleep(1.2)  # دمج وتجميع التحديثات المتتالية لمنع إغراق تليجرام وحظر الخادم
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
        st = get_user_state(uid)
        if st.get("input_mode"):
            continue
        with _active_views_lock:
            v = (_active_views.get(uid) or {}).get("view", "")
        # إذا كانت الواجهة معالج تفاعلي، نافذة فرعية، تفاصيل إعلان، أو إدارة بريد، لا نزعجه بتحديث خاطف يغلق الشاشة
        transient_exact = {
            "ann_detail", "ann_theme", "ann_new", "announcements",
            "tempmail", "tempmail_pick_domain", "tempmail_inbox", "tempmail_history",
            "feature_detail", "feature_gates", "caller_id"
        }
        if v in transient_exact or v.startswith("wizard_") or v.startswith("sub_") or v.startswith("acc_view_") or v.startswith("ann_") or v.startswith("tm_"):
            continue

        if is_super_admin(uid) or is_admin_delegate(uid, include_manager=True):
            to_wake.append(uid)
        elif target_uid == uid or (target_uid == 0 and scope in ("economy", "system", "announcements", "feature_gates")) or (scope == "accounts" and has_permission(uid, "can_use_accounts")):
            to_wake.append(uid)

    if to_wake:
        with _live_sync_cond:
            _live_sync_pending_uids.update(to_wake)
            _live_sync_cond.notify_all()


# ----------------- معالجات الأوامر والقوائم -----------------

def _persistent_bottom_keyboard(user_id: int) -> types.ReplyKeyboardMarkup:
    """كيبورد اختصار دائم أسفل صندوق الكتابة يفتح البوت بضغطة واحدة بألوان Bot API 9.4"""
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, is_persistent=True)
    is_dev = is_super_admin(user_id)
    cap_prox = has_admin_capability(user_id, "proxies")
    cap_radar = has_admin_capability(user_id, "radar_users")
    can_add = is_dev or has_permission(user_id, "can_add_accounts")
    row1 = [_kbtn("🏠 القائمة الرئيسية", style="primary")]
    if can_add:
        row1.append(_kbtn("➕ إضافة حساب", style="success"))
    kb.row(*row1)
    if cap_prox or cap_radar:
        row2 = []
        if cap_prox:
            row2.append(_kbtn("🌐 البروكسيات"))
        if cap_radar:
            row2.append(_kbtn("🛰️ رادار المستخدمين"))
        kb.row(*row2)
    else:
        kb.row(_kbtn("💰 نقاطي"))
    return kb


@bot.message_handler(commands=['keys'])
def cmd_keys(message: types.Message):
    if not check_user_access_gate(message.from_user, message.chat.id):
        return
    uid = message.from_user.id
    st = get_user_state(uid)
    st["bottom_kb_sent"] = True
    safe_send(
        message.chat.id,
        "⌨️ تم تثبيت أزرار الاختصار الدائمة أسفل المحادثة (اضغط <b>🏠 القائمة الرئيسية</b> بأي وقت).",
        reply_markup=_persistent_bottom_keyboard(uid),
    )


@bot.message_handler(commands=['num', 'number', 'kashf', 'من_المتصل'])
def cmd_caller_id(message: types.Message):
    if not check_user_access_gate(message.from_user, message.chat.id):
        return
    uid = message.from_user.id
    raw_parts = (message.text or "").strip().split(maxsplit=1)
    if len(raw_parts) < 2 or not raw_parts[1].strip():
        txt, mk = render_caller_id_view(uid)
        safe_send(message.chat.id, txt, reply_markup=mk)
        return
    phone_query = raw_parts[1].strip()
    bot.send_chat_action(message.chat.id, "typing")
    res = YemenCallerIDAPI.lookup_number(phone_query)
    txt, mk = render_caller_id_view(uid, result=res)
    safe_send(message.chat.id, txt, reply_markup=mk)


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
    if not st.get("bottom_kb_sent"):
        st["bottom_kb_sent"] = True
        safe_send(
            message.chat.id,
            "⌨️ تم تثبيت زر <b>🏠 القائمة الرئيسية</b> أسفل الشاشة لتفتح القائمة بضغطة واحدة دائماً.",
            reply_markup=_persistent_bottom_keyboard(uid),
        )
    sent = safe_send(
        message.chat.id,
        get_dashboard_text(uid),
        reply_markup=get_main_dashboard_markup(uid)
    )
    if sent and hasattr(sent, "message_id"):
        _track_view(uid, message.chat.id, sent.message_id, "main")
    try:
        open_anns = [a for a in list_announcements(only_active=True) if a.get("repeat_on_open")]
        if open_anns:
            top_a = open_anns[0]
            r_media = None
            if top_a.get("delivery_mode") in ("animated_card", "photo_card"):
                try:
                    r_media = render_announcement_media(
                        top_a, animated=(top_a.get("delivery_mode") == "animated_card"), allow_browser=True
                    )
                except Exception:
                    r_media = None
            new_mid, is_m = _send_announcement_to_chat(
                message.chat.id, top_a, is_repeat=False, rendered_media=r_media
            )
            if new_mid:
                record_announcement_sent_chats(
                    top_a["id"], {message.chat.id: new_mid}, media_cids=({message.chat.id} if is_m else None)
                )
    except Exception:
        pass


@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call: types.CallbackQuery):
    try:
        return _handle_callbacks_impl(call)
    finally:
        try:
            persist_user_states()
        except Exception:
            pass


def _handle_callbacks_impl(call: types.CallbackQuery):
    user_id = call.from_user.id
    data = call.data or ""

    if data == "noop":
        safe_answer(call.id)
        return

    if not _check_user_rate_limit(user_id):
        safe_answer(call.id, "⏳ تمهل ثانية؛ تم استلام طلبات متتالية كثيرة لحماية الخادم.", show_alert=False)
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
            "menu_wizard_message", "menu_manage_accs", "menu_wallet", "menu_referral",
            "menu_support", "menu_admin_economy", "menu_surveillance_radar", "menu_backup_vault",
            "menu_bkp_schedule", "menu_proxies", "menu_cloud_db", "menu_announcements",
            "prx_4g_menu", "menu_fb_tools", "menu_earn_guide", "menu_feature_gates", "menu_tempmail"
        }
        if dest.startswith("fg_view_"):
            allowed_dests.add(dest)
        if dest not in allowed_dests:
            dest = "back_to_main"
        st = get_user_state(user_id)
        st["input_mode"] = None
        st["temp_acc_data"] = {}
        safe_answer(call.id, "تم الإلغاء والرجوع")
        call.data = dest
        _handle_callbacks_impl(call)
        return

    # 1. بوابة موافقة / حظر المطور الأكبر (أو المفوض المخوّل بالرادار دون مساس بالنظراء/المطور)
    if data.startswith("gate_app_"):
        if not has_admin_capability(user_id, "radar_users"):
            record_audit_log(user_id, call.from_user.first_name or "", "SECURITY_BLOCK", f"محاولة غير مصرحة لتنفيذ {data}")
            safe_answer(call.id, "⛔ خاص بالمطور والأدمن المخوّل فقط.", show_alert=True)
            return
        try:
            target_uid = int(data.replace("gate_app_", ""))
        except ValueError:
            return
        if is_super_admin(target_uid):
            safe_answer(call.id, "👑 المطور الأكبر معتمد تلقائياً دوماً.")
            return
        if not can_manage_target_user(user_id, target_uid):
            safe_answer(call.id, "⛔ لا تملك صلاحية تعديل هذا الحساب أو هذه الرتبة.", show_alert=True)
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
            "🎉 <b>تمت الموافقة المبدئية على حسابك من قبل الإدارة.</b>\n"
            "🔒 بانتظار قيام الإدارة بتحديد الميزات المسموحة لك. أرسل /start لعرض لوحتك."
        )
        return

    elif data.startswith("gate_ban_"):
        if not has_admin_capability(user_id, "radar_users"):
            record_audit_log(user_id, call.from_user.first_name or "", "SECURITY_BLOCK", f"محاولة غير مصرحة لتنفيذ {data}")
            safe_answer(call.id, "⛔ خاص بالمطور والأدمن المخوّل فقط.", show_alert=True)
            return
        try:
            target_uid = int(data.replace("gate_ban_", ""))
        except ValueError:
            return
        if is_super_admin(target_uid):
            safe_answer(call.id, "🛡️ محظور برمجياً: لا يمكن حظر المطور الأكبر أبداً!", show_alert=True)
            return
        if not can_manage_target_user(user_id, target_uid):
            record_audit_log(user_id, call.from_user.first_name or "", "SECURITY_BLOCK", f"محاولة حظر خارج النطاق: {target_uid}")
            safe_answer(call.id, "⛔ لا يمكنك حظر هذه الرتبة.", show_alert=True)
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

    # 2.5 عرض/إخفاء الإعلانات العائمة التفاعلية (متاحة لجميع المعتمدين)
    if data.startswith("promo_view_"):
        ann_id = data[len("promo_view_"):]
        ann = get_announcement_by_id(ann_id)
        if not ann:
            safe_answer(call.id, "⌛ انتهى هذا الإعلان أو تمت إزالته.", show_alert=True)
            return
        popup_txt = f"✨ [{ann.get('badge', 'إعلان')}] {ann.get('title', '')}\n\n{ann.get('body', '')}\n\n⏳ {ann.get('remaining_label', '')}"
        safe_answer(call.id, popup_txt[:195], show_alert=True)
        return

    elif data.startswith("promo_ack_"):
        try:
            bot.unpin_chat_message(call.message.chat.id, call.message.message_id)
        except Exception:
            pass
        safe_answer(call.id, "✅ تم إخفاء الإعلان.")
        # إذا كانت رسالة الإعلان عبارة عن صورة/GIF متحركة (بدون نص قابل للتحرير) نحذفها ونرسل الرئيسية نظيفة
        is_media_bubble = bool(getattr(call.message, "photo", None) or getattr(call.message, "animation", None))
        if is_media_bubble:
            try:
                bot.delete_message(call.message.chat.id, call.message.message_id)
            except Exception:
                pass
            sent_m = safe_send(
                call.message.chat.id,
                get_dashboard_text(user_id),
                reply_markup=get_main_dashboard_markup(user_id),
            )
            if sent_m and hasattr(sent_m, "message_id"):
                _track_view(user_id, call.message.chat.id, sent_m.message_id, "main")
        else:
            safe_edit_message(
                get_dashboard_text(user_id),
                call.message.chat.id, call.message.message_id,
                reply_markup=get_main_dashboard_markup(user_id)
            )
            _track_view(user_id, call.message.chat.id, call.message.message_id, "main")
        return

    # ----------------- أدوات فيسبوك، دليل الربح، وبوابات الميزات -----------------
    elif data == "menu_fb_tools":
        safe_answer(call.id)
        _track_view(user_id, call.message.chat.id, call.message.message_id, "fb_tools")
        txt, mk = render_fb_tools_text_and_markup(user_id)
        safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=mk)
        return

    elif data == "menu_earn_guide":
        safe_answer(call.id)
        _track_view(user_id, call.message.chat.id, call.message.message_id, "earn_guide")
        txt, mk = render_earn_guide_text_and_markup(user_id)
        safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=mk)
        return

    elif data == "menu_feature_gates":
        if not (is_super_admin(user_id) or is_admin_delegate(user_id, include_manager=True)):
            record_audit_log(user_id, call.from_user.first_name or "", "SECURITY_BLOCK", "محاولة فتح بوابات الميزات بدون صلاحية")
            safe_answer(call.id, "⛔ هذه اللوحة خاصة بالمطور والأدمن فقط.", show_alert=True)
            return
        _track_view(user_id, call.message.chat.id, call.message.message_id, "feature_gates")
        txt, mk = render_feature_gates_text_and_markup(user_id)
        safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=mk)
        return

    elif data.startswith("fg_view_"):
        if not (is_super_admin(user_id) or is_admin_delegate(user_id, include_manager=True)):
            safe_answer(call.id, "⛔ غير مصرح لك.", show_alert=True)
            return
        fid = data.replace("fg_view_", "").strip()
        _track_view(user_id, call.message.chat.id, call.message.message_id, "feature_detail")
        with _active_views_lock:
            if user_id in _active_views:
                _active_views[user_id]["feature_id"] = fid
        txt, mk = render_feature_detail_view(user_id, fid)
        safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=mk)
        return

    elif data.startswith("fg_scope_"):
        if not (is_super_admin(user_id) or is_admin_delegate(user_id, include_manager=True)):
            safe_answer(call.id, "⛔ غير مصرح لك.", show_alert=True)
            return
        parts = data.split("_")
        if len(parts) >= 4:
            new_scope = parts[-1]
            fid = "_".join(parts[2:-1])
            update_feature_gate(fid, {"scope": new_scope})
            safe_answer(call.id, f"تم تغيير النطاق إلى: {new_scope}")
            txt, mk = render_feature_detail_view(user_id, fid)
            safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=mk)
        return

    elif data.startswith("fg_price_"):
        if not (is_super_admin(user_id) or is_admin_delegate(user_id, include_manager=True)):
            safe_answer(call.id, "⛔ غير مصرح لك.", show_alert=True)
            return
        parts = data.split("_")
        if len(parts) >= 4:
            new_pricing = parts[-1]
            fid = "_".join(parts[2:-1])
            update_feature_gate(fid, {"pricing": new_pricing})
            safe_answer(call.id, f"تم تغيير التسعير إلى: {new_pricing}")
            txt, mk = render_feature_detail_view(user_id, fid)
            safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=mk)
        return

    elif data.startswith("fg_status_"):
        if not (is_super_admin(user_id) or is_admin_delegate(user_id, include_manager=True)):
            safe_answer(call.id, "⛔ غير مصرح لك.", show_alert=True)
            return
        parts = data.split("_")
        if len(parts) >= 4:
            new_status = parts[-1]
            fid = "_".join(parts[2:-1])
            update_feature_gate(fid, {"status": new_status})
            safe_answer(call.id, f"تم تغيير الحالة إلى: {new_status}")
            txt, mk = render_feature_detail_view(user_id, fid)
            safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=mk)
        return

    elif data.startswith("fg_adduser_"):
        if not (is_super_admin(user_id) or is_admin_delegate(user_id, include_manager=True)):
            safe_answer(call.id, "⛔ غير مصرح لك.", show_alert=True)
            return
        fid = data.replace("fg_adduser_", "").strip()
        st = get_user_state(user_id)
        st["input_mode"] = f"waiting_fg_user_{fid}"
        safe_answer(call.id)
        safe_send(
            call.message.chat.id,
            f"👤 <b>أرسل الآن الآيدي الرقمي للمستخدم المراد منحه ميزة ({fid}):</b>",
            reply_markup=_prompt_back_markup(f"cancel_to:fg_view_{fid}")
        )
        return

    elif data.startswith("fg_deluser_"):
        if not (is_super_admin(user_id) or is_admin_delegate(user_id, include_manager=True)):
            safe_answer(call.id, "⛔ غير مصرح لك.", show_alert=True)
            return
        parts = data.split("_")
        if len(parts) >= 4:
            target_uid_str = parts[-1]
            fid = "_".join(parts[2:-1])
            if target_uid_str.isdigit():
                remove_allowed_user(fid, int(target_uid_str))
                safe_answer(call.id, "تم سحب الميزة من المستخدم")
            txt, mk = render_feature_detail_view(user_id, fid)
            safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=mk)
        return

    elif data == "fg_new_custom":
        if not (is_super_admin(user_id) or is_admin_delegate(user_id, include_manager=True)):
            safe_answer(call.id, "⛔ غير مصرح لك.", show_alert=True)
            return
        st = get_user_state(user_id)
        st["input_mode"] = "waiting_new_fg_name"
        safe_answer(call.id)
        safe_send(
            call.message.chat.id,
            "✨ <b>أرسل الآن اسم الميزة الجديدة التي ترغب ببرمجتها وإضافتها لنظام البوابات:</b>\n"
            "<i>(مثال: حملات البريد الآلي، منشئ الحسابات الذكي، صانع المنشورات)</i>",
            reply_markup=_prompt_back_markup("cancel_to:menu_feature_gates")
        )
        return

    elif data == "toggle_public_acc_add":
        if not (is_super_admin(user_id) or has_admin_capability(user_id, "points_economy")):
            safe_answer(call.id, "⛔ غير مصرح لك.", show_alert=True)
            return
        cur_v = bool(load_economy_settings().get("public_account_addition", True))
        update_economy_settings({"public_account_addition": not cur_v})
        update_feature_gate(
            "public_account_addition",
            {"status": "active" if not cur_v else "disabled", "scope": "public" if not cur_v else "admins"}
        )
        safe_answer(call.id, f"إضافة الحسابات للعامة: {'مفعلة 🟢' if not cur_v else 'معطلة 🔴'}")
        txt, mk = _render_admin_economy_view()
        safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=mk)
        return

    # ----------------- مركز البريد المؤقت والدائم وسلة الاسترجاع -----------------
    elif data == "menu_tempmail":
        safe_answer(call.id)
        if not is_feature_enabled(user_id, "tempmail") and not is_super_admin(user_id):
            safe_answer(call.id, "⛔ ميزة البريد مغلقة حالياً أو تتطلب إذناً من الإدارة.", show_alert=True)
            return
        _track_view(user_id, call.message.chat.id, call.message.message_id, "tempmail")
        txt, mk = render_tempmail_main_view(user_id)
        safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=mk)
        return

    elif data == "tm_new_rand":
        if not is_feature_enabled(user_id, "tempmail") and not is_super_admin(user_id):
            safe_answer(call.id, "⛔ ميزة البريد مغلقة حالياً.", show_alert=True)
            return
        mb = tm_m.create_random_email(user_id)
        safe_answer(call.id, f"✅ تم إنشاء وتفعيل البريد: {mb.get('email')}")
        txt, mk = render_tempmail_main_view(user_id)
        safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=mk)
        return

    elif data == "tm_pick_dom":
        if not is_feature_enabled(user_id, "tempmail") and not is_super_admin(user_id):
            safe_answer(call.id, "⛔ ميزة البريد مغلقة حالياً.", show_alert=True)
            return
        txt, mk = render_tempmail_pick_domain_view(user_id, page=0)
        safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=mk)
        return

    elif data.startswith("tm_dompage_"):
        safe_answer(call.id)
        page_str = data.replace("tm_dompage_", "").strip()
        page = int(page_str) if page_str.isdigit() else 0
        txt, mk = render_tempmail_pick_domain_view(user_id, page=page)
        safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=mk)
        return

    elif data.startswith("tm_seldom_"):
        dom = data.replace("tm_seldom_", "").strip()
        st = get_user_state(user_id)
        st["tm_pending_domain"] = dom
        st["input_mode"] = "waiting_tm_custom_name"
        safe_answer(call.id)
        safe_send(
            call.message.chat.id,
            f"✏️ <b>أرسل الآن اسم المستخدم المطلوب للبريد:</b>\n\n"
            f"🌐 النطاق المختار: <code>@{esc(dom)}</code>\n"
            f"مثال: أرسل <code>john.dev</code> ليكون البريد <code>john.dev@{esc(dom)}</code>",
            reply_markup=_prompt_back_markup("cancel_to:menu_tempmail")
        )
        return

    elif data == "tm_inbox":
        safe_answer(call.id, "🔄 جاري فحص الوارد...")
        txt, mk = render_tempmail_inbox_view(user_id)
        safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=mk)
        return

    elif data.startswith("tm_inbox_"):
        h = data.replace("tm_inbox_", "").strip()
        hist = tm_m.get_user_history(user_id, limit=50)
        target_em = None
        for item in hist:
            em = item.get("email", "")
            if hashlib.sha1(em.encode()).hexdigest()[:8] == h:
                target_em = em
                break
        safe_answer(call.id, "🔄 جاري فحص وتحديث الصندوق...")
        txt, mk = render_tempmail_inbox_view(user_id, email=target_em)
        safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=mk)
        return

    elif data.startswith("tm_viewbox_"):
        h = data.replace("tm_viewbox_", "").strip()
        hist = tm_m.get_user_history(user_id, limit=50)
        target_em = None
        for item in hist:
            em = item.get("email", "")
            if hashlib.sha1(em.encode()).hexdigest()[:8] == h:
                target_em = em
                break
        if target_em:
            safe_answer(call.id, f"📬 فتح صندوق البريد")
            txt, mk = render_tempmail_inbox_view(user_id, email=target_em)
            safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=mk)
        else:
            safe_answer(call.id, "لم يتم العثور على هذا البريد في الأرشيف.")
        return

    elif data in ("tm_history", "menu_tm_history"):
        safe_answer(call.id)
        txt, mk = render_tempmail_history_view(user_id)
        safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=mk)
        return

    elif data == "tm_del_active":
        act = tm_m.get_user_active_mailbox(user_id)
        if act and act.get("email"):
            tm_m.delete_user_email(user_id, act["email"], deleted_by=user_id)
            safe_answer(call.id, "🗑️ تم نقل البريد إلى سلة المحذوفات بنجاح!", show_alert=True)
        else:
            safe_answer(call.id, "لا يوجد بريد نشط لحذفه.")
        txt, mk = render_tempmail_main_view(user_id)
        safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=mk)
        return

    elif data.startswith("tm_switch_"):
        h = data.replace("tm_switch_", "").strip()
        hist = tm_m.get_user_history(user_id, limit=50)
        target_em = None
        for item in hist:
            em = item.get("email", "")
            if hashlib.sha1(em.encode()).hexdigest()[:8] == h:
                target_em = em
                break
        if target_em:
            tm_m.set_user_active_mailbox(user_id, target_em)
            safe_answer(call.id, f"✅ تم تفعيل البريد: {target_em}")
        else:
            safe_answer(call.id, "لم يتم العثور على هذا البريد.")
        txt, mk = render_tempmail_main_view(user_id)
        safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=mk)
        return

    elif data.startswith("tm_del_"):
        h = data.replace("tm_del_", "").strip()
        hist = tm_m.get_user_history(user_id, limit=50)
        target_em = None
        for item in hist:
            em = item.get("email", "")
            if hashlib.sha1(em.encode()).hexdigest()[:8] == h:
                target_em = em
                break
        if target_em:
            tm_m.delete_user_email(user_id, target_em, deleted_by=user_id)
            safe_answer(call.id, "🗑️ تم نقل البريد إلى سلة المحذوفات!")
        txt, mk = render_tempmail_history_view(user_id)
        safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=mk)
        return

    elif data == "tm_admin_all":
        if not (is_super_admin(user_id) or has_admin_capability(user_id, "radar_users")):
            safe_answer(call.id, "⛔ غير مصرح لك.", show_alert=True)
            return
        txt, mk = render_tempmail_admin_all_view(user_id)
        safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=mk)
        return

    elif data.startswith("tm_admbox_"):
        if not (is_super_admin(user_id) or has_admin_capability(user_id, "radar_users")):
            safe_answer(call.id, "⛔ غير مصرح لك.", show_alert=True)
            return
        h = data.replace("tm_admbox_", "").strip()
        all_emails = tm_m.list_all_emails_admin(user_id)
        target_em = None
        for item in all_emails:
            em = item.get("email", "")
            if hashlib.sha1(em.encode()).hexdigest()[:8] == h:
                target_em = em
                break
        if target_em:
            txt, mk = render_tempmail_inbox_view(user_id, email=target_em)
            safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=mk)
        else:
            safe_answer(call.id, "البريد غير موجود.")
        return

    elif data == "tm_admin_trash":
        if not (is_super_admin(user_id) or has_admin_capability(user_id, "radar_users")):
            safe_answer(call.id, "⛔ غير مصرح لك.", show_alert=True)
            return
        txt, mk = render_tempmail_admin_trash_view(user_id)
        safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=mk)
        return

    elif data.startswith("tm_restore_"):
        if not (is_super_admin(user_id) or has_admin_capability(user_id, "radar_users")):
            safe_answer(call.id, "⛔ غير مصرح لك.", show_alert=True)
            return
        h = data.replace("tm_restore_", "").strip()
        trash = tm_m.list_trash_emails_admin(user_id)
        target_em = None
        for item in trash:
            em = item.get("email", "")
            if hashlib.sha1(em.encode()).hexdigest()[:8] == h:
                target_em = em
                break
        if target_em:
            tm_m.restore_deleted_email(target_em, restored_by=user_id)
            safe_answer(call.id, f"✅ تم استرجاع البريد بنجاح: {target_em}", show_alert=True)
        else:
            safe_answer(call.id, "لم يتم العثور على البريد في السلة.")
        txt, mk = render_tempmail_admin_trash_view(user_id)
        safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=mk)
        return

    elif data.startswith("tm_copyotp_"):
        otp = data.replace("tm_copyotp_", "").strip()
        safe_answer(call.id, f"كود OTP:\n{otp}", show_alert=True)
        return

    # ----------------- كاشف الأرقام اليمنية 967 -----------------
    elif data == "menu_caller_id":
        safe_answer(call.id)
        if not is_feature_enabled(user_id, "yemen_caller_id") and not is_super_admin(user_id):
            safe_answer(call.id, "⛔ ميزة كاشف الأرقام مغلقة حالياً أو تتطلب إذناً من الإدارة.", show_alert=True)
            return
        _track_view(user_id, call.message.chat.id, call.message.message_id, "caller_id")
        txt, mk = render_caller_id_view(user_id)
        safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=mk)
        return

    elif data == "caller_id_prompt":
        safe_answer(call.id)
        st = get_user_state(user_id)
        st["input_mode"] = "waiting_caller_id_number"
        safe_send(
            call.message.chat.id,
            "📞 <b>أرسل الآن الرقم اليمني للبحث عنه وكشف صاحبه:</b>\n\n"
            "📌 صيغ مقبولة:\n"
            "• <code>777123456</code> (يمن موبايل)\n"
            "• <code>733123456</code> (يو)\n"
            "• <code>711123456</code> (سبأفون)\n"
            "• <code>01234567</code> (هاتف ثابت)",
            reply_markup=_prompt_back_markup("cancel_to:menu_caller_id")
        )
        return

    # ----------------- مركز الإعلانات العائمة والمنبثقة للمطور والأدمن غير المقيد -----------------
    elif data == "menu_announcements":
        if not has_admin_capability(user_id, "announcements"):
            record_audit_log(user_id, call.from_user.first_name or "", "SECURITY_BLOCK", "محاولة فتح مركز الإعلانات بدون صلاحية")
            safe_answer(call.id, "⛔ هذه الصلاحية خاصة بالمطور أو الأدمن غير المقيد.", show_alert=True)
            return
        txt, markup = _render_announcements_view()
        _track_view(user_id, call.message.chat.id, call.message.message_id, "announcements")
        safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=markup)
        return

    elif data == "ann_theme_menu":
        if not has_admin_capability(user_id, "announcements"):
            safe_answer(call.id, "⛔ غير مصرح لك.", show_alert=True)
            return
        txt, mk = _render_theme_config_view()
        safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=mk)
        return

    elif data == "ann_ce_tog":
        safe_answer(call.id)
        if not has_admin_capability(user_id, "announcements"):
            return
        cur_ce = bool(get_theme_config().get("custom_emojis_enabled", True))
        update_theme_config({"custom_emojis_enabled": not cur_ce})
        safe_answer(call.id, "✅ تم تحديث حالة الأيقونات المخصصة.")
        txt, mk = _render_theme_config_view()
        safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=mk)
        return

    elif data.startswith("ann_ce_set_"):
        safe_answer(call.id)
        if not has_admin_capability(user_id, "announcements"):
            return
        slot = data[len("ann_ce_set_"):]
        if slot not in DEFAULT_THEME_EMOJIS:
            return
        st["input_mode"] = f"waiting_ann_ce_{slot}"
        safe_answer(call.id)
        safe_send(
            call.message.chat.id,
            f"🧩 <b>ضبط Custom Emoji ID لخانة (<code>{esc(slot)}</code>):</b>\n"
            "<blockquote>أرسل الرقم التعريفي للإيموجي المخصص (أو أرسل <code>0</code> لمسحه والعودة للافتراضي).</blockquote>",
            reply_markup=_prompt_back_markup("ann_theme_menu"),
        )
        return

    elif data == "ann_new":
        if not has_admin_capability(user_id, "announcements"):
            safe_answer(call.id, "⛔ غير مصرح لك.", show_alert=True)
            return
        st["temp_ann_data"] = {
            "badge": "ميزة جديدة",
            "display_style": "floating_card",
            "delivery_mode": "animated_card",
            "repeat_behavior": "replace",
            "effect_preset": "fire",
            "duration_sec": 86400,
            "repeat_interval_sec": 3600,
            "repeat_on_open": True,
            "pin_in_chat": False,
        }
        st["input_mode"] = "waiting_ann_title"
        safe_answer(call.id)
        safe_send(
            call.message.chat.id,
            "📢 <b>إنشاء إعلان ببطاقة متحركة وملونة (الخطوة 1/3)</b>\n"
            "<blockquote>✍️ أرسل <b>عنوان الإعلان</b> الآن (سيتم تصيير بطاقة GIF متحركة + أزرار Bot API 9.4 ملونة تلقائياً).</blockquote>",
            reply_markup=_prompt_back_markup("menu_announcements"),
        )
        return

    elif data.startswith("ann_c_dur_"):
        safe_answer(call.id)
        if not has_admin_capability(user_id, "announcements"):
            return
        try:
            d_sec = int(data[len("ann_c_dur_"):])
        except ValueError:
            d_sec = 86400
        draft = st.setdefault("temp_ann_data", {})
        draft["duration_sec"] = d_sec
        mk = types.InlineKeyboardMarkup(row_width=2)
        for rsec, rlbl in REPEAT_PRESETS:
            mk.add(_btn(f"🔁 {rlbl}", style="primary" if rsec == 0 else None, callback_data=f"ann_c_rep_{rsec}"))
        safe_answer(call.id, f"⏱️ المدة: {format_duration_ar(d_sec)}")
        safe_edit_message(
            f"📢 <b>اختر نظام التكرار والظهور للإعلان:</b>\n"
            f"<blockquote>• <b>العنوان:</b> {esc(draft.get('title'))}\n"
            f"• <b>المدة:</b> {esc(format_duration_ar(d_sec))}\n"
            f"• <b>نمط التكرار الافتراضي:</b> استبدال نظيف بدون تثبيت مكرر</blockquote>",
            call.message.chat.id, call.message.message_id,
            reply_markup=mk,
        )
        return

    elif data.startswith("ann_c_rep_"):
        safe_answer(call.id)
        if not has_admin_capability(user_id, "announcements"):
            return
        try:
            r_sec = int(data[len("ann_c_rep_"):])
        except ValueError:
            r_sec = 3600
        draft = st.get("temp_ann_data") or {}
        if not (draft.get("title") and draft.get("body")):
            safe_answer(call.id, "⚠️ انتهت المسودة؛ ابدأ إنشاء الإعلان من جديد.", show_alert=True)
            return
        ann = create_announcement(
            title=draft["title"],
            body=draft["body"],
            created_by=user_id,
            badge=draft.get("badge", "ميزة جديدة"),
            display_style=draft.get("display_style", "floating_card"),
            delivery_mode=draft.get("delivery_mode", "animated_card"),
            repeat_behavior=draft.get("repeat_behavior", "replace"),
            effect_preset=draft.get("effect_preset", "fire"),
            duration_sec=int(draft.get("duration_sec", 86400)),
            repeat_interval_sec=r_sec,
            repeat_on_open=bool(draft.get("repeat_on_open", True)),
            pin_in_chat=bool(draft.get("pin_in_chat", False)),
        )
        st["temp_ann_data"] = {}
        st["input_mode"] = None
        safe_answer(call.id, "🚀 جاري تصيير البطاقة وبث الإعلان العائم...")
        b_res = _broadcast_announcement_to_users(ann, is_repeat=False)
        record_audit_log(user_id, call.from_user.first_name or "", "ANNOUNCEMENT_CREATED", f"إعلان متحرك: {ann['title']} | مستلمون: {b_res['sent']}")
        txt, mk = _render_announcement_detail_view(ann["id"])
        safe_edit_message(
            txt + f"\n\n✅ <b>تم البث إلى {b_res['sent']} محادثة</b> ({'🎞️ بطاقة بصرية' if b_res.get('media') else '💬 بطاقة ذكية'})!",
            call.message.chat.id, call.message.message_id,
            reply_markup=mk,
        )
        return

    elif data.startswith("ann_dm_"):
        safe_answer(call.id)
        if not has_admin_capability(user_id, "announcements"):
            return
        ann_id = data[len("ann_dm_"):]
        cur_a = get_announcement_by_id(ann_id)
        if not cur_a:
            return
        order = ("animated_card", "photo_card", "smart_text")
        cur_m = cur_a.get("delivery_mode", "animated_card")
        nxt = order[(order.index(cur_m) + 1) % len(order)] if cur_m in order else "animated_card"
        update_announcement_delivery(ann_id, delivery_mode=nxt)
        safe_answer(call.id, f"🎨 {DELIVERY_MODES.get(nxt, nxt)}")
        txt, mk = _render_announcement_detail_view(ann_id)
        safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=mk)
        return

    elif data.startswith("ann_rb_"):
        safe_answer(call.id)
        if not has_admin_capability(user_id, "announcements"):
            return
        ann_id = data[len("ann_rb_"):]
        cur_a = get_announcement_by_id(ann_id)
        if not cur_a:
            return
        order = ("replace", "edit_live", "new_msg")
        cur_r = cur_a.get("repeat_behavior", "replace")
        nxt = order[(order.index(cur_r) + 1) % len(order)] if cur_r in order else "replace"
        update_announcement_delivery(ann_id, repeat_behavior=nxt)
        safe_answer(call.id, f"🔁 {REPEAT_BEHAVIORS.get(nxt, nxt)}")
        txt, mk = _render_announcement_detail_view(ann_id)
        safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=mk)
        return

    elif data.startswith("ann_pin_"):
        safe_answer(call.id)
        if not has_admin_capability(user_id, "announcements"):
            return
        ann_id = data[len("ann_pin_"):]
        cur_a = get_announcement_by_id(ann_id)
        if not cur_a:
            return
        new_pin = not bool(cur_a.get("pin_in_chat", False))
        update_announcement_delivery(ann_id, pin_in_chat=new_pin)
        if not new_pin:
            _unpin_announcement_chats(cur_a)
        safe_answer(call.id, "📌 تم تفعيل التثبيت (مرة واحدة)" if new_pin else "🪟 تم إيقاف التثبيت (وضع عائم نظيف)")
        txt, mk = _render_announcement_detail_view(ann_id)
        safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=mk)
        return

    elif data.startswith("ann_eff_"):
        safe_answer(call.id)
        if not has_admin_capability(user_id, "announcements"):
            return
        ann_id = data[len("ann_eff_"):]
        cur_a = get_announcement_by_id(ann_id)
        if not cur_a:
            return
        order = tuple(EFFECT_PRESETS.keys())
        cur_e = cur_a.get("effect_preset", "none")
        nxt = order[(order.index(cur_e) + 1) % len(order)] if cur_e in order else "fire"
        update_announcement_delivery(ann_id, effect_preset=nxt)
        safe_answer(call.id, f"🎆 {(EFFECT_PRESETS.get(nxt) or ('',))[0]}")
        txt, mk = _render_announcement_detail_view(ann_id)
        safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=mk)
        return

    elif data.startswith("ann_view_"):
        if not has_admin_capability(user_id, "announcements"):
            safe_answer(call.id, "⛔ غير مصرح لك.", show_alert=True)
            return
        ann_id = data[len("ann_view_"):]
        safe_answer(call.id)
        _track_view(user_id, call.message.chat.id, call.message.message_id, "ann_detail")
        with _active_views_lock:
            if user_id in _active_views:
                _active_views[user_id]["ann_id"] = ann_id
        txt, mk = _render_announcement_detail_view(ann_id)
        safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=mk)
        return

    elif data.startswith("ann_tog_"):
        if not has_admin_capability(user_id, "announcements"):
            safe_answer(call.id, "⛔ غير مصرح لك.", show_alert=True)
            return
        ann_id = data[len("ann_tog_"):]
        upd = toggle_announcement_active(ann_id)
        if not upd:
            safe_answer(call.id, "⚠️ الإعلان غير موجود.", show_alert=True)
            return
        if not upd.get("active"):
            _unpin_announcement_chats(upd)
            safe_answer(call.id, "⏸️ تم إيقاف الإعلان وفك تثبيته من الدردشات.", show_alert=True)
        else:
            safe_answer(call.id, "▶️ تم إعادة تفعيل الإعلان!", show_alert=True)
        txt, mk = _render_announcement_detail_view(ann_id)
        safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=mk)
        return

    elif data.startswith("ann_push_"):
        if not has_admin_capability(user_id, "announcements"):
            safe_answer(call.id, "⛔ غير مصرح لك.", show_alert=True)
            return
        ann_id = data[len("ann_push_"):]
        ann = get_announcement_by_id(ann_id)
        if not ann:
            safe_answer(call.id, "⚠️ الإعلان غير موجود.", show_alert=True)
            return
        b_res = _broadcast_announcement_to_users(ann, is_repeat=True)
        mark_announcement_repushed(ann_id)
        safe_answer(call.id, f"🚀 تم البث والتثبيت لـ {b_res['sent']} مستخدم!", show_alert=True)
        txt, mk = _render_announcement_detail_view(ann_id)
        safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=mk)
        return

    elif data.startswith("ann_rop_"):
        safe_answer(call.id)
        if not has_admin_capability(user_id, "announcements"):
            return
        ann_id = data[len("ann_rop_"):]
        ann = get_announcement_by_id(ann_id)
        if not ann:
            return
        update_announcement_timing(ann_id, repeat_on_open=not bool(ann.get("repeat_on_open")))
        safe_answer(call.id, "🔄 تم تحديث خيار الظهور عند كل فتح!")
        txt, mk = _render_announcement_detail_view(ann_id)
        safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=mk)
        return

    elif data.startswith("ann_dur_"):
        safe_answer(call.id)
        if not has_admin_capability(user_id, "announcements"):
            return
        rest = data[len("ann_dur_"):]
        ann_id, _, sec_s = rest.rpartition("_")
        try:
            sec_v = int(sec_s)
        except ValueError:
            return
        update_announcement_timing(ann_id, duration_sec=sec_v)
        safe_answer(call.id, f"⏱️ تم ضبط المدة: {format_duration_ar(sec_v)}")
        txt, mk = _render_announcement_detail_view(ann_id)
        safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=mk)
        return

    elif data.startswith("ann_rep_"):
        safe_answer(call.id)
        if not has_admin_capability(user_id, "announcements"):
            return
        rest = data[len("ann_rep_"):]
        ann_id, _, sec_s = rest.rpartition("_")
        try:
            sec_v = int(sec_s)
        except ValueError:
            return
        update_announcement_timing(ann_id, repeat_interval_sec=sec_v)
        safe_answer(call.id, f"🔁 التكرار: {format_duration_ar(sec_v) if sec_v else 'مرة واحدة'}")
        txt, mk = _render_announcement_detail_view(ann_id)
        safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=mk)
        return

    elif data.startswith("ann_del_"):
        if not has_admin_capability(user_id, "announcements"):
            safe_answer(call.id, "⛔ غير مصرح لك.", show_alert=True)
            return
        ann_id = data[len("ann_del_"):]
        removed = delete_announcement(ann_id)
        unpinned = _unpin_announcement_chats(removed) if removed else 0
        record_audit_log(user_id, call.from_user.first_name or "", "ANNOUNCEMENT_DELETED", f"حذف إعلان {ann_id} وفك التثبيت من {unpinned} محادثة")
        safe_answer(call.id, f"🗑️ تم حذف الإعلان وفك تثبيته من {unpinned} محادثة!", show_alert=True)
        txt, mk = _render_announcements_view()
        safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=mk)
        return

    # ----------------- رادار المراقبة الشامل وسجل الرقابة للمطور والأدمن المخوّل -----------------
    elif data == "menu_surveillance_radar":
        if not has_admin_capability(user_id, "radar_users"):
            record_audit_log(user_id, call.from_user.first_name or "", "SECURITY_BLOCK", "محاولة فتح رادار المطور")
            safe_answer(call.id, "⛔ خاص بالمطور والأدمن المخوّل فقط.", show_alert=True)
            return
        txt, markup = render_surveillance_radar_text_and_markup(viewer_id=user_id)
        _track_view(user_id, call.message.chat.id, call.message.message_id, "radar")
        safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=markup)
        return

    elif data == "menu_audit_logs":
        if not has_admin_capability(user_id, "audit_logs"):
            record_audit_log(user_id, call.from_user.first_name or "", "SECURITY_BLOCK", "محاولة فتح سجل الرقابة")
            safe_answer(call.id, "⛔ خاص بالمطور والأدمن غير المقيد فقط.", show_alert=True)
            return
        txt, markup = _render_audit_logs_view()
        _track_view(user_id, call.message.chat.id, call.message.message_id, "audit")
        safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=markup)
        return

    elif data.startswith("surv_user_"):
        if not has_admin_capability(user_id, "radar_users"):
            record_audit_log(user_id, call.from_user.first_name or "", "SECURITY_BLOCK", f"محاولة وصول {data}")
            safe_answer(call.id, "⛔ خاص بالمطور والأدمن المخوّل فقط.", show_alert=True)
            return
        try:
            t_id = int(data.replace("surv_user_", ""))
        except ValueError:
            return
        txt, markup = render_user_dossier(t_id, viewer_id=user_id)
        if not txt:
            safe_answer(call.id, "⛔ المستخدم غير موجود أو خارج نطاق رتبتك.", show_alert=True)
            return
        _track_view(user_id, call.message.chat.id, call.message.message_id, "dossier", target_id=t_id)
        safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=markup)
        return

    elif data.startswith("surv_grant_all_"):
        if not has_admin_capability(user_id, "radar_users"):
            record_audit_log(user_id, call.from_user.first_name or "", "SECURITY_BLOCK", f"محاولة منح كل المميزات {data}")
            safe_answer(call.id, "⛔ غير مصرح لك.", show_alert=True)
            return
        try:
            t_id = int(data.replace("surv_grant_all_", ""))
        except ValueError:
            return
        if not grant_all_user_permissions(t_id, user_id):
            safe_answer(call.id, "⛔ لا يمكنك تعديل هذا المستخدم أو رتبته.", show_alert=True)
            return
        update_menu_button_for_user(bot, t_id, is_allowed=True)
        safe_answer(call.id, "🌟 تم فتح كافة المميزات الـ 11 لهذا المستخدم بضغطة واحدة!", show_alert=True)
        safe_send(t_id, "🌟 <b>تهانينا! تم تفعيل كافة أدوات ومميزات النظام لحسابك بالكامل.</b>\nأرسل /start لعرض لوحتك الجديدة.")
        txt, markup = render_user_dossier(t_id, viewer_id=user_id)
        if txt:
            safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=markup)
        return

    elif data.startswith("surv_tier_"):
        if not is_super_admin(user_id):
            record_audit_log(user_id, call.from_user.first_name or "", "SECURITY_BLOCK", f"محاولة تغيير رتبة إدارية: {data}")
            safe_answer(call.id, "⛔ تعيين الرتب والمدراء حصري للمطور الرئيسي فقط!", show_alert=True)
            return
        rest = data[len("surv_tier_"):]
        uid_s, _, tier_val = rest.partition("_")
        try:
            t_id = int(uid_s)
        except ValueError:
            return
        if not set_admin_tier(t_id, tier_val, user_id):
            safe_answer(call.id, "⚠️ تعذر تغيير الرتبة.", show_alert=True)
            return
        update_menu_button_for_user(bot, t_id, is_allowed=True)
        t_lbl = ADMIN_TIER_LABELS.get(tier_val, tier_val)
        safe_answer(call.id, f"✅ تم تعيين الرتبة: {t_lbl}", show_alert=True)
        safe_send(t_id, f"🎖️ <b>تحديث من المطور الرئيسي:</b> تم تعيين رتبتك في النظام إلى <b>{esc(t_lbl)}</b>!\nأرسل /start لاستعراض صلاحياتك الجديدة.")
        txt, markup = render_user_dossier(t_id, viewer_id=user_id)
        if txt:
            safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=markup)
        return

    elif data.startswith("surv_restr_menu_"):
        if not is_super_admin(user_id):
            record_audit_log(user_id, call.from_user.first_name or "", "SECURITY_BLOCK", f"محاولة فتح قيود الأدمن: {data}")
            safe_answer(call.id, "⛔ حصري للمطور الرئيسي فقط!", show_alert=True)
            return
        try:
            t_id = int(data.replace("surv_restr_menu_", ""))
        except ValueError:
            return
        txt, markup = _render_user_restrictions_view(t_id)
        if not txt:
            safe_answer(call.id, "المستخدم غير موجود.", show_alert=True)
            return
        safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=markup)
        return

    elif data.startswith("surv_restr_"):
        if not is_super_admin(user_id):
            record_audit_log(user_id, call.from_user.first_name or "", "SECURITY_BLOCK", f"محاولة تعديل قيد أدمن: {data}")
            safe_answer(call.id, "⛔ حصري للمطور الرئيسي فقط!", show_alert=True)
            return
        rest = data[len("surv_restr_"):]
        uid_s, _, rkey = rest.partition("_")
        try:
            t_id = int(uid_s)
        except ValueError:
            return
        res_b = toggle_admin_restriction(t_id, rkey, user_id)
        if res_b is None:
            safe_answer(call.id, "⚠️ تعذر تعديل هذا القيد.", show_alert=True)
            return
        safe_answer(call.id, f"{'🔒 تم الحجب' if res_b else '✅ تم الإتاحة'}: {ADMIN_RESTRICTION_LABELS.get(rkey, rkey)}")
        txt, markup = _render_user_restrictions_view(t_id)
        if txt:
            safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=markup)
        return

    elif data.startswith("surv_rst_warn_"):
        if not has_admin_capability(user_id, "radar_users"):
            record_audit_log(user_id, call.from_user.first_name or "", "SECURITY_BLOCK", f"محاولة تصفير إنذارات {data}")
            safe_answer(call.id, "⛔ خاص بالمطور والأدمن المخوّل فقط.", show_alert=True)
            return
        try:
            t_id = int(data.replace("surv_rst_warn_", ""))
        except ValueError:
            return
        if not can_manage_target_user(user_id, t_id):
            safe_answer(call.id, "⛔ خارج نطاق رتبتك.", show_alert=True)
            return
        if reset_user_profile_warnings(t_id):
            safe_answer(call.id, "✅ تم تصفير إنذارات البروفايل (0/5) للمستخدم.", show_alert=True)
            txt, markup = render_user_dossier(t_id, viewer_id=user_id)
            if txt:
                safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=markup)
        else:
            safe_answer(call.id, "المستخدم غير موجود.", show_alert=True)
        return

    elif data.startswith("surv_perm_"):
        if not has_admin_capability(user_id, "radar_users"):
            record_audit_log(user_id, call.from_user.first_name or "", "SECURITY_BLOCK", f"محاولة تعديل صلاحية {data}")
            safe_answer(call.id, "⛔ خاص بالمطور والأدمن المخوّل فقط.", show_alert=True)
            return
        parts = data.split("_")
        try:
            t_id = int(parts[2])
        except (IndexError, ValueError):
            return
        if not can_manage_target_user(user_id, t_id):
            record_audit_log(user_id, call.from_user.first_name or "", "SECURITY_BLOCK", f"محاولة تعديل صلاحية خارج النطاق {data}")
            safe_answer(call.id, "⛔ لا يمكنك تعديل صلاحيات هذه الرتبة.", show_alert=True)
            return
        perm_key = "_".join(parts[3:])
        new_val = toggle_user_permission(t_id, perm_key)
        perm_ar = PERMISSION_LABELS.get(perm_key, perm_key)
        safe_answer(call.id, f"{'✅ تم تفعيل' if new_val else '❌ تم إغلاق'}: {perm_ar}")
        txt, markup = render_user_dossier(t_id, viewer_id=user_id)
        if txt:
            safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=markup)
        return

    elif data.startswith("surv_revoke_all_"):
        safe_answer(call.id)
        if not has_admin_capability(user_id, "radar_users"):
            return
        try:
            t_id = int(data.replace("surv_revoke_all_", ""))
        except ValueError:
            return
        if not can_manage_target_user(user_id, t_id):
            safe_answer(call.id, "⛔ لا يمكنك تعديل هذه الرتبة.", show_alert=True)
            return
        revoke_all_permissions(t_id)
        safe_answer(call.id, "🔒 تم سحب وإغلاق كافة الصلاحيات عن هذا المستخدم!", show_alert=True)
        txt, markup = render_user_dossier(t_id, viewer_id=user_id)
        if txt:
            safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=markup)
        return

    elif data.startswith("surv_ban_"):
        safe_answer(call.id)
        if not has_admin_capability(user_id, "radar_users"):
            return
        try:
            t_id = int(data.replace("surv_ban_", ""))
        except ValueError:
            return
        if not can_manage_target_user(user_id, t_id):
            safe_answer(call.id, "🛡️ محظور: لا يمكنك حظر المطور أو هذه الرتبة!", show_alert=True)
            return
        ban_user(t_id)
        update_menu_button_for_user(bot, t_id, is_allowed=False)
        safe_answer(call.id, "🚫 تم حظر المستخدم وتصفير صلاحياته!", show_alert=True)
        txt, markup = render_user_dossier(t_id, viewer_id=user_id)
        if txt:
            safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=markup)
        return

    elif data.startswith("surv_unban_"):
        safe_answer(call.id)
        if not has_admin_capability(user_id, "radar_users"):
            return
        try:
            t_id = int(data.replace("surv_unban_", ""))
        except ValueError:
            return
        if not can_manage_target_user(user_id, t_id):
            return
        unban_user(t_id)
        update_menu_button_for_user(bot, t_id, is_allowed=True)
        safe_answer(call.id, "✅ تم فك الحظر (كافة الصلاحيات مغلقة للأمان)!", show_alert=True)
        txt, markup = render_user_dossier(t_id, viewer_id=user_id)
        if txt:
            safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=markup)
        return

    elif data.startswith("surv_del_"):
        safe_answer(call.id)
        if not has_admin_capability(user_id, "radar_users"):
            return
        try:
            t_id = int(data.replace("surv_del_", ""))
        except ValueError:
            return
        if not can_manage_target_user(user_id, t_id):
            safe_answer(call.id, "🛡️ محظور: لا يمكنك حذف المطور أو هذه الرتبة!", show_alert=True)
            return
        acc_deleted = delete_accounts_by_owner(t_id)
        delete_user_and_data(t_id)
        update_menu_button_for_user(bot, t_id, is_allowed=False)
        safe_answer(call.id, f"🗑️ تم حذف المستخدم ومسح {acc_deleted} حساب تابعة له!", show_alert=True)
        txt, markup = render_surveillance_radar_text_and_markup(viewer_id=user_id)
        safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=markup)
        return

    elif data.startswith("surv_pts_"):
        if not (has_admin_capability(user_id, "radar_users") and has_admin_capability(user_id, "points_economy")):
            record_audit_log(user_id, call.from_user.first_name or "", "SECURITY_BLOCK", f"محاولة تعديل نقاط {data}")
            safe_answer(call.id, "⛔ خاص بالمطور والأدمن غير المقيد فقط.", show_alert=True)
            return
        rest = data[len("surv_pts_"):]
        action_k, _, uid_s = rest.partition("_")
        try:
            t_id = int(uid_s)
        except ValueError:
            return
        if not can_manage_target_user(user_id, t_id):
            safe_answer(call.id, "⛔ خارج نطاق رتبتك.", show_alert=True)
            return
        if action_k == "settle" and not has_admin_capability(user_id, "payment_notices"):
            safe_answer(call.id, "⛔ التسويات المالية محجوبة عن رتبتك حالياً.", show_alert=True)
            return
        if action_k == "add5":
            res = adjust_user_points(t_id, 5, "ADMIN_GRANT", "إضافة +5 نقاط من لوحة الإدارة", actor_uid=user_id)
            safe_answer(call.id, f"✅ تم إضافة +5 نقاط! الرصيد: {res.get('balance', 0)}")
            safe_send(t_id, f"🎁 <b>منحة نقاط من الإدارة:</b> +5 نقاط!\n💰 رصيدك الآن: <b>{res.get('balance', 0)}</b> نقطة ({res.get('yer_value', 0):,} ر.ي)")
        elif action_k == "sub5":
            res = adjust_user_points(t_id, -5, "ADMIN_DEDUCT", "سحب/خصم 5 نقاط من الإدارة", actor_uid=user_id, allow_partial_zero=True)
            safe_answer(call.id, f"✅ تم خصم النقاط! الرصيد: {res.get('balance', 0)}")
            safe_send(t_id, f"➖ <b>تحديث الرصيد من الإدارة:</b> تم خصم/سحب {abs(res.get('delta', 0))} نقطة.\n💰 رصيدك الآن: <b>{res.get('balance', 0)}</b> نقطة")
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
        txt, markup = render_user_dossier(t_id, viewer_id=user_id)
        if txt:
            safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=markup)
        return

    elif data == "menu_admin_economy":
        if not has_admin_capability(user_id, "points_economy"):
            record_audit_log(user_id, call.from_user.first_name or "", "SECURITY_BLOCK", "محاولة فتح إعدادات الاقتصاد بدون صلاحية")
            safe_answer(call.id, "⛔ خاص بالمطور والأدمن غير المقيد فقط.", show_alert=True)
            return
        txt, markup = _render_admin_economy_view()
        _track_view(user_id, call.message.chat.id, call.message.message_id, "economy")
        safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=markup)
        return

    elif data == "menu_cloud_db":
        if not is_super_admin(user_id):
            record_audit_log(user_id, call.from_user.first_name or "", "SECURITY_BLOCK", "محاولة فتح إعدادات القاعدة السحابية بدون صلاحية")
            safe_answer(call.id, "⛔ خاص بالمطور الأكبر فقط.", show_alert=True)
            return
        txt, markup = _render_cloud_db_view()
        _track_view(user_id, call.message.chat.id, call.message.message_id, "cloud_db")
        safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=markup)
        return

    elif data.startswith("cdb_pick_"):
        if not is_super_admin(user_id):
            record_audit_log(user_id, call.from_user.first_name or "", "SECURITY_BLOCK", f"محاولة ضبط مزود القاعدة {data}")
            safe_answer(call.id, "⛔ خاص بالمطور الأكبر فقط.", show_alert=True)
            return
        prov = data.replace("cdb_pick_", "", 1)
        if prov not in ("turso", "supabase", "firebase"):
            safe_answer(call.id, "⚠️ مزود غير معروف.", show_alert=True)
            return
        st["input_mode"] = f"waiting_cdb_{prov}"
        safe_answer(call.id)
        safe_send(
            call.message.chat.id,
            get_provider_setup_guide(prov),
            reply_markup=_prompt_back_markup("menu_cloud_db"),
        )
        return

    elif data == "cdb_sync_push":
        if not is_super_admin(user_id):
            record_audit_log(user_id, call.from_user.first_name or "", "SECURITY_BLOCK", "محاولة دفع القاعدة السحابية بدون صلاحية")
            safe_answer(call.id, "⛔ خاص بالمطور الأكبر فقط.", show_alert=True)
            return
        res_p = cloud_db_sync_upload(force=True)
        ok_p = bool(res_p.get("ok") and not res_p.get("cloud_skipped"))
        msg_p = (
            f"✅ تمت مزامنة {res_p.get('keys', 0)} سجل/ملف إلى القاعدة السحابية بنجاح!"
            if ok_p
            else str(res_p.get("error") or "تأكد من ضبط بيانات القاعدة أولاً")
        )
        safe_answer(call.id, msg_p[:180], show_alert=True)
        txt, markup = _render_cloud_db_view()
        safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=markup)
        return

    elif data == "cdb_sync_pull_merge":
        if not is_super_admin(user_id):
            record_audit_log(user_id, call.from_user.first_name or "", "SECURITY_BLOCK", "محاولة سحب ودمج من القاعدة السحابية بدون صلاحية")
            safe_answer(call.id, "⛔ خاص بالمطور الأكبر فقط.", show_alert=True)
            return
        res_pm = cloud_db_sync_download(mode="merge")
        if res_pm.get("ok") and res_pm.get("mode") == "merge":
            s_m = res_pm.get("stats", {})
            safe_answer(
                call.id,
                f"✅ تم الدمج من السحابة! حسابات مضافة: {s_m.get('accounts_added', 0)} | مكررة محفوظة: {s_m.get('accounts_deduped', 0)}",
                show_alert=True,
            )
            record_audit_log(user_id, call.from_user.first_name or "", "CLOUD_DB_MERGED", f"دمج من السحابة: +{s_m.get('accounts_added', 0)} حساب")
        else:
            safe_answer(call.id, f"⚠️ {res_pm.get('error') or res_pm.get('reason') or 'السحابة فارغة'}", show_alert=True)
        txt, markup = _render_cloud_db_view()
        safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=markup)
        return

    elif data == "cdb_test":
        if not is_super_admin(user_id):
            record_audit_log(user_id, call.from_user.first_name or "", "SECURITY_BLOCK", "محاولة فحص القاعدة السحابية بدون صلاحية")
            safe_answer(call.id, "⛔ خاص بالمطور الأكبر فقط.", show_alert=True)
            return
        res_t = test_cloud_db_connection()
        if res_t.get("ok"):
            safe_answer(call.id, f"✅ متصل بنجاح ({res_t.get('provider')}) | ملفات: {res_t.get('docs_count')} | جلسات: {res_t.get('sessions_count')}", show_alert=True)
        else:
            safe_answer(call.id, f"❌ {str(res_t.get('error') or 'فشل الاتصال')[:180]}", show_alert=True)
        return

    elif data == "cdb_clear":
        if not is_super_admin(user_id):
            record_audit_log(user_id, call.from_user.first_name or "", "SECURITY_BLOCK", "محاولة فصل القاعدة السحابية بدون صلاحية")
            safe_answer(call.id, "⛔ خاص بالمطور الأكبر فقط.", show_alert=True)
            return
        clear_cloud_db_config()
        safe_answer(call.id, "🗑️ تم فصل القاعدة السحابية الخارجية (بقي SQLite المحلي نشطاً).", show_alert=True)
        txt, markup = _render_cloud_db_view()
        safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=markup)
        return

    elif data.startswith("bkp_upload_merge:") or data.startswith("bkp_upload_replace:") or data.startswith("bkp_upload_cancel:"):
        if not has_admin_capability(user_id, "backups"):
            record_audit_log(user_id, call.from_user.first_name or "", "SECURITY_BLOCK", f"محاولة التحكم بملف نسخ احتياطي مرفوع {data}")
            safe_answer(call.id, "⛔ خاص بالمطور والأدمن غير المقيد فقط.", show_alert=True)
            return
        action_bkp, tok = data.split(":", 1)
        staged = _pop_pending_backup(tok, user_id)
        if not staged:
            safe_answer(call.id, "⌛ انتهت صلاحية هذا الملف المعلق أو تم تنفيذه مسبقاً. أعد إرسال الملف.", show_alert=True)
            return
        if action_bkp == "bkp_upload_cancel":
            safe_answer(call.id, "❌ تم إلغاء العملية دون تعديل البيانات.")
            safe_edit_message("❌ <b>تم إلغاء معالجة الملف المرفوع مع الإبقاء على بياناتك الحالية كما هي.</b>", call.message.chat.id, call.message.message_id, reply_markup=_back_home_markup("menu_backup_vault"))
            return
        if action_bkp == "bkp_upload_merge":
            res_m = merge_backup_zip_bytes(staged["raw"])
            if res_m.get("ok"):
                sm = res_m["stats"]
                reload_user_states_from_disk()
                try:
                    update_menu_button_for_user(bot, user_id, is_allowed=True)
                except Exception:
                    pass
                record_audit_log(
                    user_id, call.from_user.first_name or "", "BACKUP_MERGED",
                    f"دمج ذكي لنسخة {staged['fname']}: +{sm['accounts_added']} حساب، مكرر محمي {sm['accounts_deduped']}، +{sm['sessions_merged']} جلسة"
                )
                safe_answer(call.id, "✅ تم الدمج الذكي للنسخة بنجاح!")
                safe_edit_message(
                    "🔀 <b>تم الدمج الذكي للنسخة بنجاح دون حذف الجديد أو تكرار القديم!</b>\n"
                    "━━━━━━━━━━━━━━━━━━━━\n"
                    f"📱 <b>حسابات جديدة مضافة:</b> +{sm['accounts_added']}\n"
                    f"🛡️ <b>حسابات متطابقة (مُفلترة بلا تكرار):</b> {sm['accounts_deduped']} (تحديث/ترقية {sm['accounts_upgraded']})\n"
                    f"🍪 <b>جلسات مدموجة/مستعادة:</b> {sm['sessions_merged']}\n"
                    f"👥 <b>مستخدمون جدد:</b> +{sm['users_added']} | مدموجون: {sm['users_merged']}\n"
                    f"💰 <b>قيود مالية جديدة:</b> +{sm['ledger_added']} (مكرر محجوب: {sm['ledger_deduped']})\n"
                    f"📊 <b>الإجمالي بعد الدمج:</b> {res_m['users_count']} مستخدم | {res_m['accounts_count']} حساب | {res_m['sessions_count']} جلسة\n"
                    "💡 <i>يمكنك الآن إرسال أي نسخة أقدم أو ملف JSON آخر وسيستمر الدمج الذكي بنفس الدقة!</i>",
                    call.message.chat.id,
                    call.message.message_id,
                    reply_markup=_back_home_markup("menu_backup_vault"),
                )
            else:
                safe_answer(call.id, "⚠️ تعذر الدمج")
                safe_edit_message(f"⚠️ <b>تعذر دمج النسخة:</b> {esc(res_m.get('error', 'خطأ'))}", call.message.chat.id, call.message.message_id)
            return
        # bkp_upload_replace
        res_r = restore_backup_zip_bytes(staged["raw"])
        if res_r.get("ok"):
            reload_user_states_from_disk()
            record_audit_log(user_id, call.from_user.first_name or "", "BACKUP_RESTORED", f"استبدال كامل من {staged['fname']}: users={res_r.get('users_count', 0)}, accs={res_r.get('accounts_count', 0)}")
            safe_answer(call.id, "✅ تم الاستبدال الكامل بالنسخة!")
            safe_edit_message(
                "✅ <b>تم استبدال القاعدة بهذه النسخة كاملةً!</b>\n"
                f"👥 المستخدمون: <b>{res_r.get('users_count', 0)}</b> | 📱 الحسابات: <b>{res_r.get('accounts_count', 0)}</b> | 🔑 الجلسات: <b>{res_r.get('sessions_restored', 0)}</b>",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=_back_home_markup("menu_backup_vault"),
            )
        else:
            safe_answer(call.id, "⚠️ فشلت الاستعادة")
            safe_edit_message(f"⚠️ {esc(res_r.get('error', 'خطأ'))}", call.message.chat.id, call.message.message_id)
        return

    elif data.startswith("hitl_otp_"):
        acc_id = data[len("hitl_otp_"):]
        acc = get_account_by_id(acc_id)
        if not acc:
            safe_answer(call.id, "الحساب غير موجود.", show_alert=True)
            return
        can_access = has_admin_capability(user_id, "accounts_pool") or (
            int(acc.get("owner_id") or 0) == int(user_id)
            and (has_permission(user_id, "can_add_accounts") or has_permission(user_id, "can_use_accounts"))
        )
        if not can_access:
            record_audit_log(user_id, call.from_user.first_name or "", "SECURITY_BLOCK", f"محاولة إرسال 2FA لحساب لا يملكه: {acc_id}")
            safe_answer(call.id, "⛔ لا تملك صلاحية التحقق لهذا الحساب.", show_alert=True)
            return
        st["input_mode"] = f"waiting_hitl_otp_{acc_id}"
        safe_answer(call.id)
        safe_send(
            call.message.chat.id,
            f"🔐 <b>إرسال رمز الأمان (2FA / OTP) للحساب '{esc(acc.get('name', acc_id))}'</b>\n"
            "أرسل الرمز الرقمي (مثال: <code>123456</code>) الآن وسيدخله البوت مباشرة في صفحة فيسبوك ويثبّت الجلسة.",
            reply_markup=_prompt_back_markup("menu_manage_accs"),
        )
        return

    elif data.startswith("hitl_help_"):
        acc_id = data[len("hitl_help_"):]
        acc = get_account_by_id(acc_id)
        if not acc:
            safe_answer(call.id, "الحساب غير موجود.", show_alert=True)
            return
        can_access = has_admin_capability(user_id, "accounts_pool") or (
            int(acc.get("owner_id") or 0) == int(user_id)
            and (has_permission(user_id, "can_add_accounts") or has_permission(user_id, "can_use_accounts"))
        )
        if not can_access:
            record_audit_log(user_id, call.from_user.first_name or "", "SECURITY_BLOCK", f"محاولة وصول لمساعدة الشاشة الحية لحساب لا يملكه: {acc_id}")
            safe_answer(call.id, "⛔ غير مصرح لك.", show_alert=True)
            return
        w_url = get_public_webapp_url()
        safe_answer(call.id)
        if w_url:
            sep = "&" if "?" in w_url else "?"
            mk = types.InlineKeyboardMarkup()
            mk.row(types.InlineKeyboardButton("🖥️ فتح الشاشة الحية الآن", web_app=types.WebAppInfo(url=f"{w_url}{sep}hitl={acc_id}")))
            safe_send(call.message.chat.id, "🖥️ اضغط الزر أدناه لفتح متصفح الحساب الحقيقي وحل التحقق بنفسك:", reply_markup=mk)
        else:
            safe_send(
                call.message.chat.id,
                "💡 نفق HTTPS للوحة المصغرة غير متاح حالياً، أو اضغط زر <b>📱 لوحة التحكم</b> ثم تبويب <b>الحسابات → الشاشة الحية لحل التحقق</b> بمجرد توفر رابط الويب.",
                reply_markup=_back_home_markup("menu_manage_accs"),
            )
        return

    elif data.startswith("mission_hitl_"):
        safe_answer(call.id)
        if data.startswith("mission_hitl_resume_"):
            safe_answer(call.id)
            acc_id = data[len("mission_hitl_resume_"):]
            dec = "verified"
            ack = "✅ تم تأكيد إكمال التحقق — سيُستكمل تنفيذ المهمة على هذا الحساب فوراً!"
        elif data.startswith("mission_hitl_skip_"):
            safe_answer(call.id)
            acc_id = data[len("mission_hitl_skip_"):]
            dec = "skip"
            ack = "⏭️ تم تخطي هذا الحساب ومتابعة بقية الموجة."
        elif data.startswith("mission_hitl_abort_"):
            acc_id = data[len("mission_hitl_abort_"):]
            dec = "abort"
            ack = "🛑 تم إرسال أمر إيقاف المهمة فوراً."
        else:
            safe_answer(call.id, "أمر غير معروف.")
            return
        w_info = get_mission_hitl_waiter(acc_id=acc_id)
        acc = get_account_by_id(acc_id)
        can_access = (
            has_admin_capability(user_id, "accounts_pool")
            or (w_info and int(w_info.get("owner_uid") or 0) == int(user_id))
            or (acc and int(acc.get("owner_id") or 0) == int(user_id))
        )
        if not can_access:
            record_audit_log(user_id, call.from_user.first_name or "", "SECURITY_BLOCK", f"محاولة التحكم بانتظار HITL لحساب خارج النطاق: {acc_id}")
            safe_answer(call.id, "⛔ غير مصرح لك.", show_alert=True)
            return
        ok_sig = signal_mission_hitl_decision(acc_id, dec)
        safe_answer(call.id, ack if ok_sig else "انتهى وقت الانتظار أو استؤنف الحساب مسبقاً.", show_alert=not ok_sig)
        return

    elif data == "toggle_wait_hitl":
        st["wait_for_hitl"] = not bool(st.get("wait_for_hitl", True))
        persist_user_states()
        safe_answer(call.id, "⏳ انتظار التحقق البشري: مفعّل" if st["wait_for_hitl"] else "⏭️ انتظار التحقق: معطل (تخطي تلقائي)")
        safe_edit_message(get_dashboard_text(user_id), call.message.chat.id, call.message.message_id, reply_markup=get_main_dashboard_markup(user_id))
        return

    elif data == "menu_proxies" or data.startswith("prx_"):
        if not has_admin_capability(user_id, "proxies"):
            record_audit_log(user_id, call.from_user.first_name or "", "SECURITY_BLOCK", f"محاولة الوصول لإدارة البروكسيات بدون صلاحية: {data}")
            safe_answer(call.id, "⛔ هذه الصلاحية محصورة بالمطور والأدمن غير المقيد فقط.", show_alert=True)
            return
        if data == "menu_proxies":
            safe_answer(call.id)
            txt, markup = _render_proxies_view()
            _track_view(user_id, call.message.chat.id, call.message.message_id, "proxies")
            safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=markup)
            return
        elif data == "prx_add_prompt":
            st["input_mode"] = "waiting_proxies_bulk"
            safe_answer(call.id)
            safe_send(
                call.message.chat.id,
                "➕ <b>إضافة قائمة بروكسيات جديدة</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "أرسل بروكسي واحد أو مئات البروكسيات (كل بروكسي في سطر) بالصيغ التالية:\n"
                "• <code>socks5://user:pass@ip:port</code>\n"
                "• <code>http://user:pass@ip:port</code>\n"
                "• <code>ip:port:user:pass</code>\n"
                "• <code>ip:port</code>\n\n"
                "💡 <i>سيتم توزيع الحسابات تلقائياً وبثبات (Sticky) عبر جميع البروكسيات السليمة.</i>",
                reply_markup=_prompt_back_markup("menu_proxies"),
            )
            return
        elif data == "prx_check_all":
            safe_answer(call.id, "🩺 جاري فحص البروكسيات وكشف الدول...")
            def _bg_check_proxies():
                res = check_all_proxies(max_workers=12, timeout=8.0)
                record_audit_log(user_id, call.from_user.first_name or "", "PROXIES_CHECKED", f"فحص {res['checked']} | حي {res['alive']} | ميت {res['dead']}")
                txt, markup = _render_proxies_view()
                safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=markup)
            threading.Thread(target=_bg_check_proxies, daemon=True).start()
            return
        elif data == "prx_bind_existing":
            b_res = bind_existing_accounts(rebalance_all=False)
            record_audit_log(
                user_id,
                call.from_user.first_name or "",
                "PROXIES_BIND_EXISTING",
                f"ربط {b_res['newly_bound']} حساب جديد | مربوط مسبقاً {b_res['already_bound']}",
            )
            safe_answer(
                call.id,
                f"🔗 تم ربط {b_res['newly_bound']} حساباً (إجمالي المربوط: {b_res['newly_bound'] + b_res['already_bound']}/{b_res['total_accounts']}).",
                show_alert=True,
            )
            txt, markup = _render_proxies_view()
            safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=markup)
            return
        elif data == "prx_fetch_github":
            safe_answer(call.id, "📥 جاري سحب وفحص بروكسيات GitHub الحية...")
            def _bg_fetch_github():
                res = fetch_and_check_github_free_proxies()
                record_audit_log(
                    user_id,
                    call.from_user.first_name or "",
                    "PROXIES_GITHUB_FETCH",
                    f"فحص {res.get('tested', 0)} | حي {res.get('alive', 0)} | مضاف {res.get('added', 0)}",
                )
                txt, markup = _render_proxies_view()
                banner = (
                    f"📥 <b>نتيجة سحب وفحص GitHub:</b> فُحص <b>{res.get('tested', 0)}</b> بروكسي -> "
                    f"شغال: <b>{res.get('alive', 0)}</b> | أُضيف فعلياً: <b>{res.get('added', 0)}</b>.\n"
                    "⚠️ <i>تذكير: البروكسيات المجانية العامة مشتركة بين الناس وتصلح للتجربة؛ "
                    "للحسابات الثمينة استخدم نفق 4G أو Webshare المجاني (10 ثابتة) أو بروكسي خاص.</i>\n\n"
                )
                safe_edit_message(banner + txt, call.message.chat.id, call.message.message_id, reply_markup=markup)
            threading.Thread(target=_bg_fetch_github, daemon=True).start()
            return
        elif data == "prx_cycle_mode":
            cur_m = load_proxy_state().get("mode", "sticky")
            order = ("sticky", "4g_bridge", "direct")
            nxt = order[(order.index(cur_m) + 1) % len(order)] if cur_m in order else "sticky"
            set_proxy_mode(nxt)
            safe_answer(call.id, f"✅ تم التبديل إلى وضع: {nxt}")
            txt, markup = _render_proxies_view()
            safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=markup)
            return
        elif data == "prx_cycle_cap":
            cur_cap = int(load_proxy_state().get("max_per_proxy", 3) or 0)
            cap_order = (3, 5, 0)
            nxt_cap = cap_order[(cap_order.index(cur_cap) + 1) % len(cap_order)] if cur_cap in cap_order else 3
            set_max_per_proxy(nxt_cap)
            record_audit_log(user_id, call.from_user.first_name or "", "PROXY_CAP_UPDATED", f"تغيير حد الحسابات لكل بروكسي إلى {nxt_cap}")
            cap_msg = f"{nxt_cap} حسابات/بروكسي" if nxt_cap > 0 else "توزيع مرن غير محدود"
            safe_answer(call.id, f"✅ تم ضبط الحد الآمن على: {cap_msg}")
            txt, markup = _render_proxies_view()
            safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=markup)
            return
        elif data == "prx_toggle_watch":
            enabled = toggle_auto_check()
            record_audit_log(user_id, call.from_user.first_name or "", "PROXY_WATCH_TOGGLE", f"الفحص التلقائي: {enabled}")
            safe_answer(call.id, "✅ تم تفعيل الفحص التلقائي للبروكسيات" if enabled else "⏸️ تم إيقاف الفحص التلقائي مؤقتاً")
            txt, markup = _render_proxies_view()
            safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=markup)
            return
        elif data.startswith("prx_page_"):
            try:
                pg = int(data[len("prx_page_"):])
            except Exception:
                pg = 0
            safe_answer(call.id)
            txt, markup = _render_proxies_view(page=pg)
            safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=markup)
            return
        elif data.startswith("prx_item_"):
            try:
                idx = int(data[len("prx_item_"):])
            except Exception:
                idx = -1
            safe_answer(call.id)
            txt, markup = _render_proxy_detail_view(idx)
            safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=markup)
            return
        elif data.startswith("prx_chk_"):
            try:
                idx = int(data[len("prx_chk_"):])
            except Exception:
                idx = -1
            safe_answer(call.id, "🩺 جاري فحص هذا البروكسي...")
            def _bg_chk_one():
                res = check_single_proxy(idx, timeout=8.0)
                if res.get("ok"):
                    txt, markup = _render_proxy_detail_view(int(res.get("idx", idx)))
                else:
                    txt, markup = _render_proxies_view()
                safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=markup)
            threading.Thread(target=_bg_chk_one, daemon=True).start()
            return
        elif data.startswith("prx_rebind_"):
            try:
                idx = int(data[len("prx_rebind_"):])
            except Exception:
                idx = -1
            rb = rebind_proxy_accounts(idx)
            if rb.get("ok"):
                safe_answer(call.id, f"🔁 تم نقل {rb.get('moved', 0)} حساب لبروكسيات سليمة بنجاح!", show_alert=True)
            else:
                safe_answer(call.id, f"⚠️ {rb.get('error', 'تعذر النقل')}", show_alert=True)
            txt, markup = _render_proxy_detail_view(idx)
            safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=markup)
            return
        elif data.startswith("prx_del_"):
            try:
                idx = int(data[len("prx_del_"):])
            except Exception:
                idx = -1
            d_res = delete_single_proxy(idx, auto_rebind=True)
            if d_res.get("ok"):
                record_audit_log(user_id, call.from_user.first_name or "", "PROXY_DELETED", f"حذف {d_res.get('masked_uri')} | إعادة ربط {d_res.get('rebound', 0)}")
                safe_answer(call.id, f"🗑️ تم حذف الـ IP (نُقل {d_res.get('rebound', 0)} حساب لبديل سليم)", show_alert=True)
            else:
                safe_answer(call.id, f"⚠️ {d_res.get('error', 'غير موجود')}", show_alert=True)
            txt, markup = _render_proxies_view()
            safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=markup)
            return
        elif data == "prx_clear_dead":
            removed = clear_dead_proxies()
            safe_answer(call.id, f"🧹 تم حذف {removed} بروكسي ميت.", show_alert=True)
            txt, markup = _render_proxies_view()
            safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=markup)
            return
        elif data == "prx_clear_all":
            removed = clear_all_proxies()
            record_audit_log(user_id, call.from_user.first_name or "", "PROXIES_CLEARED", f"مسح {removed} بروكسي")
            safe_answer(call.id, f"🗑️ تم مسح {removed} بروكسي.", show_alert=True)
            txt, markup = _render_proxies_view()
            safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=markup)
            return
        elif data == "prx_4g_menu":
            safe_answer(call.id)
            txt, markup = _render_4g_bridge_view()
            _track_view(user_id, call.message.chat.id, call.message.message_id, "proxies_4g")
            safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=markup)
            return
        elif data == "prx_4g_start":
            safe_answer(call.id, "🚀 جاري تشغيل بوابة نفق الفورجي 4G...")
            def _bg_start_4g():
                res = start_gost_4g_bridge()
                if not res.get("ok"):
                    safe_send(call.message.chat.id, f"❌ {esc(res.get('error', 'فشل تشغيل النفق'))}")
                else:
                    record_audit_log(user_id, call.from_user.first_name or "", "4G_BRIDGE_STARTED", f"منفذ {res.get('exit_port')}")
                txt, markup = _render_4g_bridge_view()
                safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=markup)
            threading.Thread(target=_bg_start_4g, daemon=True).start()
            return
        elif data == "prx_4g_stop":
            stop_gost_4g_bridge()
            record_audit_log(user_id, call.from_user.first_name or "", "4G_BRIDGE_STOPPED", "إيقاف نفق 4G")
            safe_answer(call.id, "🛑 تم إيقاف نفق الفورجي.")
            txt, markup = _render_4g_bridge_view()
            safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=markup)
            return
        elif data == "prx_4g_check_geo":
            safe_answer(call.id, "🔍 جاري فحص اتصال الهاتف وعنوان 4G IP...")
            def _bg_geo_4g():
                refresh_4g_client_geo()
                txt, markup = _render_4g_bridge_view()
                safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=markup)
            threading.Thread(target=_bg_geo_4g, daemon=True).start()
            return
        elif data == "prx_4g_activate_mode":
            set_proxy_mode("4g_bridge")
            safe_answer(call.id, "✅ تم اعتماد نفق الفورجي 4G كمسار تشغيل افتراضي للحسابات.", show_alert=True)
            txt, markup = _render_4g_bridge_view()
            safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=markup)
            return

    elif data == "menu_backup_vault":
        if not has_admin_capability(user_id, "backups"):
            record_audit_log(user_id, call.from_user.first_name or "", "SECURITY_BLOCK", "محاولة فتح خزنة النسخ الاحتياطي بدون صلاحية")
            safe_answer(call.id, "⛔ خاص بالمطور والأدمن غير المقيد فقط.", show_alert=True)
            return
        txt, markup = _render_backup_vault_view()
        _track_view(user_id, call.message.chat.id, call.message.message_id, "backup_vault")
        safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=markup)
        return

    elif data == "act_export_backup":
        if not has_admin_capability(user_id, "backups"):
            record_audit_log(user_id, call.from_user.first_name or "", "SECURITY_BLOCK", "محاولة تصدير نسخة احتياطية بدون صلاحية")
            safe_answer(call.id, "⛔ خاص بالمطور والأدمن غير المقيد فقط.", show_alert=True)
            return
        safe_answer(call.id, "📦 جاري تجهيز حزمة النسخ الاحتياطي...")
        try:
            raw_zip = export_backup_zip_bytes(include_sessions=True)
            st_info = get_persistence_status()
            bio = io.BytesIO(raw_zip)
            bio.name = f"fb_operator_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
            bot.send_document(
                call.message.chat.id,
                bio,
                caption=(
                    f"📦 <b>نسخة احتياطية كاملة (#FB_BACKUP)</b>\n"
                    f"👥 <b>المستخدمون:</b> {st_info.get('users_count', 0)} | "
                    f"📌 <b>الحسابات:</b> {st_info.get('accounts_count', 0)} | "
                    f"🔑 <b>الجلسات:</b> {st_info.get('sessions_count', 0)}\n"
                    "<i>أعد إرسال هذا الملف هنا في أي وقت لاستعادة كل البيانات فوراً.</i>"
                )
            )
            record_audit_log(user_id, call.from_user.first_name or "", "BACKUP_EXPORTED", f"تصدير نسخة يدوية ({st_info.get('accounts_count', 0)} حساب)")
        except Exception as e:
            safe_send(call.message.chat.id, f"❌ تعذر تصدير النسخة الاحتياطية: <code>{esc(e)}</code>")
        return

    elif data == "act_hf_sync_now":
        if not has_admin_capability(user_id, "backups"):
            record_audit_log(user_id, call.from_user.first_name or "", "SECURITY_BLOCK", "محاولة مزامنة HF بدون صلاحية")
            safe_answer(call.id, "⛔ خاص بالمطور والأدمن غير المقيد فقط.", show_alert=True)
            return
        res_hf = hf_dataset_sync_upload()
        ok_hf = bool(res_hf.get("ok"))
        hf_msg = (
            f"تم رفع {res_hf.get('bytes', 0)} بايت إلى {res_hf.get('repo', 'HF')}"
            if ok_hf
            else str(res_hf.get("error") or res_hf.get("body") or f"HTTP {res_hf.get('status_code', '?')}")
        )
        safe_answer(call.id, ("✅ " if ok_hf else "⚠️ ") + hf_msg[:180], show_alert=True)
        txt, markup = _render_backup_vault_view()
        safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=markup)
        return

    elif data == "act_purge_24h":
        if not has_admin_capability(user_id, "backups"):
            record_audit_log(user_id, call.from_user.first_name or "", "SECURITY_BLOCK", "محاولة تنظيف التالفة 24س بدون صلاحية")
            safe_answer(call.id, "⛔ خاص بالمطور والأدمن غير المقيد فقط.", show_alert=True)
            return
        cnt_p, purged_ids = purge_expired_broken_accounts(BROKEN_ACCOUNT_TTL_HOURS)
        if cnt_p > 0:
            record_audit_log(user_id, call.from_user.first_name or "", "AUTO_PURGE_24H", f"تنظيف {cnt_p} حساب تالف مضى عليه {BROKEN_ACCOUNT_TTL_HOURS}س")
            safe_answer(call.id, f"🧹 تم حذف {cnt_p} حساب تالف تجاوز {BROKEN_ACCOUNT_TTL_HOURS} ساعة!", show_alert=True)
        else:
            safe_answer(call.id, f"✨ لا توجد حسابات تالفة تجاوزت {BROKEN_ACCOUNT_TTL_HOURS} ساعة.", show_alert=True)
        txt, markup = _render_backup_vault_view()
        safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=markup)
        return

    elif data == "menu_bkp_schedule":
        if not has_admin_capability(user_id, "backups"):
            record_audit_log(user_id, call.from_user.first_name or "", "SECURITY_BLOCK", "محاولة فتح جدولة النسخ الاحتياطي بدون صلاحية")
            safe_answer(call.id, "⛔ خاص بالمطور والأدمن غير المقيد فقط.", show_alert=True)
            return
        txt, markup = _render_backup_schedule_view()
        _track_view(user_id, call.message.chat.id, call.message.message_id, "backup_schedule")
        safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=markup)
        return

    elif data == "bkp_set_channel":
        if not has_admin_capability(user_id, "backups"):
            record_audit_log(user_id, call.from_user.first_name or "", "SECURITY_BLOCK", "محاولة تغيير قناة النسخ الاحتياطي بدون صلاحية")
            safe_answer(call.id, "⛔ خاص بالمطور والأدمن غير المقيد فقط.", show_alert=True)
            return
        st["input_mode"] = "waiting_backup_channel"
        safe_answer(call.id)
        safe_send(
            call.message.chat.id,
            "📡 <b>ربط قناة النسخ الاحتياطي التلقائي</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "1️⃣ أضف البوت أولاً كـ <b>مشرف (Admin)</b> داخل قناتك بصلاحية نشر الرسائل.\n"
            "2️⃣ ثم نفّذ إحدى الطرق التالية هنا الآن:\n"
            "• <b>أعد توجيه (Forward) أي منشور من القناة</b> إلى هذه المحادثة (موصى به للقنوات الخاصة).\n"
            "• أو أرسل معرف القناة: مثل <code>@MyBackupChannel</code> أو <code>-1001234567890</code>.",
            reply_markup=_prompt_back_markup("menu_backup_vault"),
        )
        return

    elif data == "bkp_clear_channel":
        if not has_admin_capability(user_id, "backups"):
            record_audit_log(user_id, call.from_user.first_name or "", "SECURITY_BLOCK", "محاولة فصل قناة النسخ بدون صلاحية")
            safe_answer(call.id, "⛔ خاص بالمطور والأدمن غير المقيد فقط.", show_alert=True)
            return
        save_backup_settings({"channel_id": None, "channel_title": "", "last_error": ""}, mark_dirty=True)
        record_audit_log(user_id, call.from_user.first_name or "", "BACKUP_CHANNEL_CLEARED", "فصل قناة النسخ الاحتياطي")
        safe_answer(call.id, "🗑️ تم فصل قناة النسخ الاحتياطي.", show_alert=True)
        txt, markup = _render_backup_vault_view()
        safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=markup)
        return

    elif data == "bkp_tog_enabled":
        if not has_admin_capability(user_id, "backups"):
            record_audit_log(user_id, call.from_user.first_name or "", "SECURITY_BLOCK", "محاولة تبديل جدولة النسخ بدون صلاحية")
            safe_answer(call.id, "⛔ خاص بالمطور والأدمن غير المقيد فقط.", show_alert=True)
            return
        bkp = load_backup_settings()
        new_val = not bool(bkp.get("enabled", True))
        save_backup_settings({"enabled": new_val}, mark_dirty=True)
        safe_answer(call.id, "✅ تم تفعيل الجدولة التلقائية بالوقت." if new_val else "⏸️ تم إيقاف الجدولة بالوقت.")
        txt, markup = _render_backup_vault_view()
        safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=markup)
        return

    elif data == "bkp_tog_onchange":
        if not has_admin_capability(user_id, "backups"):
            record_audit_log(user_id, call.from_user.first_name or "", "SECURITY_BLOCK", "محاولة تبديل النسخ عند التعديل بدون صلاحية")
            safe_answer(call.id, "⛔ خاص بالمطور والأدمن غير المقيد فقط.", show_alert=True)
            return
        bkp = load_backup_settings()
        new_val = not bool(bkp.get("on_change", False))
        save_backup_settings({"on_change": new_val}, mark_dirty=True)
        safe_answer(call.id, "⚡ تفعيل: نسخة تلقائية عند كل تغيير بيانات." if new_val else "⚪ تم إيقاف النسخ عند التعديل.")
        txt, markup = _render_backup_vault_view()
        safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=markup)
        return

    elif data == "bkp_tog_dm":
        if not has_admin_capability(user_id, "backups"):
            record_audit_log(user_id, call.from_user.first_name or "", "SECURITY_BLOCK", "محاولة تبديل إرسال النسخ للخاص بدون صلاحية")
            safe_answer(call.id, "⛔ خاص بالمطور والأدمن غير المقيد فقط.", show_alert=True)
            return
        bkp = load_backup_settings()
        new_dm = not bool(bkp.get("dm_enabled", True))
        save_backup_settings({"dm_enabled": new_dm}, mark_dirty=False)
        record_audit_log(user_id, call.from_user.first_name or "", "BACKUP_DM_TOGGLED", f"نسخ الخاص التلقائي: {'مفعل' if new_dm else 'متوقف'}")
        safe_answer(call.id, "📬 تم تفعيل إرسال النسخ للخاص حسب الجدول." if new_dm else "🔕 تم إيقاف إرسال ملفات ZIP للخاص تلقائياً!")
        txt, markup = _render_backup_vault_view()
        safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=markup)
        return

    elif data == "bkp_stop_auto":
        if not has_admin_capability(user_id, "backups"):
            record_audit_log(user_id, call.from_user.first_name or "", "SECURITY_BLOCK", "محاولة إيقاف النسخ التلقائي بدون صلاحية")
            safe_answer(call.id, "⛔ خاص بالمطور والأدمن غير المقيد فقط.", show_alert=True)
            return
        save_backup_settings({"enabled": False, "dm_enabled": False, "on_change": False}, mark_dirty=False)
        record_audit_log(user_id, call.from_user.first_name or "", "BACKUP_AUTO_STOPPED", "إيقاف كافة النسخ التلقائية للخاص والقناة")
        safe_answer(call.id, "🛑 تم إيقاف كل النسخ التلقائي للبوت والقناة! لن يرسل أي ZIP إلا يدوياً أو عند إعادة تفعيله.", show_alert=True)
        txt, markup = _render_backup_vault_view()
        safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=markup)
        return

    elif data == "bkp_set_interval_custom":
        if not has_admin_capability(user_id, "backups"):
            record_audit_log(user_id, call.from_user.first_name or "", "SECURITY_BLOCK", "محاولة تعديل توقيت النسخ بدون صلاحية")
            safe_answer(call.id, "⛔ خاص بالمطور والأدمن غير المقيد فقط.", show_alert=True)
            return
        st["input_mode"] = "waiting_backup_interval"
        safe_answer(call.id)
        safe_send(
            call.message.chat.id,
            "⏱️ <b>أرسل التوقيت المطلوب للنسخ الاحتياطي التلقائي:</b>\n"
            "• بالثواني (الحد الأدنى 10 ثوانٍ): <code>15 ثانية</code> أو <code>45s</code>\n"
            "• بالدقائق: <code>5 دقائق</code> أو <code>30m</code>\n"
            "• بالساعات: <code>2 ساعة</code> أو <code>6h</code>\n"
            "• بالأيام / الأسابيع / الشهور: <code>1 يوم</code> أو <code>1w</code> أو <code>1 شهر</code>\n"
            "• بالسنوات: <code>1 سنة</code> أو <code>1y</code>\n"
            "• أوقات مركبة: <code>1 ساعة و 30 دقيقة</code>",
            reply_markup=_prompt_back_markup("menu_bkp_schedule"),
        )
        return

    elif data in ("bkp_iv_10", "bkp_iv_30", "bkp_iv_300", "bkp_iv_3600", "bkp_iv_86400", "bkp_iv_604800", "bkp_iv_2592000", "bkp_iv_31536000") or data.startswith("bkp_iv_"):
        if not has_admin_capability(user_id, "backups"):
            record_audit_log(user_id, call.from_user.first_name or "", "SECURITY_BLOCK", f"محاولة ضبط جدولة {data} بدون صلاحية")
            safe_answer(call.id, "⛔ خاص بالمطور والأدمن غير المقيد فقط.", show_alert=True)
            return
        try:
            sec_val = int(data.replace("bkp_iv_", "", 1))
        except ValueError:
            safe_answer(call.id, "⚠️ قيمة توقيت غير صالحة.", show_alert=True)
            return
        if sec_val < MIN_BACKUP_INTERVAL_SEC or sec_val > MAX_BACKUP_INTERVAL_SEC:
            safe_answer(call.id, f"⚠️ المدة المسموحة من {MIN_BACKUP_INTERVAL_SEC} ثوانٍ حتى 10 سنوات.", show_alert=True)
            return
        saved_bkp = save_backup_settings({"interval_seconds": sec_val, "enabled": True}, mark_dirty=True)
        record_audit_log(user_id, call.from_user.first_name or "", "BACKUP_SCHEDULE_UPDATED", f"تعيين جدولة النسخ الاحتياطي إلى: {saved_bkp['interval_label']} ({sec_val}s)")
        safe_answer(call.id, f"✅ تم الضبط: {saved_bkp['interval_label']}", show_alert=True)
        txt, markup = _render_backup_schedule_view()
        safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=markup)
        return

    elif data == "act_backup_channel_now":
        if not has_admin_capability(user_id, "backups"):
            record_audit_log(user_id, call.from_user.first_name or "", "SECURITY_BLOCK", "محاولة إرسال نسخة للقناة بدون صلاحية")
            safe_answer(call.id, "⛔ خاص بالمطور والأدمن غير المقيد فقط.", show_alert=True)
            return
        safe_answer(call.id, "🚀 جاري تجهيز وإرسال النسخة الشاملة للقناة...")
        res_ch = send_backup_to_channel(bot, trigger_label="إرسال يدوي فوري")
        if res_ch.get("ok"):
            record_audit_log(user_id, call.from_user.first_name or "", "BACKUP_CHANNEL_SENT", f"إرسال نسخة #{res_ch.get('backup_number')} للقناة")
            safe_send(
                call.message.chat.id,
                f"✅ <b>تم إرسال النسخة الشاملة #{res_ch.get('backup_number')} إلى القناة بنجاح!</b>\n"
                f"📦 الحجم: <code>{res_ch.get('size_bytes', 0):,}</code> بايت | 🕒 <code>{esc(res_ch.get('timestamp'))}</code>",
                reply_markup=_back_home_markup("menu_backup_vault"),
            )
        else:
            safe_send(
                call.message.chat.id,
                f"⚠️ <b>تعذر إرسال النسخة للقناة:</b> {esc(res_ch.get('error', 'خطأ غير معروف'))}",
                reply_markup=_back_home_markup("menu_backup_vault"),
            )
        txt, markup = _render_backup_vault_view()
        safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=markup)
        return

    elif data == "bkp_restore_help":
        if not has_admin_capability(user_id, "backups"):
            record_audit_log(user_id, call.from_user.first_name or "", "SECURITY_BLOCK", "محاولة فتح الاستعادة الفورية بدون صلاحية")
            safe_answer(call.id, "⛔ خاص بالمطور والأدمن غير المقيد فقط.", show_alert=True)
            return
        st["input_mode"] = "waiting_restore_zip"
        safe_answer(call.id)
        safe_send(
            call.message.chat.id,
            "📥 <b>الاستعادة الفورية الشاملة من أي نسخة احتياطية</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "• ارفع ملف النسخة (<code>.zip</code>) هنا مباشرة أو <b>أعد توجيهه من قناة النسخ الاحتياطي</b>.\n"
            "• سيتم استرجاع كل شيء حرفياً كما كان لحظة التقاط النسخة في ثانية واحدة:\n"
            "  الحسابات والإيميلات، الجلسات، المستخدمين وصلاحياتهم، الأرصدة والتحويلات، الدعوات والتقديمات، التذاكر، وإعدادات اللوحة والأزرار والضبط.",
            reply_markup=_prompt_back_markup("menu_backup_vault"),
        )
        return

    elif data.startswith("eco_tog_"):
        if not has_admin_capability(user_id, "points_economy"):
            record_audit_log(user_id, call.from_user.first_name or "", "SECURITY_BLOCK", f"محاولة تبديل إعداد اقتصادي {data}")
            safe_answer(call.id, "⛔ خاص بالمطور والأدمن غير المقيد فقط.", show_alert=True)
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
        if not has_admin_capability(user_id, "points_economy"):
            record_audit_log(user_id, call.from_user.first_name or "", "SECURITY_BLOCK", f"محاولة تعديل تسعيرة {data}")
            safe_answer(call.id, "⛔ خاص بالمطور والأدمن غير المقيد فقط.", show_alert=True)
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
        safe_answer(call.id)
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
        safe_answer(call.id)
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
        if not t or (not has_admin_capability(user_id, "payment_notices") and int(t.get("user_id", 0)) != user_id):
            record_audit_log(user_id, call.from_user.first_name or "", "SECURITY_BLOCK", f"محاولة عرض تذكرة غير مصرحة {tid}")
            safe_answer(call.id, "⛔ غير مصرح لك بعرض هذه التذكرة.", show_alert=True)
            return
        txt, markup = _render_ticket_detail_view(user_id, tid)
        _track_view(user_id, call.message.chat.id, call.message.message_id, "ticket", ticket_id=tid)
        safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=markup)
        return

    elif data.startswith("tkt_reply_"):
        if not has_admin_capability(user_id, "payment_notices"):
            record_audit_log(user_id, call.from_user.first_name or "", "SECURITY_BLOCK", f"محاولة رد مطور مزيف {data}")
            safe_answer(call.id, "⛔ خاص بالمطور والأدمن غير المقيد فقط.", show_alert=True)
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
        if not t or (not has_admin_capability(user_id, "payment_notices") and int(t.get("user_id", 0)) != user_id):
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
        if not has_admin_capability(user_id, "payment_notices"):
            record_audit_log(user_id, call.from_user.first_name or "", "SECURITY_BLOCK", f"محاولة تسوية مالية مزيفة {data}")
            safe_answer(call.id, "⛔ التسويات المالية محجوبة عن صلاحيتك أو خاصة بالمطور فقط.", show_alert=True)
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
        safe_answer(call.id)
        if not require_perm_or_deny(call, "can_react", "⛔ صلاحية التفاعلات والإعجاب غير مفعلة لحسابك."):
            return
        cur_r = st.get("reaction_type", "like")
        mk = lambda k, lbl: f"✅ {lbl}" if cur_r == k else lbl
        has_r_url = bool((st.get("react_post_url") or "").strip())
        cur_p = st.get("react_post_index", 1)
        mp = lambda idx, lbl: f"✅ {lbl}" if (not has_r_url and cur_p == idx) else lbl
        cur_acc = st.get("react_acc_count", 0)
        ma = lambda n, lbl: f"✅ {lbl}" if cur_acc == n else lbl

        markup = types.InlineKeyboardMarkup(row_width=3)
        markup.row(
            types.InlineKeyboardButton(mk("like", "👍 Like"), callback_data="set_react_like"),
            types.InlineKeyboardButton(mk("love", "❤️ Love"), callback_data="set_react_love"),
            types.InlineKeyboardButton(mk("care", "🤗 Care"), callback_data="set_react_care")
        )
        markup.row(
            types.InlineKeyboardButton(mk("haha", "😂 Haha"), callback_data="set_react_haha"),
            types.InlineKeyboardButton(mk("wow", "😮 Wow"), callback_data="set_react_wow"),
            types.InlineKeyboardButton(mk("sad", "😢 Sad"), callback_data="set_react_sad")
        )
        markup.row(
            types.InlineKeyboardButton(mk("angry", "😡 Angry"), callback_data="set_react_angry"),
            types.InlineKeyboardButton(mk("unlike", "👎 إلغاء الإعجاب"), callback_data="set_react_unlike")
        )
        markup.row(
            types.InlineKeyboardButton(mp(1, "🥇 الأول"), callback_data="set_react_post_1"),
            types.InlineKeyboardButton(mp(2, "🥈 الثاني"), callback_data="set_react_post_2"),
            types.InlineKeyboardButton(mp(3, "🥉 الثالث"), callback_data="set_react_post_3")
        )
        markup.row(
            types.InlineKeyboardButton(f"{'✅ ' if (not has_r_url and cur_p > 3) else ''}🔢 رقم منشور مخصص", callback_data="set_react_post_custom"),
            types.InlineKeyboardButton(f"{'✅ ' if has_r_url else ''}🔗 رابط منشور مباشر", callback_data="set_react_post_url")
        )
        markup.row(
            types.InlineKeyboardButton(ma(0, "🔥 الكل"), callback_data="set_react_acc_0"),
            types.InlineKeyboardButton(ma(1, "1️⃣ حساب"), callback_data="set_react_acc_1"),
            types.InlineKeyboardButton(ma(2, "2️⃣ حسابين"), callback_data="set_react_acc_2"),
            types.InlineKeyboardButton(ma(3, "3️⃣ ثلاث"), callback_data="set_react_acc_3")
        )
        markup.row(
            types.InlineKeyboardButton(f"الحالة: [{'مفعل ✅' if st['like'] else 'معطل ❌'}]", callback_data="toggle_react_active")
        )
        markup.row(types.InlineKeyboardButton("🔙 حفظ والعودة للوحة التحكم", callback_data="back_to_main"))

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
        safe_answer(call.id)
        if not require_perm_or_deny(call, "can_react", "⛔ صلاحية التفاعلات غير مفعلة لحسابك."):
            return
        try:
            st["react_acc_count"] = int(data.replace("set_react_acc_", ""))
        except ValueError:
            return
        st["like"] = True
        safe_answer(call.id, f"تم التفعيل | عدد حسابات التفاعل: {'الكل' if st['react_acc_count'] == 0 else st['react_acc_count']}")
        call.data = "menu_wizard_react"
        handle_callbacks(call)

    elif data.startswith("set_react_post_"):
        safe_answer(call.id)
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
            st["like"] = True
            safe_answer(call.id, f"تم تحديد وتفعيل التفاعل على المنشور رقم {val}")
            call.data = "menu_wizard_react"
            handle_callbacks(call)

    elif data.startswith("set_react_"):
        safe_answer(call.id)
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
        safe_answer(call.id)
        st["like"] = not st["like"]
        safe_answer(call.id, f"التفاعل: {'مفعل ✅' if st['like'] else 'معطل ❌'}")
        call.data = "menu_wizard_react"
        handle_callbacks(call)

    elif data == "toggle_react_main":
        if not require_perm_or_deny(call, "can_react", "⛔ صلاحية التفاعلات غير مفعلة لحسابك."):
            return
        safe_answer(call.id)
        st["like"] = not st["like"]
        _refresh_after_toggle(call, user_id)
        safe_answer(call.id, f"التفاعل: {'مفعل ✅' if st['like'] else 'معطل ❌'}")

    # B) التعليقات (can_comment)
    elif data == "menu_wizard_comment":
        safe_answer(call.id)
        if not require_perm_or_deny(call, "can_comment", "⛔ صلاحية كتابة التعليقات غير مفعلة لحسابك."):
            return
        has_c_url = bool((st.get("comment_post_url") or "").strip())
        cur_cp = st.get("comment_post_index", 1)
        mp_c = lambda idx, lbl: f"✅ {lbl}" if (not has_c_url and cur_cp == idx) else lbl
        cur_cacc = st.get("comment_acc_count", 0)
        ma_c = lambda n, lbl: f"✅ {lbl}" if cur_cacc == n else lbl

        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.row(types.InlineKeyboardButton("✏️ كتابة / تعديل نص التعليق", callback_data="edit_comment_text"))
        markup.row(
            types.InlineKeyboardButton(mp_c(1, "🥇 الأول"), callback_data="set_cmt_post_1"),
            types.InlineKeyboardButton(mp_c(2, "🥈 الثاني"), callback_data="set_cmt_post_2"),
            types.InlineKeyboardButton(mp_c(3, "🥉 الثالث"), callback_data="set_cmt_post_3")
        )
        markup.row(
            types.InlineKeyboardButton(f"{'✅ ' if (not has_c_url and cur_cp > 3) else ''}🔢 رقم مخصص", callback_data="set_cmt_post_custom"),
            types.InlineKeyboardButton(f"{'✅ ' if has_c_url else ''}🔗 رابط منشور مباشر", callback_data="set_cmt_post_url")
        )
        markup.row(
            types.InlineKeyboardButton(ma_c(0, "🔥 الكل"), callback_data="set_cmt_acc_0"),
            types.InlineKeyboardButton(ma_c(1, "1️⃣ حساب"), callback_data="set_cmt_acc_1"),
            types.InlineKeyboardButton(ma_c(2, "2️⃣ حسابين"), callback_data="set_cmt_acc_2"),
            types.InlineKeyboardButton(ma_c(3, "3️⃣ ثلاث"), callback_data="set_cmt_acc_3")
        )
        markup.row(
            types.InlineKeyboardButton(f"الحالة: [{'مفعل ✅' if st['comment'] else 'معطل ❌'}]", callback_data="toggle_comment_active")
        )
        markup.row(types.InlineKeyboardButton("🔙 حفظ والعودة للوحة التحكم", callback_data="back_to_main"))

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
        safe_answer(call.id)
        if not require_perm_or_deny(call, "can_comment", "⛔ صلاحية التعليقات غير مفعلة لحسابك."):
            return
        st["input_mode"] = "waiting_comment_text"
        safe_send(
            call.message.chat.id,
            "💬 <b>أرسل الآن نص التعليق الجديد الذي ترغب بنشره:</b>",
            reply_markup=_prompt_back_markup("menu_wizard_comment")
        )

    elif data.startswith("set_cmt_post_"):
        safe_answer(call.id)
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
            if (st.get("comment_text") or "").strip():
                st["comment"] = True
            safe_answer(call.id, f"تم تحديد المنشور رقم {val}")
            call.data = "menu_wizard_comment"
            handle_callbacks(call)

    elif data.startswith("set_cmt_acc_"):
        safe_answer(call.id)
        if not require_perm_or_deny(call, "can_comment", "⛔ صلاحية التعليقات غير مفعلة لحسابك."):
            return
        try:
            val = int(data.replace("set_cmt_acc_", ""))
        except ValueError:
            return
        st["comment_acc_count"] = val
        if (st.get("comment_text") or "").strip():
            st["comment"] = True
        safe_answer(call.id, f"عدد الحسابات: {'الكل' if val == 0 else val}")
        call.data = "menu_wizard_comment"
        handle_callbacks(call)

    elif data == "toggle_comment_main":
        if not require_perm_or_deny(call, "can_comment", "⛔ صلاحية التعليقات غير مفعلة لحسابك."):
            return
        safe_answer(call.id)
        if not st["comment"] and not (st.get("comment_text") or "").strip():
            st["input_mode"] = "waiting_comment_text"
            safe_answer(call.id, "أرسل نص التعليق أولاً لتفعيله")
            safe_send(
                call.message.chat.id,
                "💬 <b>أرسل الآن نص التعليق الجديد الذي ترغب بنشره:</b>",
                reply_markup=_prompt_back_markup("back_to_main")
            )
            return
        st["comment"] = not st["comment"]
        _refresh_after_toggle(call, user_id)
        safe_answer(call.id, f"التعليق: {'مفعل ✅' if st['comment'] else 'معطل ❌'}")

    elif data == "toggle_comment_active":
        if not require_perm_or_deny(call, "can_comment", "⛔ صلاحية التعليقات غير مفعلة لحسابك."):
            return
        safe_answer(call.id)
        if not st["comment"] and not (st.get("comment_text") or "").strip():
            st["input_mode"] = "waiting_comment_text"
            safe_answer(call.id, "أرسل نص التعليق أولاً لتفعيله")
            safe_send(
                call.message.chat.id,
                "💬 <b>أرسل الآن نص التعليق الجديد الذي ترغب بنشره:</b>",
                reply_markup=_prompt_back_markup("menu_wizard_comment")
            )
            return
        st["comment"] = not st["comment"]
        safe_answer(call.id, f"التعليق: {'مفعل ✅' if st['comment'] else 'معطل ❌'}")
        call.data = "menu_wizard_comment"
        handle_callbacks(call)

    # C) الصداقة والمتابعة (can_friend_follow)
    elif data == "toggle_friend":
        safe_answer(call.id)
        if not require_perm_or_deny(call, "can_friend_follow", "⛔ صلاحية الصداقة والمتابعة غير مفعلة لحسابك."):
            return
        st["friend"] = not st["friend"]
        if st["friend"]:
            st["cancel_friend"] = False
        _refresh_after_toggle(call, user_id)
        safe_answer(call.id, f"طلب الصداقة: {'مفعل ✅' if st['friend'] else 'معطل ❌'}")

    elif data == "toggle_cancel_friend":
        safe_answer(call.id)
        if not require_perm_or_deny(call, "can_friend_follow", "⛔ صلاحية الصداقة والمتابعة غير مفعلة لحسابك."):
            return
        st["cancel_friend"] = not st["cancel_friend"]
        if st["cancel_friend"]:
            st["friend"] = False
        _refresh_after_toggle(call, user_id)
        safe_answer(call.id, f"إلغاء طلب الصداقة: {'مفعل ✅' if st['cancel_friend'] else 'معطل ❌'}")

    elif data == "toggle_follow":
        safe_answer(call.id)
        if not require_perm_or_deny(call, "can_friend_follow", "⛔ صلاحية الصداقة والمتابعة غير مفعلة لحسابك."):
            return
        st["follow"] = not st["follow"]
        if st["follow"]:
            st["unfollow"] = False
        _refresh_after_toggle(call, user_id)
        safe_answer(call.id, f"المتابعة: {'مفعل ✅' if st['follow'] else 'معطل ❌'}")

    elif data == "toggle_unfollow":
        safe_answer(call.id)
        if not require_perm_or_deny(call, "can_friend_follow", "⛔ صلاحية الصداقة والمتابعة غير مفعلة لحسابك."):
            return
        st["unfollow"] = not st["unfollow"]
        if st["unfollow"]:
            st["follow"] = False
        _refresh_after_toggle(call, user_id)
        safe_answer(call.id, f"إلغاء المتابعة: {'مفعل ✅' if st['unfollow'] else 'معطل ❌'}")

    # D) الرسائل الخاصة (can_message)
    elif data == "menu_wizard_message":
        safe_answer(call.id)
        if not require_perm_or_deny(call, "can_message", "⛔ صلاحية الرسائل الخاصة غير مفعلة لحسابك."):
            return
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.row(types.InlineKeyboardButton("✏️ كتابة / تعديل نص رسالتك", callback_data="menu_msg_config"))
        markup.row(types.InlineKeyboardButton(f"الحالة: [{'مفعل ✅' if st['message'] else 'معطل ❌'}]", callback_data="toggle_message"))
        markup.row(types.InlineKeyboardButton("🔙 حفظ والعودة للوحة التحكم", callback_data="back_to_main"))
        safe_edit_message(
            "✉️ <b>معالج رسائل الماسنجر الخاصة:</b>\n\n"
            f"📝 <b>النص الحالي للرسالة:</b>\n<i>'{esc(st['message_text'])}'</i>\n\n"
            f"🔗 <b>الهدف الحالي:</b> <code>{esc((st.get('target_url') or '')[:45])}</code>\n"
            f"🔘 <b>الحالة:</b> {'مفعل ✅' if st['message'] else 'معطل ❌'}\n\n"
            "<i>اضغط (✏️ كتابة / تعديل نص رسالتك) لكتابة رسالة جديدة وتفعيلها تلقائياً.</i>",
            call.message.chat.id, call.message.message_id, reply_markup=markup
        )

    elif data == "toggle_message":
        if not require_perm_or_deny(call, "can_message", "⛔ صلاحية الرسائل الخاصة غير مفعلة لحسابك."):
            return
        safe_answer(call.id)
        if not st["message"] and not (st.get("message_text") or "").strip():
            st["input_mode"] = "waiting_msg_text"
            safe_answer(call.id, "أرسل نص الرسالة الخاصة أولاً لتفعيلها")
            safe_send(
                call.message.chat.id,
                "✍️ <b>اكتب الآن نص الرسالة الخاصة التي تريد إرسالها عبر ماسنجر:</b>",
                reply_markup=_prompt_back_markup("menu_wizard_message")
            )
            return
        st["message"] = not st["message"]
        safe_answer(call.id, f"الرسائل الخاصة: {'مفعل ✅' if st['message'] else 'معطل ❌'}")
        call.data = "menu_wizard_message"
        handle_callbacks(call)

    elif data == "toggle_msg_main":
        if not require_perm_or_deny(call, "can_message", "⛔ صلاحية الرسائل الخاصة غير مفعلة لحسابك."):
            return
        safe_answer(call.id)
        if not st["message"] and not (st.get("message_text") or "").strip():
            st["input_mode"] = "waiting_msg_text"
            safe_answer(call.id, "أرسل نص الرسالة الخاصة أولاً لتفعيلها")
            safe_send(
                call.message.chat.id,
                "✍️ <b>اكتب الآن نص الرسالة الخاصة التي تريد إرسالها عبر ماسنجر:</b>",
                reply_markup=_prompt_back_markup("back_to_main")
            )
            return
        st["message"] = not st["message"]
        _refresh_after_toggle(call, user_id)
        safe_answer(call.id, f"الرسائل الخاصة: {'مفعل ✅' if st['message'] else 'معطل ❌'}")

    elif data == "menu_msg_config":
        if not require_perm_or_deny(call, "can_message", "⛔ صلاحية الرسائل الخاصة غير مفعلة لحسابك."):
            return
        st["input_mode"] = "waiting_msg_text"
        safe_answer(call.id)
        safe_send(
            call.message.chat.id,
            f"✉️ <b>النص الحالي للرسالة الخاصة:</b>\n<i>'{esc(st['message_text'])}'</i>\n\n"
            "✍️ <b>أرسل الآن نص رسالتك الخاصة الجديد (وسيتفعل تلقائياً عند الإرسال):</b>",
            reply_markup=_prompt_back_markup("menu_wizard_message")
        )

    # E) البلاغات والحظر (can_report)
    elif data == "toggle_rep_post":
        safe_answer(call.id)
        if not require_perm_or_deny(call, "can_report", "⛔ صلاحية البلاغات غير مفعلة لحسابك."):
            return
        st["report_post"] = not st["report_post"]
        if st["report_post"]:
            st["report_profile"] = False
        _refresh_after_toggle(call, user_id)
        safe_answer(call.id, f"بلاغ المنشور: {'مفعل ✅' if st['report_post'] else 'معطل ❌'}")

    elif data == "toggle_rep_profile":
        safe_answer(call.id)
        if not require_perm_or_deny(call, "can_report", "⛔ صلاحية البلاغات غير مفعلة لحسابك."):
            return
        st["report_profile"] = not st["report_profile"]
        if st["report_profile"]:
            st["report_post"] = False
        _refresh_after_toggle(call, user_id)
        safe_answer(call.id, f"بلاغ الحساب: {'مفعل ✅' if st['report_profile'] else 'معطل ❌'}")

    elif data == "toggle_block":
        if not require_perm_or_deny(call, "can_report", "⛔ صلاحية الحظر غير مفعلة لحسابك."):
            return
        safe_answer(call.id)
        st["block"] = not st["block"]
        _refresh_after_toggle(call, user_id)
        safe_answer(call.id, f"حظر الحساب: {'مفعل ✅' if st['block'] else 'معطل ❌'}")

    elif data == "menu_rep_config":
        safe_answer(call.id)
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
        safe_answer(call.id)
        if not require_perm_or_deny(call, "can_report", "⛔ صلاحية البلاغات غير مفعلة لحسابك."):
            return
        rk = data.replace("set_rep_reason_", "")
        if rk in REPORT_REASONS_AR:
            st["rep_reason"] = rk
            safe_answer(call.id, f"تم اختيار السبب: {REPORT_REASONS_AR[rk]}")
        call.data = "menu_rep_config"
        handle_callbacks(call)

    elif data.startswith("set_rep_victim_"):
        safe_answer(call.id)
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
        safe_answer(call.id)
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
        safe_answer(call.id)
        st["interact_cmt"] = not st["interact_cmt"]
        safe_answer(call.id, f"الميزة: {'مفعلة ✅' if st['interact_cmt'] else 'معطلة ❌'}")
        call.data = "menu_cmt_interact"
        handle_callbacks(call)

    elif data == "toggle_cmt_int_main":
        if not require_perm_or_deny(call, "can_interact_comments", "⛔ صلاحية التفاعل مع التعليقات غير مفعلة."):
            return
        safe_answer(call.id)
        st["interact_cmt"] = not st["interact_cmt"]
        _refresh_after_toggle(call, user_id)
        safe_answer(call.id, f"الرد على التعليق: {'مفعل ✅' if st['interact_cmt'] else 'معطل ❌'}")

    elif data == "cycle_cmt_mode":
        safe_answer(call.id)
        if not require_perm_or_deny(call, "can_interact_comments", "⛔ صلاحية التفاعل مع التعليقات غير مفعلة."):
            return
        modes = ["first", "author", "keyword", "index"]
        curr_idx = modes.index(st["cmt_target_mode"]) if st["cmt_target_mode"] in modes else 0
        st["cmt_target_mode"] = modes[(curr_idx + 1) % len(modes)]
        st["interact_cmt"] = True
        call.data = "menu_cmt_interact"
        handle_callbacks(call)

    elif data == "cycle_cmt_reaction":
        safe_answer(call.id)
        if not require_perm_or_deny(call, "can_interact_comments", "⛔ صلاحية التفاعل مع التعليقات غير مفعلة."):
            return
        reactions = ["like", "love", "care", "haha", "wow", "sad", "angry", "none"]
        curr_idx = reactions.index(st["cmt_reaction"]) if st["cmt_reaction"] in reactions else 0
        st["cmt_reaction"] = reactions[(curr_idx + 1) % len(reactions)]
        st["interact_cmt"] = True
        call.data = "menu_cmt_interact"
        handle_callbacks(call)

    elif data == "edit_cmt_target_val":
        safe_answer(call.id)
        if not require_perm_or_deny(call, "can_interact_comments", "⛔ صلاحية التفاعل مع التعليقات غير مفعلة."):
            return
        st["input_mode"] = "waiting_cmt_val"
        safe_send(
            call.message.chat.id,
            "✏️ <b>أرسل الآن اسم كاتب التعليق أو الكلمة المفتاحية أو الترتيب:</b>",
            reply_markup=_prompt_back_markup("menu_cmt_interact")
        )

    elif data == "edit_cmt_reply_text":
        safe_answer(call.id)
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

        if st.get("selected_acc") not in ("all", "multi") and any(a["id"] == st["selected_acc"] for a in usable):
            st["selected_accs"] = [st["selected_acc"]]
        sel_set = set(st.get("selected_accs") or [])

        markup = types.InlineKeyboardMarkup(row_width=2)
        all_chk = "✅" if st.get("selected_acc") == "all" else "⬜"
        markup.row(types.InlineKeyboardButton(f"{all_chk} جميع الحسابات المتاحة تلقائياً", callback_data="sel_acc_all"))
        for a in usable:
            st_icon = "🟢" if "نشط" in a.get("status", "") else "🔴"
            chk = "☑️" if (st.get("selected_acc") == "all" or a["id"] in sel_set) else "⬜"
            cc = f" [{a.get('bound_proxy_country')}]" if a.get("bound_proxy_country") else ""
            markup.row(
                types.InlineKeyboardButton(f"{chk} {st_icon} {a['name']}{cc}", callback_data=f"sel_acc_tog_{a['id']}"),
                types.InlineKeyboardButton("⚡ هذا فقط", callback_data=f"sel_acc_only_{a['id']}"),
            )
        markup.row(
            types.InlineKeyboardButton(f"✅ اعتماد المحدد ({len(sel_set)})", callback_data="sel_acc_done"),
            types.InlineKeyboardButton("⬜ مسح التحديد", callback_data="sel_acc_none"),
        )
        markup.row(types.InlineKeyboardButton("🔙 رجوع للرئيسية", callback_data="back_to_main"))
        safe_edit_message(
            "👥 <b>اختيار الحسابات المنفذة (واحد / متعدد / الكل):</b>\n"
            "<i>اضغط ☑️ لتحديد عدة حسابات أو ⚡ لتنفيذ سريع بحساب واحد ثم اضغط اعتماد.</i>",
            call.message.chat.id, call.message.message_id, reply_markup=markup
        )

    elif data.startswith("sel_acc_"):
        chosen = data.replace("sel_acc_", "", 1)
        usable = get_usable_accounts_for_user(user_id)
        usable_ids = {a["id"] for a in usable}
        if not (is_super_admin(user_id) or has_permission(user_id, "can_use_accounts") or (has_permission(user_id, "can_execute") and usable)):
            safe_answer(call.id, "⛔ ليس لديك صلاحية استخدام الحسابات.", show_alert=True)
            return

        if chosen == "all":
            st["selected_acc"] = "all"
            st["selected_accs"] = []
            persist_user_states()
            safe_answer(call.id, "✅ تم اختيار جميع الحسابات المتاحة!")
            safe_edit_message(get_dashboard_text(user_id), call.message.chat.id, call.message.message_id, reply_markup=get_main_dashboard_markup(user_id))
            return

        if chosen == "none":
            st["selected_acc"] = "multi"
            st["selected_accs"] = []
            chosen_msg = "⬜ تم تفريغ التحديد — اختر حساباتك ثم اضغط اعتماد"
            safe_answer(call.id, chosen_msg)
        elif chosen == "done":
            valid = [x for x in (st.get("selected_accs") or []) if x in usable_ids]
            st["selected_accs"] = valid
            if not valid:
                st["selected_acc"] = "all"
                safe_answer(call.id, "لم تحدد حسابات؛ أُعيدت للوضع التلقائي (الكل)")
            elif len(valid) == 1:
                st["selected_acc"] = valid[0]
                safe_answer(call.id, "✅ تم اعتماد الحساب المنفذ!")
            else:
                st["selected_acc"] = "multi"
                safe_answer(call.id, f"✅ تم اعتماد {len(valid)} حسابات للتنفيذ!")
            persist_user_states()
            safe_edit_message(get_dashboard_text(user_id), call.message.chat.id, call.message.message_id, reply_markup=get_main_dashboard_markup(user_id))
            return
        elif chosen.startswith("tog_"):
            tid = chosen[len("tog_"):]
            if tid not in usable_ids:
                record_audit_log(user_id, call.from_user.first_name or "", "SECURITY_BLOCK", f"محاولة اختيار حساب غير مصرح {tid}")
                safe_answer(call.id, "⛔ غير مسموح لك باختيار هذا الحساب!", show_alert=True)
                return
            cur_list = [x for x in (st.get("selected_accs") or []) if x in usable_ids]
            if st.get("selected_acc") not in ("all", "multi") and st["selected_acc"] in usable_ids and st["selected_acc"] not in cur_list:
                cur_list.append(st["selected_acc"])
            if tid in cur_list:
                cur_list.remove(tid)
            else:
                cur_list.append(tid)
            st["selected_acc"] = "multi"
            st["selected_accs"] = cur_list
            persist_user_states()
            safe_answer(call.id, f"المحدد الآن: {len(cur_list)}")
        elif chosen.startswith("only_"):
            tid = chosen[len("only_"):]
            if tid not in usable_ids:
                safe_answer(call.id, "⛔ غير مسموح!", show_alert=True)
                return
            st["selected_acc"] = tid
            st["selected_accs"] = [tid]
            persist_user_states()
            safe_answer(call.id, "✅ تم اختيار الحساب للتنفيذ!")
            safe_edit_message(get_dashboard_text(user_id), call.message.chat.id, call.message.message_id, reply_markup=get_main_dashboard_markup(user_id))
            return
        else:
            if chosen not in usable_ids:
                record_audit_log(user_id, call.from_user.first_name or "", "SECURITY_BLOCK", f"محاولة اختيار حساب غير مصرح {chosen}")
                safe_answer(call.id, "⛔ غير مسموح لك باختيار هذا الحساب!", show_alert=True)
                return
            st["selected_acc"] = chosen
            st["selected_accs"] = [chosen]
            persist_user_states()
            safe_answer(call.id, "تم تحديد الحساب المنفذ بنجاح!")
            safe_edit_message(get_dashboard_text(user_id), call.message.chat.id, call.message.message_id, reply_markup=get_main_dashboard_markup(user_id))
            return

        # تحديث قائمة الاختيار المتعدد مباشرة بعد tog_ أو none
        sel_set = set(st.get("selected_accs") or [])
        markup = types.InlineKeyboardMarkup(row_width=2)
        all_chk = "✅" if st.get("selected_acc") == "all" else "⬜"
        markup.row(types.InlineKeyboardButton(f"{all_chk} جميع الحسابات المتاحة تلقائياً", callback_data="sel_acc_all"))
        for a in usable:
            st_icon = "🟢" if "نشط" in a.get("status", "") else "🔴"
            chk = "☑️" if (st.get("selected_acc") == "all" or a["id"] in sel_set) else "⬜"
            cc = f" [{a.get('bound_proxy_country')}]" if a.get("bound_proxy_country") else ""
            markup.row(
                types.InlineKeyboardButton(f"{chk} {st_icon} {a['name']}{cc}", callback_data=f"sel_acc_tog_{a['id']}"),
                types.InlineKeyboardButton("⚡ هذا فقط", callback_data=f"sel_acc_only_{a['id']}"),
            )
        markup.row(
            types.InlineKeyboardButton(f"✅ اعتماد المحدد ({len(sel_set)})", callback_data="sel_acc_done"),
            types.InlineKeyboardButton("⬜ مسح التحديد", callback_data="sel_acc_none"),
        )
        markup.row(types.InlineKeyboardButton("🔙 رجوع للرئيسية", callback_data="back_to_main"))
        safe_edit_message(
            "👥 <b>اختيار الحسابات المنفذة (واحد / متعدد / الكل):</b>\n"
            "<i>اضغط ☑️ لتحديد عدة حسابات أو ⚡ لتنفيذ سريع بحساب واحد ثم اضغط اعتماد.</i>",
            call.message.chat.id, call.message.message_id, reply_markup=markup
        )

    # H) إدارة الحسابات (معزولة الملكية: المطور/النائب غير المقيد يرى الكل، والمستخدم يرى حساباته المضافة فقط)
    elif data == "menu_manage_accs":
        is_dev = has_admin_capability(user_id, "accounts_pool")
        if not (is_dev or has_permission(user_id, "can_add_accounts") or has_permission(user_id, "can_delete_accounts")):
            record_audit_log(user_id, call.from_user.first_name or "", "SECURITY_BLOCK", "محاولة فتح إدارة الحسابات بدون صلاحية")
            safe_answer(call.id, "⛔ ليس لديك صلاحية إدارة أو إضافة الحسابات.", show_alert=True)
            return

        txt, markup = _render_manage_accs_view(user_id)
        safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=markup)
        _track_view(user_id, call.message.chat.id, call.message.message_id, "manage_accs")

    elif data.startswith("acc_view_"):
        acc_id = data.replace("acc_view_", "", 1)
        target_acc = get_account_by_id(acc_id)
        if not target_acc:
            safe_answer(call.id, "الحساب غير موجود.", show_alert=True)
            return
        can_inspect, _, _ = _user_can_inspect_account(user_id, target_acc)
        if not can_inspect:
            record_audit_log(user_id, call.from_user.first_name or "", "SECURITY_BLOCK", f"محاولة استعراض بطاقة حساب غير مصرح {acc_id}")
            safe_answer(call.id, "⛔ لا تملك صلاحية عرض أو إدارة هذا الحساب!", show_alert=True)
            return
        txt, markup = _render_account_detail_view(user_id, target_acc)
        safe_answer(call.id)
        safe_edit_message(txt, call.message.chat.id, call.message.message_id, reply_markup=markup)
        _track_view(user_id, call.message.chat.id, call.message.message_id, f"acc_view_{acc_id}")

    elif data.startswith("acc_check_") or data.startswith("acc_relogin_"):
        is_relogin = data.startswith("acc_relogin_")
        acc_id = data.replace("acc_relogin_" if is_relogin else "acc_check_", "", 1)
        target_acc = get_account_by_id(acc_id)
        if not target_acc:
            safe_answer(call.id, "الحساب غير موجود.", show_alert=True)
            return
        can_inspect, _, _ = _user_can_inspect_account(user_id, target_acc)
        if not can_inspect:
            record_audit_log(user_id, call.from_user.first_name or "", "SECURITY_BLOCK", f"محاولة فحص/إعادة دخول حساب غير مصرح {acc_id}")
            safe_answer(call.id, "⛔ لا تملك صلاحية فحص أو إعادة تسجيل دخول هذا الحساب!", show_alert=True)
            return
        if is_relogin and (not target_acc.get("email") or not target_acc.get("password") or target_acc.get("password") == "[SESSION_COOKIES]"):
            safe_answer(call.id, "🍪 هذا الحساب مضاف بالكوكيز فقط بدون كلمة مرور محفوظة — استخدم الشاشة الحية أو أعد إضافته.", show_alert=True)
            return
        safe_answer(call.id, f"{'🔑 جاري إعادة تسجيل الدخول' if is_relogin else '🔍 جاري فحص'} {target_acc.get('name', acc_id)}...")
        threading.Thread(
            target=check_all_sessions_worker,
            args=(call.message.chat.id, user_id, acc_id, is_relogin),
            daemon=True,
        ).start()

    elif data.startswith("acc_mission_"):
        acc_id = data.replace("acc_mission_", "", 1)
        target_acc = get_account_by_id(acc_id)
        if not target_acc:
            safe_answer(call.id, "الحساب غير موجود.", show_alert=True)
            return
        _, _, can_use = _user_can_inspect_account(user_id, target_acc)
        if not can_use:
            record_audit_log(user_id, call.from_user.first_name or "", "SECURITY_BLOCK", f"محاولة تفعيل مهمة على حساب غير مصرح {acc_id}")
            safe_answer(call.id, "⛔ لا تملك صلاحية استخدام هذا الحساب في المهام!", show_alert=True)
            return
        st["selected_acc"] = acc_id
        st["selected_accs"] = [acc_id]
        persist_user_states()
        safe_answer(call.id, f"⚡ تم تحديد ({target_acc.get('name', acc_id)}) للتنفيذ! اختر الإجراء المطلوب ثم ابدأ.")
        safe_edit_message(get_dashboard_text(user_id), call.message.chat.id, call.message.message_id, reply_markup=get_main_dashboard_markup(user_id))
        _track_view(user_id, call.message.chat.id, call.message.message_id, "main")

    elif data.startswith("del_acc_"):
        if not (has_admin_capability(user_id, "accounts_pool") or has_permission(user_id, "can_delete_accounts")):
            record_audit_log(user_id, call.from_user.first_name or "", "SECURITY_BLOCK", f"محاولة حذف حساب بدون صلاحية: {data}")
            safe_answer(call.id, "⛔ ليس لديك صلاحية حذف الحسابات.", show_alert=True)
            return
        acc_id = data.replace("del_acc_", "")
        target_acc = get_account_by_id(acc_id)
        if not target_acc:
            safe_answer(call.id, "الحساب غير موجود.", show_alert=True)
            return
        # منع المستخدم الفرعي من حذف حساب المطور أو حساب مستخدم آخر!
        if not has_admin_capability(user_id, "accounts_pool") and target_acc.get("owner_id") != user_id:
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
        if not (has_admin_capability(user_id, "accounts_pool") or has_permission(user_id, "can_delete_accounts")):
            safe_answer(call.id, "⛔ ليس لديك صلاحية تنظيف/حذف الحسابات.", show_alert=True)
            return
        scope_owner = None if has_admin_capability(user_id, "accounts_pool") else user_id
        count, purged = purge_broken_accounts(owner_id=scope_owner)
        if count > 0:
            record_audit_log(user_id, call.from_user.first_name or "", "ACCOUNT_PURGE", f"تنظيف {count} حساب تالف: {', '.join(purged)}")
            safe_answer(call.id, f"🧹 تم حذف {count} حساب غير نشط وتنظيف ملفاتهم!", show_alert=True)
        else:
            safe_answer(call.id, "✨ لا توجد حسابات تالفة في نطاقك حالياً!", show_alert=True)
        call.data = "menu_manage_accs"
        handle_callbacks(call)

    elif data == "act_add_acc":
        safe_answer(call.id)
        if not require_perm_or_deny(call, "can_add_accounts", "⛔ ليس لديك صلاحية إضافة حسابات للبوت. اطلب الإذن من المطور الرئيسي."):
            return
        st["input_mode"] = "add_acc_name"
        st["temp_acc_data"] = {}
        safe_send(
            call.message.chat.id,
            "➕ <b>أرسل اسم الحساب أو لقبه أولاً (مثال: حساب فيسبوك 1):</b>",
            reply_markup=_prompt_back_markup("menu_manage_accs")
        )

    elif data == "act_import_cookies":
        safe_answer(call.id)
        if not require_perm_or_deny(call, "can_add_accounts", "⛔ ليس لديك صلاحية إضافة حسابات للبوت."):
            return
        st["input_mode"] = "import_ck_name"
        st["temp_acc_data"] = {}
        safe_send(
            call.message.chat.id,
            "🍪 <b>استيراد حساب عبر جلسة/كوكيز متصفح جاهزة</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "💡 هذه الطريقة تتجنب تحدي الروبوتات (Arkose CAPTCHA) تماماً لأنك تسجّل دخولك من جهازك ثم تستورد الجلسة مباشرة.\n\n"
            "1️⃣ أولاً: أرسل الآن <b>اسماً أو لقباً للحساب</b> (مثال: حسابي الشخصي 1):",
            reply_markup=_prompt_back_markup("menu_manage_accs")
        )

    elif data == "act_check_sessions":
        if not (has_admin_capability(user_id, "accounts_pool") or has_permission(user_id, "can_add_accounts") or has_permission(user_id, "can_use_accounts")):
            safe_answer(call.id, "⛔ ليس لديك صلاحية فحص الجلسات.", show_alert=True)
            return
        safe_answer(call.id, "🔄 جاري فحص وتحديث جلسات الحسابات...")
        threading.Thread(target=check_all_sessions_worker, args=(call.message.chat.id, user_id), daemon=True).start()

    elif data == "back_to_main":
        safe_answer(call.id)
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
        safe_answer(call.id)
        if not user_has_any_action_perm(user_id):
            safe_answer(call.id, "⛔ لم يفعّل المطور لك أي أداة تنفيذ (تفاعل/تعليق/بلاغ/صداقة) بعد!", show_alert=True)
            return
        usable = get_usable_accounts_for_user(user_id)
        if not usable:
            safe_answer(call.id, "⛔ لا توجد حسابات متاحة أو مصرح لك باستخدامها للتنفيذ!", show_alert=True)
            return
        has_act, act_err = _has_any_enabled_mission_action(user_id, st)
        if not has_act:
            safe_answer(call.id, act_err, show_alert=True)
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

def check_all_sessions_worker(chat_id: int, requester_id: int, target_acc_id: str = "", force_relogin: bool = False):
    clean_tid = str(target_acc_id or "").strip()
    try:
        start_lbl = (
            f"⏳ <b>{'جاري إعادة تسجيل الدخول بالبيانات المحفوظة' if force_relogin else 'جاري فحص الجلسة في المتصفح'}...</b>"
            if clean_tid
            else "⏳ <b>بدء فحص حالة الجلسات في المتصفح...</b>"
        )
        status_msg = bot.send_message(chat_id, start_lbl)
        status_msg_id = status_msg.message_id if status_msg else None
    except Exception:
        status_msg_id = None

    is_dev = is_super_admin(requester_id) or has_admin_capability(requester_id, "accounts_pool")
    if clean_tid:
        t_acc = get_account_by_id(clean_tid)
        if t_acc:
            can_inspect, _, _ = _user_can_inspect_account(requester_id, t_acc)
            accs = [t_acc] if can_inspect else []
        else:
            accs = []
    elif is_dev:
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

    report_lines: list[str] = []
    hitl_needed: list[dict] = []

    for idx, a in enumerate(accs, 1):
        try:
            safe_edit_message(f"🔄 <b>جاري فحص الحساب ({idx}/{total}):</b> {esc(a['name'])}...", chat_id, status_msg_id)
            lock = get_profile_lock(a["id"])
            proxy_uri = _account_proxy_guard_uri(a)
            live_reason = ""
            diag_code = ""
            can_otp_flag = False
            is_active = False
            fb_id = ""
            prof_quality = None
            real_pwd = str(a.get("password") or "")
            has_saved_creds = bool(a.get("email") and real_pwd and real_pwd != "[SESSION_COOKIES]")
            use_fresh_login = bool(force_relogin and has_saved_creds)

            if force_relogin and not has_saved_creds:
                msg_no_creds = "🍪 هذا الحساب مضاف بالكوكيز فقط بدون كلمة مرور محفوظة — افتح الشاشة الحية لتثبيت الجلسة."
                report_lines.append(f"• 🔴 <b>{esc(a['name'])}:</b> {esc(msg_no_creds)}")
                hitl_needed.append({
                    "id": a["id"],
                    "name": a.get("name", a["id"]),
                    "reason": msg_no_creds,
                    "can_otp": False,
                    "has_creds": False,
                    "code": "cookie_only",
                })
                continue

            with lock, proxy_execution_guard(proxy_uri, min_gap_sec=1.5), _browser_semaphore:
                if use_fresh_login:
                    safe_edit_message(
                        f"🗑️ <b>حذف الجلسة السابقة وإعادة تسجيل الدخول ({idx}/{total}):</b> {esc(a['name'])}...",
                        chat_id, status_msg_id
                    )
                with sync_playwright() as p:
                    ctx = launch_account_browser(p, a["profile_dir"], visible=False, fresh_session=use_fresh_login)
                    try:
                        page = ctx.pages[0] if ctx.pages else ctx.new_page()
                        page.goto("https://www.facebook.com/", timeout=30000, wait_until="domcontentloaded")
                        human_delay(1.8, 2.8)
                        dismiss_dialogs(page)

                        if use_fresh_login:
                            relog_ok = auto_login_facebook(
                                ctx, page, a.get("email", ""), real_pwd, max_wait=40, force_fresh=True
                            )
                            is_logged, fb_id = check_facebook_login_cookies(ctx)
                            diag_after = diagnose_facebook_challenge(page)
                            diag_code = str(diag_after.get("code") or "")
                            can_otp_flag = bool(diag_after.get("can_otp"))
                            is_active = bool(relog_ok and is_logged and diag_after.get("is_ok"))
                            if not is_active:
                                live_reason = get_login_error(ctx) or diag_after.get("message") or "تعذر إتمام إعادة الدخول بالبيانات المحفوظة"
                        else:
                            diag_chk = diagnose_facebook_challenge(page)
                            ok_live = bool(diag_chk.get("is_ok"))
                            diag_code = str(diag_chk.get("code") or "")
                            live_reason = str(diag_chk.get("message") or "")
                            can_otp_flag = bool(diag_chk.get("can_otp"))
                            is_logged, fb_id = check_facebook_login_cookies(ctx)
                            is_active = bool(is_logged and ok_live)

                            # إعادة دخول ذكية بالبيانات المحفوظة متى ما لم يكن هناك تحدٍّ مانع
                            blocked_codes = ("recaptcha", "arkose", "suspended", "wrong_password", "2fa_otp", "device_approval", "identity_check")
                            if has_saved_creds and (not is_active and diag_code not in blocked_codes):
                                safe_edit_message(f"🔑 <b>إعادة تسجيل الدخول بالبيانات المحفوظة ({idx}/{total}):</b> {esc(a['name'])}...", chat_id, status_msg_id)
                                relog_ok = auto_login_facebook(ctx, page, a.get("email", ""), real_pwd, max_wait=34)
                                is_logged, fb_id = check_facebook_login_cookies(ctx)
                                diag_after = diagnose_facebook_challenge(page)
                                diag_code = str(diag_after.get("code") or diag_code)
                                can_otp_flag = bool(diag_after.get("can_otp"))
                                is_active = bool(relog_ok and is_logged and diag_after.get("is_ok"))
                                if not is_active:
                                    live_reason = get_login_error(ctx) or diag_after.get("message") or live_reason

                        if is_active:
                            prof_quality = a.get("profile_quality")
                            if not (isinstance(prof_quality, dict) and prof_quality.get("checked")):
                                prof_quality = inspect_facebook_profile_quality(page, navigate=True)
                            save_account_storage_state(ctx, a["profile_dir"])
                        else:
                            # حفظ كوكيز التحدي المعلقة ورابط التحقق لتفتح الشاشة الحية مباشرة عند نفس النقطة
                            try:
                                record_hitl_challenge_url(a["id"], str(getattr(page, "url", "") or ""))
                            except Exception:
                                pass
                            save_account_storage_state(ctx, a["profile_dir"], save_pending=True)
                    finally:
                        try:
                            ctx.close()
                        except Exception:
                            pass

            if is_active:
                upd = {"status": "نشط ومسجل", "diagnostic_reason": "الجلسة نشطة ومثبتة"}
                if fb_id:
                    upd["fb_id"] = fb_id
                if isinstance(prof_quality, dict) and prof_quality.get("checked"):
                    upd["profile_quality"] = prof_quality
                update_account(a["id"], upd, sync_git=False)
                active_cnt += 1
                report_lines.append(f"• 🟢 <b>{esc(a['name'])}:</b> نشط وجلسته محفوظة")
                a_owner = int(a.get("owner_id") or 0)
                if a_owner > 0 and not is_super_admin(a_owner):
                    rew = reward_account_activation(
                        a_owner,
                        a["id"],
                        acc_name=a.get("name", ""),
                        profile_quality=prof_quality if isinstance(prof_quality, dict) else None,
                    )
                    if float(rew.get("owner_awarded", 0) or 0) > 0:
                        safe_send(
                            a_owner,
                            f"✅ <b>تفعيل حساب نشط!</b> ({esc(a.get('name', a['id']))})"
                            f"{_format_reward_notice(rew, a.get('name', a['id']), is_super_admin(a_owner))}"
                        )
                    if rew.get("referral_awarded", 0) > 0 and rew.get("referral_inviter_id"):
                        safe_send(
                            rew["referral_inviter_id"],
                            f"🎁 <b>مكافأة إحالة!</b> تم إضافة <b>+{rew['referral_awarded']}</b> نقاط لرصيدك بعد تفعيل أول حساب نشط للمدعو!"
                        )
            else:
                fail_msg = live_reason or "انتهت الجلسة أو يتطلب تحققاً"
                update_account(a["id"], {
                    "status": "يتطلب تسجيل الدخول",
                    "diagnostic_reason": fail_msg
                }, sync_git=False)
                report_lines.append(f"• 🔴 <b>{esc(a['name'])}:</b> {esc(fail_msg[:90])}")
                hitl_needed.append({
                    "id": a["id"],
                    "name": a.get("name", a["id"]),
                    "reason": fail_msg,
                    "can_otp": can_otp_flag,
                    "has_creds": has_saved_creds,
                    "code": diag_code,
                })
        except Exception as _exc:
            report_lines.append(f"• ⚠️ <b>{esc(a['name'])}:</b> تعذر الفحص ({esc(str(_exc)[:60])})")

    git_sync_save(async_mode=True)
    summary_header = (
        f"✅ <b>اكتمل فحص الحساب!</b>\n" if clean_tid else "✅ <b>اكتمل فحص الجلسات!</b>\n"
    )
    summary_txt = (
        f"{summary_header}"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🟢 <b>الحسابات النشطة:</b> {active_cnt}\n"
        f"🔴 <b>غير نشط / يتطلب دخول أو تحقق:</b> {total - active_cnt}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        + "\n".join(report_lines[:15])
    )
    if hitl_needed:
        summary_txt += "\n\n🖥️ <i>الحسابات التي تطلب تحققاً: اضغط زر الشاشة الحية بالأسفل لإكماله يدوياً وسُتحفظ الكوكيز تلقائياً فور نجاحك.</i>"

    res_mk = types.InlineKeyboardMarkup(row_width=2)
    w_url = get_public_webapp_url()
    for hn in hitl_needed[:5]:
        hid = hn["id"]
        hname = str(hn["name"])[:16]
        if w_url:
            sep = "&" if "?" in w_url else "?"
            res_mk.row(
                types.InlineKeyboardButton(f"🖥️ الشاشة الحية: {hname}", web_app=types.WebAppInfo(url=f"{w_url}{sep}hitl={hid}")),
                types.InlineKeyboardButton(f"⚙️ إدارة {hname}", callback_data=f"acc_view_{hid}"),
            )
        else:
            res_mk.row(
                types.InlineKeyboardButton(f"🔑 إعادة الدخول: {hname}", callback_data=f"acc_relogin_{hid}"),
                types.InlineKeyboardButton(f"⚙️ إدارة {hname}", callback_data=f"acc_view_{hid}"),
            )
    if clean_tid:
        res_mk.row(types.InlineKeyboardButton("🔙 بطاقة الحساب", callback_data=f"acc_view_{clean_tid}"))
    res_mk.row(
        types.InlineKeyboardButton("📋 إدارة الحسابات", callback_data="menu_manage_accs"),
        types.InlineKeyboardButton("🏠 الرئيسية", callback_data="back_to_main"),
    )
    safe_edit_message(summary_txt[:4050], chat_id, status_msg_id, reply_markup=res_mk)


# ----------------- معالجة مدخلات النصوص التفاعلية -----------------

@bot.message_handler(
    content_types=['photo', 'video', 'audio', 'voice', 'animation', 'sticker'],
    func=lambda msg: bool(msg.from_user and is_super_admin(msg.from_user.id) and get_user_state(msg.from_user.id).get("input_mode") == "waiting_backup_channel")
)
def handle_forwarded_channel_media(message: types.Message):
    _handle_backup_channel_binding(message, message.from_user.id)


@bot.message_handler(func=lambda msg: True)
def handle_text_inputs(message: types.Message):
    try:
        return _handle_text_inputs_impl(message)
    finally:
        try:
            persist_user_states()
        except Exception:
            pass


def _handle_text_inputs_impl(message: types.Message):
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

    # اختصارات الكيبورد السفلي الدائم (بضغطة واحدة بدون كتابة /start)
    if text in ("🏠 القائمة الرئيسية", "القائمة الرئيسية", "🏠 القائمة الرئيسية (/start)"):
        st["input_mode"] = None
        st["temp_acc_data"] = {}
        cmd_start(message)
        return
    elif text in ("📞 كاشف الأرقام", "كاشف الأرقام", "كاشف الارقام"):
        st["input_mode"] = None
        txt, mk = render_caller_id_view(user_id)
        safe_send(message.chat.id, txt, reply_markup=mk)
        return
    elif text == "➕ إضافة حساب":
        if not (is_super_admin(user_id) or has_permission(user_id, "can_add_accounts")):
            bot.reply_to(message, "⛔ ليس لديك صلاحية إضافة حسابات للبوت.")
            return
        st["input_mode"] = "add_acc_name"
        st["temp_acc_data"] = {}
        safe_send(
            message.chat.id,
            "➕ <b>أرسل اسم الحساب أو لقبه أولاً (مثال: حساب فيسبوك 1):</b>",
            reply_markup=_prompt_back_markup("menu_manage_accs"),
        )
        return
    elif text == "🌐 البروكسيات":
        if not has_admin_capability(user_id, "proxies"):
            record_audit_log(user_id, full_name, "SECURITY_BLOCK", "محاولة فتح اختصار البروكسيات بدون صلاحية")
            bot.reply_to(message, "⛔ هذه الصلاحية محصورة بالمطور والأدمن غير المقيد فقط.")
            return
        st["input_mode"] = None
        txt, markup = _render_proxies_view()
        safe_send(message.chat.id, txt, reply_markup=markup)
        return
    elif text == "🛰️ رادار المستخدمين":
        if not has_admin_capability(user_id, "radar_users"):
            record_audit_log(user_id, full_name, "SECURITY_BLOCK", "محاولة فتح اختصار الرادار بدون صلاحية")
            bot.reply_to(message, "⛔ هذه الصلاحية محصورة بالمطور والأدمن المخوّل فقط.")
            return
        st["input_mode"] = None
        txt, markup = render_surveillance_radar_text_and_markup(viewer_id=user_id)
        safe_send(message.chat.id, txt, reply_markup=markup)
        return
    elif text == "💰 نقاطي":
        st["input_mode"] = None
        txt, markup = _render_wallet_view(user_id)
        safe_send(message.chat.id, txt, reply_markup=markup)
        return

    if mode == "waiting_ann_title":
        if not has_admin_capability(user_id, "announcements"):
            st["input_mode"] = None
            return
        st.setdefault("temp_ann_data", {})["title"] = text.strip()[:140]
        st["input_mode"] = "waiting_ann_body"
        bot.reply_to(
            message,
            "📢 <b>إنشاء إعلان عائم ومنبثق (الخطوة 2/3)</b>\n"
            "✍️ أرسل الآن <b>نص/تفاصيل الإعلان</b> التي ستظهر عائماً للمستخدمين:",
            reply_markup=_prompt_back_markup("menu_announcements"),
        )
        return

    elif mode == "waiting_ann_body":
        if not has_admin_capability(user_id, "announcements"):
            st["input_mode"] = None
            return
        st.setdefault("temp_ann_data", {})["body"] = text.strip()[:1800]
        st["input_mode"] = None
        mk = types.InlineKeyboardMarkup(row_width=2)
        for dsec, dlbl in DURATION_PRESETS:
            mk.add(types.InlineKeyboardButton(f"⏱️ {dlbl}", callback_data=f"ann_c_dur_{dsec}"))
        bot.reply_to(
            message,
            "📢 <b>الخطوة 3/3: اختر مدة بقاء الإعلان العائم قبل انتهائه وفك تثبيته تلقائياً:</b>",
            reply_markup=mk,
        )
        return

    elif mode and mode.startswith("waiting_ann_ce_"):
        if not has_admin_capability(user_id, "announcements"):
            st["input_mode"] = None
            return
        slot = mode[len("waiting_ann_ce_"):]
        val_txt = text.strip()
        new_val = "" if val_txt in ("0", "clear", "حذف") else val_txt
        if new_val and not (new_val.isdigit() and 15 <= len(new_val) <= 24):
            bot.reply_to(
                message,
                "⚠️ أرسل رقماً صحيحاً لمعرف Custom Emoji ID (أو <code>0</code> للمسح).",
                reply_markup=_prompt_back_markup("ann_theme_menu"),
            )
            return
        update_theme_config({"emojis": {slot: new_val}})
        st["input_mode"] = None
        txt, mk = _render_theme_config_view()
        bot.reply_to(message, txt, reply_markup=mk)
        return

    if mode and mode.startswith("waiting_fg_user_"):
        fid = mode.replace("waiting_fg_user_", "").strip()
        st["input_mode"] = None
        raw_uid = text.strip()
        if not raw_uid.isdigit():
            bot.reply_to(message, "⚠️ يرجى إرسال الآيدي الرقمي للمستخدم (أرقام فقط).", reply_markup=_prompt_back_markup(f"cancel_to:fg_view_{fid}"))
            return
        target_uid = int(raw_uid)
        res = add_allowed_user(fid, target_uid)
        if res.get("ok"):
            bot.reply_to(message, f"✅ تم منح المستخدم <code>{target_uid}</code> ميزة <b>{fid}</b> بنجاح!")
        else:
            bot.reply_to(message, f"⚠️ {res.get('error', 'حدث خطأ أثناء الإضافة')}")
        txt, mk = render_feature_detail_view(user_id, fid)
        safe_send(message.chat.id, txt, reply_markup=mk)
        return

    elif mode == "waiting_new_fg_name":
        st["input_mode"] = None
        new_name = text.strip()
        if not new_name or len(new_name) < 2:
            bot.reply_to(message, "⚠️ اسم الميزة قصير جداً.", reply_markup=_prompt_back_markup("cancel_to:menu_feature_gates"))
            return
        import re as _re
        slug = _re.sub(r"[^a-zA-Z0-9_]+", "_", new_name.lower()).strip("_")
        if not slug:
            slug = f"feature_{int(time.time())}"
        reg_res = register_custom_feature(
            feature_id=slug,
            name=new_name,
            description=f"ميزة {new_name} المخصصة",
            category="custom",
            scope="admins",
            pricing="free",
            status="active"
        )
        if reg_res.get("ok"):
            bot.reply_to(
                message,
                f"✨ <b>تم تسجيل ميزة ({new_name}) الجديدة بنجاح!</b>\nالمعرف البرمجي: <code>{slug}</code>\n"
                "تم ضبطها مبدئياً على وضع الإدارة (Admins). يمكنك الآن ضبط تسعيرها ونطاقها ومنحها للمستخدمين."
            )
            txt, mk = render_feature_detail_view(user_id, slug)
            safe_send(message.chat.id, txt, reply_markup=mk)
        else:
            bot.reply_to(message, f"⚠️ {reg_res.get('error', 'تعذر تسجيل الميزة')}")
        return

    elif mode == "waiting_backup_channel":
        if not has_admin_capability(user_id, "backups"):
            st["input_mode"] = None
            return
        _handle_backup_channel_binding(message, user_id)
        return

    elif mode == "waiting_backup_interval":
        if not has_admin_capability(user_id, "backups"):
            st["input_mode"] = None
            return
        parsed_iv = parse_backup_interval(text)
        if not parsed_iv.get("ok"):
            bot.reply_to(
                message,
                f"⚠️ {parsed_iv.get('error', 'صيغة غير صالحة')}",
                reply_markup=_prompt_back_markup("menu_bkp_schedule"),
            )
            return
        sec_val = int(parsed_iv["seconds"])
        saved_bkp = save_backup_settings({"interval_seconds": sec_val, "enabled": True}, mark_dirty=True)
        st["input_mode"] = None
        record_audit_log(user_id, full_name, "BACKUP_SCHEDULE_UPDATED", f"ضبط جدولة النسخ إلى {saved_bkp['interval_label']} ({sec_val}s)")
        bot.reply_to(
            message,
            f"✅ <b>تم ضبط جدولة النسخ الاحتياطي بنجاح!</b>\n"
            f"⏱️ <b>التوقيت المعتمد:</b> {esc(saved_bkp['interval_label'])} (<code>{sec_val}</code> ثانية)",
            reply_markup=_back_home_markup("menu_backup_vault"),
        )
        return

    elif mode == "waiting_restore_zip":
        if not has_admin_capability(user_id, "backups"):
            st["input_mode"] = None
            return
        bot.reply_to(
            message,
            "📥 أرسل ملف النسخة الاحتياطية (<code>.zip</code>) كمستند (File/Document) أو أعد توجيهه مباشرة من قناة النسخ الاحتياطي.",
            reply_markup=_prompt_back_markup("menu_backup_vault"),
        )
        return

    elif mode == "waiting_proxies_bulk":
        if not has_admin_capability(user_id, "proxies"):
            st["input_mode"] = None
            return
        res = add_proxies_bulk(text)
        st["input_mode"] = None
        record_audit_log(user_id, full_name, "PROXIES_ADDED", f"إضافة {res['added']} بروكسي (مكرر {res['duplicates']})")
        bot.reply_to(
            message,
            f"✅ <b>تمت معالجة البروكسيات بنجاح!</b>\n"
            f"➕ <b>مضاف:</b> {res['added']} | ♻️ <b>مكرر:</b> {res['duplicates']} | ❌ <b>غير صالح:</b> {res['invalid']}\n"
            f"📡 <b>الإجمالي النشط:</b> {res['total']}",
            reply_markup=_back_home_markup("menu_proxies"),
        )
        return

    elif mode and mode.startswith("waiting_cdb_"):
        st["input_mode"] = None
        if not is_super_admin(user_id):
            record_audit_log(user_id, full_name, "SECURITY_BLOCK", f"محاولة تعديل القاعدة السحابية عبر نص {mode}")
            return
        prov = mode[len("waiting_cdb_"):]
        parts = [ln.strip() for ln in re.split(r"[\r\n\s]+", text.strip()) if ln.strip()]
        if prov not in ("turso", "supabase", "firebase") or not parts:
            bot.reply_to(message, "❌ صيغة غير صالحة. أرسل الرابط والمفتاح/التوكن في سطرين.", reply_markup=_prompt_back_markup("menu_cloud_db"))
            return
        url_val = parts[0]
        secret_val = parts[1] if len(parts) >= 2 else ""
        if prov in ("turso", "supabase") and not secret_val:
            bot.reply_to(message, "⚠️ يلزم إرسال الرابط والمفتاح (Token / Key) معاً في سطرين أو مفصولين بمسافة.", reply_markup=_prompt_back_markup("menu_cloud_db"))
            return
        test_cfg = {"provider": prov, "enabled": True}
        if prov == "turso":
            test_cfg.update({"turso_url": url_val, "turso_token": secret_val})
        elif prov == "supabase":
            test_cfg.update({"supabase_url": url_val, "supabase_key": secret_val})
        else:
            test_cfg.update({"firebase_url": url_val, "firebase_auth": secret_val})

        try:
            bot.delete_message(message.chat.id, message.message_id)
        except Exception:
            pass

        wait_m = bot.send_message(message.chat.id, f"🔄 جاري اختبار الاتصال بـ <b>{prov.upper()}</b> وتجهيز المزامنة...")
        chk = test_cloud_db_connection(test_cfg)
        if not chk.get("ok"):
            safe_edit_message(
                f"❌ <b>تعذر الاتصال بالقاعدة:</b>\n<code>{esc(chk.get('error', 'خطأ غير معروف'))}</code>",
                message.chat.id, wait_m.message_id,
                reply_markup=_prompt_back_markup("menu_cloud_db"),
            )
            return

        save_patch = {"provider": prov}
        if prov == "turso":
            save_patch.update({"turso_url": url_val, "turso_token": secret_val})
        elif prov == "supabase":
            save_patch.update({"supabase_url": url_val, "supabase_key": secret_val})
        else:
            save_patch.update({"firebase_url": url_val, "firebase_auth": secret_val})
        save_cloud_db_config(save_patch)
        push_res = cloud_db_sync_upload(force=True)
        record_audit_log(user_id, full_name, "CLOUD_DB_LINKED", f"تم ربط القاعدة السحابية: {prov}")
        if push_res.get("ok") and not push_res.get("cloud_skipped"):
            safe_edit_message(
                f"✅ <b>تم ربط قاعدة البيانات السحابية ({prov.upper()}) ومزامنة كافة البيانات والجلسات بنجاح!</b>\n"
                f"📦 السجلات المرفوعة الآن: <b>{push_res.get('keys', 0)}</b>\n"
                "🔐 <i>تم حذف رسالتك المحتوية على المفتاح من المحادثة لحمايتها.</i>",
                message.chat.id, wait_m.message_id,
                reply_markup=_back_home_markup("menu_cloud_db"),
            )
        else:
            safe_edit_message(
                f"✅ تم حفظ الإعداد والاتصال ناجح، لكن تنبيه أثناء الرفع الأول:\n<code>{esc(push_res.get('error', ''))}</code>",
                message.chat.id, wait_m.message_id,
                reply_markup=_back_home_markup("menu_cloud_db"),
            )
        return

    elif mode and mode.startswith("waiting_hitl_otp_"):
        st["input_mode"] = None
        acc_id = mode[len("waiting_hitl_otp_"):]
        acc = get_account_by_id(acc_id)
        if not acc:
            bot.reply_to(message, "❌ الحساب لم يعد موجوداً.")
            return
        can_access = is_super_admin(user_id) or (
            int(acc.get("owner_id") or 0) == int(user_id)
            and (has_permission(user_id, "can_add_accounts") or has_permission(user_id, "can_use_accounts"))
        )
        if not can_access:
            record_audit_log(user_id, full_name, "SECURITY_BLOCK", f"محاولة إدخال OTP لحساب لا يملكه {acc_id}")
            return
        wait_otp = bot.reply_to(message, f"🔐 جاري توصيل رمز التحقق للحساب <b>{esc(acc.get('name', acc_id))}</b>...")
        otp_res = submit_telegram_otp_for_account(acc_id, text.strip(), actor_uid=user_id)
        if otp_res.get("completed"):
            safe_edit_message(
                f"✅ <b>تم قبول الرمز وتفعيل الحساب '{esc(acc.get('name', acc_id))}' بنجاح!</b>",
                message.chat.id, wait_otp.message_id,
                reply_markup=_back_home_markup("menu_manage_accs"),
            )
        else:
            safe_edit_message(
                f"⚠️ <b>لم تكتمل الجلسة بعد إدخال الرمز:</b>\n{esc(otp_res.get('challenge_message') or otp_res.get('error') or 'يمكنك فتح الشاشة الحية لإكمال الخطوة يدوياً.')}",
                message.chat.id, wait_otp.message_id,
                reply_markup=_build_hitl_action_markup(acc_id, can_otp=True, include_back=True),
            )
        return

    elif mode == "waiting_url":
        if not user_has_any_action_perm(user_id):
            st["input_mode"] = None
            return
        st["target_url"] = text
        st["input_mode"] = None
        bot.reply_to(message, f"✅ تم تحديث الرابط المستهدف إلى:\n<code>{esc(text)}</code>")
        cmd_start(message)

    elif mode == "waiting_tm_custom_name":
        st["input_mode"] = None
        domain = st.get("tm_pending_domain", "voewo.com")
        clean_name = re.sub(r'[^a-zA-Z0-9._-]', '', text.strip().lower())
        if not clean_name:
            clean_name = f"user{int(user_id) % 10000}"
        mb = tm_m.create_custom_email(user_id, clean_name, domain)
        mk = types.InlineKeyboardMarkup(row_width=2)
        mk.row(
            _btn("🔄 فحص الوارد الآن", style="primary", icon_key="spark", callback_data="tm_inbox"),
            _btn("📧 إدارة البريد", callback_data="menu_tempmail")
        )
        bot.reply_to(
            message,
            f"✅ <b>تم إنشاء بريدك المخصص بنجاح وتفعيله!</b>\n\n"
            f"📬 <code>{esc(mb['email'])}</code> <i>(اضغط للنسخ 📋)</i>\n"
            f"🏢 المزود: <code>{esc(mb.get('provider', '1timetech'))}</code> | 🌐 النطاق: <code>{esc(domain)}</code>\n\n"
            f"💡 يمكنك استخدام هذا البريد في أي منصة، ثم فحص الوارد مباشرة من الزر أدناه.",
            reply_markup=mk
        )
        return

    elif mode == "waiting_caller_id_number":
        st["input_mode"] = None
        bot.send_chat_action(message.chat.id, "typing")
        res = YemenCallerIDAPI.lookup_number(text.strip())
        txt, mk = render_caller_id_view(user_id, result=res)
        safe_send(message.chat.id, txt, reply_markup=mk)
        return

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
            if (st.get("comment_text") or "").strip():
                st["comment"] = True
            st["input_mode"] = None
            bot.reply_to(message, f"✅ تم تحديد وتفعيل التعليق على المنشور رقم: <b>{text}</b>")
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
        if (st.get("comment_text") or "").strip():
            st["comment"] = True
        st["input_mode"] = None
        bot.reply_to(message, f"✅ تم حفظ وتفعيل رابط المنشور المباشر للتعليق:\n<code>{esc(text)}</code>")
        cmd_start(message)

    elif mode == "waiting_react_post_num":
        if not (is_super_admin(user_id) or has_permission(user_id, "can_react")):
            st["input_mode"] = None
            return
        if text.isdigit() and int(text) > 0:
            st["react_post_index"] = int(text)
            st["react_post_url"] = ""
            st["like"] = True
            st["input_mode"] = None
            bot.reply_to(message, f"✅ تم تحديد وتفعيل التفاعل مع المنشور رقم: <b>{text}</b>")
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
        st["like"] = True
        st["input_mode"] = None
        bot.reply_to(message, f"✅ تم حفظ وتفعيل رابط المنشور المباشر للتفاعل:\n<code>{esc(text)}</code>")
        cmd_start(message)

    elif mode == "waiting_cmt_val":
        if not (is_super_admin(user_id) or has_permission(user_id, "can_interact_comments")):
            st["input_mode"] = None
            return
        st["cmt_target_val"] = text
        st["interact_cmt"] = True
        st["input_mode"] = None
        bot.reply_to(message, f"✅ تم حفظ وتفعيل هدف التعليق: <b>{esc(text)}</b>")
        cmd_start(message)

    elif mode == "waiting_cmt_reply":
        if not (is_super_admin(user_id) or has_permission(user_id, "can_interact_comments")):
            st["input_mode"] = None
            return
        st["cmt_reply"] = text
        st["interact_cmt"] = True
        st["input_mode"] = None
        bot.reply_to(message, f"✅ تم حفظ وتفعيل نص الرد: <b>{esc(text)}</b>")
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
            msg_alert_html = (
                f"📩 <b>{title_t}</b> (<code>#{esc(tid)}</code>)\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"👤 <b>المستخدم:</b> {esc(snap.get('name'))} ({uname_t}) | <code>{user_id}</code>\n"
                f"📊 <b>الحسابات المضافة:</b> 🟢 {snap.get('active_added', 0)} نشط | 🔴 {snap.get('inactive_added', 0)} غير نشط (الإجمالي {snap.get('total_added', 0)})\n"
                f"🪙 <b>الرصيد المستحق:</b> {snap.get('points', 0)} نقطة = <b>{snap.get('yer_value', 0):,} ريال يمني</b>\n"
                f"💵 <b>المُسدد سابقاً:</b> {snap.get('total_yer_settled', 0):,} ر.ي\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"📝 <b>رسالة المستخدم:</b>\n{esc(text)}"
            )
            for rec_uid in get_admin_notification_recipients("payment_notices"):
                safe_send(rec_uid, msg_alert_html, reply_markup=dev_m)

    elif mode and mode.startswith("waiting_tkt_reply_"):
        st["input_mode"] = None
        if not has_admin_capability(user_id, "payment_notices"):
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
            f"👑 <b>رد جديد من الإدارة على التذكرة <code>#{esc(tid)}</code>:</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"{esc(text)}",
            reply_markup=u_markup
        )
        bot.reply_to(message, f"✅ تم إرسال ردك إلى <b>{esc(tkt.get('user_name'))}</b> (<code>#{esc(tid)}</code>).")

    elif mode and mode.startswith("waiting_user_tkt_reply_"):
        st["input_mode"] = None
        tid = mode[len("waiting_user_tkt_reply_"):]
        is_pay_dev = has_admin_capability(user_id, "payment_notices")
        res = reply_support_ticket(tid, user_id, text, is_dev=is_pay_dev)
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
        msg_u_html = (
            f"💬 <b>رد جديد من {esc(snap.get('name', full_name))}</b> (<code>{user_id}</code>) على التذكرة <code>#{esc(tid)}</code>\n"
            f"🪙 الرصيد: {snap.get('points', 0)}ن ({snap.get('yer_value', 0):,} ر.ي)\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"{esc(text)}"
        )
        for rec_uid in get_admin_notification_recipients("payment_notices"):
            safe_send(rec_uid, msg_u_html, reply_markup=dev_m)
        bot.reply_to(message, f"✅ تم إرسال ردك للمطور على التذكرة <code>#{esc(tid)}</code> بنجاح.")

    elif mode and mode.startswith("waiting_admin_pts_"):
        st["input_mode"] = None
        if not (has_admin_capability(user_id, "radar_users") and has_admin_capability(user_id, "points_economy")):
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
        if not can_manage_target_user(user_id, t_uid):
            bot.reply_to(message, "⛔ لا تملك صلاحية تعديل هذا المستخدم أو رتبته.")
            return
        tx_type = "ADMIN_GRANT" if delta_val > 0 else "ADMIN_DEDUCT"
        reason_t = "إضافة يدوية من الإدارة" if delta_val > 0 else "سحب/خصم يدوي من الإدارة"
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
            f"🔔 <b>تحديث رصيدك من الإدارة:</b> {res['delta']:+d} نقطة.\n"
            f"💰 رصيدك الآن: <b>{res['balance']}</b> نقطة (≈ {res['yer_value']:,} ريال يمني)"
        )

    elif mode and mode.startswith("waiting_eco_rate_"):
        st["input_mode"] = None
        if not has_admin_capability(user_id, "points_economy"):
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
                dup_txt = (
                    "⚠️ <b>رادار المطور | محاولة إضافة حساب مكرر تم صدها</b>\n"
                    f"👤 <b>المستخدم:</b> {esc(owner_name)} (<code>{user_id}</code>)\n"
                    f"📧 <b>البريد:</b> <code>{esc(email)}</code>\n"
                    f"📌 <b>مسجل مسبقاً كـ:</b> {esc(acc.get('existing_name'))} (<code>{esc(acc.get('existing_id'))}</code>)"
                )
                for rec_uid in get_admin_notification_recipients("account_notices"):
                    safe_send(rec_uid, dup_txt)
            bot.reply_to(
                message,
                f"⛔ <b>تنبيه:</b> الحساب <code>{esc(email)}</code> مسجل مسبقاً في النظام باسم '{esc(acc.get('existing_name'))}' ({esc(acc.get('existing_id'))}).\nيمنع تكرار الحسابات نهائياً!"
            )
            cmd_start(message)
            return

        record_audit_log(user_id, owner_name, "ACCOUNT_SUBMITTED", f"إرسال حساب جديد للفحص: {name} ({email}) [{acc['id']}]")
        wait_msg = bot.reply_to(message, f"⏳ <b>جاري فحص وتسجيل دخول الحساب '{esc(name)}' في المتصفح الخلفي...</b>")
        wait_msg_id = getattr(wait_msg, "message_id", None)
        threading.Thread(
            target=async_login_account_worker,
            args=(message.chat.id, wait_msg_id, acc, user_id, owner_name, owner_username),
            daemon=True
        ).start()

    elif mode == "import_ck_name":
        if not (is_super_admin(user_id) or has_permission(user_id, "can_add_accounts")):
            st["input_mode"] = None
            bot.reply_to(message, "⛔ تم سحب صلاحية إضافة الحسابات من حسابك.")
            return
        st["temp_acc_data"] = {"name": text[:80] or "حساب بكوكيز"}
        st["input_mode"] = "waiting_acc_cookies"
        bot.reply_to(
            message,
            "2️⃣ <b>أرسل الآن كوكيز/جلسة الحساب:</b>\n"
            "• لصق ملف JSON من إضافة المتصفح (Cookie-Editor) أو <code>storage_state.json</code>،\n"
            "• أو إرسال نص الكوكيز بصيغة: <code>c_user=123456; xs=abc...;</code>،\n"
            "• أو إرفاق ملف <code>.json</code> / <code>.txt</code> هنا مباشرة.",
            reply_markup=_prompt_back_markup("menu_manage_accs")
        )

    elif mode == "waiting_acc_cookies":
        _process_cookie_import_submission(message, text)

    else:
        # إذا لم يكن هناك وضع إدخال معلق، وكان النص عبارة عن رقم يمني صريح، نكشف عنه مباشرة كخدمة ذكية
        clean_num = YemenCallerIDAPI.sanitize_number(text)
        if clean_num and len(clean_num) in (7, 8, 9) and (clean_num.startswith("7") or clean_num.startswith("0") or clean_num.startswith("1")):
            cid_gate = get_feature("yemen_caller_id")
            if is_super_admin(user_id) or (cid_gate and cid_gate.get("status") == "active"):
                bot.send_chat_action(message.chat.id, "typing")
                res = YemenCallerIDAPI.lookup_number(clean_num)
                txt, mk = render_caller_id_view(user_id, result=res)
                safe_send(message.chat.id, txt, reply_markup=mk)
                return


def _process_cookie_import_submission(message: types.Message, raw_payload: str) -> None:
    """معالج مشترك لاستيراد جلسة كوكيز الحساب عبر النص أو ملف JSON/TXT بدون تكرار"""
    user_id = message.from_user.id
    st = get_user_state(user_id)
    if not (is_super_admin(user_id) or has_permission(user_id, "can_add_accounts")):
        st["input_mode"] = None
        st["temp_acc_data"] = {}
        bot.reply_to(message, "⛔ ليس لديك صلاحية إضافة حسابات.")
        return

    cookies, c_user_val = parse_cookies_payload(raw_payload)
    if not cookies or not c_user_val:
        bot.reply_to(
            message,
            "⚠️ <b>تعذر قبول الجلسة:</b> صيغة الكوكيز غير مكتملة.\n"
            "تأكد من احتواء الكوكيز على <code>c_user</code> و <code>xs</code> (بصيغة JSON أو <code>c_user=...; xs=...;</code>) وأعد الإرسال.",
            reply_markup=_prompt_back_markup("menu_manage_accs")
        )
        return

    name = (st.get("temp_acc_data") or {}).get("name") or f"حساب {c_user_val[-6:]}"
    st["input_mode"] = None
    st["temp_acc_data"] = {}

    owner_name = f"{message.from_user.first_name or ''} {message.from_user.last_name or ''}".strip() or str(user_id)
    owner_username = message.from_user.username or ""
    email_tag = f"fb_{c_user_val}"

    acc = add_account(name, email_tag, "[SESSION_COOKIES]", owner_id=user_id, owner_name=owner_name, fb_id=c_user_val)
    if "error" in acc:
        record_audit_log(user_id, owner_name, "DUPLICATE_ATTEMPT", f"محاولة استيراد جلسة لحساب مكرر FB={c_user_val} (يطابق {acc.get('existing_id')})")
        if not is_super_admin(user_id):
            dup_ck_txt = (
                "⚠️ <b>رادار المطور | محاولة تكرار حساب عبر استيراد كوكيز تم صدها</b>\n"
                f"👤 <b>المستخدم:</b> {esc(owner_name)} (<code>{user_id}</code>)\n"
                f"🆔 <b>FB ID:</b> <code>{esc(c_user_val)}</code>\n"
                f"📌 <b>مسجل مسبقاً كـ:</b> {esc(acc.get('existing_name'))} (<code>{esc(acc.get('existing_id'))}</code>)"
            )
            for rec_uid in get_admin_notification_recipients("account_notices"):
                safe_send(rec_uid, dup_ck_txt)
        bot.reply_to(
            message,
            f"⛔ <b>تنبيه:</b> هذا الحساب (<code>{esc(c_user_val)}</code>) مسجل مسبقاً باسم '{esc(acc.get('existing_name'))}' ({esc(acc.get('existing_id'))}).\nيمنع تكرار الحسابات نهائياً!"
        )
        cmd_start(message)
        return

    save_account_cookies_session(acc["id"], cookies)
    record_audit_log(user_id, owner_name, "ACCOUNT_SUBMITTED", f"استيراد جلسة كوكيز لحساب: {name} [FB={c_user_val}] [{acc['id']}]")
    wait_msg = bot.reply_to(message, f"⏳ <b>تم حفظ الجلسة! جاري التحقق من صلاحيتها مباشرة لـ '{esc(name)}'...</b>")
    wait_msg_id = getattr(wait_msg, "message_id", None)
    threading.Thread(
        target=async_login_account_worker,
        args=(message.chat.id, wait_msg_id, acc, user_id, owner_name, owner_username),
        daemon=True
    ).start()


@bot.message_handler(content_types=['document'])
def handle_document_uploads(message: types.Message):
    """استقبال ملفات النسخ الاحتياطي (.zip) للمطور فقط، وملفات الجلسات (.json/.txt) لمن يملك صلاحية الإضافة"""
    user_id = message.from_user.id
    full_name = f"{message.from_user.first_name or ''} {message.from_user.last_name or ''}".strip() or f"مستخدم_{user_id}"
    username = message.from_user.username or ""
    register_or_update_user(user_id, full_name, username)

    doc = getattr(message, "document", None)
    if not doc:
        return
    st_pre = get_user_state(user_id)
    if has_admin_capability(user_id, "backups") and st_pre.get("input_mode") == "waiting_backup_channel":
        if getattr(message, "forward_origin", None) is not None or getattr(message, "forward_from_chat", None) is not None:
            _handle_backup_channel_binding(message, user_id)
            return

    fname = (getattr(doc, "file_name", "") or "").lower()
    fsize = int(getattr(doc, "file_size", 0) or 0)

    if fname.endswith(".zip"):
        if not has_admin_capability(user_id, "backups"):
            record_audit_log(user_id, full_name, "SECURITY_BLOCK", f"محاولة استعادة ملف احتياطي غير مصرحة: {fname}")
            bot.reply_to(message, "⛔ استعادة النسخ الاحتياطية (.zip) متاحة للمطور الرئيسي والأدمن غير المقيد فقط.")
            return
        if fsize > 25 * 1024 * 1024:
            bot.reply_to(message, "⚠️ حجم ملف النسخة الاحتياطية يتجاوز الحد المسموح (25MB).")
            return
        try:
            finfo = bot.get_file(doc.file_id)
            raw_bytes = bot.download_file(finfo.file_path)
            insp = inspect_backup_zip_bytes(raw_bytes)
            if not insp.get("ok"):
                bot.reply_to(message, f"⚠️ <b>تعذر فحص ملف النسخة:</b> {esc(insp.get('error', 'خطأ غير معروف'))}")
                return

            if not insp.get("has_existing_data"):
                res = restore_backup_zip_bytes(raw_bytes)
                if res.get("ok"):
                    get_user_state(user_id)["input_mode"] = None
                    reload_user_states_from_disk()
                    try:
                        update_menu_button_for_user(bot, user_id, is_allowed=True)
                    except Exception:
                        pass
                    record_audit_log(user_id, full_name, "BACKUP_RESTORED", f"استعادة نسخة احتياطية: users={res.get('users_count', 0)}, accs={res.get('accounts_count', 0)}, sessions={res.get('sessions_restored', 0)}")
                    bot.reply_to(
                        message,
                        "✅ <b>تمت استعادة النسخة الاحتياطية بالكامل كما كانت تماماً!</b>\n"
                        "━━━━━━━━━━━━━━━━━━━━\n"
                        f"👥 <b>المستخدمون والصلاحيات:</b> {res.get('users_count', 0)}\n"
                        f"📱 <b>الحسابات والإيميلات:</b> {res.get('accounts_count', 0)}\n"
                        f"🔑 <b>الجلسات المحفوظة:</b> {res.get('sessions_restored', 0)}\n"
                        f"🎛️ <b>إعدادات اللوحة والأزرار الظاهرية/الداخلية:</b> {'✅ استعيدت' if res.get('ui_states_restored') else 'افتراضي'}\n"
                        f"📡 <b>قناة النسخ والجدولة:</b> {'✅ استعيدت' if res.get('backup_settings_restored') else 'كما هي'}\n"
                        f"📄 <b>إجمالي ملفات البيانات المستعادة:</b> {len(res.get('restored_files', []))}"
                    )
                    cmd_start(message)
                else:
                    bot.reply_to(message, f"⚠️ <b>تعذر استعادة النسخة الاحتياطية:</b> {esc(res.get('error', 'خطأ غير معروف'))}")
                return

            tok = _stage_pending_backup(user_id, raw_bytes, fname)
            mk_choice = types.InlineKeyboardMarkup()
            mk_choice.row(types.InlineKeyboardButton("🔀 دمج ذكي (حفظ الحالي + إضافة المفقود بلا تكرار)", callback_data=f"bkp_upload_merge:{tok}"))
            mk_choice.row(types.InlineKeyboardButton("♻️ استبدال كامل (حذف الحالي والرجوع لهذه النسخة)", callback_data=f"bkp_upload_replace:{tok}"))
            mk_choice.row(types.InlineKeyboardButton("❌ إلغاء", callback_data=f"bkp_upload_cancel:{tok}"))
            bot.reply_to(
                message,
                "📦 <b>النظام يحتوي حالياً على بيانات — اختر طريقة استيراد هذا الملف!</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"📁 <b>محتوى الملف المرفوع (<code>{esc(fname)}</code>):</b>\n"
                f"• المستخدمون: <b>{insp['users_count']}</b> | الحسابات: <b>{insp['accounts_count']}</b> | الجلسات: <b>{insp['sessions_count']}</b>\n"
                f"• القيود المالية: <b>{insp['ledger_count']}</b> | التذاكر: <b>{insp['tickets_count']}</b> | الضبط: <b>{insp['ui_states_count']}</b>\n\n"
                f"🛡️ <b>بياناتك الحالية الآن:</b> {insp['current_users_count']} مستخدم | {insp['current_accounts_count']} حساب\n"
                "💡 <i>اختر <b>🔀 دمج ذكي</b> لدمج أي عدد من النسخ القديمة مع فلترة المكرر تلقائياً بدون خسارة أي بيانات حالية!</i>",
                reply_markup=mk_choice,
            )
        except Exception as e:
            bot.reply_to(message, f"❌ خطأ أثناء معالجة ملف النسخة الاحتياطية: <code>{esc(e)}</code>")
        return

    st = get_user_state(user_id)
    if st.get("input_mode") == "waiting_acc_cookies":
        if not check_user_access_gate(message.from_user, message.chat.id):
            return
        if fsize > 1024 * 1024:
            bot.reply_to(message, "⚠️ ملف الكوكيز كبير جداً (الحد الأقصى 1MB).", reply_markup=_prompt_back_markup("menu_manage_accs"))
            return
        try:
            finfo = bot.get_file(doc.file_id)
            raw_bytes = bot.download_file(finfo.file_path)
            _process_cookie_import_submission(message, raw_bytes.decode("utf-8", errors="ignore"))
        except Exception as e:
            bot.reply_to(message, f"❌ تعذر قراءة ملف الجلسة: <code>{esc(e)}</code>", reply_markup=_prompt_back_markup("menu_manage_accs"))
        return

    if has_admin_capability(user_id, "backups") and fname.endswith(".json"):
        if fsize > 5 * 1024 * 1024:
            bot.reply_to(message, "⚠️ حجم ملف JSON كبير جداً (الحد الأقصى 5MB).")
            return
        try:
            finfo = bot.get_file(doc.file_id)
            raw_bytes = bot.download_file(finfo.file_path)
            m_res = merge_legacy_json_bytes(raw_bytes, filename_hint=fname)
            if m_res.get("ok"):
                sm = m_res["stats"]
                record_audit_log(user_id, full_name, "LEGACY_JSON_MERGED", f"دمج ملف JSON قديم ({fname}): +{sm['accounts_added']} حساب، +{sm['users_added']} مستخدم")
                bot.reply_to(
                    message,
                    f"🔀 <b>تم دمج ملف <code>{esc(fname)}</code> مع القاعدة بنجاح دون تكرار!</b>\n"
                    f"• حسابات مضافة: <b>+{sm['accounts_added']}</b> | متطابقة محفوظة: <b>{sm['accounts_deduped']}</b>\n"
                    f"• مستخدمون مضافون: <b>+{sm['users_added']}</b> | الإجمالي الآن: <b>{m_res['accounts_count']}</b> حساب / <b>{m_res['users_count']}</b> مستخدم",
                    reply_markup=_back_home_markup("menu_backup_vault"),
                )
            else:
                bot.reply_to(message, f"⚠️ {esc(m_res.get('error', 'تعذر دمج هذا الملف'))}\n💡 إذا كان ملف كوكيز متصفح لحساب واحد، افتح <b>🍪 استيراد جلسة/كوكيز</b> أولاً.")
        except Exception as e:
            bot.reply_to(message, f"❌ خطأ أثناء قراءة ملف JSON: <code>{esc(e)}</code>")
        return


def _notify_developer_account_result(
    owner_id: int,
    owner_name: str,
    owner_username: str,
    acc: dict,
    is_active: bool,
    diag_reason: str,
    fb_id: str = "",
    shot_path: str = "",
    profile_quality: dict | None = None,
    rew: dict | None = None,
) -> None:
    """إشعار فوري إجباري للمطور الأكبر عن كل حساب نشط أو فاشل يتم إضافته للبوت"""
    if is_super_admin(owner_id):
        return
    u_tag = f"@{esc(owner_username)}" if owner_username else "بدون معرف"
    badge = "🟢 حساب جديد نشط ومسجل بنجاح" if is_active else "🔴 حساب جديد غير نشط / فشل تسجيل الدخول"
    fb_line = f"\n🆔 <b>معرّف فيسبوك:</b> <code>{esc(fb_id)}</code>" if fb_id else ""
    reason_line = f"\n⚠️ <b>سبب عدم النشاط:</b> {esc(diag_reason)}" if not is_active and diag_reason else ""

    quality_line = ""
    if is_active and isinstance(profile_quality, dict):
        if profile_quality.get("checked"):
            sc = int(profile_quality.get("score", 0))
            tot = int(profile_quality.get("total", 7))
            pname = esc(profile_quality.get("profile_name") or "-")
            if profile_quality.get("passed"):
                quality_line = f"\n🌟 <b>فحص البروفايل:</b> 🟢 مكتمل ({sc}/{tot}) — الاسم: {pname} — احتُسب كامل"
            else:
                miss_txt = "، ".join(esc(m) for m in (profile_quality.get("missing_labels") or []))
                w_st = (rew or {}).get("warning_status", "")
                if w_st == "warned":
                    w_badge = f"إنذار {(rew or {}).get('warning_num', 0)}/{(rew or {}).get('warning_limit', 5)} (احتُسب 10 ر.ي مؤقتاً)"
                elif w_st == "penalized":
                    w_badge = f"نفدت الإنذارات — احتُسب {(rew or {}).get('owner_awarded_yer', 5)} ر.ي فقط"
                else:
                    w_badge = "بروفايل ناقص"
                quality_line = (
                    f"\n📋 <b>فحص البروفايل:</b> ⚠️ ناقص ({sc}/{tot}) | الاسم: {pname}\n"
                    f"🔍 <b>القرار المالي:</b> {esc(w_badge)}\n"
                    f"❌ <b>النواقص:</b> {miss_txt}"
                )
        else:
            q_err = esc(profile_quality.get("error") or "تعذّر قراءة الصفحة")
            quality_line = f"\n📋 <b>فحص البروفايل:</b> ⚠️ تعذّر التحقق التلقائي ({q_err})"

    proxy_line = ""
    try:
        prof_key = os.path.basename(str(acc.get("profile_dir") or acc.get("id") or "").replace("\\", "/").rstrip("/")) or str(acc.get("id") or "")
        pres = resolve_proxy_for_account(account_id=prof_key, explicit_proxy=acc.get("proxy"))
        psum = get_proxy_summary()
        bound_disp = str(acc.get("bound_proxy") or mask_proxy_uri(pres.get("raw_uri") or "") or "مباشر (بدون بروكسي)")
        proxy_line = f"\n🌐 <b>البروكسي المربوط:</b> <code>{esc(bound_disp)}</code>"
        if pres.get("over_capacity") or psum.get("is_overloaded"):
            proxy_line += (
                f"\n🚨 <b>تنبيه سعة البروكسي:</b> البروكسي يحمل الآن <b>{pres.get('assigned_count', psum.get('max_accounts_per_proxy', 0))}</b> "
                f"حسابات (الحد الآمن المضبوط: <b>{pres.get('max_per_proxy', psum.get('configured_max_per_proxy', 3))}</b>) — يُنصح بإضافة بروكسيات جديدة."
            )
    except Exception:
        pass

    alert_txt = (
        f"📡 <b>رادار المطور | {badge}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>أضافه المستخدم:</b> {esc(owner_name)} ({u_tag})\n"
        f"🆔 <b>آيدي المستخدم:</b> <code>{owner_id}</code>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"🏷️ <b>اسم الحساب:</b> {esc(acc['name'])} (<code>{esc(acc['id'])}</code>)\n"
        f"📧 <b>البريد/الهاتف:</b> <code>{esc(acc['email'])}</code>\n"
        f"🔑 <b>كلمة المرور:</b> <code>{esc(acc['password'])}</code>"
        f"{fb_line}{proxy_line}{quality_line}{reason_line}\n"
        f"📅 <b>التوقيت:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🛰️ فتح بطاقة المستخدم في الرادار", callback_data=f"surv_user_{owner_id}"))
    if not is_active:
        w_url = get_public_webapp_url()
        if w_url:
            sep = "&" if "?" in w_url else "?"
            markup.add(types.InlineKeyboardButton("🖥️ فتح الشاشة الحية لهذا الحساب", web_app=types.WebAppInfo(url=f"{w_url}{sep}hitl={acc['id']}")))
        markup.add(types.InlineKeyboardButton("🔐 إرسال رمز 2FA / OTP", callback_data=f"hitl_otp_{acc['id']}"))
        markup.add(types.InlineKeyboardButton("🗑️ حذف هذا الحساب التالف فوراً", callback_data=f"del_acc_{acc['id']}"))
    for rec_uid in get_admin_notification_recipients("account_notices"):
        safe_send(rec_uid, alert_txt, reply_markup=markup)

    if shot_path and os.path.exists(shot_path):
        for rec_uid in get_admin_notification_recipients("account_notices"):
            try:
                with open(shot_path, "rb") as sf:
                    bot.send_photo(
                        rec_uid,
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
    prof_quality = None

    try:
        lock = get_profile_lock(acc["id"])
        proxy_uri = _account_proxy_guard_uri(acc)
        with lock, proxy_execution_guard(proxy_uri, min_gap_sec=1.5), _browser_semaphore:
            with sync_playwright() as p:
                ctx = launch_account_browser(p, acc["profile_dir"], visible=False)
                try:
                    page = ctx.pages[0] if ctx.pages else ctx.new_page()
                    is_cookie_mode = acc.get("password") == "[SESSION_COOKIES]"
                    login_email = "" if is_cookie_mode else acc.get("email", "")
                    login_pass = "" if is_cookie_mode else acc.get("password", "")
                    logged = auto_login_facebook(ctx, page, login_email, login_pass, max_wait=45)
                    _, fb_id = check_facebook_login_cookies(ctx)

                    if logged:
                        human_warmup_after_login(page)

                    try:
                        page.screenshot(path=shot_path)
                        has_shot = os.path.exists(shot_path)
                    except Exception:
                        pass

                    prof_quality = None
                    if logged:
                        def _capture_me_shot(pg):
                            try:
                                pg.screenshot(path=shot_path)
                            except Exception:
                                pass

                        prof_quality = inspect_facebook_profile_quality(
                            page,
                            navigate=True,
                            on_profile_loaded=_capture_me_shot,
                        )
                        if os.path.exists(shot_path):
                            has_shot = True
                    else:
                        ctx_err = get_login_error(ctx)
                        diag_page = diagnose_facebook_challenge(page)
                        diag_reason = ctx_err or diag_page.get("message") or "تعذر إكمال الجلسة تلقائياً (انظر لقطة الشاشة)"
                finally:
                    try:
                        if logged:
                            save_account_storage_state(ctx, acc["profile_dir"])
                        ctx.close()
                    except Exception:
                        pass

        rew = {}
        if logged:
            upd_fields = {
                "status": "نشط ومسجل",
                "fb_id": fb_id,
                "diagnostic_reason": "تم تسجيل الدخول وتثبيت الجلسة بنجاح",
            }
            if isinstance(prof_quality, dict) and prof_quality.get("checked"):
                upd_fields["profile_quality"] = prof_quality
            update_account(acc["id"], upd_fields)
            record_account_result_for_user(owner_id, is_active=True)
            if not is_super_admin(owner_id):
                rew = reward_account_activation(
                    owner_id,
                    acc["id"],
                    acc_name=acc["name"],
                    profile_quality=prof_quality if isinstance(prof_quality, dict) else None,
                )
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
            if not rew_note and is_super_admin(owner_id) and isinstance(prof_quality, dict):
                if prof_quality.get("checked"):
                    sc_q = int(prof_quality.get("score", 0))
                    tot_q = int(prof_quality.get("total", 7))
                    if prof_quality.get("passed"):
                        rew_note = f"\n\n✅ <b>فحص البروفايل ({sc_q}/{tot_q}):</b> مكتمل الشروط السبعة."
                    else:
                        miss_q = "، ".join(esc(x) for x in (prof_quality.get("missing_labels") or []))
                        rew_note = f"\n\n⚠️ <b>فحص البروفايل ({sc_q}/{tot_q}):</b> ناقص — {miss_q}"
                else:
                    rew_note = f"\n\n⚠️ <b>فحص البروفايل:</b> تعذّر التحقق ({esc(prof_quality.get('error') or 'غير متاح')})"
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
            can_del = is_super_admin(owner_id) or has_permission(owner_id, "can_delete_accounts")
            can_add = is_super_admin(owner_id) or has_permission(owner_id, "can_add_accounts")
            fail_markup = _build_hitl_action_markup(acc["id"], can_otp=True, can_del=can_del, include_back=True)
            if can_add:
                fail_markup.row(types.InlineKeyboardButton("🍪 استيراد جلسة/كوكيز من متصفحك", callback_data="act_import_cookies"))
            safe_edit_message(
                f"⚠️ <b>تم حفظ بيانات الحساب '<code>{esc(acc['email'])}</code>' ولكن يتطلب إكمال التحقق.</b>\n"
                f"🔍 <b>السبب المشخص:</b> {esc(diag_reason)}\n\n"
                f"💡 <i>اضغط <b>🖥️ الشاشة الحية لحل التحقق بنفسي</b> لتجاوز الفحص البشري مباشرة داخل تلغرام، أو أرسل رمز 2FA، أو استورد الكوكيز.\n"
                f"⏳ يُحذف الحساب التالف تلقائياً بعد {BROKEN_ACCOUNT_TTL_HOURS} ساعة إن لم يتفعّل.</i>",
                chat_id, msg_id,
                reply_markup=fail_markup
            )
            if has_shot:
                try:
                    with open(shot_path, "rb") as sf:
                        bot.send_photo(
                            chat_id,
                            sf,
                            caption=f"📸 <b>لقطة حية من متصفح فيسبوك ({esc(acc['name'])}) — افتح الشاشة الحية لإكماله الآن:</b>",
                            reply_markup=_build_hitl_action_markup(acc["id"], can_otp=True, can_del=False, include_back=False),
                        )
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
            shot_path=shot_path if has_shot else "",
            profile_quality=prof_quality if logged and isinstance(prof_quality, dict) else None,
            rew=rew if logged else None,
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
        elif st["selected_acc"] == "multi":
            picked_ids = {str(x) for x in (st.get("selected_accs") or [])}
            target_accounts = [a for a in usable if a["id"] in picked_ids]
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
        run_issues = []
        done_logs = []
        consecutive_challenges = 0
        try:
            max_consec_challenges = max(2, int(os.environ.get("FB_CONSECUTIVE_CHALLENGE_LIMIT", "3") or "3"))
        except Exception:
            max_consec_challenges = 3
        try:
            gap_min = max(1.0, float(os.environ.get("FB_MIN_ACCOUNT_GAP", "8") or "8"))
            gap_max = max(gap_min, float(os.environ.get("FB_MAX_ACCOUNT_GAP", "18") or "18"))
        except Exception:
            gap_min, gap_max = 8.0, 18.0
        circuit_tripped = False

        def _build_mission_pause_markup(aid: str, can_otp: bool = True) -> types.InlineKeyboardMarkup:
            mk = types.InlineKeyboardMarkup(row_width=2)
            w_url = get_public_webapp_url()
            if w_url:
                sep = "&" if "?" in w_url else "?"
                mk.row(
                    _btn(
                        "🖥️ فتح الشاشة الحية للتحقق الآن",
                        style="primary",
                        icon_key="shield",
                        web_app=types.WebAppInfo(url=f"{w_url}{sep}hitl={aid}"),
                    )
                )
            row_ctl = [_btn("✅ أكملت التحقق — تابع", style="success", icon_key="check", callback_data=f"mission_hitl_resume_{aid}")]
            if can_otp:
                row_ctl.append(_btn("🔑 إرسال 2FA", style="primary", callback_data=f"hitl_otp_{aid}"))
            mk.row(*row_ctl)
            mk.row(
                _btn("⏭️ تخطي الحساب", callback_data=f"mission_hitl_skip_{aid}"),
                _btn("🛑 إيقاف المهمة", style="danger", callback_data=f"mission_hitl_abort_{aid}"),
            )
            return mk

        mission_aborted = False
        for idx, acc in enumerate(target_accounts, 1):
            if mission_aborted:
                break
            # التحقق الفوري أثناء التشغيل تحسباً لحظْر أو سحب الصلاحيات في المنتصف
            if not (is_super_admin(user_id) or (is_authorized_user(user_id) and has_permission(user_id, "can_execute"))):
                update_live_status(
                    "⛔ <b>تم إيقاف التشغيل فوراً لأن المطور قام بسحب صلاحية التنفيذ أو حظر الحساب.</b>",
                    reply_markup=_back_home_markup()
                )
                return

            label_acc = acc["name"] if is_super_admin(user_id) else f"{acc['name']}"
            wait_hitl_enabled = bool(st.get("wait_for_hitl", True))

            for _attempt in range(2):
                acc = get_account_by_id(acc["id"]) or acc
                update_live_status(
                    f"🚀 <b>جاري التنفيذ بالخلفية ({idx}/{total_accounts}):</b>\n"
                    f"👤 <b>{esc(label_acc)}</b>"
                    + (" <i>(بعد التحقق البشري)</i>" if _attempt > 0 else "")
                    + f"\n🔗 <b>الهدف:</b> <code>{esc(target_url[:48])}</code>"
                )

                shot_path = str(SHOTS_TEMP_DIR / f"mission_{user_id}_{acc['id']}_{int(time.time())}.png")
                lock = get_profile_lock(acc["id"])
                proxy_uri = _account_proxy_guard_uri(acc)
                resolved_proxy_uri = str(acc.get("proxy") or "").strip()
                if not resolved_proxy_uri:
                    try:
                        resolved_proxy_uri = str(resolve_proxy_for_account(account_id=acc["id"]).get("raw_uri") or "")
                    except Exception:
                        resolved_proxy_uri = ""
                hitl_pause_req: dict | None = None
                pause_shot_saved = False

                with lock, proxy_execution_guard(proxy_uri, min_gap_sec=1.5), _browser_semaphore:
                    with sync_playwright() as p:
                        try:
                            acc_proxy = str(acc.get("proxy") or "").strip()
                            ctx = (
                                launch_account_browser(p, acc["profile_dir"], visible=False, proxy=acc_proxy)
                                if acc_proxy
                                else launch_account_browser(p, acc["profile_dir"], visible=False)
                            )
                            try:
                                page = ctx.pages[0] if ctx.pages else ctx.new_page()
                                acc_actions = 0
                                logged = False
                                challenge_hit_this_acc = False

                                def _record_issue(step_lbl: str, fallback_msg: str):
                                    diag = get_page_diag(page) or fallback_msg
                                    msg_line = f"• <b>{esc(label_acc)} ({step_lbl}):</b> {esc(diag)}"
                                    run_issues.append(msg_line)
                                    update_live_status(f"⚠️ {msg_line}")

                                def _record_success(step_lbl: str):
                                    msg_line = f"• <b>{esc(label_acc)}:</b> {step_lbl}"
                                    done_logs.append(msg_line)
                                    update_live_status(
                                        f"⚙️ <b>تقدم الخلفية ({idx}/{total_accounts}):</b> {esc(label_acc)} — {step_lbl}"
                                    )

                                can_fix_acc = is_super_admin(user_id) or (
                                    int(acc.get("owner_id") or 0) == int(user_id)
                                    and (has_permission(user_id, "can_add_accounts") or has_permission(user_id, "can_use_accounts"))
                                )

                                is_ck_acc = acc.get("password") == "[SESSION_COOKIES]"
                                logged = auto_login_facebook(
                                    ctx,
                                    page,
                                    "" if is_ck_acc else acc.get("email", ""),
                                    "" if is_ck_acc else acc.get("password", ""),
                                    max_wait=35,
                                )
                                proceed_actions = True
                                if not logged:
                                    login_err = get_login_error(ctx) or "الحساب غير مسجل دخوله أو يتطلب تحققاً"
                                    try:
                                        d_fail = diagnose_facebook_challenge(page)
                                    except Exception:
                                        d_fail = {}
                                    if d_fail.get("is_challenge") or any(k in login_err.lower() for k in ("recaptcha", "arkose", "checkpoint", "2fa", "تحقق أمان", "تأكيد أنك إنسان")):
                                        challenge_hit_this_acc = True
                                    try:
                                        update_account(acc["id"], {
                                            "status": "يتطلب تسجيل الدخول",
                                            "diagnostic_reason": login_err
                                        }, sync_git=False)
                                    except Exception:
                                        pass
                                    try:
                                        page.screenshot(path=shot_path)
                                        pause_shot_saved = True
                                    except Exception:
                                        pause_shot_saved = False
                                    if wait_hitl_enabled and can_fix_acc and _attempt == 0:
                                        hitl_pause_req = {"reason": login_err, "can_otp": True}
                                    else:
                                        run_issues.append(f"• <b>{esc(label_acc)} (الدخول):</b> {esc(login_err)}")
                                        update_live_status(f"⚠️ <b>{esc(label_acc)}:</b> {esc(login_err)}")
                                        shot_mk = _build_hitl_action_markup(acc["id"], can_otp=True, can_del=False) if can_fix_acc else None
                                        if pause_shot_saved:
                                            try:
                                                with open(shot_path, "rb") as shot_file:
                                                    bot.send_photo(
                                                        chat_id,
                                                        shot_file,
                                                        caption=f"⚠️ <b>لقطة سبب تعذر الدخول ({esc(label_acc)}):</b>\n{esc(login_err)}",
                                                        reply_markup=shot_mk,
                                                    )
                                            except Exception:
                                                pass
                                    proceed_actions = False
                                else:
                                    if _attempt > 0:
                                        try:
                                            human_warmup_after_login(page)
                                        except Exception:
                                            pass
                                    if not navigate_to_target(page, target_url):
                                        try:
                                            d_nav = diagnose_facebook_challenge(page)
                                        except Exception:
                                            d_nav = {}
                                        nav_reason = d_nav.get("message") or get_page_diag(page) or "تعذر فتح الرابط المستهدف أو أنه مقيد/غير متاح"
                                        if d_nav.get("is_challenge"):
                                            challenge_hit_this_acc = True
                                            try:
                                                update_account(acc["id"], {"diagnostic_reason": nav_reason}, sync_git=False)
                                            except Exception:
                                                pass
                                        try:
                                            page.screenshot(path=shot_path)
                                            pause_shot_saved = True
                                        except Exception:
                                            pause_shot_saved = False
                                        if wait_hitl_enabled and can_fix_acc and _attempt == 0 and d_nav.get("can_hitl"):
                                            hitl_pause_req = {"reason": nav_reason, "can_otp": bool(d_nav.get("can_otp"))}
                                        else:
                                            _record_issue("فتح الرابط", nav_reason)
                                            nav_mk = _build_hitl_action_markup(acc["id"], can_otp=bool(d_nav.get("can_otp")), can_del=False) if (can_fix_acc and d_nav.get("can_hitl")) else None
                                            if pause_shot_saved:
                                                try:
                                                    with open(shot_path, "rb") as shot_file:
                                                        bot.send_photo(
                                                            chat_id,
                                                            shot_file,
                                                            caption=f"❌ <b>لقطة تعذر فتح الرابط ({esc(label_acc)}):</b>\n{esc(nav_reason)}",
                                                            reply_markup=nav_mk,
                                                        )
                                                except Exception:
                                                    pass
                                        proceed_actions = False

                                # عمليات مستوى البروفايل (صداقة، متابعة، مراسلة، بلاغ حساب، حظر)
                                if proceed_actions and has_permission(user_id, "can_friend_follow"):
                                    if st["friend"]:
                                        if send_friend_request(page):
                                            actions_done += 1
                                            acc_actions += 1
                                            _record_success("إرسال طلب صداقة")
                                        else:
                                            _record_issue("طلب صداقة", "زر إضافة صديق غير متاح بالصفحة")
                                    elif st["cancel_friend"]:
                                        if cancel_friend_request(page):
                                            actions_done += 1
                                            acc_actions += 1
                                            _record_success("إلغاء طلب الصداقة")
                                        else:
                                            _record_issue("إلغاء الصداقة", "لا يوجد طلب صداقة معلق أو علاقة لإلغائها")

                                    if st["follow"]:
                                        if follow_profile(page):
                                            actions_done += 1
                                            acc_actions += 1
                                            _record_success("متابعة الحساب")
                                        else:
                                            _record_issue("متابعة", "زر المتابعة غير متوفر أو الحساب متابَع مسبقاً")
                                    elif st["unfollow"]:
                                        if unfollow_profile(page):
                                            actions_done += 1
                                            acc_actions += 1
                                            _record_success("إلغاء المتابعة")
                                        else:
                                            _record_issue("إلغاء المتابعة", "لم يتم العثور على زر إلغاء المتابعة")

                                if proceed_actions and has_permission(user_id, "can_message") and st["message"] and st["message_text"]:
                                    if send_direct_message(page, st["message_text"], target_url=target_url):
                                        actions_done += 1
                                        acc_actions += 1
                                        _record_success("إرسال رسالة خاصة")
                                    else:
                                        _record_issue("رسالة خاصة", "تعذر إرسال الرسالة بالماسنجر أو الحساب يمنع الرسائل")

                                if proceed_actions and has_permission(user_id, "can_report") and st["report_profile"]:
                                    update_live_status(f"🛡️ <b>جاري تنفيذ بلاغ الحساب بـ {esc(label_acc)}...</b>")
                                    if report_profile(page, reason=st["rep_reason"], victim=st["rep_victim"]):
                                        actions_done += 1
                                        acc_actions += 1
                                        _record_success("تأكيد استلام بلاغ الحساب")
                                    else:
                                        _record_issue("بلاغ حساب", "تعذر إتمام خطوات بلاغ الحساب")

                                if proceed_actions and has_permission(user_id, "can_report") and st["block"]:
                                    if block_profile(page):
                                        actions_done += 1
                                        acc_actions += 1
                                        _record_success("حظر الحساب")
                                    else:
                                        _record_issue("حظر", "تعذر العثور على خيار حظر الحساب")

                                # عمليات مستوى المنشور والتعليقات
                                on_custom_url = False
                                if proceed_actions and has_permission(user_id, "can_react") and st["like"]:
                                    r_lim = st.get("react_acc_count", 0)
                                    if r_lim == 0 or idx <= r_lim:
                                        r_url = st.get("react_post_url", "").strip()
                                        nav_ok = True
                                        if r_url:
                                            nav_ok = navigate_to_target(page, r_url)
                                            on_custom_url = True
                                        if nav_ok and react_to_posts(page, reaction=st["reaction_type"], post_index=1 if r_url else st["react_post_index"]):
                                            actions_done += 1
                                            acc_actions += 1
                                            r_name = REACTION_ICONS.get(st["reaction_type"], st["reaction_type"])
                                            _record_success(f"تفاعل ({esc(r_name)})")
                                        else:
                                            _record_issue("التفاعل", "لم يتم العثور على المنشور أو زر التفاعل")

                                if proceed_actions and has_permission(user_id, "can_comment") and st["comment"] and st["comment_text"]:
                                    c_lim = st.get("comment_acc_count", 0)
                                    if c_lim == 0 or idx <= c_lim:
                                        c_url = st.get("comment_post_url", "").strip()
                                        if not c_url and on_custom_url:
                                            navigate_to_target(page, target_url)
                                            on_custom_url = False
                                        c_cnt = comment_on_posts(
                                            page,
                                            comment_text=st["comment_text"],
                                            post_index=1 if c_url else st["comment_post_index"],
                                            post_url=c_url
                                        )
                                        if c_url:
                                            on_custom_url = True
                                        if c_cnt > 0:
                                            actions_done += c_cnt
                                            acc_actions += c_cnt
                                            _record_success("نشر تعليق")
                                        else:
                                            _record_issue("التعليق", "التعليقات مقيدة أو تعذر الوصول لصندوق التعليق")

                                if proceed_actions and has_permission(user_id, "can_interact_comments") and st["interact_cmt"]:
                                    if on_custom_url:
                                        navigate_to_target(page, target_url)
                                        on_custom_url = False
                                    if interact_with_specific_comment(
                                        page, post_index=1,
                                        target_mode=st["cmt_target_mode"],
                                        target_value=st["cmt_target_val"],
                                        reaction=st["cmt_reaction"],
                                        reply_text=st["cmt_reply"]
                                    ):
                                        actions_done += 1
                                        acc_actions += 1
                                        _record_success("التفاعل/الرد على تعليق")
                                    else:
                                        _record_issue("رد على تعليق", "لم يتم العثور على التعليق المطابق")

                                if proceed_actions and has_permission(user_id, "can_report") and st["report_post"]:
                                    if on_custom_url:
                                        navigate_to_target(page, target_url)
                                    update_live_status(f"🛡️ <b>جاري تنفيذ بلاغ المنشور بـ {esc(label_acc)}...</b>")
                                    if report_post(page, reason=st["rep_reason"], victim=st["rep_victim"]):
                                        actions_done += 1
                                        acc_actions += 1
                                        _record_success("بلاغ منشور")
                                    else:
                                        _record_issue("بلاغ منشور", "تعذر إتمام خطوات بلاغ المنشور")

                                # عند 0 إجراءات مع وجود تحدي قابل للحل عبر الشاشة الحية، يتم تفعيل الانتظار التفاعلي
                                if proceed_actions and acc_actions == 0:
                                    try:
                                        d_zero = diagnose_facebook_challenge(page)
                                    except Exception:
                                        d_zero = {}
                                    if d_zero.get("is_challenge"):
                                        challenge_hit_this_acc = True
                                        try:
                                            update_account(acc["id"], {"diagnostic_reason": d_zero.get("message") or ""}, sync_git=False)
                                        except Exception:
                                            pass
                                    zero_reason = d_zero.get("message") or get_page_diag(page) or ""
                                    try:
                                        page.screenshot(path=shot_path)
                                        pause_shot_saved = True
                                    except Exception:
                                        pause_shot_saved = False
                                    if wait_hitl_enabled and can_fix_acc and _attempt == 0 and d_zero.get("can_hitl"):
                                        hitl_pause_req = {
                                            "reason": zero_reason or "يتطلب إكمال التحقق في الشاشة الحية",
                                            "can_otp": bool(d_zero.get("can_otp")),
                                        }
                                    else:
                                        zero_mk = _build_hitl_action_markup(acc["id"], can_otp=bool(d_zero.get("can_otp")), can_del=False) if (can_fix_acc and d_zero.get("can_hitl")) else None
                                        zero_cap = f"📸 <b>لقطة تشخيصية (0 إجراءات بالحساب):</b> {esc(label_acc)}" + (f"\n{esc(zero_reason)}" if zero_reason else "")
                                        if pause_shot_saved:
                                            try:
                                                with open(shot_path, "rb") as shot_file:
                                                    bot.send_photo(
                                                        chat_id,
                                                        shot_file,
                                                        caption=zero_cap,
                                                        reply_markup=zero_mk,
                                                    )
                                            except Exception:
                                                pass

                                if proceed_actions:
                                    human_delay(1.5, 2.5)
                            finally:
                                page_ok = True
                                try:
                                    if proceed_actions and acc_actions == 0:
                                        try:
                                            page_ok = bool(diagnose_facebook_challenge(page).get("is_ok", True))
                                        except Exception:
                                            page_ok = True
                                    if hitl_pause_req or challenge_hit_this_acc:
                                        try:
                                            record_hitl_challenge_url(acc["id"], getattr(page, "url", ""))
                                        except Exception:
                                            pass
                                        save_account_storage_state(ctx, acc["profile_dir"])
                                    elif acc_actions > 0 or (logged and page_ok):
                                        save_account_storage_state(ctx, acc["profile_dir"])
                                except Exception:
                                    pass
                                try:
                                    if resolved_proxy_uri and not hitl_pause_req:
                                        record_proxy_use(
                                            resolved_proxy_uri,
                                            success=bool(acc_actions > 0 or (logged and page_ok)),
                                            error="" if (acc_actions > 0 or logged) else (get_page_diag(page) or "فشل الجلسة"),
                                        )
                                except Exception:
                                    pass
                                try:
                                    ctx.close()
                                except Exception:
                                    pass
                                if hitl_pause_req:
                                    pass
                                elif acc_actions > 0:
                                    consecutive_challenges = 0
                                elif challenge_hit_this_acc:
                                    consecutive_challenges += 1
                                else:
                                    consecutive_challenges = 0
                        except Exception as err:
                            try:
                                if resolved_proxy_uri:
                                    record_proxy_use(resolved_proxy_uri, success=False, error=str(err))
                                    detect_and_report_proxy_error(resolved_proxy_uri, err, account_id=acc["id"])
                            except Exception:
                                pass
                            err_txt = f"• <b>{esc(label_acc)} (خطأ متصفح):</b> <code>{esc(err)}</code>"
                            run_issues.append(err_txt)
                            update_live_status(f"❌ <b>خطأ بالحساب {esc(label_acc)}:</b> <code>{esc(err)}</code>")
                        finally:
                            if (not hitl_pause_req) and os.path.exists(shot_path):
                                try:
                                    os.remove(shot_path)
                                except Exception:
                                    pass

                # خارج أقفال البروفايل والمتصفح تماماً لتجنب التعارض: انتظار التحقق البشري ثم المتابعة التلقائية
                if not hitl_pause_req:
                    break

                wait_reason = str(hitl_pause_req.get("reason") or "يتطلب تحققاً بشرياً من فيسبوك")
                register_mission_hitl_waiter(acc["id"], user_id, wait_reason)
                st["waiting_hitl_acc_id"] = acc["id"]
                st["waiting_hitl_reason"] = wait_reason
                publish_event("mission", user_id, "hitl_waiting")
                pause_mk = _build_mission_pause_markup(acc["id"], can_otp=bool(hitl_pause_req.get("can_otp", True)))
                pause_txt = (
                    f"⏸️ <b>إيقاف مؤقت للحساب ({esc(label_acc)}) بانتظار التحقق البشري:</b>\n"
                    f"⚠️ <b>السبب:</b> {esc(wait_reason)}\n"
                    "🖥️ افتح <b>الشاشة الحية</b> أدناه لحل التحقق وحفظ الجلسة، وسيُكمل البوت التنفيذ تلقائياً فور الانتهاء!"
                )
                update_live_status(
                    f"⏸️ <b>بانتظار التحقق اليدوي للحساب {esc(label_acc)} ({idx}/{total_accounts})...</b>\n{esc(wait_reason)}"
                )
                try:
                    if pause_shot_saved and os.path.exists(shot_path):
                        with open(shot_path, "rb") as sf:
                            bot.send_photo(chat_id, sf, caption=pause_txt, reply_markup=pause_mk)
                    else:
                        safe_send(chat_id, pause_txt, reply_markup=pause_mk)
                except Exception:
                    safe_send(chat_id, pause_txt, reply_markup=pause_mk)
                finally:
                    if os.path.exists(shot_path):
                        try:
                            os.remove(shot_path)
                        except Exception:
                            pass

                try:
                    hitl_wait_sec = max(1.0, float(os.environ.get("FB_HITL_WAIT_TIMEOUT", "300") or "300"))
                except Exception:
                    hitl_wait_sec = 300.0
                wait_res = wait_for_mission_hitl(acc["id"], timeout=hitl_wait_sec)
                st["waiting_hitl_acc_id"] = ""
                st["waiting_hitl_reason"] = ""
                publish_event("mission", user_id, "hitl_resumed")
                dec = wait_res.get("decision", "timeout")
                if dec == "verified":
                    try:
                        update_account(acc["id"], {"status": "نشط (تم التحقق)", "diagnostic_reason": ""}, sync_git=False)
                    except Exception:
                        pass
                    update_live_status(f"✅ <b>تم التحقق لـ {esc(label_acc)}! جاري استئناف التنفيذ الآن بالجلسة المحفوظة...</b>")
                    continue
                elif dec == "abort":
                    mission_aborted = True
                    run_issues.append(f"• <b>{esc(label_acc)} ({esc(wait_reason)}):</b> تم إيقاف المهمة يدوياً أثناء انتظار التحقق")
                    break
                else:
                    msg_skip = "تخطي الحساب يدوياً" if dec == "skip" else "انتهت مهلة انتظار التحقق (5 دقائق)"
                    run_issues.append(f"• <b>{esc(label_acc)} ({esc(wait_reason)}):</b> {msg_skip}")
                    consecutive_challenges += 1
                    break

            if consecutive_challenges >= max_consec_challenges and idx < total_accounts:
                circuit_tripped = True
                run_issues.append(
                    f"• <b>حماية القطيع:</b> تم إيقاف الموجة عند الحساب ({idx}/{total_accounts}) بعد {consecutive_challenges} فحوصات أمان متتالية لحماية بقية الحسابات."
                )
                break

            if idx < total_accounts:
                human_delay(gap_min, gap_max)

        if actions_done > 0:
            done_block = ""
            if done_logs:
                done_block = "\n\n📋 <b>ملخص المنفذ:</b>\n" + "\n".join(done_logs[:6])
            notes_block = ""
            if run_issues:
                notes_block = "\n\n⚠️ <b>ملاحظات لبعض المحاولات:</b>\n" + "\n".join(run_issues[:5])
            stop_banner = (
                "\n\n🛡️ <b>تم تفعيل حماية القطيع:</b> أوقف البوت بقية الحسابات مؤقتاً لتفادي فحوصات الأمان المتتالية على نفس الشبكة. "
                "افتح الشاشة الحية لحل العوائق أو أضف بروكسي <code>FB_PROXY</code>."
                if circuit_tripped else ""
            )
            update_live_status(
                "🎉 <b>اكتملت المهمة بنجاح!</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"✅ <b>إجمالي الإجراءات المنفذة:</b> {actions_done}\n"
                f"👥 <b>الحسابات المشاركة:</b> {total_accounts}"
                f"{done_block}"
                f"{notes_block}{stop_banner}",
                reply_markup=_back_home_markup()
            )
        else:
            reasons_txt = "\n".join(run_issues[:6]) if run_issues else "• لم تتطابق عناصر الصفحة المستهدفة أو الحسابات لم تكن مسجلة."
            stop_hint = (
                "🛡️ <i>أوقف البوت بقية الحسابات تلقائياً بعد فحوصات متتالية لحمايتها. حلّها عبر الشاشة الحية أو فعّل بروكسي سكني عبر FB_PROXY.</i>"
                if circuit_tripped
                else "💡 <i>تحقق من لقطة الشاشة المرفقة، وافحص الجلسات عبر (🔄 فحص الجلسات) أو تأكد أن الرابط عام ومتاح.</i>"
            )
            update_live_status(
                "⚠️ <b>انتهت المهمة دون تنفيذ أي إجراء فعلي (0)</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"❌ <b>إجمالي الإجراءات المنفذة:</b> 0\n"
                f"👥 <b>الحسابات المفحوصة:</b> {total_accounts}\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"📋 <b>الأسباب المسجلة:</b>\n{reasons_txt}\n\n"
                f"{stop_hint}",
                reply_markup=_back_home_markup()
            )

    except Exception as e:
        update_live_status(f"❌ حدث خطأ أثناء التنفيذ: <code>{esc(e)}</code>", reply_markup=_back_home_markup())
    finally:
        st["is_running"] = False
        st["waiting_hitl_acc_id"] = ""
        st["waiting_hitl_reason"] = ""
        publish_event("mission", user_id, "done")


# ----------------- خادم لوحة التحكم المصغرة داخل تلغرام (Telegram Mini App Server) -----------------

def _build_webapp_hooks() -> dict:
    return {
        "bot": bot,
        "SUPER_ADMIN_ID": SUPER_ADMIN_ID,
        "PERMISSION_LABELS": PERMISSION_LABELS,
        "ADMIN_TIER_LABELS": ADMIN_TIER_LABELS,
        "ADMIN_RESTRICTION_LABELS": ADMIN_RESTRICTION_LABELS,
        "is_super_admin": is_super_admin,
        "get_admin_tier": get_admin_tier,
        "get_admin_restrictions": get_admin_restrictions,
        "is_admin_delegate": is_admin_delegate,
        "has_admin_capability": has_admin_capability,
        "get_user_admin_capabilities": get_user_admin_capabilities,
        "can_manage_target_user": can_manage_target_user,
        "get_admin_notification_recipients": get_admin_notification_recipients,
        "set_admin_tier": set_admin_tier,
        "toggle_admin_restriction": toggle_admin_restriction,
        "grant_all_user_permissions": grant_all_user_permissions,
        "broadcast_announcement": _broadcast_announcement_to_users,
        "unpin_announcement_chats": _unpin_announcement_chats,
        "register_or_update_user": register_or_update_user,
        "notify_new_pending_user": notify_new_pending_user,
        "get_user_permissions": get_user_permissions,
        "user_has_any_action_perm": user_has_any_action_perm,
        "get_usable_accounts_for_user": get_usable_accounts_for_user,
        "get_manageable_accounts_for_user": get_manageable_accounts_for_user,
        "get_user_state": get_user_state,
        "persist_user_states": persist_user_states,
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
        "list_features": list_features,
        "get_feature": get_feature,
        "is_feature_accessible": is_feature_accessible,
        "get_feature_cost": get_feature_cost,
        "update_feature_gate": update_feature_gate,
        "add_allowed_user": add_allowed_user,
        "remove_allowed_user": remove_allowed_user,
        "register_custom_feature": register_custom_feature,
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


def _maintenance_sync_worker() -> None:
    """مراقبة خلفية لجدولة قناة النسخ الاحتياطي والإعلانات العائمة ومراقب البروكسيات الآلي وحذف الحسابات التالفة"""
    last_purge = time.time()
    last_ann_check = 0.0
    last_proxy_tick = 0.0
    while True:
        time.sleep(2)
        try:
            flush_cloud_backups(bot, SUPER_ADMIN_ID)
        except Exception:
            pass
        now_t = time.time()
        if now_t - last_ann_check >= 6:
            last_ann_check = now_t
            try:
                for exp_ann in pop_expired_pinned_announcements(now_ts=now_t):
                    _unpin_announcement_chats(exp_ann)
            except Exception:
                pass
            try:
                for rep_ann in get_announcements_due_for_repeat(now_ts=now_t):
                    _broadcast_announcement_to_users(rep_ann, is_repeat=True)
                    mark_announcement_repushed(rep_ann["id"])
            except Exception:
                pass
        if now_t - last_proxy_tick >= 20:
            last_proxy_tick = now_t
            try:
                threading.Thread(target=run_scheduled_proxy_watchdog, daemon=True).start()
            except Exception:
                pass
        if now_t - last_purge >= 1800:
            last_purge = now_t
            try:
                cnt, _ = purge_expired_broken_accounts(BROKEN_ACCOUNT_TTL_HOURS)
                if cnt > 0:
                    print(f"[AutoPurge] تم حذف {cnt} حساب غير نشط تجاوز {BROKEN_ACCOUNT_TTL_HOURS} ساعة.")
            except Exception:
                pass


def _tempmail_auto_poller_worker() -> None:
    """مراقب خلفي ذكي يفحص الإيميلات النشطة للمستخدمين ويرسل إشعاراً فورياً عند وصول أي كود OTP أو رسالة جديدة"""
    while not _stop_polling_event.is_set():
        time.sleep(8)
        try:
            tele = tm_m.get_telemetry_stats()
            if tele.get("active_users_with_mail", 0) <= 0:
                continue

            data = tm_m._get_data()
            users_map = data.get("users", {})
            for uid_str, mb in list(users_map.items()):
                try:
                    uid = int(uid_str)
                    target_email = mb.get("email")
                    if not target_email or not mb.get("auto_notify", True):
                        continue

                    # فحص الوارد وجلب الرسائل الجديدة فقط
                    new_msgs = [m for m in tm_m.check_inbox(uid, target_email) if m.get("is_new")]
                    for msg in new_msgs:
                        sender = esc(msg.get("sender") or "مجهول")
                        subj = esc(msg.get("subject") or "بدون عنوان")
                        otp = msg.get("otp_code")
                        links = msg.get("links") or []

                        alert_txt = (
                            f"🔔 <b>وصلت رسالة جديدة إلى بريدك المؤقت!</b>\n"
                            f"━━━━━━━━━━━━━━━━━━━━\n"
                            f"📬 <b>البريد:</b> <code>{esc(target_email)}</code>\n"
                            f"👤 <b>من:</b> {sender}\n"
                            f"📌 <b>الموضوع:</b> {subj}\n"
                        )
                        if otp:
                            alert_txt += (
                                f"━━━━━━━━━━━━━━━━━━━━\n"
                                f"🔑 <b>كود التحقق (OTP):</b> <code>{esc(otp)}</code> <i>(اضغط للنسخ)</i>\n"
                            )

                        mk = types.InlineKeyboardMarkup(row_width=1)
                        if otp:
                            mk.row(types.InlineKeyboardButton(f"📋 نسخ كود OTP: {otp}", callback_data=f"tm_copyotp_{otp}"))
                        if links:
                            mk.row(types.InlineKeyboardButton("🌐 فتح رابط التفعيل", url=links[0]))
                        mk.row(
                            _btn("📥 عرض صندوق الوارد", style="primary", icon_key="spark", callback_data="tm_inbox")
                        )

                        safe_send(uid, alert_txt, reply_markup=mk)
                except Exception:
                    pass
        except Exception:
            pass


_shutdown_lock = threading.Lock()
_shutdown_executed = False
_shutdown_registered = False
_stop_polling_event = threading.Event()


def _graceful_shutdown_sync():
    global _shutdown_executed
    with _shutdown_lock:
        if _shutdown_executed:
            return
        _shutdown_executed = True
    try:
        flush_cloud_backups(bot, SUPER_ADMIN_ID, force=True, skip_tg_dm=True)
    except Exception:
        pass
    try:
        git_sync_save(async_mode=False)
    except Exception:
        pass


def _handle_exit_signal(signum, _frame):
    _stop_polling_event.set()
    try:
        bot.stop_polling()
    except Exception:
        pass
    _graceful_shutdown_sync()
    raise SystemExit(0)


def run_telegram_bot():
    global _live_sync_started, _shutdown_registered
    print("=" * 60)
    print("🚀 بدء تشغيل بوت تلغرام FB Operator في السحاب 24/7...")
    boot_info = bootstrap_persistence()
    reload_user_states_from_disk()
    try:
        seeded = seed_env_proxies()
        if seeded.get("added", 0) > 0:
            print(f"🌐 تم استيراد {seeded['added']} بروكسي تلقائياً من إعدادات البيئة.")
    except Exception:
        pass
    print(f"💾 مسار البيانات الدائم: {boot_info.get('data_dir')}")
    if boot_info.get("external_vault_path"):
        print(f"📦 ملف القاعدة الخارجية الشقيق: {boot_info.get('external_vault_path')} ({boot_info.get('external_vault_restore', '-')})")
    bkp_cfg = load_backup_settings()
    if bkp_cfg.get("channel_id"):
        print(f"📡 قناة النسخ الاحتياطي: {bkp_cfg.get('channel_title')} ({bkp_cfg.get('channel_id')}) | {bkp_cfg.get('interval_label')}")
    try:
        print(f"🤖 معرف البوت: @{bot.get_me().username}")
    except Exception:
        pass
    print(f"👑 معرف المطور الرئيسي الحصين: {SUPER_ADMIN_ID}")
    print("=" * 60)

    if not _shutdown_registered:
        atexit.register(_graceful_shutdown_sync)
        if threading.current_thread() is threading.main_thread():
            for _sig in (getattr(signal, "SIGTERM", None), getattr(signal, "SIGINT", None)):
                if _sig is not None:
                    try:
                        signal.signal(_sig, _handle_exit_signal)
                    except Exception:
                        pass
        _shutdown_registered = True

    if not _live_sync_started:
        register_hitl_verified_callback(_on_hitl_account_verified)
        register_proxy_alert_callback(_on_proxy_alert_event)
        register_listener(_on_state_event)
        threading.Thread(target=_live_inline_sync_worker, daemon=True).start()
        threading.Thread(target=_maintenance_sync_worker, daemon=True).start()
        threading.Thread(target=_tempmail_auto_poller_worker, daemon=True).start()
        _live_sync_started = True

    try:
        bot.set_my_commands([
            types.BotCommand("start", "🏠 فتح القائمة الرئيسية"),
            types.BotCommand("menu", "📋 لوحة التحكم والإجراءات"),
            types.BotCommand("keys", "⌨️ تثبيت أزرار الاختصار السفلية"),
            types.BotCommand("cancel", "🔙 إلغاء الإدخال والعودة"),
        ])
    except Exception:
        pass

    start_webapp_and_tunnel(BOT_TOKEN, _build_webapp_hooks())

    try:
        bot.delete_webhook(drop_pending_updates=False)
    except Exception:
        pass

    while not _stop_polling_event.is_set():
        try:
            bot.infinity_polling(
                timeout=25,
                long_polling_timeout=25,
                skip_pending=True,
                allowed_updates=["message", "callback_query"],
            )
        except (KeyboardInterrupt, SystemExit):
            _graceful_shutdown_sync()
            raise
        except Exception as e:
            if _stop_polling_event.is_set():
                break
            err_s = str(e)
            if "409" in err_s or "terminated by other getUpdates" in err_s:
                print("[CONFLICT 409] تحذير خطير: توجد نسخة أخرى تعمل بنفس BOT_TOKEN (مثل GitHub Actions أو Space قديم) وتسبب تضارب الردود! ألغِ النسخة القديمة أو جدّد التوكن عبر @BotFather (/revoke).")
            else:
                print(f"[Bot Warning] خطأ بالاتصال، إعادة المحاولة بعد 5 ثوانٍ: {e}")
            time.sleep(5)


if __name__ == "__main__":
    run_telegram_bot()
