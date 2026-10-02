#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v4.0.12：版本号统一升级（server.py * 2 + manifest + 测试断言），并写入 changelog。

注：按本项目既有教训 —— 涉及 server.py 的修改一律走「读-替换-写 + 断言计数」，
不用 Edit 工具（历史上曾报成功但未实改）。
"""
import io, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
OLD, NEW = "4.0.11", "4.0.12"

CHANGE_412 = (
    "4.0.12：登录页「忘记密码」提示改为指引在飞牛终端执行 vditor reset-password 一键重置密码"
    "（原需手动删除 pwhash 文件），并说明重启后回到首次设置页；"
    "修复「设置」保存成功提示被设置面板遮罩遮挡的问题（toast 层级提升至所有弹层之上）；"
    "安装向导「文档存储文件夹」不再预设路径、默认留空即使用默认目录，说明文案重写，"
    "明确自定义目录需在 fnOS 系统应用设置中允许本应用访问；"
    "卸载向导说明改为完整版，明确是否清除应用数据由本应用「设置→卸载清理」选项决定。"
)


def sub_once(path, old, new, expect_note=""):
    """精确替换一次并断言，失败立即退出。"""
    with io.open(path, encoding="utf-8") as f:
        src = f.read()
    # 先判断是否已是目标值（保证可重复执行），再做替换与计数断言
    if NEW != OLD and new in src:
        print("SKIP %s（已是目标值）" % os.path.basename(path))
        return
    cnt = src.count(old)
    if cnt != 1:
        raise SystemExit("FAIL %s: 待替换串出现 %d 次（应为 1）%s" % (path, cnt, expect_note))
    with io.open(path, "w", encoding="utf-8", newline="") as f:
        f.write(src.replace(old, new, 1))
    print("OK   %s: %s -> %s" % (os.path.basename(path), old, new))


# 1) 两处 server.py 的 APP_VERSION
for p in ("vditor-fpk/app/server.py", "vditor-nas/server.py"):
    sub_once(os.path.join(HERE, p), 'APP_VERSION = "%s"' % OLD, 'APP_VERSION = "%s"' % NEW)

# 2) manifest 版本号 + changelog
# 注意：源码 manifest 采用「无空格 + 单行」格式（version=4.0.11 / changelog=4.0.11：...），
# 打包后 fnpack 才会重新对齐并补 """，故此处必须按源码格式精确替换。
# changelog 各版本条目直接拼接、不可插入换行（否则多行会破坏 manifest 的 key=value 逐行解析）。
mf = os.path.join(HERE, "vditor-fpk", "manifest")
sub_once(mf, "version=%s" % OLD, "version=%s" % NEW)
sub_once(mf, "changelog=%s：" % OLD, "changelog=%s%s：" % (CHANGE_412, OLD))

# 3) 测试里的版本断言（两者都跑 vditor-nas，须同步）
for t in ("test_v406.py", "test_v407.py"):
    tp = os.path.join(HERE, t)
    with io.open(tp, encoding="utf-8") as f:
        s = f.read()
    if OLD in s:
        s = s.replace(OLD, NEW)
        with io.open(tp, "w", encoding="utf-8", newline="") as f:
            f.write(s)
        print("OK   %s: 版本断言 -> %s" % (t, NEW))
    else:
        print("SKIP %s（无 %s 断言）" % (t, OLD))

print("\nv4.0.12 版本升级完成")
