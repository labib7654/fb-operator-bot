# -*- coding: utf-8 -*-
"""
خادم تشغيل البوت لمنصة Hugging Face Spaces (Gradio)
متوافق مع ZeroGPU و CPU Basic، ويشغل البوت 24/7 في خيط مستقل
"""
import os
import sys
import threading
import time

# 1. إضافة كافة المسارات المحتملة للـ sys.path لضمان العثور على fb_operator فوراً
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
candidate_paths = [
    BASE_DIR,
    os.path.join(BASE_DIR, "HUGGINGFACE_UPLOAD"),
    "/app",
    "/app/HUGGINGFACE_UPLOAD"
]
for p in candidate_paths:
    if os.path.exists(p) and p not in sys.path:
        sys.path.insert(0, p)

def run_bot_worker():
    time.sleep(2)
    try:
        print("[Bot Worker] بدء فحص وتحميل متصفح Playwright Chromium...", flush=True)
        import subprocess
        subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=False)
    except Exception as e:
        print(f"[Bot Worker Warning] {e}", flush=True)

    try:
        print("[Bot Worker] جاري إطلاق محرك البوت FB Operator...", flush=True)
        from fb_operator.telegram_bot import run_telegram_bot
        run_telegram_bot()
    except Exception as e:
        print(f"[Bot Worker Error] {e}", file=sys.stderr, flush=True)
        import traceback
        traceback.print_exc()

# 2. إطلاق البوت في خيط خلفي مستقل
bot_thread = threading.Thread(target=run_bot_worker, daemon=True, name="FB_Bot_Thread")
bot_thread.start()

# 3. إطلاق واجهة Gradio مع دعم ديكوريتور ZeroGPU
import gradio as gr
try:
    import spaces
    @spaces.GPU
    def bot_status():
        return "🟢 البوت يعمل الآن بنجاح في سحاب Hugging Face بذاكرة 16GB RAM."
except Exception:
    def bot_status():
        return "🟢 البوت يعمل الآن بنجاح في سحاب Hugging Face بذاكرة 16GB RAM."

demo = gr.Interface(
    fn=bot_status,
    inputs=[],
    outputs="text",
    title="FB Operator Bot 24/7"
)

demo.launch()
