# -*- coding: utf-8 -*-
"""
텔레그램 웹훅 설정 스크립트

Vercel HTTPS 웹훅만 허용합니다. 로컬/터널(ngrok, inkognit, SSH 등) URL은 거부합니다.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from urllib.parse import urlparse

# 프로젝트 루트를 경로에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _get_token() -> str:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        try:
            from config.telegram_config import TELEGRAM_BOT_TOKEN  # type: ignore

            token = TELEGRAM_BOT_TOKEN
        except Exception:
            token = None
    if not token or token == "YOUR_BOT_TOKEN_HERE":
        raise SystemExit(
            "TELEGRAM_BOT_TOKEN이 없습니다. 환경변수 또는 config/telegram_config.py를 설정하세요."
        )
    return token


def _telegram_api(token: str, method: str, payload: dict | None = None) -> dict:
    url = f"https://api.telegram.org/bot{token}/{method}"
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method="POST" if data else "GET")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        raise SystemExit(f"Telegram API 오류 HTTP {e.code}: {body}") from e


def validate_vercel_webhook_url(webhook_url: str) -> str:
    """Vercel 웹훅 URL만 허용. 터널/로컬은 거부."""
    if not webhook_url:
        raise ValueError("Webhook URL이 비어 있습니다.")

    parsed = urlparse(webhook_url.strip())
    host = (parsed.hostname or "").lower()
    path = (parsed.path or "").rstrip("/")

    if parsed.scheme != "https":
        raise ValueError("HTTPS만 허용합니다.")

    if parsed.port not in (None, 443):
        raise ValueError("비표준 포트는 허용하지 않습니다. (터널/SSH 차단)")

    blocked_markers = (
        "localhost",
        "127.0.0.1",
        "0.0.0.0",
        "ngrok",
        "inkognit",
        "localtunnel",
        "cloudflared",
        "trycloudflare",
        "serveo",
        "pagekite",
        "ssh.",
    )
    for marker in blocked_markers:
        if marker in host or marker in webhook_url.lower():
            raise ValueError(f"차단된 호스트/터널 패턴입니다: {marker}")

    if not (host == "vercel.app" or host.endswith(".vercel.app")):
        raise ValueError(
            "Vercel 도메인(*.vercel.app)만 허용합니다. "
            f"입력: {host or '(없음)'}"
        )

    if path != "/api/webhook":
        raise ValueError("경로는 /api/webhook 이어야 합니다.")

    return f"https://{host}/api/webhook"


def set_webhook(webhook_url: str) -> bool:
    token = _get_token()
    try:
        webhook_url = validate_vercel_webhook_url(webhook_url)
    except ValueError as e:
        print(f"[차단] {e}")
        print("허용 예: https://your-app.vercel.app/api/webhook")
        return False

    result = _telegram_api(token, "setWebhook", {"url": webhook_url})
    if result.get("ok"):
        print("[OK] 웹훅 설정 성공")
        print(f"     URL: {webhook_url}")
        check_webhook()
        return True

    print(f"[FAIL] 웹훅 설정 실패: {result}")
    return False


def delete_webhook(force: bool = False) -> bool:
    """웹훅 삭제는 로컬/터널 Polling으로 이어질 수 있어 기본 차단."""
    if not force:
        print("[차단] 웹훅 삭제는 비활성화되어 있습니다.")
        print("       로컬/터널 수신을 막기 위함입니다.")
        print("       정말 필요하면: python scripts/set_webhook.py --delete --force")
        return False

    token = _get_token()
    result = _telegram_api(token, "deleteWebhook", {})
    if result.get("ok"):
        print("[WARN] 웹훅이 삭제되었습니다. 텔레그램 수신이 끊길 수 있습니다.")
        return True
    print(f"[FAIL] 웹훅 삭제 실패: {result}")
    return False


def check_webhook() -> None:
    token = _get_token()
    result = _telegram_api(token, "getWebhookInfo")
    info = result.get("result") or {}
    url = info.get("url") or "(설정되지 않음)"
    print("[INFO] 현재 웹훅")
    print(f"       URL: {url}")
    print(f"       pending: {info.get('pending_update_count')}")
    if info.get("last_error_date"):
        print(f"       last_error: {info.get('last_error_message')}")

    if url and url != "(설정되지 않음)":
        try:
            validate_vercel_webhook_url(url)
            print("       status: Vercel 웹훅 OK")
        except ValueError as e:
            print(f"       status: [경고] Vercel이 아님 — {e}")
            print("       조치: python scripts/set_webhook.py https://<app>.vercel.app/api/webhook")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("사용법:")
        print("  웹훅 설정: python scripts/set_webhook.py https://<app>.vercel.app/api/webhook")
        print("  웹훅 확인: python scripts/set_webhook.py --check")
        print("  웹훅 삭제: python scripts/set_webhook.py --delete --force  (비권장)")
        sys.exit(1)

    command = sys.argv[1]
    if command == "--delete":
        delete_webhook(force="--force" in sys.argv[2:])
    elif command == "--check":
        check_webhook()
    else:
        set_webhook(command)
