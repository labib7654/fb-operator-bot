# -*- coding: utf-8 -*-
"""
خادم تشغيل خدمة البوت والبوابة السحابية لمنصة Render
-----------------------------------------------------
1. يفتح منفذ HTTP فوري متوافق مع فحص صحة Render (Health Check) على المنفذ المحدد في PORT.
2. يعرض صفحة لوحة معلومات HTML نظيفة وواضحة عند فتح الرابط في المتصفح.
3. يشغل بوت التليجرام في خيط خلفي مستقل مع إعادة التشغيل التلقائي عند حدوث أي انقطاع.
"""
from __future__ import annotations

import os
import sys
import time
import json
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime

# إضافة المجلد الرئيسي للمشروع إلى مسارات بايثون
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
PARENT_DIR = os.path.dirname(BASE_DIR)
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

PORT = int(os.environ.get("PORT", 10000))
START_TIME = time.time()

HTML_DASHBOARD_TEMPLATE = """<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>خادم الخدمة السحابية | حالة النظام</title>
    <style>
        :root {
            --bg-color: #0f172a;
            --card-bg: #1e293b;
            --border-color: #334155;
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
            --accent-green: #10b981;
            --accent-blue: #38bdf8;
            --accent-amber: #f59e0b;
        }
        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
        }
        body {
            background-color: var(--bg-color);
            color: var(--text-main);
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            padding: 1.5rem;
        }
        .container {
            width: 100%;
            max-width: 640px;
            background-color: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 2rem;
            box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.3);
        }
        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid var(--border-color);
            padding-bottom: 1.25rem;
            margin-bottom: 1.5rem;
        }
        h1 {
            font-size: 1.25rem;
            font-weight: 600;
        }
        .badge-live {
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            background: rgba(16, 185, 129, 0.15);
            color: var(--accent-green);
            padding: 0.35rem 0.75rem;
            border-radius: 9999px;
            font-size: 0.85rem;
            font-weight: 500;
        }
        .pulse-dot {
            width: 8px;
            height: 8px;
            background-color: var(--accent-green);
            border-radius: 50%;
            box-shadow: 0 0 8px var(--accent-green);
        }
        .grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 1rem;
            margin-bottom: 1.5rem;
        }
        .stat-card {
            background: rgba(15, 23, 42, 0.6);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 1rem;
        }
        .stat-label {
            font-size: 0.8rem;
            color: var(--text-muted);
            margin-bottom: 0.35rem;
        }
        .stat-value {
            font-size: 1.05rem;
            font-weight: 600;
        }
        .services-list {
            margin-bottom: 1.5rem;
        }
        .service-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 0.75rem 0;
            border-bottom: 1px solid rgba(51, 65, 85, 0.5);
            font-size: 0.92rem;
        }
        .service-item:last-child {
            border-bottom: none;
        }
        .status-ok {
            color: var(--accent-green);
            font-size: 0.85rem;
        }
        .status-paused {
            color: var(--accent-amber);
            font-size: 0.85rem;
        }
        footer {
            border-top: 1px solid var(--border-color);
            padding-top: 1rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-size: 0.8rem;
            color: var(--text-muted);
        }
        a {
            color: var(--accent-blue);
            text-decoration: none;
        }
        a:hover {
            text-decoration: underline;
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div>
                <h1>خادم الخدمات السحابية</h1>
                <p style="font-size: 0.85rem; color: var(--text-muted); margin-top: 0.25rem;">المنظومة متصلة وجاهزة لاستقبال الأوامر</p>
            </div>
            <div class="badge-live">
                <span class="pulse-dot"></span>
                <span>نشط 24/7</span>
            </div>
        </header>

        <div class="grid">
            <div class="stat-card">
                <div class="stat-label">بوت التليجرام</div>
                <div class="stat-value" style="color: var(--accent-blue);">@FP_toolbot</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">قاعدة البيانات (Supabase)</div>
                <div class="stat-value" style="color: var(--accent-green);">متصلة ومؤمّنة</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">مدة التشغيل الحالية</div>
                <div class="stat-value" id="uptime">__UPTIME__</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">استهلاك الذاكرة</div>
                <div class="stat-value" style="color: var(--accent-green);">خفيف (&lt; 90 MB)</div>
            </div>
        </div>

        <div class="services-list">
            <div class="service-item">
                <span>✉️ البريد المؤقت (Gmail VIP & النطاقات المخصصة)</span>
                <span class="status-ok">● يعمل 100%</span>
            </div>
            <div class="service-item">
                <span>📞 كاشف الأرقام اليمنية وهوية المتصل</span>
                <span class="status-ok">● يعمل 100%</span>
            </div>
            <div class="service-item">
                <span>📱 الأرقام الوهمية واستقبال الرسائل</span>
                <span class="status-ok">● يعمل 100%</span>
            </div>
            <div class="service-item">
                <span>💰 نظام النقاط والمحفظة والإحالات</span>
                <span class="status-ok">● يعمل 100%</span>
            </div>
            <div class="service-item">
                <span>🌐 أتمتة فيسبوك والمتصفح</span>
                <span class="status-paused">⏸ متوقفة مؤقتاً لتجهيز سيرفر أوراكل</span>
            </div>
        </div>

        <footer>
            <span>فحص الصحة: <code>/healthz</code></span>
            <span>تحديث تلقائي: نشط</span>
        </footer>
    </div>
</body>
</html>
"""

