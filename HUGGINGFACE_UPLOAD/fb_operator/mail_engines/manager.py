from .onetime_tech import OneTimeTechEngine
from .tempmail_io import TempMailIoEngine
from .mail_tm import MailTmEngine
from .guerrillamail import GuerrillaMailEngine

class MailEngineManager:
    """
    المنسق الشامل لمحركات البريد المؤقت (Unified Multi-Engine Orchestrator)
    يجمع محركات:
    1. Instant Mail (1timetech)
    2. Temp-Mail.io
    3. Mail.tm
    4. GuerrillaMail
    مع دعم التبديل التلقائي عند تعثر أي سيرفر وجمع النطاقات الشائعة والمميزة.
    """
    ENGINES = {
        OneTimeTechEngine.NAME: OneTimeTechEngine,
        TempMailIoEngine.NAME: TempMailIoEngine,
        MailTmEngine.NAME: MailTmEngine,
        GuerrillaMailEngine.NAME: GuerrillaMailEngine
    }

    # ترتيب الأولوية في الفحص التلقائي
    PRIORITY_ORDER = [
        OneTimeTechEngine.NAME,
        TempMailIoEngine.NAME,
        MailTmEngine.NAME,
        GuerrillaMailEngine.NAME
    ]

    @classmethod
    def get_all_domains(cls) -> dict[str, list[str]]:
        """جلب جميع النطاقات المصنفة حسب المحرك"""
        catalog = {}
        for name, engine in cls.ENGINES.items():
            try:
                domains = engine.get_domains()
                if domains:
                    catalog[name] = domains
            except Exception:
                continue
        return catalog

    @classmethod
    def get_flat_domain_list(cls) -> list[dict]:
        """قائمة مسطحة بالنطاقات مع اسم المحرك التابع لها"""
        flat = []
        for eng_name, domains in cls.get_all_domains().items():
            for d in domains:
                flat.append({"domain": d, "engine": eng_name})
        return flat

    @classmethod
    def generate_random_mailbox(cls, preferred_engine: str = None) -> dict:
        """توليد بريد عشوائي مع التبديل التلقائي عند الفشل"""
        engines_to_try = [preferred_engine] if preferred_engine and preferred_engine in cls.ENGINES else cls.PRIORITY_ORDER

        for eng_name in engines_to_try:
            engine = cls.ENGINES.get(eng_name)
            if not engine:
                continue
            try:
                mb = engine.create_mailbox()
                if mb and mb.get("email"):
                    return mb
            except Exception:
                continue

        # Fallback to first available
        return OneTimeTechEngine.create_mailbox()

    @classmethod
    def generate_custom_mailbox(cls, username: str, domain: str) -> dict:
        """توليد بريد مخصص حسب النطاق والاسم المطلوبين"""
        # تحديد أي محرك يملك هذا النطاق
        target_engine = None
        for eng_name, engine in cls.ENGINES.items():
            if domain.lower() in [d.lower() for d in engine.get_domains()]:
                target_engine = engine
                break

        if not target_engine:
            target_engine = OneTimeTechEngine  # الافتراضي

        return target_engine.create_mailbox(username=username, domain=domain)

    @classmethod
    def check_inbox(cls, email: str, provider: str, token: str = "") -> list[dict]:
        """فحص البريد الوارد حسب المزود الذي أنشأ الحساب"""
        engine = cls.ENGINES.get(provider)
        if not engine:
            # تخمين المزود عبر اسم النطاق
            domain = email.split("@")[-1].lower() if "@" in email else ""
            for eng in cls.ENGINES.values():
                if domain in [d.lower() for d in eng.get_domains()]:
                    engine = eng
                    break
        if not engine:
            engine = OneTimeTechEngine

        try:
            return engine.get_messages(email=email, token=token)
        except Exception:
            return []
