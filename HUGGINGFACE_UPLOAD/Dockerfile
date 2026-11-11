# بيئة متكاملة لتشغيل Playwright ومتصفح جوجل كروم الحقيقي مع بيئة شاشة سطح مكتب افتراضية Xvfb
FROM mcr.microsoft.com/playwright/python:v1.49.0-noble

WORKDIR /app

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV DEBIAN_FRONTEND=noninteractive
ENV PORT=7860
ENV DISPLAY=:99

# تثبيت خادم الشاشة الافتراضية Xvfb وخطوط اللغة العربية والإيموجي
RUN apt-get update && apt-get install -y --no-install-recommends \
    xvfb \
    x11-utils \
    libxss1 \
    libasound2 \
    libnss3 \
    fonts-noto-core \
    fonts-noto-cjk \
    fonts-noto-extra \
    fonts-noto-ui-core \
    fonts-noto-color-emoji \
    wget \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# تثبيت متصفح Google Chrome الرسمي
RUN wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /usr/share/keyrings/google-chrome.gpg && \
    echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome.gpg] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list && \
    apt-get update && apt-get install -y google-chrome-stable && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install --with-deps chromium

# تثبيت cloudflared لتشغيل نفق HTTPS الآمن للوحة التحكم المصغرة داخل تلغرام عند الحاجة
RUN wget -q https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -O /usr/local/bin/cloudflared && \
    chmod +x /usr/local/bin/cloudflared || true

# تخصيص الصلاحيات لمستخدم Docker
RUN mkdir -p /app/fb_operator/profiles /app/scratch && \
    chown -R 1000:1000 /app

COPY --chown=1000:1000 . .

USER 1000

EXPOSE 7860

# تشغيل البوت داخل شاشة عرض افتراضية حقيقية بدقة 1080p
CMD ["xvfb-run", "-a", "-s", "-screen 0 1920x1080x24 -ac +extension GLX +render -noreset", "python", "fb_operator/telegram_bot.py"]
