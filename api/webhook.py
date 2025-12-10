# -*- coding: utf-8 -*-
"""
Vercel 서버리스 함수 - 텔레그램 Webhook
"""

import json
import os
import sys
import asyncio
from http.server import BaseHTTPRequestHandler

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

        # 허용된 채팅방 ID 가져오기
        ALLOWED_CHAT_IDS_STR = os.getenv("ALLOWED_CHAT_IDS")
        if not ALLOWED_CHAT_IDS_STR:
            try:
                from config.telegram_config import ALLOWED_CHAT_IDS  # type: ignore
                ALLOWED_CHAT_IDS_STR = ALLOWED_CHAT_IDS
            except (ModuleNotFoundError, ImportError):
                ALLOWED_CHAT_IDS_STR = None
        
        # 허용된 채팅방 ID 리스트로 변환 (쉼표로 구분된 문자열을 리스트로)
        allowed_chat_ids = []
        if ALLOWED_CHAT_IDS_STR:
            allowed_chat_ids = [int(chat_id.strip()) for chat_id in ALLOWED_CHAT_IDS_STR.split(",") if chat_id.strip()]
        
        print(f"DEBUG: Application initialized - ALLOWED_CHAT_IDS_STR: {ALLOWED_CHAT_IDS_STR}, allowed_chat_ids: {allowed_chat_ids}")

        application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

        def get_chat_id(update):
            """업데이트에서 채팅방 ID 가져오기"""
            if update.message:
                return update.message.chat.id
            elif update.edited_message:
                return update.edited_message.chat.id
            elif update.channel_post:
                return update.channel_post.chat.id
            elif update.edited_channel_post:
                return update.edited_channel_post.chat.id
            return None

        def is_allowed_chat(chat_id):
            """채팅방이 허용된 목록에 있는지 확인"""
            if chat_id is None:
                return False
            if not allowed_chat_ids:  # 허용 목록이 비어있으면 모든 채팅방 허용
                return True
            return chat_id in allowed_chat_ids

        async def start_command(update, context):
            # 메시지가 없으면 무시
            if not update.message:
                print("DEBUG: start_command - update.message is None")
                return
            
            # 채팅방 ID 확인
            chat_id = get_chat_id(update)
            print(f"DEBUG: start_command - chat_id: {chat_id}, allowed_chat_ids: {allowed_chat_ids}")
            if not is_allowed_chat(chat_id):
                # 허용되지 않은 채팅방에서는 조용히 무시
                print(f"DEBUG: start_command - Chat {chat_id} is not allowed")
                return
            print(f"DEBUG: start_command - Processing command for chat {chat_id}")
            
            welcome_message = (
                "🏠 담보대출 계산기 봇에 오신 것을 환영합니다!\n\n"
                "이 봇은 여러 금융사의 담보대출 한도와 금리를 계산해드립니다.\n\n"
                "📝 사용 방법:\n"
                "담보물건 정보를 메시지로 보내주시면 자동으로 계산해드립니다.\n\n"
                "💡 입력 예시:\n"
                "• 담보물건 주소: 서울특별시 강남구\n"
                "• KB시세: 5억원\n"
                "• 신용점수: 750점\n"
                "• 나이: 35세\n\n"
                "또는 실제 담보물건 정보를 그대로 복사해서 보내주셔도 됩니다.\n\n"
                "🔍 명령어:\n"
                "/start - 이 도움말 보기\n"
                "/help - 도움말 보기\n\n"
                "이제 담보물건 정보를 보내주시면 계산해드리겠습니다! 🚀"
            )
            await update.message.reply_text(welcome_message)

        async def handle_message(update, context):
            # 메시지가 없으면 무시
            if not update.message:
                print("DEBUG: handle_message - update.message is None")
                return
            
            # 채팅방 ID 확인
            chat_id = get_chat_id(update)
            print(f"DEBUG: handle_message - chat_id: {chat_id}, allowed_chat_ids: {allowed_chat_ids}")
            if not is_allowed_chat(chat_id):
                # 허용되지 않은 채팅방에서는 조용히 무시
                print(f"DEBUG: handle_message - Chat {chat_id} is not allowed")
                return
            print(f"DEBUG: handle_message - Processing message for chat {chat_id}")
            
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


class handler(BaseHTTPRequestHandler):
    """
    Vercel Python 서버리스 함수 핸들러
    BaseHTTPRequestHandler를 상속하여 텔레그램 웹훅 요청만 처리합니다.
    """
    
    def _send_response(self, status_code, data):
        """응답 전송 헬퍼 메서드"""
        body = json.dumps(data).encode('utf-8')
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    
    def do_GET(self):
        """GET 요청 처리 (헬스체크)"""
        self._send_response(200, {"ok": True, "message": "Webhook endpoint is active"})
    
    def do_POST(self):
        """POST 요청 처리 (텔레그램 웹훅)"""
        try:
            # 요청 body 읽기
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length == 0:
                self._send_response(200, {"ok": True, "skipped": "empty body"})
                return
            
            body_bytes = self.rfile.read(content_length)
            body_str = body_bytes.decode('utf-8')
            body = json.loads(body_str) if body_str else {}
            
            # 텔레그램 update 형식 검증 (update_id가 있어야 함)
            if not isinstance(body, dict) or "update_id" not in body:
                self._send_response(200, {"ok": True, "skipped": "not telegram update"})
                return
            
            # 텔레그램 업데이트 처리
            from telegram import Update
            
            app = get_application()
            update = Update.de_json(body, app.bot)
            
            # 업데이트 정보 로깅
            if update.message:
                print(f"DEBUG: Received update - message.chat.id: {update.message.chat.id}, message.text: {update.message.text[:50] if update.message.text else None}")
            else:
                print(f"DEBUG: Received update - no message (update type: {type(update)})")
            
            # 비동기 처리 (Application 초기화 포함)
            async def process():
                # 초기화되지 않았으면 초기화
                if not app._initialized:
                    await app.initialize()
                await app.process_update(update)
            
            asyncio.run(process())
            
            self._send_response(200, {"ok": True})
            
        except json.JSONDecodeError:
            self._send_response(200, {"ok": True, "skipped": "invalid JSON"})
        except Exception as e:
            import traceback
            error_msg = str(e)
            traceback_str = traceback.format_exc()
            
            # 오류 로깅 (Vercel 로그에 출력)
            print(f"Error processing update: {error_msg}")
            print(traceback_str)
            
            self._send_response(500, {"error": error_msg})
    
    def log_message(self, format, *args):
        """로그 메시지 출력 (Vercel 로그에 출력)"""
        print(f"{self.address_string()} - {format % args}")

