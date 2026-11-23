# -*- coding: utf-8 -*-
"""
SmailPro / Sonjj Credentials & Session Loader
---------------------------------------------
Loads and manages valid session cookies for SmailPro & Sonjj API.
"""
from __future__ import annotations

import os

FALLBACK_COOKIE = (
    "XSRF-TOKEN=eyJpdiI6IjFnek1EWjdHWEJjVWExSDc3NmZCV3c9PSIsInZhbHVlIjoiZFhQY0N5czVvMUN5S0kxR2FRMFh1UkZnVzFzT1hhRnlHQXozc2c4S0tQdkVZZFBRVVpVUEsxWUcwVzNjV0Vrd0wwQ2t4djFSVFZrSDI0OGJ1SnVadnlCTlJNeEduTkNhR3ZlbnB6dXdQRlJtQk9Xa2Nud3BDaCthZmh2RjBvNWgiLCJtYWMiOiIzYzlhZWZhNWVjNmIwYjY5YWRhY2NjMWU1ZTdjMmExMzExY2ZmZjk5OWY2ZTVlOTExMTY3NDA1ZmU4NDFlZDc0IiwidGFnIjoiIn0%3D; "
    "sonjj_session=eyJpdiI6IlVibDBiNElYaWJVb3VCQ3BSYVRUeUE9PSIsInZhbHVlIjoiZy91OXB0NFo3ekpHMjdGWmJjYWhSSHRzSk1hUkZabit3TkZMeS9HVGJJeUR4WFZIVnZHNTRQQlZUNEpPZEt1ajREcWoycVFBUHcvQ3duZ0ppdUNNOElJMGVEbXpwMVZJdytRaHI0TlVuQ0NXTUdGekNHU2c5cWxVc0lDZysva2YiLCJtYWMiOiI2OThiNTkyNjEwNzBlMjM0NjM3NmI5ODZjY2Q2Nzg2ZDMxY2Y4NDAwNWM2MWM5MGRkMDEwYmYyYTI2MjdiMmZmIiwidGFnIjoiIn0%3D"
)

def get_smailpro_cookie(custom_path: str = None) -> str:
    """
    Returns the current valid SmailPro cookie string.
    Checks environment variable, local cookie file, or fallback cookie.
    """
    # 1. Environment variable
    env_cookie = os.environ.get("SMAILPRO_COOKIE")
    if env_cookie and len(env_cookie.strip()) > 20:
        return env_cookie.strip()

    # 2. Provided or local file
    search_paths = []
    if custom_path:
        search_paths.append(custom_path)

    current_dir = os.path.dirname(os.path.abspath(__file__))
    search_paths.extend([
        os.path.join(current_dir, "smailpro_cookie.txt"),
        os.path.join(os.path.dirname(current_dir), "fb_operator", "smailpro_cookie.txt"),
        os.path.join(os.path.dirname(current_dir), "smailpro_cookie.txt")
    ])

    for path in search_paths:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                    if "sonjj_session=" in content:
                        return content
            except Exception:
                pass

    # 3. Fallback cookie
    return FALLBACK_COOKIE


def update_smailpro_cookie(new_cookie: str, save_path: str = None) -> bool:
    """
    Saves a new session cookie to disk for persistent usage.
    """
    if not new_cookie or "sonjj_session=" not in new_cookie:
        return False

    current_dir = os.path.dirname(os.path.abspath(__file__))
    target = save_path or os.path.join(current_dir, "smailpro_cookie.txt")
    try:
        with open(target, "w", encoding="utf-8") as f:
            f.write(new_cookie.strip())
        return True
    except Exception:
        return False
