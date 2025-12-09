# -*- coding: utf-8 -*-
"""
텔레그램 봇 메인 진입점
"""

import asyncio
import logging
import sys
import os

# 프로젝트 루트를 경로에 추가
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from config.telegram_config import TELEGRAM_BOT_TOKEN
from parsers.message_parser import MessageParser
from calculator.base_calculator import BaseCalculator
from utils.formatter import format_all_results

# 로깅 설정
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """봇 시작 명령어"""
    await update.message.reply_text(
        "안녕하세요! 담보대출 계산기 봇입니다.\n\n"
        "담보물건 정보를 입력해주시면 여러 금융사의 한도와 금리를 계산해드립니다.\n\n"
        "사용법: 담보물건 정보를 그대로 복사해서 보내주세요."
    )


async def calculate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """담보대출 계산 처리"""
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
        logger.error(f"계산 중 오류 발생: {e}", exc_info=True)
        await update.message.reply_text(
            f"계산 중 오류가 발생했습니다.\n\n"
            f"오류 내용: {str(e)}\n\n"
            f"메시지 형식을 확인해주세요."
        )


def main():
    """메인 함수"""
    if TELEGRAM_BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("⚠️  텔레그램 봇 토큰을 설정해주세요!")
        print("config/telegram_config.py 파일을 열어서 TELEGRAM_BOT_TOKEN을 입력하세요.")
        return
    
    # 텔레그램 봇 애플리케이션 생성
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # 핸들러 등록
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, calculate))
    
    # 봇 시작
    print("🤖 텔레그램 봇이 시작되었습니다...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

