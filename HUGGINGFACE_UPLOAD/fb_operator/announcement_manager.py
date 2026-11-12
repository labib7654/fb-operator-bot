# -*- coding: utf-8 -*-
"""
محرك الإعلانات العائمة والبطاقات التفاعلية المتقدمة (Floating Feature Announcements Engine)
----------------------------------------------------------------------------------------
يتيح للمطور الأكبر (والأدمن المفوّض غير المقيد) إنشاء إعلانات مميزات وتحديثات تظهر:
1. عائماً في اللوحة التفاعلية (<dialog> Top-Layer متحرك + شريط معلق + تنبيه متكرر).
2. مثبّتاً وعائماً أعلى دردشة تلغرام (Pin Message + بطاقات وأزرار تفاعلية).
3. بتحكم كامل: تفعيل، إيقاف، إزالة فورية مع فك التثبيت للجميع، جدولة فترة محددة تلقائية الانتهاء،
   وتكرار دوري منتظم حتى انتهاء المدة أو الإزالة.
"""
from __future__ import annotations

import json
import os
import secrets
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import fb_operator.config as config
from fb_operator.state_events import publish_event

_ann_lock = threading.RLock()

BADGE_OPTIONS = (
    "ميزة جديدة",
    "تحديث مهم",
    "تنبيه عاجل",
    "عرض محدود",
)

STYLE_OPTIONS = {
    "floating_card": "🪟 بطاقة عائمة منبثقة (تظهر فوق الواجهة)",
    "top_ribbon": "📣 شريط معلق عائم أعلى الشاشة + تنبيه",
    "full_spotlight": "✨ نافذة عرض موسّعة للميزة",
}

DELIVERY_MODES = {
    "animated_card": "🎞️ بطاقة GIF متحركة + أزرار ملونة",
    "photo_card": "🖼️ بطاقة HD صورية + أزرار ملونة",
    "smart_text": "💬 بطاقة <blockquote> ذكية + أزرار ملونة",
}

REPEAT_BEHAVIORS = {
    "replace": "♻️ استبدال نظيف (تحذف السابقة بلا تكدس)",
    "edit_live": "⚡ تحديث حي في نفس الرسالة (بدون أي تكرار)",
    "new_msg": "📨 إرسال تنبيه جديد كل مرة",
}

EFFECT_PRESETS = {
    "none": ("بدون تأثير حركي", ""),
    "fire": ("🔥 لهب وحماس", "5104841245755180586"),
    "heart": ("❤️ احتفال وقلوب", "5044134455711629726"),
    "thumb": ("👍 إعجاب متطاير", "5107584321108051014"),
}

DEFAULT_THEME_EMOJIS = {
    "rocket": "",
    "spark": "",
    "check": "",
    "shield": "",
    "fb": "",
    "proxy": "",
    "alert": "",
}

DURATION_PRESETS = (
    (900, "15 دقيقة"),
    (3600, "ساعة واحدة"),
    (21600, "6 ساعات"),
    (86400, "24 ساعة (يوم)"),
    (604800, "7 أيام"),
    (0, "دائم حتى يزيله المطور"),
)

REPEAT_PRESETS = (
    (0, "مرة واحدة بدون تكرار آلي"),
    (300, "متكرر كل 5 دقائق"),
    (1800, "متكرر كل 30 دقيقة"),
    (3600, "متكرر كل ساعة"),
    (21600, "متكرر كل 6 ساعات"),
    (86400, "متكرر يومياً"),
)


def _announcements_path() -> Path:
    return Path(getattr(config, "ANNOUNCEMENTS_FILE", Path(config.DATA_DIR) / "announcements.json"))


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(f".json.tmp.{threading.get_ident()}")
    raw = json.dumps(payload, ensure_ascii=False, indent=2)
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(raw)
        f.flush()
        try:
            os.fsync(f.fileno())
        except Exception:
            pass
    os.replace(tmp, path)


def _notify_persistence_and_clients(reason: str) -> None:
    try:
        from fb_operator.persistence_manager import notify_data_changed
        notify_data_changed(reason)
    except Exception:
        pass
    try:
        publish_event("announcements", 0, reason)
    except Exception:
        pass


