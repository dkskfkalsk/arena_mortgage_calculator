#!/usr/bin/env python3
"""
Render에서 PDF 웹훅 서버 실행용 스크립트.
- HTTP 서버를 띄워 요청이 올 때마다 api.webhook의 handler로 처리.
- Render Start Command: python run_webhook_render.py
- PORT는 Render가 설정하는 환경변수 사용 (기본 10000).
"""
import os
import sys
import signal

# 프로젝트 루트를 path에 추가
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from http.server import HTTPServer
from api.webhook import handler

_server = None


def _shutdown(signum=None, frame=None):
    if _server:
        print("[RENDER] Shutting down", file=sys.stderr, flush=True)
        _server.shutdown()


def main():
    global _server
    port = int(os.environ.get("PORT", 10000))
    _server = HTTPServer(("0.0.0.0", port), handler)
    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)
    print(f"[RENDER] Webhook server listening on 0.0.0.0:{port}", file=sys.stderr, flush=True)
    try:
        _server.serve_forever()
    finally:
        _server.server_close()
        print("[RENDER] Server process finished", file=sys.stderr, flush=True)


if __name__ == "__main__":
    main()
