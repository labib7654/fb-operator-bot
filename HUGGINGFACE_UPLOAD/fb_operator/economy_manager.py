"""
إدارة النقاط والإحالات والدعم.
"""

import json
import os
import secrets
import shutil
import string
import threading
import time
from datetime import datetime
from pathlib import Path

import fb_operator.account_manager as acc_mgr
import fb_operator.admin_manager as adm_mgr
from fb_operator.config import (
    BASE_DIR,
    ECONOMY_SETTINGS_FILE,
    POINTS_LEDGER_FILE,
    INVITE_CODES_FILE,
    SUPPORT_TICKETS_FILE,
)
from fb_operator.state_events import publish_event

_economy_lock = threading.RLock()

DEFAULT_OP_COSTS: dict[str, int] = {
    "like": 1,
    "comment": 2,
    "interact_cmt": 2,
    "friend": 1,
    "cancel_friend": 1,
    "follow": 1,
    "unfollow": 1,
    "message": 3,
    "report_post": 5,
    "report_profile": 5,
    "block": 5,
}

OP_COST_LABELS_AR: dict[str, str] = {
    "like": "إعجاب / تفاعل",
    "comment": "كتابة تعليق",
    "interact_cmt": "رد / تفاعل على تعليق",
    "friend": "طلب صداقة",
    "cancel_friend": "إلغاء صداقة",
    "follow": "متابعة",
    "unfollow": "إلغاء متابعة",
    "message": "رسالة خاصة",
    "report_post": "بلاغ منشور",
    "report_profile": "بلاغ حساب",
    "block": "حظر حساب",
}

DEFAULT_WALLETS = [
    {
        "id": "jeeb",
        "name": "محفظة جيب",
        "number": "771172888",
        "beneficiary": "لبيب فهد رعدان",
        "notes": "تحويل مباشر لرقم المحفظة",
        "active": True
    },
    {
        "id": "jawali",
        "name": "محفظة جوالي",
        "number": "771172888",
        "beneficiary": "لبيب فهد رعدان",
        "notes": "تحويل مباشر لرقم المحفظة",
        "active": True
    },
    {
        "id": "kuraimi",
        "name": "بنك الكريمي",
        "number": "300000000",
        "beneficiary": "لبيب فهد رعدان",
        "notes": "إرسال الحوالة بالريال اليمني",
        "active": True
    },
    {
        "id": "onecash",
        "name": "ون كاش",
        "number": "771172888",
        "beneficiary": "لبيب فهد رعدان",
        "notes": "تحويل لمحفظة ون كاش",
        "active": True
    }
]

DEFAULT_ECONOMY_SETTINGS: dict = {
    "public_mode": False,
    "enforce_points_on_actions": False,
    "suppliers_can_invite": True,
    "invited_suppliers_can_invite": True,
    "public_allow_report": False,
    "referral_trigger": "first_active",  # "first_active" | "instant"
    "yer_per_point": 10,
    "active_account_reward": 1,
    "incomplete_account_yer": 5,
    "profile_warning_limit": 5,
    "referral_reward": 4,
    "operation_costs": dict(DEFAULT_OP_COSTS),
    "wallets": list(DEFAULT_WALLETS),
    "sales_recipient_id": 7411444902,
    "sales_recipient_username": "",
}


def _atomic_write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + f".tmp.{threading.get_ident()}")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        try:
            os.fsync(f.fileno())
        except Exception:
            pass
    os.replace(tmp_path, path)


