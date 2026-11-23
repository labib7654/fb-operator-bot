# -*- coding: utf-8 -*-
"""
محرك تصيير البطاقات البصرية والمتحركة متعددة التقنيات (HTML5 + CSS3 + SVG -> Chromium + Pillow GIF/PNG)
-----------------------------------------------------------------------------------------------------
ينتج بطاقات إعلانية وملخصات عالية الدقة باللغة العربية (RTL متقنة التشكيل والربط) بدون رسوم كرتونية أو حشو:
- محرك HTML5/CSS3/SVG يُصيَّر داخل متصفح Chromium (Playwright / Patchright) لضمان دقة الخط العربي بالكامل.
- يجمع الإطارات إلى GIF متحركة سلسة عبر Pillow (نقطة بث حي + وميض خفيف أعلى البطاقة) مع كاش ذكي بالبصمة (SHA-256).
"""
from __future__ import annotations

import hashlib
import html
import io
import os
import threading
import time
from pathlib import Path
from typing import Any

try:
    from PIL import Image
    HAS_PIL = True
except Exception:
    HAS_PIL = False

try:
    from patchright.sync_api import sync_playwright as _sync_pw
    HAS_PW = True
except Exception:
    try:
        from playwright.sync_api import sync_playwright as _sync_pw
        HAS_PW = True
    except Exception:
        _sync_pw = None
        HAS_PW = False

import fb_operator.config as config

_RENDER_LOCK = threading.Lock()
_MEM_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_CACHE_TTL_SEC = 1800.0

_BADGE_THEMES = {
    "ميزة جديدة": ("#2ea043", "rgba(46, 160, 67, 0.16)", "NEW FEATURE"),
    "تحديث مهم": ("#1f6feb", "rgba(31, 111, 235, 0.16)", "CORE UPDATE"),
    "تنبيه عاجل": ("#d29922", "rgba(210, 153, 34, 0.16)", "PRIORITY NOTICE"),
    "عرض محدود": ("#f85149", "rgba(248, 81, 73, 0.16)", "LIMITED ACCESS"),
}


def _cache_dir() -> Path:
    d = Path(config.DATA_DIR) / "banner_cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


def clear_banner_cache() -> None:
    with _RENDER_LOCK:
        _MEM_CACHE.clear()


