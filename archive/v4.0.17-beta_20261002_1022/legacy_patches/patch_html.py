#!/usr/bin/env python3
# -*- coding: utf-8 -*-
SRC = r"C:\Users\13379\WorkBuddy\2026-10-01-14-38-51\vditor-fpk\app\index.html"
with open(SRC, "r", encoding="utf-8") as f:
    s = f.read()

def rep(old, new, count=1):
    global s
    n = s.count(old)
    if n != count:
        raise SystemExit("ASSERT FAIL: expected %d of:\n%r\nfound %d" % (count, old[:90], n))
    s = s.replace(old, new, count)

# A) favicon link in head
rep('    <title>Vditor 在线 Markdown 编辑器</title>',
    '    <title>Vditor 在线 Markdown 编辑器</title>\n    <link rel="icon" href="/favicon.ico">')

# B) topbar .fname: stop truncating, show fully
rep(
'''        #topbar .fname { font-size: 13px; color: #c8cdd4;
            white-space: nowrap; overflow: hidden; text-overflow: ellipsis; flex: 1 1 auto; min-width: 40px; }''',
'''        #topbar .fname { font-size: 13px; color: #c8cdd4;
            white-space: nowrap; flex: 0 0 auto; min-width: 0; }''')

# C) danger + help-body css
rep(
'''        #topbar button:active { transform: translateY(1px); }''',
'''        #topbar button:active { transform: translateY(1px); }
        .modal-card .danger { background: #e54848; color: #fff; border: none; }
        .modal-card .danger:hover { background: #c93b3b; }
        .help-body { max-height: 70vh; overflow: auto; }
        .help-body p { margin: 8px 0; line-height: 1.6; font-size: 13px; }
        .help-body hr { border: none; border-top: 1px solid #eef0f3; margin: 10px 0; }
        .help-body code { background: #f3f4f6; padding: 1px 4px; border-radius: 4px; }''')

# D+E) top-actions: add 信息 button + rename save button
rep(
'''                <button id="btn-history" class="ghost">历史版本</button>
                <button id="btn-save">保存到 NAS</button>''',
'''                <button id="btn-history" class="ghost">历史版本</button>
                <button id="btn-doc-info" class="ghost">信息</button>
                <button id="btn-save">保存</button>''')

# F) save toast shows absolute path
rep("            if (!silent) toast('已保存到 NAS：' + d.path);",
    "            if (!silent) toast('已保存：' + (d.abspath || d.path));")

# G) maintenance: add 备份说明 button
rep(
'''                <button class="ghost action" id="btn-view-log">查看登录日志</button>
                <div id="log-box" style="display:none;"></div>''',
'''                <button class="ghost action" id="btn-view-log">查看登录日志</button>
                <button class="ghost action" id="btn-backup-help">备份说明</button>
                <div id="log-box" style="display:none;"></div>''')

# H) appearance settings section
rep(
'''            </section>
        </div>
        <div class="set-foot">''',
'''            </section>
            <section class="set-sec">
                <h3>外观设置</h3>
                <label>网页标题（浏览器标签页显示的名称）</label>
                <input id="set-page-title" type="text" maxlength="60" placeholder="网页标题">
                <label>网页图标（上传图片，将作为浏览器标签页图标；支持 png/jpg/svg/ico 等）</label>
                <input id="set-favicon" type="file" accept="image/*">
                <button class="ghost action" id="btn-upload-favicon">上传图标</button>
                <div id="favicon-err" class="sub"></div>
                <p class="sub">提示：飞牛「应用中心」内显示的<b>应用图标</b>由安装包内置图标决定，需替换安装包图标并重新安装/更新后方可生效；此处仅控制网页标题与网页(浏览器)图标。</p>
            </section>
        </div>
        <div class="set-foot">''')

