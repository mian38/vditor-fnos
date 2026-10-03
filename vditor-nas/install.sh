#!/usr/bin/env bash
# Vditor NAS 安装脚本（飞牛 FnOS / 任意 systemd Linux，无需 Docker）
# 用法:
#   sudo bash install.sh                 # 默认装到 /opt/vditor-nas，交互输入端口
#   sudo bash install.sh /opt/vditor-nas 3838   # 指定目录与端口
set -e

SRC="$(cd "$(dirname "$0")" && pwd)"
INSTALL_DIR="${1:-/opt/vditor-nas}"
PORT_ARG="${2:-}"

echo "源目录   : $SRC"
echo "安装目录 : $INSTALL_DIR"

# 1. 复制文件
mkdir -p "$INSTALL_DIR"
cp -r "$SRC/." "$INSTALL_DIR/"
mkdir -p "$INSTALL_DIR/uploads"
chmod -R a+rX "$INSTALL_DIR"
chmod +x "$INSTALL_DIR/server.py" 2>/dev/null || true

# 2. 端口配置
if [ -n "$PORT_ARG" ]; then
  sed -i "s/^PORT=.*/PORT=$PORT_ARG/" "$INSTALL_DIR/config.env"
else
  CUR=$(grep '^PORT=' "$INSTALL_DIR/config.env" | cut -d= -f2)
  read -r -p "请输入浏览器访问端口 [默认 $CUR]: " INPUT
  if [ -n "$INPUT" ]; then
    sed -i "s/^PORT=.*/PORT=$INPUT/" "$INSTALL_DIR/config.env"
  fi
fi
PORT=$(grep '^PORT=' "$INSTALL_DIR/config.env" | cut -d= -f2)

# 3. 检查 python3
PY="$(command -v python3 || true)"
if [ -z "$PY" ]; then
  echo "错误：未找到 python3，请先安装 Python 3.8+ 后再运行本脚本。" >&2
  exit 1
fi
echo "使用 Python: $PY"

# 4. 注册并启动服务
if [ -d /run/systemd/system ]; then
  UNIT=/etc/systemd/system/vditor-nas.service
  cat > "$UNIT" <<EOF
[Unit]
Description=Vditor NAS Markdown Editor
After=network.target

[Service]
Type=simple
WorkingDirectory=$INSTALL_DIR
ExecStart=$PY $INSTALL_DIR/server.py
Restart=on-failure
RestartSec=5
User=root

[Install]
WantedBy=multi-user.target
EOF
  systemctl daemon-reload
  systemctl enable vditor-nas
  systemctl restart vditor-nas
  sleep 1
  echo "---- systemd 服务状态 ----"
  systemctl status vditor-nas --no-pager || true
else
  echo "未检测到 systemd，使用 nohup 后台启动"
  nohup "$PY" "$INSTALL_DIR/server.py" >/var/log/vditor-nas.log 2>&1 &
  echo "已后台启动，日志: /var/log/vditor-nas.log"
fi

IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
echo "=================================================="
echo " 安装完成！"
echo " 本机访问 : http://127.0.0.1:$PORT"
echo " 局域网   : http://${IP:-<NAS的IP>}:$PORT"
echo " 注意     : 若无法访问，请在飞牛『设置→安全/防火墙』中放行端口 $PORT"
echo " 卸载     : sudo bash $INSTALL_DIR/uninstall.sh"
echo "=================================================="