def build_announcement_card_html(ann: dict[str, Any], phase: float = 0.0) -> str:
    """بناء مستند HTML5/CSS3/SVG مستقل وعالي التباين لبطاقة الإعلان (RTL)"""
    badge = str(ann.get("badge") or "ميزة جديدة").strip()
    accent, accent_soft, tag_en = _BADGE_THEMES.get(badge, ("#2ea043", "rgba(46, 160, 67, 0.16)", "LIVE UPDATE"))

    title = html.escape(str(ann.get("title") or "تحديث جديد")[:110], quote=True)
    body_raw = str(ann.get("body") or "")[:360]
    body_lines = [html.escape(line.strip(), quote=True) for line in body_raw.splitlines() if line.strip()][:5]
    body_html = "<br>".join(body_lines) if body_lines else "افتح لوحة التحكم لاستعراض الميزة الجديدة."
    cta_label = html.escape(str(ann.get("cta_label") or "استعراض الميزة الآن")[:34], quote=True)
    rem_label = html.escape(str(ann.get("remaining_label") or "مباشر الآن")[:30], quote=True)
    badge_esc = html.escape(badge, quote=True)

    # حساب حركة السطوع والمؤشر الحي بناءً على الطور phase في [0..1)
    pulse_scale = 1.0 + 0.55 * abs((phase * 2.0) % 2.0 - 1.0)
    pulse_alpha = 0.85 - 0.55 * abs((phase * 2.0) % 2.0 - 1.0)
    sweep_pct = int(-25 + phase * 150)

    return f"""<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  html, body {{
    width: 780px;
    height: 360px;
    background: #0d1117;
    color: #e6edf3;
    font-family: "Noto Sans Arabic", "Noto Color Emoji", "Segoe UI", Tahoma, Arial, sans-serif;
    overflow: hidden;
  }}
  .stage {{
    width: 780px;
    height: 360px;
    padding: 20px;
    background: #0d1117;
    display: flex;
    align-items: stretch;
  }}
  .card {{
    position: relative;
    width: 100%;
    height: 100%;
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 14px;
    padding: 22px 26px 20px 26px;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    overflow: hidden;
  }}
  .top-beam {{
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    height: 3px;
    background: #21262d;
  }}
  .top-sweep {{
    position: absolute;
    top: 0;
    left: {sweep_pct}%;
    width: 38%;
    height: 3px;
    background: linear-gradient(90deg, transparent, {accent}, #e6edf3 50%, {accent}, transparent);
  }}
  .header {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
  }}
  .badge-wrap {{
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 6px 12px;
    border-radius: 999px;
    background: {accent_soft};
    border: 1px solid {accent};
    color: #f0f6fc;
    font-size: 13px;
    font-weight: 700;
  }}
  .live-dot {{
    width: 9px;
    height: 9px;
    border-radius: 50%;
    background: {accent};
    box-shadow: 0 0 0 {round(pulse_scale * 4.0, 1)}px rgba(46, 160, 67, {round(pulse_alpha * 0.45, 2)});
  }}
  .brand-meta {{
    display: inline-flex;
    align-items: center;
    gap: 8px;
    color: #8b949e;
    font-size: 12px;
    font-family: "JetBrains Mono", "Consolas", monospace;
    letter-spacing: 0.4px;
  }}
  .content {{
    margin: 12px 0;
  }}
  .title {{
    font-size: 25px;
    font-weight: 800;
    line-height: 1.32;
    color: #f0f6fc;
    margin-bottom: 10px;
  }}
  .body {{
    font-size: 15px;
    line-height: 1.62;
    color: #9da7b3;
    border-right: 3px solid {accent};
    padding-right: 14px;
    max-height: 112px;
    overflow: hidden;
  }}
  .footer {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding-top: 12px;
    border-top: 1px solid #262c36;
  }}
  .cta-pill {{
    display: inline-flex;
    align-items: center;
    gap: 8px;
    background: {accent};
    color: #ffffff;
    font-size: 13px;
    font-weight: 700;
    padding: 7px 14px;
    border-radius: 8px;
  }}
  .ttl-pill {{
    font-size: 13px;
    color: #c9d1d9;
    background: #0d1117;
    border: 1px solid #30363d;
    padding: 6px 12px;
    border-radius: 8px;
  }}
</style>
</head>
<body>
  <div class="stage">
    <div class="card">
      <div class="top-beam"></div>
      <div class="top-sweep"></div>
      <div class="header">
        <span class="badge-wrap">
          <span class="live-dot"></span>
          <span>{badge_esc}</span>
        </span>
        <span class="brand-meta">
          <svg width="14" height="14" viewBox="0 0 16 16" fill="{accent}"><path d="M8 1l2.2 4.6L15 6.3l-3.5 3.4.8 4.8L8 12.2l-4.3 2.3.8-4.8L1 6.3l4.8-.7z"/></svg>
          <span>FP_TOOL · {tag_en}</span>
        </span>
      </div>
      <div class="content">
        <div class="title">{title}</div>
        <div class="body">{body_html}</div>
      </div>
      <div class="footer">
        <span class="cta-pill">{cta_label}</span>
        <span class="ttl-pill">الصلاحية: {rem_label}</span>
      </div>
    </div>
  </div>
</body>
</html>"""


