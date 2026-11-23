"""
واجهة تطبيق تلغرام التفاعلي المصغّر (Telegram Mini App WebApp UI)
تُعرض مباشرة داخل نافذة تلغرام عبر زر القائمة (Menu Button) أو لوحة البوت
بمصادقة Telegram initData وتوافق كامل مع سمات تلغرام الداكنة والفاتحة.
"""


def get_miniapp_html() -> str:
    return r"""<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>لوحة تحكم FB Operator</title>
    <script src="https://telegram.org/js/telegram-web-app.js"></script>
    <style>
        :root {
            --bg: var(--tg-theme-bg-color, #0e1621);
            --bg-sec: var(--tg-theme-secondary-bg-color, #17212b);
            --text: var(--tg-theme-text-color, #f5f5f5);
            --muted: var(--tg-theme-hint-color, #8e9ba8);
            --accent: var(--tg-theme-button-color, #2b7de9);
            --accent-text: var(--tg-theme-button-text-color, #ffffff);
            --border: rgba(255, 255, 255, 0.08);
            --ok: #2ea043;
            --danger: #e5534b;
            --warn: #d29922;
            --radius: 10px;
        }
        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Tahoma, Arial, sans-serif;
            -webkit-tap-highlight-color: transparent;
        }
        body {
            background: var(--bg);
            color: var(--text);
            min-height: 100vh;
            padding: 12px 12px 28px;
            font-size: 14px;
            line-height: 1.5;
        }
        .container { max-width: 720px; margin: 0 auto; }

        /* الشريط العلوي */
        .topbar {
            background: var(--bg-sec);
            border: 1px solid var(--border);
            border-radius: var(--radius);
            padding: 12px 14px;
            margin-bottom: 12px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 10px;
        }
        .topbar-title { font-size: 15px; font-weight: 700; }
        .topbar-sub { font-size: 12px; color: var(--muted); }
        .role-pill {
            font-size: 11px;
            font-weight: 600;
            padding: 4px 10px;
            border-radius: 6px;
            background: rgba(43, 125, 233, 0.16);
            color: var(--accent);
            border: 1px solid rgba(43, 125, 233, 0.35);
            white-space: nowrap;
        }

        /* شريط التبويبات */
        .tabs {
            display: flex;
            gap: 6px;
            margin-bottom: 12px;
            overflow-x: auto;
            padding-bottom: 2px;
        }
        .tab-btn {
            flex: 1;
            min-width: fit-content;
            padding: 9px 12px;
            background: var(--bg-sec);
            color: var(--muted);
            border: 1px solid var(--border);
            border-radius: 8px;
            font-size: 13px;
            font-weight: 600;
            cursor: pointer;
            text-align: center;
        }
        .tab-btn.active {
            background: var(--accent);
            color: var(--accent-text);
            border-color: var(--accent);
        }

        /* الكتل والحقول */
        .panel {
            background: var(--bg-sec);
            border: 1px solid var(--border);
            border-radius: var(--radius);
            padding: 14px;
            margin-bottom: 12px;
        }
        .panel-title {
            font-size: 14px;
            font-weight: 700;
            margin-bottom: 10px;
            padding-bottom: 6px;
            border-bottom: 1px solid var(--border);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .field { margin-bottom: 10px; }
        .field label {
            display: block;
            font-size: 12px;
            color: var(--muted);
            margin-bottom: 4px;
            font-weight: 600;
        }
        input[type="text"], input[type="password"], input[type="number"], select, textarea {
            width: 100%;
            background: var(--bg);
            color: var(--text);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 9px 11px;
            font-size: 13px;
            outline: none;
        }
        input:focus, select:focus, textarea:focus { border-color: var(--accent); }
        textarea { resize: vertical; min-height: 64px; }

        .row-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
        @media (max-width: 480px) { .row-2 { grid-template-columns: 1fr; } }

        /* أزرار التبديل والمفاتيح */
        .toggle-item {
            display: flex;
            align-items: center;
            justify-content: space-between;
            background: var(--bg);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 9px 11px;
            margin-bottom: 8px;
            gap: 10px;
        }
        .toggle-label { font-size: 13px; font-weight: 600; }
        .toggle-desc { font-size: 11px; color: var(--muted); }
        .switch-btn {
            padding: 5px 12px;
            border-radius: 6px;
            border: 1px solid var(--border);
            font-size: 12px;
            font-weight: 700;
            cursor: pointer;
            min-width: 68px;
            text-align: center;
        }
        .switch-on { background: rgba(46, 160, 67, 0.2); color: #3fb950; border-color: rgba(46, 160, 67, 0.45); }
        .switch-off { background: rgba(229, 83, 75, 0.14); color: #f47067; border-color: rgba(229, 83, 75, 0.35); }

        /* الأزرار الرئيسية */
        .btn {
            width: 100%;
            padding: 10px 14px;
            border-radius: 8px;
            border: none;
            font-size: 13px;
            font-weight: 700;
            cursor: pointer;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 6px;
        }
        .btn-primary { background: var(--accent); color: var(--accent-text); }
        .btn-ok { background: var(--ok); color: #ffffff; }
        .btn-danger { background: rgba(229, 83, 75, 0.18); color: #f47067; border: 1px solid rgba(229, 83, 75, 0.4); }
        .btn-muted { background: var(--bg); color: var(--text); border: 1px solid var(--border); }
        .btn-sm { width: auto; padding: 6px 11px; font-size: 12px; }
        .btn:disabled { opacity: 0.55; cursor: not-allowed; }

        /* قوائم العناصر */
        .item-row {
            background: var(--bg);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 10px 12px;
            margin-bottom: 8px;
        }
        .item-head {
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 8px;
            margin-bottom: 4px;
        }
        .item-name { font-weight: 700; font-size: 13px; }
        .badge-ok { color: #3fb950; font-size: 11px; font-weight: 700; }
        .badge-bad { color: #f47067; font-size: 11px; font-weight: 700; }
        .badge-warn { color: #d29922; font-size: 11px; font-weight: 700; }
        .mono {
            font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
            font-size: 12px;
            color: var(--muted);
            word-break: break-all;
        }

        .status-banner {
            background: var(--bg);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 10px 12px;
            font-size: 12px;
            color: var(--text);
            margin-top: 8px;
            white-space: pre-wrap;
        }
        .toast {
            position: fixed;
            bottom: 16px;
            left: 50%;
            transform: translateX(-50%);
            background: #1f2937;
            color: #ffffff;
            border: 1px solid rgba(255,255,255,0.18);
            padding: 9px 16px;
            border-radius: 8px;
            font-size: 13px;
            font-weight: 600;
            z-index: 9999;
            display: none;
            max-width: 90vw;
            text-align: center;
        }
        .hidden { display: none !important; }
        .locked-box {
            text-align: center;
            padding: 36px 18px;
            background: var(--bg-sec);
            border: 1px solid var(--border);
            border-radius: var(--radius);
            margin-top: 24px;
        }
        dialog.hitl-dialog {
            width: min(860px, 98vw);
            max-width: 98vw;
            max-height: 95dvh;
            margin: auto;
            padding: 0;
            border: 1px solid var(--border);
            border-radius: var(--radius);
            background: var(--bg-sec);
            color: var(--text);
        }
        @media (max-width: 768px) {
            dialog.hitl-dialog {
                width: 100vw;
                max-width: 100vw;
                height: 100dvh;
                max-height: 100dvh;
                margin: 0;
                border-radius: 0;
                border: none;
            }
        }
        dialog.hitl-dialog[open] {
            display: flex;
            flex-direction: column;
        }
        dialog.hitl-dialog:modal {
            overscroll-behavior: contain;
        }
        dialog.hitl-dialog::backdrop {
            overflow: hidden;
            overscroll-behavior: contain;
            background: rgba(0, 0, 0, 0.72);
        }

        /* ===== الإعلانات العائمة (Popover & Top-Layer Dialog) ===== */
        #promoToastRegion {
            position: fixed;
            inset-block-start: 12px;
            inset-inline: 12px;
            z-index: 980;
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 8px;
            pointer-events: none;
        }
        .promo-toast-card {
            pointer-events: auto;
            width: min(460px, 100%);
            margin: 0;
            inset: auto;
            position: relative;
            background: #141b25;
            color: var(--text);
            border: 1px solid rgba(43, 125, 233, 0.55);
            border-radius: 10px;
            padding: 12px 14px;
            box-shadow: 0 14px 36px rgba(0, 0, 0, 0.55);
            display: none;
            opacity: 0;
            transition-property: opacity, transform, display, overlay;
            transition-duration: 240ms;
            transition-timing-function: cubic-bezier(0.2, 0.8, 0.2, 1);
            transition-behavior: allow-discrete;
        }
        .promo-toast-card.style-urgent {
            border-color: rgba(248, 81, 73, 0.7);
            background: #1c1519;
        }
        .promo-toast-card.style-ribbon {
            border-color: rgba(46, 160, 67, 0.65);
            background: #111c17;
        }
        .promo-toast-card.style-glow {
            border-color: rgba(210, 153, 34, 0.7);
            background: #1b1812;
        }
        .promo-toast-card:is(:popover-open, .\:popover-open) {
            display: block;
            opacity: 1;
        }
        @starting-style {
            .promo-toast-card:is(:popover-open, .\:popover-open) {
                opacity: 0;
            }
        }
        @media (prefers-reduced-motion: no-preference) {
            .promo-toast-card {
                transform: translateY(-10px) scale(0.98);
            }
            .promo-toast-card:is(:popover-open, .\:popover-open) {
                transform: translateY(0) scale(1);
            }
            @starting-style {
                .promo-toast-card:is(:popover-open, .\:popover-open) {
                    transform: translateY(-10px) scale(0.98);
                }
            }
        }
        @media (prefers-reduced-motion: reduce) {
            .promo-toast-card {
                transition-duration: 120ms;
                transform: none;
            }
        }
        .promo-head {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 8px;
            margin-bottom: 6px;
        }
        .promo-badge {
            font-size: 11px;
            font-weight: 700;
            padding: 2px 8px;
            border-radius: 5px;
            background: rgba(43, 125, 233, 0.18);
            color: #7ab8ff;
            border: 1px solid rgba(43, 125, 233, 0.35);
        }
        .style-urgent .promo-badge {
            background: rgba(248, 81, 73, 0.18);
            color: #ff9492;
            border-color: rgba(248, 81, 73, 0.35);
        }
        .style-glow .promo-badge {
            background: rgba(210, 153, 34, 0.18);
            color: #f3c86a;
            border-color: rgba(210, 153, 34, 0.35);
        }
        .style-ribbon .promo-badge {
            background: rgba(46, 160, 67, 0.18);
            color: #7ee787;
            border-color: rgba(46, 160, 67, 0.35);
        }
        .promo-title {
            font-size: 14px;
            font-weight: 700;
            margin-bottom: 4px;
            color: var(--text);
        }
        .promo-body {
            font-size: 12.5px;
            color: var(--muted);
            white-space: pre-wrap;
            line-height: 1.5;
            margin-bottom: 10px;
        }
        .promo-actions {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 8px;
            flex-wrap: wrap;
        }
        dialog.promo-dialog {
            padding: 0;
            border: 1px solid var(--border);
            border-radius: 12px;
            background: #131922;
            color: var(--text);
            width: min(460px, 94vw);
            max-width: 94vw;
            margin: auto;
            box-shadow: 0 24px 60px rgba(0, 0, 0, 0.7);
            opacity: 0;
            transition-property: opacity, transform, display, overlay;
            transition-duration: 240ms;
            transition-timing-function: cubic-bezier(0.2, 0.8, 0.2, 1);
            transition-behavior: allow-discrete;
        }
        dialog.promo-dialog[open] {
            opacity: 1;
        }
        dialog.promo-dialog[data-closing] {
            opacity: 0;
        }
        @starting-style {
            dialog.promo-dialog[open] {
                opacity: 0;
            }
        }
        dialog.promo-dialog:modal {
            overscroll-behavior: contain;
        }
        dialog.promo-dialog::backdrop {
            overflow: hidden;
            overscroll-behavior: contain;
            background: rgba(0, 0, 0, 0.72);
            opacity: 0;
            transition-property: opacity, display, overlay;
            transition-duration: 240ms;
            transition-timing-function: ease-out;
            transition-behavior: allow-discrete;
        }
        dialog.promo-dialog[open]::backdrop {
            opacity: 1;
        }
        dialog.promo-dialog[data-closing]::backdrop {
            opacity: 0;
        }
        @starting-style {
            dialog.promo-dialog[open]::backdrop {
                opacity: 0;
            }
        }
        @media (prefers-reduced-motion: no-preference) {
            dialog.promo-dialog {
                transform: translateY(14px) scale(0.97);
            }
            dialog.promo-dialog[open] {
                transform: translateY(0) scale(1);
            }
            dialog.promo-dialog[data-closing] {
                transform: translateY(10px) scale(0.97);
            }
            @starting-style {
                dialog.promo-dialog[open] {
                    transform: translateY(14px) scale(0.97);
                }
            }
        }
        @media (prefers-reduced-motion: reduce) {
            dialog.promo-dialog,
            dialog.promo-dialog::backdrop {
                transition-duration: 120ms;
                transform: none;
            }
        }
        .promo-modal-inner {
            padding: 16px;
        }
        .promo-modal-footer {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 8px;
            flex-wrap: wrap;
            margin-top: 12px;
            padding-top: 10px;
            border-top: 1px solid var(--border);
        }
        .hitl-head {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 10px;
            padding: 10px 14px;
            border-bottom: 1px solid var(--border);
        }
        .hitl-head h2 {
            margin: 0;
            font-size: 15px;
            font-weight: 700;
            text-wrap: balance;
        }
        .hitl-body {
            flex: 1;
            min-height: 0;
            padding: 6px 10px max(8px, env(safe-area-inset-bottom, 8px)) 10px;
            overflow-y: auto;
            display: flex;
            flex-direction: column;
            gap: 6px;
        }
        .hitl-head-actions {
            display: flex;
            align-items: center;
            gap: 6px;
            flex-shrink: 0;
        }
        .hitl-ar-bar {
            background: rgba(56, 139, 253, 0.12);
            border: 1px solid rgba(56, 139, 253, 0.35);
            border-radius: 8px;
            padding: 6px 10px;
            font-size: 13px;
            line-height: 1.5;
            color: var(--text);
            white-space: pre-line;
            word-break: break-word;
        }
        .hitl-zoom-bar {
            display: flex;
            flex-wrap: wrap;
            align-items: center;
            justify-content: space-between;
            gap: 5px;
        }
        .hitl-zoom-group {
            display: flex;
            flex-wrap: wrap;
            align-items: center;
            gap: 4px;
        }
        .hitl-zoom-badge {
            font-size: 12px;
            font-weight: 700;
            padding: 4px 8px;
            border-radius: 6px;
            background: rgba(88, 166, 255, 0.12);
            color: var(--accent);
            border: 1px solid var(--border);
            min-inline-size: 46px;
            text-align: center;
        }
        .hitl-stage {
            position: relative;
            flex: 1;
            width: 100%;
            min-height: 56dvh;
            max-height: none;
            background: #0d1117;
            border: 1px solid var(--border);
            border-radius: 8px;
            overflow: auto;
            -webkit-overflow-scrolling: touch;
            overscroll-behavior: contain;
            touch-action: pan-x pan-y pinch-zoom;
        }
        .hitl-tools-drawer {
            border: 1px solid var(--border);
            border-radius: 8px;
            background: var(--bg);
            padding: 4px 8px;
        }
        .hitl-tools-drawer summary {
            cursor: pointer;
            font-size: 12px;
            font-weight: 700;
            color: var(--muted);
            padding: 4px 2px;
            user-select: none;
        }
        .hitl-tools-drawer[open] summary {
            margin-bottom: 6px;
            border-bottom: 1px solid var(--border);
        }
        .hitl-canvas-wrap {
            position: relative;
            width: 100%;
            margin: 0 auto;
            aspect-ratio: 1280 / 800;
            cursor: crosshair;
            touch-action: none;
            user-select: none;
            -webkit-user-select: none;
        }
        .hitl-canvas-wrap.pan-mode {
            cursor: grab;
        }
        .hitl-canvas-wrap.pan-mode:active {
            cursor: grabbing;
        }
        .hitl-canvas-wrap img {
            display: block;
            width: 100%;
            height: 100%;
            object-fit: fill;
            user-select: none;
            -webkit-user-drag: none;
            pointer-events: none;
        }
        .hitl-tap-dot {
            position: absolute;
            width: 22px;
            height: 22px;
            margin: -11px 0 0 -11px;
            border-radius: 50%;
            border: 2px solid #3fb950;
            background: rgba(63, 185, 80, 0.30);
            pointer-events: none;
            z-index: 3;
        }
        .hitl-toolbar {
            display: flex;
            flex-wrap: wrap;
            gap: 6px;
        }
        @media (pointer: coarse) {
            .hitl-toolbar .btn,
            .hitl-zoom-bar .btn {
                min-block-size: 44px;
                min-inline-size: 44px;
                padding: 8px 11px;
            }
        }
        .multi-acc-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
            gap: 6px;
            margin-top: 8px;
        }
        .multi-acc-chip {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 6px;
            padding: 8px 10px;
            border-radius: 6px;
            border: 1px solid var(--border);
            background: var(--bg);
            color: var(--text);
            font-size: 12px;
            font-weight: 600;
            cursor: pointer;
            text-align: right;
        }
        .multi-acc-chip.picked {
            border-color: var(--accent);
            background: rgba(31, 111, 235, 0.14);
        }
        .proxy-kpi-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
            gap: 8px;
            margin-bottom: 12px;
        }
        .proxy-kpi-box {
            background: var(--bg);
            border: 1px solid var(--border);
            border-radius: 6px;
            padding: 8px 10px;
        }
        .proxy-kpi-val {
            font-size: 16px;
            font-weight: 700;
            color: var(--text);
            font-variant-numeric: tabular-nums;
        }
        .proxy-kpi-lbl {
            font-size: 11px;
            color: var(--muted);
            margin-top: 2px;
        }
        .proxy-acc-chip {
            display: inline-flex;
            align-items: center;
            gap: 4px;
            padding: 3px 8px;
            border-radius: 999px;
            font-size: 11px;
            font-weight: 600;
            border: 1px solid var(--border);
            background: var(--panel);
            color: var(--text);
            cursor: pointer;
        }
    </style>
</head>
<body>
<div class="container">
    <div id="loadingBox" class="locked-box">
        <div style="font-weight:700;margin-bottom:6px;">جاري التحقق من جلسة تلغرام...</div>
        <div style="font-size:12px;color:var(--muted);">يرجى فتح هذه اللوحة من داخل تطبيق تلغرام فقط.</div>
    </div>

    <div id="lockedBox" class="locked-box hidden">
        <div id="lockedTitle" style="font-size:16px;font-weight:700;margin-bottom:8px;">الوصول مقفل</div>
        <div id="lockedMsg" style="font-size:13px;color:var(--muted);"></div>
        <div id="inviteRedeemBox" class="hidden" style="margin-top:16px;text-align:right;max-width:380px;margin-left:auto;margin-right:auto;">
            <div class="field">
                <label>هل لديك كود إحالة أو تفعيل؟</label>
                <input type="text" id="inpRedeemCode" placeholder="أدخل الكود مثال: FB-XXXX-XXXX">
            </div>
            <button type="button" class="btn btn-primary" onclick="redeemInviteCode()">تفعيل حساب إضافة الحسابات بالكود</button>
        </div>
    </div>

    <div id="appShell" class="hidden">
        <div class="topbar">
            <div>
                <div class="topbar-title" id="userNameLbl">FB Operator</div>
                <div class="topbar-sub" id="userPermsSummary">متصل بالسحابة</div>
            </div>
            <div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap;justify-content:flex-end;">
                <div class="role-pill" id="walletPill" style="background:rgba(46,160,67,0.16);color:#3fb950;border-color:rgba(46,160,67,0.35);">0 نقطة</div>
                <div class="role-pill" id="rolePill">مستخدم</div>
            </div>
        </div>

        <div class="tabs" id="tabsBar"></div>

        <!-- تبويب العمليات الميدانية -->
        <div id="tab-mission" class="tab-view hidden">
            <div class="panel">
                <div class="panel-title">إعدادات الهدف والمنفذ</div>
                <div class="field" id="grpExecutor">
                    <label>الحسابات المنفذة</label>
                    <select id="inpSelectedAcc" onchange="onSelectedAccChange()"></select>
                    <div id="multiAccPicker" class="multi-acc-grid hidden"></div>
                </div>
                <div class="field">
                    <label>الرابط المستهدف (صفحة، حساب، أو منشور)</label>
                    <input type="text" id="inpTargetUrl" placeholder="https://www.facebook.com/...">
                </div>
                <div class="field">
                    <label>الحد الأقصى لعدد الحسابات المشاركة (0 = الكل)</label>
                    <input type="number" id="inpAccLimit" min="0" value="0">
                </div>
            </div>

            <div class="panel" id="secReact">
                <div class="panel-title">
                    <span>التفاعلات والإعجابات</span>
                    <button type="button" class="switch-btn" id="btnTogReact" onclick="toggleLocalBool('like')"></button>
                </div>
                <div class="row-2">
                    <div class="field">
                        <label>نوع التفاعل</label>
                        <select id="inpReactionType">
                            <option value="like">إعجاب (Like)</option>
                            <option value="love">أحببته (Love)</option>
                            <option value="care">أدعمه (Care)</option>
                            <option value="haha">هاهاها (Haha)</option>
                            <option value="wow">واو (Wow)</option>
                            <option value="sad">أحزنني (Sad)</option>
                            <option value="angry">أغضبني (Angry)</option>
                            <option value="unlike">إلغاء الإعجاب (Unlike)</option>
                        </select>
                    </div>
                    <div class="field">
                        <label>ترتيب المنشور</label>
                        <input type="number" id="inpReactIndex" min="1" value="1">
                    </div>
                </div>
                <div class="field">
                    <label>أو رابط منشور مباشر للتفاعل (اختياري)</label>
                    <input type="text" id="inpReactUrl" placeholder="اتركه فارغاً لاستخدام ترتيب المنشور أعلاه">
                </div>
            </div>

            <div class="panel" id="secComment">
                <div class="panel-title">
                    <span>كتابة التعليقات</span>
                    <button type="button" class="switch-btn" id="btnTogComment" onclick="toggleLocalBool('comment')"></button>
                </div>
                <div class="field">
                    <label>نص التعليق</label>
                    <textarea id="inpCommentText"></textarea>
                </div>
                <div class="row-2">
                    <div class="field">
                        <label>ترتيب المنشور</label>
                        <input type="number" id="inpCommentIndex" min="1" value="1">
                    </div>
                    <div class="field">
                        <label>رابط منشور مباشر (اختياري)</label>
                        <input type="text" id="inpCommentUrl" placeholder="اختياري">
                    </div>
                </div>
            </div>

            <div class="panel" id="secInteractCmt">
                <div class="panel-title">
                    <span>التفاعل والرد على تعليق محدد</span>
                    <button type="button" class="switch-btn" id="btnTogIntCmt" onclick="toggleLocalBool('interact_cmt')"></button>
                </div>
                <div class="row-2">
                    <div class="field">
                        <label>طريقة البحث عن التعليق</label>
                        <select id="inpCmtMode">
                            <option value="first">أول تعليق ظاهر</option>
                            <option value="author">حسب اسم المعلق</option>
                            <option value="keyword">حسب كلمة داخل التعليق</option>
                            <option value="index">حسب الترتيب</option>
                        </select>
                    </div>
                    <div class="field">
                        <label>قيمة البحث (الاسم / الكلمة / الرقم)</label>
                        <input type="text" id="inpCmtTargetVal">
                    </div>
                </div>
                <div class="row-2">
                    <div class="field">
                        <label>تفاعل على التعليق</label>
                        <select id="inpCmtReact">
                            <option value="like">أعجبني</option>
                            <option value="love">أحببته</option>
                            <option value="care">أدعمه</option>
                            <option value="haha">هاهاها</option>
                            <option value="wow">واو</option>
                            <option value="sad">أحزنني</option>
                            <option value="angry">أغضبني</option>
                            <option value="none">بدون تفاعل</option>
                        </select>
                    </div>
                    <div class="field">
                        <label>نص الرد على التعليق</label>
                        <input type="text" id="inpCmtReply">
                    </div>
                </div>
            </div>

            <div class="panel" id="secFriend">
                <div class="panel-title">طلبات الصداقة والمتابعة</div>
                <div class="toggle-item"><span class="toggle-label">إرسال طلب صداقة</span><button type="button" class="switch-btn" id="btnTogFriend" onclick="toggleLocalBool('friend')"></button></div>
                <div class="toggle-item"><span class="toggle-label">إلغاء طلب صداقة</span><button type="button" class="switch-btn" id="btnTogCancelFriend" onclick="toggleLocalBool('cancel_friend')"></button></div>
                <div class="toggle-item"><span class="toggle-label">متابعة الحساب</span><button type="button" class="switch-btn" id="btnTogFollow" onclick="toggleLocalBool('follow')"></button></div>
                <div class="toggle-item"><span class="toggle-label">إلغاء المتابعة</span><button type="button" class="switch-btn" id="btnTogUnfollow" onclick="toggleLocalBool('unfollow')"></button></div>
            </div>

            <div class="panel" id="secMessage">
                <div class="panel-title">
                    <span>رسائل الماسنجر الخاصة</span>
                    <button type="button" class="switch-btn" id="btnTogMsg" onclick="toggleLocalBool('message')"></button>
                </div>
                <div class="field">
                    <label>نص الرسالة الخاصة</label>
                    <textarea id="inpMsgText"></textarea>
                </div>
            </div>

            <div class="panel" id="secReport">
                <div class="panel-title">البلاغات الرسمية والحظر</div>
                <div class="toggle-item"><span class="toggle-label">بلاغ عن منشور</span><button type="button" class="switch-btn" id="btnTogRepPost" onclick="toggleLocalBool('report_post')"></button></div>
                <div class="toggle-item"><span class="toggle-label">بلاغ عن الحساب بالكامل</span><button type="button" class="switch-btn" id="btnTogRepProf" onclick="toggleLocalBool('report_profile')"></button></div>
                <div class="toggle-item"><span class="toggle-label">حظر الحساب المستهدف</span><button type="button" class="switch-btn" id="btnTogBlock" onclick="toggleLocalBool('block')"></button></div>
                <div class="row-2" style="margin-top:8px;">
                    <div class="field">
                        <label>سبب البلاغ</label>
                        <select id="inpRepReason">
                            <option value="harassment">مضايقة أو إساءة</option>
                            <option value="fake">حساب مزيف / انتحال</option>
                            <option value="hate_violence">عنف أو كراهية</option>
                            <option value="fraud">احتيال وخداع</option>
                            <option value="adult">محتوى غير لائق</option>
                            <option value="spam">سبام ومحتوى مزعج</option>
                        </select>
                    </div>
                    <div class="field">
                        <label>الطرف المتضرر</label>
                        <select id="inpRepVictim">
                            <option value="me">أنا الشخص المتضرر</option>
                            <option value="not_real">ليس شخصاً حقيقياً</option>
                            <option value="friend">أحد أصدقائي</option>
                        </select>
                    </div>
                </div>
            </div>

            <div class="panel" id="secExecute">
                <div class="panel-title" style="margin-bottom:8px;">
                    <span>انتظار الشاشة الحية عند طلب التحقق</span>
                    <button type="button" class="switch-btn" id="btnTogWaitHitl" onclick="toggleWaitHitl()"></button>
                </div>
                <div id="missionCostBadge" class="mono" style="margin-bottom:8px;"></div>
                <button type="button" class="btn btn-ok" id="btnLaunchMission" onclick="launchMission()">بدء تنفيذ المهمة في الخلفية الآن</button>
                <div id="missionLiveBanner" class="status-banner hidden"></div>
                <div id="missionHitlBox" class="status-banner hidden" style="margin-top:8px;border-color:rgba(210,153,34,0.6);"></div>
            </div>
        </div>

        <!-- تبويب إدارة وإضافة الحسابات -->
        <div id="tab-accounts" class="tab-view hidden">
            <div style="margin-bottom:10px;" id="accBackBar">
                <button type="button" class="btn btn-muted btn-sm" onclick="goHomeTab()">رجوع للقائمة الرئيسية</button>
            </div>
            <div class="panel" id="secAddAccount">
                <div class="panel-title">إضافة حساب فيسبوك جديد للبوت</div>
                <div class="field"><label>اسم / لقب الحساب</label><input type="text" id="addAccName" placeholder="مثال: حساب فيسبوك 1"></div>
                <div class="field"><label>البريد الإلكتروني أو رقم الهاتف</label><input type="text" id="addAccEmail" placeholder="email@example.com"></div>
                <div class="field"><label>كلمة المرور</label><input type="password" id="addAccPass" placeholder="********"></div>
                <button type="button" class="btn btn-primary" id="btnAddAccSubmit" onclick="submitNewAccount()">إضافة وفحص الحساب الآن</button>
            </div>

            <div class="panel">
                <div class="panel-title">
                    <span id="accListTitle">الحسابات المسجلة</span>
                    <div style="display:flex;gap:6px;">
                        <button type="button" class="btn btn-muted btn-sm" id="btnCheckSessions" onclick="triggerCheckSessions()">فحص الجلسات</button>
                        <button type="button" class="btn btn-danger btn-sm hidden" id="btnPurgeBroken" onclick="purgeBroken()">تنظيف التالفة</button>
                    </div>
                </div>
                <div id="accountsContainer"></div>
            </div>
        </div>

        <!-- تبويب المستخدمين والصلاحيات -->
        <div id="tab-radar" class="tab-view hidden">
            <div class="panel">
                <div class="panel-title">
                    <span>المستخدمين والصلاحيات</span>
                    <div style="display:flex;gap:6px;">
                        <button type="button" class="btn btn-muted btn-sm" onclick="loadAdminRadar()">تحديث</button>
                        <button type="button" class="btn btn-muted btn-sm" onclick="goHomeTab()">رجوع</button>
                    </div>
                </div>
                <div id="radarUsersContainer"></div>
            </div>
            <div class="panel hidden" id="selectedUserDossier"></div>
        </div>

        <!-- تبويب سجل الرقابة (حصري لـ SUPER_ADMIN_ID) -->
        <div id="tab-audit" class="tab-view hidden">
            <div class="panel">
                <div class="panel-title">
                    <span>سجل الرقابة والأحداث الكامل</span>
                    <div style="display:flex;gap:6px;">
                        <button type="button" class="btn btn-muted btn-sm" onclick="loadAuditLogs()">تحديث</button>
                        <button type="button" class="btn btn-muted btn-sm" onclick="goHomeTab()">رجوع</button>
                    </div>
                </div>
                <div id="auditLogsContainer"></div>
            </div>
        </div>

        <!-- تبويب المحفظة والنقاط والإحالات -->
        <div id="tab-wallet" class="tab-view hidden">
            <div style="margin-bottom:10px;" id="walletBackBar">
                <button type="button" class="btn btn-muted btn-sm" onclick="goHomeTab()">رجوع للقائمة الرئيسية</button>
            </div>
            <div class="panel" id="walletSummaryCard"></div>
            <div class="panel hidden" id="referralPanel"></div>
            <div class="panel">
                <div class="panel-title">سجل حركات المحفظة والنقاط</div>
                <div id="ledgerContainer"></div>
            </div>
        </div>

        <!-- تبويب الدعم والموافقة على بيع الحسابات والمحاسبة -->
        <div id="tab-support" class="tab-view hidden">
            <div style="margin-bottom:10px;" id="supportBackBar">
                <button type="button" class="btn btn-muted btn-sm" onclick="goHomeTab()">رجوع للقائمة الرئيسية</button>
            </div>
            <div class="panel" id="supportComposerPanel"></div>
            <div class="panel">
                <div class="panel-title">سجل المحادثات وطلبات المحاسبة</div>
                <div id="supportTicketsContainer"></div>
            </div>
        </div>

        <!-- تبويب تسعيرة النقاط والوضع العام -->
        <div id="tab-economy" class="tab-view hidden">
            <div class="panel">
                <div class="panel-title">
                    <span>إعدادات النقاط والتسعيرة والوضع العام</span>
                    <button type="button" class="btn btn-muted btn-sm" onclick="goHomeTab()">رجوع</button>
                </div>
                <div id="economySettingsContainer"></div>
            </div>
        </div>

        <!-- تبويب الإعلانات العائمة التفاعلية -->
        <div id="tab-announcements" class="tab-view hidden">
            <div class="panel">
                <div class="panel-title">
                    <span>إعلانات المميزات العائمة والمثبتة</span>
                    <div style="display:flex;gap:6px;">
                        <button type="button" class="btn btn-muted btn-sm" onclick="loadAnnouncementsTab()">تحديث</button>
                        <button type="button" class="btn btn-muted btn-sm" onclick="goHomeTab()">رجوع</button>
                    </div>
                </div>
                <div class="field">
                    <label for="annTitle">عنوان الإعلان العائم</label>
                    <input type="text" id="annTitle" placeholder="مثال: ميزة البروكسي الذكي وفحص الحسابات التلقائي">
                </div>
                <div class="field">
                    <label for="annBody">تفاصيل العرض أو الميزة</label>
                    <textarea id="annBody" placeholder="اكتب شرحاً مختصراً وواضحاً يظهر في البطاقة العائمة داخل تلغرام والتطبيق..."></textarea>
                </div>
                <div class="row-2">
                    <div class="field">
                        <label for="annBadge">الشارة</label>
                        <select id="annBadge"></select>
                    </div>
                    <div class="field">
                        <label for="annStyle">نمط العرض العائم</label>
                        <select id="annStyle"></select>
                    </div>
                </div>
                <div class="row-2">
                    <div class="field">
                        <label for="annDeliveryMode">نمط بطاقة تلغرام</label>
                        <select id="annDeliveryMode"></select>
                    </div>
                    <div class="field">
                        <label for="annRepeatBehavior">سلوك التكرار (منع التكدس)</label>
                        <select id="annRepeatBehavior"></select>
                    </div>
                </div>
                <div class="field">
                    <label for="annEffect">التأثير التفاعلي بالرسالة</label>
                    <select id="annEffect"></select>
                </div>
                <div class="row-2">
                    <div class="field">
                        <label for="annDuration">مدة البقاء (إلغاء تلقائي عند الانتهاء)</label>
                        <select id="annDuration"></select>
                    </div>
                    <div class="field">
                        <label for="annRepeat">إعادة الإرسال والتكرار</label>
                        <select id="annRepeat"></select>
                    </div>
                </div>
                <div class="row-2">
                    <div class="field">
                        <label for="annCtaLabel">نص زر الإجراء</label>
                        <input type="text" id="annCtaLabel" value="فتح الميزة الآن">
                    </div>
                    <div class="field">
                        <label for="annCtaTab">التبويب المستهدف عند النقر</label>
                        <select id="annCtaTab">
                            <option value="mission">العمليات</option>
                            <option value="accounts">الحسابات</option>
                            <option value="wallet">المحفظة والإحالة</option>
                            <option value="support">الدعم والمحاسبة</option>
                        </select>
                    </div>
                </div>
                <div class="item-row" style="margin-bottom:10px;">
                    <label style="display:flex;align-items:center;gap:8px;cursor:pointer;margin-bottom:6px;text-transform:none;color:var(--text);">
                        <input type="checkbox" id="annPinChat" style="width:auto;">
                        <span>تثبيت أعلى المحادثة (اختياري — اتركه متوقفاً لمنع تكرار إشعارات التثبيت)</span>
                    </label>
                    <label style="display:flex;align-items:center;gap:8px;cursor:pointer;margin-bottom:6px;text-transform:none;color:var(--text);">
                        <input type="checkbox" id="annPushNow" checked style="width:auto;">
                        <span>بث فوري وإيقاظ اللوحة لدى جميع المستخدمين</span>
                    </label>
                    <label style="display:flex;align-items:center;gap:8px;cursor:pointer;margin:0;text-transform:none;color:var(--text);">
                        <input type="checkbox" id="annRepeatOnOpen" checked style="width:auto;">
                        <span>إبراز البطاقة العائمة تلقائياً عند فتح لوحة التحكم</span>
                    </label>
                </div>
                <button type="button" class="btn btn-primary" id="btnCreateAnn" onclick="createAnnouncementSubmit()">نشر وبث البطاقة الذكية الآن</button>
            </div>
            <div class="panel">
                <div class="panel-title">الإعلانات المنشورة</div>
                <div id="announcementsAdminList"></div>
            </div>
        </div>

        <!-- تبويب البروكسيات والمراقبة الحية -->
        <div id="tab-proxies" class="tab-view hidden">
            <div class="panel">
                <div class="panel-title">
                    <span>مراقبة البروكسيات والاستخدام التفصيلي</span>
                    <div style="display:flex;gap:6px;">
                        <button type="button" class="btn btn-muted btn-sm" onclick="loadProxiesTab()">تحديث</button>
                        <button type="button" class="btn btn-muted btn-sm" onclick="goHomeTab()">رجوع</button>
                    </div>
                </div>
                <div id="proxyKpiGrid" class="proxy-kpi-grid"></div>
                <div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:10px;">
                    <button type="button" class="btn btn-primary btn-sm" onclick="proxyAction('check_all')">فحص كل البروكسيات</button>
                    <button type="button" class="btn btn-ok btn-sm" onclick="proxyAction('bind_existing')">توزيع وربط الحسابات</button>
                    <button type="button" class="btn btn-muted btn-sm" onclick="proxyAction('fetch_github')">سحب وفحص GitHub</button>
                    <button type="button" class="btn btn-muted btn-sm" id="btnProxyWatchToggle" onclick="proxyAction('toggle_watch')">المراقب التلقائي</button>
                    <button type="button" class="btn btn-danger btn-sm" onclick="proxyAction('clear_dead')">حذف الميتة</button>
                </div>
                <div class="row-2" style="margin-bottom:10px;">
                    <div class="field">
                        <label for="inpProxyCap">الحد الآمن للحسابات لكل IP</label>
                        <select id="inpProxyCap" onchange="proxyAction('set_cap', {limit: parseInt(this.value, 10)})">
                            <option value="3">3 حسابات لكل IP (موصى به)</option>
                            <option value="5">5 حسابات لكل IP (أقصى حد)</option>
                            <option value="0">غير محدود</option>
                        </select>
                    </div>
                    <div class="field">
                        <label for="inpProxyInterval">فترة الفحص التلقائي المستمر</label>
                        <select id="inpProxyInterval" onchange="proxyAction('set_interval', {seconds: parseInt(this.value, 10)})">
                            <option value="60">كل 60 ثانية</option>
                            <option value="120">كل دقيقتين</option>
                            <option value="300">كل 5 دقائق</option>
                            <option value="600">كل 10 دقائق</option>
                        </select>
                    </div>
                </div>
                <div class="field">
                    <label for="inpProxiesBulk">إضافة بروكسيات (socks5 / http / ip:port:user:pass)</label>
                    <textarea id="inpProxiesBulk" rows="3" placeholder="45.38.107.97:6014:user:pass"></textarea>
                </div>
                <button type="button" class="btn btn-primary" onclick="submitBulkProxies()">حفظ البروكسيات وربط الحسابات فوراً</button>
            </div>
            <div class="panel">
                <div class="panel-title">تفاصيل كل IP (عدد الاستخدامات + الحسابات المربوطة به)</div>
                <div id="proxiesDetailList"></div>
            </div>
        </div>
    </div>
</div>

<div id="toast" class="toast" role="status" aria-live="polite"></div>

<div id="promoToastRegion" role="region" aria-label="تنبيهات المميزات العائمة">
    <div id="promoToastCard" class="promo-toast-card" popover="manual">
        <div class="promo-head">
            <span id="promoToastBadge" class="promo-badge">ميزة جديدة</span>
            <button type="button" id="promoToastCloseBtn" class="btn btn-muted btn-sm" popovertarget="promoToastCard" popovertargetaction="hide">إغلاق</button>
        </div>
        <div id="promoToastTitle" class="promo-title"></div>
        <div id="promoToastBody" class="promo-body"></div>
        <div class="promo-actions">
            <button type="button" id="promoToastOpenBtn" class="btn btn-primary btn-sm">معاينة البطاقة</button>
            <button type="button" id="promoToastAckBtn" class="btn btn-ok btn-sm">فتح الميزة</button>
        </div>
    </div>
</div>

<dialog id="promoModal" class="promo-dialog" closedby="any" aria-labelledby="promoModalTitle">
    <div class="promo-modal-inner" id="promoModalInner">
        <div class="promo-head">
            <span id="promoModalBadge" class="promo-badge">ميزة جديدة</span>
            <span id="promoModalTtl" class="mono"></span>
        </div>
        <div id="promoModalTitle" class="promo-title" style="font-size:16px;margin-bottom:8px;"></div>
        <div id="promoModalBody" class="promo-body" style="color:var(--text);font-size:13px;"></div>
        <div class="promo-modal-footer">
            <button type="button" id="promoModalCtaBtn" class="btn btn-ok btn-sm">الانتقال الآن</button>
            <button type="button" id="promoModalCloseBtn" class="btn btn-muted btn-sm">تم الاطلاع وإغلاق</button>
        </div>
    </div>
</dialog>

<dialog id="hitlDialog" class="hitl-dialog" aria-labelledby="hitlDialogTitle" closedby="closerequest">
    <div class="hitl-head">
        <h2 id="hitlDialogTitle">الشاشة الحية التفاعلية لحل التحقق</h2>
        <div class="hitl-head-actions">
            <span class="hitl-zoom-badge" id="hitlTtlBadge">--:--</span>
            <button type="button" class="btn btn-muted btn-sm" id="btnHitlExtend" onclick="hitlAction('extend_ttl')">⏳ +5د</button>
            <button type="button" class="btn btn-muted btn-sm" id="btnHitlClose" autofocus>إغلاق</button>
        </div>
    </div>
    <div class="hitl-body">
        <div id="hitlLiveStatus" role="status" aria-live="polite" class="status-banner" style="margin-top:0;">جاري تجهيز المتصفح...</div>
        <div id="hitlArBar" class="hitl-ar-bar hidden"></div>
        <div class="hitl-zoom-bar">
            <div class="hitl-zoom-group">
                <button type="button" class="btn btn-muted btn-sm" aria-label="تصغير الشاشة" onclick="hitlZoom(-0.5)">🔍-</button>
                <span class="hitl-zoom-badge" id="hitlZoomBadge">1.0x</span>
                <button type="button" class="btn btn-muted btn-sm" aria-label="تكبير الشاشة" onclick="hitlZoom(0.5)">🔍+</button>
                <button type="button" class="btn btn-muted btn-sm" onclick="hitlResetZoom()">إعادة</button>
            </div>
            <div class="hitl-zoom-group">
                <button type="button" class="btn btn-muted btn-sm" id="btnHitlPanMode" onclick="hitlTogglePanMode()">👆 نقر</button>
                <button type="button" class="btn btn-muted btn-sm" id="btnHitlViewportMode" onclick="hitlToggleViewportMode()">🖥️ كمبيوتر</button>
                <button type="button" class="btn btn-muted btn-sm" id="btnHitlTranslate" onclick="hitlAction('toggle_translate')">🌐 ترجمة: ✅</button>
            </div>
        </div>
        <div class="hitl-stage" id="hitlStage">
            <div class="hitl-canvas-wrap" id="hitlCanvasWrap">
                <img id="hitlScreenImg" alt="شاشة متصفح الحساب الحية — انقر مباشرة في موضع زر التحقق أو مربع الإدخال">
                <div id="hitlTapDot" class="hitl-tap-dot hidden"></div>
            </div>
        </div>
        <div class="hitl-toolbar">
            <button type="button" class="btn btn-ok btn-sm" onclick="hitlAction('check_now')">✅ فحص وحفظ الجلسة</button>
            <button type="button" class="btn btn-warn btn-sm" id="btnHitlPauseAuto" onclick="hitlAction('pause_auto')">✋ تحكم يدوي</button>
            <button type="button" class="btn btn-primary btn-sm hidden" id="btnHitlPrefill" onclick="hitlAction('prefill_creds')">🔑 دخول تلقائي أمامي</button>
        </div>
        <details class="hitl-tools-drawer">
            <summary>⌨️ أزرار التحكم والكتابة ورمز التحقق (2FA / OTP)</summary>
            <div class="hitl-toolbar" style="margin-bottom:6px;">
                <button type="button" class="btn btn-muted btn-sm" onclick="hitlScroll(-320)">أعلى</button>
                <button type="button" class="btn btn-muted btn-sm" onclick="hitlScroll(320)">أسفل</button>
                <button type="button" class="btn btn-muted btn-sm" onclick="hitlKey('Tab')">Tab</button>
                <button type="button" class="btn btn-muted btn-sm" onclick="hitlKey('Space')">مسافة</button>
                <button type="button" class="btn btn-muted btn-sm" onclick="hitlKey('Enter')">Enter</button>
                <button type="button" class="btn btn-muted btn-sm" onclick="hitlKey('Backspace')">حذف حرف</button>
                <button type="button" class="btn btn-muted btn-sm" onclick="hitlAction('reload')">تحديث الصفحة</button>
            </div>
            <div class="field" style="margin-bottom:0;">
                <label for="hitlTextInput">إرسال نص أو رمز التحقق (2FA / OTP) إلى الصفحة الحية</label>
                <div style="display:flex;gap:6px;flex-wrap:wrap;">
                    <input type="text" id="hitlTextInput" autocomplete="one-time-code" placeholder="أدخل رمز 2FA أو أي نص لإرساله للحقل المحدد..." style="flex:1;min-width:160px;">
                    <button type="button" class="btn btn-primary btn-sm" onclick="hitlSendText(true)">إرسال + Enter</button>
                    <button type="button" class="btn btn-muted btn-sm" onclick="hitlSendText(false)">كتابة فقط</button>
                </div>
            </div>
        </details>
    </div>
</dialog>

<script>
const tg = window.Telegram && window.Telegram.WebApp ? window.Telegram.WebApp : null;
if (tg) {
    tg.ready();
    tg.expand();
}

let appState = null;
let selectedRadarUid = null;
let currentTabs = [];
let lastEventSeq = 0;
let syncRunning = false;
let syncAbortCtrl = null;
let lastRadarData = null;
let activePromoAnn = null;
let queuedPromoAnn = null;
let promoToastTimer = null;
let promoToastPaused = false;
let promoTickerInterval = null;
let promoShownOnOpen = {};
let promoLastRepopAt = {};
let promoDialogWired = false;
let _canTransDisplayCached = null;

if (tg && tg.BackButton) {
    tg.BackButton.onClick(() => handleNativeBack());
}

function escHtml(v) {
    return String(v == null ? "" : v)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
}

function showToast(msg) {
    const t = document.getElementById("toast");
    t.textContent = msg;
    t.style.display = "block";
    setTimeout(() => { t.style.display = "none"; }, 3200);
}

async function apiCall(path, method = "GET", bodyObj = null, signal = null) {
    const initData = tg ? tg.initData : "";
    const opts = {
        method,
        headers: {
            "Content-Type": "application/json",
            "X-Telegram-Init-Data": initData || ""
        }
    };
    if (signal) {
        opts.signal = signal;
    }
    if (bodyObj !== null) {
        opts.body = JSON.stringify(bodyObj);
    }
    const res = await fetch(path, opts);
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
        const err = new Error(data.error || ("HTTP " + res.status));
        err.status = res.status;
        throw err;
    }
    return data;
}

function closeRadarDossier() {
    selectedRadarUid = null;
    const panel = document.getElementById("selectedUserDossier");
    if (panel) {
        panel.classList.add("hidden");
        panel.innerHTML = "";
    }
    updateTelegramBackButton();
}

function goHomeTab() {
    if (selectedRadarUid !== null) {
        closeRadarDossier();
    }
    if (currentTabs.length > 0) {
        switchTab(currentTabs[0].id);
    }
}

function handleNativeBack() {
    const activeTab = document.getElementById("tabsBar")?.dataset.activeTab || "";
    if (activeTab === "radar" && selectedRadarUid !== null) {
        closeRadarDossier();
        return;
    }
    if (currentTabs.length > 1 && activeTab !== currentTabs[0].id) {
        switchTab(currentTabs[0].id);
    }
}

function updateTelegramBackButton() {
    if (!tg || !tg.BackButton) return;
    const activeTab = document.getElementById("tabsBar")?.dataset.activeTab || "";
    const inSubView = (activeTab === "radar" && selectedRadarUid !== null) ||
        (currentTabs.length > 1 && activeTab && activeTab !== currentTabs[0].id);
    try {
        if (inSubView) tg.BackButton.show();
        else tg.BackButton.hide();
    } catch (_) {}
}

function refreshUsableSelect() {
    const sel = document.getElementById("inpSelectedAcc");
    if (!sel || !appState) return;
    const prevVal = sel.value || (appState.mission_state && appState.mission_state.selected_acc) || "all";
    sel.innerHTML = "";
    const optAll = document.createElement("option");
    optAll.value = "all";
    optAll.textContent = "جميع الحسابات المتاحة النشطة";
    sel.appendChild(optAll);
    for (const a of (appState.usable_accounts || [])) {
        const opt = document.createElement("option");
        opt.value = a.id;
        opt.textContent = (a.is_active ? "[نشط] " : "[غير نشط] ") + a.name;
        sel.appendChild(opt);
    }
    const exists = Array.from(sel.options).some(o => o.value === prevVal);
    sel.value = exists ? prevVal : "all";
}

async function applyLiveSyncUpdate(scopes) {
    const fresh = await apiCall("/api/bootstrap");
    if (fresh.event_seq) lastEventSeq = fresh.event_seq;

    if (!fresh.authorized) {
        document.getElementById("appShell").classList.add("hidden");
        const lb = document.getElementById("lockedBox");
        lb.classList.remove("hidden");
        document.getElementById("lockedTitle").textContent = fresh.status === "banned" ? "حسابك محظور" : "بانتظار موافقة المطور";
        document.getElementById("lockedMsg").textContent = fresh.message || "يرجى انتظار اعتماد المطور وتخصيص الصلاحيات لك.";
        const irb = document.getElementById("inviteRedeemBox");
        if (irb) irb.classList.toggle("hidden", !fresh.can_redeem_invite);
        updateTelegramBackButton();
        return;
    }

    const wasLocked = !appState || !appState.authorized;
    const prevPerms = JSON.stringify(appState && appState.permissions ? appState.permissions : {});
    const prevCaps = JSON.stringify(appState && appState.capabilities ? appState.capabilities : {});
    const prevTier = (appState && appState.admin_tier) || "";
    const prevAnnIds = new Set((appState && appState.announcements ? appState.announcements : []).map(a => a.id));

    const nextPerms = JSON.stringify(fresh.permissions || {});
    const nextCaps = JSON.stringify(fresh.capabilities || {});
    const nextTier = fresh.admin_tier || "";
    appState = fresh;
    document.getElementById("appShell").classList.remove("hidden");

    const scList = scopes || [];
    if (wasLocked || prevPerms !== nextPerms || prevCaps !== nextCaps || prevTier !== nextTier) {
        renderApp();
    } else {
        updateWalletTopbar();
        renderMissionBanner();
        renderMissionCostBadge();
        refreshUsableSelect();
        renderAccountsList();
        renderWalletTab();
        renderSupportComposer();
        renderSupportTickets();
    }

    const caps = fresh.capabilities || {};
    const activeTab = document.getElementById("tabsBar")?.dataset.activeTab || "";
    if ((fresh.is_super_admin || caps.radar_users) && (scList.includes("users") || scList.includes("accounts") || scList.includes("economy") || scList.includes("support")) && activeTab === "radar") {
        await loadAdminRadar();
    }
    if ((fresh.is_super_admin || caps.audit_logs) && (scList.includes("audit") || scList.includes("users") || scList.includes("accounts")) && activeTab === "audit") {
        await loadAuditLogs();
    }
    if ((fresh.is_super_admin || caps.points_economy) && scList.includes("economy") && activeTab === "economy") {
        renderEconomyTab();
    }
    if ((fresh.is_super_admin || caps.announcements) && scList.includes("announcements") && activeTab === "announcements") {
        renderAnnouncementsList();
    }
    if ((fresh.is_super_admin || caps.proxies) && (scList.includes("proxies") || scList.includes("accounts")) && activeTab === "proxies") {
        await loadProxiesTab();
    }
    if (scList.includes("announcements")) {
        const latestAnns = fresh.announcements || [];
        const newItem = latestAnns.find(a => !prevAnnIds.has(a.id)) || latestAnns[0];
        if (newItem) {
            presentFloatingAnnouncement(newItem, newItem.display_style === "full_spotlight");
        } else if (activePromoAnn) {
            hidePromoToast();
        }
    }
}

async function startEventSyncLoop() {
    if (syncRunning) return;
    syncRunning = true;
    let backoffMs = 1500;

    while (syncRunning) {
        if (document.visibilityState === "hidden") {
            await new Promise(r => setTimeout(r, 800));
            continue;
        }
        try {
            syncAbortCtrl = new AbortController();
            const ev = await apiCall("/api/sync/wait?since=" + lastEventSeq + "&timeout=22", "GET", null, syncAbortCtrl.signal);
            backoffMs = 1500;
            if (ev && typeof ev.seq === "number" && ev.seq > lastEventSeq) {
                lastEventSeq = ev.seq;
            }
            if (ev && ev.changed) {
                await applyLiveSyncUpdate(ev.scopes || []);
            }
        } catch (err) {
            if (err && err.name === "AbortError") {
                continue;
            }
            if (err && (err.status === 401 || err.status === 403)) {
                syncRunning = false;
                break;
            }
            await new Promise(r => setTimeout(r, backoffMs));
            backoffMs = Math.min(8000, backoffMs * 2);
        }
    }
}

document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "hidden" && syncAbortCtrl) {
        try { syncAbortCtrl.abort(); } catch (_) {}
    } else if (document.visibilityState === "visible" && syncRunning) {
        applyLiveSyncUpdate(["users", "accounts", "audit", "mission", "economy", "support", "announcements"]).catch(() => {});
    }
});

async function redeemInviteCode() {
    const code = (document.getElementById("inpRedeemCode")?.value || "").trim();
    if (!code) {
        showToast("أدخل كود الدعوة أولاً");
        return;
    }
    try {
        const res = await apiCall("/api/referral/redeem", "POST", { code });
        showToast(res.message || "تم التفعيل بنجاح!");
        await bootstrap();
    } catch (e) {
        showToast(e.message);
    }
}

async function bootstrap() {
    try {
        wirePromoControls();
        const data = await apiCall("/api/bootstrap");
        document.getElementById("loadingBox").classList.add("hidden");
        if (data.event_seq) lastEventSeq = data.event_seq;

        if (!data.authorized) {
            appState = data;
            const lb = document.getElementById("lockedBox");
            lb.classList.remove("hidden");
            document.getElementById("lockedTitle").textContent = data.status === "banned" ? "حسابك محظور" : "بانتظار موافقة المطور";
            document.getElementById("lockedMsg").textContent = data.message || "يرجى انتظار اعتماد المطور وتخصيص الصلاحيات لك.";
            const irb = document.getElementById("inviteRedeemBox");
            if (irb) irb.classList.toggle("hidden", !data.can_redeem_invite);
            startEventSyncLoop();
            return;
        }

        appState = data;
        document.getElementById("appShell").classList.remove("hidden");
        renderApp();
        startEventSyncLoop();
        const urlParams = new URLSearchParams(window.location.search);
        const deepHitl = (urlParams.get("hitl") || "").trim();
        const deepPromo = (urlParams.get("promo") || "").trim();
        if (deepHitl) {
            if (currentTabs.some(t => t.id === "accounts")) switchTab("accounts", false);
            openHitlLive(deepHitl);
        } else if (deepPromo) {
            const targetAnn = (appState.announcements || []).find(a => a.id === deepPromo) || (appState.announcements || [])[0];
            if (targetAnn) openPromoModal(targetAnn);
        } else {
            triggerOpenPromoIfNeeded();
        }
    } catch (err) {
        document.getElementById("loadingBox").classList.add("hidden");
        const lb = document.getElementById("lockedBox");
        lb.classList.remove("hidden");
        document.getElementById("lockedTitle").textContent = "تعذر التحقق من جلسة تلغرام";
        document.getElementById("lockedMsg").textContent = err.message || "افتح اللوحة من زر القائمة داخل تلغرام حصراً.";
    }
}

function updateWalletTopbar() {
    if (!appState) return;
    const wp = document.getElementById("walletPill");
    if (!wp) return;
    const w = appState.wallet || { points: 0, yer_value: 0 };
    wp.textContent = (w.points || 0) + " نقطة (" + Number(w.yer_value || 0).toLocaleString("en-US") + " ريال)";
}

function renderApp() {
    document.getElementById("lockedBox").classList.add("hidden");
    const u = appState.user;
    const p = appState.permissions || {};
    const caps = appState.capabilities || {};
    const isDev = !!appState.is_super_admin;

    document.getElementById("userNameLbl").textContent = u.name || "FB Operator";
    document.getElementById("rolePill").textContent = appState.admin_tier_label || (isDev ? "المطور الرئيسي" : "عضو معتمد");
    updateWalletTopbar();

    const enabledLabels = appState.enabled_labels || [];
    if (isDev) {
        document.getElementById("userPermsSummary").textContent = "تحكم كامل";
    } else if (appState.admin_tier === "super_delegate" || appState.admin_tier === "manager") {
        document.getElementById("userPermsSummary").textContent =
            (appState.admin_tier_label || "مفوّض إداري") +
            (enabledLabels.length ? " | المفعل: " + enabledLabels.join("، ") : "");
    } else {
        document.getElementById("userPermsSummary").textContent =
            enabledLabels.length ? "المفعل: " + enabledLabels.join("، ") : "بانتظار تفعيل الميزات من المطور";
    }

    // بناء التبويبات حسب الصلاحيات والرتبة الإدارية بدقة
    const hasActions = isDev || p.can_react || p.can_comment || p.can_interact_comments || p.can_friend_follow || p.can_message || p.can_report;
    const hasAccTab = isDev || caps.accounts_pool || p.can_add_accounts || p.can_delete_accounts;
    const hasAnyPerm = isDev || Object.values(p || {}).some(Boolean) || Object.values(caps).some(Boolean) || ((appState.wallet && appState.wallet.points) > 0);

    const tabs = [];
    if (hasActions) tabs.push({ id: "mission", label: "العمليات" });
    if (hasAccTab) tabs.push({ id: "accounts", label: (p.can_add_accounts && !hasActions && !isDev && !caps.accounts_pool) ? "إضافة الحسابات" : "الحسابات" });
    if (hasAnyPerm) {
        tabs.push({ id: "wallet", label: "المحفظة والإحالة" });
        tabs.push({ id: "support", label: (isDev || caps.payment_notices) ? "صندوق الدعم والبيع" : "الدعم وبيع الحسابات" });
    }
    if (isDev || caps.radar_users) tabs.push({ id: "radar", label: "المستخدمين والصلاحيات" });
    if (isDev || caps.proxies) tabs.push({ id: "proxies", label: "البروكسيات" });
    if (isDev || caps.announcements) tabs.push({ id: "announcements", label: "الإعلانات العائمة" });
    if (isDev || caps.points_economy) tabs.push({ id: "economy", label: "تسعيرة النقاط والوضع العام" });
    if (isDev || caps.audit_logs) tabs.push({ id: "audit", label: "سجل الرقابة" });
    currentTabs = tabs;

    const accBackBar = document.getElementById("accBackBar");
    if (accBackBar) {
        accBackBar.classList.toggle("hidden", tabs.length <= 1 || tabs[0].id === "accounts");
    }

    const tabsBar = document.getElementById("tabsBar");
    tabsBar.innerHTML = "";

    if (!tabs.length) {
        document.querySelectorAll(".tab-view").forEach(v => v.classList.add("hidden"));
        const lb = document.getElementById("lockedBox");
        lb.classList.remove("hidden");
        document.getElementById("lockedTitle").textContent = "حسابك معتمد بنجاح";
        document.getElementById("lockedMsg").textContent = "لم يفعّل المطور أي أداة أو صلاحية لحسابك بعد.";
        const irb = document.getElementById("inviteRedeemBox");
        if (irb) irb.classList.add("hidden");
        updateTelegramBackButton();
        syncPromoTicker();
        return;
    }

    const currentActive = tabsBar.dataset.activeTab;
    const activeTabId = tabs.some(t => t.id === currentActive) ? currentActive : tabs[0].id;
    tabsBar.dataset.activeTab = activeTabId;

    for (const t of tabs) {
        const b = document.createElement("button");
        b.type = "button";
        b.dataset.tabId = t.id;
        b.className = "tab-btn" + (t.id === activeTabId ? " active" : "");
        b.textContent = t.label;
        b.onclick = () => switchTab(t.id);
        tabsBar.appendChild(b);
    }

    switchTab(activeTabId, false);
    populateMissionForm();
    renderAccountsList();
    renderWalletTab();
    renderSupportComposer();
    renderSupportTickets();
    if (isDev || caps.points_economy) renderEconomyTab();
    if (isDev || caps.announcements) {
        populateAnnouncementFormMeta();
        renderAnnouncementsList();
    }
    if (isDev || caps.proxies) renderProxiesTab(appState.proxy_report);
    syncPromoTicker();
}

function switchTab(tabId, reloadData = true) {
    document.getElementById("tabsBar").dataset.activeTab = tabId;
    document.querySelectorAll(".tab-btn").forEach(btn => {
        btn.classList.toggle("active", btn.dataset.tabId === tabId);
    });

    document.querySelectorAll(".tab-view").forEach(v => v.classList.add("hidden"));
    const target = document.getElementById("tab-" + tabId);
    if (target) target.classList.remove("hidden");

    updateTelegramBackButton();

    if (reloadData) {
        if (tabId === "radar") loadAdminRadar();
        if (tabId === "proxies") loadProxiesTab();
        if (tabId === "announcements") loadAnnouncementsTab();
        if (tabId === "audit") loadAuditLogs();
        if (tabId === "economy") renderEconomyTab();
        if (tabId === "wallet") renderWalletTab();
        if (tabId === "support") { renderSupportComposer(); renderSupportTickets(); }
    }
}

function setToggleBtn(id, val) {
    const el = document.getElementById(id);
    if (!el) return;
    el.textContent = val ? "مفعل" : "معطل";
    el.className = "switch-btn " + (val ? "switch-on" : "switch-off");
}

function toggleLocalBool(field) {
    if (!appState || !appState.mission_state) return;
    const ms = appState.mission_state;
    ms[field] = !ms[field];
    if (field === "friend" && ms.friend) ms.cancel_friend = false;
    if (field === "cancel_friend" && ms.cancel_friend) ms.friend = false;
    if (field === "follow" && ms.follow) ms.unfollow = false;
    if (field === "unfollow" && ms.unfollow) ms.follow = false;
    if (field === "report_post" && ms.report_post) ms.report_profile = false;
    if (field === "report_profile" && ms.report_profile) ms.report_post = false;
    populateMissionForm();
}

function populateMissionForm() {
    const p = appState.permissions;
    const isDev = appState.is_super_admin;
    const ms = appState.mission_state;

    // إظهار الأقسام المصرح بها فقط
    document.getElementById("secReact").classList.toggle("hidden", !(isDev || p.can_react));
    document.getElementById("secComment").classList.toggle("hidden", !(isDev || p.can_comment));
    document.getElementById("secInteractCmt").classList.toggle("hidden", !(isDev || p.can_interact_comments));
    document.getElementById("secFriend").classList.toggle("hidden", !(isDev || p.can_friend_follow));
    document.getElementById("secMessage").classList.toggle("hidden", !(isDev || p.can_message));
    document.getElementById("secReport").classList.toggle("hidden", !(isDev || p.can_report));
    document.getElementById("secExecute").classList.toggle("hidden", !(isDev || p.can_execute));

    const canUse = isDev || p.can_use_accounts || (p.can_execute && (appState.usable_accounts || []).length > 0);
    document.getElementById("grpExecutor").classList.toggle("hidden", !canUse);

    const sel = document.getElementById("inpSelectedAcc");
    sel.innerHTML = "";
    const optAll = document.createElement("option");
    optAll.value = "all";
    optAll.textContent = "جميع الحسابات المتاحة النشطة";
    sel.appendChild(optAll);
    const optMulti = document.createElement("option");
    optMulti.value = "multi";
    optMulti.textContent = "تحديد حسابات معينة (متعدد)";
    sel.appendChild(optMulti);
    for (const a of (appState.usable_accounts || [])) {
        const opt = document.createElement("option");
        opt.value = a.id;
        opt.textContent = (a.is_active ? "[نشط] " : "[غير نشط] ") + a.name;
        sel.appendChild(opt);
    }
    sel.value = ms.selected_acc || "all";
    renderMultiAccPicker();

    document.getElementById("inpTargetUrl").value = ms.target_url || "";
    document.getElementById("inpAccLimit").value = ms.acc_count_limit || 0;
    document.getElementById("inpReactionType").value = ms.reaction_type || "like";
    document.getElementById("inpReactIndex").value = ms.react_post_index || 1;
    document.getElementById("inpReactUrl").value = ms.react_post_url || "";
    document.getElementById("inpCommentText").value = ms.comment_text || "";
    document.getElementById("inpCommentIndex").value = ms.comment_post_index || 1;
    document.getElementById("inpCommentUrl").value = ms.comment_post_url || "";
    document.getElementById("inpCmtMode").value = ms.cmt_target_mode || "first";
    document.getElementById("inpCmtTargetVal").value = ms.cmt_target_val || "";
    document.getElementById("inpCmtReact").value = ms.cmt_reaction || "like";
    document.getElementById("inpCmtReply").value = ms.cmt_reply || "";
    document.getElementById("inpMsgText").value = ms.message_text || "";
    document.getElementById("inpRepReason").value = ms.rep_reason || "harassment";
    document.getElementById("inpRepVictim").value = ms.rep_victim || "me";

    setToggleBtn("btnTogReact", !!ms.like);
    setToggleBtn("btnTogComment", !!ms.comment);
    setToggleBtn("btnTogIntCmt", !!ms.interact_cmt);
    setToggleBtn("btnTogFriend", !!ms.friend);
    setToggleBtn("btnTogCancelFriend", !!ms.cancel_friend);
    setToggleBtn("btnTogFollow", !!ms.follow);
    setToggleBtn("btnTogUnfollow", !!ms.unfollow);
    setToggleBtn("btnTogMsg", !!ms.message);
    setToggleBtn("btnTogRepPost", !!ms.report_post);
    setToggleBtn("btnTogRepProf", !!ms.report_profile);
    setToggleBtn("btnTogBlock", !!ms.block);
    setToggleBtn("btnTogWaitHitl", ms.wait_for_hitl !== false);

    renderMissionBanner();
    renderMissionCostBadge();
}

function onSelectedAccChange() {
    if (!appState || !appState.mission_state) return;
    const val = document.getElementById("inpSelectedAcc").value || "all";
    appState.mission_state.selected_acc = val;
    if (val === "multi" && (!Array.isArray(appState.mission_state.selected_accs) || !appState.mission_state.selected_accs.length)) {
        appState.mission_state.selected_accs = [];
    }
    renderMultiAccPicker();
    renderMissionCostBadge();
}

function renderMultiAccPicker() {
    const box = document.getElementById("multiAccPicker");
    if (!box || !appState || !appState.mission_state) return;
    const ms = appState.mission_state;
    const selVal = document.getElementById("inpSelectedAcc")?.value || ms.selected_acc || "all";
    box.classList.toggle("hidden", selVal !== "multi");
    if (selVal !== "multi") return;

    const picked = new Set(Array.isArray(ms.selected_accs) ? ms.selected_accs : []);
    box.innerHTML = "";
    for (const a of (appState.usable_accounts || [])) {
        const chip = document.createElement("button");
        chip.type = "button";
        chip.className = "multi-acc-chip" + (picked.has(a.id) ? " picked" : "");
        const left = document.createElement("span");
        left.textContent = (picked.has(a.id) ? "☑ " : "☐ ") + a.name;
        const badge = document.createElement("span");
        badge.className = a.is_active ? "badge-ok" : "badge-bad";
        badge.textContent = a.is_active ? "نشط" : "متوقف";
        chip.appendChild(left);
        chip.appendChild(badge);
        chip.onclick = () => {
            const arr = new Set(Array.isArray(ms.selected_accs) ? ms.selected_accs : []);
            if (arr.has(a.id)) arr.delete(a.id);
            else arr.add(a.id);
            ms.selected_accs = Array.from(arr);
            renderMultiAccPicker();
            renderMissionCostBadge();
        };
        box.appendChild(chip);
    }
}

function toggleWaitHitl() {
    if (!appState || !appState.mission_state) return;
    appState.mission_state.wait_for_hitl = !(appState.mission_state.wait_for_hitl !== false);
    setToggleBtn("btnTogWaitHitl", !!appState.mission_state.wait_for_hitl);
}

function renderMissionCostBadge() {
    const el = document.getElementById("missionCostBadge");
    if (!el || !appState || !appState.mission_state) return;
    if (appState.is_super_admin) {
        el.textContent = "المطور الرئيسي: تنفيذ مجاني غير محدود بدون خصم نقاط";
        return;
    }
    const cfg = appState.economy_settings || {};
    const costs = cfg.operation_costs || {};
    const ms = appState.mission_state;
    let perAcc = 0;
    for (const k of Object.keys(costs)) {
        if (ms[k]) perAcc += Number(costs[k] || 0);
    }
    const selAcc = document.getElementById("inpSelectedAcc")?.value || ms.selected_acc || "all";
    const usable = appState.usable_accounts || [];
    const activePool = usable.filter(a => a.is_active);
    const poolLen = activePool.length || usable.length || 1;
    const lim = parseInt(document.getElementById("inpAccLimit")?.value || ms.acc_count_limit || "0", 10) || 0;
    let estAccs = 1;
    if (selAcc === "multi") {
        estAccs = Math.max(1, (ms.selected_accs || []).length);
    } else if (selAcc === "all") {
        estAccs = lim > 0 ? Math.min(poolLen, lim) : poolLen;
    }
    const totalCost = perAcc * estAccs;
    const bal = (appState.wallet && appState.wallet.points) || 0;
    if (appState.points_enforced) {
        el.textContent = "تكلفة هذه المهمة: " + totalCost + " نقطة | رصيدك المتاح: " + bal + " نقطة";
        el.className = bal >= totalCost ? "badge-ok" : "badge-bad";
    } else {
        el.textContent = "نظام الخصم الفوري للنقاط معطل حالياً من المطور | رصيدك: " + bal + " نقطة";
        el.className = "mono";
    }
}

function renderMissionBanner() {
    const ms = appState.mission_state || {};
    const banner = document.getElementById("missionLiveBanner");
    const btn = document.getElementById("btnLaunchMission");
    const hitlBox = document.getElementById("missionHitlBox");
    if (btn) btn.disabled = !!ms.is_running;
    if (ms.live_status_text) {
        banner.classList.remove("hidden");
        banner.textContent = ms.live_status_text;
    }
    if (hitlBox) {
        if (ms.waiting_hitl_acc_id) {
            hitlBox.classList.remove("hidden");
            hitlBox.innerHTML = "";
            const title = document.createElement("div");
            title.style.fontWeight = "700";
            title.style.marginBottom = "6px";
            title.textContent = "المهمة متوقفة مؤقتاً بانتظار إكمال التحقق للحساب: " + ms.waiting_hitl_acc_id;
            const reasonEl = document.createElement("div");
            reasonEl.className = "mono";
            reasonEl.style.marginBottom = "8px";
            reasonEl.textContent = ms.waiting_hitl_reason || "افتح الشاشة الحية لحل التحقق وسيُستكمل التنفيذ تلقائياً.";
            const actions = document.createElement("div");
            actions.style.cssText = "display:flex;gap:6px;flex-wrap:wrap;";
            const bOpen = document.createElement("button");
            bOpen.type = "button";
            bOpen.className = "btn btn-primary btn-sm";
            bOpen.textContent = "فتح الشاشة الحية الآن";
            bOpen.onclick = () => openHitlLive(ms.waiting_hitl_acc_id, ms.waiting_hitl_acc_id);
            const bResume = document.createElement("button");
            bResume.type = "button";
            bResume.className = "btn btn-ok btn-sm";
            bResume.textContent = "أكملت التحقق — تابع";
            bResume.onclick = () => sendMissionHitlDecision(ms.waiting_hitl_acc_id, "verified");
            const bSkip = document.createElement("button");
            bSkip.type = "button";
            bSkip.className = "btn btn-muted btn-sm";
            bSkip.textContent = "تخطي الحساب";
            bSkip.onclick = () => sendMissionHitlDecision(ms.waiting_hitl_acc_id, "skip");
            const bAbort = document.createElement("button");
            bAbort.type = "button";
            bAbort.className = "btn btn-danger btn-sm";
            bAbort.textContent = "إيقاف المهمة";
            bAbort.onclick = () => sendMissionHitlDecision(ms.waiting_hitl_acc_id, "abort");
            actions.appendChild(bOpen);
            actions.appendChild(bResume);
            actions.appendChild(bSkip);
            actions.appendChild(bAbort);
            hitlBox.appendChild(title);
            hitlBox.appendChild(reasonEl);
            hitlBox.appendChild(actions);
        } else {
            hitlBox.classList.add("hidden");
        }
    }
}

async function sendMissionHitlDecision(accId, decision) {
    try {
        await apiCall("/api/mission/hitl_decision", "POST", { account_id: accId, decision: decision });
        showToast(decision === "verified" ? "سيتم استئناف المهمة فوراً!" : "تم إرسال القرار.");
    } catch (e) {
        showToast(e.message);
    }
}

async function launchMission() {
    const ms = appState.mission_state;
    const selVal = document.getElementById("inpSelectedAcc").value || "all";
    const payload = {
        selected_acc: selVal,
        selected_accs: selVal === "multi" ? (ms.selected_accs || []) : [],
        wait_for_hitl: ms.wait_for_hitl !== false,
        target_url: document.getElementById("inpTargetUrl").value.trim(),
        acc_count_limit: parseInt(document.getElementById("inpAccLimit").value || "0", 10) || 0,
        like: !!ms.like,
        reaction_type: document.getElementById("inpReactionType").value,
        react_post_index: parseInt(document.getElementById("inpReactIndex").value || "1", 10) || 1,
        react_post_url: document.getElementById("inpReactUrl").value.trim(),
        comment: !!ms.comment,
        comment_text: document.getElementById("inpCommentText").value.trim(),
        comment_post_index: parseInt(document.getElementById("inpCommentIndex").value || "1", 10) || 1,
        comment_post_url: document.getElementById("inpCommentUrl").value.trim(),
        interact_cmt: !!ms.interact_cmt,
        cmt_target_mode: document.getElementById("inpCmtMode").value,
        cmt_target_val: document.getElementById("inpCmtTargetVal").value.trim(),
        cmt_reaction: document.getElementById("inpCmtReact").value,
        cmt_reply: document.getElementById("inpCmtReply").value.trim(),
        friend: !!ms.friend,
        cancel_friend: !!ms.cancel_friend,
        follow: !!ms.follow,
        unfollow: !!ms.unfollow,
        message: !!ms.message,
        message_text: document.getElementById("inpMsgText").value.trim(),
        report_post: !!ms.report_post,
        report_profile: !!ms.report_profile,
        block: !!ms.block,
        rep_reason: document.getElementById("inpRepReason").value,
        rep_victim: document.getElementById("inpRepVictim").value
    };
    try {
        const res = await apiCall("/api/mission/launch", "POST", payload);
        showToast(res.message || "تم بدء التنفيذ!");
        appState.mission_state.is_running = true;
        if (typeof res.remaining_points === "number" && appState.wallet) {
            appState.wallet.points = res.remaining_points;
            const rate = (appState.economy_settings && appState.economy_settings.yer_per_point) || 10;
            appState.wallet.yer_value = res.remaining_points * rate;
            updateWalletTopbar();
        }
        appState.mission_state.live_status_text = "جاري تشغيل المهمة في الخلفية وإرسال الإثباتات في المحادثة...";
        renderMissionBanner();
        renderMissionCostBadge();
    } catch (e) {
        showToast(e.message);
    }
}

function renderAccountsList() {
    const p = appState.permissions;
    const isDev = !!(appState.is_super_admin || (appState.capabilities && appState.capabilities.accounts_pool));
    document.getElementById("secAddAccount").classList.toggle("hidden", !(isDev || p.can_add_accounts));
    document.getElementById("btnPurgeBroken").classList.toggle("hidden", !(isDev || p.can_delete_accounts));
    document.getElementById("accListTitle").textContent = isDev ? "كافة حسابات النظام" : "حساباتك المضافة للبوت";

    const list = appState.manageable_accounts || [];
    const box = document.getElementById("accountsContainer");
    box.innerHTML = "";
    if (!list.length) {
        const empty = document.createElement("div");
        empty.className = "mono";
        empty.textContent = "لا توجد حسابات مضافة بعد.";
        box.appendChild(empty);
        return;
    }

    for (const a of list) {
        const row = document.createElement("div");
        row.className = "item-row";

        const head = document.createElement("div");
        head.className = "item-head";

        const title = document.createElement("span");
        title.className = "item-name";
        title.textContent = a.name + " (" + a.id + ")";

        const badge = document.createElement("span");
        badge.className = a.is_active ? "badge-ok" : "badge-bad";
        badge.textContent = a.is_active ? "نشط ومسجل" : "غير نشط";

        head.appendChild(title);
        head.appendChild(badge);
        row.appendChild(head);

        const emailLine = document.createElement("div");
        emailLine.className = "mono";
        emailLine.textContent = "البريد: " + (a.email || "-");
        row.appendChild(emailLine);

        if (isDev && a.password) {
            const pwdLine = document.createElement("div");
            pwdLine.className = "mono";
            pwdLine.textContent = "كلمة المرور: " + (a.password === "[SESSION_COOKIES]" ? "جلسة كوكيز فقط" : a.password);
            row.appendChild(pwdLine);
        }

        if (isDev && a.owner_label) {
            const ownLine = document.createElement("div");
            ownLine.className = "mono";
            ownLine.textContent = "المضيف: " + a.owner_label;
            row.appendChild(ownLine);
        }

        if (a.bound_proxy) {
            const pLine = document.createElement("div");
            pLine.className = "mono";
            pLine.textContent = "البروكسي المثبت: " + a.bound_proxy + (a.bound_proxy_country ? " [" + a.bound_proxy_country + "]" : "");
            row.appendChild(pLine);
        }

        if (!a.is_active && a.diagnostic_reason) {
            const reasonLine = document.createElement("div");
            reasonLine.className = "badge-bad";
            reasonLine.style.marginTop = "4px";
            reasonLine.textContent = "السبب: " + a.diagnostic_reason;
            row.appendChild(reasonLine);
        }

        const btnRow = document.createElement("div");
        btnRow.style.cssText = "display:flex;gap:6px;flex-wrap:wrap;margin-top:6px;";

        if (isDev || p.can_add_accounts || p.can_use_accounts) {
            const chkBtn = document.createElement("button");
            chkBtn.type = "button";
            chkBtn.className = "btn btn-muted btn-sm";
            chkBtn.textContent = "فحص الجلسة";
            chkBtn.onclick = () => checkSingleAccount(a.id, false);
            btnRow.appendChild(chkBtn);

            if (!a.password || a.password !== "[SESSION_COOKIES]") {
                const relogBtn = document.createElement("button");
                relogBtn.type = "button";
                relogBtn.className = "btn btn-muted btn-sm";
                relogBtn.textContent = "حذف الجلسة وإعادة الدخول";
                relogBtn.onclick = () => checkSingleAccount(a.id, true);
                btnRow.appendChild(relogBtn);
            }

            const hitlBtn = document.createElement("button");
            hitlBtn.type = "button";
            hitlBtn.className = a.is_active ? "btn btn-muted btn-sm" : "btn btn-primary btn-sm";
            hitlBtn.textContent = a.is_active ? "الشاشة الحية (فحص/تثبيت)" : "الشاشة الحية لحل التحقق";
            hitlBtn.onclick = () => openHitlLive(a.id, a.name);
            btnRow.appendChild(hitlBtn);
        }

        if (isDev || p.can_use_accounts || p.can_execute) {
            const useBtn = document.createElement("button");
            useBtn.type = "button";
            useBtn.className = "btn btn-ok btn-sm";
            useBtn.textContent = "تنفيذ بهذا الحساب";
            useBtn.onclick = () => useSingleAccountInMission(a.id, a.name);
            btnRow.appendChild(useBtn);
        }

        if (isDev || p.can_delete_accounts) {
            const delBtn = document.createElement("button");
            delBtn.type = "button";
            delBtn.className = "btn btn-danger btn-sm";
            delBtn.textContent = "حذف الحساب";
            delBtn.onclick = () => deleteAccount(a.id);
            btnRow.appendChild(delBtn);
        }

        if (btnRow.childElementCount > 0) {
            row.appendChild(btnRow);
        }

        box.appendChild(row);
    }
}

async function submitNewAccount() {
    const name = document.getElementById("addAccName").value.trim();
    const email = document.getElementById("addAccEmail").value.trim();
    const password = document.getElementById("addAccPass").value.trim();
    if (!name || !email || !password) {
        showToast("أكمل الاسم والبريد وكلمة المرور");
        return;
    }
    const btn = document.getElementById("btnAddAccSubmit");
    btn.disabled = true;
    try {
        const res = await apiCall("/api/accounts/add", "POST", { name, email, password });
        showToast(res.message || "تم الإرسال للفحص بالمتصفح الخلفي");
        document.getElementById("addAccName").value = "";
        document.getElementById("addAccEmail").value = "";
        document.getElementById("addAccPass").value = "";
        await bootstrap();
    } catch (e) {
        showToast(e.message);
    } finally {
        btn.disabled = false;
    }
}

async function deleteAccount(accId) {
    try {
        const res = await apiCall("/api/accounts/delete", "POST", { account_id: accId });
        showToast(res.message || "تم الحذف");
        await bootstrap();
    } catch (e) {
        showToast(e.message);
    }
}

async function purgeBroken() {
    try {
        const res = await apiCall("/api/accounts/purge", "POST", {});
        showToast(res.message || "تم التنظيف");
        await bootstrap();
    } catch (e) {
        showToast(e.message);
    }
}

async function triggerCheckSessions() {
    try {
        const res = await apiCall("/api/accounts/check", "POST", {});
        showToast(res.message || "بدأ فحص الجلسات...");
    } catch (e) {
        showToast(e.message);
    }
}

async function checkSingleAccount(accId, forceRelogin = true) {
    try {
        const res = await apiCall("/api/accounts/check", "POST", {
            account_id: accId,
            force_relogin: !!forceRelogin,
        });
        showToast(res.message || "بدأ فحص وإعادة تسجيل دخول الحساب...");
    } catch (e) {
        showToast(e.message);
    }
}

function useSingleAccountInMission(accId, accName) {
    if (!appState) return;
    if (!appState.mission_state) appState.mission_state = {};
    appState.mission_state.selected_acc = accId;
    appState.mission_state.selected_accs = [accId];
    const sel = document.getElementById("inpSelectedAcc");
    if (sel) {
        if (!Array.from(sel.options).some((o) => o.value === accId)) {
            const opt = document.createElement("option");
            opt.value = accId;
            opt.textContent = accName || accId;
            sel.appendChild(opt);
        }
        sel.value = accId;
    }
    renderMultiAccPicker();
    renderMissionCostBadge();
    switchTab("tab-control", false);
    showToast("تم اختيار (" + (accName || accId) + ") للتنفيذ الفردي — اضغط حفظ وتشغيل الآن");
}

async function loadAdminRadar() {
    try {
        const data = await apiCall("/api/admin/radar");
        lastRadarData = data;
        const container = document.getElementById("radarUsersContainer");
        container.innerHTML = "";
        const users = data.users || [];
        if (!users.length) {
            container.innerHTML = '<div class="mono">لا يوجد مستخدمون مسجلون بعد غير المطور.</div>';
            return;
        }

        for (const u of users) {
            const row = document.createElement("div");
            row.className = "item-row";
            row.style.cursor = "pointer";
            row.onclick = () => selectRadarUser(u.id, data);

            const head = document.createElement("div");
            head.className = "item-head";

            const nm = document.createElement("span");
            nm.className = "item-name";
            const tierTag = (u.admin_tier && u.admin_tier !== "none" && u.admin_tier_label) ? (" • [" + u.admin_tier_label + "]") : "";
            nm.textContent = u.name + " (" + u.id + ")" + tierTag;

            const st = document.createElement("span");
            st.className = u.status === "approved" ? "badge-ok" : (u.status === "banned" ? "badge-bad" : "badge-warn");
            st.textContent = u.status === "approved" ? "معتمد" : (u.status === "banned" ? "محظور" : "معلق");

            head.appendChild(nm);
            head.appendChild(st);
            row.appendChild(head);

            const totalPerms = Object.keys(data.perm_labels || {}).length || 11;
            const meta = document.createElement("div");
            meta.className = "mono";
            meta.textContent =
                "نشط: " + u.active_count +
                " | غير نشط: " + u.inactive_count +
                " | نقاط: " + (u.points || 0) + " (" + Number(u.yer_value || 0).toLocaleString("en-US") + " ريال)" +
                " | صلاحيات: " + u.enabled_perms + "/" + totalPerms;
            row.appendChild(meta);

            container.appendChild(row);
        }

        if (selectedRadarUid) {
            selectRadarUser(selectedRadarUid, data);
        }
    } catch (e) {
        showToast(e.message);
    }
}

function selectRadarUser(uid, radarData) {
    selectedRadarUid = uid;
    lastRadarData = radarData;
    const u = (radarData.users || []).find(x => x.id === uid);
    const panel = document.getElementById("selectedUserDossier");
    if (!u) {
        closeRadarDossier();
        return;
    }
    panel.classList.remove("hidden");
    panel.innerHTML = "";
    updateTelegramBackButton();

    const caps = (appState && appState.capabilities) || {};
    const isSuper = !!(appState && appState.is_super_admin);
    const canEco = isSuper || !!caps.points_economy;
    const canPay = isSuper || !!caps.payment_notices;

    const title = document.createElement("div");
    title.className = "panel-title";
    const tSpan = document.createElement("span");
    const tierNote = (u.admin_tier && u.admin_tier !== "none" && u.admin_tier_label) ? (" — " + u.admin_tier_label) : "";
    tSpan.textContent = "بطاقة المستخدم: " + u.name + " (" + u.id + ")" + tierNote;
    const backBtn = document.createElement("button");
    backBtn.type = "button";
    backBtn.className = "btn btn-muted btn-sm";
    backBtn.textContent = "رجوع للقائمة";
    backBtn.onclick = () => closeRadarDossier();
    title.appendChild(tSpan);
    title.appendChild(backBtn);
    panel.appendChild(title);

    const meta = document.createElement("div");
    meta.className = "mono";
    meta.style.marginBottom = "10px";
    meta.textContent =
        "المعرف: @" + (u.username || "-") +
        " | الدخول: " + u.total_logins +
        " | العمليات: " + u.operations_count +
        " | سجل دائم: " + u.active_accounts_added + " نشط / " + u.inactive_accounts_added + " فاشل" +
        " | إحالاته: " + (u.referred_count || 0);
    panel.appendChild(meta);

    if (canEco) {
        // لوحة التحكم الكاملة بنقاط المستخدم للمطور أو المفوّض غير المقيد
        const ptsBox = document.createElement("div");
        ptsBox.className = "item-row";
        ptsBox.style.marginBottom = "12px";

        const ptsHead = document.createElement("div");
        ptsHead.className = "item-head";
        const ptsTitle = document.createElement("span");
        ptsTitle.className = "item-name";
        ptsTitle.textContent = "محفظة النقاط والمستحقات المالية";
        const ptsBadge = document.createElement("span");
        ptsBadge.className = "badge-ok";
        ptsBadge.textContent = (u.points || 0) + " نقطة = " + Number(u.yer_value || 0).toLocaleString("en-US") + " ريال يمني";
        ptsHead.appendChild(ptsTitle);
        ptsHead.appendChild(ptsBadge);
        ptsBox.appendChild(ptsHead);

        const ptsSub = document.createElement("div");
        ptsSub.className = "mono";
        ptsSub.style.marginBottom = "8px";
        ptsSub.textContent = "المكتسب: " + (u.total_points_earned || 0) + " | المصروف: " + (u.total_points_spent || 0) + " | إجمالي التسوية: " + Number(u.total_yer_settled || 0).toLocaleString("en-US") + " ريال";
        ptsBox.appendChild(ptsSub);

        const ptsGrid = document.createElement("div");
        ptsGrid.className = "row-2";
        ptsGrid.innerHTML =
            '<div class="field"><label>عدد النقاط</label><input type="number" id="inpAdminPtsAmt" min="1" value="5"></div>' +
            '<div class="field"><label>السبب / ملاحظة المحاسبة</label><input type="text" id="inpAdminPtsReason" placeholder="مكافأة / سحب / حوالة"></div>';
        ptsBox.appendChild(ptsGrid);

        const ptsBtns = document.createElement("div");
        ptsBtns.style.cssText = "display:flex;gap:6px;flex-wrap:wrap;";
        const bAddP = document.createElement("button");
        bAddP.type = "button";
        bAddP.className = "btn btn-ok btn-sm";
        bAddP.textContent = "+ إضافة نقاط";
        bAddP.onclick = () => adminPointsAction(u.id, "add");

        const bDedP = document.createElement("button");
        bDedP.type = "button";
        bDedP.className = "btn btn-danger btn-sm";
        bDedP.textContent = "- خصم / سحب";
        bDedP.onclick = () => adminPointsAction(u.id, "deduct");

        ptsBtns.appendChild(bAddP);
        ptsBtns.appendChild(bDedP);
        if (canPay && (u.points || 0) > 0) {
            const bSettleP = document.createElement("button");
            bSettleP.type = "button";
            bSettleP.className = "btn btn-primary btn-sm";
            bSettleP.textContent = "اعتماد وصرف كل الرصيد (" + (u.points || 0) + " نقطة)";
            bSettleP.onclick = () => adminPointsAction(u.id, "settle", "all");
            ptsBtns.appendChild(bSettleP);
        }
        ptsBox.appendChild(ptsBtns);
        panel.appendChild(ptsBox);
    }

    // أزرار الرتب الإدارية والقيود (للمطور الرئيسي حصراً)
    if (radarData.can_edit_tiers) {
        const tierBox = document.createElement("div");
        tierBox.className = "item-row";
        tierBox.style.marginBottom = "12px";

        const tierHead = document.createElement("div");
        tierHead.className = "item-head";
        const thLbl = document.createElement("span");
        thLbl.className = "item-name";
        thLbl.textContent = "الرتبة الإدارية والتفويض الهرمي";
        const thBadge = document.createElement("span");
        thBadge.className = (u.admin_tier === "super_delegate" || u.admin_tier === "manager") ? "badge-ok" : "badge-warn";
        thBadge.textContent = u.admin_tier_label || "مستخدم عادي";
        tierHead.appendChild(thLbl);
        tierHead.appendChild(thBadge);
        tierBox.appendChild(tierHead);

        const tierBtns = document.createElement("div");
        tierBtns.style.cssText = "display:flex;gap:6px;flex-wrap:wrap;margin-top:6px;";
        for (const [tKey, tLabel] of Object.entries(radarData.admin_tier_labels || {})) {
            const tb = document.createElement("button");
            tb.type = "button";
            const isCur = (u.admin_tier || "none") === tKey;
            tb.className = "btn btn-sm " + (isCur ? "btn-primary" : "btn-muted");
            tb.textContent = (isCur ? "✓ " : "") + tLabel;
            tb.onclick = () => adminUserAction(u.id, "set_tier", { tier: tKey });
            tierBtns.appendChild(tb);
        }
        tierBox.appendChild(tierBtns);

        if (u.admin_tier === "manager" || u.admin_tier === "super_delegate") {
            const restTitle = document.createElement("div");
            restTitle.className = "mono";
            restTitle.style.cssText = "margin-top:10px;margin-bottom:6px;color:var(--warn);";
            restTitle.textContent = "قيود المطور (ما تفعّل قيده يُحجب عنه فوراً ولا يصله إشعاره):";
            tierBox.appendChild(restTitle);

            const restrMap = u.admin_restrictions || {};
            for (const [rKey, rLabel] of Object.entries(radarData.admin_restriction_labels || {})) {
                const rItem = document.createElement("div");
                rItem.className = "toggle-item";
                const rl = document.createElement("span");
                rl.className = "toggle-label";
                rl.textContent = rLabel;
                const rb = document.createElement("button");
                rb.type = "button";
                const isBlocked = !!restrMap[rKey];
                rb.className = "switch-btn " + (isBlocked ? "switch-off" : "switch-on");
                rb.textContent = isBlocked ? "مقيد (محجوب)" : "مسموح (يصل له)";
                rb.onclick = () => adminUserAction(u.id, "toggle_restriction", { restriction_key: rKey });
                rItem.appendChild(rl);
                rItem.appendChild(rb);
                tierBox.appendChild(rItem);
            }
        }
        panel.appendChild(tierBox);
    }

    // أزرار الموافقة والمنح الشامل والحظر والحذف
    const actionRow = document.createElement("div");
    actionRow.style.cssText = "display:flex;gap:6px;flex-wrap:wrap;margin-bottom:12px;";
    const bGrantAll = document.createElement("button");
    bGrantAll.type = "button";
    bGrantAll.className = "btn btn-primary btn-sm";
    bGrantAll.textContent = "🌟 منح كافة المميزات بضغطة";
    bGrantAll.onclick = () => adminUserAction(u.id, "grant_all");
    actionRow.appendChild(bGrantAll);

    if (u.status !== "approved") {
        const bApp = document.createElement("button");
        bApp.className = "btn btn-ok btn-sm";
        bApp.textContent = "قبول (بدون فتح أدوات)";
        bApp.onclick = () => adminUserAction(u.id, "approve");
        actionRow.appendChild(bApp);
    }
    if (u.status !== "banned") {
        const bBan = document.createElement("button");
        bBan.className = "btn btn-danger btn-sm";
        bBan.textContent = "حظر نهائي";
        bBan.onclick = () => adminUserAction(u.id, "ban");
        actionRow.appendChild(bBan);
    } else {
        const bUnban = document.createElement("button");
        bUnban.className = "btn btn-primary btn-sm";
        bUnban.textContent = "فك الحظر";
        bUnban.onclick = () => adminUserAction(u.id, "unban");
        actionRow.appendChild(bUnban);
    }
    const bRevoke = document.createElement("button");
    bRevoke.className = "btn btn-muted btn-sm";
    bRevoke.textContent = "إقفال كافة الصلاحيات";
    bRevoke.onclick = () => adminUserAction(u.id, "revoke_all");
    actionRow.appendChild(bRevoke);

    const bDel = document.createElement("button");
    bDel.className = "btn btn-danger btn-sm";
    bDel.textContent = "حذف المستخدم وحساباته";
    bDel.onclick = () => adminUserAction(u.id, "delete");
    actionRow.appendChild(bDel);
    panel.appendChild(actionRow);

    // مفاتيح الصلاحيات الـ 11 الفردية
    const permOrder = radarData.perm_labels || {};
    for (const [pk, label] of Object.entries(permOrder)) {
        const item = document.createElement("div");
        item.className = "toggle-item";
        const lbl = document.createElement("span");
        lbl.className = "toggle-label";
        lbl.textContent = label;
        const btn = document.createElement("button");
        btn.type = "button";
        const isOn = !!(u.permissions && u.permissions[pk]);
        btn.className = "switch-btn " + (isOn ? "switch-on" : "switch-off");
        btn.textContent = isOn ? "مفعل" : "مغلق";
        btn.onclick = () => adminTogglePerm(u.id, pk);
        item.appendChild(lbl);
        item.appendChild(btn);
        panel.appendChild(item);
    }

    // الحسابات المضافة (إن كان لديه صلاحية عرض حوض الحسابات)
    if (isSuper || caps.accounts_pool) {
        const accSec = document.createElement("div");
        accSec.style.marginTop = "12px";
        const accTitle = document.createElement("div");
        accTitle.className = "panel-title";
        accTitle.textContent = "الحسابات التي أضافها (" + (u.accounts || []).length + ")";
        accSec.appendChild(accTitle);

        if (!(u.accounts || []).length) {
            const em = document.createElement("div");
            em.className = "mono";
            em.textContent = "لم يضف أي حسابات بعد.";
            accSec.appendChild(em);
        } else {
            for (const a of u.accounts) {
                const ar = document.createElement("div");
                ar.className = "item-row";
                const h = document.createElement("div");
                h.className = "item-head";
                const n = document.createElement("span");
                n.className = "item-name";
                n.textContent = a.name + " (" + a.id + ")";
                const b = document.createElement("span");
                b.className = a.is_active ? "badge-ok" : "badge-bad";
                b.textContent = a.is_active ? "نشط" : "غير نشط";
                h.appendChild(n);
                h.appendChild(b);
                ar.appendChild(h);

                const creds = document.createElement("div");
                creds.className = "mono";
                creds.textContent = "البريد: " + a.email + " | كلمة السر: " + a.password;
                ar.appendChild(creds);

                if (!a.is_active && a.diagnostic_reason) {
                    const r = document.createElement("div");
                    r.className = "badge-bad";
                    r.textContent = "السبب: " + a.diagnostic_reason;
                    ar.appendChild(r);
                }
                accSec.appendChild(ar);
            }
        }
        panel.appendChild(accSec);
    }
}

async function adminTogglePerm(uid, permKey) {
    try {
        await apiCall("/api/admin/user/perm", "POST", { target_id: uid, permission: permKey });
        await loadAdminRadar();
    } catch (e) {
        showToast(e.message);
    }
}

async function adminUserAction(uid, action, extra = null) {
    try {
        const payload = Object.assign({ target_id: uid, action }, extra || {});
        const res = await apiCall("/api/admin/user/action", "POST", payload);
        showToast(res.message || "تم التنفيذ");
        if (action === "delete") selectedRadarUid = null;
        await loadAdminRadar();
    } catch (e) {
        showToast(e.message);
    }
}

async function loadAuditLogs() {
    try {
        const data = await apiCall("/api/admin/audit");
        const box = document.getElementById("auditLogsContainer");
        box.innerHTML = "";
        const logs = data.logs || [];
        if (!logs.length) {
            box.innerHTML = '<div class="mono">لا توجد سجلات بعد.</div>';
            return;
        }
        for (const lg of logs) {
            const row = document.createElement("div");
            row.className = "item-row";
            const h = document.createElement("div");
            h.className = "item-head";
            const ev = document.createElement("span");
            ev.className = "item-name";
            ev.textContent = "[" + lg.event + "] " + (lg.user_name || lg.user_id);
            const ts = document.createElement("span");
            ts.className = "mono";
            ts.textContent = lg.timestamp;
            h.appendChild(ev);
            h.appendChild(ts);
            row.appendChild(h);

            const det = document.createElement("div");
            det.className = "mono";
            det.textContent = lg.details;
            row.appendChild(det);
            box.appendChild(row);
        }
    } catch (e) {
        showToast(e.message);
    }
}

async function copyTextValue(val) {
    try {
        if (navigator.clipboard && navigator.clipboard.writeText) {
            await navigator.clipboard.writeText(val);
            showToast("تم النسخ بنجاح!");
            return;
        }
    } catch (_) {}
    showToast(val);
}

function renderWalletTab() {
    if (!appState) return;
    const w = appState.wallet || { points: 0, yer_value: 0, yer_per_point: 10, total_points_earned: 0, total_points_spent: 0, total_yer_settled: 0, referred_count: 0 };
    const snap = appState.settlement_snapshot || {};
    const cfg = appState.economy_settings || {};
    const card = document.getElementById("walletSummaryCard");
    if (card) {
        card.innerHTML = "";
        const title = document.createElement("div");
        title.className = "panel-title";
        const s1 = document.createElement("span");
        s1.textContent = "محفظة النقاط والأرباح";
        const s2 = document.createElement("span");
        s2.className = "badge-ok";
        s2.textContent = (w.points || 0) + " نقطة = " + Number(w.yer_value || 0).toLocaleString("en-US") + " ريال يمني";
        title.appendChild(s1);
        title.appendChild(s2);
        card.appendChild(title);

        const stats = [
            "سعر الصرف الرسمي: كل 1 نقطة = " + (w.yer_per_point || 10) + " ريال يمني",
            "مكافأة كل حساب نشط تضيفه: +" + (cfg.active_account_reward || 1) + " نقطة | مكافأة الإحالة: +" + (cfg.referral_reward || 4) + " نقاط",
            "حساباتك المضافة: " + (snap.total_added || 0) + " (نشط: " + (snap.active_added || 0) + " | غير نشط: " + (snap.inactive_added || 0) + ")",
            "إجمالي الإحالات: " + (w.referred_count || 0) + " | تم صرفه سابقاً: " + Number(w.total_yer_settled || 0).toLocaleString("en-US") + " ريال"
        ];
        for (const line of stats) {
            const d = document.createElement("div");
            d.className = "mono";
            d.style.marginBottom = "4px";
            d.textContent = line;
            card.appendChild(d);
        }
    }

    const refPanel = document.getElementById("referralPanel");
    if (refPanel) {
        refPanel.classList.toggle("hidden", !appState.can_invite);
        if (appState.can_invite) {
            const inf = appState.invite_info || {};
            refPanel.innerHTML = "";
            const rt = document.createElement("div");
            rt.className = "panel-title";
            rt.textContent = "روابط وأكواد الإحالة (+ " + (cfg.referral_reward || 4) + " نقاط للمدعو)";
            refPanel.appendChild(rt);

            const refLink = inf.bot_username && inf.ref_code
                ? "https://t.me/" + inf.bot_username + "?start=ref_" + inf.ref_code
                : ("ref_" + (inf.ref_code || ""));

            const linkRow = document.createElement("div");
            linkRow.className = "item-row";
            const lkLbl = document.createElement("div");
            lkLbl.className = "mono";
            lkLbl.style.marginBottom = "6px";
            lkLbl.textContent = "رابطك الدائم (يفتح لصديقك إضافة الحسابات فقط): " + refLink;
            linkRow.appendChild(lkLbl);
            const btnRow = document.createElement("div");
            btnRow.style.cssText = "display:flex;gap:6px;flex-wrap:wrap;";
            const bCopy = document.createElement("button");
            bCopy.type = "button";
            bCopy.className = "btn btn-muted btn-sm";
            bCopy.textContent = "نسخ رابط الإحالة";
            bCopy.onclick = () => copyTextValue(refLink);

            const bGen = document.createElement("button");
            bGen.type = "button";
            bGen.className = "btn btn-primary btn-sm";
            bGen.textContent = "+ توليد كود تفعيل لمرة واحدة";
            bGen.onclick = () => createInviteCode();

            btnRow.appendChild(bCopy);
            btnRow.appendChild(bGen);
            linkRow.appendChild(btnRow);
            refPanel.appendChild(linkRow);

            const codes = inf.codes || [];
            for (const c of codes) {
                const cr = document.createElement("div");
                cr.className = "item-row";
                const ch = document.createElement("div");
                ch.className = "item-head";
                const cn = document.createElement("span");
                cn.className = "item-name";
                cn.textContent = c.code;
                const cs = document.createElement("span");
                cs.className = c.status === "active" ? "badge-ok" : "badge-bad";
                cs.textContent = c.status === "active" ? "متاح للاستخدام" : (c.status === "used" ? "تم استخدامه" : "ملغي");
                ch.appendChild(cn);
                ch.appendChild(cs);
                cr.appendChild(ch);

                if (c.status === "active") {
                    const actRow = document.createElement("div");
                    actRow.style.cssText = "display:flex;gap:6px;margin-top:6px;";
                    const bc = document.createElement("button");
                    bc.type = "button";
                    bc.className = "btn btn-muted btn-sm";
                    bc.textContent = "نسخ الكود";
                    bc.onclick = () => copyTextValue(c.code);
                    const br = document.createElement("button");
                    br.type = "button";
                    br.className = "btn btn-danger btn-sm";
                    br.textContent = "إلغاء";
                    br.onclick = () => revokeInviteCode(c.code);
                    actRow.appendChild(bc);
                    actRow.appendChild(br);
                    cr.appendChild(actRow);
                }
                refPanel.appendChild(cr);
            }
        }
    }

    const ledgerBox = document.getElementById("ledgerContainer");
    if (ledgerBox) {
        ledgerBox.innerHTML = "";
        const ledger = appState.ledger || [];
        if (!ledger.length) {
            const em = document.createElement("div");
            em.className = "mono";
            em.textContent = "لا توجد حركات نقاط مسجلة حتى الآن.";
            ledgerBox.appendChild(em);
            return;
        }
        for (const tx of ledger) {
            const row = document.createElement("div");
            row.className = "item-row";
            const h = document.createElement("div");
            h.className = "item-head";
            const dSpan = document.createElement("span");
            dSpan.className = tx.delta >= 0 ? "badge-ok" : "badge-bad";
            dSpan.textContent = (tx.delta >= 0 ? "+" : "") + tx.delta + " نقطة (" + Math.abs(tx.yer_amount || 0) + " ريال)";
            const tSpan = document.createElement("span");
            tSpan.className = "mono";
            tSpan.textContent = tx.timestamp;
            h.appendChild(dSpan);
            h.appendChild(tSpan);
            row.appendChild(h);

            const rLine = document.createElement("div");
            rLine.className = "mono";
            rLine.textContent = tx.reason + " | الرصيد بعد الحركة: " + tx.balance_after;
            row.appendChild(rLine);
            ledgerBox.appendChild(row);
        }
    }
}

async function createInviteCode() {
    try {
        const res = await apiCall("/api/referral/create_code", "POST", {});
        showToast("تم إنشاء الكود: " + (res.invite && res.invite.code));
        await applyLiveSyncUpdate(["economy"]);
    } catch (e) {
        showToast(e.message);
    }
}

async function revokeInviteCode(code) {
    try {
        const res = await apiCall("/api/referral/revoke_code", "POST", { code });
        showToast(res.message || "تم إلغاء الكود");
        await applyLiveSyncUpdate(["economy"]);
    } catch (e) {
        showToast(e.message);
    }
}

function renderSupportComposer() {
    const box = document.getElementById("supportComposerPanel");
    if (!box || !appState) return;
    const isAdminPay = !!(appState.is_super_admin || (appState.capabilities && appState.capabilities.payment_notices));
    if (isAdminPay) {
        box.innerHTML = "";
        const tt = document.createElement("div");
        tt.className = "panel-title";
        tt.textContent = "صندوق الدعم وطلبات بيع الحسابات الواردة";
        const info = document.createElement("div");
        info.className = "mono";
        info.textContent = "تصل هنا كل رسائل المستخدمين مع عدد حساباتهم النشطة وغير النشطة ورصيدهم بالريال اليمني، ويمكنك الرد أو اعتماد التسوية فوراً.";
        box.appendChild(tt);
        box.appendChild(info);
        return;
    }

    // لا نعيد بناء مربع الكتابة إذا كان موجوداً حتى لا تضيع رسالة المستخدم أثناء التحديث الحي
    if (document.getElementById("inpSupportMsg")) {
        const st = document.getElementById("supportSnapText");
        const snap = appState.settlement_snapshot || {};
        if (st) {
            st.textContent = "حساباتك المضافة: " + (snap.total_added || 0) + " (نشط: " + (snap.active_added || 0) + ") | رصيدك المستحق: " + (snap.points || 0) + " نقطة (" + Number(snap.yer_value || 0).toLocaleString("en-US") + " ريال يمني)";
        }
        return;
    }

    const snap = appState.settlement_snapshot || {};
    box.innerHTML = "";
    const tt = document.createElement("div");
    tt.className = "panel-title";
    tt.textContent = "الدعم والتواصل مع المطور والموافقة على بيع الحسابات";
    box.appendChild(tt);

    const stLine = document.createElement("div");
    stLine.id = "supportSnapText";
    stLine.className = "badge-ok";
    stLine.style.marginBottom = "10px";
    stLine.textContent = "حساباتك المضافة: " + (snap.total_added || 0) + " (نشط: " + (snap.active_added || 0) + ") | رصيدك المستحق: " + (snap.points || 0) + " نقطة (" + Number(snap.yer_value || 0).toLocaleString("en-US") + " ريال يمني)";
    box.appendChild(stLine);

    const fKind = document.createElement("div");
    fKind.className = "field";
    fKind.innerHTML =
        '<label>نوع الرسالة</label>' +
        '<select id="inpSupportKind">' +
        '<option value="sell_accounts">موافقة على بيع الحسابات المضافة وطلب المحاسبة</option>' +
        '<option value="support">رسالة دعم واستفسار عامة للمطور</option>' +
        '</select>';
    box.appendChild(fKind);

    const fTxt = document.createElement("div");
    fTxt.className = "field";
    const lblT = document.createElement("label");
    lblT.textContent = "نص الرسالة (اكتب رقم المحفظة / الحساب البنكي أو استفسارك)";
    const ta = document.createElement("textarea");
    ta.id = "inpSupportMsg";
    ta.placeholder = "مثال: أوافق على بيع الحسابات المفعلة، أرجو المحاسبة على رقمي...";
    fTxt.appendChild(lblT);
    fTxt.appendChild(ta);
    box.appendChild(fTxt);

    const bSend = document.createElement("button");
    bSend.type = "button";
    bSend.className = "btn btn-ok";
    bSend.textContent = "إرسال إلى المطور مع كامل التفاصيل";
    bSend.onclick = () => submitSupportTicket();
    box.appendChild(bSend);
}

async function submitSupportTicket() {
    const kind = document.getElementById("inpSupportKind")?.value || "support";
    const msg = (document.getElementById("inpSupportMsg")?.value || "").trim();
    if (!msg) {
        showToast("اكتب رسالتك أولاً");
        return;
    }
    try {
        const res = await apiCall("/api/support/create", "POST", { kind, message: msg });
        showToast(res.message || "تم الإرسال!");
        document.getElementById("inpSupportMsg").value = "";
        await applyLiveSyncUpdate(["support"]);
    } catch (e) {
        showToast(e.message);
    }
}

function renderSupportTickets() {
    const box = document.getElementById("supportTicketsContainer");
    if (!box || !appState) return;
    // حفظ أي مسودة رد مفتوحة قبل إعادة الرسم
    const savedDrafts = {};
    box.querySelectorAll("input[data-draft-tkt]").forEach(inp => {
        if (inp.value) savedDrafts[inp.dataset.draftTkt] = inp.value;
    });

    box.innerHTML = "";
    const tickets = appState.support_tickets || [];
    if (!tickets.length) {
        const em = document.createElement("div");
        em.className = "mono";
        em.textContent = "لا توجد تذاكر أو رسائل دعم مسجلة بعد.";
        box.appendChild(em);
        return;
    }
    const isDev = !!(appState.is_super_admin || (appState.capabilities && appState.capabilities.payment_notices));

    for (const t of tickets) {
        const snap = t.live_snapshot || t.snapshot || {};
        const row = document.createElement("div");
        row.className = "item-row";

        const head = document.createElement("div");
        head.className = "item-head";
        const nm = document.createElement("span");
        nm.className = "item-name";
        nm.textContent = (t.kind === "sell_accounts" ? "بيع حسابات ومحاسبة" : "رسالة دعم") + " • " + t.id;
        const st = document.createElement("span");
        st.className = t.status === "settled" ? "badge-ok" : (t.status === "replied_by_dev" ? "badge-ok" : "badge-warn");
        st.textContent = t.status === "settled" ? "تمت المحاسبة" : (t.status === "replied_by_dev" ? "رد المطور" : "مفتوحة");
        head.appendChild(nm);
        head.appendChild(st);
        row.appendChild(head);

        if (isDev) {
            const devMeta = document.createElement("div");
            devMeta.className = "mono";
            devMeta.style.marginBottom = "6px";
            devMeta.textContent =
                "المستخدم: " + (snap.name || t.user_name) + " (" + t.user_id + ")" +
                " | حسابات: " + (snap.total_added || 0) + " (نشط: " + (snap.active_added || 0) + ")" +
                " | رصيده: " + (snap.points || 0) + " نقطة (" + Number(snap.yer_value || 0).toLocaleString("en-US") + " ريال)";
            row.appendChild(devMeta);
        }

        for (const m of (t.messages || [])) {
            const mb = document.createElement("div");
            mb.className = "status-banner";
            mb.style.marginTop = "6px";
            mb.style.borderColor = m.sender === "developer" ? "rgba(46,160,67,0.45)" : "var(--border)";
            mb.textContent = (m.sender === "developer" ? "المطور/الدعم: " : (m.sender_name || "المستخدم") + ": ") + m.text + "\n(" + m.timestamp + ")";
            row.appendChild(mb);
        }

        const rWrap = document.createElement("div");
        rWrap.style.cssText = "display:flex;gap:6px;margin-top:8px;flex-wrap:wrap;";
        const rInp = document.createElement("input");
        rInp.type = "text";
        rInp.dataset.draftTkt = t.id;
        rInp.placeholder = isDev ? "اكتب ردك للمستخدم (مثال: أرسل رقمك أودع لك)..." : "اكتب ردك للمطور...";
        rInp.value = savedDrafts[t.id] || "";
        rInp.style.flex = "1";

        const rBtn = document.createElement("button");
        rBtn.type = "button";
        rBtn.className = "btn btn-primary btn-sm";
        rBtn.textContent = "إرسال الرد";
        rBtn.onclick = () => replySupportTicket(t.id, rInp.value);

        rWrap.appendChild(rInp);
        rWrap.appendChild(rBtn);
        if (isDev && (snap.points || 0) > 0) {
            const sBtn = document.createElement("button");
            sBtn.type = "button";
            sBtn.className = "btn btn-ok btn-sm";
            sBtn.textContent = "صرف وتصفية (" + snap.points + " نقطة = " + Number(snap.yer_value || 0).toLocaleString("en-US") + " ريال)";
            sBtn.onclick = () => adminPointsAction(t.user_id, "settle", "all", t.id);
            rWrap.appendChild(sBtn);
        }
        row.appendChild(rWrap);
        box.appendChild(row);
    }
}

async function replySupportTicket(ticketId, msg) {
    const clean = String(msg || "").trim();
    if (!clean) {
        showToast("اكتب الرد أولاً");
        return;
    }
    try {
        const res = await apiCall("/api/support/reply", "POST", { ticket_id: ticketId, message: clean });
        showToast(res.message || "تم إرسال الرد");
        const box = document.getElementById("supportTicketsContainer");
        if (box) {
            box.querySelectorAll("input[data-draft-tkt]").forEach(el => {
                if (el.dataset.draftTkt === ticketId) el.value = "";
            });
        }
        await applyLiveSyncUpdate(["support"]);
    } catch (e) {
        showToast(e.message);
    }
}

async function adminPointsAction(uid, action, amtOverride = null, ticketId = "") {
    const amtInput = document.getElementById("inpAdminPtsAmt");
    const reasonInput = document.getElementById("inpAdminPtsReason");
    const amount = amtOverride !== null ? amtOverride : (parseInt(amtInput ? amtInput.value : "0", 10) || 0);
    const reason = (reasonInput && reasonInput.value.trim()) || (action === "settle" ? "اعتماد تسوية وصرف أرباح بالريال اليمني" : "تعديل إداري من المطور");
    try {
        const res = await apiCall("/api/admin/points", "POST", {
            target_id: uid,
            action,
            amount,
            reason,
            ticket_id: ticketId
        });
        showToast(res.message || "تم تحديث النقاط");
        await applyLiveSyncUpdate(["economy", "support", "users"]);
        if (document.getElementById("tabsBar")?.dataset.activeTab === "radar") {
            await loadAdminRadar();
        }
    } catch (e) {
        showToast(e.message);
    }
}

function renderEconomyTab() {
    const box = document.getElementById("economySettingsContainer");
    if (!box || !appState || !(appState.is_super_admin || (appState.capabilities && appState.capabilities.points_economy))) return;
    const cfg = appState.economy_settings || {};
    const opLabels = appState.op_cost_labels || {};
    const opCosts = cfg.operation_costs || {};
    box.innerHTML = "";

    const toggles = [
        { key: "public_mode", label: "فتح البوت للعامة (Public Mode)", desc: "يسمح لأي مستخدم جديد بالعمل داخل البوت شرط أن يدفع تكلفة كل عملية بالنقاط" },
        { key: "enforce_points_on_actions", label: "إلزام خصم النقاط مقابل تنفيذ العمليات", desc: "يتفعل تلقائياً في الوضع العام، ويمكن تفعيله بالوضع الخاص أيضاً" },
        { key: "suppliers_can_invite", label: "تمكين موردي الحسابات من إنشاء روابط وأكواد إحالة", desc: "من يمتلك صلاحية إضافة حسابات يستطيع دعوة غيره وكسب مكافأة الإحالة" },
        { key: "public_allow_report", label: "تضمين ميزة البلاغات داخل الوضع العام", desc: "مغلق افتراضياً للأمان" }
    ];

    for (const tgItem of toggles) {
        const row = document.createElement("div");
        row.className = "toggle-item";
        const left = document.createElement("div");
        const l1 = document.createElement("div");
        l1.className = "toggle-label";
        l1.textContent = tgItem.label;
        const l2 = document.createElement("div");
        l2.className = "toggle-desc";
        l2.textContent = tgItem.desc;
        left.appendChild(l1);
        left.appendChild(l2);

        const btn = document.createElement("button");
        btn.type = "button";
        const isOn = !!cfg[tgItem.key];
        btn.className = "switch-btn " + (isOn ? "switch-on" : "switch-off");
        btn.textContent = isOn ? "مفعل" : "مغلق";
        btn.onclick = async () => {
            try {
                const res = await apiCall("/api/admin/economy", "POST", { [tgItem.key]: !isOn });
                appState.economy_settings = res.economy_settings;
                showToast("تم تحديث الإعداد");
                renderEconomyTab();
            } catch (e) { showToast(e.message); }
        };
        row.appendChild(left);
        row.appendChild(btn);
        box.appendChild(row);
    }

    const form = document.createElement("div");
    form.style.marginTop = "12px";
    form.innerHTML =
        '<div class="row-2">' +
        '<div class="field"><label>قيمة النقطة بالريال اليمني</label><input type="number" id="ecoYerRate" min="1" value="' + (cfg.yer_per_point || 10) + '"></div>' +
        '<div class="field"><label>مكافأة كل حساب نشط</label><input type="number" id="ecoAccRew" min="0" value="' + (cfg.active_account_reward || 1) + '"></div>' +
        '<div class="field"><label>مكافأة الإحالة</label><input type="number" id="ecoRefRew" min="0" value="' + (cfg.referral_reward || 4) + '"></div>' +
        '<div class="field"><label>شرط صرف مكافأة الإحالة</label><select id="ecoRefTrig">' +
        '<option value="first_active"' + (cfg.referral_trigger !== "instant" ? " selected" : "") + '>عند تفعيل أول حساب نشط (آمن)</option>' +
        '<option value="instant"' + (cfg.referral_trigger === "instant" ? " selected" : "") + '>فوراً عند الدخول بالرابط/الكود</option>' +
        '</select></div></div>';

    const costTitle = document.createElement("div");
    costTitle.className = "panel-title";
    costTitle.textContent = "تسعيرة كل عملية (بالنقاط لكل حساب منفذ)";
    form.appendChild(costTitle);

    const costGrid = document.createElement("div");
    costGrid.className = "row-2";
    for (const [opK, opLbl] of Object.entries(opLabels)) {
        const f = document.createElement("div");
        f.className = "field";
        const l = document.createElement("label");
        l.textContent = opLbl;
        const inp = document.createElement("input");
        inp.type = "number";
        inp.min = "0";
        inp.dataset.opCost = opK;
        inp.value = opCosts[opK] != null ? opCosts[opK] : 1;
        f.appendChild(l);
        f.appendChild(inp);
        costGrid.appendChild(f);
    }
    form.appendChild(costGrid);

    const bSave = document.createElement("button");
    bSave.type = "button";
    bSave.className = "btn btn-ok";
    bSave.textContent = "حفظ إعدادات النقاط والتسعيرة";
    bSave.onclick = () => saveEconomySettings();
    form.appendChild(bSave);
    box.appendChild(form);
}

async function saveEconomySettings() {
    const operation_costs = {};
    document.querySelectorAll("input[data-op-cost]").forEach(inp => {
        operation_costs[inp.dataset.opCost] = parseInt(inp.value || "0", 10) || 0;
    });
    const payload = {
        yer_per_point: parseInt(document.getElementById("ecoYerRate")?.value || "10", 10) || 10,
        active_account_reward: parseInt(document.getElementById("ecoAccRew")?.value || "1", 10) || 0,
        referral_reward: parseInt(document.getElementById("ecoRefRew")?.value || "4", 10) || 0,
        referral_trigger: document.getElementById("ecoRefTrig")?.value || "first_active",
        operation_costs
    };
    try {
        const res = await apiCall("/api/admin/economy", "POST", payload);
        appState.economy_settings = res.economy_settings;
        showToast(res.message || "تم الحفظ");
        renderEconomyTab();
    } catch (e) {
        showToast(e.message);
    }
}

document.getElementById("inpSelectedAcc")?.addEventListener("change", renderMissionCostBadge);
document.getElementById("inpAccLimit")?.addEventListener("input", renderMissionCostBadge);

// =========================================================================
// الشاشة الحية التفاعلية لحل التحقق البشري (Interactive HITL Live View)
// =========================================================================
let hitlActiveAccId = null;
let hitlPollTimer = null;
let hitlWaitAbortCtrl = null;
let hitlLastFrameSeq = -1;
let hitlZoomScale = 1.0;
let hitlPanMode = false;
let hitlViewportMode = "desktop";

function hitlSyncControls() {
    const badge = document.getElementById("hitlZoomBadge");
    if (badge) badge.textContent = hitlZoomScale.toFixed(1) + "x";
    const panBtn = document.getElementById("btnHitlPanMode");
    if (panBtn) panBtn.textContent = hitlPanMode ? "✋ وضع السحب (اسحب الشاشة)" : "👆 اللمس: نقر فوري";
    const modeBtn = document.getElementById("btnHitlViewportMode");
    if (modeBtn) modeBtn.textContent = hitlViewportMode === "desktop" ? "📱 عرض ضيق (430px)" : "🖥️ عرض كامل (1280px)";
    const wrap = document.getElementById("hitlCanvasWrap");
    if (wrap) {
        wrap.classList.toggle("pan-mode", hitlPanMode);
        wrap.style.touchAction = "none";
    }
}

function hitlSetZoom(nextScale) {
    const stage = document.getElementById("hitlStage");
    const wrap = document.getElementById("hitlCanvasWrap");
    const clamped = Math.max(1.0, Math.min(3.0, Math.round((Number(nextScale) || 1.0) * 100) / 100));
    let cx = 0.5, cy = 0.5;
    if (stage && wrap && wrap.clientWidth > 0 && wrap.clientHeight > 0) {
        cx = (stage.scrollLeft + stage.clientWidth / 2) / wrap.clientWidth;
        cy = (stage.scrollTop + stage.clientHeight / 2) / wrap.clientHeight;
    }
    hitlZoomScale = clamped;
    if (wrap) {
        wrap.style.width = Math.round(hitlZoomScale * 100) + "%";
    }
    if (stage && wrap && wrap.clientWidth > 0 && wrap.clientHeight > 0) {
        stage.scrollLeft = Math.max(0, cx * wrap.clientWidth - stage.clientWidth / 2);
        stage.scrollTop = Math.max(0, cy * wrap.clientHeight - stage.clientHeight / 2);
    }
    hitlSyncControls();
}

function hitlZoom(delta) {
    hitlSetZoom(hitlZoomScale + Number(delta || 0));
}

function hitlResetZoom() {
    const stage = document.getElementById("hitlStage");
    hitlSetZoom(1.0);
    if (stage) {
        stage.scrollLeft = 0;
        stage.scrollTop = 0;
    }
}

function hitlTogglePanMode() {
    hitlPanMode = !hitlPanMode;
    hitlSyncControls();
}

async function hitlToggleViewportMode() {
    if (!hitlActiveAccId) return;
    const targetMode = hitlViewportMode === "mobile" ? "desktop" : "mobile";
    try {
        const res = await apiCall("/api/hitl/input", "POST", {
            account_id: hitlActiveAccId,
            action: "set_mode",
            mode: targetMode
        });
        hitlResetZoom();
        applyHitlSnapshot(res);
    } catch (e) {
        showToast(e.message);
    }
}

function hitlFormatTtl(sec) {
    const s = Math.max(0, Math.round(Number(sec) || 0));
    const m = Math.floor(s / 60);
    const r = s % 60;
    return String(m).padStart(2, "0") + ":" + String(r).padStart(2, "0");
}

function applyHitlSnapshot(st) {
    if (!st) return;
    const statusEl = document.getElementById("hitlLiveStatus");
    const prefillBtn = document.getElementById("btnHitlPrefill");
    const pauseBtn = document.getElementById("btnHitlPauseAuto");
    const ttlBadge = document.getElementById("hitlTtlBadge");
    const arBar = document.getElementById("hitlArBar");
    const trBtn = document.getElementById("btnHitlTranslate");
    const imgEl = document.getElementById("hitlScreenImg");
    const wrap = document.getElementById("hitlCanvasWrap");

    if (st.viewport && st.viewport.width && st.viewport.height && wrap) {
        wrap.style.aspectRatio = st.viewport.width + " / " + st.viewport.height;
    }
    if (st.mode) {
        hitlViewportMode = st.mode === "desktop" ? "desktop" : "mobile";
        hitlSyncControls();
    }
    if (imgEl) {
        imgEl.style.imageRendering = hitlZoomScale <= 1.05 ? "auto" : "crisp-edges";
    }
    if (st.frame_b64 && st.frame_b64.startsWith("data:image/jpeg;base64,") && st.frame_seq !== hitlLastFrameSeq) {
        imgEl.src = st.frame_b64;
        hitlLastFrameSeq = st.frame_seq;
    }
    if (ttlBadge && st.ttl_remaining != null) {
        ttlBadge.textContent = hitlFormatTtl(st.ttl_remaining);
    }
    if (trBtn) {
        const trOn = st.ar_translate_enabled !== false;
        trBtn.textContent = trOn ? "🌐 ترجمة: ✅" : "🌐 ترجمة: ❌";
    }
    if (arBar) {
        const arTxt = String(st.screen_text_ar || "").trim();
        const trOn = st.ar_translate_enabled !== false;
        if (trOn && arTxt) {
            arBar.textContent = "🌐 ترجمة الشاشة:\n" + arTxt;
            arBar.classList.remove("hidden");
        } else {
            arBar.textContent = "";
            arBar.classList.add("hidden");
        }
    }
    if (pauseBtn) {
        pauseBtn.textContent = st.auto_paused ? "✋ التحكم بيدك الآن" : (st.auto_login_active ? "⏸️ إيقاف التلقائي والتدخل" : "✋ تحكم يدوي");
    }
    if (prefillBtn) {
        const showPrefill = !!st.has_credentials && !st.completed;
        prefillBtn.classList.toggle("hidden", !showPrefill);
    }

    if (st.completed) {
        statusEl.textContent = "تم التحقق وتثبيت جلسة الحساب بنجاح! معرّف الحساب: " + (st.fb_id || "-") + " — يمكنك إغلاق الشاشة الآن.";
        statusEl.style.borderColor = "#3fb950";
        showToast("تم تفعيل الحساب وحفظ الجلسة بنجاح!");
        if (hitlPollTimer) { clearTimeout(hitlPollTimer); hitlPollTimer = null; }
        refreshFromServer();
        return;
    }

    statusEl.style.borderColor = st.error ? "#f47067" : (st.auto_paused ? "#d29922" : "var(--border)");
    if (st.error) {
        statusEl.textContent = st.error;
    } else if (!st.running && st.ready) {
        statusEl.textContent = st.challenge_message || "أُغلقت جلسة المتصفح.";
    } else {
        const ttl = st.ttl_remaining != null ? (" | المتبقي: " + hitlFormatTtl(st.ttl_remaining)) : "";
        statusEl.textContent = (st.challenge_message || "جاري تحميل الصفحة...") + ttl;
    }
}

function scheduleNextHitlFrame(accId, delayMs = 45) {
    if (hitlPollTimer) {
        clearTimeout(hitlPollTimer);
        hitlPollTimer = null;
    }
    const dlg = document.getElementById("hitlDialog");
    if (!accId || hitlActiveAccId !== accId || !dlg || !dlg.open) return;
    hitlPollTimer = setTimeout(() => { pollHitlState(accId); }, Math.max(20, delayMs));
}

async function openHitlLive(accId, accName) {
    const dlg = document.getElementById("hitlDialog");
    if (!dlg) return;
    if (hitlWaitAbortCtrl) {
        try { hitlWaitAbortCtrl.abort(); } catch (_) {}
        hitlWaitAbortCtrl = null;
    }
    const preferMobile = (typeof window !== "undefined" && window.innerWidth <= 760);
    const initMode = preferMobile ? "mobile" : "desktop";
    hitlActiveAccId = accId;
    hitlLastFrameSeq = -1;
    hitlPanMode = false;
    hitlViewportMode = initMode;
    hitlResetZoom();
    const titleEl = document.getElementById("hitlDialogTitle");
    if (titleEl) {
        titleEl.textContent = "الشاشة الحية: " + (accName ? (accName + " (" + accId + ")") : accId);
    }
    const statusEl = document.getElementById("hitlLiveStatus");
    if (statusEl) statusEl.textContent = "جاري تشغيل متصفح الحساب والبث الحي (CDP Screencast)...";
    const arBar = document.getElementById("hitlArBar");
    if (arBar) { arBar.textContent = ""; arBar.classList.add("hidden"); }
    const ttlBadge = document.getElementById("hitlTtlBadge");
    if (ttlBadge) ttlBadge.textContent = "--:--";
    const imgEl = document.getElementById("hitlScreenImg");
    if (imgEl) imgEl.removeAttribute("src");

    if (!dlg.open) {
        dlg.showModal();
    }
    try {
        const res = await apiCall("/api/hitl/start", "POST", { account_id: accId, mode: initMode });
        applyHitlSnapshot(res);
        if (res && !res.completed && (res.running || !res.ready)) {
            scheduleNextHitlFrame(accId, 30);
        }
    } catch (e) {
        if (statusEl) statusEl.textContent = "تعذر تشغيل الشاشة الحية: " + e.message;
    }
}

async function pollHitlState(accId) {
    const targetAcc = accId || hitlActiveAccId;
    const dlg = document.getElementById("hitlDialog");
    if (!targetAcc || hitlActiveAccId !== targetAcc || !dlg || !dlg.open) return;
    let shouldContinue = true;
    let nextDelay = 45;
    if (hitlWaitAbortCtrl) {
        try { hitlWaitAbortCtrl.abort(); } catch (_) {}
    }
    hitlWaitAbortCtrl = typeof AbortController !== "undefined" ? new AbortController() : null;
    try {
        const res = await fetch(
            "/api/hitl/wait?acc_id=" + encodeURIComponent(targetAcc) + "&since=" + encodeURIComponent(String(hitlLastFrameSeq)),
            {
                method: "GET",
                headers: tg && tg.initData ? { "X-Telegram-Init-Data": tg.initData } : {},
                signal: hitlWaitAbortCtrl ? hitlWaitAbortCtrl.signal : undefined,
            }
        );
        const st = await res.json();
        if (res.ok && st) {
            applyHitlSnapshot(st);
            if (st.completed || (!st.running && st.ready)) {
                shouldContinue = false;
            }
        } else {
            nextDelay = 900;
        }
    } catch (e) {
        if (e && e.name === "AbortError") return;
        nextDelay = 900;
    }
    if (shouldContinue && hitlActiveAccId === targetAcc && dlg.open) {
        scheduleNextHitlFrame(targetAcc, nextDelay);
    }
}

async function stopHitlLive() {
    if (hitlPollTimer) {
        clearTimeout(hitlPollTimer);
        hitlPollTimer = null;
    }
    if (hitlWaitAbortCtrl) {
        try { hitlWaitAbortCtrl.abort(); } catch (_) {}
        hitlWaitAbortCtrl = null;
    }
    const accId = hitlActiveAccId;
    hitlActiveAccId = null;
    if (!accId) return;
    try {
        await apiCall("/api/hitl/stop", "POST", { account_id: accId });
    } catch (e) {}
}

async function hitlSendText(withEnter) {
    if (!hitlActiveAccId) return;
    const inp = document.getElementById("hitlTextInput");
    const txt = inp ? inp.value : "";
    if (!txt) {
        showToast("أدخل النص أو الرمز أولاً");
        return;
    }
    try {
        const res = await apiCall("/api/hitl/input", "POST", {
            account_id: hitlActiveAccId,
            action: "type",
            text: txt,
            submit: !!withEnter
        });
        if (inp) inp.value = "";
        applyHitlSnapshot(res);
    } catch (e) {
        showToast(e.message);
    }
}

async function hitlKey(k) {
    if (!hitlActiveAccId) return;
    try {
        const res = await apiCall("/api/hitl/input", "POST", { account_id: hitlActiveAccId, action: "key", key: k });
        applyHitlSnapshot(res);
    } catch (e) {
        showToast(e.message);
    }
}

async function hitlScroll(dy) {
    if (!hitlActiveAccId) return;
    try {
        const res = await apiCall("/api/hitl/input", "POST", { account_id: hitlActiveAccId, action: "scroll", dy: dy });
        applyHitlSnapshot(res);
    } catch (e) {
        showToast(e.message);
    }
}

async function hitlAction(act) {
    if (!hitlActiveAccId) return;
    try {
        const res = await apiCall("/api/hitl/input", "POST", { account_id: hitlActiveAccId, action: act });
        applyHitlSnapshot(res);
    } catch (e) {
        showToast(e.message);
    }
}

/* ===== محرك الإعلانات العائمة التفاعلية (Top-Layer Dialog + Manual Popover) ===== */
function canTransitionDisplay() {
    if (_canTransDisplayCached !== null) return _canTransDisplayCached;
    if (!window.CSS || !CSS.supports || !CSS.supports("transition-behavior", "allow-discrete")) {
        _canTransDisplayCached = false;
        return false;
    }
    const ua = navigator.userAgent || "";
    if (/Firefox\/\d+/i.test(ua) && !/Seamonkey/i.test(ua)) {
        _canTransDisplayCached = false;
        return false;
    }
    _canTransDisplayCached = true;
    return true;
}

function hasNativePopover(el) {
    return !!(el && Object.hasOwn(HTMLElement.prototype, "popover") && typeof el.showPopover === "function");
}

function formatAnnRemainingAr(ann) {
    if (!ann || !ann.expires_at_ts || ann.expires_at_ts <= 0) return ann && ann.remaining_label ? ann.remaining_label : "دائم حتى الإزالة";
    const diff = Math.max(0, Math.floor(Number(ann.expires_at_ts) - Date.now() / 1000));
    if (diff <= 0) return "منتهي الصلاحية";
    if (diff < 60) return diff + " ثانية متبقية";
    if (diff < 3600) return Math.floor(diff / 60) + " دقيقة متبقية";
    if (diff < 86400) return Math.floor(diff / 3600) + " ساعة متبقية";
    return Math.floor(diff / 86400) + " يوم متبقي";
}

function wirePromoControls() {
    if (promoDialogWired) return;
    promoDialogWired = true;

    const modal = document.getElementById("promoModal");
    const closeBtn = document.getElementById("promoModalCloseBtn");
    const toastCard = document.getElementById("promoToastCard");
    const toastCloseBtn = document.getElementById("promoToastCloseBtn");

    if (closeBtn) {
        closeBtn.addEventListener("click", () => closePromoModalAnimated());
    }
    if (modal) {
        modal.addEventListener("cancel", (ev) => {
            if (!canTransitionDisplay()) {
                ev.preventDefault();
                closePromoModalAnimated();
            }
        });
        modal.addEventListener("close", () => {
            modal.returnValue = "";
            modal.removeAttribute("data-closing");
            flushQueuedPromoToast();
        });
        if (!("closedBy" in HTMLDialogElement.prototype)) {
            modal.addEventListener("click", (ev) => {
                if (!modal.open) return;
                const r = modal.getBoundingClientRect();
                const outside = ev.clientX < r.left || ev.clientX > r.right || ev.clientY < r.top || ev.clientY > r.bottom;
                if (outside) closePromoModalAnimated();
            });
        }
    }
    if (toastCard) {
        toastCard.addEventListener("mouseenter", () => { promoToastPaused = true; clearPromoToastTimer(); });
        toastCard.addEventListener("mouseleave", () => { promoToastPaused = false; schedulePromoToastAutoHide(); });
        toastCard.addEventListener("focusin", () => { promoToastPaused = true; clearPromoToastTimer(); });
        toastCard.addEventListener("focusout", () => {
            if (!toastCard.contains(document.activeElement)) {
                promoToastPaused = false;
                schedulePromoToastAutoHide();
            }
        });
        if (!hasNativePopover(toastCard) && toastCloseBtn) {
            toastCloseBtn.addEventListener("click", () => hidePromoToast());
        }
    }
}

function clearPromoToastTimer() {
    if (promoToastTimer) {
        clearTimeout(promoToastTimer);
        promoToastTimer = null;
    }
}

function schedulePromoToastAutoHide() {
    clearPromoToastTimer();
    if (promoToastPaused) return;
    promoToastTimer = setTimeout(() => {
        if (!promoToastPaused) hidePromoToast();
    }, 11000);
}

function isAnyModalOpen() {
    const hitl = document.getElementById("hitlDialog");
    const promo = document.getElementById("promoModal");
    return !!((hitl && hitl.open) || (promo && promo.open));
}

function hidePromoToast() {
    clearPromoToastTimer();
    const card = document.getElementById("promoToastCard");
    if (!card) return;
    if (hasNativePopover(card)) {
        try { card.hidePopover(); } catch (_) {}
    } else {
        card.classList.remove(":popover-open");
    }
}

function showPromoToast(ann) {
    if (!ann) return;
    if (isAnyModalOpen()) {
        queuedPromoAnn = ann;
        return;
    }
    const card = document.getElementById("promoToastCard");
    if (!card) return;
    activePromoAnn = ann;
    promoLastRepopAt[ann.id] = Date.now();

    card.className = "promo-toast-card";
    if (ann.display_style === "top_ribbon") card.classList.add("style-ribbon");
    else if (ann.display_style === "full_spotlight") card.classList.add("style-glow");
    else if (String(ann.badge || "").includes("عاجل")) card.classList.add("style-urgent");

    document.getElementById("promoToastBadge").textContent = ann.badge || "ميزة جديدة";
    document.getElementById("promoToastTitle").textContent = ann.title || "";
    document.getElementById("promoToastBody").textContent = ann.body || "";

    const openBtn = document.getElementById("promoToastOpenBtn");
    const ackBtn = document.getElementById("promoToastAckBtn");
    if (openBtn) openBtn.onclick = () => { hidePromoToast(); openPromoModal(ann); };
    if (ackBtn) {
        ackBtn.textContent = ann.cta_label || "فتح الميزة";
        ackBtn.onclick = () => executePromoCta(ann);
    }

    if (hasNativePopover(card)) {
        try { card.showPopover(); } catch (_) {}
    } else {
        card.classList.add(":popover-open");
    }
    try { tg?.HapticFeedback?.notificationOccurred("success"); } catch (_) {}
    schedulePromoToastAutoHide();
}

function flushQueuedPromoToast() {
    if (queuedPromoAnn && !isAnyModalOpen()) {
        const next = queuedPromoAnn;
        queuedPromoAnn = null;
        showPromoToast(next);
    }
}

function openPromoModal(ann) {
    if (!ann) return;
    const modal = document.getElementById("promoModal");
    if (!modal) return;
    hidePromoToast();
    activePromoAnn = ann;
    promoLastRepopAt[ann.id] = Date.now();

    document.getElementById("promoModalBadge").textContent = ann.badge || "ميزة جديدة";
    document.getElementById("promoModalTtl").textContent = formatAnnRemainingAr(ann);
    document.getElementById("promoModalTitle").textContent = ann.title || "";
    document.getElementById("promoModalBody").textContent = ann.body || "";

    const ctaBtn = document.getElementById("promoModalCtaBtn");
    if (ctaBtn) {
        const hasTargetTab = !!(ann.cta_tab && currentTabs.some(t => t.id === ann.cta_tab));
        ctaBtn.classList.toggle("hidden", !hasTargetTab);
        ctaBtn.textContent = ann.cta_label || "الانتقال الآن";
        ctaBtn.onclick = () => executePromoCta(ann);
    }
    modal.removeAttribute("data-closing");
    if (!modal.open && typeof modal.showModal === "function") {
        modal.showModal();
    }
    try { tg?.HapticFeedback?.impactOccurred("medium"); } catch (_) {}
}

function closePromoModalAnimated() {
    const modal = document.getElementById("promoModal");
    if (!modal || !modal.open) return;
    if (modal.hasAttribute("data-closing")) return;
    if (canTransitionDisplay() || window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
        modal.close("user_close");
        return;
    }
    modal.setAttribute("data-closing", "");
    const anims = typeof modal.getAnimations === "function" ? modal.getAnimations() : [];
    Promise.allSettled(anims.map(a => a.finished)).then(() => {
        modal.removeAttribute("data-closing");
        if (modal.open) modal.close("user_close");
    });
}

function executePromoCta(ann) {
    hidePromoToast();
    closePromoModalAnimated();
    if (ann && ann.cta_tab && currentTabs.some(t => t.id === ann.cta_tab)) {
        switchTab(ann.cta_tab, true);
    }
}

function presentFloatingAnnouncement(ann, preferModal = false) {
    if (!ann) return;
    if (preferModal && !isAnyModalOpen()) {
        openPromoModal(ann);
    } else {
        showPromoToast(ann);
    }
}

function triggerOpenPromoIfNeeded() {
    const anns = (appState && appState.announcements) || [];
    const target = anns.find(a => a.repeat_on_open && !promoShownOnOpen[a.id]);
    if (!target) return;
    promoShownOnOpen[target.id] = true;
    presentFloatingAnnouncement(target, target.display_style === "full_spotlight");
}

function syncPromoTicker() {
    if (promoTickerInterval) {
        clearTimeout(promoTickerInterval);
        promoTickerInterval = null;
    }
    if (!appState || !appState.authorized) return;
    const list = (appState && appState.announcements) || [];
    const nowSec = Math.floor(Date.now() / 1000);
    const valid = list.filter(a => !a.expires_at_ts || Number(a.expires_at_ts) <= 0 || Number(a.expires_at_ts) > nowSec);
    if (valid.length !== list.length && appState) {
        appState.announcements = valid;
    }
    if (!valid.length) return;

    let nextWaitMs = 60000;
    for (const a of valid) {
        if (a.expires_at_ts && Number(a.expires_at_ts) > 0) {
            nextWaitMs = Math.min(nextWaitMs, Math.max(1000, (Number(a.expires_at_ts) - nowSec) * 1000));
        }
        const repMs = (a.repeat_interval_sec || 0) * 1000;
        if (repMs > 0) {
            const last = promoLastRepopAt[a.id] || Date.now();
            const dueIn = Math.max(1000, repMs - (Date.now() - last));
            nextWaitMs = Math.min(nextWaitMs, dueIn);
        }
    }

    promoTickerInterval = setTimeout(() => {
        if (document.visibilityState === "visible" && appState && appState.authorized) {
            const curSec = Math.floor(Date.now() / 1000);
            const curList = (appState && appState.announcements) || [];
            const activeValid = curList.filter(a => !a.expires_at_ts || Number(a.expires_at_ts) <= 0 || Number(a.expires_at_ts) > curSec);
            appState.announcements = activeValid;
            for (const a of activeValid) {
                const repMs = (a.repeat_interval_sec || 0) * 1000;
                if (repMs > 0 && Date.now() - (promoLastRepopAt[a.id] || 0) >= repMs) {
                    presentFloatingAnnouncement(a, false);
                    break;
                }
            }
        }
        syncPromoTicker();
    }, Math.max(5000, nextWaitMs));
}

function populateAnnouncementFormMeta() {
    if (!appState || !appState.ann_meta) return;
    const meta = appState.ann_meta;
    const selBadge = document.getElementById("annBadge");
    if (selBadge && !selBadge.options.length) {
        for (const b of (meta.badges || [])) {
            const o = document.createElement("option");
            o.value = b;
            o.textContent = b;
            selBadge.appendChild(o);
        }
    }
    const selStyle = document.getElementById("annStyle");
    if (selStyle && !selStyle.options.length) {
        for (const [k, v] of Object.entries(meta.styles || {})) {
            const o = document.createElement("option");
            o.value = k;
            o.textContent = v;
            selStyle.appendChild(o);
        }
    }
    const selDur = document.getElementById("annDuration");
    if (selDur && !selDur.options.length) {
        for (const pair of (meta.durations || [])) {
            const o = document.createElement("option");
            o.value = String(pair[0]);
            o.textContent = pair[1];
            if (Number(pair[0]) === 86400) o.selected = true;
            selDur.appendChild(o);
        }
    }
    const selRep = document.getElementById("annRepeat");
    if (selRep && !selRep.options.length) {
        for (const pair of (meta.repeats || [])) {
            const o = document.createElement("option");
            o.value = String(pair[0]);
            o.textContent = pair[1];
            if (Number(pair[0]) === 3600) o.selected = true;
            selRep.appendChild(o);
        }
    }
    const selDm = document.getElementById("annDeliveryMode");
    if (selDm && !selDm.options.length) {
        for (const [k, v] of Object.entries(meta.delivery_modes || {})) {
            const o = document.createElement("option");
            o.value = k;
            o.textContent = v;
            if (k === "animated_card") o.selected = true;
            selDm.appendChild(o);
        }
    }
    const selRb = document.getElementById("annRepeatBehavior");
    if (selRb && !selRb.options.length) {
        for (const [k, v] of Object.entries(meta.repeat_behaviors || {})) {
            const o = document.createElement("option");
            o.value = k;
            o.textContent = v;
            if (k === "replace") o.selected = true;
            selRb.appendChild(o);
        }
    }
    const selEff = document.getElementById("annEffect");
    if (selEff && !selEff.options.length) {
        for (const [k, v] of Object.entries(meta.effect_presets || {})) {
            const o = document.createElement("option");
            o.value = k;
            o.textContent = v;
            if (k === "none") o.selected = true;
            selEff.appendChild(o);
        }
    }
}

async function loadAnnouncementsTab() {
    populateAnnouncementFormMeta();
    try {
        const res = await apiCall("/api/announcements/list");
        if (appState) {
            appState.announcements = res.announcements || [];
            appState.all_announcements = res.all_announcements || [];
        }
        renderAnnouncementsList();
    } catch (e) {
        showToast(e.message);
    }
}

function renderAnnouncementsList() {
    const box = document.getElementById("announcementsAdminList");
    if (!box || !appState) return;
    const items = appState.all_announcements || [];
    box.innerHTML = "";
    if (!items.length) {
        box.innerHTML = '<div class="mono">لا توجد إعلانات منشورة حتى الآن.</div>';
        return;
    }
    for (const a of items) {
        const row = document.createElement("div");
        row.className = "item-row";

        const head = document.createElement("div");
        head.className = "item-head";
        const nm = document.createElement("span");
        nm.className = "item-name";
        nm.textContent = "[" + (a.badge || "إعلان") + "] " + a.title;
        const st = document.createElement("span");
        st.className = (a.active && !a.is_expired) ? "badge-ok" : "badge-bad";
        st.textContent = a.is_expired ? "منتهي" : (a.active ? "نشط وعائم" : "موقوف");
        head.appendChild(nm);
        head.appendChild(st);
        row.appendChild(head);

        const body = document.createElement("div");
        body.className = "mono";
        body.style.marginBottom = "6px";
        body.textContent = a.body;
        row.appendChild(body);

        const metaLine = document.createElement("div");
        metaLine.className = "mono";
        metaLine.style.marginBottom = "8px";
        const dmLabel = (appState.ann_meta && appState.ann_meta.delivery_modes && appState.ann_meta.delivery_modes[a.delivery_mode || "animated_card"]) || (a.delivery_mode || "animated_card");
        const rbLabel = (appState.ann_meta && appState.ann_meta.repeat_behaviors && appState.ann_meta.repeat_behaviors[a.repeat_behavior || "replace"]) || (a.repeat_behavior || "replace");
        metaLine.textContent =
            "المدة: " + formatAnnRemainingAr(a) +
            " | التكرار: " + ((a.repeat_interval_sec || 0) > 0 ? ("كل " + Math.round(a.repeat_interval_sec / 60) + " د") : "مرة واحدة") +
            " | النمط: " + dmLabel +
            " | السلوك: " + rbLabel +
            " | تثبيت: " + (a.pin_in_chat ? "نعم" : "لا (بدون إزعاج)");
        row.appendChild(metaLine);

        const actRow = document.createElement("div");
        actRow.style.cssText = "display:flex;gap:6px;flex-wrap:wrap;";

        const bPreview = document.createElement("button");
        bPreview.type = "button";
        bPreview.className = "btn btn-muted btn-sm";
        bPreview.textContent = "معاينة عائمة";
        bPreview.onclick = () => openPromoModal(a);
        actRow.appendChild(bPreview);

        const bPush = document.createElement("button");
        bPush.type = "button";
        bPush.className = "btn btn-primary btn-sm";
        bPush.textContent = "بث وإرسال للجميع الآن";
        bPush.onclick = () => manageAnnouncementAction(a.id, "push_now");
        actRow.appendChild(bPush);

        const bTog = document.createElement("button");
        bTog.type = "button";
        bTog.className = "btn btn-sm " + (a.active ? "btn-muted" : "btn-ok");
        bTog.textContent = a.active ? "إيقاف مؤقت" : "تفعيل";
        bTog.onclick = () => manageAnnouncementAction(a.id, "toggle");
        actRow.appendChild(bTog);

        const bDel = document.createElement("button");
        bDel.type = "button";
        bDel.className = "btn btn-danger btn-sm";
        bDel.textContent = "حذف الإعلان";
        bDel.onclick = () => manageAnnouncementAction(a.id, "delete");
        actRow.appendChild(bDel);

        row.appendChild(actRow);
        box.appendChild(row);
    }
}

async function createAnnouncementSubmit() {
    const title = (document.getElementById("annTitle")?.value || "").trim();
    const body = (document.getElementById("annBody")?.value || "").trim();
    if (!title || !body) {
        showToast("أدخل عنوان الإعلان ونصه أولاً");
        return;
    }
    const btn = document.getElementById("btnCreateAnn");
    if (btn) btn.disabled = true;
    try {
        const res = await apiCall("/api/announcements/manage", "POST", {
            action: "create",
            title,
            body,
            badge: document.getElementById("annBadge")?.value || "ميزة جديدة",
            display_style: document.getElementById("annStyle")?.value || "floating_card",
            delivery_mode: document.getElementById("annDeliveryMode")?.value || "animated_card",
            repeat_behavior: document.getElementById("annRepeatBehavior")?.value || "replace",
            effect_preset: document.getElementById("annEffect")?.value || "none",
            duration_sec: parseInt(document.getElementById("annDuration")?.value || "86400", 10) || 0,
            repeat_interval_sec: parseInt(document.getElementById("annRepeat")?.value || "3600", 10) || 0,
            cta_label: document.getElementById("annCtaLabel")?.value || "فتح الميزة الآن",
            cta_tab: document.getElementById("annCtaTab")?.value || "mission",
            pin_in_chat: !!document.getElementById("annPinChat")?.checked,
            push_telegram: !!document.getElementById("annPushNow")?.checked,
            repeat_on_open: !!document.getElementById("annRepeatOnOpen")?.checked,
        });
        showToast(res.message || "تم نشر الإعلان العائم بنجاح");
        document.getElementById("annTitle").value = "";
        document.getElementById("annBody").value = "";
        if (appState) {
            appState.announcements = res.announcements || [];
            appState.all_announcements = res.all_announcements || [];
        }
        renderAnnouncementsList();
        if (res.announcement) presentFloatingAnnouncement(res.announcement, false);
    } catch (e) {
        showToast(e.message);
    } finally {
        if (btn) btn.disabled = false;
    }
}

async function manageAnnouncementAction(annId, action) {
    try {
        const res = await apiCall("/api/announcements/manage", "POST", { action, ann_id: annId });
        showToast(res.message || "تم التحديث");
        if (appState) {
            appState.announcements = res.announcements || [];
            appState.all_announcements = res.all_announcements || [];
        }
        renderAnnouncementsList();
        if (action === "delete" || action === "toggle") {
            if (activePromoAnn && activePromoAnn.id === annId) {
                hidePromoToast();
                closePromoModalAnimated();
            }
        }
    } catch (e) {
        showToast(e.message);
    }
}

(function wireHitlDialog() {
    const dlg = document.getElementById("hitlDialog");
    const closeBtn = document.getElementById("btnHitlClose");
    const stage = document.getElementById("hitlStage");
    const wrap = document.getElementById("hitlCanvasWrap");
    const dot = document.getElementById("hitlTapDot");

    if (closeBtn && dlg) {
        closeBtn.addEventListener("click", () => dlg.close("user_close"));
    }
    if (dlg) {
        dlg.addEventListener("close", () => {
            dlg.returnValue = "";
            stopHitlLive();
            flushQueuedPromoToast();
        });
    }
    if (wrap && stage) {
        let dragState = null;
        let lastTapSentAt = 0;

        async function dispatchCanvasClick(clientX, clientY) {
            if (!hitlActiveAccId) return;
            const imgEl = document.getElementById("hitlScreenImg");
            const rect = (imgEl && imgEl.getBoundingClientRect().width > 0)
                ? imgEl.getBoundingClientRect()
                : wrap.getBoundingClientRect();
            if (!rect.width || !rect.height) return;
            const xNorm = Math.max(0.002, Math.min(0.998, (clientX - rect.left) / rect.width));
            const yNorm = Math.max(0.002, Math.min(0.998, (clientY - rect.top) / rect.height));
            lastTapSentAt = Date.now();
            if (dot) {
                dot.style.left = (xNorm * 100).toFixed(2) + "%";
                dot.style.top = (yNorm * 100).toFixed(2) + "%";
                dot.classList.remove("hidden");
                setTimeout(() => dot.classList.add("hidden"), 650);
            }
            try { tg?.HapticFeedback?.impactOccurred("light"); } catch (_) {}
            try {
                const res = await apiCall("/api/hitl/input", "POST", {
                    account_id: hitlActiveAccId,
                    action: "click",
                    x_norm: xNorm,
                    y_norm: yNorm
                });
                applyHitlSnapshot(res);
            } catch (e) {
                showToast(e.message);
            }
        }

        wrap.addEventListener("pointerdown", (ev) => {
            if (ev.button && ev.button !== 0) return;
            dragState = {
                id: ev.pointerId,
                startX: ev.clientX,
                startY: ev.clientY,
                lastX: ev.clientX,
                lastY: ev.clientY,
                moved: false
            };
            try { wrap.setPointerCapture(ev.pointerId); } catch (_) {}
        });
        wrap.addEventListener("pointermove", (ev) => {
            if (!dragState || dragState.id !== ev.pointerId) return;
            if (Math.hypot(ev.clientX - dragState.startX, ev.clientY - dragState.startY) > 18) {
                dragState.moved = true;
            }
            if (hitlPanMode || dragState.moved) {
                stage.scrollLeft -= (ev.clientX - dragState.lastX);
                stage.scrollTop -= (ev.clientY - dragState.lastY);
                ev.preventDefault();
            }
            dragState.lastX = ev.clientX;
            dragState.lastY = ev.clientY;
        });
        wrap.addEventListener("pointercancel", () => { dragState = null; });
        wrap.addEventListener("pointerup", async (ev) => {
            if (!dragState || dragState.id !== ev.pointerId) return;
            const wasMoved = dragState.moved;
            dragState = null;
            if (hitlPanMode || wasMoved) return;
            await dispatchCanvasClick(ev.clientX, ev.clientY);
        });
        wrap.addEventListener("click", async (ev) => {
            if (hitlPanMode) return;
            if (Date.now() - lastTapSentAt < 450) return;
            await dispatchCanvasClick(ev.clientX, ev.clientY);
        });
    }
})();

async function loadProxiesTab() {
    try {
        const res = await apiCall("/api/proxies/status", "GET");
        appState.proxy_report = res;
        renderProxiesTab(res);
    } catch (e) {
        showToast(e.message);
    }
}

async function proxyAction(act, extra) {
    try {
        const res = await apiCall("/api/proxies/manage", "POST", Object.assign({ action: act }, extra || {}));
        showToast(res.message || "تم التحديث");
        if (res.proxy_report) {
            appState.proxy_report = res.proxy_report;
            renderProxiesTab(res.proxy_report);
        }
    } catch (e) {
        showToast(e.message);
    }
}

async function submitBulkProxies() {
    const inp = document.getElementById("inpProxiesBulk");
    const txt = (inp && inp.value || "").trim();
    if (!txt) {
        showToast("ألصق قائمة البروكسيات أولاً");
        return;
    }
    await proxyAction("add", { text: txt });
    if (inp) inp.value = "";
}

function renderProxiesTab(report) {
    const rep = report || (appState && appState.proxy_report);
    const kpiBox = document.getElementById("proxyKpiGrid");
    const listBox = document.getElementById("proxiesDetailList");
    if (!kpiBox || !listBox) return;
    if (!rep || !rep.summary) {
        kpiBox.innerHTML = "";
        listBox.textContent = "جاري التحميل...";
        return;
    }
    const s = rep.summary;
    const capSel = document.getElementById("inpProxyCap");
    if (capSel) capSel.value = String(s.configured_max_per_proxy || 0);
    const ivSel = document.getElementById("inpProxyInterval");
    if (ivSel) ivSel.value = String(s.auto_check_interval_sec || 120);
    const watchBtn = document.getElementById("btnProxyWatchToggle");
    if (watchBtn) {
        watchBtn.textContent = s.auto_check_enabled ? "المراقب الآلي: شغال" : "المراقب الآلي: متوقف";
    }

    const kpis = [
        { val: String(s.total || 0), lbl: "إجمالي البروكسيات" },
        { val: String(s.alive || 0) + " / " + String(s.dead || 0), lbl: "حي / متعطل" },
        { val: String(s.bindings_count || 0) + (s.safe_capacity ? " / " + s.safe_capacity : ""), lbl: "حسابات مربوطة" },
        { val: String(s.total_uses || 0), lbl: "إجمالي مرات التشغيل" },
    ];
    kpiBox.innerHTML = "";
    for (const k of kpis) {
        const box = document.createElement("div");
        box.className = "proxy-kpi-box";
        const vEl = document.createElement("div");
        vEl.className = "proxy-kpi-val";
        vEl.textContent = k.val;
        const lEl = document.createElement("div");
        lEl.className = "proxy-kpi-lbl";
        lEl.textContent = k.lbl;
        box.appendChild(vEl);
        box.appendChild(lEl);
        kpiBox.appendChild(box);
    }

    const items = rep.items || [];
    listBox.innerHTML = "";
    if (!items.length) {
        const empty = document.createElement("div");
        empty.className = "mono";
        empty.textContent = "لا توجد بروكسيات مضافة بعد. ألصق بروكسيات Webshare أو اسحب من GitHub أعلاه.";
        listBox.appendChild(empty);
        return;
    }

    for (const it of items) {
        const row = document.createElement("div");
        row.className = "item-row";

        const head = document.createElement("div");
        head.className = "item-head";
        const title = document.createElement("span");
        title.className = "item-name";
        title.textContent = "#" + (it.idx + 1) + "  " + (it.masked_uri || (it.host + ":" + it.port)) + (it.country_code ? " [" + it.country_code + "]" : "");
        const badge = document.createElement("span");
        badge.className = it.alive === true ? "badge-ok" : (it.alive === false ? "badge-bad" : "mono");
        badge.textContent = it.alive === true ? ("يعمل" + (it.latency_ms ? " · " + it.latency_ms + "ms" : "")) : (it.alive === false ? "متعطل" : "لم يُفحص");
        head.appendChild(title);
        head.appendChild(badge);
        row.appendChild(head);

        const statsLine = document.createElement("div");
        statsLine.className = "mono";
        statsLine.textContent =
            "الاستخدام: " + (it.uses_count || 0) +
            " مرة (نجح " + (it.success_count || 0) + " · فشل " + (it.total_fail_count || 0) + ")" +
            " | الحسابات: " + (it.bound_count || 0) + (it.max_per_proxy ? "/" + it.max_per_proxy : "");
        row.appendChild(statsLine);

        if (it.last_error) {
            const errEl = document.createElement("div");
            errEl.className = "badge-bad";
            errEl.style.marginTop = "4px";
            errEl.textContent = "سبب العطل: " + it.last_error;
            row.appendChild(errEl);
        }

        const accWrap = document.createElement("div");
        accWrap.style.cssText = "display:flex;gap:5px;flex-wrap:wrap;margin-top:6px;";
        const bAccs = it.bound_accounts || [];
        if (!bAccs.length) {
            const noneChip = document.createElement("span");
            noneChip.className = "mono";
            noneChip.textContent = "لا توجد حسابات مربوطة بهذا الـ IP";
            accWrap.appendChild(noneChip);
        } else {
            for (const b of bAccs) {
                const chip = document.createElement("button");
                chip.type = "button";
                chip.className = "proxy-acc-chip";
                const isAct = String(b.status || "").includes("نشط");
                chip.textContent = (isAct ? "● " : "○ ") + b.name;
                chip.onclick = () => openHitlLive(b.id, b.name);
                accWrap.appendChild(chip);
            }
        }
        row.appendChild(accWrap);

        const btns = document.createElement("div");
        btns.style.cssText = "display:flex;gap:6px;flex-wrap:wrap;margin-top:8px;";
        const bChk = document.createElement("button");
        bChk.type = "button";
        bChk.className = "btn btn-primary btn-sm";
        bChk.textContent = "فحص هذا الـ IP";
        bChk.onclick = () => proxyAction("check_one", { selector: it.id || it.idx });
        const bRebind = document.createElement("button");
        bRebind.type = "button";
        bRebind.className = "btn btn-muted btn-sm";
        bRebind.textContent = "نقل حساباته لـ IP سليم";
        bRebind.onclick = () => proxyAction("rebind_one", { selector: it.id || it.idx });
        const bDel = document.createElement("button");
        bDel.type = "button";
        bDel.className = "btn btn-danger btn-sm";
        bDel.textContent = "حذف";
        bDel.onclick = () => proxyAction("delete_one", { selector: it.id || it.idx });
        btns.appendChild(bChk);
        btns.appendChild(bRebind);
        btns.appendChild(bDel);
        row.appendChild(btns);

        listBox.appendChild(row);
    }
}

bootstrap();
</script>
</body>
</html>
"""
