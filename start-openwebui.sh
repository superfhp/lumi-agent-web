#!/usr/bin/env bash
set -euo pipefail

cd /opt/lumi-agent-web

# Path-prefix used by the Siflow route for this service. It is required both
# by the SvelteKit build and by the FastAPI prefix-stripping middleware.
export PUBLIC_BASE_PATH="${PUBLIC_BASE_PATH:-/siflow/auriga/skyinfer/xyli05/lumi-agent-web/v1/8888}"

# CORS：如果前后端同端口生产部署，通常 * 就够；也可以按实际域名收窄
export CORS_ALLOW_ORIGIN="${CORS_ALLOW_ORIGIN:-*}"

# 透传 OpenWebUI 用户信息给上游模型服务 / Hermes
export ENABLE_FORWARD_USER_INFO_HEADERS="${ENABLE_FORWARD_USER_INFO_HEADERS:-true}"
export FORWARD_USER_INFO_HEADER_USER_ID="${FORWARD_USER_INFO_HEADER_USER_ID:-X-OpenWebUI-User-Id}"
export FORWARD_USER_INFO_HEADER_USER_NAME="${FORWARD_USER_INFO_HEADER_USER_NAME:-X-OpenWebUI-User-Name}"
export FORWARD_USER_INFO_HEADER_USER_EMAIL="${FORWARD_USER_INFO_HEADER_USER_EMAIL:-X-OpenWebUI-User-Email}"
export FORWARD_USER_INFO_HEADER_USER_ROLE="${FORWARD_USER_INFO_HEADER_USER_ROLE:-X-OpenWebUI-User-Role}"
export FORWARD_SESSION_INFO_HEADER_CHAT_ID="${FORWARD_SESSION_INFO_HEADER_CHAT_ID:-X-OpenWebUI-Chat-Id}"
export FORWARD_SESSION_INFO_HEADER_MESSAGE_ID="${FORWARD_SESSION_INFO_HEADER_MESSAGE_ID:-X-OpenWebUI-Message-Id}"

# 持久化数据目录
export DATA_DIR="${DATA_DIR:-/hpfu/openweb_hermes}"
mkdir -p "$DATA_DIR"

# 上传文件只落盘，跳过解析/embedding
export SKIP_FILE_PROCESSING="${SKIP_FILE_PROCESSING:-true}"
export BYPASS_EMBEDDING_AND_RETRIEVAL="${BYPASS_EMBEDDING_AND_RETRIEVAL:-true}"

# Langfuse 默认关闭
export ENABLE_LANGFUSE="${ENABLE_LANGFUSE:-false}"
export LANGFUSE_SECRET_KEY="${LANGFUSE_SECRET_KEY:-}"
export LANGFUSE_PUBLIC_KEY="${LANGFUSE_PUBLIC_KEY:-}"
export LANGFUSE_HOST="${LANGFUSE_HOST:-https://cloud.langfuse.com}"

# WEBUI_SECRET_KEY 持久化，避免重启掉登录态
if [ -z "${WEBUI_SECRET_KEY:-}" ]; then
  SECRET_KEY_FILE="$DATA_DIR/.webui_secret_key"
  if [ ! -f "$SECRET_KEY_FILE" ]; then
    if command -v openssl >/dev/null 2>&1; then
      openssl rand -hex 48 > "$SECRET_KEY_FILE"
    else
      head -c 48 /dev/urandom | od -An -tx1 | tr -d ' \n' > "$SECRET_KEY_FILE"
    fi
    chmod 600 "$SECRET_KEY_FILE"
  fi
  export WEBUI_SECRET_KEY="$(cat "$SECRET_KEY_FILE")"
fi

# 前端 build 产物
export FRONTEND_BUILD_DIR="${FRONTEND_BUILD_DIR:-/opt/lumi-agent-web/build}"

PORT="${PORT:-8888}"

exec /opt/lumi-agent-web/.venv/bin/uvicorn open_webui.main:app \
  --app-dir /opt/lumi-agent-web/backend \
  --host 0.0.0.0 \
  --port "$PORT" \
  --forwarded-allow-ips "${FORWARDED_ALLOW_IPS:-*}"
