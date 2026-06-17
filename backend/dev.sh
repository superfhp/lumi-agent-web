export CORS_ALLOW_ORIGIN="http://47.99.95.132:5173;http://47.99.95.132:8888"

# 向上游模型服务（Hermes Agent 等 OpenAI-compatible endpoint）透传 OpenWebUI 用户信息。
# OpenWebUI 本地历史记录依赖自己的 chats.user_id；Hermes 的 sessions.user_id
# 只有在上游收到并解析这些 header 时才会写入。
export ENABLE_FORWARD_USER_INFO_HEADERS="${ENABLE_FORWARD_USER_INFO_HEADERS:-true}"
export FORWARD_USER_INFO_HEADER_USER_ID="${FORWARD_USER_INFO_HEADER_USER_ID:-X-OpenWebUI-User-Id}"
export FORWARD_USER_INFO_HEADER_USER_NAME="${FORWARD_USER_INFO_HEADER_USER_NAME:-X-OpenWebUI-User-Name}"
export FORWARD_USER_INFO_HEADER_USER_EMAIL="${FORWARD_USER_INFO_HEADER_USER_EMAIL:-X-OpenWebUI-User-Email}"
export FORWARD_USER_INFO_HEADER_USER_ROLE="${FORWARD_USER_INFO_HEADER_USER_ROLE:-X-OpenWebUI-User-Role}"
export FORWARD_SESSION_INFO_HEADER_CHAT_ID="${FORWARD_SESSION_INFO_HEADER_CHAT_ID:-X-OpenWebUI-Chat-Id}"
export FORWARD_SESSION_INFO_HEADER_MESSAGE_ID="${FORWARD_SESSION_INFO_HEADER_MESSAGE_ID:-X-OpenWebUI-Message-Id}"

# 数据根目录（uploads/cache/vector_db/webui.db 都在它下面）
# 与 Hermes Agent 容器共享挂载点 /hpfu，方便 agent 直接读取上传文件
export DATA_DIR="${DATA_DIR:-/hpfu/openweb_hermes}"
mkdir -p "$DATA_DIR"

# 跳过文件解析/分块/embedding 全流程：
# 文件只落盘到 $DATA_DIR/uploads，秒回 completed
# 由 Hermes Agent 直接通过 file 工具按路径读取
export SKIP_FILE_PROCESSING="${SKIP_FILE_PROCESSING:-true}"
export BYPASS_EMBEDDING_AND_RETRIEVAL="${BYPASS_EMBEDDING_AND_RETRIEVAL:-true}"

# ────────────────────────────────────────────────────────────────────
# Langfuse LLM 观测（trace / generation / tool span）
#   在 OpenWebUI middleware 层统一上报所有中间过程到 Langfuse，
#   包括 LLM completions、tool calls、thinking/reasoning。
#   每条 chat 请求对应一条 Trace，session_id = chat_id。
# ────────────────────────────────────────────────────────────────────
export ENABLE_LANGFUSE="${ENABLE_LANGFUSE:-false}"
export LANGFUSE_SECRET_KEY="${LANGFUSE_SECRET_KEY:-}"
export LANGFUSE_PUBLIC_KEY="${LANGFUSE_PUBLIC_KEY:-}"
export LANGFUSE_HOST="${LANGFUSE_HOST:-https://cloud.langfuse.com}"

# ────────────────────────────────────────────────────────────────────
# WEBUI_SECRET_KEY：JWT / cookie 签名密钥
#   上游默认值是硬编码字符串 't0p-s3cr3t'（见 env.py），生产环境必须替换。
#   首次启动若未设置，则随机生成一份持久化到 $DATA_DIR/.webui_secret_key，
#   之后每次启动复用同一份；密钥变更后所有用户会被踢下线。
#
# 其他多账号开关（ENABLE_SIGNUP / DEFAULT_USER_ROLE 等）属于 PersistentConfig，
# 已写入 webui.db 的 config 表，请在管理员后台修改。
# ────────────────────────────────────────────────────────────────────

# 持久化 WEBUI_SECRET_KEY：首次启动随机生成并落到 $DATA_DIR/.webui_secret_key
# 之后每次启动复用同一份，避免重启后所有用户掉线。
if [ -z "${WEBUI_SECRET_KEY:-}" ]; then
    SECRET_KEY_FILE="$DATA_DIR/.webui_secret_key"
    if [ ! -f "$SECRET_KEY_FILE" ]; then
        # 优先用 openssl，退化到 /dev/urandom
        if command -v openssl >/dev/null 2>&1; then
            openssl rand -hex 48 > "$SECRET_KEY_FILE"
        else
            head -c 48 /dev/urandom | od -An -tx1 | tr -d ' \n' > "$SECRET_KEY_FILE"
        fi
        chmod 600 "$SECRET_KEY_FILE"
    fi
    export WEBUI_SECRET_KEY="$(cat "$SECRET_KEY_FILE")"
fi

PORT="${PORT:-8888}"
uvicorn open_webui.main:app --port $PORT --host 0.0.0.0 --forwarded-allow-ips "${FORWARDED_ALLOW_IPS:-*}" --reload
