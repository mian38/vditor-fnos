#!/usr/bin/env bash
# -*- coding: utf-8 -*-
# Copyright (c) 2026 mian38
# SPDX-License-Identifier: MIT
#
# preflight.sh —— 多 agent 并行开发前的仓库安全自检
#
# 用法：
#   bash preflight.sh            # 仅检查，输出 GO/NO-GO（不改动任何东西）
#   bash preflight.sh --claim ID # 声明本 agent 独占（写 .workbuddy/agent_lock），若被他人占用则拒绝
#   bash preflight.sh --release ID # 释放本 agent 的锁
#
# 目的：在多个 WorkBuddy agent 并发改仓库前，快速确认
#   1) 当前分支；2) 工作区是否干净；3) 相对 main 是否落后（会冲突）；
#   4) 是否有其他 agent 已声明独占锁。据此避免并行改同一分支/同一文件导致冲突或资源竞争。
set -u

cd "$(dirname "$0")" || exit 1

LOCK_DIR=".workbuddy"
LOCK_FILE="$LOCK_DIR/agent_lock"
LOCK_TTL=1800   # 锁有效期（秒）：30 分钟，超时视为失效

is_fresh_lock() {
  [ -f "$LOCK_FILE" ] || return 1
  local now mtime age
  now=$(date +%s)
  mtime=$(stat -c %Y "$LOCK_FILE" 2>/dev/null || echo 0)
  age=$(( now - mtime ))
  [ "$age" -lt "$LOCK_TTL" ] || return 1
  return 0
}

cmd="${1:-check}"
owner="${2:-agent-$$}"

case "$cmd" in
  --claim)
    if is_fresh_lock; then
      existing=$(head -1 "$LOCK_FILE" 2>/dev/null)
      echo "NO-GO: 另一 agent 已声明独占锁（$existing），请等待其释放或改用独立分支"
      exit 1
    fi
    mkdir -p "$LOCK_DIR"
    printf '%s\n%s\n' "$owner" "$(date '+%Y-%m-%d %H:%M:%S')" > "$LOCK_FILE"
    echo "OK: 已声明独占锁（$owner）。完成后请运行 bash preflight.sh --release $owner"
    exit 0
    ;;
  --release)
    if [ ! -f "$LOCK_FILE" ]; then
      echo "OK: 无锁可释放"
      exit 0
    fi
    existing=$(head -1 "$LOCK_FILE" 2>/dev/null)
    if [ -n "$2" ] && [ "$existing" != "$2" ]; then
      echo "SKIP: 锁属于 $existing，非 $2，不释放"
      exit 1
    fi
    rm -f "$LOCK_FILE"
    echo "OK: 已释放锁（原属 $existing）"
    exit 0
    ;;
esac

# ---- 默认：只读检查 ----
ok=1
echo "==== preflight: 仓库并行安全自检 ===="

branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "(unknown)")
echo "[分支] $branch"

dirty=$(git status --porcelain 2>/dev/null)
if [ -z "$dirty" ]; then
  echo "[状态] 工作区干净 ✓"
else
  echo "[状态] 工作区有未提交改动 ✗"
  echo "$dirty" | sed 's/^/    /'
  ok=0
fi

if [ "$branch" = "main" ]; then
  echo "[主线] 当前在 main —— 多 agent 并发改 main 高风险，建议切到 feat/fix 分支 ⚠"
else
  echo "[主线] 不在 main（符合短期分支规范）✓"
fi

if git rev-parse --verify main >/dev/null 2>&1; then
  behind=$(git rev-list --count HEAD..main 2>/dev/null || echo 0)
  ahead=$(git rev-list --count main..HEAD 2>/dev/null || echo 0)
  echo "[差异] 领先 main $ahead / 落后 main $behind"
  if [ "$behind" -gt 0 ]; then
    echo "[分歧] 本地落后 main，先 rebase/pull 再改 ✗"
    ok=0
  fi
fi

if git remote | grep -q .; then
  if git rev-parse --verify '@{upstream}' >/dev/null 2>&1; then
    lr=$(git rev-list --left-right --count HEAD...'@{upstream}' 2>/dev/null || echo "0	0")
    echo "[远程] 左/右分歧: $lr"
  fi
else
  echo "[远程] 无远程（本地仓库）—— 仅依赖分支纪律避免并行冲突"
fi

if is_fresh_lock; then
  existing=$(head -1 "$LOCK_FILE" 2>/dev/null)
  echo "[锁] 存在其他 agent 的独占锁（$existing）⚠ 并发改动有冲突风险"
  ok=0
else
  echo "[锁] 无有效独占锁 ✓"
fi

echo "======================================"
if [ "$ok" -eq 1 ]; then
  echo "GO: 可以安全开始改动（仍建议独立 feat/fix 分支）"
  exit 0
else
  echo "NO-GO: 存在上述风险，先处理后再开始并行改动"
  exit 1
fi
