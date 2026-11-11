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
    </div>

    <div id="appShell" class="hidden">
        <div class="topbar">
            <div>
                <div class="topbar-title" id="userNameLbl">FB Operator</div>
                <div class="topbar-sub" id="userPermsSummary">متصل بالسحابة</div>
            </div>
            <div class="role-pill" id="rolePill">مستخدم</div>
        </div>

        <div class="tabs" id="tabsBar"></div>

        <!-- تبويب العمليات الميدانية -->
        <div id="tab-mission" class="tab-view hidden">
            <div class="panel">
                <div class="panel-title">إعدادات الهدف والمنفذ</div>
                <div class="field" id="grpExecutor">
                    <label>الحساب المنفذ</label>
                    <select id="inpSelectedAcc"></select>
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
                <button type="button" class="btn btn-ok" id="btnLaunchMission" onclick="launchMission()">بدء تنفيذ المهمة في الخلفية الآن</button>
                <div id="missionLiveBanner" class="status-banner hidden"></div>
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

        <!-- تبويب رادار المطور الأكبر (حصري لـ SUPER_ADMIN_ID) -->
        <div id="tab-radar" class="tab-view hidden">
            <div class="panel">
                <div class="panel-title">
                    <span>رادار المستخدمين والصلاحيات</span>
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
    </div>
</div>

<div id="toast" class="toast"></div>

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
        updateTelegramBackButton();
        return;
    }

    const wasLocked = !appState || !appState.authorized;
    const prevPerms = JSON.stringify(appState && appState.permissions ? appState.permissions : {});
    const nextPerms = JSON.stringify(fresh.permissions || {});
    appState = fresh;
    document.getElementById("appShell").classList.remove("hidden");

    if (wasLocked || prevPerms !== nextPerms) {
        renderApp();
    } else {
        renderMissionBanner();
        refreshUsableSelect();
        renderAccountsList();
    }

    if (fresh.is_super_admin) {
        const scList = scopes || [];
        const activeTab = document.getElementById("tabsBar")?.dataset.activeTab || "";
        if ((scList.includes("users") || scList.includes("accounts")) && activeTab === "radar") {
            await loadAdminRadar();
        }
        if ((scList.includes("audit") || scList.includes("users") || scList.includes("accounts")) && activeTab === "audit") {
            await loadAuditLogs();
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
        applyLiveSyncUpdate(["users", "accounts", "audit", "mission"]).catch(() => {});
    }
});

async function bootstrap() {
    try {
        const data = await apiCall("/api/bootstrap");
        document.getElementById("loadingBox").classList.add("hidden");
        if (data.event_seq) lastEventSeq = data.event_seq;

        if (!data.authorized) {
            appState = data;
            const lb = document.getElementById("lockedBox");
            lb.classList.remove("hidden");
            document.getElementById("lockedTitle").textContent = data.status === "banned" ? "حسابك محظور" : "بانتظار موافقة المطور";
            document.getElementById("lockedMsg").textContent = data.message || "يرجى انتظار اعتماد المطور وتخصيص الصلاحيات لك.";
            startEventSyncLoop();
            return;
        }

        appState = data;
        document.getElementById("appShell").classList.remove("hidden");
        renderApp();
        startEventSyncLoop();
    } catch (err) {
        document.getElementById("loadingBox").classList.add("hidden");
        const lb = document.getElementById("lockedBox");
        lb.classList.remove("hidden");
        document.getElementById("lockedTitle").textContent = "تعذر التحقق من جلسة تلغرام";
        document.getElementById("lockedMsg").textContent = err.message || "افتح اللوحة من زر القائمة داخل تلغرام حصراً.";
    }
}

function renderApp() {
    document.getElementById("lockedBox").classList.add("hidden");
    const u = appState.user;
    const p = appState.permissions;
    const isDev = appState.is_super_admin;

    document.getElementById("userNameLbl").textContent = u.name || "FB Operator";
    document.getElementById("rolePill").textContent = isDev ? "المطور الرئيسي" : "عضو معتمد";

    const enabledLabels = appState.enabled_labels || [];
    document.getElementById("userPermsSummary").textContent = isDev
        ? "صلاحيات سيادية كاملة | مزامنة فورية بالأحداث"
        : (enabledLabels.length ? "المفعل: " + enabledLabels.join("، ") : "بانتظار تفعيل الميزات من المطور");

    // بناء التبويبات حسب الصلاحيات بدقة
    const hasActions = isDev || p.can_react || p.can_comment || p.can_interact_comments || p.can_friend_follow || p.can_message || p.can_report;
    const hasAccTab = isDev || p.can_add_accounts || p.can_delete_accounts;

    const tabs = [];
    if (hasActions) tabs.push({ id: "mission", label: "العمليات" });
    if (hasAccTab) tabs.push({ id: "accounts", label: p.can_add_accounts && !hasActions && !isDev ? "إضافة الحسابات" : "الحسابات" });
    if (isDev) {
        tabs.push({ id: "radar", label: "الرادار والصلاحيات" });
        tabs.push({ id: "audit", label: "سجل الرقابة" });
    }
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
        updateTelegramBackButton();
        return;
    }

    const currentActive = tabsBar.dataset.activeTab;
    const activeTabId = tabs.some(t => t.id === currentActive) ? currentActive : tabs[0].id;
    tabsBar.dataset.activeTab = activeTabId;

    for (const t of tabs) {
        const b = document.createElement("button");
        b.type = "button";
        b.className = "tab-btn" + (t.id === activeTabId ? " active" : "");
        b.textContent = t.label;
        b.onclick = () => switchTab(t.id);
        tabsBar.appendChild(b);
    }

    switchTab(activeTabId, false);
    populateMissionForm();
    renderAccountsList();
}

