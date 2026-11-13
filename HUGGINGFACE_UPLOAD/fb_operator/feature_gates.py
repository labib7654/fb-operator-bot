# -*- coding: utf-8 -*-
"""
محرك إدارة وبوابات الميزات المستقبلية (Feature Gates & Extensibility Engine)
---------------------------------------------------------------------------
يتيح للمطور الأكبر التحكم بكل ميزة حالية أو مستقبلية:
1. نطاق الوصول: (public = عامة للجميع | admins = للمطور والأدمن فقط | specific = لأشخاص محددين بالـ ID).
2. نموذج التسعير: (free = مجانية بدون رصيد | points = خصم نقاط محددة عند كل تشغيل).
3. حالة الميزة: (active = نشطة | disabled = معطلة مؤقتاً | beta = تجريبية | coming_soon = قيد التطوير).
4. إضافة ميزات عالمية جديدة ديناميكياً (مثل الإيميلات، الذكاء الاصطناعي، وغيرها).
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

import fb_operator.config as config
from fb_operator.state_events import publish_event

_feature_lock = threading.RLock()

FEATURE_GATES_FILE = config.FEATURE_GATES_FILE


class ResultDict(dict):
    """قاموس يدعم التحقق الشرطي المنطقي bool(r) واستدعاء .get('ok') في آن واحد"""
    def __bool__(self) -> bool:
        return bool(self.get("ok", True))


DEFAULT_FEATURES: dict[str, dict[str, Any]] = {
    "tempmail": {
        "id": "tempmail",
        "title": "البريد المؤقت",
        "description": "إنشاء إيميلات مؤقتة واستقبال أكواد التفعيل والرسائل.",
        "category": "البريد",
        "status": "active",
        "access_scope": "public",
        "pricing_type": "free",
        "points_cost": 0,
        "allowed_user_ids": [],
    },
    "fb_tools": {
        "id": "fb_tools",
        "title": "تفاعل فيسبوك",
        "description": "التفاعل والتعليق والمتابعة على منشورات وحسابات فيسبوك.",
        "category": "فيسبوك",
        "status": "active",
        "access_scope": "admins",
        "pricing_type": "points",
        "points_cost": 1,
        "allowed_user_ids": [],
    },
    "public_account_addition": {
        "id": "public_account_addition",
        "title": "إضافة حسابات",
        "description": "إضافة وتوريد الحسابات مع دليل احتساب النقاط.",
        "category": "الحسابات",
        "status": "active",
        "access_scope": "public",
        "pricing_type": "free",
        "points_cost": 0,
        "allowed_user_ids": [],
    },
    "proxy_tunnel": {
        "id": "proxy_tunnel",
        "title": "البروكسيات",
        "description": "إدارة وتوزيع البروكسيات للحسابات.",
        "category": "الشبكات",
        "status": "active",
        "access_scope": "admins",
        "pricing_type": "free",
        "points_cost": 0,
        "allowed_user_ids": [],
    },
    "live_hitl": {
        "id": "live_hitl",
        "title": "الشاشة الحية",
        "description": "عرض شاشة المتصفح لحل كابتشا فيسبوك يدوياً.",
        "category": "الأمان",
        "status": "active",
        "access_scope": "admins",
        "pricing_type": "free",
        "points_cost": 0,
        "allowed_user_ids": [],
    },
    "yemen_caller_id": {
        "id": "yemen_caller_id",
        "title": "كاشف الأرقام",
        "description": "معرفة اسم المتصل والشبكة لجميع الأرقام اليمنية.",
        "category": "أدوات",
        "status": "active",
        "access_scope": "public",
        "pricing_type": "free",
        "points_cost": 0,
        "allowed_user_ids": [],
    },
    "email_campaigns": {
        "id": "email_campaigns",
        "title": "حملات البريد",
        "description": "إرسال رسائل بريدية جماعية.",
        "category": "تسويق",
        "status": "coming_soon",
        "access_scope": "admins",
        "pricing_type": "points",
        "points_cost": 5,
        "allowed_user_ids": [],
    },
    "auto_account_creator": {
        "id": "auto_account_creator",
        "title": "صانع الحسابات",
        "description": "إنشاء حسابات فيسبوك تلقائياً.",
        "category": "أتمتة",
        "status": "coming_soon",
        "access_scope": "admins",
        "pricing_type": "points",
        "points_cost": 10,
        "allowed_user_ids": [],
    }
}


def _get_file_path() -> Path:
    p = globals().get("FEATURE_GATES_FILE") or getattr(config, "FEATURE_GATES_FILE", None)
    return Path(p or config.DATA_DIR / "feature_gates.json")


def _atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(f".tmp_{os.getpid()}_{threading.get_ident()}")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)


def load_feature_gates() -> dict[str, dict[str, Any]]:
    with _feature_lock:
        p = _get_file_path()
        if not p.exists():
            gates = dict(DEFAULT_FEATURES)
            try:
                _atomic_write_json(p, gates)
            except Exception:
                pass
            return gates
        try:
            with open(p, "r", encoding="utf-8") as f:
                raw = json.load(f)
            if not isinstance(raw, dict):
                raw = {}
        except Exception:
            raw = {}

        # دمج الميزات الافتراضية مع أي ميزات جديدة مضافة مستقبلاً
        merged: dict[str, dict[str, Any]] = {}
        for fid, def_f in DEFAULT_FEATURES.items():
            saved_f = raw.get(fid)
            if isinstance(saved_f, dict):
                item = dict(def_f)
                item.update(saved_f)
                merged[fid] = item
            else:
                merged[fid] = dict(def_f)

        for fid, custom_f in raw.items():
            if fid not in merged and isinstance(custom_f, dict):
                merged[fid] = custom_f

        return merged


def save_feature_gates(gates: dict[str, dict[str, Any]], notify: bool = True) -> None:
    with _feature_lock:
        p = _get_file_path()
        _atomic_write_json(p, gates)
    if notify:
        try:
            from fb_operator.persistence_manager import notify_data_changed
            notify_data_changed("feature_gates")
        except Exception:
            pass
        publish_event("feature_gates", 0, "gates_updated")


def list_features(viewer_id: int = 0) -> list[dict[str, Any]]:
    gates = load_feature_gates()
    res: list[dict[str, Any]] = []
    is_dev = False
    try:
        from fb_operator.admin_manager import is_super_admin
        is_dev = is_super_admin(viewer_id)
    except Exception:
        pass
    for fid, f in gates.items():
        accessible, reason = check_feature_access(viewer_id, fid)
        item = dict(f)
        item["is_accessible"] = accessible
        item["inaccessibility_reason"] = reason
        if not is_dev and f.get("status") == "coming_soon" and not accessible:
            item["display_badge"] = "قريباً ⏳"
        elif accessible:
            item["display_badge"] = "متاح لك ✅"
        else:
            item["display_badge"] = "مقيد 🔒"
        res.append(item)
    return res


def get_feature(feature_id: str) -> dict[str, Any] | None:
    gates = load_feature_gates()
    return gates.get(str(feature_id or "").strip())


def check_feature_access(user_id: int, feature_id: str) -> tuple[bool, str]:
    """فحص وصول المستخدم للميزة مع ذكر السبب بالتفصيل: المطور الأكبر يملك حق الوصول دائماً."""
    uid = int(user_id)
    try:
        from fb_operator.admin_manager import is_super_admin
        if is_super_admin(uid):
            return True, ""
    except Exception:
        pass

    gates = load_feature_gates()
    f = gates.get(feature_id)
    if not f:
        return False, "الميزة غير موجودة في سجل النظام."

    st = str(f.get("status") or "active").lower()
    if st == "disabled":
        return False, f"ميزة '{f.get('title')}' معطلة مؤقتاً للصيانة والتحديث."
    if st == "coming_soon":
        allowed_uids = [int(x) for x in (f.get("allowed_user_ids") or [])]
        if uid in allowed_uids:
            return True, ""
        return False, f"ميزة '{f.get('title')}' قيد التطوير والتجهيز وستتاح قريباً."

    allowed_uids = [int(x) for x in (f.get("allowed_user_ids") or [])]
    if uid in allowed_uids:
        return True, ""

    scope = str(f.get("access_scope") or "admins").lower()
    if scope == "public":
        return True, ""

    if scope == "admins":
        from fb_operator.admin_manager import is_admin_delegate
        if is_admin_delegate(uid, include_manager=True):
            return True, ""
        return False, f"ميزة '{f.get('title')}' مخصصة للإدارة والمطور فقط."

    if scope == "specific":
        allowed_uids = [int(x) for x in (f.get("allowed_user_ids") or [])]
        if uid in allowed_uids:
            return True, ""
        return False, f"ميزة '{f.get('title')}' مخصصة لمستخدمين محددين حالياً."

    return False, "لا تملك تصريحاً لاستخدام هذه الميزة."


def is_feature_accessible(arg1: Any, arg2: Any) -> bool:
    """دالة فحص مرنة تقبل (user_id, feature_id) أو (feature_id, user_id) وتعيد True/False مباشرة"""
    if isinstance(arg1, int) or (isinstance(arg1, str) and arg1.isdigit()):
        uid = int(arg1)
        fid = str(arg2)
    else:
        fid = str(arg1)
        uid = int(arg2)
    acc, _ = check_feature_access(uid, fid)
    return acc


# اسم بديل متطابق للتوافق الشامل
is_feature_enabled = is_feature_accessible


def get_feature_cost(feature_id: str, user_id: int = 0) -> int:
    f = get_feature(feature_id)
    if not f:
        return 0
    if f.get("pricing_type") == "points":
        return max(0, int(f.get("points_cost") or 0))
    return 0


def update_feature_gate(feature_id: str, patch: dict[str, Any], actor_id: int = 0) -> ResultDict:
    with _feature_lock:
        gates = load_feature_gates()
        f = gates.get(feature_id)
        if not f:
            return ResultDict(ok=False, error=f"الميزة غير موجودة: {feature_id}")

        if "status" in patch:
            new_st = str(patch["status"]).lower()
            if new_st in ("active", "disabled", "beta", "coming_soon"):
                f["status"] = new_st

        # دعم access_scope و scope
        scope_val = patch.get("access_scope") or patch.get("scope")
        if scope_val:
            new_sc = str(scope_val).lower()
            if new_sc in ("public", "admins", "specific"):
                f["access_scope"] = new_sc

        # دعم pricing_type و pricing
        pricing_val = patch.get("pricing_type") or patch.get("pricing")
        if pricing_val:
            new_pr = str(pricing_val).lower()
            if new_pr in ("free", "points"):
                f["pricing_type"] = new_pr

        if "points_cost" in patch:
            try:
                f["points_cost"] = max(0, min(1000, int(patch["points_cost"])))
            except Exception:
                pass

        if "allowed_user_ids" in patch and isinstance(patch["allowed_user_ids"], (list, tuple, set)):
            clean_ids = []
            for u in patch["allowed_user_ids"]:
                try:
                    clean_ids.append(int(u))
                except Exception:
                    pass
            f["allowed_user_ids"] = list(set(clean_ids))

        if "title" in patch and str(patch["title"]).strip():
            f["title"] = str(patch["title"]).strip()[:80]

        if "description" in patch:
            f["description"] = str(patch["description"]).strip()[:200]

        save_feature_gates(gates)
        res = ResultDict(f)
        res["ok"] = True
        return res


def add_allowed_user(feature_id: str, target_uid: int) -> ResultDict:
    with _feature_lock:
        gates = load_feature_gates()
        f = gates.get(feature_id)
        if not f:
            return ResultDict(ok=False, error="الميزة غير موجودة")
        uids = [int(x) for x in (f.get("allowed_user_ids") or [])]
        target_int = int(target_uid)
        if target_int not in uids:
            uids.append(target_int)
            f["allowed_user_ids"] = uids
            save_feature_gates(gates)
            return ResultDict(ok=True)
        return ResultDict(ok=True, already_present=True)


def remove_allowed_user(feature_id: str, target_uid: int) -> ResultDict:
    with _feature_lock:
        gates = load_feature_gates()
        f = gates.get(feature_id)
        if not f:
            return ResultDict(ok=False, error="الميزة غير موجودة")
        uids = [int(x) for x in (f.get("allowed_user_ids") or [])]
        target_int = int(target_uid)
        if target_int in uids:
            uids = [x for x in uids if x != target_int]
            f["allowed_user_ids"] = uids
            save_feature_gates(gates)
            return ResultDict(ok=True)
        return ResultDict(ok=True, already_absent=True)


def register_custom_feature(
    feature_id: str,
    title: str = "",
    description: str = "",
    category: str = "ميزات عامة",
    access_scope: str = "admins",
    pricing_type: str = "free",
    points_cost: int = 0,
    status: str = "active",
    **kwargs: Any,
) -> ResultDict:
    """تسجيل ميزة جديدة في المنظومة وإتاحة بوابتها فوراً للإدارة والتسعير."""
    fid = str(feature_id or "").strip().lower()
    if not fid:
        return ResultDict(ok=False, error="معرّف الميزة مطلوب.")

    t_val = title or kwargs.get("name") or fid
    sc_val = kwargs.get("scope") or access_scope
    pr_val = kwargs.get("pricing") or pricing_type

    with _feature_lock:
        gates = load_feature_gates()
        new_f: dict[str, Any] = {
            "id": fid,
            "title": str(t_val).strip()[:80],
            "description": str(description or "").strip()[:200],
            "category": str(category or "ميزات عامة").strip()[:50],
            "status": status if status in ("active", "disabled", "beta", "coming_soon") else "active",
            "access_scope": sc_val if sc_val in ("public", "admins", "specific") else "admins",
            "pricing_type": pr_val if pr_val in ("free", "points") else "free",
            "points_cost": max(0, min(1000, int(points_cost or 0))),
            "allowed_user_ids": [],
        }
        gates[fid] = new_f
        save_feature_gates(gates)
        res = ResultDict(new_f)
        res["ok"] = True
        return res
