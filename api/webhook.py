# -*- coding: utf-8 -*-
"""
Vercel 서버리스 함수 - 텔레그램 Webhook
"""

import json
import os
import sys

# 프로젝트 루트를 경로에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 전역 애플리케이션 인스턴스
application = None


async def get_application():
    """텔레그램 애플리케이션 인스턴스 가져오기 (싱글톤, async)"""
    global application

    if application is None:
        # 지연 import
        from telegram.ext import Application, MessageHandler, CommandHandler, filters
        from parsers.message_parser import MessageParser
        from calculator.base_calculator import BaseCalculator
        from utils.formatter import format_all_results

        # 로컬에서는 config/telegram_config.py, Vercel에서는 환경변수 사용
        try:
            from config.telegram_config import TELEGRAM_BOT_TOKEN  # type: ignore
        except ModuleNotFoundError:
            TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")

        application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

        # /start, /help 명령어 핸들러
        async def start_command(update, context):
            await update.message.reply_text(
                "안녕하세요! 담보대출 계산기 봇입니다.\n\n"
                "부동산 정보를 메시지로 보내주시면 여러 금융사의 대출 한도와 금리를 계산해드립니다."
            )

        # 메시지 핸들러
        async def handle_message(update, context):
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


# Vercel Python 함수 핸들러 (async)
async def handler(request):
    from telegram import Update

    if getattr(request, "method", "POST") != "POST":
        return {
            "statusCode": 405,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": "Method not allowed"})
        }

    try:
        body = await request.json()
    except Exception:
        body = {}

    try:
        app = await get_application()
        update = Update.de_json(body, app.bot)
        await app.process_update(update)

        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"ok": True})
        }
    except Exception as e:
        import traceback
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": str(e), "traceback": traceback.format_exc()})
        }


__all__ = ["handler"]