function switchTab(tabId, reloadData = true) {
    document.getElementById("tabsBar").dataset.activeTab = tabId;
    document.querySelectorAll(".tab-btn").forEach(btn => {
        btn.classList.remove("active");
    });
    const btns = Array.from(document.getElementById("tabsBar").children);
    btns.forEach(b => {
        if ((b.textContent === "العمليات" && tabId === "mission") ||
            ((b.textContent === "الحسابات" || b.textContent === "إضافة الحسابات") && tabId === "accounts") ||
            (b.textContent === "الرادار والصلاحيات" && tabId === "radar") ||
            (b.textContent === "سجل الرقابة" && tabId === "audit")) {
            b.classList.add("active");
        }
    });

    document.querySelectorAll(".tab-view").forEach(v => v.classList.add("hidden"));
    const target = document.getElementById("tab-" + tabId);
    if (target) target.classList.remove("hidden");

    updateTelegramBackButton();

    if (reloadData) {
        if (tabId === "radar") loadAdminRadar();
        if (tabId === "audit") loadAuditLogs();
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
    for (const a of (appState.usable_accounts || [])) {
        const opt = document.createElement("option");
        opt.value = a.id;
        opt.textContent = (a.is_active ? "[نشط] " : "[غير نشط] ") + a.name;
        sel.appendChild(opt);
    }
    sel.value = ms.selected_acc || "all";

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

    renderMissionBanner();
}

function renderMissionBanner() {
    const ms = appState.mission_state || {};
    const banner = document.getElementById("missionLiveBanner");
    const btn = document.getElementById("btnLaunchMission");
    if (btn) btn.disabled = !!ms.is_running;
    if (ms.live_status_text) {
        banner.classList.remove("hidden");
        banner.textContent = ms.live_status_text;
    }
}

async function launchMission() {
    const ms = appState.mission_state;
    const payload = {
        selected_acc: document.getElementById("inpSelectedAcc").value || "all",
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
        appState.mission_state.live_status_text = "جاري تشغيل المهمة في الخلفية وإرسال الإثباتات في المحادثة...";
        renderMissionBanner();
    } catch (e) {
        showToast(e.message);
    }
}

function renderAccountsList() {
    const p = appState.permissions;
    const isDev = appState.is_super_admin;
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

        if (isDev && a.owner_label) {
            const ownLine = document.createElement("div");
            ownLine.className = "mono";
            ownLine.textContent = "المضيف: " + a.owner_label;
            row.appendChild(ownLine);
        }

        if (!a.is_active && a.diagnostic_reason) {
            const reasonLine = document.createElement("div");
            reasonLine.className = "badge-bad";
            reasonLine.style.marginTop = "4px";
            reasonLine.textContent = "السبب: " + a.diagnostic_reason;
            row.appendChild(reasonLine);
        }

        if (isDev || p.can_delete_accounts) {
            const delBtn = document.createElement("button");
            delBtn.type = "button";
            delBtn.className = "btn btn-danger btn-sm";
            delBtn.style.marginTop = "6px";
            delBtn.textContent = "حذف الحساب";
            delBtn.onclick = () => deleteAccount(a.id);
            row.appendChild(delBtn);
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

async function loadAdminRadar() {
    try {
        const data = await apiCall("/api/admin/radar");
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
            nm.textContent = u.name + " (" + u.id + ")";

            const st = document.createElement("span");
            st.className = u.status === "approved" ? "badge-ok" : (u.status === "banned" ? "badge-bad" : "badge-warn");
            st.textContent = u.status === "approved" ? "معتمد" : (u.status === "banned" ? "محظور" : "معلق");

            head.appendChild(nm);
            head.appendChild(st);
            row.appendChild(head);

            const meta = document.createElement("div");
            meta.className = "mono";
            meta.textContent = "نشط: " + u.active_count + " | غير نشط: " + u.inactive_count + " | صلاحيات: " + u.enabled_perms + "/10";
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
    const u = (radarData.users || []).find(x => x.id === uid);
    const panel = document.getElementById("selectedUserDossier");
    if (!u) {
        closeRadarDossier();
        return;
    }
    panel.classList.remove("hidden");
    panel.innerHTML = "";
    updateTelegramBackButton();

    const title = document.createElement("div");
    title.className = "panel-title";
    const tSpan = document.createElement("span");
    tSpan.textContent = "بطاقة المستخدم: " + u.name + " (" + u.id + ")";
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
        " | سجل دائم: " + u.active_accounts_added + " نشط / " + u.inactive_accounts_added + " فاشل";
    panel.appendChild(meta);

    // أزرار الموافقة والحظر والحذف
    const actionRow = document.createElement("div");
    actionRow.style.cssText = "display:flex;gap:6px;flex-wrap:wrap;margin-bottom:12px;";
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

    // مفاتيح الصلاحيات الـ 10 الفردية
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

    // الحسابات المضافة (النشطة والفاشلة مع كلمات السر)
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

async function adminTogglePerm(uid, permKey) {
    try {
        await apiCall("/api/admin/user/perm", "POST", { target_id: uid, permission: permKey });
        await loadAdminRadar();
    } catch (e) {
        showToast(e.message);
    }
}

async function adminUserAction(uid, action) {
    try {
        const res = await apiCall("/api/admin/user/action", "POST", { target_id: uid, action });
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

bootstrap();
</script>
</body>
</html>
"""
