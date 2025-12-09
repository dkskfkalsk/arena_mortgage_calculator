# -*- coding: utf-8 -*-
"""
Vercel 서버리스 함수 - 텔레그램 Webhook
"""

import json
import os
import sys

# 프로젝트 루트를 경로에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
from config.telegram_config import TELEGRAM_BOT_TOKEN
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
        
        # 핸들러 등록
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
        
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    return application


async def handler(request):
    """Vercel 서버리스 함수 핸들러"""
    if request.method == "POST":
        try:
            body = await request.json()
            update = Update.de_json(body, get_application().bot)
            
            await get_application().process_update(update)
            
            return {
                "statusCode": 200,
                "body": json.dumps({"ok": True})
            }
        except Exception as e:
            return {
                "statusCode": 500,
                "body": json.dumps({"error": str(e)})
            }
    else:
        return {
            "statusCode": 405,
            "body": json.dumps({"error": "Method not allowed"})
        }


# Vercel용 진입점 (Vercel은 자동으로 handler 함수를 찾습니다)
# 또는 명시적으로 export
__all__ = ["handler"]

