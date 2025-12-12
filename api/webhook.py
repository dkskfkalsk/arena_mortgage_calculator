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
        from telegram.ext import (
            Application, MessageHandler, CommandHandler, filters
        )
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
            # 메시지 또는 채널 포스트 가져오기
            message = update.message or update.channel_post or update.edited_message or update.edited_channel_post
            if not message:
                print("DEBUG: start_command - No message found")
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
            await message.reply_text(welcome_message)

        async def handle_message(update, context=None):
            # 메시지 또는 채널 포스트 가져오기
            message = update.message or update.channel_post or update.edited_message or update.edited_channel_post
            if not message:
                print("DEBUG: handle_message - No message found in update")
                return
            
            # 어떤 타입의 메시지인지 확인
            msg_type = "message" if update.message else "channel_post" if update.channel_post else "edited_message" if update.edited_message else "edited_channel_post"
            print(f"DEBUG: handle_message - Message type: {msg_type}")
            
            # 채팅방 ID 확인
            chat_id = get_chat_id(update)
            print(f"DEBUG: handle_message - chat_id: {chat_id}, allowed_chat_ids: {allowed_chat_ids}")
            if not is_allowed_chat(chat_id):
                # 허용되지 않은 채팅방에서는 조용히 무시
                print(f"DEBUG: handle_message - Chat {chat_id} is not allowed")
                return
            print(f"DEBUG: handle_message - Processing message for chat {chat_id}, type: {msg_type}")
            
            message_text = message.text
            if not message_text:
                print("DEBUG: handle_message - No text in message, sending help message")
                await message.reply_text(
                    "텍스트 메시지를 보내주세요.\n\n"
                    "담보물건 정보를 텍스트로 입력해주시면 계산해드립니다.\n\n"
                    "/start 명령어로 사용 방법을 확인하실 수 있습니다."
                )
                return
            try:
                parser = MessageParser()
                property_data = parser.parse(message_text)
                print(f"DEBUG: handle_message - property_data: {property_data}")
                print(f"DEBUG: handle_message - kb_price in property_data: {property_data.get('kb_price')}")
                results = BaseCalculator.calculate_all_banks(property_data)
                print(f"DEBUG: handle_message - results count: {len(results) if results else 0}")
                formatted_result = format_all_results(results)
                await message.reply_text(formatted_result)
            except Exception as e:
                await message.reply_text(
                    f"계산 중 오류가 발생했습니다.\n\n"
                    f"오류 내용: {str(e)}"
                )

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
            print(f"DEBUG: Received update - update_id: {update.update_id}")
            print(f"DEBUG: Update attributes: message={update.message is not None}, edited_message={update.edited_message is not None}, channel_post={update.channel_post is not None}, callback_query={update.callback_query is not None}")
            
            # 채팅방 ID 가져오기 및 필터링
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
            
            print(f"DEBUG: chat_id: {chat_id}, allowed_chat_ids: {allowed_chat_ids}")
            
            # 허용된 채팅방이 설정되어 있고, 현재 채팅방이 허용 목록에 없으면 무시
            if allowed_chat_ids and chat_id not in allowed_chat_ids:
                print(f"DEBUG: Chat {chat_id} is not in allowed list, ignoring update")
                self._send_response(200, {"ok": True, "skipped": "chat not allowed"})
                return
            
            if update.message:
                print(f"DEBUG: message.chat.id: {update.message.chat.id}, message.text: {update.message.text[:50] if update.message.text else None}")
            elif update.edited_message:
                print(f"DEBUG: edited_message.chat.id: {update.edited_message.chat.id}")
            elif update.channel_post:
                print(f"DEBUG: channel_post.chat.id: {update.channel_post.chat.id}")
            elif update.callback_query:
                print(f"DEBUG: callback_query.from_user.id: {update.callback_query.from_user.id}")
            else:
                print(f"DEBUG: Unknown update type - update dict keys: {list(body.keys())}")
            
            # 비동기 처리 (Application 초기화 포함)
            # Vercel 서버리스 환경에서 이벤트 루프 안전하게 처리
            async def process():
                try:
                    # 초기화되지 않았으면 초기화
                    if not app._initialized:
                        await app.initialize()
                    
                    # channel_post, edited_message, edited_channel_post는 MessageHandler가 처리하지 않으므로 직접 처리
                    if update.channel_post or update.edited_message or update.edited_channel_post:
                        # handle_message 함수 직접 호출 (context는 사용하지 않으므로 None 전달)
                        if hasattr(app, '_handle_message'):
                            print("DEBUG: Directly calling handle_message for channel_post/edited_message")
                            await app._handle_message(update, None)
                        else:
                            # fallback: process_update 사용 (일반 메시지만 처리됨)
                            await app.process_update(update)
                    else:
                        # 일반 메시지는 process_update로 처리
                        await app.process_update(update)
                    
                    # Application의 내부 HTTP 작업들이 완료될 때까지 기다리기
                    # 텔레그램 봇의 HTTP 클라이언트가 모든 요청을 완료할 때까지 대기
                    # pending 작업이 없을 때까지 반복적으로 확인
                    max_wait_iterations = 20  # 최대 2초 대기 (20 * 0.1초)
                    for i in range(max_wait_iterations):
                        await asyncio.sleep(0.1)
                        # 현재 루프의 모든 작업 확인
                        try:
                            loop = asyncio.get_running_loop()
                            pending = [t for t in asyncio.all_tasks(loop) if not t.done()]
                            # 현재 작업(process 함수)과 sleep 작업만 남아있으면 완료된 것으로 간주
                            if len(pending) <= 2:  # process 함수와 현재 sleep 작업
                                print(f"DEBUG: All tasks completed after {i+1} iterations")
                                break
                        except RuntimeError:
                            # 루프를 가져올 수 없으면 중단
                            break
                    
                    # 마지막으로 한 번 더 짧게 대기하여 HTTP 응답이 완전히 전송되도록 함
                    await asyncio.sleep(0.2)
                    
                except Exception as e:
                    print(f"DEBUG: Error in process(): {str(e)}")
                    import traceback
                    traceback.print_exc()
                    raise
            
            # 이벤트 루프 안전하게 실행
            # Vercel 서버리스 환경에서는 매 요청마다 새로운 컨텍스트이므로 새 루프 생성
            # asyncio.run()을 사용하여 새로운 이벤트 루프에서 실행하고 자동으로 정리
            try:
                # 실행 중인 루프가 있는지 확인
                try:
                    loop = asyncio.get_running_loop()
                    # 실행 중인 루프가 있으면 에러 (이 경우는 발생하지 않아야 함)
                    print("DEBUG: Warning - event loop already running, this should not happen in Vercel")
                    # 강제로 새 루프에서 실행하기 위해 스레드 사용
                    import threading
                    import queue
                    
                    result_queue = queue.Queue()
                    
                    def run_in_thread():
                        try:
                            # 새로운 이벤트 루프에서 실행
                            new_loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(new_loop)
                            try:
                                new_loop.run_until_complete(process())
                                result_queue.put(("success", None))
                            finally:
                                # 루프 정리 전에 모든 pending 작업 완료 대기
                                try:
                                    pending = [t for t in asyncio.all_tasks(new_loop) if not t.done()]
                                    if pending:
                                        # 타임아웃 설정하여 무한 대기 방지
                                        try:
                                            new_loop.run_until_complete(asyncio.wait_for(
                                                asyncio.gather(*pending, return_exceptions=True),
                                                timeout=2.0
                                            ))
                                        except asyncio.TimeoutError:
                                            print("DEBUG: Timeout waiting for pending tasks, closing loop anyway")
                                except Exception as cleanup_e:
                                    print(f"DEBUG: Cleanup warning: {str(cleanup_e)}")
                                finally:
                                    # 루프를 닫기 전에 짧게 대기
                                    try:
                                        new_loop.run_until_complete(asyncio.sleep(0.1))
                                    except:
                                        pass
                                    new_loop.close()
                        except Exception as e:
                            result_queue.put(("error", e))
                    
                    thread = threading.Thread(target=run_in_thread, daemon=False)
                    thread.start()
                    thread.join(timeout=30)  # 30초 타임아웃
                    
                    if not result_queue.empty():
                        status, error = result_queue.get()
                        if status == "error":
                            raise error
                    elif thread.is_alive():
                        raise TimeoutError("Process timeout after 30 seconds")
                except RuntimeError:
                    # 실행 중인 루프가 없으면 asyncio.run() 사용
                    # asyncio.run()은 자동으로 루프를 생성하고 정리함
                    asyncio.run(process())
            except Exception as e:
                # 모든 방법이 실패하면 asyncio.run() 사용 (새 루프 생성)
                print(f"DEBUG: Event loop error, using asyncio.run(): {str(e)}")
                import traceback
                traceback.print_exc()
                # 마지막 시도: 완전히 새로운 루프에서 실행
                try:
                    asyncio.run(process())
                except Exception as final_e:
                    print(f"DEBUG: Final error in asyncio.run(): {str(final_e)}")
                    import traceback
                    traceback.print_exc()
                    # 오류가 발생해도 사용자에게는 성공 메시지 전송 (이미 처리되었을 수 있음)
                    pass
            
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

