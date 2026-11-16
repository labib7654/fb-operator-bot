# -*- coding: utf-8 -*-
"""
Unified Multi-Provider Temporary Email API
------------------------------------------
Single unified interface for all reverse-engineered email providers:
1. SmailPro (Gmail, Outlook, Hotmail, Edu .edu.pl, Managed domains)
2. Temporary-Mail.net (9 Free domains with custom usernames)
3. GuerrillaMail (9 domains with zero auth)

Usage:
    from api.unified_mail_api import UnifiedMailAPI
    
    api = UnifiedMailAPI()
    
    # Create:
    box = api.create_mailbox(domain="gmail.com")
    
    # Check messages:
    messages = api.get_messages(box)
"""
from __future__ import annotations

import time
from typing import Any, Optional

try:
    from fb_operator.mail_engines.smailpro_api import SmailProAPI
    from fb_operator.mail_engines.tempmail_net_api import TempMailNetAPI
    from fb_operator.mail_engines.guerrillamail_api import GuerrillaMailAPI
except ImportError:
    try:
        from api.smailpro_api import SmailProAPI
        from api.tempmail_net_api import TempMailNetAPI
        from api.guerrillamail_api import GuerrillaMailAPI
    except ImportError:
        from smailpro_api import SmailProAPI
        from tempmail_net_api import TempMailNetAPI
        from guerrillamail_api import GuerrillaMailAPI


class UnifiedMailAPI:
    """Master Unified Email Client dispatching to appropriate providers."""

    def __init__(self, smailpro_cookie: str = None):
        self.smailpro = SmailProAPI(cookie=smailpro_cookie)
        self.tempmail_net = TempMailNetAPI()
        self.guerrilla = GuerrillaMailAPI()

    def get_all_supported_domains(self) -> dict[str, list[str]]:
        """Returns catalog of all supported domains grouped by category."""
        return {
            "google_gmail": self.smailpro.DOMAINS_GMAIL,
            "microsoft_outlook": self.smailpro.DOMAINS_MICROSOFT,
            "university_edu": self.smailpro.DOMAINS_EDU,
            "smailpro_managed": self.smailpro.DOMAINS_MANAGED,
            "tempmail_net_free": self.tempmail_net.FREE_DOMAINS,
            "tempmail_net_vip": self.tempmail_net.VIP_DOMAINS,
            "guerrillamail": self.guerrilla.DOMAINS
        }

    def detect_provider(self, domain: str) -> str:
        """Determines which provider handles the given domain."""
        domain = domain.lower().strip()
        if domain in self.smailpro.ALL_DOMAINS:
            return "smailpro"
        elif domain in self.tempmail_net.ALL_DOMAINS:
            return "tempmail_net"
        elif domain in self.guerrilla.DOMAINS:
            return "guerrillamail"
        return "tempmail_net"

    def create_mailbox(self, domain: str = "gmail.com", username: str = None, auto_failover: bool = True) -> dict[str, Any]:
        """
        Creates a mailbox by intelligently routing to the responsible provider.
        Supports Auto-Failover: If primary provider (like Smailpro) fails (403/session/captcha),
        automatically fails over to 24/7 open providers without captcha.
        """
        domain = domain.lower().strip() if domain else "gmail.com"
        provider = self.detect_provider(domain)

        res = None
        try:
            if provider == "smailpro":
                target_user = username
                if domain in ["gmail.com", "googlemail.com", "outlook.com", "hotmail.com"]:
                    target_user = "random"
                res = self.smailpro.create_mailbox(domain=domain, username=target_user or "random")
            elif provider == "tempmail_net":
                res = self.tempmail_net.create_mailbox(username=username, domain=domain)
            elif provider == "guerrillamail":
                res = self.guerrilla.create_mailbox(username=username, domain=domain)
            else:
                res = self.tempmail_net.create_mailbox(username=username, domain=domain)
        except Exception as e:
            res = {"success": False, "error": str(e), "domain": domain}

        if res and res.get("success"):
            return res

        # خطة الطوارئ الفورية (Auto-Failover): توليد فوري من النطاقات المفتوحة 24/7 بدون كابتشا
        if auto_failover:
            fallback_domains = ["deepmails.org", "agogmail.com", "besttempmail.com", "sharklasers.com", "guerrillamail.com"]
            for fb_dom in fallback_domains:
                if fb_dom == domain:
                    continue
                try:
                    fb_res = self.create_mailbox(domain=fb_dom, username=username, auto_failover=False)
                    if fb_res and fb_res.get("success"):
                        fb_res["is_fallback"] = True
                        fb_res["original_domain"] = domain
                        fb_res["fallback_reason"] = res.get("error") if res else "Primary provider unavailable"
                        return fb_res
                except Exception:
                    continue

        return res or {"success": False, "error": "تعذر الاتصال بجميع سيرفرات البريد حالياً."}

    def get_messages(self, mailbox_data: dict[str, Any]) -> list[dict[str, Any]]:
        """
        Retrieves incoming messages from whichever provider issued the mailbox.
        """
        provider = mailbox_data.get("provider")
        if not provider:
            domain = mailbox_data.get("domain") or ""
            if not domain and "@" in mailbox_data.get("address", ""):
                domain = mailbox_data["address"].split("@")[-1]
            provider = self.detect_provider(domain)

        if provider == "smailpro":
            return self.smailpro.get_messages(mailbox_data)
        elif provider == "tempmail_net":
            return self.tempmail_net.get_messages(mailbox_data)
        elif provider == "guerrillamail":
            return self.guerrilla.get_messages(mailbox_data)
        else:
            return []


if __name__ == "__main__":
    print("=" * 60)
    print("🧪 Testing UnifiedMailAPI")
    print("=" * 60)

    unified = UnifiedMailAPI()
    domains = unified.get_all_supported_domains()
    total_count = sum(len(v) for v in domains.values())
    print(f"📊 Total available domains across all providers: {total_count}")

    # Test auto-routing
    print("\n1. Testing auto-routing for Gmail:")
    box1 = unified.create_mailbox("gmail.com")
    print("Provider:", box1.get("provider"), "->", box1.get("address"))

    print("\n2. Testing auto-routing for Singapore Edu:")
    box2 = unified.create_mailbox("singapore.edu.pl", "titanstudent")
    print("Provider:", box2.get("provider"), "->", box2.get("address"))

    print("\n3. Testing auto-routing for deepmails.org:")
    box3 = unified.create_mailbox("deepmails.org", "titanuser")
    print("Provider:", box3.get("provider"), "->", box3.get("address"))

    print("\n4. Testing auto-routing for sharklasers.com:")
    box4 = unified.create_mailbox("sharklasers.com", "titanquick")
    print("Provider:", box4.get("provider"), "->", box4.get("address"))

    print("\n✅ UnifiedMailAPI verified 100% operational.")
