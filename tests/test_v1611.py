#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (c) 2026 mian38
# SPDX-License-Identifier: MIT
"""1.6.1.1 专项测试：撤销栈污染修复 / 撤销滚动保留 / 密码显示按钮 / 强确认输入守卫。

静态断言 + 轻量 DOM 桩，不拉起真实服务；行为层由 CDP 实证覆盖（见 daily log）。
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IDX = os.path.join(ROOT, 'vditor-fpk', 'app', 'index.html')
html = io_open = open(IDX, encoding='utf-8').read()

passed = failed = 0
def check(name, cond, detail=''):
    global passed, failed
    if cond:
        passed += 1
        print('  PASS ', name)
    else:
        failed += 1
        print('  FAIL ', name, detail)

print('== 1.6.1.1 静态断言 ==')
code = re.search(r'<script>([\s\S]*?)</script>', html).group(1)

# 1) setContent 的 resetUndo 语义
check('setContent 支持 resetUndo 参数并传给 setValue',
      re.search(r'function setContent\(text, resetUndo\)', code) is not None
      and 'vditor.setValue(t, !!resetUndo)' in code)
check('打开/新建/删除/恢复/切模式等 6 处非编辑写入清空撤销栈',
      len(re.findall(r'setContent\([^)]*, true\)', code)) >= 6)
check('查找替换调用 setContent 不清栈（保留用户可撤销）',
      len(re.findall(r'setContent\(out\);', code)) == 2)

# 2) 撤销滚动保留
check('Undo 滚动保留：按键时间戳 + 编辑区宿主结构判定',
      'undoKeyDownAt = Date.now()' in code
      and 'const inEditorHost = function' in code
      and 'mu.removedNodes.length' in code)
check('撤销窗口 600ms 且恢复写回 scrollTop',
      'undoKeyDownAt > 600' in code and 'ed.scrollTop = target' in code)
check('打开新文档归零滚动记忆',
      re.search(r'const fill = \(\) => \{\s*resetUndoScroll\(\);', code) is not None)

# 3) 密码显示按钮
for pid in ['login-pw', 'setup-pw', 'setup-pw2']:
    m = re.search(r'<div class="pw-field">\s*<input id="%s"[^>]*type="password"[\s\S]{0,220}?id="%s-toggle"' % (pid, pid), html)
    check('%s 有显示/隐藏按钮且初始 type=password' % pid, m is not None)
check('三个密码切换按钮均挂 btn btn--ghost 变体',
      len(re.findall(r'class="btn btn--ghost pw-toggle"', html)) == 3)
check('切换逻辑含 aria-pressed / 显示隐藏文案 / 焦点回输入框',
      "btn.setAttribute('aria-pressed', show ? 'true' : 'false')" in code
      and "btn.textContent = show ? '隐藏' : '显示'" in code
      and 'input.focus()' in code)

# 4) 强确认输入守卫
check('强确认守卫拦截 paste/copy/cut/drop/dragover/contextmenu/dragstart',
      all(("'%s'" % t) in code for t in ['paste', 'copy', 'cut', 'drop', 'dragover', 'contextmenu', 'dragstart'])
      and "e.preventDefault()" in code)
check('beforeinput 仅放行逐字键入/输入法组合/删除',
      "t === 'insertText'" in code and "t === 'insertCompositionText'" in code
      and "if (!allowed) e.preventDefault()" in code)
check('组合键（Ctrl/Cmd/Alt）一律拦截',
      'if (e.ctrlKey || e.metaKey || e.altKey) e.preventDefault();' in code)
check('输入框提示明确「逐字手动输入 / 不支持粘贴拖入」',
      '请逐字手动输入文件名；不支持粘贴、拖入或快捷键填入' in html
      and 'BIGDOC_INPUT_HINT' in code)

print('\n结果: %d 通过, %d 失败' % (passed, failed))
sys.exit(0 if failed == 0 else 1)