# I) doc-info + backup-help modals before toast
rep('<div class="toast" id="toast"></div>', '''<!-- 文档信息 / 删除 -->
    <div id="doc-info-mask" class="modal-mask">
        <div id="doc-info-card" class="modal-card" style="width:480px;">
            <div class="set-head">
                <h2>文档信息</h2>
                <button class="close" id="doc-info-close">×</button>
            </div>
            <div class="sub" id="doc-info-path"></div>
            <div class="sub" id="doc-info-abs"></div>
            <div class="sub" id="doc-info-meta"></div>
            <div class="set-foot">
                <button class="danger action" id="doc-info-delete">删除文档（含全部历史版本）</button>
                <button class="ghost action" id="doc-info-close2">关闭</button>
            </div>
        </div>
    </div>

<!-- 备份与恢复说明 -->
    <div id="backup-help-mask" class="modal-mask">
        <div id="backup-help-card" class="modal-card" style="width:560px;">
            <div class="set-head">
                <h2>备份与恢复说明</h2>
                <button class="close" id="backup-help-close">×</button>
            </div>
            <div class="help-body">
                <p><b>① 导出备份（配置 + 文档）</b>：生成 <code>.tar.gz</code> 完整快照，内含全部 Markdown 文档内容，以及配置文件（设置 / 文件夹 / 密码哈希 / 登录日志）。</p>
                <p><b>适用场景</b>：整机迁移、换设备、防灾容灾、需要把<b>文档内容</b>整体带走或恢复时使用。</p>
                <p><b>如何恢复</b>：把该包解压到新/原实例对应目录覆盖即可（配置在 etc，文档在各分区）。文档随包走，最完整。</p>
                <hr>
                <p><b>② 导出配置(JSON)</b>：仅导出设置项（不含文档内容），体积小、便于阅读与编辑。</p>
                <p><b>适用场景</b>：想把<b>偏好设置</b>（版本策略、自动保存间隔、代理/安全选项、网页标题与图标等）快速迁移到另一个 Vditor 实例，或单独备份设置时使用。</p>
                <p><b>如何恢复</b>：在目标实例「设置 → 导入配置(JSON)」上传该文件即可，<b>不会影响目标实例已有的文档</b>。</p>
                <hr>
                <p class="sub">一句话：要搬<b>文档</b>用①，要搬<b>设置</b>用②；两者互补，建议定期同时备份。</p>
            </div>
        </div>
    </div>

    <div class="toast" id="toast"></div>''')

# J) loadSettings: populate page title + apply appearance
rep(
'''            document.getElementById('set-autosave').value = autoSaveSec;
        }).catch(() => toast('读取设置失败'));''',
'''            document.getElementById('set-autosave').value = autoSaveSec;
            document.getElementById('set-page-title').value = SETTINGS_UI.page_title || '';
            applyAppearance();
        }).catch(() => toast('读取设置失败'));''')

# K) saveSettings: send page_title + apply
rep(
'''            max_versions: parseInt(document.getElementById('set-max-versions').value, 10) || 50,
            autosave_interval: parseInt(document.getElementById('set-autosave').value, 10) || 60,
        };''',
'''            max_versions: parseInt(document.getElementById('set-max-versions').value, 10) || 50,
            autosave_interval: parseInt(document.getElementById('set-autosave').value, 10) || 60,
            page_title: (document.getElementById('set-page-title').value || '').trim(),
        };''')
rep(
'''            SETTINGS_UI = d.settings || SETTINGS_UI;
            autoSaveSec = SETTINGS_UI.autosave_interval || 60;
            toast('设置已保存');''',
'''            SETTINGS_UI = d.settings || SETTINGS_UI;
            autoSaveSec = SETTINGS_UI.autosave_interval || 60;
            applyAppearance();
            toast('设置已保存');''')

# L) bindings
rep(
'''        document.getElementById('settings-save').addEventListener('click', saveSettings);''',
'''        document.getElementById('settings-save').addEventListener('click', saveSettings);
        document.getElementById('btn-upload-favicon').addEventListener('click', uploadFavicon);
        document.getElementById('btn-doc-info').addEventListener('click', openDocInfo);
        document.getElementById('doc-info-close').addEventListener('click', closeDocInfo);
        document.getElementById('doc-info-close2').addEventListener('click', closeDocInfo);
        document.getElementById('doc-info-delete').addEventListener('click', deleteCurrentDoc);
        document.getElementById('btn-backup-help').addEventListener('click', () => { document.getElementById('backup-help-mask').style.display = 'flex'; });
        document.getElementById('backup-help-close').addEventListener('click', () => { document.getElementById('backup-help-mask').style.display = 'none'; });''')

