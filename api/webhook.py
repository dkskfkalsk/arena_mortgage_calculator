# -*- coding: utf-8 -*-
"""
Vercel 서버리스 함수 - 텔레그램 Webhook
"""

import json
import os
import sys
import asyncio
import logging
from http.server import BaseHTTPRequestHandler

# Vercel 로그 출력을 위한 강력한 헬퍼 함수
def log_print(*args, **kwargs):
    """Vercel에서 확실하게 로그가 보이도록 하는 헬퍼"""
    import time
    timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
    message = ' '.join(str(arg) for arg in args)
    log_line = f"[{timestamp}] {message}\n"
    
    # stderr에 직접 쓰기 (가장 확실한 방법)
    try:
        sys.stderr.write(log_line)
        sys.stderr.flush()
    except:
        pass
    
    # stdout에도 쓰기
    try:
        sys.stdout.write(log_line)
        sys.stdout.flush()
    except:
        pass

# 로깅 설정 (Vercel에서 로그가 보이도록)
logging.basicConfig(
    level=logging.DEBUG,  # DEBUG 레벨로 변경하여 모든 로그 출력
    format='[%(asctime)s] %(levelname)s - %(name)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stderr),  # stderr로 출력
        logging.StreamHandler(sys.stdout)   # stdout으로도 출력
    ],
    force=True  # 기존 설정 강제 재설정
)
logger = logging.getLogger(__name__)

# 초기화 로그 (가장 먼저 출력)
log_print("=" * 50)
log_print("WEBHOOK MODULE LOADED")
log_print("=" * 50)
logger.info("Webhook module initialized")

# 프로젝트 루트를 경로에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 모듈 로드 시 즉시 출력 (가장 먼저 실행)
log_print("=" * 60)
log_print("WEBHOOK.PY MODULE LOADED - START")
log_print(f"Python version: {sys.version}")
log_print(f"Working directory: {os.getcwd()}")
log_print("=" * 60)

# 전역 애플리케이션 인스턴스
application = None

