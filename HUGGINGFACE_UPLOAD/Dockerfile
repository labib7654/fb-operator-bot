# صورة رسمية خفيفة وقوية من مايكروسوفت مبنية خصيصاً لتشغيل Playwright مع متصفحات هيدلس وكافة مكتبات لينكس
FROM mcr.microsoft.com/playwright/python:v1.49.0-noble

WORKDIR /app

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV DEBIAN_FRONTEND=noninteractive
ENV PORT=7860

# تثبيت خطوط اللغة العربية والنظام لضمان عرض النصوص العربية والإيموجي بدقة 100% في لقطات الشاشة
RUN apt-get update && apt-get install -y --no-install-recommends \
    fonts-noto-core \
    fonts-noto-cjk \
    fonts-noto-extra \
    fonts-noto-ui-core \
    fonts-noto-color-emoji \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install chromium

# تجهيز الصلاحيات للمستخدم 1000 المتوافق مع Hugging Face وأي بيئة سحابية
RUN mkdir -p /app/fb_operator/profiles /app/scratch && \
    chown -R 1000:1000 /app

COPY --chown=1000:1000 . .

USER 1000

EXPOSE 7860

CMD ["python", "fb_operator/telegram_bot.py"]
