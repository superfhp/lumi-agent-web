export CORS_ALLOW_ORIGIN="http://47.99.95.132:5173;http://47.99.95.132:8888"

# 数据根目录（uploads/cache/vector_db/webui.db 都在它下面）
# 与 Hermes Agent 容器共享挂载点 /hpfu，方便 agent 直接读取上传文件
export DATA_DIR="${DATA_DIR:-/hpfu/openweb_hermes}"
mkdir -p "$DATA_DIR"

# 跳过文件解析/分块/embedding 全流程：
# 文件只落盘到 $DATA_DIR/uploads，秒回 completed
# 由 Hermes Agent 直接通过 file 工具按路径读取
export SKIP_FILE_PROCESSING="${SKIP_FILE_PROCESSING:-true}"
export BYPASS_EMBEDDING_AND_RETRIEVAL="${BYPASS_EMBEDDING_AND_RETRIEVAL:-true}"

PORT="${PORT:-8888}"
uvicorn open_webui.main:app --port $PORT --host 0.0.0.0 --forwarded-allow-ips "${FORWARDED_ALLOW_IPS:-*}" --reload
