# -*- coding: utf-8 -*-
"""
Clean Mail Engines Package
--------------------------
Unified interface for reverse-engineered temporary mail providers:
1. SmailPro (Real Gmail, Googlemail, Outlook, Hotmail, 3 Edu, 5 Clean .com)
2. Temporary-Mail.net (9 Free domains)
3. GuerrillaMail (9 domains)
"""
from __future__ import annotations

from fb_operator.mail_engines.unified_mail_api import UnifiedMailAPI
from fb_operator.mail_engines.smailpro_api import SmailProAPI
from fb_operator.mail_engines.tempmail_net_api import TempMailNetAPI
from fb_operator.mail_engines.guerrillamail_api import GuerrillaMailAPI

__all__ = [
    "UnifiedMailAPI",
    "SmailProAPI",
    "TempMailNetAPI",
    "GuerrillaMailAPI"
]
