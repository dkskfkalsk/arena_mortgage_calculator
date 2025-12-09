# -*- coding: utf-8 -*-
"""
Vercel 서버리스 함수 - 텔레그램 Webhook
"""

import json
import os
import sys

# 프로젝트 루트를 경로에 추가
# Vercel 배포 구조에서는 /var/task가 프로젝트 루트이므로 한 단계만 올라간다.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes

# 로컬에서는 config/telegram_config.py를 사용하되,
# Vercel 배포 시에는 파일이 .gitignore로 제외되므로 환경변수를 바로 읽는다.
try:
    from config.telegram_config import TELEGRAM_BOT_TOKEN  # type: ignore
except ModuleNotFoundError:
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
from parsers.message_parser import MessageParser
from calculator.base_calculator import BaseCalculator
from utils.formatter import format_all_results


# 전역 애플리케이션 인스턴스
application = None


def get_application():
    """텔레그램 애플리케이션 인스턴스 가져오기 (싱글톤)"""
    global application
    if application is None:
        application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
        
        # /start, /help 명령어 핸들러
        async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
            await update.message.reply_text(
                "안녕하세요! 담보대출 계산기 봇입니다.\n\n"
                "부동산 정보를 메시지로 보내주시면 여러 금융사의 대출 한도와 금리를 계산해드립니다."
            )
        
        # 메시지 핸들러
        async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
            message_text = update.message.text
            
            if not message_text:
                await update.message.reply_text("메시지가 비어있습니다.")
                return
            
            try:
                # 메시지 파싱
                parser = MessageParser()
                property_data = parser.parse(message_text)
                
                # 계산 수행
                results = BaseCalculator.calculate_all_banks(property_data)
                
                # 결과 포맷팅
                formatted_result = format_all_results(results)
                
                # 결과 전송
                await update.message.reply_text(formatted_result)
                
            except Exception as e:
                await update.message.reply_text(
                    f"계산 중 오류가 발생했습니다.\n\n"
                    f"오류 내용: {str(e)}"
                )
        
        # 핸들러 등록
        application.add_handler(CommandHandler("start", start_command))
        application.add_handler(CommandHandler("help", start_command))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    return application


def index(request):
    """Vercel 서버리스 함수 핸들러 (index 함수 사용)"""
    import asyncio
    
    try:
        # Vercel Request 객체 처리
        # request는 dict 형식일 수 있음
        if isinstance(request, dict):
            method = request.get('method', 'POST')
            body = request.get('body', {})
            if isinstance(body, str):
                body = json.loads(body)
        else:
            # 객체인 경우
            method = getattr(request, 'method', 'POST')
            if hasattr(request, 'json'):
                body = request.json()
            elif hasattr(request, 'body'):
                body_str = request.body
                if isinstance(body_str, bytes):
                    body_str = body_str.decode('utf-8')
                body = json.loads(body_str) if body_str else {}
            else:
                body = {}
        
        if method != "POST":
            return {
                "statusCode": 405,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({"error": "Method not allowed"})
            }
        
        # Update 객체 생성
        update = Update.de_json(body, get_application().bot)
        
        # 비동기 처리
        asyncio.run(get_application().process_update(update))
        
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"ok": True})
        }
    except Exception as e:
        import traceback
        error_msg = str(e)
        traceback_str = traceback.format_exc()
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": error_msg, "traceback": traceback_str})
        }