# 전역 이벤트 루프 (웹사이트 참조: 단일 이벤트 루프 재사용)
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

        # 환경변수에서 토큰 가져오기 (Vercel에서는 환경변수 사용)
        log_print("=" * 60)
        log_print("LOADING ENVIRONMENT VARIABLES")
        log_print("=" * 60)
        
        TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
        log_print(f"TELEGRAM_BOT_TOKEN from env: {'SET' if TELEGRAM_BOT_TOKEN else 'NOT SET'}")
        if TELEGRAM_BOT_TOKEN:
            log_print(f"TELEGRAM_BOT_TOKEN length: {len(TELEGRAM_BOT_TOKEN)}")
            log_print(f"TELEGRAM_BOT_TOKEN prefix: {TELEGRAM_BOT_TOKEN[:20]}...")
        
        if not TELEGRAM_BOT_TOKEN:
            log_print("TELEGRAM_BOT_TOKEN not found in env, trying config file...")
            # 로컬 테스트용 fallback
            try:
                from config.telegram_config import TELEGRAM_BOT_TOKEN  # type: ignore
                log_print("TELEGRAM_BOT_TOKEN loaded from config file")
            except ModuleNotFoundError:
                log_print("ERROR: TELEGRAM_BOT_TOKEN not found in env or config")
                logger.error("TELEGRAM_BOT_TOKEN not found")
                raise ValueError("TELEGRAM_BOT_TOKEN 환경변수를 설정해주세요.")

        # 허용된 채팅방 ID 가져오기
        ALLOWED_CHAT_IDS_STR = os.getenv("ALLOWED_CHAT_IDS")
        log_print(f"ALLOWED_CHAT_IDS from env: {'SET' if ALLOWED_CHAT_IDS_STR else 'NOT SET'}")
        if ALLOWED_CHAT_IDS_STR:
            log_print(f"ALLOWED_CHAT_IDS value: {ALLOWED_CHAT_IDS_STR}")
        
        if not ALLOWED_CHAT_IDS_STR:
            log_print("ALLOWED_CHAT_IDS not found in env, trying config file...")
            try:
                from config.telegram_config import ALLOWED_CHAT_IDS  # type: ignore
                ALLOWED_CHAT_IDS_STR = ALLOWED_CHAT_IDS
                log_print(f"ALLOWED_CHAT_IDS loaded from config: {ALLOWED_CHAT_IDS_STR}")
            except (ModuleNotFoundError, ImportError):
                ALLOWED_CHAT_IDS_STR = None
                log_print("ALLOWED_CHAT_IDS not found in config, using None (all chats allowed)")
        
        # 허용된 채팅방 ID 리스트로 변환 (쉼표로 구분된 문자열을 리스트로)
        allowed_chat_ids = []
        if ALLOWED_CHAT_IDS_STR:
            allowed_chat_ids = [int(chat_id.strip()) for chat_id in ALLOWED_CHAT_IDS_STR.split(",") if chat_id.strip()]
        
        log_print("=" * 60)
        log_print(f"ENVIRONMENT VARIABLES LOADED:")
        log_print(f"  TELEGRAM_BOT_TOKEN: {'SET' if TELEGRAM_BOT_TOKEN else 'NOT SET'}")
        log_print(f"  ALLOWED_CHAT_IDS_STR: {ALLOWED_CHAT_IDS_STR}")
        log_print(f"  allowed_chat_ids: {allowed_chat_ids}")
        log_print("=" * 60)
        logger.info(f"Application initialized - TELEGRAM_BOT_TOKEN: {'SET' if TELEGRAM_BOT_TOKEN else 'NOT SET'}, allowed_chat_ids: {allowed_chat_ids}")

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
            # 메시지 또는 채널 포스트 가져오기
            message = update.message or update.channel_post or update.edited_message or update.edited_channel_post
            if not message:
                log_print("DEBUG: start_command - No message found")
                logger.debug("start_command - No message found")
                return
            
            # 채팅방 ID 확인
            chat_id = get_chat_id(update)
            log_print(f"DEBUG: start_command - chat_id: {chat_id}, allowed_chat_ids: {allowed_chat_ids}")
            logger.info(f"start_command - chat_id: {chat_id}")
            if not is_allowed_chat(chat_id):
                # 허용되지 않은 채팅방에서는 조용히 무시
                log_print(f"DEBUG: start_command - Chat {chat_id} is not allowed")
                logger.warning(f"start_command - Chat {chat_id} is not allowed")
                return
            log_print(f"DEBUG: start_command - Processing command for chat {chat_id}")
            logger.info(f"start_command - Processing command for chat {chat_id}")
            
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
                reply_task = asyncio.create_task(message.reply_text(welcome_message))
                await reply_task
            except Exception as e:
                log_print(f"DEBUG: Error sending welcome message: {str(e)}")
                logger.error(f"Error sending welcome message: {str(e)}", exc_info=True)
                # 오류가 발생해도 조용히 처리 (사용자에게는 이미 처리된 것으로 보임)

        async def handle_message(update, context=None):
            # 메시지 또는 채널 포스트 가져오기
            message = update.message or update.channel_post or update.edited_message or update.edited_channel_post
            
            if not message:
                log_print("DEBUG: handle_message - No message found in update")
                logger.warning("handle_message - No message found in update")
                return
            
            # 어떤 타입의 메시지인지 확인
            msg_type = "message" if update.message else "channel_post" if update.channel_post else "edited_message" if update.edited_message else "edited_channel_post"
            log_print(f"DEBUG: handle_message - Message type: {msg_type}")
            logger.info(f"handle_message - Message type: {msg_type}")
            
            # 채팅방 ID 확인
            chat_id = get_chat_id(update)
            log_print(f"DEBUG: handle_message - chat_id: {chat_id}, allowed_chat_ids: {allowed_chat_ids}")
            logger.info(f"handle_message - chat_id: {chat_id}")
            
            if not is_allowed_chat(chat_id):
                log_print(f"DEBUG: handle_message - Chat {chat_id} is not allowed")
                logger.warning(f"handle_message - Chat {chat_id} is not allowed")
                return
            
            log_print(f"DEBUG: handle_message - Processing message for chat {chat_id}, type: {msg_type}")
            logger.info(f"handle_message - Processing message for chat {chat_id}, type: {msg_type}")
            
            message_text = message.text
            if not message_text:
                log_print("DEBUG: handle_message - No text in message, sending help message")
                logger.info("handle_message - No text in message, sending help message")
                await message.reply_text(
                    "텍스트 메시지를 보내주세요.\n\n"
                    "담보물건 정보를 텍스트로 입력해주시면 계산해드립니다.\n\n"
                    "/start 명령어로 사용 방법을 확인하실 수 있습니다."
                )
                log_print("DEBUG: handle_message - Help message sent, returning immediately")
                logger.info("handle_message - Help message sent")
                return
            
            try:
                parser = MessageParser()
                property_data = parser.parse(message_text)
                log_print(f"DEBUG: handle_message - property_data: {property_data}")
                log_print(f"DEBUG: handle_message - kb_price in property_data: {property_data.get('kb_price')}")
                logger.info(f"handle_message - property_data parsed: kb_price={property_data.get('kb_price')}")
                
                results = BaseCalculator.calculate_all_banks(property_data)
                log_print(f"DEBUG: handle_message - results count: {len(results) if results else 0}")
                logger.info(f"handle_message - results count: {len(results) if results else 0}")
                
                formatted_result = format_all_results(results)
                
                # 메시지 전송 후 즉시 종료 (대기 없음)
                await message.reply_text(formatted_result)
                log_print("DEBUG: handle_message - Message sent, returning immediately")
                logger.info("handle_message - Message sent successfully")
                return
                
            except Exception as e:
                log_print(f"DEBUG: Error in handle_message: {str(e)}")
                logger.error(f"Error in handle_message: {str(e)}", exc_info=True)
                import traceback
                traceback.print_exc()
                
                try:
                    # 에러 메시지 전송 시도 후 즉시 종료
                    await message.reply_text(
                        f"계산 중 오류가 발생했습니다.\n\n"
                        f"오류 내용: {str(e)}"
                    )
                    log_print("DEBUG: handle_message - Error message sent, returning immediately")
                    logger.info("handle_message - Error message sent to user")
                    return
                except Exception as reply_error:
                    log_print(f"DEBUG: Failed to send error message: {str(reply_error)}")
                    logger.error(f"Failed to send error message: {str(reply_error)}", exc_info=True)
                    # 전송 실패해도 즉시 종료
                    return

        # 명령어 핸들러
        application.add_handler(CommandHandler("start", start_command))
        application.add_handler(CommandHandler("help", start_command))
        
        # 일반 메시지 처리 (명령어 제외)
        application.add_handler(MessageHandler(~filters.COMMAND, handle_message))
        
        # handle_message를 전역에서 접근 가능하도록 저장
        application._handle_message = handle_message

    return application


