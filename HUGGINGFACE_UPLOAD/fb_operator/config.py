"""
إعدادات وثوابت أداة FB Operator
"""

import os
from pathlib import Path

# المسار الأساسي للأداة
BASE_DIR = Path(__file__).resolve().parent

# مجلد حفظ جلسات وبروفايلات الحسابات (معزولة بالكامل)
PROFILES_DIR = BASE_DIR / "profiles"
PROFILES_DIR.mkdir(parents=True, exist_ok=True)

# ملف سجل الحسابات المحفوظة
ACCOUNTS_FILE = BASE_DIR / "accounts.json"

# إعدادات التخفي وفترات الانتظار البشري (بالثواني)
DEFAULT_MIN_DELAY = 2.5
DEFAULT_MAX_DELAY = 5.0

# مسار متصفح جوجل كروم على نظام ويندوز
CHROME_EXECUTABLE = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
