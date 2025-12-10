# -*- coding: utf-8 -*-
"""
Vercel 서버리스 함수 - 텔레그램 Webhook
Vercel Python 런타임에 맞춘 표준 함수 핸들러
"""

import json
import os
import sys
import asyncio

# 프로젝트 루트를 경로에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 전역 애플리케이션 인스턴스
application = None


def get_application():
    """텔레그램 애플리케이션 인스턴스 가져오기 (싱글톤)"""
    global application

    if application is None:
        from telegram.ext import Application, MessageHandler, CommandHandler, filters
        from parsers.message_parser import MessageParser
        from calculator.base_calculator import BaseCalculator
        from utils.formatter import format_all_results

        # 환경변수에서 토큰 가져오기 (Vercel에서는 환경변수 사용)
        TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
        if not TELEGRAM_BOT_TOKEN:
            # 로컬 테스트용 fallback
            try:
                from config.telegram_config import TELEGRAM_BOT_TOKEN  # type: ignore
            except ModuleNotFoundError:
                raise ValueError("TELEGRAM_BOT_TOKEN 환경변수를 설정해주세요.")

        application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

        async def start_command(update, context):
            await update.message.reply_text(
                "안녕하세요! 담보대출 계산기 봇입니다.\n\n"
                "부동산 정보를 메시지로 보내주시면 여러 금융사의 대출 한도와 금리를 계산해드립니다."
            )

        async def handle_message(update, context):
            message_text = update.message.text
            if not message_text:
                await update.message.reply_text("메시지가 비어있습니다.")
                return
            try:
                parser = MessageParser()
                property_data = parser.parse(message_text)
                results = BaseCalculator.calculate_all_banks(property_data)
                formatted_result = format_all_results(results)
                await update.message.reply_text(formatted_result)
            except Exception as e:
                await update.message.reply_text(
                    f"계산 중 오류가 발생했습니다.\n\n"
                    f"오류 내용: {str(e)}"
                )

        application.add_handler(CommandHandler("start", start_command))
        application.add_handler(CommandHandler("help", start_command))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    return application


def handler(req):
    """
    Vercel Python 서버리스 함수 핸들러
    텔레그램 웹훅 요청만 처리합니다.
    
    Args:
        req: Vercel Request 객체 (req.method, req.body 등)
        
    Returns:
        dict: Vercel Response 형식
    """
    # GET 요청은 헬스체크로 간주하고 즉시 반환
    if req.method == "GET":
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"ok": True, "message": "Webhook endpoint is active"})
        }
    
    # POST 요청만 처리 (텔레그램 웹훅)
    if req.method != "POST":
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"ok": True, "skipped": "not POST"})
        }
    
    # 요청 body 파싱
    try:
        # Vercel의 req.body는 문자열 또는 바이트
        body_str = req.body
        if isinstance(body_str, bytes):
            body_str = body_str.decode('utf-8')
        body = json.loads(body_str) if body_str else {}
    except (json.JSONDecodeError, AttributeError, TypeError):
        body = {}
    
    # 텔레그램 update 형식 검증 (update_id가 있어야 함)
    if not isinstance(body, dict) or "update_id" not in body:
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"ok": True, "skipped": "not telegram update"})
        }
    
    # 텔레그램 업데이트 처리
    try:
        from telegram import Update
        
        app = get_application()
        update = Update.de_json(body, app.bot)
        
        # 비동기 처리
        asyncio.run(app.process_update(update))
        
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"ok": True})
        }
    except Exception as e:
        import traceback
        error_msg = str(e)
        traceback_str = traceback.format_exc()
        
        # 오류 로깅 (Vercel 로그에 출력)
        print(f"Error processing update: {error_msg}")
        print(traceback_str)
        
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": error_msg})
        }


# Vercel이 찾는 핸들러 함수
__all__ = ["handler"]