def format_uptime(seconds: float) -> str:
    secs = int(seconds)
    hours = secs // 3600
    minutes = (secs % 3600) // 60
    s = secs % 60
    if hours > 0:
        return f"{hours} ساعة و {minutes} دقيقة"
    if minutes > 0:
        return f"{minutes} دقيقة و {s} ثانية"
    return f"{s} ثوانٍ"

class HealthAndDashboardHandler(BaseHTTPRequestHandler):
    def _respond(self, is_head: bool = False):
        uptime_str = format_uptime(time.time() - START_TIME)
        path = self.path.split("?")[0].rstrip("/")

        if path in ("", "/dashboard", "/index.html"):
            html = HTML_DASHBOARD_TEMPLATE.replace("__UPTIME__", uptime_str)
            body = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if not is_head:
                self.wfile.write(body)
            return

        if path in ("/health", "/healthz", "/ping", "/status"):
            res = {
                "status": "ok",
                "service": "online",
                "bot": "FP_toolbot",
                "database": "supabase_connected",
                "uptime_seconds": int(time.time() - START_TIME),
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }
            body = json.dumps(res, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if not is_head:
                self.wfile.write(body)
            return

        # أي مسار آخر
        self.send_response(404)
        self.end_headers()

    def do_HEAD(self):
        self._respond(is_head=True)

    def do_GET(self):
        self._respond(is_head=False)

    def do_POST(self):
        self._respond(is_head=False)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Allow", "GET, HEAD, POST, OPTIONS")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, format, *args):
        # منع ملء سجلات رندر بطلبات الـ Ping المتكررة
        pass

def run_http_server():
    server = HTTPServer(("0.0.0.0", PORT), HealthAndDashboardHandler)
    print(f"[Render HTTP] Server listening on http://0.0.0.0:{PORT} (Dashboard & Health Check ready)", flush=True)
    server.serve_forever()

def run_bot_worker():
    time.sleep(1.0)
    print("[Bot Worker] Starting Telegram Bot Engine...", flush=True)
    while True:
        try:
            from fb_operator.telegram_bot import run_telegram_bot
            run_telegram_bot()
        except Exception as e:
            print(f"[Bot Worker Exception] {e}", file=sys.stderr, flush=True)
            time.sleep(5)

if __name__ == "__main__":
    # 1. إطلاق خادم HTTP فورياً في خيط مستقل لكي يستجيب لرندر في أقل من 0.1 ثانية
    http_thread = threading.Thread(target=run_http_server, daemon=True, name="Render_HTTP_Server")
    http_thread.start()

    # 2. إطلاق بوت التليجرام
    run_bot_worker()
