# -*- coding: utf-8 -*-
"""
텔레그램 웹훅 설정 스크립트
Vercel 배포 후 텔레그램에 웹훅 URL을 등록합니다.
"""

import sys
import os

# 프로젝트 루트를 경로에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from telegram import Bot
from config.telegram_config import TELEGRAM_BOT_TOKEN, WEBHOOK_URL


def set_webhook(webhook_url: str):
    """
    텔레그램에 웹훅 URL 등록
    
    Args:
        webhook_url: Vercel 배포 후 생성된 Webhook URL
                    예: "https://your-app.vercel.app/api/webhook"
    """
    if TELEGRAM_BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("❌ 텔레그램 봇 토큰을 먼저 설정해주세요!")
        print("config/telegram_config.py 파일에 TELEGRAM_BOT_TOKEN을 입력하세요.")
        return False
    
    if not webhook_url:
        print("❌ Webhook URL을 입력해주세요!")
        print("사용법: python scripts/set_webhook.py https://your-app.vercel.app/api/webhook")
        return False
    
    try:
        bot = Bot(token=TELEGRAM_BOT_TOKEN)
        result = bot.set_webhook(url=webhook_url)
        
        if result:
            print(f"✅ 웹훅 설정 성공!")
            print(f"   URL: {webhook_url}")
            
            # 웹훅 정보 확인
            webhook_info = bot.get_webhook_info()
            print(f"\n📋 웹훅 정보:")
            print(f"   URL: {webhook_info.url}")
            print(f"   보류 중인 업데이트: {webhook_info.pending_update_count}")
            
            return True
        else:
            print("❌ 웹훅 설정 실패")
            return False
            
    except Exception as e:
        print(f"❌ 오류 발생: {e}")
        return False


def delete_webhook():
    """웹훅 삭제 (로컬 Polling 방식으로 전환 시 사용)"""
    if TELEGRAM_BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("❌ 텔레그램 봇 토큰을 먼저 설정해주세요!")
        return False
    
    try:
        bot = Bot(token=TELEGRAM_BOT_TOKEN)
        result = bot.delete_webhook()
        
        if result:
            print("✅ 웹훅 삭제 성공!")
            print("   이제 로컬에서 Polling 방식으로 실행할 수 있습니다.")
            return True
        else:
            print("❌ 웹훅 삭제 실패")
            return False
            
    except Exception as e:
        print(f"❌ 오류 발생: {e}")
        return False


def check_webhook():
    """현재 웹훅 정보 확인"""
    if TELEGRAM_BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("❌ 텔레그램 봇 토큰을 먼저 설정해주세요!")
        return
    
    try:
        bot = Bot(token=TELEGRAM_BOT_TOKEN)
        webhook_info = bot.get_webhook_info()
        
        print("📋 현재 웹훅 정보:")
        print(f"   URL: {webhook_info.url or '(설정되지 않음)'}")
        print(f"   보류 중인 업데이트: {webhook_info.pending_update_count}")
        if webhook_info.last_error_date:
            print(f"   마지막 오류: {webhook_info.last_error_message}")
        
    except Exception as e:
        print(f"❌ 오류 발생: {e}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("📖 사용법:")
        print("   웹훅 설정: python scripts/set_webhook.py <webhook_url>")
        print("   웹훅 삭제: python scripts/set_webhook.py --delete")
        print("   웹훅 확인: python scripts/set_webhook.py --check")
        print("\n예시:")
        print("   python scripts/set_webhook.py https://your-app.vercel.app/api/webhook")
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == "--delete":
        delete_webhook()
    elif command == "--check":
        check_webhook()
    else:
        # 웹훅 URL로 인식
        set_webhook(command)

