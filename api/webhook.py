# -*- coding: utf-8 -*-
"""
Vercel 서버리스 함수 - 텔레그램 Webhook
"""

# 가장 먼저 실행되는 로그 (모듈 임포트 시 즉시 실행)
import sys
sys.stderr.write("=" * 80 + "\n")
sys.stderr.write("WEBHOOK.PY FILE LOADED - MODULE IMPORT STARTED\n")
sys.stderr.write("=" * 80 + "\n")
sys.stderr.flush()

import json
import os
import asyncio
import logging
from http.server import BaseHTTPRequestHandler

# 프로젝트 루트를 경로에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stderr)]
)
logger = logging.getLogger(__name__)

# 모듈 로드 시 로그 출력 (여러 방법으로 확실하게)
sys.stderr.write("[WEBHOOK] Module loaded - stderr write\n")
sys.stderr.flush()
print("=" * 60, file=sys.stderr, flush=True)
print("[WEBHOOK] Module loaded - print to stderr", file=sys.stderr, flush=True)
logger.info("Webhook module initialized")

# 전역 애플리케이션 인스턴스
application = None

# 전역 이벤트 루프
_global_loop = None


def get_application():
    """텔레그램 애플리케이션 인스턴스 가져오기 (싱글톤)"""
    global application

    if application is None:
        from telegram.ext import (
            Application, MessageHandler, CommandHandler, filters
        )
        from parsers.message_parser import MessageParser
        from calculator.base_calculator import BaseCalculator
        from utils.formatter import format_all_results

        # 환경변수에서 토큰 가져오기
        TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
        if not TELEGRAM_BOT_TOKEN:
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
        
        # 허용된 채팅방 ID 리스트로 변환
        allowed_chat_ids = []
        if ALLOWED_CHAT_IDS_STR:
            allowed_chat_ids = [int(chat_id.strip()) for chat_id in ALLOWED_CHAT_IDS_STR.split(",") if chat_id.strip()]
        
        print(f"[WEBHOOK] Application initializing - allowed_chat_ids: {allowed_chat_ids}", file=sys.stderr, flush=True)
        logger.info(f"Application initialized - allowed_chat_ids: {allowed_chat_ids}")

        application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
        print("[WEBHOOK] Application initialized successfully", file=sys.stderr, flush=True)

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
            message = update.message or update.channel_post or update.edited_message or update.edited_channel_post
            if not message:
                return
            
            chat_id = get_chat_id(update)
            print(f"[WEBHOOK] start_command - chat_id: {chat_id}", file=sys.stderr, flush=True)
            logger.info(f"start_command - chat_id: {chat_id}")
            
            if not is_allowed_chat(chat_id):
                print(f"[WEBHOOK] start_command - Chat {chat_id} is NOT allowed", file=sys.stderr, flush=True)
                logger.warning(f"start_command - Chat {chat_id} is not allowed")
                return
            
            print(f"[WEBHOOK] start_command - Chat {chat_id} is allowed", file=sys.stderr, flush=True)
            
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
            try:
                await message.reply_text(welcome_message)
            except Exception as e:
                logger.error(f"Error sending welcome message: {str(e)}", exc_info=True)

        async def handle_message(update, context=None):
            message = update.message or update.channel_post or update.edited_message or update.edited_channel_post
            
            if not message:
                print("[WEBHOOK] handle_message - No message found", file=sys.stderr, flush=True)
                logger.warning("handle_message - No message found in update")
                return
            
            chat_id = get_chat_id(update)
            print(f"[WEBHOOK] handle_message - chat_id: {chat_id}", file=sys.stderr, flush=True)
            logger.info(f"handle_message - chat_id: {chat_id}")
            
            if not is_allowed_chat(chat_id):
                print(f"[WEBHOOK] handle_message - Chat {chat_id} is NOT allowed", file=sys.stderr, flush=True)
                logger.warning(f"handle_message - Chat {chat_id} is not allowed")
                return
            
            print(f"[WEBHOOK] handle_message - Chat {chat_id} is allowed, processing", file=sys.stderr, flush=True)
            
            message_text = message.text
            if not message_text:
                logger.info("handle_message - No text in message")
                await message.reply_text(
                    "텍스트 메시지를 보내주세요.\n\n"
                    "담보물건 정보를 텍스트로 입력해주시면 계산해드립니다.\n\n"
                    "/start 명령어로 사용 방법을 확인하실 수 있습니다."
                )
                return
            
            try:
                print(f"[WEBHOOK] Parsing message text...", file=sys.stderr, flush=True)
                parser = MessageParser()
                property_data = parser.parse(message_text)
                print(f"[WEBHOOK] Parsed - kb_price: {property_data.get('kb_price')}", file=sys.stderr, flush=True)
                logger.info(f"handle_message - property_data parsed: kb_price={property_data.get('kb_price')}")
                
                print("[WEBHOOK] Calculating results...", file=sys.stderr, flush=True)
                results = BaseCalculator.calculate_all_banks(property_data)
                print(f"[WEBHOOK] Results count: {len(results) if results else 0}", file=sys.stderr, flush=True)
                logger.info(f"handle_message - results count: {len(results) if results else 0}")
                
                formatted_result = format_all_results(results)
                print("[WEBHOOK] Sending reply message...", file=sys.stderr, flush=True)
                await message.reply_text(formatted_result)
                print("[WEBHOOK] Message sent successfully!", file=sys.stderr, flush=True)
                logger.info("handle_message - Message sent successfully")
                
            except Exception as e:
                print(f"[WEBHOOK] Error in handle_message: {str(e)}", file=sys.stderr, flush=True)
                logger.error(f"Error in handle_message: {str(e)}", exc_info=True)
                try:
                    await message.reply_text(
                        f"계산 중 오류가 발생했습니다.\n\n"
                        f"오류 내용: {str(e)}"
                    )
                except Exception as reply_error:
                    logger.error(f"Failed to send error message: {str(reply_error)}", exc_info=True)

        # 핸들러 등록
        application.add_handler(CommandHandler("start", start_command))
        application.add_handler(CommandHandler("help", start_command))
        application.add_handler(MessageHandler(~filters.COMMAND, handle_message))
        
        # handle_message를 전역에서 접근 가능하도록 저장
        application._handle_message = handle_message

    return application


