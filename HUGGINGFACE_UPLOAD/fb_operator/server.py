# -*- coding: utf-8 -*-
"""
خادم بدء التشغيل الفوري والـ Health Check لمنصة Render و Hugging Face
يفتح منفذ HTTP فوراً في 0.05 ثانية لكي يتعرف عليه رندر مباشرة دون أي تأخير،
ثم يطلق بوت تيليجرام في خيط مستقل.
"""
import os
import sys
import time
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

PORT = int(os.environ.get("PORT", 10000))

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(b'{"status": "live", "bot": "fb-operator"}\n')

    def log_message(self, format, *args):
        pass  # منع ملء السجلات بطلبات الـ Ping

def run_http_server():
    server = HTTPServer(("0.0.0.0", PORT), HealthHandler)
    print(f"✅ [Render] HTTP Health Server is listening on 0.0.0.0:{PORT}...")
    server.serve_forever()

if __name__ == "__main__":
    # 1. فتح المنفذ فوراً في الخلفية
    http_thread = threading.Thread(target=run_http_server, daemon=True)
    http_thread.start()
    time.sleep(0.5)

    # 2. تشغيل بوت تلغرام
    print("🚀 [Bot] تشغيل بوت تلغرام FB Operator...")
    from fb_operator.telegram_bot import run_telegram_bot
    run_telegram_bot()
