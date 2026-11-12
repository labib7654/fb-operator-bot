"""
ناقل التحديثات الفورية المعتمد على الأحداث (Event-Driven Real-Time Sync Bus)
يُخطِر الخادم والأطراف المتصلة لحظياً فور حدوث أي تغيير فعلي بالبيانات أو الصلاحيات أو المهام
دون الحاجة لإرسال طلبات استطلاع متكررة كل بضع ثوانٍ.
"""

import threading
import time
from typing import Callable

_cond = threading.Condition()
_seq: int = 1
_events: list[tuple[int, str, int]] = []  # (seq, scope, target_uid)
_listeners: list[Callable[[str, int, str], None]] = []


def get_seq() -> int:
    with _cond:
        return _seq


def register_listener(cb: Callable[[str, int, str], None]) -> None:
    with _cond:
        if cb not in _listeners:
            _listeners.append(cb)


def publish_event(scope: str, target_uid: int | None = None, reason: str = "") -> int:
    """نشر حدث تحديث فوري وإيقاظ كافة المستمعين المتأثرين بدون أي حجب."""
    t_uid = int(target_uid) if target_uid else 0
    with _cond:
        global _seq
        _seq += 1
        cur_seq = _seq
        _events.append((cur_seq, scope, t_uid))
        if len(_events) > 320:
            del _events[:-200]
        _cond.notify_all()
        listeners_copy = list(_listeners)

    for cb in listeners_copy:
        try:
            cb(scope, t_uid, reason)
        except Exception:
            pass
    return cur_seq


def _match_event(scope: str, t_uid: int, viewer_uid: int, is_dev: bool, can_see_shared_accounts: bool) -> bool:
    if is_dev:
        return True
    if scope == "accounts":
        return t_uid in (0, viewer_uid) or can_see_shared_accounts
    if scope in ("users", "mission", "economy", "support", "system", "announcements", "proxies"):
        return t_uid == 0 or t_uid == viewer_uid
    return False


def wait_for_relevant_events(
    since_seq: int,
    viewer_uid: int,
    is_dev: bool,
    can_see_shared_accounts: bool,
    timeout: float = 25.0,
) -> tuple[bool, int, list[str]]:
    """
    ينتظر سكوناً (Blocking Condition.wait) حتى وقوع حدث يهم المستخدم أو المطور.
    يعيد: (هل يوجد تغيير، رقم النسخة الحالي، قائمة النطاقات المتأثرة).
    """
    cursor = max(0, int(since_seq))
    deadline = time.monotonic() + max(1.0, float(timeout))

    with _cond:
        while True:
            if _seq > cursor:
                matched_scopes: list[str] = []
                # إذا فات المخزن الدائري أحداثاً قديمة جداً (انقطاع طويل)، نعتبره تغييراً فورياً
                if _events and cursor < (_events[0][0] - 1):
                    return True, _seq, ["users", "accounts"]

                for ev_seq, sc, t_uid in _events:
                    if ev_seq > cursor and _match_event(sc, t_uid, viewer_uid, is_dev, can_see_shared_accounts):
                        if sc not in matched_scopes:
                            matched_scopes.append(sc)
                latest_seq = _seq
                if matched_scopes:
                    return True, latest_seq, matched_scopes
                # مرّ حدث لا يخص هذا المستخدم؛ نرفع المؤشر المحلي ونستمر بالانتظار بهدوء
                cursor = latest_seq

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False, _seq, []
            _cond.wait(timeout=remaining)