def _safe_load_json(path: Path, default_value):
    if not path.exists():
        return default_value
    try:
        with open(path, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        if type(loaded) is not type(default_value):
            raise ValueError("Type mismatch")
        return loaded
    except Exception:
        try:
            bak = path.with_suffix(".corrupt.bak")
            if path.exists() and not bak.exists():
                shutil.copy2(path, bak)
        except Exception:
            pass
        return default_value


def _now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _gen_id(prefix: str, length: int = 8) -> str:
    alphabet = string.ascii_uppercase + string.digits
    token = "".join(secrets.choice(alphabet) for _ in range(length))
    return f"{prefix}-{token}"


def _clamp_int(val, default: int, min_v: int, max_v: int) -> int:
    try:
        n = int(val)
        return max(min_v, min(max_v, n))
    except Exception:
        return default


def _normalize_settings(raw: dict | None) -> dict:
    raw = raw if isinstance(raw, dict) else {}
    raw_costs = raw.get("operation_costs") if isinstance(raw.get("operation_costs"), dict) else {}
    norm_costs = {
        k: _clamp_int(raw_costs.get(k, default_c), default_c, 0, 10000)
        for k, default_c in DEFAULT_OP_COSTS.items()
    }
    ref_trigger = raw.get("referral_trigger")
    if ref_trigger not in ("first_active", "instant"):
        ref_trigger = "first_active"
    pub = bool(raw.get("public_mode", False))
    raw_wallets = raw.get("wallets")
    norm_wallets = []
    if isinstance(raw_wallets, list) and len(raw_wallets) > 0:
        for idx_w, w in enumerate(raw_wallets):
            if isinstance(w, dict) and w.get("name"):
                w_id = str(w.get("id") or f"w_{idx_w+1}").strip().lower()
                norm_wallets.append({
                    "id": w_id,
                    "name": str(w.get("name", "")).strip(),
                    "number": str(w.get("number", "")).strip(),
                    "beneficiary": str(w.get("beneficiary", "")).strip(),
                    "notes": str(w.get("notes", "")).strip(),
                    "active": bool(w.get("active", True))
                })
    if not norm_wallets:
        norm_wallets = [dict(w) for w in DEFAULT_WALLETS]

    raw_sales_id = raw.get("sales_recipient_id")
    try:
        sales_id = int(raw_sales_id) if raw_sales_id else 7411444902
    except Exception:
        sales_id = 7411444902

    sales_uname = str(raw.get("sales_recipient_username") or "").strip().lstrip("@")

    return {
        "public_mode": pub,
        "enforce_points_on_actions": True if pub else bool(raw.get("enforce_points_on_actions", False)),
        "suppliers_can_invite": bool(raw.get("suppliers_can_invite", True)),
        "invited_suppliers_can_invite": bool(raw.get("invited_suppliers_can_invite", True)),
        "public_allow_report": bool(raw.get("public_allow_report", False)),
        "public_account_addition": bool(raw.get("public_account_addition", True)),
        "referral_trigger": ref_trigger,
        "yer_per_point": _clamp_int(raw.get("yer_per_point", 10), 10, 1, 1000000),
        "active_account_reward": _clamp_int(raw.get("active_account_reward", 1), 1, 0, 10000),
        "incomplete_account_yer": _clamp_int(raw.get("incomplete_account_yer", 5), 5, 0, 1000000),
        "profile_warning_limit": _clamp_int(raw.get("profile_warning_limit", 5), 5, 0, 20),
        "referral_reward": _clamp_int(raw.get("referral_reward", 4), 4, 0, 10000),
        "operation_costs": norm_costs,
        "wallets": norm_wallets,
        "sales_recipient_id": sales_id,
        "sales_recipient_username": sales_uname,
    }


def load_economy_settings() -> dict:
    with _economy_lock:
        raw = _safe_load_json(ECONOMY_SETTINGS_FILE, {})
        norm = _normalize_settings(raw)
        if not ECONOMY_SETTINGS_FILE.exists():
            _atomic_write_json(ECONOMY_SETTINGS_FILE, norm)
        return norm


def update_economy_settings(patch: dict, actor_uid: int = 0) -> dict:
    with _economy_lock:
        cur = load_economy_settings()
        if isinstance(patch, dict):
            for bool_k in (
                "public_mode",
                "enforce_points_on_actions",
                "suppliers_can_invite",
                "invited_suppliers_can_invite",
                "public_allow_report",
                "public_account_addition",
            ):
                if bool_k in patch:
                    cur[bool_k] = bool(patch[bool_k])
            if "referral_trigger" in patch and patch["referral_trigger"] in ("first_active", "instant"):
                cur["referral_trigger"] = patch["referral_trigger"]
            if "yer_per_point" in patch:
                cur["yer_per_point"] = _clamp_int(patch["yer_per_point"], cur["yer_per_point"], 1, 1000000)
            if "active_account_reward" in patch:
                cur["active_account_reward"] = _clamp_int(patch["active_account_reward"], cur["active_account_reward"], 0, 10000)
            if "incomplete_account_yer" in patch:
                cur["incomplete_account_yer"] = _clamp_int(patch["incomplete_account_yer"], cur.get("incomplete_account_yer", 5), 0, 1000000)
            if "profile_warning_limit" in patch:
                cur["profile_warning_limit"] = _clamp_int(patch["profile_warning_limit"], cur.get("profile_warning_limit", 5), 0, 20)
            if "referral_reward" in patch:
                cur["referral_reward"] = _clamp_int(patch["referral_reward"], cur["referral_reward"], 0, 10000)
            if "wallets" in patch and isinstance(patch["wallets"], list):
                cur["wallets"] = patch["wallets"]
            if "sales_recipient_id" in patch:
                cur["sales_recipient_id"] = patch["sales_recipient_id"]
            if "sales_recipient_username" in patch:
                cur["sales_recipient_username"] = patch["sales_recipient_username"]
            if isinstance(patch.get("operation_costs"), dict):
                for op_k, default_v in DEFAULT_OP_COSTS.items():
                    if op_k in patch["operation_costs"]:
                        cur["operation_costs"][op_k] = _clamp_int(
                            patch["operation_costs"][op_k],
                            cur["operation_costs"].get(op_k, default_v),
                            0,
                            10000,
                        )
        norm = _normalize_settings(cur)
        _atomic_write_json(ECONOMY_SETTINGS_FILE, norm)

    acc_mgr.git_sync_save(async_mode=True)
    if actor_uid:
        adm_mgr.record_audit_log(actor_uid, "المطور", "ECONOMY_SETTINGS", f"تحديث إعدادات النقاط والوضع العام: public={norm['public_mode']}, enforce={norm['enforce_points_on_actions']}, rate={norm['yer_per_point']}")
    publish_event("economy", 0, "settings_updated")
    return norm


def is_points_enforced_for_user(uid: int) -> bool:
    if adm_mgr.is_super_admin(uid):
        return False
    settings = load_economy_settings()
    return bool(settings.get("public_mode") or settings.get("enforce_points_on_actions"))


def can_user_invite(uid: int) -> bool:
    if adm_mgr.is_super_admin(uid):
        return True
    if not adm_mgr.is_authorized_user(uid):
        return False
    if adm_mgr.has_permission(uid, "can_invite"):
        return True
    settings = load_economy_settings()
    if settings.get("suppliers_can_invite", True) and adm_mgr.has_permission(uid, "can_add_accounts"):
        return True
    return False


def ensure_public_access_if_enabled(user_id: int) -> bool:
    """
    في حال فتح المطور 'الوضع العام': يتم اعتماد المستخدم غير المحظور تلقائياً
    بصلاحيات العضو العام، مع إبقاء خصم النقاط إلزامياً عند تنفيذ العمليات.
    """
    if adm_mgr.is_super_admin(user_id):
        return True
    settings = load_economy_settings()
    if not settings.get("public_mode"):
        return False

    changed = False
    with _economy_lock, adm_mgr._users_lock:
        users = adm_mgr.load_users()
        uid = str(int(user_id))
        u = users.get(uid)
        if not u or u.get("status") == "banned":
            return False
        if u.get("status") == "pending":
            u["status"] = "approved"
            u["role"] = "user"
            perms = dict(adm_mgr.DEFAULT_PERMISSIONS)
            for k in (
                "can_use_accounts",
                "can_add_accounts",
                "can_react",
                "can_comment",
                "can_interact_comments",
                "can_friend_follow",
                "can_message",
                "can_delete_accounts",
                "can_execute",
                "can_invite",
            ):
                perms[k] = True
            if settings.get("public_allow_report"):
                perms["can_report"] = True
            u["permissions"] = perms
            adm_mgr.save_users(users, sync_git=True)
            changed = True

    if changed:
        adm_mgr.record_audit_log(int(user_id), u.get("name", ""), "PUBLIC_AUTO_JOIN", "دخول تلقائي عبر الوضع العام للبوت (تحت نظام النقاط)")
        publish_event("users", int(user_id), "public_approved")
    return True


def _load_ledger_unlocked() -> list[dict]:
    data = _safe_load_json(POINTS_LEDGER_FILE, [])
    return [x for x in data if isinstance(x, dict)]


def load_points_ledger(user_id: int | None = None, limit: int = 50) -> list[dict]:
    with _economy_lock:
        items = _load_ledger_unlocked()
    if user_id is not None:
        uid = int(user_id)
        items = [x for x in items if int(x.get("user_id", 0)) == uid]
    if limit and limit > 0:
        return items[-limit:]
    return items


def adjust_user_points(
    target_uid: int,
    delta: int | float,
    tx_type: str,
    reason: str,
    actor_uid: int = 0,
    idempotency_key: str | None = None,
    mark_settled_yer: bool = False,
    allow_partial_zero: bool = False,
    extra: dict | None = None,
) -> dict:
    """
    دالة محفظة ذرية آمنة لتعديل النقاط (إضافة/خصم/مكافأة/تسوية):
    - تحترم ترتيب الأقفال (_economy_lock -> _users_lock) لمنع أي جمود.
    - تدعم الكسور الدقيقة (مثل 0.5 نقطة = 5 ريال) مع الإبقاء على int للأعداد الصحيحة.
    - تمنع السحب بالسالب إلا في التصفير الصريح عند allow_partial_zero=True.
    - تدعم مفتاح عدم التكرار idempotency_key لمنع منح مكافأة واحدة مرتين.
    """
    tid = int(target_uid)
    raw_delta = round(float(delta), 2)
    delta_num: int | float = int(raw_delta) if abs(raw_delta - int(raw_delta)) < 1e-9 else raw_delta
    entry: dict | None = None
    settings = load_economy_settings()
    rate = settings["yer_per_point"]

    with _economy_lock:
        ledger = _load_ledger_unlocked()
        if idempotency_key:
            for prev in ledger:
                if prev.get("idempotency_key") == idempotency_key:
                    with adm_mgr._users_lock:
                        users = adm_mgr.load_users()
                        cur_bal = adm_mgr.safe_nonneg_points((users.get(str(tid)) or {}).get("points", 0))
                    return {
                        "ok": False,
                        "duplicate": True,
                        "balance": cur_bal,
                        "yer_value": int(round(cur_bal * rate)),
                    }

        with adm_mgr._users_lock:
            users = adm_mgr.load_users()
            u = users.get(str(tid))
            if not u:
                return {"ok": False, "error": "user_not_found"}

            bal_before = adm_mgr.safe_nonneg_points(u.get("points", 0))
            if delta_num < 0:
                abs_d = round(abs(float(delta_num)), 2)
                if float(bal_before) + 1e-9 < abs_d:
                    if not allow_partial_zero:
                        return {
                            "ok": False,
                            "error": "insufficient_points",
                            "required": adm_mgr.safe_nonneg_points(abs_d),
                            "balance": bal_before,
                            "yer_per_point": rate,
                        }
                    delta_num = -bal_before if bal_before else 0

            bal_after = adm_mgr.safe_nonneg_points(float(bal_before) + float(delta_num))
            u["points"] = bal_after
            if delta_num > 0:
                u["total_points_earned"] = adm_mgr.safe_nonneg_points(float(u.get("total_points_earned", 0)) + float(delta_num))
            elif delta_num < 0:
                u["total_points_spent"] = adm_mgr.safe_nonneg_points(float(u.get("total_points_spent", 0)) + abs(float(delta_num)))

            yer_delta = int(round(abs(float(delta_num)) * rate))
            if mark_settled_yer and delta_num < 0:
                u["total_yer_settled"] = int(u.get("total_yer_settled", 0)) + yer_delta

            adm_mgr.save_users(users, sync_git=False)

        tx_id = _gen_id("TX", 8)
        yer_signed = int(round(float(delta_num) * rate))
        entry = {
            "id": tx_id,
            "timestamp": _now_str(),
            "user_id": tid,
            "user_name": str(u.get("name", "")),
            "actor_uid": int(actor_uid or 0),
            "tx_type": str(tx_type),
            "delta": delta_num,
            "balance_before": bal_before,
            "balance_after": bal_after,
            "yer_per_point": rate,
            "yer_amount": yer_signed,
            "reason": str(reason or "")[:300],
            "idempotency_key": idempotency_key,
            "extra": extra if isinstance(extra, dict) else {},
        }
        ledger.append(entry)
        if len(ledger) > 2000:
            ledger = ledger[-2000:]
        _atomic_write_json(POINTS_LEDGER_FILE, ledger)

    acc_mgr.git_sync_save(async_mode=True)
    sign_txt = f"+{delta_num}" if delta_num >= 0 else str(delta_num)
    adm_mgr.record_audit_log(
        tid,
        entry["user_name"],
        f"POINTS_{tx_type}",
        f"{sign_txt} نقطة ({yer_delta} ريال) | الرصيد الجديد: {entry['balance_after']} | {reason}",
    )
    publish_event("economy", tid, tx_type.lower())
    return {
        "ok": True,
        "tx": entry,
        "delta": delta_num,
        "balance": entry["balance_after"],
        "yer_per_point": rate,
        "yer_value": int(round(float(entry["balance_after"]) * rate)),
        "yer_delta": yer_delta,
    }


def credit_user_balance(uid: int, points: int | float, reason: str = "") -> dict:
    """إيداع نقاط في محفظة المستخدم"""
    return adjust_user_points(uid, points, tx_type="REWARD", reason=reason or "شحن رصيد")


def deduct_user_balance(uid: int, points: int | float, reason: str = "") -> dict:
    """خصم نقاط من محفظة المستخدم"""
    return adjust_user_points(uid, -abs(points), tx_type="MISSION", reason=reason or "خصم رصيد", allow_partial_zero=True)


def reward_account_activation(
    owner_id: int,
    acc_id: str,
    acc_name: str = "",
    profile_quality: dict | None = None,
) -> dict:
    """
    منح نقاط تفعيل حساب فيسبوك نشط للمالك (+1 نقطة = 10 ريال للحساب المكتمل، بدون تكرار):
    - يطبق نظام الـ 5 إنذارات عندما يكون الحساب ناقص المواصفات (الاسم العربي، الغلاف، السيرة، الجامعة، الحالة، المنشورات):
      * الإنذارات 1..5: تحذير واضح + بقاء المكافأة كاملة (10 ريال).
      * بعد استنفاد الـ 5 إنذارات: يُحتسب الحساب الناقص بنصف السعر (5 ريال = 0.5 نقطة افتراضياً)،
        بينما يستمر احتساب أي حساب كامل المواصفات بـ 10 ريال كاملة.
    - وإطلاق مكافأة الإحالة (+4 نقاط = 40 ريال) للمُحيل عند أول حساب نشط للمدعو.
    """
    settings = load_economy_settings()
    rate = settings["yer_per_point"]
    acc_reward = settings["active_account_reward"]
    inc_yer = int(settings.get("incomplete_account_yer", 5))
    warn_limit = int(settings.get("profile_warning_limit", 5))
    ref_reward = settings["referral_reward"]
    oid = int(owner_id)

    wallet_now = get_user_wallet(oid)
    out: dict = {
        "owner_id": oid,
        "owner_awarded": 0,
        "owner_awarded_yer": 0,
        "owner_balance": wallet_now["points"],
        "owner_yer_value": wallet_now["yer_value"],
        "referral_inviter_id": 0,
        "referral_awarded": 0,
        "referral_inviter_balance": 0,
        "yer_per_point": rate,
        "warning_status": "none",  # none | complete | warned | penalized
        "warning_num": 0,
        "warning_limit": warn_limit,
        "warnings_remaining": warn_limit,
        "missing_labels": [],
        "full_reward_yer": int(round(acc_reward * rate)),
        "incomplete_reward_yer": inc_yer,
    }

    is_incomplete = bool(
        isinstance(profile_quality, dict)
        and profile_quality.get("checked")
        and not profile_quality.get("passed")
    )
    missing_labels = list(profile_quality.get("missing_labels") or []) if isinstance(profile_quality, dict) else []
    out["missing_labels"] = missing_labels

    if oid > 0 and acc_reward > 0:
        with _economy_lock:
            ledger_chk = _load_ledger_unlocked()
            already_paid = any(prev.get("idempotency_key") == f"acc_active:{acc_id}" for prev in ledger_chk)
            award_pts: int | float = acc_reward
            tx_reason = f"تفعيل حساب فيسبوك نشط ({acc_name or acc_id})"

            if is_incomplete and not already_paid:
                with adm_mgr._users_lock:
                    users = adm_mgr.load_users()
                    u_obj = users.get(str(oid))
                    prev_w = int((u_obj or {}).get("profile_warnings_used", 0))
                    if prev_w < warn_limit:
                        new_w = prev_w + 1
                        if isinstance(u_obj, dict):
                            u_obj["profile_warnings_used"] = new_w
                            adm_mgr.save_users(users, sync_git=False)
                        out["warning_status"] = "warned"
                        out["warning_num"] = new_w
                        out["warnings_remaining"] = max(0, warn_limit - new_w)
                        tx_reason = f"تفعيل حساب ناقص مواصفات [إنذار {new_w}/{warn_limit}] ({acc_name or acc_id})"
                    else:
                        half_pts = adm_mgr.safe_nonneg_points(inc_yer / max(1, rate))
                        award_pts = min(acc_reward, half_pts)
                        out["warning_status"] = "penalized"
                        out["warning_num"] = warn_limit
                        out["warnings_remaining"] = 0
                        tx_reason = f"تفعيل حساب ناقص بعد نفاد الإنذارات ({inc_yer} ر.ي) ({acc_name or acc_id})"
            elif isinstance(profile_quality, dict) and profile_quality.get("checked") and profile_quality.get("passed"):
                out["warning_status"] = "complete"
                tx_reason = f"تفعيل حساب فيسبوك مكتمل المواصفات ({acc_name or acc_id})"

            res_owner = adjust_user_points(
                target_uid=oid,
                delta=award_pts,
                tx_type="ACTIVE_ACCOUNT_REWARD",
                reason=tx_reason,
                actor_uid=0,
                idempotency_key=f"acc_active:{acc_id}",
                extra={"account_id": acc_id, "warning_status": out["warning_status"], "missing": missing_labels},
            )
            if res_owner.get("ok"):
                out["owner_awarded"] = award_pts
                out["owner_awarded_yer"] = res_owner["yer_delta"]
                out["owner_balance"] = res_owner["balance"]
                out["owner_yer_value"] = res_owner["yer_value"]

    # مكافأة المُحيل (+4 نقاط) عند أول تفعيل حساب نشط للمدعو
    inviter_id = 0
    already_rewarded = True
    with adm_mgr._users_lock:
        users = adm_mgr.load_users()
        u = users.get(str(oid))
        if u:
            inviter_id = int(u.get("referred_by") or 0)
            already_rewarded = bool(u.get("referral_rewarded", False))

    if inviter_id > 0 and not already_rewarded and inviter_id != oid and ref_reward > 0:
        redeemer_name = (adm_mgr.load_users().get(str(oid)) or {}).get("name", str(oid))
        ref_res = adjust_user_points(
            target_uid=inviter_id,
            delta=ref_reward,
            tx_type="REFERRAL_REWARD",
            reason=f"مكافأة إحالة وتفعيل أول حساب نشط للمستخدم {redeemer_name} ({oid})",
            actor_uid=oid,
            idempotency_key=f"ref_bonus:{oid}",
            extra={"referred_uid": oid, "account_id": acc_id},
        )
        if ref_res.get("ok"):
            with _economy_lock, adm_mgr._users_lock:
                users = adm_mgr.load_users()
                u_red = users.get(str(oid))
                if u_red:
                    u_red["referral_rewarded"] = True
                u_inv = users.get(str(inviter_id))
                if u_inv:
                    u_inv["referred_count"] = int(u_inv.get("referred_count", 0)) + 1
                adm_mgr.save_users(users, sync_git=True)
            publish_event("users", inviter_id, "referral_rewarded")
            out["referral_inviter_id"] = inviter_id
            out["referral_awarded"] = ref_reward
            out["referral_inviter_balance"] = ref_res["balance"]

    return out


def estimate_mission_account_count(usable: list[dict], params: dict) -> int:
    selected_acc = str(params.get("selected_acc") or "all")
    usable_ids = {str(a.get("id")) for a in usable if a.get("id")}
    if selected_acc == "multi":
        raw_sel = params.get("selected_accs") or []
        picked = [str(x) for x in raw_sel if str(x) in usable_ids]
        if picked:
            return len(dict.fromkeys(picked))
        return 0
    if selected_acc != "all":
        return 1 if selected_acc in usable_ids else 0
    active = [a for a in usable if "نشط" in str(a.get("status", ""))]
    pool = active if active else usable
    if not pool:
        return 0
    limits = []
    for k in ("comment_acc_count", "react_acc_count", "acc_count_limit"):
        try:
            v = int(params.get(k, 0) or 0)
            if v > 0:
                limits.append(v)
        except Exception:
            pass
    if limits:
        return max(1, min(len(pool), max(limits)))
    return len(pool)


def calculate_mission_cost(mission_flags: dict, accounts_count: int = 1) -> tuple[int, list[tuple[str, int]]]:
    settings = load_economy_settings()
    costs = settings["operation_costs"]
    per_acc_cost = 0
    breakdown: list[tuple[str, int]] = []
    for op_k, op_lbl in OP_COST_LABELS_AR.items():
        if bool(mission_flags.get(op_k)):
            c = int(costs.get(op_k, DEFAULT_OP_COSTS.get(op_k, 1)))
            if c > 0:
                per_acc_cost += c
                breakdown.append((op_lbl, c))
    mult = max(1, int(accounts_count or 1))
    return per_acc_cost * mult, breakdown


def debit_points_for_mission(uid: int, mission_flags: dict, accounts_count: int, target_url: str = "") -> dict:
    """
    خصم تكلفة العملية ذرياً قبل التنفيذ إذا كان نظام النقاط مفعلاً أو البوت مفتوحاً للعامة.
    """
    enforced = is_points_enforced_for_user(uid)
    total_cost, breakdown = calculate_mission_cost(mission_flags, accounts_count)
    wallet = get_user_wallet(uid)
    if not enforced or total_cost <= 0:
        return {
            "ok": True,
            "enforced": enforced,
            "cost": 0,
            "balance": wallet["points"],
            "breakdown": breakdown,
        }

    ops_desc = " + ".join(f"{lbl}({c})" for lbl, c in breakdown) or "تشغيل ميداني"
    reason = f"تنفيذ [{ops_desc}] × {max(1, int(accounts_count))} حساب | {target_url[:50]}"
    res = adjust_user_points(
        target_uid=uid,
        delta=-total_cost,
        tx_type="MISSION_DEBIT",
        reason=reason,
        actor_uid=uid,
        extra={"accounts_count": accounts_count, "breakdown": breakdown},
    )
    if not res.get("ok"):
        res["required"] = total_cost
        res["enforced"] = True
        res["breakdown"] = breakdown
        return res
    res["cost"] = total_cost
    res["enforced"] = True
    res["breakdown"] = breakdown
    return res


def get_user_wallet(uid: int) -> dict:
    settings = load_economy_settings()
    rate = settings["yer_per_point"]
    users = adm_mgr.load_users()
    u = users.get(str(int(uid))) or {}
    pts = adm_mgr.safe_nonneg_points(u.get("points", 0))
    return {
        "user_id": int(uid),
        "points": pts,
        "yer_per_point": rate,
        "yer_value": int(round(float(pts) * rate)),
        "total_points_earned": adm_mgr.safe_nonneg_points(u.get("total_points_earned", 0)),
        "total_points_spent": adm_mgr.safe_nonneg_points(u.get("total_points_spent", 0)),
        "total_yer_settled": int(u.get("total_yer_settled", 0)),
        "referred_by": int(u.get("referred_by") or 0),
        "referral_rewarded": bool(u.get("referral_rewarded", False)),
        "referred_count": int(u.get("referred_count", 0)),
        "ref_code": str(u.get("ref_code") or ""),
        "profile_warnings_used": int(u.get("profile_warnings_used", 0)),
        "profile_warning_limit": int(settings.get("profile_warning_limit", 5)),
    }


# ----------------- نظام روابط وأكواد الإحالة والتفعيل -----------------

def _load_invite_codes_unlocked() -> list[dict]:
    data = _safe_load_json(INVITE_CODES_FILE, [])
    return [x for x in data if isinstance(x, dict)]


def get_or_create_personal_ref_code(owner_id: int) -> str:
    oid = int(owner_id)
    created = False
    code = ""
    with _economy_lock, adm_mgr._users_lock:
        users = adm_mgr.load_users()
        u = users.get(str(oid))
        if not u:
            return ""
        code = str(u.get("ref_code") or "").strip().upper()
        if not code:
            alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
            rand_part = "".join(secrets.choice(alphabet) for _ in range(6))
            code = f"U{str(oid)[-4:]}{rand_part}"
            u["ref_code"] = code
            adm_mgr.save_users(users, sync_git=True)
            created = True
    if created:
        publish_event("economy", oid, "ref_code_created")
    return code


def create_invite_code(owner_id: int, max_uses: int = 1, label: str = "") -> dict:
    oid = int(owner_id)
    if not can_user_invite(oid):
        return {"ok": False, "error": "ليس لديك صلاحية إنشاء أكواد إحالة."}
    uses_lim = _clamp_int(max_uses, 1, 1, 100)
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    p1 = "".join(secrets.choice(alphabet) for _ in range(4))
    p2 = "".join(secrets.choice(alphabet) for _ in range(4))
    code_str = f"FB-{p1}-{p2}"

    owners = adm_mgr.load_users()
    owner_name = str((owners.get(str(oid)) or {}).get("name") or oid)
    rec = {
        "code": code_str,
        "owner_id": oid,
        "owner_name": owner_name,
        "label": str(label or "")[:60],
        "max_uses": uses_lim,
        "uses": 0,
        "used_by": [],
        "status": "active",
        "created_at": _now_str(),
    }
    with _economy_lock:
        codes = _load_invite_codes_unlocked()
        codes.append(rec)
        if len(codes) > 1000:
            codes = codes[-1000:]
        _atomic_write_json(INVITE_CODES_FILE, codes)

    acc_mgr.git_sync_save(async_mode=True)
    adm_mgr.record_audit_log(oid, owner_name, "INVITE_CREATED", f"إنشاء كود إحالة وتفعيل حسابات: {code_str}")
    publish_event("economy", oid, "invite_created")
    return {"ok": True, "invite": rec}


def list_invite_codes_by_owner(owner_id: int) -> list[dict]:
    oid = int(owner_id)
    with _economy_lock:
        codes = _load_invite_codes_unlocked()
    return [c for c in codes if int(c.get("owner_id", 0)) == oid]


def revoke_invite_code(actor_id: int, code_str: str, is_dev: bool = False) -> bool:
    clean = str(code_str or "").strip().upper()
    ok = False
    owner_id = 0
    with _economy_lock:
        codes = _load_invite_codes_unlocked()
        for c in codes:
            if str(c.get("code", "")).upper() == clean:
                owner_id = int(c.get("owner_id", 0))
                if is_dev or owner_id == int(actor_id):
                    c["status"] = "revoked"
                    _atomic_write_json(INVITE_CODES_FILE, codes)
                    ok = True
                break
    if ok:
        acc_mgr.git_sync_save(async_mode=True)
        publish_event("economy", owner_id, "invite_revoked")
    return ok


def looks_like_invite_token(text: str) -> bool:
    t = str(text or "").strip().upper()
    if t.startswith("REF_"):
        t = t[4:]
    return bool(t.startswith("FB-") and 8 <= len(t) <= 24)


def redeem_invite_code(redeemer_id: int, raw_token: str, user_name: str = "", username: str = "") -> dict:
    """
    استخدام رابط أو كود إحالة:
    - يتحقق من صحة الكود ومنع استغلال الإحالة الذاتية أو إحالة حساب معتمد مسبقاً أو محظور.
    - يفتح للمدعو ميزة 'إضافة حسابات فيسبوك فقط' (can_add_accounts=True) بدون أي صلاحيات خطرة أخرى.
    - يربط المدعو بالمُحيل دائماً، ويصرف +4 نقاط إما فوراً (حسب الإعداد) أو عند أول حساب فيسبوك نشط يفعله المدعو.
    """
    rid = int(redeemer_id)
    token = str(raw_token or "").strip()
    if token.lower().startswith("ref_"):
        token = token[4:].strip()
    token_upper = token.upper()
    if not token_upper or len(token_upper) < 4:
        return {"ok": False, "error": "كود الإحالة غير صالح."}

    # ضمان وجود سجل المستخدم قبل المطابقة
    adm_mgr.register_or_update_user(rid, user_name or f"مستخدم_{rid}", username, touch_login=False)

    settings = load_economy_settings()
    inviter_id = 0
    inviter_name = ""
    matched_source = ""

    with _economy_lock:
        codes = _load_invite_codes_unlocked()
        matched_code_rec = None
        for c in codes:
            if str(c.get("code", "")).upper() == token_upper:
                matched_code_rec = c
                break

        with adm_mgr._users_lock:
            users = adm_mgr.load_users()
            u_red = users.get(str(rid))
            if not u_red:
                return {"ok": False, "error": "تعذر العثور على سجل المستخدم."}
            if adm_mgr.is_super_admin(rid):
                return {"ok": False, "error": "المطور الرئيسي لا يحتاج كود إحالة."}
            if u_red.get("status") == "banned":
                return {"ok": False, "error": "تم حظر حسابك نهائياً ولا يمكن تفعيله بكود."}
            if u_red.get("referred_by"):
                return {"ok": False, "error": "تم تفعيل حسابك مسبقاً عبر إحالة أخرى."}

            # منع من لديه مسبقاً حساب معتمد مع صلاحيات من إعادة التحايل بالكود
            existing_perms = u_red.get("permissions", {})
            if u_red.get("status") == "approved" and any(existing_perms.values()):
                return {"ok": False, "error": "حسابك مفعل ومعتمد مسبقاً ولا يحتاج لكود دعوة."}

            if matched_code_rec is not None:
                if matched_code_rec.get("status") != "active" or int(matched_code_rec.get("uses", 0)) >= int(matched_code_rec.get("max_uses", 1)):
                    return {"ok": False, "error": "هذا الكود مستخدم مسبقاً أو منتهي الصلاحية."}
                inviter_id = int(matched_code_rec.get("owner_id", 0))
                inviter_name = str(matched_code_rec.get("owner_name", inviter_id))
                matched_source = matched_code_rec["code"]
            else:
                # دعم رابط الإحالة الشخصي ref_<ref_code> أو ref_<uid>
                for uk, uv in users.items():
                    if str(uv.get("ref_code", "")).upper() == token_upper or (token_upper.isdigit() and str(uv.get("id")) == token_upper):
                        inviter_id = int(uv.get("id", 0))
                        inviter_name = str(uv.get("name", inviter_id))
                        matched_source = f"LINK:{uv.get('ref_code') or inviter_id}"
                        break

            if not inviter_id:
                return {"ok": False, "error": "كود أو رابط الإحالة غير صحيح أو غير موجود."}
            if inviter_id == rid:
                return {"ok": False, "error": "لا يمكنك استخدام رابط أو كود الإحالة الخاص بك!"}

            inviter_rec = users.get(str(inviter_id))
            if not inviter_rec or (not adm_mgr.is_super_admin(inviter_id) and inviter_rec.get("status") != "approved"):
                return {"ok": False, "error": "صاحب كود الإحالة غير نشط حالياً."}
            if not adm_mgr.is_super_admin(inviter_id):
                inv_perms = inviter_rec.get("permissions", {})
                if not (inv_perms.get("can_invite") or (settings.get("suppliers_can_invite", True) and inv_perms.get("can_add_accounts"))):
                    return {"ok": False, "error": "صاحب الكود لا يملك صلاحية الإحالة حالياً."}

            # تطبيق فتح ميزة إضافة حسابات فيسبوك فقط بشكل صارم
            new_perms = dict(adm_mgr.DEFAULT_PERMISSIONS)
            new_perms["can_add_accounts"] = True
            if settings.get("invited_suppliers_can_invite", True):
                new_perms["can_invite"] = True

            u_red["status"] = "approved"
            u_red["role"] = "user"
            u_red["permissions"] = new_perms
            u_red["referred_by"] = inviter_id
            u_red["referral_code_used"] = matched_source
            u_red["referral_rewarded"] = False

            if matched_code_rec is not None:
                matched_code_rec["uses"] = int(matched_code_rec.get("uses", 0)) + 1
                used_list = matched_code_rec.setdefault("used_by", [])
                used_list.append({"uid": rid, "name": u_red.get("name", ""), "at": _now_str()})
                if matched_code_rec["uses"] >= int(matched_code_rec.get("max_uses", 1)):
                    matched_code_rec["status"] = "used"
                _atomic_write_json(INVITE_CODES_FILE, codes)

            adm_mgr.save_users(users, sync_git=True)

    instant_bonus = 0
    if settings.get("referral_trigger") == "instant" and settings["referral_reward"] > 0:
        ref_res = adjust_user_points(
            target_uid=inviter_id,
            delta=settings["referral_reward"],
            tx_type="REFERRAL_REWARD",
            reason=f"مكافأة إحالة فورية عند دخول {u_red.get('name', rid)} ({rid})",
            actor_uid=rid,
            idempotency_key=f"ref_bonus:{rid}",
            extra={"referred_uid": rid},
        )
        if ref_res.get("ok"):
            instant_bonus = settings["referral_reward"]
            with _economy_lock, adm_mgr._users_lock:
                users = adm_mgr.load_users()
                if str(rid) in users:
                    users[str(rid)]["referral_rewarded"] = True
                if str(inviter_id) in users:
                    users[str(inviter_id)]["referred_count"] = int(users[str(inviter_id)].get("referred_count", 0)) + 1
                adm_mgr.save_users(users, sync_git=True)

    adm_mgr.record_audit_log(
        rid,
        str(user_name or rid),
        "REFERRAL_JOINED",
        f"انضمام عبر إحالة {inviter_name} ({inviter_id}) بالكود {matched_source} — تفعيل إضافة الحسابات فقط",
    )
    publish_event("users", rid, "referral_redeemed")
    publish_event("economy", inviter_id, "referral_joined")
    return {
        "ok": True,
        "inviter_id": inviter_id,
        "inviter_name": inviter_name,
        "code": matched_source,
        "instant_bonus": instant_bonus,
        "referral_trigger": settings["referral_trigger"],
        "referral_reward": settings["referral_reward"],
    }


# ----------------- تذاكر الدعم والموافقة على بيع الحسابات والمحاسبة ثنائية الاتجاه -----------------

def _load_tickets_unlocked() -> list[dict]:
    data = _safe_load_json(SUPPORT_TICKETS_FILE, [])
    return [x for x in data if isinstance(x, dict)]


def build_user_settlement_snapshot(uid: int) -> dict:
    settings = load_economy_settings()
    rate = settings["yer_per_point"]
    users = adm_mgr.load_users()
    u = users.get(str(int(uid))) or {}
    bd = acc_mgr.get_accounts_breakdown_by_owner(int(uid))
    pts = adm_mgr.safe_nonneg_points(u.get("points", 0))
    return {
        "user_id": int(uid),
        "name": str(u.get("name", f"مستخدم_{uid}")),
        "username": str(u.get("username", "")),
        "points": pts,
        "yer_per_point": rate,
        "yer_value": int(round(float(pts) * rate)),
        "total_added": len(bd["all"]),
        "active_added": len(bd["active"]),
        "inactive_added": len(bd["inactive"]),
        "historical_active": int(u.get("active_accounts_added", 0)),
        "historical_inactive": int(u.get("inactive_accounts_added", 0)),
        "total_yer_settled": int(u.get("total_yer_settled", 0)),
        "referred_count": int(u.get("referred_count", 0)),
    }


def create_support_ticket(uid: int, kind: str, message_text: str) -> dict:
    clean_msg = str(message_text or "").strip()[:2000]
    if not clean_msg:
        return {"ok": False, "error": "اكتب نص الرسالة أولاً."}
    norm_kind = "sell_accounts" if kind == "sell_accounts" else "support"
    snap = build_user_settlement_snapshot(uid)
    now_s = _now_str()
    tkt = {
        "id": _gen_id("TKT", 6),
        "user_id": int(uid),
        "user_name": snap["name"],
        "user_username": snap["username"],
        "kind": norm_kind,
        "sale_agreed": norm_kind == "sell_accounts",
        "status": "open",
        "created_at": now_s,
        "updated_at": now_s,
        "snapshot": snap,
        "messages": [
            {
                "sender": "user",
                "sender_uid": int(uid),
                "sender_name": snap["name"],
                "text": clean_msg,
                "timestamp": now_s,
            }
        ],
    }
    with _economy_lock:
        tickets = _load_tickets_unlocked()
        tickets.append(tkt)
        if len(tickets) > 500:
            tickets = tickets[-500:]
        _atomic_write_json(SUPPORT_TICKETS_FILE, tickets)

    acc_mgr.git_sync_save(async_mode=True)
    ev = "SUPPORT_SELL_REQUEST" if norm_kind == "sell_accounts" else "SUPPORT_MESSAGE"
    adm_mgr.record_audit_log(
        uid,
        snap["name"],
        ev,
        f"تذكرة {tkt['id']} | الحسابات: 🟢{snap['active_added']} 🔴{snap['inactive_added']} | النقاط: {snap['points']} ({snap['yer_value']} ريال)",
    )
    publish_event("support", int(uid), "ticket_created")
    return {"ok": True, "ticket": tkt}


def reply_support_ticket(ticket_id: str, sender_uid: int, message_text: str, is_dev: bool = False) -> dict:
    clean_msg = str(message_text or "").strip()[:2000]
    if not clean_msg:
        return {"ok": False, "error": "لا يمكن إرسال رد فارغ."}

    updated_tkt = None
    target_uid = 0
    with _economy_lock:
        tickets = _load_tickets_unlocked()
        for t in tickets:
            if t.get("id") == ticket_id:
                target_uid = int(t.get("user_id", 0))
                if not is_dev and target_uid != int(sender_uid):
                    return {"ok": False, "error": "forbidden"}
                now_s = _now_str()
                sender_role = "developer" if is_dev else "user"
                sender_name = "👑 المطور / الدعم" if is_dev else str(t.get("user_name") or sender_uid)
                t.setdefault("messages", []).append({
                    "sender": sender_role,
                    "sender_uid": int(sender_uid),
                    "sender_name": sender_name,
                    "text": clean_msg,
                    "timestamp": now_s,
                })
                t["status"] = "replied_by_dev" if is_dev else "replied_by_user"
                t["updated_at"] = now_s
                t["snapshot"] = build_user_settlement_snapshot(target_uid)
                updated_tkt = dict(t)
                _atomic_write_json(SUPPORT_TICKETS_FILE, tickets)
                break

    if not updated_tkt:
        return {"ok": False, "error": "التذكرة غير موجودة."}

    acc_mgr.git_sync_save(async_mode=True)
    adm_mgr.record_audit_log(
        sender_uid,
        "المطور" if is_dev else updated_tkt["user_name"],
        "SUPPORT_REPLY",
        f"رد على التذكرة {ticket_id}: {clean_msg[:80]}",
    )
    publish_event("support", target_uid, "ticket_reply")
    return {"ok": True, "ticket": updated_tkt}


def settle_payout(
    target_uid: int,
    settle_points: int | float | None,
    actor_uid: int,
    ticket_id: str | None = None,
    note: str = "تسوية ومحاسبة مالية معتمدة",
) -> dict:
    tid = int(target_uid)
    wallet = get_user_wallet(tid)
    pts_to_settle = wallet["points"] if settle_points is None else adm_mgr.safe_nonneg_points(settle_points)
    if pts_to_settle <= 0:
        return {"ok": False, "error": "لا توجد نقاط موجبة للتسوية أو القيمة المطلوبة صفر."}

    res = adjust_user_points(
        target_uid=tid,
        delta=-pts_to_settle,
        tx_type="PAYOUT_SETTLED",
        reason=note,
        actor_uid=actor_uid,
        mark_settled_yer=True,
        extra={"ticket_id": ticket_id or ""},
    )
    if not res.get("ok"):
        return res

    settled_tkt = None
    if ticket_id:
        with _economy_lock:
            tickets = _load_tickets_unlocked()
            for t in tickets:
                if t.get("id") == ticket_id and int(t.get("user_id", 0)) == tid:
                    now_s = _now_str()
                    t["status"] = "settled"
                    t["updated_at"] = now_s
                    t.setdefault("messages", []).append({
                        "sender": "developer",
                        "sender_uid": int(actor_uid),
                        "sender_name": "🧾 إشعار محاسبة رسمي",
                        "text": f"تم اعتماد صرف وتصفية {pts_to_settle} نقطة ({res['yer_delta']:,} ريال يمني). الرصيد المتبقي: {res['balance']} نقطة.",
                        "timestamp": now_s,
                    })
                    t["snapshot"] = build_user_settlement_snapshot(tid)
                    settled_tkt = dict(t)
                    _atomic_write_json(SUPPORT_TICKETS_FILE, tickets)
                    break

    publish_event("support", tid, "payout_settled")
    return {
        "ok": True,
        "points_settled": pts_to_settle,
        "yer_paid": res["yer_delta"],
        "remaining_points": res["balance"],
        "remaining_yer": res["yer_value"],
        "ticket": settled_tkt,
    }


def list_support_tickets(viewer_uid: int, is_dev: bool = False, limit: int = 50) -> list[dict]:
    with _economy_lock:
        tickets = _load_tickets_unlocked()
    if not is_dev:
        vid = int(viewer_uid)
        tickets = [t for t in tickets if int(t.get("user_id", 0)) == vid]
    # إرفاق أحدث لقطة أرقام للمستخدم عند العرض
    out = []
    for t in reversed(tickets):
        copy_t = dict(t)
        copy_t["live_snapshot"] = build_user_settlement_snapshot(int(t.get("user_id", 0)))
        out.append(copy_t)
        if limit and len(out) >= limit:
            break
    return out


def get_ticket_by_id(ticket_id: str) -> dict | None:
    with _economy_lock:
        tickets = _load_tickets_unlocked()
    for t in tickets:
        if t.get("id") == ticket_id:
            copy_t = dict(t)
            copy_t["live_snapshot"] = build_user_settlement_snapshot(int(t.get("user_id", 0)))
            return copy_t
    return None


def list_active_wallets() -> list[dict]:
    """قائمة المحافظ المفعلة والمتاحة للمستخدمين لشراء النقاط."""
    cfg = load_economy_settings()
    return [w for w in cfg.get("wallets", []) if w.get("active", True)]


def get_all_wallets() -> list[dict]:
    """كافة المحافظ المضافة (المفعلة والمعطلة) لإدارة المطور."""
    cfg = load_economy_settings()
    return list(cfg.get("wallets", []))


def get_wallet_by_id(w_id: str) -> dict | None:
    """جلب بيانات محفظة معينة عبر معرفها."""
    cfg = load_economy_settings()
    target = str(w_id).strip().lower()
    for w in cfg.get("wallets", []):
        if str(w.get("id", "")).strip().lower() == target:
            return w
    return None


def add_custom_wallet(name: str, number: str, beneficiary: str, notes: str = "", actor_uid: int = 0) -> dict:
    """إضافة محفظة دفع جديدة بواسطة المطور."""
    cfg = load_economy_settings()
    wallets = list(cfg.get("wallets", []))
    w_id = f"w_{int(time.time())}"
    new_w = {
        "id": w_id,
        "name": str(name).strip(),
        "number": str(number).strip(),
        "beneficiary": str(beneficiary).strip(),
        "notes": str(notes).strip(),
        "active": True
    }
    wallets.append(new_w)
    update_economy_settings({"wallets": wallets}, actor_uid=actor_uid)
    if actor_uid:
        adm_mgr.record_audit_log(actor_uid, "المطور", "WALLET_ADD", f"إضافة محفظة دفع جديدة: {name} ({number})")
    return new_w


def delete_custom_wallet(w_id: str, actor_uid: int = 0) -> bool:
    """حذف محفظة مخصصة بواسطة المطور."""
    cfg = load_economy_settings()
    wallets = list(cfg.get("wallets", []))
    target = str(w_id).strip().lower()
    new_wallets = [w for w in wallets if str(w.get("id", "")).strip().lower() != target]
    if len(new_wallets) != len(wallets):
        update_economy_settings({"wallets": new_wallets}, actor_uid=actor_uid)
        if actor_uid:
            adm_mgr.record_audit_log(actor_uid, "المطور", "WALLET_DELETE", f"حذف محفظة الدفع: {w_id}")
        return True
    return False


def toggle_wallet(w_id: str, actor_uid: int = 0) -> bool:
    """تفعيل أو تعطيل ظهور المحفظة للمستخدمين."""
    cfg = load_economy_settings()
    wallets = list(cfg.get("wallets", []))
    target = str(w_id).strip().lower()
    new_status = False
    found = False
    for w in wallets:
        if str(w.get("id", "")).strip().lower() == target:
            w["active"] = not bool(w.get("active", True))
            new_status = w["active"]
            found = True
            break
    if found:
        update_economy_settings({"wallets": wallets}, actor_uid=actor_uid)
        if actor_uid:
            adm_mgr.record_audit_log(actor_uid, "المطور", "WALLET_TOGGLE", f"تغيير حالة المحفظة {w_id} إلى: {new_status}")
    return new_status


def get_sales_recipient() -> tuple[int, str]:
    """معرف وحساب تليجرام المخصص لاستقبال استفسارات وسندات شراء النقاط."""
    cfg = load_economy_settings()
    raw_id = cfg.get("sales_recipient_id")
    try:
        s_id = int(raw_id) if raw_id else 7411444902
    except Exception:
        s_id = 7411444902
    s_uname = str(cfg.get("sales_recipient_username") or "").strip().lstrip("@")
    return s_id, s_uname


def set_sales_recipient(sales_id: int, username: str = "", actor_uid: int = 0) -> dict:
    """تغيير وجهة استقبال المبيعات إلى أي حساب تليجرام آخر عبر الآيدي."""
    patch = {
        "sales_recipient_id": int(sales_id),
        "sales_recipient_username": str(username).strip().lstrip("@")
    }
    update_economy_settings(patch, actor_uid=actor_uid)
    if actor_uid:
        adm_mgr.record_audit_log(actor_uid, "المطور", "SALES_RECIPIENT", f"تعيين وجهة المبيعات: ID={sales_id}, User=@{username}")
    return patch

