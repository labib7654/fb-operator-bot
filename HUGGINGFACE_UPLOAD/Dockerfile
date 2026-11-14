# بيئة متكاملة لتشغيل Playwright ومتصفح جوجل كروم الحقيقي مع بيئة شاشة سطح مكتب افتراضية Xvfb
FROM mcr.microsoft.com/playwright/python:v1.49.0-jammy

WORKDIR /app

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONPATH=/app
ENV DEBIAN_FRONTEND=noninteractive
ENV PORT=10000
ENV DISPLAY=:99

# تثبيت خادم الشاشة الافتراضية Xvfb والخطوط والأدوات الأساسية بحزم مستقرة 100%
RUN apt-get update && apt-get install -y --no-install-recommends \
    xvfb \
    x11-utils \
    wget \
    curl \
    gnupg \
    ca-certificates \
    fonts-noto-color-emoji \
    && rm -rf /var/lib/apt/lists/*

# تثبيت متصفح Google Chrome الرسمي
RUN wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /usr/share/keyrings/google-chrome.gpg && \
    echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome.gpg] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list && \
    apt-get update && apt-get install -y google-chrome-stable && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN patchright install chromium || playwright install --with-deps chromium

# تثبيت cloudflared لتشغيل نفق HTTPS الآمن للوحة التحكم المصغرة داخل تلغرام ونفق الفورجي
RUN wget -q https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -O /usr/local/bin/cloudflared && \
    chmod +x /usr/local/bin/cloudflared || true

# تثبيت محرك go-gost v3.3.3 لتشغيل نفق الفورجي 4G العكسي وبوابات البروكسي السحابية
RUN wget -q https://github.com/go-gost/gost/releases/download/v3.3.3/gost_3.3.3_linux_amd64.tar.gz -O /tmp/gost.tar.gz && \
    tar -xzf /tmp/gost.tar.gz -C /usr/local/bin gost && \
    chmod +x /usr/local/bin/gost && \
    rm -f /tmp/gost.tar.gz || true

# تخصيص الصلاحيات لمستخدم Docker
RUN mkdir -p /app/fb_operator/profiles /app/scratch && \
    chown -R 1000:1000 /app

COPY --chown=1000:1000 . .

USER 1000

EXPOSE 10000 7860

# تشغيل البوت مع خادم الـ Health Check الفوري
CMD ["xvfb-run", "-a", "-s", "-screen 0 1920x1080x24 -ac +extension GLX +render -noreset", "python", "-u", "fb_operator/server.py"]
