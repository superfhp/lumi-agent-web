export CORS_ALLOW_ORIGIN="http://47.99.95.132:5173;http://47.99.95.132:8888"
PORT="${PORT:-8888}"
uvicorn open_webui.main:app --port $PORT --host 0.0.0.0 --forwarded-allow-ips "${FORWARDED_ALLOW_IPS:-*}" --reload
