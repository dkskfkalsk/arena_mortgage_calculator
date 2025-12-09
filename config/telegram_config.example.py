# -*- coding: utf-8 -*-
"""
텔레그램 봇 및 배포 설정 (예시 파일)
이 파일을 복사해서 telegram_config.py로 만들고 토큰을 입력하세요.

cp config/telegram_config.example.py config/telegram_config.py
"""

import os

# ============================================
# 텔레그램 봇 API 토큰 설정
# ============================================
# 방법 1: 환경변수 사용 (Vercel 배포 시 권장)
#   - Vercel 대시보드 → Settings → Environment Variables
#   - Key: TELEGRAM_BOT_TOKEN
#   - Value: @BotFather에서 발급받은 토큰
#
# 방법 2: 직접 입력 (로컬 실행 시)
#   - 아래 TELEGRAM_BOT_TOKEN에 직접 토큰 입력
#   - 주의: 이 파일을 Git에 커밋하지 마세요!

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")

# ============================================
# Vercel Webhook URL 설정
# ============================================
# Vercel 배포 후 자동으로 생성되는 Webhook URL
# 예: "https://your-app.vercel.app/api/webhook"
# 
# 설정 방법:
#   1. Vercel에 배포 후 생성된 URL 확인
#   2. Vercel 대시보드 → Settings → Environment Variables
#   3. Key: WEBHOOK_URL, Value: https://your-app.vercel.app/api/webhook
#   4. 또는 아래에 직접 입력 (로컬 테스트용)

WEBHOOK_URL = os.getenv("WEBHOOK_URL", None)