def _render_with_chromium(ann: dict[str, Any], animated: bool) -> dict[str, Any] | None:
    if not HAS_PW or _sync_pw is None:
        return None
    if animated and not HAS_PIL:
        animated = False

    launch_args = [
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
    ]
    phases = [0.0, 0.14, 0.28, 0.42, 0.56, 0.70, 0.84, 0.96] if animated else [0.35]
    frames_png: list[bytes] = []

    with _sync_pw() as pw:
        browser = None
        last_exc = None
        for opts in (
            {"headless": True, "channel": "chrome", "args": launch_args},
            {"headless": True, "args": launch_args},
            {"headless": True, "channel": "msedge", "args": launch_args},
        ):
            try:
                browser = pw.chromium.launch(**opts)
                break
            except Exception as exc:
                last_exc = exc
        if browser is None:
            if last_exc:
                raise last_exc
            return None
        try:
            page = browser.new_page(viewport={"width": 780, "height": 360}, device_scale_factor=1)
            for ph in phases:
                page.set_content(build_announcement_card_html(ann, phase=ph), wait_until="domcontentloaded", timeout=8000)
                frames_png.append(page.screenshot(type="png"))
        finally:
            try:
                browser.close()
            except Exception:
                pass

    if not frames_png:
        return None

    if animated and HAS_PIL and len(frames_png) > 1:
        pil_frames = []
        for raw in frames_png:
            im = Image.open(io.BytesIO(raw)).convert("RGB")
            pil_frames.append(im.quantize(colors=128, method=Image.Quantize.MEDIANCUT))
        out_buf = io.BytesIO()
        pil_frames[0].save(
            out_buf,
            format="GIF",
            save_all=True,
            append_images=pil_frames[1:],
            duration=115,
            loop=0,
            optimize=True,
        )
        return {
            "kind": "gif",
            "ext": "gif",
            "mime": "image/gif",
            "bytes": out_buf.getvalue(),
        }

    return {
        "kind": "png",
        "ext": "png",
        "mime": "image/png",
        "bytes": frames_png[0],
    }


def render_announcement_media(
    ann: dict[str, Any],
    animated: bool = True,
    allow_browser: bool = True,
) -> dict[str, Any] | None:
    """تصيير بطاقة الإعلان البصرية (GIF متحركة أو PNG عالية الدقة) مع كاش بالبصمة"""
    if not isinstance(ann, dict) or not (ann.get("title") or ann.get("body")):
        return None

    key_raw = "|".join([
        str(ann.get("id") or ""),
        str(ann.get("title") or ""),
        str(ann.get("body") or ""),
        str(ann.get("badge") or ""),
        str(ann.get("cta_label") or ""),
        str(ann.get("remaining_label") or ""),
        "gif" if animated else "png",
    ])
    digest = hashlib.sha256(key_raw.encode("utf-8")).hexdigest()[:24]
    now = time.time()

    with _RENDER_LOCK:
        cached = _MEM_CACHE.get(digest)
        if cached and (now - cached[0]) < _CACHE_TTL_SEC:
            return dict(cached[1])

        ext = "gif" if (animated and HAS_PIL) else "png"
        disk_file = _cache_dir() / f"{digest}.{ext}"
        if disk_file.exists():
            try:
                raw_bytes = disk_file.read_bytes()
                if raw_bytes:
                    res = {
                        "kind": ext,
                        "ext": ext,
                        "mime": "image/gif" if ext == "gif" else "image/png",
                        "bytes": raw_bytes,
                    }
                    _MEM_CACHE[digest] = (now, res)
                    return dict(res)
            except Exception:
                pass

        if not allow_browser:
            return None

        try:
            rendered = _render_with_chromium(ann, animated=animated)
        except Exception:
            rendered = None

        if not rendered or not rendered.get("bytes"):
            return None

        try:
            out_ext = rendered["ext"]
            (_cache_dir() / f"{digest}.{out_ext}").write_bytes(rendered["bytes"])
        except Exception:
            pass
        _MEM_CACHE[digest] = (now, rendered)
        return dict(rendered)