# M) new functions after hideConfirm
rep(
'''    function hideConfirm() {
        document.getElementById('confirm-mask').style.display = 'none';
        _confirmCb = null;
    }

    // ---------- 文件列表（多分区）----------''',
'''    function hideConfirm() {
        document.getElementById('confirm-mask').style.display = 'none';
        _confirmCb = null;
    }

    // ---------- 外观应用（标题 / 图标）----------
    function applyAppearance() {
        const t = (SETTINGS_UI.page_title || '').trim();
        if (t) document.title = t;
        const fav = (SETTINGS_UI.favicon || '').trim();
        let href = '/favicon.ico';
        if (/^https?:/i.test(fav)) href = fav;
        else if (fav === 'local') href = '/favicon.ico';
        let link = document.querySelector('link[rel~="icon"]');
        if (!link) { link = document.createElement('link'); link.rel = 'icon'; document.head.appendChild(link); }
        link.href = href;
    }
    function uploadFavicon() {
        const inp = document.getElementById('set-favicon');
        if (!inp.files || !inp.files[0]) { document.getElementById('favicon-err').textContent = '请先选择图片文件'; return; }
        document.getElementById('favicon-err').textContent = '';
        const fd = new FormData();
        fd.append('file', inp.files[0]);
        fetch('/api/favicon', { method: 'POST', body: fd })
            .then(r => r.json()).then(d => {
                if (!d.ok) { document.getElementById('favicon-err').textContent = '上传失败：' + (d.error || ''); return; }
                SETTINGS_UI.favicon = 'local';
                applyAppearance();
                toast('图标已上传并生效');
            }).catch(() => document.getElementById('favicon-err').textContent = '上传失败');
    }
    function openDocInfo() {
        if (!currentPath) { toast('请先打开一个文档'); return; }
        fetch('/api/doc/info?root=' + encodeURIComponent(currentRoot) + '&path=' + encodeURIComponent(currentPath))
            .then(r => r.json()).then(d => {
                if (d.error) { toast('获取信息失败：' + d.error); return; }
                if (!d.exists) { toast('文件不存在'); return; }
                document.getElementById('doc-info-path').textContent = '相对路径：' + d.path;
                document.getElementById('doc-info-abs').textContent = '绝对路径：' + d.abspath;
                const kb = (d.size / 1024).toFixed(2);
                const dt = new Date(d.mtime * 1000).toLocaleString();
                document.getElementById('doc-info-meta').textContent =
                    '大小：' + kb + ' KB　修改时间：' + dt + '　历史版本数：' + d.version_count;
                document.getElementById('doc-info-mask').style.display = 'flex';
            }).catch(() => toast('获取信息失败'));
    }
    function closeDocInfo() { document.getElementById('doc-info-mask').style.display = 'none'; }
    function deleteCurrentDoc() {
        showConfirm('删除文档', '确定删除「' + (currentPath || '') + '」及其全部历史版本吗？此操作不可恢复！', () => {
            fetch('/api/doc/delete', { method: 'POST', headers: {'Content-Type':'application/json'},
                body: JSON.stringify({ root: currentRoot, path: currentPath }) })
                .then(r => r.json()).then(d => {
                    if (!d.ok) { toast('删除失败：' + (d.error || '')); return; }
                    toast('已删除文档及其历史版本');
                    closeDocInfo();
                    if (currentPath) { currentPath = null; currentRoot = null; setCurName('未选择'); vditor.setValue('', false); }
                    refreshFiles();
                }).catch(() => toast('删除失败'));
        });
    }

    // ---------- 文件列表（多分区）----------''')

with open(SRC, "w", encoding="utf-8") as f:
    f.write(s)

print("OK index.html patched.")
for tok in ("btn-doc-info", "doc-info-mask", "backup-help-mask", "set-page-title", "applyAppearance",
           "uploadFavicon", "deleteCurrentDoc", 'id="btn-save">保存', 'rel="icon"', "已保存："):
    print(tok, "->", tok in s)
