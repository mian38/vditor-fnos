#!/usr/bin/env bash
# Vditor NAS 卸载脚本
set -e
INSTALL_DIR="${1:-/opt/vditor-nas}"

# 停止 systemd 服务
if [ -f /etc/systemd/system/vditor-nas.service ]; then
  systemctl stop vditor-nas 2>/dev/null || true
  systemctl disable vditor-nas 2>/dev/null || true
  rm -f /etc/systemd/system/vditor-nas.service
  systemctl daemon-reload
  echo "已停止并移除 systemd 服务"
fi

# 停止可能残留的后台进程
pkill -f "$INSTALL_DIR/server.py" 2>/dev/null || true
pkill -f "server.py" 2>/dev/null || true

# 删除安装目录（含已上传文件，谨慎）
rm -rf "$INSTALL_DIR"
echo "已卸载，安装目录 $INSTALL_DIR 已删除"