class handler(BaseHTTPRequestHandler):
    """Vercel Python 서버리스 함수 핸들러"""
    
    def __init__(self, *args, **kwargs):
        # 핸들러 초기화 시 즉시 로그 출력
        sys.stderr.write("[HANDLER] Handler class initialized\n")
        sys.stderr.flush()
        print("[HANDLER] Handler __init__ called", file=sys.stderr, flush=True)
        logger.info("Handler initialized")
        super().__init__(*args, **kwargs)
    
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
        # 여러 방법으로 로그 출력
        sys.stderr.write("[WEBHOOK] GET request received - stderr write\n")
        sys.stderr.flush()
        print("=" * 60, file=sys.stderr, flush=True)
        print("[WEBHOOK] GET request received - print to stderr", file=sys.stderr, flush=True)
        logger.info("GET request - Health check")
        self._send_response(200, {"ok": True, "message": "Webhook endpoint is active"})
    
    def do_POST(self):
        """POST 요청 처리 (텔레그램 웹훅)"""
        # 여러 방법으로 로그 출력
        sys.stderr.write("[WEBHOOK] POST request received - stderr write\n")
        sys.stderr.flush()
        print("=" * 60, file=sys.stderr, flush=True)
        print("[WEBHOOK] POST request received - print to stderr", file=sys.stderr, flush=True)
        logger.info("POST request received")
        
        try:
            # 요청 body 읽기
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length == 0:
                print("[WEBHOOK] Empty body, skipping", file=sys.stderr, flush=True)
                self._send_response(200, {"ok": True, "skipped": "empty body"})
                return

            body_bytes = self.rfile.read(content_length)
            body_str = body_bytes.decode('utf-8')
            body = json.loads(body_str) if body_str else {}

            # 텔레그램 update 형식 검증
            if not isinstance(body, dict) or "update_id" not in body:
                print("[WEBHOOK] Not a telegram update, skipping", file=sys.stderr, flush=True)
                logger.warning("Not a telegram update, skipping")
                self._send_response(200, {"ok": True, "skipped": "not telegram update"})
                return

            # 텔레그램 업데이트 처리
            print("[WEBHOOK] Processing telegram update...", file=sys.stderr, flush=True)
            from telegram import Update
            app = get_application()
            update = Update.de_json(body, app.bot)
            print(f"[WEBHOOK] Update ID: {update.update_id}", file=sys.stderr, flush=True)
            logger.info(f"Received update - update_id: {update.update_id}")

            # 메시지가 없는 경우 무시
            if not update.message and not update.edited_message and not update.channel_post and not update.edited_channel_post:
                print("[WEBHOOK] No message found, skipping", file=sys.stderr, flush=True)
                logger.warning("No message found, skipping")
                self._send_response(200, {"ok": True, "skipped": "no message"})
                return

            # 채팅방 ID 확인
            def get_chat_id_from_update(update):
                if update.message:
                    return update.message.chat.id
                elif update.edited_message:
                    return update.edited_message.chat.id
                elif update.channel_post:
                    return update.channel_post.chat.id
                elif update.edited_channel_post:
                    return update.edited_channel_post.chat.id
                return None

            chat_id = get_chat_id_from_update(update)
            print(f"[WEBHOOK] Chat ID: {chat_id}", file=sys.stderr, flush=True)

            # 허용된 채팅방 ID 확인
            ALLOWED_CHAT_IDS_STR = os.getenv("ALLOWED_CHAT_IDS")
            if not ALLOWED_CHAT_IDS_STR:
                try:
                    from config.telegram_config import ALLOWED_CHAT_IDS  # type: ignore
                    ALLOWED_CHAT_IDS_STR = ALLOWED_CHAT_IDS
                except (ModuleNotFoundError, ImportError):
                    ALLOWED_CHAT_IDS_STR = None

            allowed_chat_ids = []
            if ALLOWED_CHAT_IDS_STR:
                allowed_chat_ids = [int(chat_id.strip()) for chat_id in ALLOWED_CHAT_IDS_STR.split(",") if chat_id.strip()]

            print(f"[WEBHOOK] Allowed chat IDs: {allowed_chat_ids}", file=sys.stderr, flush=True)
            logger.info(f"chat_id: {chat_id}, allowed_chat_ids: {allowed_chat_ids}")

            # 허용된 채팅방이 설정되어 있고, 현재 채팅방이 허용 목록에 없으면 무시
            if allowed_chat_ids and chat_id not in allowed_chat_ids:
                print(f"[WEBHOOK] Chat {chat_id} is NOT in allowed list, ignoring", file=sys.stderr, flush=True)
                logger.warning(f"Chat {chat_id} is not in allowed list, ignoring update")
                self._send_response(200, {"ok": True, "skipped": "chat not allowed"})
                return

            print(f"[WEBHOOK] Chat {chat_id} is allowed, processing message", file=sys.stderr, flush=True)

            # 비동기 처리 함수
            async def process():
                try:
                    print("[WEBHOOK] Starting async process", file=sys.stderr, flush=True)
                    
                    # 초기화되지 않았으면 초기화
                    if not app._initialized:
                        print("[WEBHOOK] Initializing application", file=sys.stderr, flush=True)
                        await app.initialize()
                    
                    # channel_post, edited_message, edited_channel_post는 직접 처리
                    if update.channel_post or update.edited_message or update.edited_channel_post:
                        print("[WEBHOOK] Processing channel_post/edited_message directly", file=sys.stderr, flush=True)
                        if hasattr(app, '_handle_message'):
                            await app._handle_message(update, None)
                        else:
                            logger.warning("_handle_message not found, using process_update")
                            await app.process_update(update)
                    else:
                        # 일반 메시지는 process_update로 처리
                        print("[WEBHOOK] Processing regular message with process_update", file=sys.stderr, flush=True)
                        await app.process_update(update)
                    
                    print("[WEBHOOK] Message processing completed", file=sys.stderr, flush=True)
                    logger.info("Message processing completed")
                    
                except Exception as e:
                    print(f"[WEBHOOK] Error in process(): {str(e)}", file=sys.stderr, flush=True)
                    logger.error(f"Error in process(): {str(e)}", exc_info=True)
                    import traceback
                    traceback.print_exc()

            # 이벤트 루프 실행
            global _global_loop
            
            try:
                # 기존 루프 확인
                try:
                    loop = asyncio.get_running_loop()
                    print("[WEBHOOK] Event loop already running, using thread", file=sys.stderr, flush=True)
                    logger.info("Event loop already running, using thread")
                    import threading
                    
                    def run_in_new_thread():
                        global _global_loop
                        try:
                            if _global_loop is None or _global_loop.is_closed():
                                new_loop = asyncio.new_event_loop()
                                asyncio.set_event_loop(new_loop)
                            else:
                                new_loop = _global_loop
                                asyncio.set_event_loop(new_loop)
                            
                            new_loop.run_until_complete(process())
                            
                            if not new_loop.is_closed():
                                _global_loop = new_loop
                        except Exception as e:
                            print(f"[WEBHOOK] Thread error: {str(e)}", file=sys.stderr, flush=True)
                            logger.error(f"Thread error: {str(e)}", exc_info=True)
                    
                    thread = threading.Thread(target=run_in_new_thread, daemon=False)
                    thread.start()
                    thread.join(timeout=25)
                    
                    if thread.is_alive():
                        print("[WEBHOOK] Thread timeout", file=sys.stderr, flush=True)
                        logger.error("Thread timeout after 25 seconds")
                        
                except RuntimeError:
                    print("[WEBHOOK] No running loop, creating new one", file=sys.stderr, flush=True)
                    logger.info("No running loop, creating new one")
                    
                    if _global_loop is None or _global_loop.is_closed():
                        _global_loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(_global_loop)
                    
                    try:
                        _global_loop.run_until_complete(process())
                    except Exception as e:
                        print(f"[WEBHOOK] Error in process: {str(e)}", file=sys.stderr, flush=True)
                        logger.error(f"Error in process: {str(e)}", exc_info=True)
                    
            except Exception as e:
                print(f"[WEBHOOK] Event loop error: {str(e)}", file=sys.stderr, flush=True)
                logger.error(f"Event loop error: {str(e)}", exc_info=True)
                import traceback
                traceback.print_exc()

            print("[WEBHOOK] Sending 200 OK response", file=sys.stderr, flush=True)
            self._send_response(200, {"ok": True})

        except json.JSONDecodeError:
            print("[WEBHOOK] JSON decode error", file=sys.stderr, flush=True)
            self._send_response(200, {"ok": True, "skipped": "invalid JSON"})
        except Exception as e:
            print(f"[WEBHOOK] Error processing update: {str(e)}", file=sys.stderr, flush=True)
            logger.error(f"Error processing update: {str(e)}", exc_info=True)
            import traceback
            traceback.print_exc()
            self._send_response(500, {"error": str(e)})
    
    def log_message(self, format, *args):
        """로그 메시지 출력"""
        message = f"{self.address_string()} - {format % args}"
        logger.info(message)