def format_duration_ar(sec: int) -> str:
    s = max(0, int(sec or 0))
    if s == 0:
        return "دائم حتى الإزالة"
    if s < 60:
        return f"{s} ثانية"
    if s < 3600:
        return f"{s // 60} دقيقة"
    if s < 86400:
        h = s // 3600
        m = (s % 3600) // 60
        return f"{h} ساعة" + (f" و{m} د" if m else "")
    d = s // 86400
    h = (s % 86400) // 3600
    return f"{d} يوم" + (f" و{h} س" if h else "")


def _normalize_theme(raw: Any) -> dict[str, Any]:
    src = raw if isinstance(raw, dict) else {}
    emojis_raw = src.get("emojis") if isinstance(src.get("emojis"), dict) else {}
    emojis: dict[str, str] = {}
    for k in DEFAULT_THEME_EMOJIS:
        val = str(emojis_raw.get(k) or "").strip()
        emojis[k] = val if (val.isdigit() and 15 <= len(val) <= 24) else ""
    return {
        "custom_emojis_enabled": bool(src.get("custom_emojis_enabled", True)),
        "emojis": emojis,
    }


def _normalize_ann(raw: dict[str, Any]) -> dict[str, Any]:
    exp_ts = float(raw.get("expires_at_ts") or 0.0)
    dur = max(0, int(raw.get("duration_sec") or 0))
    rep = max(0, int(raw.get("repeat_interval_sec") or 0))
    style = str(raw.get("display_style") or "floating_card").strip()
    if style not in STYLE_OPTIONS:
        style = "floating_card"
    delivery_mode = str(raw.get("delivery_mode") or "animated_card").strip()
    if delivery_mode not in DELIVERY_MODES:
        delivery_mode = "animated_card"
    repeat_behavior = str(raw.get("repeat_behavior") or "replace").strip()
    if repeat_behavior not in REPEAT_BEHAVIORS:
        repeat_behavior = "replace"
    effect_preset = str(raw.get("effect_preset") or "none").strip()
    if effect_preset not in EFFECT_PRESETS:
        effect_preset = "none"
    badge = str(raw.get("badge") or "ميزة جديدة").strip()[:32]
    sent_raw = raw.get("sent_chats") if isinstance(raw.get("sent_chats"), dict) else {}
    sent_clean: dict[str, int] = {}
    for k, v in sent_raw.items():
        try:
            sent_clean[str(int(k))] = int(v)
        except Exception:
            pass
    return {
        "id": str(raw.get("id") or f"ann_{int(time.time())}_{secrets.token_hex(2)}"),
        "title": str(raw.get("title") or "").strip()[:140],
        "body": str(raw.get("body") or "").strip()[:1800],
        "badge": badge,
        "display_style": style,
        "delivery_mode": delivery_mode,
        "repeat_behavior": repeat_behavior,
        "effect_preset": effect_preset,
        "cta_label": str(raw.get("cta_label") or "استعراض الميزة الآن").strip()[:48],
        "cta_tab": str(raw.get("cta_tab") or "").strip()[:24],
        "pin_in_chat": bool(raw.get("pin_in_chat", False)),
        "repeat_on_open": bool(raw.get("repeat_on_open", True)),
        "repeat_interval_sec": rep,
        "duration_sec": dur,
        "expires_at_ts": exp_ts,
        "expires_at": str(raw.get("expires_at") or ""),
        "active": bool(raw.get("active", True)),
        "created_by": int(raw.get("created_by") or 0),
        "created_at": str(raw.get("created_at") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        "last_repushed_ts": float(raw.get("last_repushed_ts") or 0.0),
        "push_count": max(0, int(raw.get("push_count") or 0)),
        "sent_chats": sent_clean,
        "media_chat_ids": [str(x) for x in (raw.get("media_chat_ids") or []) if str(x).isdigit()][:100],
    }


def load_announcements_state() -> dict[str, Any]:
    with _ann_lock:
        path = _announcements_path()
        if not path.exists():
            return {"announcements": [], "theme": _normalize_theme({})}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {"announcements": [], "theme": _normalize_theme({})}
        if not isinstance(data, dict):
            return {"announcements": [], "theme": _normalize_theme({})}
        items = [
            _normalize_ann(x)
            for x in (data.get("announcements") or [])
            if isinstance(x, dict) and str(x.get("title") or x.get("body") or "").strip()
        ]
        return {"announcements": items[-100:], "theme": _normalize_theme(data.get("theme"))}


def save_announcements_state(state: dict[str, Any], notify: bool = True, reason: str = "announcements_update") -> None:
    with _ann_lock:
        items = [_normalize_ann(x) for x in (state.get("announcements") or []) if isinstance(x, dict)]
        payload = {
            "announcements": items[-100:],
            "theme": _normalize_theme(state.get("theme")),
        }
        _atomic_write_json(_announcements_path(), payload)
    if notify:
        _notify_persistence_and_clients(reason)


def get_theme_config() -> dict[str, Any]:
    with _ann_lock:
        return dict(load_announcements_state().get("theme") or _normalize_theme({}))


def update_theme_config(updates: dict[str, Any]) -> dict[str, Any]:
    with _ann_lock:
        st = load_announcements_state()
        cur = _normalize_theme(st.get("theme"))
        if "custom_emojis_enabled" in updates:
            cur["custom_emojis_enabled"] = bool(updates["custom_emojis_enabled"])
        if isinstance(updates.get("emojis"), dict):
            merged_em = dict(cur["emojis"])
            for k, v in updates["emojis"].items():
                if k in DEFAULT_THEME_EMOJIS:
                    s = str(v or "").strip()
                    merged_em[k] = s if (s.isdigit() and 15 <= len(s) <= 24) else ""
            cur["emojis"] = merged_em
        st["theme"] = _normalize_theme(cur)
        save_announcements_state(st, notify=True, reason="theme_updated")
        return dict(st["theme"])


def create_announcement(
    title: str,
    body: str,
    created_by: int,
    badge: str = "ميزة جديدة",
    display_style: str = "floating_card",
    delivery_mode: str = "animated_card",
    repeat_behavior: str = "replace",
    effect_preset: str = "none",
    cta_label: str = "استعراض الميزة الآن",
    cta_tab: str = "",
    duration_sec: int = 86400,
    repeat_interval_sec: int = 3600,
    repeat_on_open: bool = True,
    pin_in_chat: bool = False,
) -> dict[str, Any]:
    now = time.time()
    dur = max(0, int(duration_sec or 0))
    exp_ts = (now + dur) if dur > 0 else 0.0
    exp_str = datetime.fromtimestamp(exp_ts).strftime("%Y-%m-%d %H:%M:%S") if exp_ts > 0 else ""
    item = _normalize_ann({
        "id": f"ann_{int(now)}_{secrets.token_hex(2)}",
        "title": title,
        "body": body,
        "badge": badge or "ميزة جديدة",
        "display_style": display_style,
        "delivery_mode": delivery_mode,
        "repeat_behavior": repeat_behavior,
        "effect_preset": effect_preset,
        "cta_label": cta_label or "استعراض الميزة الآن",
        "cta_tab": cta_tab,
        "pin_in_chat": bool(pin_in_chat),
        "repeat_on_open": bool(repeat_on_open),
        "repeat_interval_sec": max(0, int(repeat_interval_sec or 0)),
        "duration_sec": dur,
        "expires_at_ts": exp_ts,
        "expires_at": exp_str,
        "active": True,
        "created_by": int(created_by or 0),
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "last_repushed_ts": now,
        "push_count": 1,
        "sent_chats": {},
        "media_chat_ids": [],
    })
    with _ann_lock:
        st = load_announcements_state()
        st["announcements"].append(item)
        save_announcements_state(st, notify=True, reason="announcement_created")
    return _enrich_ann(item, now)


def _enrich_ann(item: dict[str, Any], now_ts: float | None = None) -> dict[str, Any]:
    now = time.time() if now_ts is None else float(now_ts)
    out = dict(item)
    exp_ts = float(out.get("expires_at_ts") or 0.0)
    if exp_ts > 0:
        rem = max(0, int(exp_ts - now))
        expired = now >= exp_ts
    else:
        rem = 0
        expired = False
    out["is_expired"] = expired
    out["remaining_sec"] = rem
    out["remaining_label"] = "منتهي الصلاحية" if expired else ("دائم حتى الإزالة" if exp_ts <= 0 else format_duration_ar(rem))
    out["repeat_label"] = format_duration_ar(int(out.get("repeat_interval_sec") or 0)) if int(out.get("repeat_interval_sec") or 0) > 0 else "مرة واحدة"
    out["is_effectively_active"] = bool(out.get("active") and not expired)
    return out


def list_announcements(only_active: bool = False, now_ts: float | None = None) -> list[dict[str, Any]]:
    now = time.time() if now_ts is None else float(now_ts)
    changed = False
    with _ann_lock:
        st = load_announcements_state()
        for a in st["announcements"]:
            exp_ts = float(a.get("expires_at_ts") or 0.0)
            if a.get("active") and exp_ts > 0 and now >= exp_ts:
                a["active"] = False
                changed = True
        if changed:
            save_announcements_state(st, notify=True, reason="announcement_expired")
        items = [_enrich_ann(a, now) for a in reversed(st["announcements"])]
    if only_active:
        return [a for a in items if a["is_effectively_active"]]
    return items


def get_announcement_by_id(ann_id: str) -> dict[str, Any] | None:
    target = str(ann_id or "").strip()
    if not target:
        return None
    for a in list_announcements(only_active=False):
        if a["id"] == target:
            return a
    return None


def toggle_announcement_active(ann_id: str) -> dict[str, Any] | None:
    target = str(ann_id or "").strip()
    now = time.time()
    updated = None
    with _ann_lock:
        st = load_announcements_state()
        for a in st["announcements"]:
            if a["id"] == target:
                new_active = not bool(a.get("active", True))
                a["active"] = new_active
                # إذا أعاد المطور تفعيل إعلان منتهي المدة، يمنحه نفس المدة مجدداً إن كانت محددة
                if new_active and float(a.get("expires_at_ts") or 0.0) > 0 and now >= float(a.get("expires_at_ts") or 0.0):
                    dur = max(900, int(a.get("duration_sec") or 3600))
                    a["expires_at_ts"] = now + dur
                    a["expires_at"] = datetime.fromtimestamp(a["expires_at_ts"]).strftime("%Y-%m-%d %H:%M:%S")
                updated = _enrich_ann(a, now)
                break
        if updated:
            save_announcements_state(st, notify=True, reason="announcement_toggled")
    return updated


def update_announcement_timing(
    ann_id: str,
    duration_sec: int | None = None,
    repeat_interval_sec: int | None = None,
    repeat_on_open: bool | None = None,
) -> dict[str, Any] | None:
    target = str(ann_id or "").strip()
    now = time.time()
    updated = None
    with _ann_lock:
        st = load_announcements_state()
        for a in st["announcements"]:
            if a["id"] == target:
                if duration_sec is not None:
                    dur = max(0, int(duration_sec))
                    a["duration_sec"] = dur
                    if dur > 0:
                        a["expires_at_ts"] = now + dur
                        a["expires_at"] = datetime.fromtimestamp(a["expires_at_ts"]).strftime("%Y-%m-%d %H:%M:%S")
                    else:
                        a["expires_at_ts"] = 0.0
                        a["expires_at"] = ""
                    a["active"] = True
                if repeat_interval_sec is not None:
                    a["repeat_interval_sec"] = max(0, int(repeat_interval_sec))
                if repeat_on_open is not None:
                    a["repeat_on_open"] = bool(repeat_on_open)
                updated = _enrich_ann(a, now)
                break
        if updated:
            save_announcements_state(st, notify=True, reason="announcement_timing_updated")
    return updated


def delete_announcement(ann_id: str) -> dict[str, Any] | None:
    target = str(ann_id or "").strip()
    removed = None
    with _ann_lock:
        st = load_announcements_state()
        kept = []
        for a in st["announcements"]:
            if a["id"] == target and removed is None:
                removed = dict(a)
            else:
                kept.append(a)
        if removed is not None:
            st["announcements"] = kept
            save_announcements_state(st, notify=True, reason="announcement_deleted")
    return removed


def update_announcement_delivery(
    ann_id: str,
    delivery_mode: str | None = None,
    repeat_behavior: str | None = None,
    pin_in_chat: bool | None = None,
    effect_preset: str | None = None,
) -> dict[str, Any] | None:
    target = str(ann_id or "").strip()
    now = time.time()
    updated = None
    with _ann_lock:
        st = load_announcements_state()
        for a in st["announcements"]:
            if a["id"] == target:
                if delivery_mode in DELIVERY_MODES:
                    a["delivery_mode"] = delivery_mode
                if repeat_behavior in REPEAT_BEHAVIORS:
                    a["repeat_behavior"] = repeat_behavior
                if pin_in_chat is not None:
                    a["pin_in_chat"] = bool(pin_in_chat)
                if effect_preset in EFFECT_PRESETS:
                    a["effect_preset"] = effect_preset
                updated = _enrich_ann(a, now)
                break
        if updated:
            save_announcements_state(st, notify=True, reason="announcement_delivery_updated")
    return updated


def record_announcement_sent_chats(
    ann_id: str,
    sent_map: dict[int, int],
    media_cids: set[int] | list[int] | None = None,
) -> None:
    if not sent_map:
        return
    target = str(ann_id or "").strip()
    with _ann_lock:
        st = load_announcements_state()
        changed = False
        for a in st["announcements"]:
            if a["id"] == target:
                chats = dict(a.get("sent_chats") or {})
                for cid, mid in sent_map.items():
                    chats[str(int(cid))] = int(mid)
                a["sent_chats"] = chats
                if media_cids is not None:
                    existing_m = set(str(x) for x in (a.get("media_chat_ids") or []))
                    for mc in media_cids:
                        existing_m.add(str(int(mc)))
                    a["media_chat_ids"] = sorted(existing_m)[-100:]
                changed = True
                break
        if changed:
            save_announcements_state(st, notify=False)


def mark_announcement_repushed(ann_id: str) -> None:
    target = str(ann_id or "").strip()
    with _ann_lock:
        st = load_announcements_state()
        for a in st["announcements"]:
            if a["id"] == target:
                a["last_repushed_ts"] = time.time()
                a["push_count"] = int(a.get("push_count") or 0) + 1
                save_announcements_state(st, notify=True, reason="announcement_repushed")
                return


def pop_expired_pinned_announcements(now_ts: float | None = None) -> list[dict[str, Any]]:
    now = time.time() if now_ts is None else float(now_ts)
    expired_items: list[dict[str, Any]] = []
    with _ann_lock:
        st = load_announcements_state()
        changed = False
        for a in st["announcements"]:
            exp_ts = float(a.get("expires_at_ts") or 0.0)
            if a.get("active") and exp_ts > 0 and now >= exp_ts:
                a["active"] = False
                changed = True
                if a.get("sent_chats"):
                    expired_items.append(dict(a))
        if changed:
            save_announcements_state(st, notify=True, reason="announcement_auto_expired")
    return expired_items


def get_announcements_due_for_repeat(now_ts: float | None = None) -> list[dict[str, Any]]:
    now = time.time() if now_ts is None else float(now_ts)
    due: list[dict[str, Any]] = []
    for a in list_announcements(only_active=True, now_ts=now):
        rep = int(a.get("repeat_interval_sec") or 0)
        if rep <= 0:
            continue
        last_ts = float(a.get("last_repushed_ts") or 0.0)
        if (now - last_ts) >= rep:
            due.append(a)
    return due


def _tg_ico(fallback: str, emoji_id: str = "", use_custom: bool = False) -> str:
    if use_custom and emoji_id and str(emoji_id).isdigit():
        return f'<tg-emoji emoji-id="{emoji_id}">{fallback}</tg-emoji>'
    return fallback


def format_announcement_telegram_html(
    ann: dict[str, Any],
    esc_fn=None,
    is_repeat: bool = False,
    use_custom_emojis: bool = True,
) -> str:
    if esc_fn is None:
        import html as _html
        esc_fn = lambda v: _html.escape(str(v or ""), quote=True)
    theme = get_theme_config()
    em = theme.get("emojis") or {}
    allow_ce = bool(use_custom_emojis and theme.get("custom_emojis_enabled", True))

    badge = esc_fn(ann.get("badge") or "ميزة جديدة")
    title = esc_fn(ann.get("title") or "تحديث جديد")
    body = esc_fn(ann.get("body") or "")
    rem_lbl = esc_fn(ann.get("remaining_label") or "")
    rep_lbl = esc_fn(ann.get("repeat_label") or "مرة واحدة")

    ico_top = _tg_ico("⚡", em.get("rocket", ""), allow_ce)
    ico_time = _tg_ico("⏱", em.get("spark", ""), allow_ce)
    rep_prefix = "🔁 " if is_repeat else ""

    lines = [
        f"{rep_prefix}{ico_top} <b>{badge}</b> · <b>{title}</b>",
    ]
    if body:
        if len(body) > 260:
            lines.append(f"<blockquote expandable>{body}</blockquote>")
        else:
            lines.append(f"<blockquote>{body}</blockquote>")
    lines.append(f"{ico_time} <b>{rem_lbl}</b>  ·  🔄 <code>{rep_lbl}</code>")
    return "\n".join(lines)