class handler(BaseHTTPRequestHandler):
    """
    Vercel Python 서버리스 함수 핸들러
    BaseHTTPRequestHandler를 상속하여 텔레그램 웹훅 요청만 처리합니다.
    """
    
    def __init__(self, *args, **kwargs):
        """핸들러 초기화 시 로그 출력"""
        log_print("=" * 60)
        log_print("HANDLER CLASS INITIALIZED")
        log_print("=" * 60)
        super().__init__(*args, **kwargs)
    
    def _send_response(self, status_code, data):
        """응답 전송 헬퍼 메서드"""
        log_print(f"Sending response: status={status_code}, data={data}")
        body = json.dumps(data).encode('utf-8')
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    
    def do_GET(self):
        """GET 요청 처리 (헬스체크)"""
        log_print("GET REQUEST - Health check")
        logger.info("GET request - Health check")
        self._send_response(200, {"ok": True, "message": "Webhook endpoint is active"})
    
    def do_POST(self):
        """POST 요청 처리 (텔레그램 웹훅)"""
        # 요청 시작 로그 (가장 먼저)
        log_print("=" * 50)
        log_print("POST REQUEST RECEIVED")
        log_print("=" * 50)
        logger.info("POST request received")
        
        try:
            # 요청 body 읽기
            content_length = int(self.headers.get('Content-Length', 0))
            log_print(f"Content-Length: {content_length}")
            
            if content_length == 0:
                log_print("Empty body, skipping")
                self._send_response(200, {"ok": True, "skipped": "empty body"})
                return

            body_bytes = self.rfile.read(content_length)
            body_str = body_bytes.decode('utf-8')
            log_print(f"Body received: {body_str[:200]}...")  # 처음 200자만 로그
            body = json.loads(body_str) if body_str else {}

            # 텔레그램 update 형식 검증 (update_id가 있어야 함)
            if not isinstance(body, dict) or "update_id" not in body:
                log_print("Not a telegram update, skipping")
                logger.warning("Not a telegram update, skipping")
                self._send_response(200, {"ok": True, "skipped": "not telegram update"})
                return

            # 텔레그램 업데이트 처리
            log_print("Loading telegram library...")
            from telegram import Update
            log_print("Getting application instance...")
            app = get_application()
            log_print("Creating Update object...")
            update = Update.de_json(body, app.bot)
            log_print(f"Update object created: update_id={update.update_id}")

            # 업데이트 정보 로깅
            log_print(f"DEBUG: Received update - update_id: {update.update_id}")
            log_print(f"DEBUG: Update attributes: message={update.message is not None}, edited_message={update.edited_message is not None}, channel_post={update.channel_post is not None}, callback_query={update.callback_query is not None}")
            logger.info(f"Received update - update_id: {update.update_id}, message={update.message is not None}, channel_post={update.channel_post is not None}")

            # 채팅방 ID 확인 및 필터링
            def get_chat_id_from_update(update):
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

            chat_id = get_chat_id_from_update(update)

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

            log_print(f"DEBUG: chat_id: {chat_id}, allowed_chat_ids: {allowed_chat_ids}")
            logger.info(f"chat_id: {chat_id}, allowed_chat_ids: {allowed_chat_ids}")

            # 허용된 채팅방이 설정되어 있고, 현재 채팅방이 허용 목록에 없으면 무시
            if allowed_chat_ids and chat_id not in allowed_chat_ids:
                log_print(f"DEBUG: Chat {chat_id} is not in allowed list, ignoring update")
                logger.warning(f"Chat {chat_id} is not in allowed list, ignoring update")
                self._send_response(200, {"ok": True, "skipped": "chat not allowed"})
                return

            if update.message:
                log_print(f"DEBUG: message.chat.id: {update.message.chat.id}, message.text: {update.message.text[:50] if update.message.text else None}")
                logger.info(f"message.chat.id: {update.message.chat.id}, message.text: {update.message.text[:50] if update.message.text else None}")
            elif update.edited_message:
                log_print(f"DEBUG: edited_message.chat.id: {update.edited_message.chat.id}")
                logger.info(f"edited_message.chat.id: {update.edited_message.chat.id}")
            elif update.channel_post:
                log_print(f"DEBUG: channel_post.chat.id: {update.channel_post.chat.id}")
                logger.info(f"channel_post.chat.id: {update.channel_post.chat.id}")
            elif update.callback_query:
                log_print(f"DEBUG: callback_query.from_user.id: {update.callback_query.from_user.id}")
                logger.info(f"callback_query.from_user.id: {update.callback_query.from_user.id}")
            else:
                log_print(f"DEBUG: Unknown update type - update dict keys: {list(body.keys())}")
                logger.warning(f"Unknown update type - update dict keys: {list(body.keys())}")

            # 비동기 처리 함수
            async def process():
                try:
                    # 초기화되지 않았으면 초기화
                    if not app._initialized:
                        await app.initialize()
                    
                    # channel_post, edited_message, edited_channel_post는 MessageHandler가 처리하지 않으므로 직접 처리
                    if update.channel_post or update.edited_message or update.edited_channel_post:
                        # handle_message 함수 직접 호출 (context는 사용하지 않으므로 None 전달)
                        if hasattr(app, '_handle_message'):
                            log_print("DEBUG: Directly calling handle_message for channel_post/edited_message")
                            logger.info("Directly calling handle_message for channel_post/edited_message")
                            await app._handle_message(update, None)
                        else:
                            # fallback: process_update 사용 (일반 메시지만 처리됨)
                            logger.warning("_handle_message not found, using process_update")
                            await app.process_update(update)
                    else:
                        # 일반 메시지는 process_update로 처리
                        logger.info("Processing regular message with process_update")
                        await app.process_update(update)
                    
                    # 메시지 전송 완료 후 즉시 종료 (대기 없음)
                    log_print("DEBUG: Message processing completed, returning immediately")
                    logger.info("Message processing completed")
                    
                except Exception as e:
                    log_print(f"DEBUG: Error in process(): {str(e)}")
                    logger.error(f"Error in process(): {str(e)}", exc_info=True)
                    import traceback
                    traceback.print_exc()
                    # 에러 발생해도 raise하지 않음 (이미 텔레그램 응답 전송 시도했으므로)

            # 이벤트 루프 안전하게 실행 (웹사이트 참조: 단일 이벤트 루프 재사용)
            global _global_loop
            
                try:
                    # 기존 루프 확인
                    try:
                        loop = asyncio.get_running_loop()
                        # 이미 실행 중인 루프가 있으면 새 스레드에서 실행
                        log_print("DEBUG: Event loop already running, using thread")
                        logger.info("Event loop already running, using thread")
                    import threading
                    import queue
                    
                    result_queue = queue.Queue()
                    exception_queue = queue.Queue()
                    
                    def run_in_new_thread():
                        global _global_loop
                        try:
                            # 전역 루프가 없으면 생성, 있으면 재사용
                            if _global_loop is None or _global_loop.is_closed():
                                new_loop = asyncio.new_event_loop()
                                asyncio.set_event_loop(new_loop)
                            else:
                                new_loop = _global_loop
                                asyncio.set_event_loop(new_loop)
                            
                            try:
                                new_loop.run_until_complete(process())
                                result_queue.put("success")
                            finally:
                                # 루프를 닫지 않고 유지 (재사용을 위해)
                                # 단, pending tasks만 정리
                                try:
                                    pending = [t for t in asyncio.all_tasks(new_loop) if not t.done()]
                                    if pending:
                                        # 완료될 때까지 짧게 대기
                                        try:
                                            new_loop.run_until_complete(asyncio.wait_for(
                                                asyncio.gather(*pending, return_exceptions=True),
                                                timeout=0.5
                                            ))
                                        except (asyncio.TimeoutError, Exception):
                                            # 타임아웃이나 오류 발생 시 무시 (루프는 유지)
                                            pass
                                except Exception as cleanup_error:
                                    log_print(f"DEBUG: Cleanup error (ignored): {str(cleanup_error)}")
                                    logger.warning(f"Cleanup error (ignored): {str(cleanup_error)}")
                                
                                # 전역 루프에 저장 (재사용을 위해)
                                if not new_loop.is_closed():
                                    _global_loop = new_loop
                        except Exception as e:
                            exception_queue.put(e)
                    
                    thread = threading.Thread(target=run_in_new_thread, daemon=False)
                    thread.start()
                    thread.join(timeout=25)
                    
                    if not exception_queue.empty():
                        raise exception_queue.get()
                    
                    if thread.is_alive():
                        log_print("DEBUG: Thread timeout after 25 seconds")
                        logger.error("Thread timeout after 25 seconds")
                        raise TimeoutError("Process timeout after 25 seconds")
                        
                except RuntimeError:
                    # 실행 중인 루프가 없으면 전역 루프 사용 또는 생성
                    log_print("DEBUG: No running loop, using global loop or creating new one")
                    logger.info("No running loop, using global loop or creating new one")
                    
                    if _global_loop is None or _global_loop.is_closed():
                        # 전역 루프가 없거나 닫혔으면 새로 생성
                        _global_loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(_global_loop)
                        log_print("DEBUG: Created new global event loop")
                        logger.info("Created new global event loop")
                    else:
                        # 전역 루프 재사용
                        asyncio.set_event_loop(_global_loop)
                        log_print("DEBUG: Reusing existing global event loop")
                        logger.info("Reusing existing global event loop")
                    
                    try:
                        _global_loop.run_until_complete(process())
                    except RuntimeError as e:
                        # "Event loop is closed" 오류는 무시
                        if "Event loop is closed" not in str(e):
                            raise
                        log_print(f"DEBUG: Event loop closed (ignored): {str(e)}")
                        logger.warning(f"Event loop closed (ignored): {str(e)}")
                    except Exception as e:
                        # 다른 오류는 로그만 남기고 계속 진행
                        log_print(f"DEBUG: Error in process (ignored): {str(e)}")
                        logger.error(f"Error in process (ignored): {str(e)}", exc_info=True)
                    
            except Exception as e:
                log_print(f"DEBUG: Event loop error: {str(e)}")
                logger.error(f"Event loop error: {str(e)}", exc_info=True)
                import traceback
                traceback.print_exc()
                # 오류가 발생해도 HTTP 응답은 정상 반환 (이미 메시지 전송 시도했으므로)

            self._send_response(200, {"ok": True})

        except json.JSONDecodeError:
            self._send_response(200, {"ok": True, "skipped": "invalid JSON"})
        except Exception as e:
            import traceback
            error_msg = str(e)
            traceback_str = traceback.format_exc()
            # 오류 로깅 (Vercel 로그에 출력)
            log_print(f"Error processing update: {error_msg}")
            log_print(traceback_str)
            logger.error(f"Error processing update: {error_msg}", exc_info=True)
            self._send_response(500, {"error": error_msg})
    
    def log_message(self, format, *args):
        """로그 메시지 출력 (Vercel 로그에 출력)"""
        message = f"{self.address_string()} - {format % args}"
        log_print(message)
        logger.info(message)

