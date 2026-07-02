# -*- coding: utf-8 -*-
"""
Vercel 서버리스 함수 - 텔레그램 Webhook
"""

# 가장 먼저 실행되는 로그 (모듈 임포트 시 즉시 실행, Vercel 로그 절약을 위해 최소화)
import sys

import json
import os
import asyncio
import logging
import time
from http.server import BaseHTTPRequestHandler

# 프로젝트 루트를 경로에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 원금 계산 유틸리티 임포트
from utils.mortgage_calculator import (
    calculate_principal,
    extract_manual_ratios,
    extract_manual_principals,
    classify_financial_institution
)

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[logging.StreamHandler(sys.stderr)]
)
logger = logging.getLogger(__name__)

# Vercel: 요청당 256줄 제한이 있으므로 서드파티 로거를 WARNING으로 올려 로그 양 축소
if os.getenv("VERCEL") == "1" or os.getenv("VERCEL_ENV"):
    for name in ("httpx", "httpcore", "httpcore.http11", "httpcore.connection",
                 "telegram", "telegram.ext", "telegram.ext.ExtBot",
                 "asyncio", "urllib3.connectionpool"):
        log = logging.getLogger(name)
        log.setLevel(logging.WARNING)

# 모듈 로드 시 로그 출력 (한 줄로 축소)
logger.info("Webhook module initialized")

# 전역 텔레그램 애플리케이션 인스턴스 (요청 간 캐시 용도)
telegram_application = None

# 전역 이벤트 루프
_global_loop = None

# 마지막 요청 처리 시각 (0 = 아직 요청 없음 / 방금 깨어남)
_last_request_time = 0

# 처리된 update_id 캐시 (텔레그램 재시도 루프 방지)
# 서버리스 인스턴스 내에서만 유효하지만 연속 재시도는 대부분 같은 인스턴스로 옴
_processed_update_ids: set = set()
_MAX_CACHED_UPDATE_IDS = 200


def get_application(force_new=False):
    """텔레그램 애플리케이션 인스턴스 가져오기. force_new=True면 요청 전용 새 인스턴스 반환(캐시 안 함)."""
    global telegram_application

    def _build():
        from telegram.ext import (
            Application, MessageHandler, CommandHandler, filters
        )
        from parsers.message_parser import MessageParser
        from calculator.base_calculator import BaseCalculator
        from utils.formatter import format_all_results
        from utils.validators import (
            extract_bank_appraisal_price_from_special_notes,
            extract_kb_ai_price_from_special_notes,
            extract_housematch_price_from_special_notes,
            extract_realestatetech_price_from_special_notes,
            extract_korea_realestate_price_from_special_notes,
        )

        # 환경변수에서 토큰 가져오기
        TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
        if not TELEGRAM_BOT_TOKEN:
            try:
                from config.telegram_config import TELEGRAM_BOT_TOKEN  # type: ignore
            except ModuleNotFoundError:
                raise ValueError("TELEGRAM_BOT_TOKEN 환경변수를 설정해주세요.")

        # 허용된 채팅방 ID 가져오기 (1번방: banks, 2번방: loan, 3번방: banks_2 - PDF 등기부등본 분석, pdf_only - PDF 파싱만)
        ALLOWED_CHAT_IDS_BANKS_STR = os.getenv("ALLOWED_CHAT_IDS_BANKS")
        ALLOWED_CHAT_IDS_LOAN_STR = os.getenv("ALLOWED_CHAT_IDS_LOAN")
        ALLOWED_CHAT_IDS_BANKS_2_STR = os.getenv("ALLOWED_CHAT_IDS_BANKS_2")
        ALLOWED_CHAT_IDS_PDF_ONLY_STR = os.getenv("ALLOWED_CHAT_IDS_PDF_ONLY")
        
        if not ALLOWED_CHAT_IDS_BANKS_STR:
            try:
                from config.telegram_config import ALLOWED_CHAT_IDS_BANKS  # type: ignore
                ALLOWED_CHAT_IDS_BANKS_STR = ALLOWED_CHAT_IDS_BANKS
            except (ModuleNotFoundError, ImportError):
                ALLOWED_CHAT_IDS_BANKS_STR = None
        
        if not ALLOWED_CHAT_IDS_LOAN_STR:
            try:
                from config.telegram_config import ALLOWED_CHAT_IDS_LOAN  # type: ignore
                ALLOWED_CHAT_IDS_LOAN_STR = ALLOWED_CHAT_IDS_LOAN
            except (ModuleNotFoundError, ImportError):
                ALLOWED_CHAT_IDS_LOAN_STR = None
        
        if not ALLOWED_CHAT_IDS_BANKS_2_STR:
            try:
                from config.telegram_config import ALLOWED_CHAT_IDS_BANKS_2  # type: ignore
                ALLOWED_CHAT_IDS_BANKS_2_STR = ALLOWED_CHAT_IDS_BANKS_2
            except (ModuleNotFoundError, ImportError):
                ALLOWED_CHAT_IDS_BANKS_2_STR = None
        
        if not ALLOWED_CHAT_IDS_PDF_ONLY_STR:
            try:
                from config.telegram_config import ALLOWED_CHAT_IDS_PDF_ONLY  # type: ignore
                ALLOWED_CHAT_IDS_PDF_ONLY_STR = ALLOWED_CHAT_IDS_PDF_ONLY
            except (ModuleNotFoundError, ImportError, AttributeError):
                ALLOWED_CHAT_IDS_PDF_ONLY_STR = None
        
        # 허용된 채팅방 ID 리스트로 변환
        allowed_chat_ids_banks = []
        if ALLOWED_CHAT_IDS_BANKS_STR:
            allowed_chat_ids_banks = [int(chat_id.strip()) for chat_id in ALLOWED_CHAT_IDS_BANKS_STR.split(",") if chat_id.strip()]
        
        allowed_chat_ids_loan = []
        if ALLOWED_CHAT_IDS_LOAN_STR:
            allowed_chat_ids_loan = [int(chat_id.strip()) for chat_id in ALLOWED_CHAT_IDS_LOAN_STR.split(",") if chat_id.strip()]
        
        allowed_chat_ids_banks_2 = []
        if ALLOWED_CHAT_IDS_BANKS_2_STR:
            allowed_chat_ids_banks_2 = [int(chat_id.strip()) for chat_id in ALLOWED_CHAT_IDS_BANKS_2_STR.split(",") if chat_id.strip()]
        
        allowed_chat_ids_pdf_only = []
        if ALLOWED_CHAT_IDS_PDF_ONLY_STR:
            allowed_chat_ids_pdf_only = [int(chat_id.strip()) for chat_id in ALLOWED_CHAT_IDS_PDF_ONLY_STR.split(",") if chat_id.strip()]
        
        # 전체 허용된 채팅방 ID (모두 합침)
        allowed_chat_ids = allowed_chat_ids_banks + allowed_chat_ids_loan + allowed_chat_ids_banks_2 + allowed_chat_ids_pdf_only
        
        print(f"[WEBHOOK] Application initializing - allowed_chat_ids_banks: {allowed_chat_ids_banks}, allowed_chat_ids_loan: {allowed_chat_ids_loan}, allowed_chat_ids_banks_2: {allowed_chat_ids_banks_2}, allowed_chat_ids_pdf_only: {allowed_chat_ids_pdf_only}", file=sys.stderr, flush=True)
        logger.info(f"Application initialized - allowed_chat_ids_banks: {allowed_chat_ids_banks}, allowed_chat_ids_loan: {allowed_chat_ids_loan}, allowed_chat_ids_banks_2: {allowed_chat_ids_banks_2}, allowed_chat_ids_pdf_only: {allowed_chat_ids_pdf_only}")

        app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
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
        
        def get_chat_type(chat_id):
            """채팅방 타입 반환: 'banks', 'loan', 또는 'banks_2' (PDF 등기부등본 분석)"""
            if chat_id in allowed_chat_ids_banks:
                return "banks"
            elif chat_id in allowed_chat_ids_loan:
                return "loan"
            elif chat_id in allowed_chat_ids_banks_2:
                return "banks_2"
            return "banks"  # 기본값은 banks

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
                "/help - 상세 기능 설명 보기\n\n"
                "이제 담보물건 정보를 보내주시면 계산해드리겠습니다! 🚀"
            )
            try:
                await message.reply_text(welcome_message)
            except Exception as e:
                logger.error(f"Error sending welcome message: {str(e)}", exc_info=True)

        async def help_command(update, context):
            message = update.message or update.channel_post or update.edited_message or update.edited_channel_post
            if not message:
                return
            
            chat_id = get_chat_id(update)
            print(f"[WEBHOOK] help_command - chat_id: {chat_id}", file=sys.stderr, flush=True)
            logger.info(f"help_command - chat_id: {chat_id}")
            
            if not is_allowed_chat(chat_id):
                print(f"[WEBHOOK] help_command - Chat {chat_id} is NOT allowed", file=sys.stderr, flush=True)
                logger.warning(f"help_command - Chat {chat_id} is not allowed")
                return
            
            print(f"[WEBHOOK] help_command - Chat {chat_id} is allowed", file=sys.stderr, flush=True)
            
            help_message = (
                "📋 등기부 분석 봇 사용설명서\n"
                "────────────────────\n\n"
                "【사용법】\n"
                "• 등기부등본 PDF를 보내면 자동으로 분석합니다.\n"
                "• PDF와 함께 보낸 글은 아래 키워드로 인식됩니다.\n\n"
                "【캡션 키워드】\n"
                "• 특이사항: 내용 → '특이사항' 줄에 표시\n"
                "• 요청사항: 내용 → '요청사항' 줄에 표시\n"
                "• 1순위 120%설정 기재 → 해당 순위 원금 비율 반영\n"
                "• 직업(사업자/직장인 등), 신용점수(예: 850점) → 결과에 반영\n\n"
                "【결과 안내】\n"
                "소유자·주소·면적·KB시세·세대수·근저당권(채권최고액/원금)·LTV(채권최고액/원금 기준)\n"
                "KB시세가 없으면 'KB시세 없음. 다른 시세 첨부 바랍니다.' 안내\n\n"
                "【명령어】\n"
                "/help — 이 사용설명서\n"
                "/start — 환영 메시지"
            )
            try:
                await message.reply_text(help_message)
            except Exception as e:
                logger.error(f"Error sending help message: {str(e)}", exc_info=True)

        async def handle_document(update, context=None):
            """PDF 문서 처리 핸들러 (등기부등본 분석)"""
            message = update.message or update.channel_post or update.edited_message or update.edited_channel_post
            
            if not message:
                return
            
            chat_id = get_chat_id(update)
            if not is_allowed_chat(chat_id):
                return
            
            # banks_2 또는 pdf_only 소속 여부 확인 (동일 chat_id가 여러 목록에 있을 수 있음)
            if chat_id not in allowed_chat_ids_banks_2 and chat_id not in allowed_chat_ids_pdf_only:
                await message.reply_text("등기부 PDF 분석은 등기부·KB시세 전용 방에서 이용해 주세요.")
                return
            
            pdf_only_mode = chat_id in allowed_chat_ids_pdf_only
            
            document = message.document
            if not document:
                return
            
            # PDF 파일인지 확인
            file_name = document.file_name or ""
            if not file_name.lower().endswith('.pdf'):
                await message.reply_text("⚠️ PDF 파일만 분석할 수 있습니다.")
                return
            
            print(f"[WEBHOOK] PDF document received: {file_name}", file=sys.stderr, flush=True)
            logger.info(f"PDF document received: {file_name}")

            async def reply_text_safe(text: str):
                """
                '답장' 형태는 유지하되, 텔레그램에서 원본 메시지를 못 찾는 경우에도
                (Message to be replied not found) 전송 자체가 실패하지 않도록 처리.
                """
                bot = message.get_bot()
                return await bot.send_message(
                    chat_id=message.chat.id,
                    text=text,
                    reply_to_message_id=getattr(message, "message_id", None),
                    allow_sending_without_reply=True,
                )
            
            processing_msg = None  # 분석 중 메시지 저장용
            try:
                # 파일 다운로드
                processing_msg = await reply_text_safe(f"📄 등기부등본 분석 중... ({file_name})")
                
                file = await document.get_file()
                file_bytes = await file.download_as_bytearray()
                
                # PDF 분석 (무거운 동기 작업은 스레드 풀에서 실행해 이벤트 루프 블로킹 방지)
                import tempfile
                from parsers.registry_parser import analyze_pdf
                
                # 임시 파일로 저장 후 분석
                with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp_file:
                    tmp_file.write(file_bytes)
                    tmp_path = tmp_file.name
                
                caption = message.caption or ""
                try:
                    def _blocking_pdf_work():
                        result = analyze_pdf(tmp_path)
                        return format_registry_result(result, caption, file_name, pdf_only=pdf_only_mode)
                    loop = asyncio.get_event_loop()
                    response = await loop.run_in_executor(None, _blocking_pdf_work)
                    
                    # "분석 중" 메시지 삭제
                    if processing_msg:
                        try:
                            await processing_msg.delete()
                        except Exception as del_err:
                            print(f"[WEBHOOK] Failed to delete processing message: {str(del_err)}", file=sys.stderr, flush=True)
                    
                    # 에러 메시지인 경우 (KB 시세가 없고 대체 시세도 없는 경우) - pdf_only 모드에서는 해당 메시지 없음
                    if response and isinstance(response, str) and "KB 시세가 검색되지 않으므로" in response:
                        await reply_text_safe(response)
                        return
                    
                    # 결과 반환
                    print("[WEBHOOK] Sending PDF result to user", file=sys.stderr, flush=True)
                    await reply_text_safe(response)
                    print("[WEBHOOK] PDF result sent successfully", file=sys.stderr, flush=True)
                    
                    # banks_2 채팅방에서는 등기부 정보만 표시하고 계산 결과는 표시하지 않음
                    # (계산은 다른 채팅방에서 텍스트 메시지로 처리)
                    
                finally:
                    # 임시 파일 삭제
                    import os as tmp_os
                    try:
                        tmp_os.unlink(tmp_path)
                    except:
                        pass
                
            except Exception as e:
                print(f"[WEBHOOK] Error analyzing PDF: {str(e)}", file=sys.stderr, flush=True)
                logger.error(f"Error analyzing PDF: {str(e)}", exc_info=True)
                
                # 오류 발생 시에도 "분석 중" 메시지 삭제
                if processing_msg:
                    try:
                        await processing_msg.delete()
                    except:
                        pass
                
                await reply_text_safe(f"❌ PDF 분석 중 오류가 발생했습니다.\n\n오류: {str(e)}")

        def parse_complex_amount(text):
            """복합 금액 파싱 (억+천만/만원 조합, 원 단위 등)
            
            예시:
            - "1억5천만원" → 15000 (만원 단위)
            - "1억2620만" → 12620 (만원 단위)
            - "10억300만원" → 100300 (만원 단위)
            - "510,000,000원" → 51000 (만원 단위, 원을 만원으로 변환)
            - "60750" → 60750 (만원 단위로 가정)
            """
            import re
            
            if not text:
                return None
            
            # 쉼표 제거
            text_clean = text.replace(',', '').replace('，', '')
            
            total_man = 0  # 만원 단위 합계
            
            # 공백 제거한 버전도 함께 확인
            text_no_space = text_clean.replace(' ', '').replace('　', '')
            
            # 패턴 1: "1억5천만원" 또는 "1억 5천만" (억 + 천만)
            pattern1 = r'(\d+)\s*억\s*(\d+)\s*천\s*만\s*원?'
            match1 = re.search(pattern1, text_clean)
            if not match1:
                # 공백 없는 버전 시도
                pattern1_no_space = r'(\d+)억(\d+)천만원?'
                match1 = re.search(pattern1_no_space, text_no_space)
            if match1:
                eok = int(match1.group(1))  # 억 단위
                cheon_man = int(match1.group(2))  # 천만 단위
                total_man = eok * 10000 + cheon_man * 1000
                return total_man
            
            # 패턴 2: "1억2620만" 또는 "1억 2620만원" (억 + 만)
            pattern2 = r'(\d+)\s*억\s*(\d+)\s*만\s*원?'
            match2 = re.search(pattern2, text_clean)
            if not match2:
                # 공백 없는 버전 시도
                pattern2_no_space = r'(\d+)억(\d+)만원?'
                match2 = re.search(pattern2_no_space, text_no_space)
            if match2:
                eok = int(match2.group(1))  # 억 단위
                man = int(match2.group(2))  # 만 단위
                total_man = eok * 10000 + man
                return total_man
            
            # 패턴 3: "1억5000원" (억 + 원, 원을 만원으로 변환)
            pattern3 = r'(\d+)\s*억\s*(\d+)\s*원'
            match3 = re.search(pattern3, text_clean)
            if match3:
                eok = int(match3.group(1))  # 억 단위
                won = int(match3.group(2))  # 원 단위
                total_man = eok * 10000 + won // 10000
                return total_man
            
            # 패턴 4: "20억" (억만)
            pattern4 = r'(\d+)\s*억\s*원?'
            match4 = re.search(pattern4, text_clean)
            if match4:
                eok = int(match4.group(1))
                total_man = eok * 10000
                return total_man
            
            # 패턴 5: "5천만원" 또는 "5천만" (천만만)
            pattern5 = r'(\d+)\s*천\s*만\s*원?'
            match5 = re.search(pattern5, text_clean)
            if match5:
                cheon_man = int(match5.group(1))
                total_man = cheon_man * 1000
                return total_man
            
            # 패턴 6: "7000만원" 또는 "7000만" (만만)
            pattern6 = r'(\d+)\s*만\s*원?'
            match6 = re.search(pattern6, text_clean)
            if match6:
                man = int(match6.group(1))
                total_man = man
                return total_man
            
            # 패턴 7: "510,000,000원" 또는 "510000000원" (원 단위를 만원으로 변환)
            pattern7 = r'(\d+)\s*원'
            match7 = re.search(pattern7, text_clean)
            if match7:
                won = int(match7.group(1))
                total_man = won // 10000
                return total_man
            
            # 패턴 8: 숫자만 있는 경우 (만원 단위로 가정, 예: "60750")
            pattern8 = r'^(\d+)$'
            match8 = re.search(pattern8, text_clean)
            if match8:
                num = int(match8.group(1))
                # 10000 이상이면 만원 단위로 가정, 아니면 그대로
                if num >= 10000:
                    total_man = num
                    return total_man
                else:
                    # 작은 숫자는 만원 단위로 해석 (예: 60750 → 60750만원)
                    total_man = num
                    return total_man
            
            return None
        
        def parse_caption_info(caption):
            """캡션에서 고객 정보 추출"""
            import re
            info = {
                'job': '',           # 직업 (사업자, 직장인 등)
                'credit_score': '',  # 신용점수 또는 신용등급
                'residence': '',     # 거주여부
                'households': '',    # 세대수
                'property_type': '', # 구분 (아파트, 빌라 등)
                'kb_price': '',      # KB시세 일반
                'kb_price_low': '',  # KB시세 하한
                'special_notes': [], # 특이사항 (리스트로 변경)
                'request': '',       # 요청사항
                'borrower_name': '', # 차주 이름
                'collateral_provider': '', # 담보제공자 이름
                'name_display': '',  # 최종 표시할 이름 형식
                'area': '',          # 면적 (캡션에서 입력한 경우)
                'total_floor': '',   # 총층수 (캡션에서 입력한 경우)
                'trust_amount': '',  # 신탁 금액 (만원 단위 문자열)
                'tenant': None,      # 세입자 정보 {deposit_man, monthly_rent_man, display_name} 또는 None
            }
            
            if not caption:
                return info
            
            # 차주/담보제공자 구분 추출
            # 형식: "윤행자(차주),최효석" 또는 "윤행자(차), 최효석(담)" 등
            borrower_match = re.search(r'([가-힣]+)\s*\(\s*(?:차주?|차)\s*\)', caption)
            if borrower_match:
                info['borrower_name'] = borrower_match.group(1)
            
            collateral_match = re.search(r'([가-힣]+)\s*\(\s*(?:담보?|담)\s*\)', caption)
            if collateral_match:
                info['collateral_provider'] = collateral_match.group(1)
            
            # 차주만 있고 담보제공자가 명시 안된 경우: "윤행자(차주),최효석" 형태
            if info['borrower_name'] and not info['collateral_provider']:
                # 차주 다음에 오는 이름을 담보제공자로 인식
                after_borrower = re.search(r'\(\s*(?:차주?|차)\s*\)\s*[,/\s]+\s*([가-힣]+)', caption)
                if after_borrower:
                    info['collateral_provider'] = after_borrower.group(1)
            
            # 직업 추출 (사업자, 직장인, 프리랜서, 무직 등)
            # 가라사업자 보유 체크 (직장인 + 사업자 보유 조건)
            has_gara_business = re.search(r'가라\s*사업자', caption)
            
            # 먼저 기본 직업 추출
            job_patterns = [
                (r'직장인', '직장인'),
                (r'사업자', '사업자'),
                (r'프리랜서', '프리랜서'),
                (r'무직', '무직'),
                (r'자영업', '자영업'),
                (r'공무원', '공무원'),
                (r'전문직', '전문직'),
            ]
            for pattern, job_name in job_patterns:
                # "가라사업자"는 직업 "사업자"로 인식하지 않도록 예외 처리
                if pattern == r'사업자' and has_gara_business:
                    continue
                if re.search(pattern, caption):
                    info['job'] = job_name
                    break
            
            # 가라사업자 보유인 경우 특이사항에 추가
            if has_gara_business:
                info['special_notes'].append('사업자 보유(즉발보유, 부가세 누락신고 조건)')
            
            # 신용등급 추출 (4등급, 5등급 등)
            grade_match = re.search(r'(\d{1,2})\s*등급', caption)
            if grade_match:
                grade = int(grade_match.group(1))
                if 1 <= grade <= 10:
                    info['credit_score'] = f"{grade}등급"
            
            # 신용점수 추출 (신용점수 850, 신용 850, 850점 등) - 등급이 없는 경우만
            if not info['credit_score']:
                credit_patterns = [
                    r'신용\s*[점수]*\s*[:：]?\s*(\d{3})',
                    r'신용\s*(\d{3})',
                    r'(\d{3})\s*점',
                ]
                for pattern in credit_patterns:
                    match = re.search(pattern, caption)
                    if match:
                        score = int(match.group(1))
                        if 300 <= score <= 1000:  # 유효한 신용점수 범위
                            info['credit_score'] = str(score)
                            break
            
            # 거주여부 추출 (비거주 먼저 - "비거주(월세동의)"에서 "거주" 오매칭 방지)
            if re.search(r'비거주|임대|전세', caption):
                info['residence'] = '비거주'
            elif re.search(r'거주|실거주|본인\s*거주', caption):
                info['residence'] = '거주'
            
            # 세대수 추출 (세대수 700, 700세대, 271 / 5개동 등)
            households_match = (
                re.search(r'세대\s*[수]*\s*[:：]?\s*(\d+)\s*(?:/\s*(\d+)\s*개동)?', caption) or
                re.search(r'(\d+)\s*/\s*(\d+)\s*개동', caption)  # "271 / 5개동" 단독
            )
            if households_match:
                h = households_match.group(1)
                dong = households_match.group(2) if households_match.lastindex >= 2 else None
                info['households'] = f"{h}세대" + (f" / {dong}개동" if dong else "")
            else:
                for pattern in [r'(\d+)\s*세대', r'세대\s*[수]*\s*[:：]?\s*(\d+)']:
                    match = re.search(pattern, caption)
                    if match:
                        info['households'] = match.group(1) + '세대'
                        break
            
            # 구분 추출 (아파트, 빌라, 오피스텔 등)
            property_patterns = [
                (r'아파트', '아파트'),
                (r'빌라', '빌라'),
                (r'오피스텔', '오피스텔'),
                (r'다세대', '다세대'),
                (r'다가구', '다가구'),
                (r'단독주택', '단독주택'),
                (r'연립', '연립'),
            ]
            for pattern, prop_type in property_patterns:
                if re.search(pattern, caption):
                    info['property_type'] = prop_type
                    break
            
            # KB시세 추출 (우선순위: KB시세 > 부동산테크시세 > 하우스머치 중위시세)
            # 1. KB시세 추출
            kb_price_found = False
            
            # 패턴 1: "KB 시세 일반가 7억 6,500만", "KB 시세 24,400만원" (공백 유연)
            # KB 접두 필수 + (?!ai) 로 "KB AI시세"가 일반 KB시세로 오인되지 않게 함 (AI시세 끝의 '시세' 매칭 방지)
            kb_patterns = [
                r'kb\s*(?!ai)\s*시세\s*[\s\S]*?(?:일반\s*가?|일반가)\s*([\d,\s억천만원]+)',  # KB 시세 (줄바꿈) 일반가 7억 6,500만
                r'kb\s*(?!ai)\s*시세\s*(?:일반\s*가?|일반가)\s*([\d,\s억천만원]+)',  # 같은 줄
                r'kb\s*(?!ai)\s*시세\s*[:：]?\s*([\d,]+)\s*만원',  # "KB 시세 24,400만원" (공백 유연)
                r'kb\s*시세\s*[:：]\s*일반\s*([\d,\s억천만원]+)',  # KB시세 : 일반 87,500만원
                r'kb\s*(?!ai)\s*(?:시세|일반\s*가?)\s*[:：]?\s*([\d,\s억천만원]+)',  # 복합 단위 포함
                r'kb\s*(?!ai)\s*시세\s*[:：]?\s*([\d,]+)',  # "kb시세 60750" 또는 "KB 시세 24400"
            ]
            for pattern in kb_patterns:
                match = re.search(pattern, caption, re.IGNORECASE | re.DOTALL)
                if match:
                    price_text = match.group(1).strip()
                    price_man = parse_complex_amount(price_text)
                    if price_man:
                        info['kb_price'] = f"{price_man:,}"
                        kb_price_found = True
                        break
            
            # 2. 부동산테크시세 추출 (KB시세가 없을 경우)
            # "KBx 8400", "부동산테크 50,000만" 형식
            if not kb_price_found:
                tech_patterns = [
                    r'(?:부동산\s*테크|kb\s*x|kbx)\s*[:：/]?\s*([\d,\s억천만원]+)',
                    r'(?:부동산\s*테크|kb\s*x|kbx)\s*[:：/]?\s*([\d,]+)',
                ]
                for pattern in tech_patterns:
                    match = re.search(pattern, caption, re.IGNORECASE)
                    if match:
                        price_text = match.group(1).strip()
                        price_man = parse_complex_amount(price_text)
                        if price_man:
                            info['kb_price'] = f"{price_man:,}"
                            info['price_type'] = "부동산테크 시세"
                            kb_price_found = True
                            break
            
            # 3. 하우스머치 중위시세 추출 (KB시세, 부동산테크시세가 없을 경우)
            # "하우스머치 40,000만", "하머중위 8400", "하우스머치 중위 8400" 형식
            if not kb_price_found:
                hammer_patterns = [
                    r'(?:하우스\s*머치|하머)\s*[:：/]?\s*([\d,\s억천만원]+)',  # 하우스머치 40,000만 (중위 없이)
                    r'(?:하우스\s*머치\s*중위|하머\s*중위|하머중위)\s*[:：/]?\s*([\d,\s억천만원]+)',
                    r'(?:하우스\s*머치\s*중위|하머\s*중위|하머중위)\s*[:：/]?\s*([\d,]+)',
                    # "KBx / 하머중위 8400" 형식에서 하머중위 뒤의 숫자 추출
                    r'(?:kb\s*x|kbx)\s*/\s*(?:하우스\s*머치\s*중위|하머\s*중위|하머중위)\s*([\d,\s억천만원]+)',
                    r'(?:kb\s*x|kbx)\s*/\s*(?:하우스\s*머치\s*중위|하머\s*중위|하머중위)\s*([\d,]+)',
                ]
                for pattern in hammer_patterns:
                    match = re.search(pattern, caption, re.IGNORECASE)
                    if match:
                        price_text = match.group(1).strip()
                        price_man = parse_complex_amount(price_text)
                        if price_man:
                            info['kb_price'] = f"{price_man:,}"
                            info['price_type'] = "하우스머치 시세"
                            kb_price_found = True
                            break
            
            # 4. 감정가/탁감가 추출 (KB시세, 부동산테크시세, 하우스머치 중위시세가 없을 경우)
            # "은행감정가 8억", "감정가 80,000만원", "탁감가 82,000만", "탁감 80,000" 형식 처리
            if not kb_price_found:
                appraisal_patterns = [
                    r'(?:은행\s*감정가|감정가|탁감가|탁감)\s*[:：]?\s*([\d,\s억천만원]+)',  # "감정가 60,000만", "탁감가 82,000만" 등
                    r'(?:은행\s*감정가|감정가|탁감가|탁감)\s*[:：]?\s*([\d,]+(?:\s*만원?)?)',  # "감정가 60,000만" 형식 명시적 처리
                    r'(?:은행\s*감정가|감정가|탁감가|탁감)\s*[:：]?\s*([\d,]+)',  # 숫자만 있는 경우
                ]
                for pattern in appraisal_patterns:
                    match = re.search(pattern, caption, re.IGNORECASE)
                    if match:
                        price_text = match.group(1).strip()
                        price_man = parse_complex_amount(price_text)
                        if price_man:
                            info['kb_price'] = f"{price_man:,}"
                            info['price_type'] = "감정가·탁감가"
                            kb_price_found = True
                            print(f"[WEBHOOK] parse_caption_info - 감정가/탁감가 추출: {price_text} -> {price_man}만원", file=sys.stderr, flush=True)
                            logger.info(f"parse_caption_info - 감정가/탁감가 추출: {price_text} -> {price_man}만원")
                            break
            
            # KB시세 하한 추출 (복합 단위 지원, 줄바꿈 허용)
            kb_low_patterns = [
                r'kb\s*(?!ai)\s*시세\s*[\s\S]*?(?:하한\s*가?|하한가)\s*([\d,\s억천만원]+)',  # KB 시세 (줄바꿈) 하한가
                r'하위\s*평균\s*가\s*([\d,\s억천만원]+)',  # 하위평균가 7억 3,000만
                r'하위평균가\s*([\d,\s억천만원]+)',  # 하위평균가7억 3,000만 (공백 없음)
                r'kb시세\s*[:：]\s*하한\s*([\d,\s억천만원]+)',  # KB시세 : 하한 85,500만원
                r'(?:kb\s*)?하한\s*[가]?\s*[:：]?\s*([\d,\s억천만원]+)',  # KB하한 1억5천만원
                r'(?:kb\s*)?하한\s*[가]?\s*[:：]?\s*([\d,]+)',  # KB하한 6500
            ]
            for pattern in kb_low_patterns:
                match = re.search(pattern, caption, re.IGNORECASE | re.DOTALL)
                if match:
                    price_text = match.group(1).strip()
                    price_man = parse_complex_amount(price_text)
                    if price_man:
                        info['kb_price_low'] = f"{price_man:,}"
                        break
            
            # 총층수 추출 (콜론·공백·띄어쓰기 유연)
            total_floor_patterns = [
                r'총\s*층\s*수\s*[:：\s]*(\d+)\s*층?',   # 총 층 수 : 20층
                r'총층수\s*[:：\s]*(\d+)\s*층?',        # 총층수 : 20층, 총층수: 20
                r'총\s*층수\s*[:：\s]*(\d+)\s*층?',    # 총 층수 20층
                r'(?:총\s*)?층수\s*[:：\s]*(\d+)\s*층?', # 층수 20층
            ]
            for pattern in total_floor_patterns:
                match = re.search(pattern, caption, re.IGNORECASE)
                if match:
                    num = match.group(1).strip()
                    if num.isdigit() and 1 <= int(num) <= 200:
                        info['total_floor'] = f"{num}층"
                        break
            
            # 면적 추출 (전용 83.89, 83.89㎡ 등)
            area_patterns = [
                r'전용\s*[:：]?\s*(\d+(?:\.\d+)?)',  # 전용 83.89
                r'(\d+(?:\.\d+)?)\s*㎡',             # 83.89㎡
                r'면적\s*[:：]?\s*(\d+(?:\.\d+)?)',  # 면적 83.89
            ]
            for pattern in area_patterns:
                match = re.search(pattern, caption)
                if match:
                    info['area'] = f"{match.group(1)}㎡"
                    break
            
            # 요청사항 추출
            requests = []
            
            # N순위 대환조건 (1순위 대환조건, 2순위 대환조건 등)
            rank_match = re.search(r'(\d)\s*순위\s*대환\s*조?건?', caption)
            if rank_match:
                requests.append(f"{rank_match.group(1)}순위 대환조건")
            
            # 금융사명 대환조건 (애큐온 대환, 카카오뱅크 대환조건 등)
            bank_patterns = [
                r'(애큐온|카카오뱅크|카카오|제주은행|신한|국민|우리|하나|기업|농협|SC|씨티|케이뱅크|토스|OK저축은행|페퍼|웰컴|SBI|JB우리|MG|BNK|키움)\s*(?:저축은행|은행|캐피탈)?\s*대환\s*조?건?',
            ]
            for pattern in bank_patterns:
                match = re.search(pattern, caption, re.IGNORECASE)
                if match:
                    bank_name = match.group(1)
                    if f"{bank_name} 대환조건" not in ' '.join(requests):
                        requests.append(f"{bank_name} 대환조건")
            
            # 후순위 요청
            if re.search(r'후순위', caption):
                requests.append("후순위 추가대출")
            
            # 추가대출 요청
            if re.search(r'추가\s*대출', caption) and "후순위" not in caption:
                requests.append("추가대출")
            
            # 선순위 대환
            if re.search(r'선순위\s*대환', caption):
                requests.append("선순위 대환")
            
            # 전액 대환
            if re.search(r'전액\s*대환', caption):
                requests.append("전액 대환")
            
            info['request'] = ' / '.join(requests) if requests else ''
            
            # 신탁 금액 추출 (신탁금액, 신탁원금, 신탁대환, 신탁 뒤에 금액) - 복합 단위 지원
            trust_patterns = [
                r'신탁\s*금액\s*[:：]?\s*([\d,\s억천만원]+)',  # 신탁 금액 1억5천만원
                r'신탁\s*원금\s*[:：]?\s*([\d,\s억천만원]+)',  # 신탁원금 1억5천만원
                r'신탁\s*대환\s*[:：]?\s*([\d,\s억천만원]+)',  # 신탁대환 1억5천만원
                r'신탁\s*[:：]?\s*([\d,\s억천만원]+)',        # 신탁 1억5천만원, 신탁: 15000
            ]
            for pattern in trust_patterns:
                match = re.search(pattern, caption, re.IGNORECASE)
                if match:
                    price_text = match.group(1).strip()
                    price_man = parse_complex_amount(price_text)
                    if price_man:
                        info['trust_amount'] = f"{price_man:,}"
                        break
            
            # 세입자 추출 (공통 유틸 사용)
            from utils.tenant_extractor import extract_tenant_info
            tenant = extract_tenant_info(caption, parse_amount_fn=parse_complex_amount)
            if tenant:
                info['tenant'] = tenant
            
            # 특이사항 추출 (캡션에서 "특이사항" 키워드 뒤의 내용)
            # 패턴: "특이사항 : 내용" 또는 "특이사항: 내용" 또는 "특이사항 내용"
            # "특이사항 : 요청사항 : 내용" (한 줄에 붙은 경우) 방지: \n요청사항 또는 같은 줄 요청사항에서 중단
            special_notes_match = re.search(r'특이사항\s*[:：]?\s*(.+?)(?=\s*요청사항\s*[:：]|\n요청사항|\n\n|$)', caption, re.IGNORECASE | re.DOTALL)
            if special_notes_match:
                special_note_text = special_notes_match.group(1).strip()
                # 여러 줄일 수 있으므로 줄바꿈 제거하고 공백으로 대체
                special_note_text = re.sub(r'\s+', ' ', special_note_text).strip()
                if special_note_text:
                    info['special_notes'].append(special_note_text)
            
            # 요청사항 추출 (캡션에서 "요청사항" 키워드 뒤의 내용) - 기존 로직 덮어쓰기
            # 패턴: "요청사항 : 내용" 또는 "요청사항: 내용" 또는 "요청사항 내용"
            request_match = re.search(r'요청사항\s*[:：]?\s*(.+?)(?=\n특이사항|\n\n|$)', caption, re.IGNORECASE | re.DOTALL)
            if request_match:
                request_text = request_match.group(1).strip()
                # 여러 줄일 수 있으므로 줄바꿈 제거하고 공백으로 대체
                request_text = re.sub(r'\s+', ' ', request_text).strip()
                if request_text:
                    # 기존 requests에 추가하지 않고 덮어쓰기
                    info['request'] = request_text
            
            return info

        def extract_name_from_filename(file_name):
            """파일명에서 고객 이름 추출 (예: "최성운 260122.pdf" -> "최성운")"""
            import re
            if not file_name:
                return ""
            # 파일 확장자 제거
            name_without_ext = file_name.replace('.pdf', '').replace('.PDF', '')
            # 공백이나 숫자로 분리 (예: "최성운 260122" -> "최성운")
            match = re.match(r'^([가-힣A-Za-z]+)', name_without_ext)
            if match:
                return match.group(1).strip()
            return ""
        
        def format_registry_result(result, caption, file_name, pdf_only=False):
            """등기부등본 분석 결과를 텔레그램 메시지 형식으로 포맷. pdf_only=True면 KB API·공공데이터·스크래핑 호출 없음"""
            import re
            
            # 캡션에서 추가 정보 추출
            caption_info = parse_caption_info(caption)
            
            lines = []
            
            # 소유자 정보 (이름, 나이)
            # 차주/담보제공자 구분이 있는 경우 처리
            borrower = caption_info.get('borrower_name', '')
            collateral_provider = caption_info.get('collateral_provider', '')
            
            # 수탁자 여부 확인 (신탁인 경우)
            is_trustee = result.수탁자여부 if hasattr(result, '수탁자여부') else False
            
            # 수탁자인 경우 파일명에서 고객 이름 추출
            if is_trustee:
                customer_name = extract_name_from_filename(file_name)
                if customer_name:
                    # 수탁자인 경우 고객 이름을 성명으로 사용
                    lines.append(f"성   명 : {customer_name}")
                    lines.append(f"직   업 : {caption_info['job']}")
                    lines.append(f"신용점수 : {caption_info['credit_score']}")
                    lines.append(f"거주여부 : {caption_info['residence']}")
                    lines.append(f"소유현황 : 신탁")
                else:
                    # 파일명에서 이름을 못 찾은 경우
                    if borrower:
                        lines.append(f"성   명 : {borrower}")
                    else:
                        lines.append(f"성   명 : 확인불가")
                    lines.append(f"직   업 : {caption_info['job']}")
                    lines.append(f"신용점수 : {caption_info['credit_score']}")
                    lines.append(f"거주여부 : {caption_info['residence']}")
                    lines.append(f"소유현황 : 신탁")
            elif result.소유자목록:
                # 공동명의인 경우 2명 모두 표시
                owners = result.소유자목록[:2]  # 최대 2명까지
                
                # 첫 번째 소유자의 나이 계산 (만나이, 한국 시간 기준)
                age = ""
                if owners[0].생년월일:
                    try:
                        from datetime import datetime
                        try:
                            from zoneinfo import ZoneInfo
                        except ImportError:
                            # Python 3.8 이하의 경우
                            from pytz import timezone
                            ZoneInfo = lambda tz: timezone(tz)
                        
                        # 생년월일 형식: "YYYY.MM.DD"
                        birth_parts = owners[0].생년월일.split('.')
                        birth_year = int(birth_parts[0])
                        birth_month = int(birth_parts[1]) if len(birth_parts) > 1 else 1
                        birth_day = int(birth_parts[2]) if len(birth_parts) > 2 else 1
                        
                        # 한국 시간대(Asia/Seoul, UTC+9) 기준으로 현재 날짜 가져오기
                        korea_tz = ZoneInfo('Asia/Seoul')
                        today = datetime.now(korea_tz).date()
                        birth_date = datetime(birth_year, birth_month, birth_day, tzinfo=korea_tz).date()
                        
                        # 만나이 계산: 생일이 지났는지 확인
                        calculated_age = today.year - birth_year
                        if (today.month, today.day) < (birth_month, birth_day):
                            calculated_age -= 1
                        
                        age = f"({calculated_age})"  # 만 나이
                    except:
                        age = ""
                
                # 차주/담보제공자 구분이 있는 경우
                if borrower and collateral_provider:
                    # 담보제공자 나이 (등기부 소유자 = 담보제공자)
                    name_display = f"{borrower}(차), {collateral_provider}(담) {age}"
                elif borrower:
                    # 차주만 있는 경우 (담보제공자는 등기부 소유자)
                    if len(owners) == 1:
                        name_display = f"{borrower}(차), {owners[0].성명}(담) {age}"
                    else:
                        # 공동명의인 경우 2명 모두 표시
                        owner_names = ", ".join([o.성명 for o in owners])
                        name_display = f"{borrower}(차), {owner_names}(담) {age}"
                else:
                    # 일반적인 경우 (등기부 소유자가 차주)
                    if len(owners) == 1:
                        name_display = f"{owners[0].성명} {age}"
                    else:
                        # 공동명의인 경우 2명 모두 표시
                        owner_names = ", ".join([o.성명 for o in owners])
                        name_display = f"{owner_names} {age}"
                
                lines.append(f"성   명 : {name_display}")
                lines.append(f"직   업 : {caption_info['job']}")
                lines.append(f"신용점수 : {caption_info['credit_score']}")
                lines.append(f"거주여부 : {caption_info['residence']}")
                
                # 소유현황
                if len(owners) == 1:
                    share = owners[0].지분 if owners[0].지분 else "단독소유"
                else:
                    # 공동명의인 경우
                    share = "공동소유"
                lines.append(f"소유현황 : {share}")
            else:
                # 등기부에서 소유자를 못 찾은 경우
                # 파일명에서 이름 추출 시도
                name_from_file = extract_name_from_filename(file_name)
                
                if borrower and collateral_provider:
                    name_display = f"{borrower}(차), {collateral_provider}(담)"
                elif borrower:
                    name_display = f"{borrower}(차)"
                elif name_from_file:
                    # 파일명에서 추출한 이름 사용
                    name_display = name_from_file
                    print(f"[WEBHOOK] 파일명에서 이름 추출: {name_from_file}", file=sys.stderr, flush=True)
                    logger.info(f"파일명에서 이름 추출: {name_from_file}")
                else:
                    name_display = "확인불가"
                
                lines.append(f"성   명 : {name_display}")
                lines.append(f"직   업 : {caption_info['job']}")
                lines.append(f"신용점수 : {caption_info['credit_score']}")
                lines.append(f"거주여부 : {caption_info['residence']}")
                lines.append(f"소유현황 : ")
            
            # 주소 (층수 포함)
            address = result.부동산_주소 or "확인불가"
            floor_info = result.층수정보 or ""
            
            # 총층수: 캡션 우선, 없으면 PDF(등기부)에서 추출
            total_floor = caption_info.get('total_floor') or ""
            if not total_floor and floor_info:
                # "15층 중 2층 203호" 또는 "17층 1802호" 또는 "18층" 형태에서 파싱
                floor_match = re.search(r'(\d+)층\s*중', floor_info)
                if floor_match:
                    total_floor = f"{floor_match.group(1)}층"
                else:
                    floor_match = re.search(r'^(\d+)층', floor_info)
                    if floor_match:
                        total_floor = f"{floor_match.group(1)}층"
            unit_info = ""
            if floor_info:
                
                # 호수 정보
                unit_match = re.search(r'(\d+)호', floor_info)
                if unit_match:
                    unit_info = f"{unit_match.group(1)}호"
            
            # 주소 포맷팅 (총층수는 별도 줄에 표시하므로 주소에는 포함하지 않음)
            lines.append(f"주   소 : {address}")
            
            # 총층수
            if total_floor:
                lines.append(f"총층수 : {total_floor}")
            else:
                lines.append(f"총층수 : ")
            
            # 면적 (캡션에서 입력한 면적 우선, 없으면 등기부에서 추출)
            area_from_caption = caption_info.get('area')
            area_from_pdf = result.면적 or ''
            area = area_from_caption or area_from_pdf or ''
            area_source = " (캡션 입력)" if (area and area_from_caption) else (" (등기부 추출)" if area else "")
            lines.append(f"면   적 : {area}{area_source}")
            
            # 세대수, 구분, KB시세 (캡션에서 추출한 정보 사용, KB API 결과로 업데이트 가능)
            households = caption_info.get('households') or ''
            property_type = caption_info.get('property_type') or ''
            
            # KB시세: 캡션에서 추출한 것이 없으면 등기부 주소/면적로 자동 조회
            kb_price = caption_info['kb_price']
            kb_price_low = caption_info['kb_price_low']
            # 캡션에서 탁감가/감정가로 추출된 경우 표시 라벨용 (동일 취급)
            caption_price_type = caption_info.get('price_type')  # '감정가·탁감가' 등
            
            # 면적에서 숫자 추출 (64.08㎡ -> 64.08, "51㎡/37.85㎡" -> 37.85 전용 사용은 get_kb_price_from_registry 내부에서)
            area_value = None
            if area:
                import re as area_re
                area_match = area_re.search(r'([\d.]+)', str(area))
                if area_match:
                    try:
                        area_value = float(area_match.group(1))
                    except Exception:
                        pass
            
            # KB API 검색 상태 추적 (실패/결과없음 구분용)
            kb_api_searched = False
            kb_api_failed = False  # 예외 발생 시 True
            kb_api_no_result = False  # 결과 없음 시 True
            kb_complex_id = None  # KB 시세 참고 링크(kbland.kr/c/{단지ID})용
            kb_result = None  # KB API 전체 결과 (사용승인일·재건축 정보 포함)
            real_transactions_display = ""  # KB 시세 없을 때 공공데이터 실거래가
            
            # 등기부에서 주소와 면적을 추출한 경우 KB API 호출 (면적은 문자열 그대로 전달해 51/37.85 등 전용 추출)
            # pdf_only 모드에서는 KB API·공공데이터·스크래핑 호출 없음 (Vercel 수준에서 PDF 파싱만)
            has_area = bool(area and str(area).strip()) or (area_value is not None and area_value > 0)
            # 캡션에 KB AI시세만 있고 공식 KB시세(캡션 파싱값)가 없으면 자동 조회로 kb_price 채우지 않음
            kb_ai_from_caption = extract_kb_ai_price_from_special_notes(caption or "")
            skip_kb_api_for_ai_only_caption = (
                kb_ai_from_caption is not None and not (caption_info.get("kb_price") or "").strip()
            )
            should_call_kb_api = (
                address and address != "확인불가" and has_area and not pdf_only
                and not skip_kb_api_for_ai_only_caption
            )
            
            if should_call_kb_api:
                kb_api_searched = True
                print(f"[WEBHOOK] KB API 호출 조건 충족 - KB시세: {kb_price or '없음'}, 세대수: {households or '없음'}, 구분: {property_type or '없음'}", file=sys.stderr, flush=True)
                try:
                    # 면적 문자열 그대로 전달 (51㎡/37.85㎡ → API에서 전용 37.85 사용)
                    area_for_kb = str(area).strip() if area else str(area_value or 0)
                    print(f"[WEBHOOK] KB 시세 자동 조회 시작 - 주소: {address}, 면적: {area_for_kb}", file=sys.stderr, flush=True)
                    logger.info(f"KB 시세 자동 조회 시작 - 주소: {address}, 면적: {area_for_kb}")
                    
                    from KB_api.kb_price_api import get_kb_price_from_registry
                    kb_result = get_kb_price_from_registry(address, area_for_kb)
                    
                    if kb_result:
                        kb_price_num = kb_result.get('kb_price')
                        kb_price_min_num = kb_result.get('kb_price_min')
                        kb_complex_id = kb_result.get('complex_id')
                        
                        if kb_price_num:
                            kb_price = f"{int(kb_price_num):,}"
                            print(f"[WEBHOOK] ✅ KB 시세 조회 성공: 일반 {kb_price}만원", file=sys.stderr, flush=True)
                            logger.info(f"KB 시세 조회 성공: 일반 {kb_price}만원")
                        
                        if kb_price_min_num:
                            kb_price_low = f"{int(kb_price_min_num):,}"
                            print(f"[WEBHOOK] ✅ KB 시세 하한 조회 성공: {kb_price_low}만원", file=sys.stderr, flush=True)
                            logger.info(f"KB 시세 하한 조회 성공: {kb_price_low}만원")
                        
                        # KB API 결과에서 세대수 정보 가져오기 (캡션에 없을 경우)
                        kb_households = kb_result.get('households')
                        if kb_households is not None:
                            if not households:
                                households = str(kb_households)
                                print(f"[WEBHOOK] ✅ KB API에서 세대수 추출: {households}세대", file=sys.stderr, flush=True)
                                logger.info(f"KB API에서 세대수 추출: {households}세대")
                            else:
                                print(f"[WEBHOOK] 세대수는 캡션에서 이미 제공됨: {households}세대", file=sys.stderr, flush=True)
                        
                        # KB API 결과에서 구분 정보 가져오기 (캡션에 없을 경우)
                        kb_type = kb_result.get('type')
                        kb_complex_name = kb_result.get('complex_name', '')
                        kb_complex_type = kb_result.get('complex_type')  # 스크래핑에서 추출한 단지유형
                        if not property_type:
                            # 스크래핑에서 추출한 단지유형 우선 사용 (주상복합, 아파트, 오피스텔)
                            if kb_complex_type:
                                property_type = kb_complex_type
                                print(f"[WEBHOOK] ✅ KB 스크래핑에서 구분 추출: {property_type}", file=sys.stderr, flush=True)
                                logger.info(f"KB 스크래핑에서 구분 추출: {property_type}")
                            # 스크래핑 실패 시 기본값 "아파트"
                            elif kb_type or kb_complex_name:
                                property_type = "아파트"
                                print(f"[WEBHOOK] ✅ KB API에서 구분 추출(기본값): {property_type}", file=sys.stderr, flush=True)
                                logger.info(f"KB API에서 구분 추출(기본값): {property_type}")
                        else:
                            print(f"[WEBHOOK] 구분은 캡션에서 이미 제공됨: {property_type}", file=sys.stderr, flush=True)
                    else:
                        kb_api_no_result = True
                        print(f"[WEBHOOK] ⚠️ KB 시세 조회 실패 (결과 없음)", file=sys.stderr, flush=True)
                        logger.warning("KB 시세 조회 실패 (결과 없음)")
                        # KB 시세 없을 때 공공데이터 실거래가 조회
                        try:
                            from KB_api.kb_price_api import KBPriceAPI
                            from utils.real_transaction_api import get_real_transactions, format_real_transactions_display
                            api = KBPriceAPI()
                            dongcode = api.find_dongcode(address)
                            if dongcode:
                                real_tx = get_real_transactions(
                                    address, dongcode,
                                    area_hint=area_value,
                                    max_items=5
                                )
                                if real_tx:
                                    real_transactions_display = format_real_transactions_display(real_tx)
                                    print(f"[WEBHOOK] ✅ 실거래가 조회 성공: {len(real_tx)}건", file=sys.stderr, flush=True)
                                    logger.info(f"실거래가 조회 성공: {len(real_tx)}건")
                        except Exception as rt_e:
                            logger.debug("실거래가 조회 실패: %s", rt_e)
                except Exception as e:
                    kb_api_failed = True
                    print(f"[WEBHOOK] ❌ KB 시세 조회 중 오류: {str(e)}", file=sys.stderr, flush=True)
                    logger.error(f"KB 시세 조회 중 오류: {str(e)}", exc_info=True)
            
            # KB 시세가 없으면 캡션에서 대체 시세 추출 시도 (감정가, 탁감가, 테크시세 등)
            alternative_price_type = caption_price_type  # 캡션에서 탁감가/감정가로 추출된 경우
            if not kb_price:
                from utils.validators import (
                    extract_bank_appraisal_price_from_special_notes,
                    extract_realestatetech_price_from_special_notes,
                    extract_korea_realestate_price_from_special_notes,
                    extract_housematch_price_from_special_notes
                )
                
                # 캡션을 special_notes로 사용하여 대체 시세 추출
                caption_text = caption or ""
                
                # 우선순위: 감정가/탁감가 > 부동산테크 시세 > 한국부동산원 시세 > 하우스머치 시세
                bank_appraisal_price = extract_bank_appraisal_price_from_special_notes(caption_text)
                if bank_appraisal_price is not None:
                    kb_price = f"{int(bank_appraisal_price):,}"
                    alternative_price_type = "감정가·탁감가"
                    print(f"[WEBHOOK] ✅ 캡션에서 {alternative_price_type} 추출: {kb_price}만원", file=sys.stderr, flush=True)
                    logger.info(f"캡션에서 {alternative_price_type} 추출: {kb_price}만원")
                else:
                    realestatetech_price = extract_realestatetech_price_from_special_notes(caption_text)
                    if realestatetech_price is not None:
                        kb_price = f"{int(realestatetech_price):,}"
                        alternative_price_type = "부동산테크 시세"
                        print(f"[WEBHOOK] ✅ 캡션에서 부동산테크 시세 추출: {kb_price}만원", file=sys.stderr, flush=True)
                        logger.info(f"캡션에서 부동산테크 시세 추출: {kb_price}만원")
                    else:
                        korea_realestate_price = extract_korea_realestate_price_from_special_notes(caption_text)
                        if korea_realestate_price is not None:
                            kb_price = f"{int(korea_realestate_price):,}"
                            alternative_price_type = "한국부동산원 시세"
                            print(f"[WEBHOOK] ✅ 캡션에서 한국부동산원 시세 추출: {kb_price}만원", file=sys.stderr, flush=True)
                            logger.info(f"캡션에서 한국부동산원 시세 추출: {kb_price}만원")
                        else:
                            housematch_price = extract_housematch_price_from_special_notes(caption_text)
                            if housematch_price is not None:
                                kb_price = f"{int(housematch_price):,}"
                                alternative_price_type = "하우스머치 시세"
                                print(f"[WEBHOOK] ✅ 캡션에서 하우스머치 시세 추출: {kb_price}만원", file=sys.stderr, flush=True)
                                logger.info(f"캡션에서 하우스머치 시세 추출: {kb_price}만원")
            
            # KB 시세 없을 때도 로그만 남기고 계속 진행 (고객 정보 전부 출력 후 맨 끝에 멘트 추가)
            if not kb_price:
                if kb_api_searched:
                    if kb_api_failed:
                        print(f"[WEBHOOK] KB API 검색 실패 (예외 발생)", file=sys.stderr, flush=True)
                        logger.warning("KB API 검색 실패 (예외 발생)")
                    elif kb_api_no_result:
                        print(f"[WEBHOOK] KB API 검색 결과 없음", file=sys.stderr, flush=True)
                        logger.warning("KB API 검색 결과 없음")
            
            # 세대수 / 동수, 구분 표시 (KB API 결과로 업데이트된 값 사용)
            buildings = ""
            if kb_result and kb_result.get('buildings') is not None and '개동' not in (households or ''):
                buildings = f" / {kb_result.get('buildings')}개동"
            lines.append(f"세대수 : {households}{buildings}")
            from parsers.registry_parser import apply_no_land_registry_property_type, should_note_no_land_registry
            property_type = apply_no_land_registry_property_type(
                property_type, getattr(result, '대지권미등기', False)
            )
            lines.append(f"구   분 : {property_type}")
            # 사용승인일 (KB 기본정보에서 추출한 경우)
            if kb_result and (kb_result.get('approval_date') or kb_result.get('years_since_completion') is not None):
                approval_str = kb_result.get('approval_date') or ''
                years_str = f"({kb_result.get('years_since_completion')}년차)" if kb_result.get('years_since_completion') is not None else ''
                lines.append(f"사용승인일 : {approval_str} {years_str}".strip())
            # 재건축 정보 (날짜 있는 단계 중 가장 최근 날짜 1개만 출력)
            if kb_result and kb_result.get('redevelop_yn') and kb_result.get('redevelop_stages'):
                stages_with_date = [
                    s for s in kb_result.get('redevelop_stages', [])
                    if s.get('step') and s.get('name') and s.get('date')
                ]
                if stages_with_date:
                    def _parse_redevelop_date(d):
                        try:
                            parts = (d or '').split('.')
                            if len(parts) == 3:
                                return (int(parts[0]), int(parts[1]), int(parts[2]))
                        except (ValueError, AttributeError):
                            pass
                        return (0, 0, 0)
                    latest = max(stages_with_date, key=lambda s: _parse_redevelop_date(s.get('date', '')))
                    step = latest.get('step')
                    name = latest.get('name', '')
                    date_val = latest.get('date', '')
                    lines.append(f"재건축 : {step}단계{name}'{date_val}")
            
            # 시세 표시 (KB 시세인지 대체 시세인지, 없음인지에 따라 다르게 표시)
            if alternative_price_type:
                # 대체 시세 사용 시: "감정가 : 60,000만원" 형식
                lines.append(f"{alternative_price_type} : {kb_price}만원")
            elif kb_price:
                # KB 시세 사용 시: 기존 형식 유지
                lines.append(f"KB시세 : 일반 {kb_price}만원")
                lines.append(f"KB시세 : 하한 {kb_price_low}만원" if kb_price_low else f"KB시세 : 하한      만원")
                # KB 시세 참고 링크 (kbland.kr/c/{단지ID})
                if kb_complex_id:
                    kb_price_url = f"https://kbland.kr/c/{kb_complex_id}"
                    lines.append(f"KB시세 참고 : {kb_price_url}")
            else:
                # KB 시세가 없어도 단지 식별 ID가 있으면 단지 페이지는 안내
                lines.append("KB시세 : 없음")
                lines.append("KB시세 : 하한      만원")
                if kb_complex_id:
                    kb_price_url = f"https://kbland.kr/c/{kb_complex_id}"
                    lines.append(f"KB단지 참고 : {kb_price_url}")
                if real_transactions_display:
                    tx_lines = [ln.strip() for ln in real_transactions_display.split("\n") if ln.strip()]
                    if tx_lines:
                        lines.append(f"실거래가 : {tx_lines[0]}")
                        for ln in tx_lines[1:]:
                            lines.append(f"           {ln}")
            
            # 근저당권 설정 내역
            lines.append(f"=========설정내역=========")
            
            # 신탁 금액 처리 (수탁자인 경우)
            trust_amount = caption_info.get('trust_amount', '')
            trust_amount_man = None
            if is_trustee and trust_amount:
                try:
                    trust_amount_man = int(trust_amount.replace(',', ''))
                    # 신탁 금액을 1순위로 추가
                    lines.append(f"1순위 : 신탁")
                    lines.append(f"           {trust_amount_man:,}만원")
                except (ValueError, TypeError):
                    pass
            
            # 세입자 처리 (캡션에 전세/월세 세입자 키워드 있을 때)
            tenant = caption_info.get('tenant')
            tenant_rank = 2 if (is_trustee and trust_amount_man) else 1  # 신탁 있으면 2순위
            if tenant:
                dep = tenant['deposit_man']
                mon = tenant.get('monthly_rent_man')
                name = tenant['display_name']
                if mon:
                    lines.append(f"{tenant_rank}순위 : {name}")
                    lines.append(f"           {dep:,}만원(100%) / 월세 {mon:,}만원")
                else:
                    lines.append(f"{tenant_rank}순위 : {name}")
                    lines.append(f"           {dep:,}만원(100%)")
            
            # 캡션에서 수동 지정된 비율 및 감액등기 원금 추출
            manual_ratios = extract_manual_ratios(caption or "")
            manual_principals = extract_manual_principals(caption or "")
            needs_principal_check = False  # 깔끔하지 않은 금액이 있는지 체크
            gamak_excluded_creditors = []  # 1천만원 미만 차이로 감액등기 미적용된 금융사
            
            # 기존 근저당권 목록 처리
            if result.근저당권목록:
                total_amount = 0
                mortgage_amounts = []  # 각 근저당권의 채권최고액 만원 단위 저장
                principal_amounts = []  # 각 근저당권의 원금 만원 단위 저장
                
                # 신탁·세입자가 있으면 기존 근저당권 순위를 밀어냄
                start_rank = 1 + (1 if (is_trustee and trust_amount_man) else 0) + (1 if tenant else 0)
                
                rank_offset = (1 if (is_trustee and trust_amount_man) else 0) + (1 if tenant else 0)
                for i, m in enumerate(result.근저당권목록, start=start_rank):
                    gamak_applied = False
                    # 금액을 만원 단위로 변환
                    amount_match = re.search(r'금?\s*([\d,]+)\s*원', m.채권최고액)
                    if amount_match:
                        amount_won = int(amount_match.group(1).replace(',', ''))
                        amount_man = amount_won // 10000  # 만원 단위
                        total_amount += amount_won
                        mortgage_amounts.append(amount_man)
                        
                        # 원금 계산 (신탁·세입자로 순위 밀림 반영)
                        manual_ratio = manual_ratios.get(str(i - rank_offset))
                        principal_won, used_ratio, is_clean = calculate_principal(
                            amount_won, 
                            m.근저당권자,
                            manual_ratio
                        )
                        principal_man = principal_won // 10000
                        principal_amounts.append(principal_man)
                        
                        # 깔끔하지 않으면 플래그 설정
                        if not is_clean and not manual_ratio:
                            needs_principal_check = True
                        
                        # 근저당권자 이름 간소화 (감액등기 매칭용)
                        creditor_raw = m.근저당권자
                        creditor = re.sub(r'주식회사', '', creditor_raw)
                        creditor = re.sub(r'유한회사', '', creditor)
                        creditor = re.sub(r'사단법인', '', creditor)
                        creditor = creditor.strip()
                        
                        # 감액등기: 고객이 원금을 보냈을 때 채권최고액 역산 (차이 1000만원 이상일 때만)
                        manual_principal_man = manual_principals.get(str(i - rank_offset))
                        if manual_principal_man is None:
                            for key, val in manual_principals.items():
                                if key.isdigit():
                                    continue
                                if key in creditor or creditor in key:
                                    manual_principal_man = val
                                    break
                        
                        # 수동 원금 지정 시 항상 반영 (감액등기 여부와 무관, 직접 기재한 원금 사용)
                        if manual_principal_man is not None and getattr(m, '권리종류', '근저당권') != "전세권":
                            principal_man = manual_principal_man
                            principal_amounts[-1] = principal_man
                            new_max_claim_man = int(manual_principal_man * used_ratio / 100)
                            diff_man = abs(amount_man - new_max_claim_man)
                            if diff_man >= 1000:
                                # 감액등기: 채권최고액도 역산하여 표시
                                amount_man = new_max_claim_man
                                mortgage_amounts[-1] = amount_man
                                amount_str = f"{amount_man:,}만({principal_man:,})만원({used_ratio}%)"
                                gamak_applied = True
                            else:
                                # 원금만 수동 지정 (채권최고액은 등기부 그대로)
                                amount_str = f"{amount_man:,} ({principal_man:,})만원({used_ratio}%)"
                        
                        if not gamak_applied:
                            if getattr(m, '권리종류', '근저당권') == "전세권":
                                amount_str = f"{amount_man:,} ({amount_man:,})만원(100%)"
                            else:
                                amount_str = f"{amount_man:,} ({principal_man:,})만원({used_ratio}%)"
                    else:
                        amount_str = m.채권최고액
                        # 만원 단위 추출 시도
                        man_match = re.search(r'([\d,]+)\s*만', amount_str)
                        if man_match:
                            extracted_man = int(man_match.group(1).replace(',', ''))
                            mortgage_amounts.append(extracted_man)
                            principal_amounts.append(extracted_man)  # 원금도 동일하게 추가
                        
                        creditor_raw = m.근저당권자
                        creditor = re.sub(r'주식회사', '', creditor_raw)
                        creditor = re.sub(r'유한회사', '', creditor)
                        creditor = re.sub(r'사단법인', '', creditor)
                        creditor = creditor.strip()
                    
                    # 채무자 정보 + 감액등기 표시
                    debtor = m.채무자 if m.채무자 else ""
                    creditor_line = f"{i}순위 : {creditor}"
                    setup_date = (getattr(m, "설정일", "") or "").strip()
                    meta_parts = []
                    if setup_date:
                        meta_parts.append(setup_date)
                    if debtor:
                        meta_parts.append(debtor)
                    if meta_parts:
                        creditor_line += f"({' / '.join(meta_parts)})"
                    if gamak_applied:
                        creditor_line += " 감액등기"
                    lines.append(creditor_line)
                    lines.append(f"           {amount_str}")
                
                # 신탁·세입자 금액을 mortgage_amounts, principal_amounts에 추가 (LTV 계산용)
                insert_idx = 0
                if is_trustee and trust_amount_man:
                    mortgage_amounts.insert(insert_idx, trust_amount_man)
                    principal_amounts.insert(insert_idx, trust_amount_man)
                    insert_idx += 1
                if tenant:
                    dep = tenant['deposit_man']
                    mortgage_amounts.insert(insert_idx, dep)
                    principal_amounts.insert(insert_idx, dep)  # 세입자도 채권최고액=원금
                
                # KB시세 대비 LTV 계산 (채권최고액 기준 / 원금 기준)
                if kb_price and mortgage_amounts:
                    try:
                        # KB시세 일반가를 만원 단위로 변환
                        kb_price_man = int(kb_price.replace(',', ''))
                        # 채권최고액 합계 계산 (만원 단위)
                        total_mortgage_man = sum(mortgage_amounts)
                        # 원금 합계 계산 (만원 단위)
                        total_principal_man = sum(principal_amounts)
                        # 비율 계산
                        if kb_price_man > 0:
                            ratio_mortgage = (total_mortgage_man / kb_price_man) * 100
                            ratio_principal = (total_principal_man / kb_price_man) * 100
                            lines.append(f"{ratio_mortgage:.2f}% / {ratio_principal:.2f}%")
                    except (ValueError, ZeroDivisionError):
                        pass
            elif is_trustee and trust_amount_man:
                # 신탁만 있고 다른 근저당권이 없는 경우
                mortgage_amounts = [trust_amount_man]
                principal_amounts = [trust_amount_man]  # 신탁은 채권최고액=원금
                if tenant:
                    dep = tenant['deposit_man']
                    mortgage_amounts.append(dep)
                    principal_amounts.append(dep)
                # KB시세 대비 비율 계산 (LTV)
                if kb_price and mortgage_amounts:
                    try:
                        kb_price_man = int(kb_price.replace(',', ''))
                        if kb_price_man > 0:
                            total_man = sum(mortgage_amounts)
                            ratio = (total_man / kb_price_man) * 100
                            lines.append(f"{ratio:.2f}% / {ratio:.2f}%")
                    except (ValueError, ZeroDivisionError):
                        pass
            elif tenant:
                # 세입자만 있고 근저당권이 없는 경우
                dep = tenant['deposit_man']
                mortgage_amounts = [dep]
                principal_amounts = [dep]
                if kb_price:
                    try:
                        kb_price_man = int(kb_price.replace(',', ''))
                        if kb_price_man > 0:
                            ratio = (dep / kb_price_man) * 100
                            lines.append(f"{ratio:.2f}% / {ratio:.2f}%")
                    except (ValueError, ZeroDivisionError):
                        pass
            else:
                lines.append("설정된 근저당권 없음")
            
            lines.append(f"========================")
            
            # 압류/가압류 및 경매 정보 (특이사항에 포함)
            special_notes = []
            
            # 캡션에서 추출한 특이사항 추가 (즉발보유 등)
            if caption_info.get('special_notes'):
                special_notes.extend(caption_info['special_notes'])
            # 감액등기 미적용 (보낸 원금 < 계산 원금, 채권최고액 차이 1천만원 미만)
            for cred in gamak_excluded_creditors:
                special_notes.append(f"{cred} 감액등기 미적용")
            
            if result.압류목록:
                seizure_info = []
                for s in result.압류목록:
                    seizure_info.append(f"{s.종류}({s.권리자})")
                special_notes.append("압류: " + ", ".join(seizure_info))
            
            if result.경매목록:
                auction_info = []
                for a in result.경매목록:
                    auction_info.append(f"{a.종류}({a.채권자})")
                special_notes.append("경매: " + ", ".join(auction_info))
            
            # 환매특약/전매제한 정보 추가
            if hasattr(result, '환매특약') and result.환매특약:
                special_notes.append(result.환매특약)
            
            # 별도등기 정보 추가 (말소되지 않은 경우만)
            if hasattr(result, '별도등기') and result.별도등기:
                special_notes.append("별도등기 있음")

            if should_note_no_land_registry(property_type, getattr(result, '대지권미등기', False)):
                if "대지권미등기" not in " / ".join(special_notes):
                    special_notes.append("대지권미등기")
            
            # 특이사항
            lines.append(f"특이사항 : {' / '.join(special_notes) if special_notes else ''}")
            
            # 요청사항
            request_text = caption_info.get('request', '')
            lines.append(f"요청사항 : {request_text}")
            
            # KB 시세 없을 때 맨 끝에 멘트 추가 (pdf_only 모드에서는 조회 자체를 안 하므로 생략)
            if not kb_price and not pdf_only:
                lines.append("KB시세 없음. 다른 시세 첨부 바랍니다.")
            
            # 근저당권 원금 설정이 깔끔하지 않을 때 확인 필요 멘트 추가
            if needs_principal_check:
                lines.append("*근저당권 원금설정 확인 필요*")
            
            # 수탁자인데 신탁 금액 미기재 시 맨 아래 안내
            if is_trustee and not trust_amount:
                lines.append("신탁 금액 기재 바랍니다.")
            
            return "\n".join(lines)

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
            
            # 명령어 처리 (process_update 없이 _handle_message만 쓸 때 필요)
            # 그룹에서 /help@ARENAHOLDINGS_bot 형태로 오면 cmd에 @뒤 봇이름까지 포함됨 → 앞부분만 비교
            cmd = (message.text or "").strip()
            cmd_base = cmd.split("@")[0].strip() if "@" in cmd else cmd
            if cmd_base == "/start":
                await start_command(update, context)
                return
            if cmd_base in ("/help", "/도움말"):
                await help_command(update, context)
                return
            
            # Render 등 서버 슬립 깨우기: "일어나" → banks_2(PDF 방)에서만 회신
            if (message.text or "").strip() == "일어나":
                if chat_id in allowed_chat_ids_banks_2:
                    global _last_request_time
                    if _last_request_time == 0 or (time.time() - _last_request_time) > 600:
                        await message.reply_text("(벌떡) 깜빡 잠들었습니다. 다시 일하겠습니다.")
                    else:
                        await message.reply_text("네, 이미 깨어있습니다!")
                    return
                # banks_2가 아니면 "일어나"는 무시
            
            # 채팅방 타입 확인 (banks, loan, 또는 banks_2)
            chat_type = get_chat_type(chat_id)
            print(f"[WEBHOOK] Chat type: {chat_type}", file=sys.stderr, flush=True)
            logger.info(f"handle_message - chat_type: {chat_type}")
            
            # PDF 등기부 업로드: banks_2 또는 pdf_only에 포함된 채팅방이면 문서 핸들러로 처리
            if message.document and (chat_id in allowed_chat_ids_banks_2 or chat_id in allowed_chat_ids_pdf_only):
                print(f"[WEBHOOK] PDF in banks_2/pdf_only chat, calling handle_document", file=sys.stderr, flush=True)
                await handle_document(update, context)
                return
            # 다른 방에서 PDF만 보낸 경우 안내 메시지 (무응답 방지)
            if message.document:
                await message.reply_text("등기부 PDF 분석은 등기부·KB시세 전용 방에서 이용해 주세요.")
                return
            
            # 새 멤버 입장 메시지 처리
            if message.new_chat_members:
                logger.info("handle_message - New chat members joined")
                welcome_message = "환영합니다! 🏠\n아레나 담보계산기방입니다."
                try:
                    await message.reply_text(welcome_message)
                except Exception as e:
                    logger.error(f"Error sending welcome message: {str(e)}", exc_info=True)
                return
            
            message_text = message.text
            if not message_text:
                logger.info("handle_message - No text in message")
                return
            
            try:
                print(f"[WEBHOOK] Parsing message text...", file=sys.stderr, flush=True)
                parser = MessageParser()
                property_data = parser.parse(message_text)
                print(f"[WEBHOOK] Parsed - kb_price: {property_data.get('kb_price')}", file=sys.stderr, flush=True)
                logger.info(f"handle_message - property_data parsed: kb_price={property_data.get('kb_price')}")
                
                # 파싱된 데이터가 의미 없는 경우 무시
                has_meaningful_data = any([
                    property_data.get("kb_price") is not None,
                    property_data.get("kb_ai_price") is not None,
                    property_data.get("housematch_price") is not None,
                    property_data.get("address"),
                    property_data.get("property_type"),
                    bool(property_data.get("mortgages"))
                ])
                if not has_meaningful_data:
                    print(f"[WEBHOOK] Parsed data not meaningful, ignoring", file=sys.stderr, flush=True)
                    logger.info("handle_message - Parsed data not meaningful")
                    return
                
                # 필수/추가 정보 누락 체크
                missing_required = []
                missing_optional = []
                
                # KB시세가 없으면 KB API 검색 시도 (주소와 면적이 있는 경우)
                # 대부계산기방(loan): 보낸 메시지 내용만 사용, KB API 호출 안 함
                kb_api_searched = False
                kb_api_failed = False
                kb_api_no_result = False
                
                if not property_data.get("kb_price"):
                    address = property_data.get("address", "")
                    area = property_data.get("area")
                    
                    # 면적: 문자열 그대로 KB API에 전달 (51㎡/37.85㎡ → API에서 전용 37.85 사용)
                    has_area = False
                    if area is not None:
                        if isinstance(area, str) and area.strip():
                            has_area = True
                        else:
                            try:
                                has_area = float(area) > 0
                            except (ValueError, TypeError):
                                pass
                    
                    # 본문에 KB AI시세만 있고 공식 KB시세는 없는 경우: KB API로 kb_price 채우지 않음
                    # (KB시세 전용 금융사에 자동 조회 KB가 섞이는 것 방지, kb_ai_price만 쓰는 은행만 산출)
                    # 파서가 kb_ai를 못 넣었어도 전체 메시지에서 KB AI 패턴이 있으면 동일하게 스킵
                    kb_ai_from_message_text = extract_kb_ai_price_from_special_notes(message_text)
                    skip_kb_api_auto_fill = (
                        property_data.get("price_type") == "kb_ai"
                        and property_data.get("kb_ai_price") is not None
                    ) or kb_ai_from_message_text is not None
                    
                    # 주소와 면적이 있으면 KB API 검색 시도 (면적 문자열 그대로 전달)
                    # loan 방에서는 보낸 내용만 사용하므로 KB API 호출 생략
                    if chat_type != "loan" and address and address != "확인불가" and has_area and not skip_kb_api_auto_fill:
                        kb_api_searched = True
                        try:
                            area_for_kb = str(area).strip() if area else "0"
                            print(f"[WEBHOOK] KB 시세 자동 조회 시작 - 주소: {address}, 면적: {area_for_kb}", file=sys.stderr, flush=True)
                            logger.info(f"KB 시세 자동 조회 시작 - 주소: {address}, 면적: {area_for_kb}")
                            
                            from KB_api.kb_price_api import get_kb_price_from_registry
                            kb_result = get_kb_price_from_registry(address, area_for_kb)
                            
                            if kb_result:
                                kb_price_num = kb_result.get('kb_price')
                                if kb_price_num:
                                    property_data["kb_price"] = kb_price_num
                                    property_data["kb_price_raw"] = f"KB시세: {int(kb_price_num):,}만원"
                                    print(f"[WEBHOOK] ✅ KB 시세 조회 성공: {int(kb_price_num):,}만원", file=sys.stderr, flush=True)
                                    logger.info(f"KB 시세 조회 성공: {int(kb_price_num):,}만원")
                                if kb_result.get('approval_date') is not None:
                                    property_data["approval_date"] = kb_result["approval_date"]
                                if kb_result.get('years_since_completion') is not None:
                                    property_data["years_since_completion"] = kb_result["years_since_completion"]
                                if kb_result.get('households') is not None:
                                    property_data["household_count"] = kb_result["households"]
                                if not kb_price_num:
                                    kb_api_no_result = True
                                    print(f"[WEBHOOK] ⚠️ KB 시세 조회 실패 (결과 없음)", file=sys.stderr, flush=True)
                                    logger.warning("KB 시세 조회 실패 (결과 없음)")
                            else:
                                kb_api_no_result = True
                                print(f"[WEBHOOK] ⚠️ KB 시세 조회 실패 (결과 없음)", file=sys.stderr, flush=True)
                                logger.warning("KB 시세 조회 실패 (결과 없음)")
                        except Exception as e:
                            kb_api_failed = True
                            print(f"[WEBHOOK] ❌ KB 시세 조회 중 오류: {str(e)}", file=sys.stderr, flush=True)
                            logger.error(f"KB 시세 조회 중 오류: {str(e)}", exc_info=True)
                    
                    # KB API 검색 후에도 KB시세가 없으면 적용 가능한 대체 시세 추출 (탁감가·KB AI·하우스머치·부동산테크·한국부동산원)
                    if not property_data.get("kb_price"):
                        special_notes = property_data.get("special_notes", "") or ""
                        bank_appraisal_price = extract_bank_appraisal_price_from_special_notes(special_notes)
                        kb_ai_price = property_data.get("kb_ai_price") or extract_kb_ai_price_from_special_notes(
                            special_notes
                        ) or extract_kb_ai_price_from_special_notes(message_text)
                        housematch_price = property_data.get("housematch_price") or extract_housematch_price_from_special_notes(special_notes)
                        realestatetech_price = extract_realestatetech_price_from_special_notes(special_notes)
                        korea_realestate_price = extract_korea_realestate_price_from_special_notes(special_notes)
                        has_alternative_price = any([
                            bank_appraisal_price is not None,
                            kb_ai_price is not None,
                            housematch_price is not None,
                            realestatetech_price is not None,
                            korea_realestate_price is not None,
                        ])
                        if has_alternative_price:
                            # 적용 가능한 시세가 하나라도 있으면 한도 산출 진행 (해당 시세를 사용하는 금융사만 결과 나옴)
                            if kb_ai_price is not None and not property_data.get("kb_ai_price"):
                                property_data["kb_ai_price"] = kb_ai_price
                                property_data["price_type"] = "kb_ai"
                            if housematch_price is not None and not property_data.get("housematch_price"):
                                property_data["housematch_price"] = housematch_price
                                property_data["price_type"] = "housematch"
                            price_sources_found = [p for p, v in [
                                ("감정가·탁감가", bank_appraisal_price),
                                ("KB AI시세", kb_ai_price),
                                ("하우스머치", housematch_price),
                                ("부동산테크", realestatetech_price),
                                ("한국부동산원", korea_realestate_price),
                            ] if v is not None]
                            print(f"[WEBHOOK] 적용 가능 시세로 한도 산출 진행: {', '.join(price_sources_found)}", file=sys.stderr, flush=True)
                            logger.info(f"handle_message - 적용 가능 시세로 한도 산출 진행: {price_sources_found}")
                        else:
                            # KB API 검색을 했는지, 실패했는지, 결과가 없었는지 구분
                            if kb_api_searched:
                                if kb_api_failed:
                                    print(f"[WEBHOOK] KB API 검색 실패 (예외 발생)", file=sys.stderr, flush=True)
                                    logger.warning("KB API 검색 실패 (예외 발생)")
                                elif kb_api_no_result:
                                    print(f"[WEBHOOK] KB API 검색 결과 없음", file=sys.stderr, flush=True)
                                    logger.warning("KB API 검색 결과 없음")
                            missing_required.append("KB시세")
                if not property_data.get("address") or not property_data.get("region"):
                    missing_required.append("주소(시/구 포함)")
                
                if not property_data.get("mortgages"):
                    missing_optional.append("선순위 근저당권 설정내역(기관명, 채권최고액/원금)")
                if not property_data.get("property_type"):
                    missing_optional.append("물건 유형(아파트/빌라/오피스텔 등)")
                
                if missing_required:
                    # KB시세가 필수 항목에 있고, KB API 검색을 했지만 결과가 없고, 탁감가/감정가도 없을 때
                    if "KB시세" in missing_required and kb_api_searched:
                        error_message = "KB 시세가 검색되지 않으므로 다른 시세 첨부 부탁드립니다"
                        await message.reply_text(error_message)
                        logger.info("handle_message - KB 시세 검색 실패, 메시지 전송")
                        return
                    
                    lines = ["한도 산출을 위해 아래 정보가 필요합니다."]
                    for item in missing_required:
                        lines.append(f"- {item}")
                    if missing_optional:
                        lines.append("")
                        lines.append("추가로 있으면 함께 보내주세요:")
                        lines.append("- " + ", ".join(missing_optional))
                    await message.reply_text("\n".join(lines))
                    logger.info("handle_message - Missing required data, reply sent")
                    return
                
                print(f"[WEBHOOK] Calculating results for chat_type: {chat_type}...", file=sys.stderr, flush=True)
                # 채팅방 타입에 따라 다른 계산 함수 호출
                if chat_type == "loan":
                    results = BaseCalculator.calculate_all_loans(property_data)
                else:  # banks 또는 None (기본값)
                    results = BaseCalculator.calculate_all_banks(property_data)
                print(f"[WEBHOOK] Results count: {len(results) if results else 0}", file=sys.stderr, flush=True)
                logger.info(f"handle_message - results count: {len(results) if results else 0}")
                
                formatted_result = format_all_results(results, property_data)
                
                if missing_optional:
                    formatted_result += (
                        "\n\n추가 정보가 있으면 반영해 드릴게요:\n- "
                        + ", ".join(missing_optional)
                    )
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
        app.add_handler(CommandHandler("start", start_command))
        app.add_handler(CommandHandler("help", help_command))
        # '도움말'은 BotFather에 등록되지 않으면 PTB가 ValueError를 던지므로, handle_message에서만 처리
        app.add_handler(MessageHandler(~filters.COMMAND, handle_message))
        
        # handle_message를 전역에서 접근 가능하도록 저장
        app._handle_message = handle_message

        return app

    if force_new:
        return _build()
    if telegram_application is None:
        telegram_application = _build()
    return telegram_application


async def application(scope, receive, send):
    """
    Vercel Python Runtime 엔트리포인트 (ASGI).

    - Vercel이 `api.webhook:application`을 ASGI/WSGI 앱으로 로드하려고 하므로,
      기존 BaseHTTPRequestHandler 방식 대신 ASGI callable을 제공한다.
    """
    if scope.get("type") != "http":
        return

    method = (scope.get("method") or "GET").upper()
    path = scope.get("path") or "/"

    async def _send_json(status_code: int, data: dict):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        headers = [
            (b"content-type", b"application/json; charset=utf-8"),
            (b"content-length", str(len(body)).encode("utf-8")),
        ]
        await send({"type": "http.response.start", "status": status_code, "headers": headers})
        await send({"type": "http.response.body", "body": body})

    # 헬스체크
    if method == "GET":
        return await _send_json(200, {"ok": True, "message": "Webhook endpoint is active"})

    if method != "POST":
        return await _send_json(405, {"ok": False, "error": "Method not allowed"})

    # 요청 body 수신
    body_bytes = b""
    while True:
        event = await receive()
        if event.get("type") != "http.request":
            continue
        body_bytes += event.get("body", b"")
        if not event.get("more_body"):
            break

    if not body_bytes:
        return await _send_json(200, {"ok": True, "skipped": "empty body"})

    try:
        body_str = body_bytes.decode("utf-8")
    except Exception:
        return await _send_json(200, {"ok": True, "skipped": "invalid encoding"})

    try:
        payload = json.loads(body_str) if body_str else {}
    except json.JSONDecodeError:
        return await _send_json(200, {"ok": True, "skipped": "invalid JSON"})

    # 텔레그램 update 형식 검증
    if not isinstance(payload, dict) or "update_id" not in payload:
        return await _send_json(200, {"ok": True, "skipped": "not telegram update"})

    try:
        from telegram import Update

        # 요청마다 새 Application 사용 (Vercel 환경에서 루프/상태 꼬임 방지)
        app = get_application(force_new=True)
        update = Update.de_json(payload, app.bot)

        async def _process():
            if not app._initialized:
                await app.initialize()
            if hasattr(app, "_handle_message"):
                await app._handle_message(update, None)
            else:
                await app.process_update(update)

        await _process()

        try:
            global _last_request_time
            _last_request_time = time.time()
        except Exception:
            pass

        return await _send_json(200, {"ok": True})
    except Exception as e:
        logger.error("ASGI webhook error: %s", str(e), exc_info=True)
        return await _send_json(500, {"ok": False, "error": str(e)})


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
        # 여러 방법으로 로그 출력 (가장 먼저 실행)
        sys.stderr.write("=" * 80 + "\n")
        sys.stderr.write("[WEBHOOK] ===== POST REQUEST RECEIVED =====\n")
        sys.stderr.write("=" * 80 + "\n")
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

            # 텔레그램 업데이트 처리: 요청마다 새 루프 + 이번 요청 전용 Application (Event loop is closed 방지)
            from telegram import Update
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            app = get_application(force_new=True)
            update = Update.de_json(body, app.bot)
            print("[WEBHOOK] Processing telegram update...", file=sys.stderr, flush=True)
            print(f"[WEBHOOK] Update ID: {update.update_id}", file=sys.stderr, flush=True)
            logger.info(f"Received update - update_id: {update.update_id}")

            # 텔레그램 재시도 루프 방지: 이미 처리한 update_id 무시
            global _processed_update_ids, _MAX_CACHED_UPDATE_IDS
            uid = update.update_id
            if uid in _processed_update_ids:
                print(f"[WEBHOOK] Duplicate update_id {uid}, skipping (Telegram retry)", file=sys.stderr, flush=True)
                logger.info(f"Duplicate update_id {uid}, skipping")
                self._send_response(200, {"ok": True, "skipped": "duplicate update_id"})
                return
            # 캐시 크기 제한 (오래된 것부터 제거)
            if len(_processed_update_ids) >= _MAX_CACHED_UPDATE_IDS:
                _processed_update_ids.clear()
            _processed_update_ids.add(uid)

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

            # 허용된 채팅방 ID 확인 (1번방: banks, 2번방: loan, 3번방: banks_2, pdf_only - PDF 파싱만)
            ALLOWED_CHAT_IDS_BANKS_STR = os.getenv("ALLOWED_CHAT_IDS_BANKS")
            ALLOWED_CHAT_IDS_LOAN_STR = os.getenv("ALLOWED_CHAT_IDS_LOAN")
            ALLOWED_CHAT_IDS_BANKS_2_STR = os.getenv("ALLOWED_CHAT_IDS_BANKS_2")
            ALLOWED_CHAT_IDS_PDF_ONLY_STR = os.getenv("ALLOWED_CHAT_IDS_PDF_ONLY")
            
            if not ALLOWED_CHAT_IDS_BANKS_STR:
                try:
                    from config.telegram_config import ALLOWED_CHAT_IDS_BANKS  # type: ignore
                    ALLOWED_CHAT_IDS_BANKS_STR = ALLOWED_CHAT_IDS_BANKS
                except (ModuleNotFoundError, ImportError):
                    ALLOWED_CHAT_IDS_BANKS_STR = None
            
            if not ALLOWED_CHAT_IDS_LOAN_STR:
                try:
                    from config.telegram_config import ALLOWED_CHAT_IDS_LOAN  # type: ignore
                    ALLOWED_CHAT_IDS_LOAN_STR = ALLOWED_CHAT_IDS_LOAN
                except (ModuleNotFoundError, ImportError):
                    ALLOWED_CHAT_IDS_LOAN_STR = None
            
            if not ALLOWED_CHAT_IDS_BANKS_2_STR:
                try:
                    from config.telegram_config import ALLOWED_CHAT_IDS_BANKS_2  # type: ignore
                    ALLOWED_CHAT_IDS_BANKS_2_STR = ALLOWED_CHAT_IDS_BANKS_2
                except (ModuleNotFoundError, ImportError):
                    ALLOWED_CHAT_IDS_BANKS_2_STR = None

            if not ALLOWED_CHAT_IDS_PDF_ONLY_STR:
                try:
                    from config.telegram_config import ALLOWED_CHAT_IDS_PDF_ONLY  # type: ignore
                    ALLOWED_CHAT_IDS_PDF_ONLY_STR = ALLOWED_CHAT_IDS_PDF_ONLY
                except (ModuleNotFoundError, ImportError, AttributeError):
                    ALLOWED_CHAT_IDS_PDF_ONLY_STR = None

            allowed_chat_ids_banks = []
            if ALLOWED_CHAT_IDS_BANKS_STR:
                allowed_chat_ids_banks = [int(chat_id.strip()) for chat_id in ALLOWED_CHAT_IDS_BANKS_STR.split(",") if chat_id.strip()]

            allowed_chat_ids_loan = []
            if ALLOWED_CHAT_IDS_LOAN_STR:
                allowed_chat_ids_loan = [int(chat_id.strip()) for chat_id in ALLOWED_CHAT_IDS_LOAN_STR.split(",") if chat_id.strip()]

            allowed_chat_ids_banks_2 = []
            if ALLOWED_CHAT_IDS_BANKS_2_STR:
                allowed_chat_ids_banks_2 = [int(chat_id.strip()) for chat_id in ALLOWED_CHAT_IDS_BANKS_2_STR.split(",") if chat_id.strip()]

            allowed_chat_ids_pdf_only = []
            if ALLOWED_CHAT_IDS_PDF_ONLY_STR:
                allowed_chat_ids_pdf_only = [int(chat_id.strip()) for chat_id in ALLOWED_CHAT_IDS_PDF_ONLY_STR.split(",") if chat_id.strip()]

            # 전체 허용된 채팅방 ID (모두 합침)
            allowed_chat_ids = allowed_chat_ids_banks + allowed_chat_ids_loan + allowed_chat_ids_banks_2 + allowed_chat_ids_pdf_only

            print(f"[WEBHOOK] Allowed chat IDs - banks: {allowed_chat_ids_banks}, loan: {allowed_chat_ids_loan}, banks_2: {allowed_chat_ids_banks_2}, pdf_only: {allowed_chat_ids_pdf_only}", file=sys.stderr, flush=True)
            logger.info(f"chat_id: {chat_id}, allowed_chat_ids_banks: {allowed_chat_ids_banks}, allowed_chat_ids_loan: {allowed_chat_ids_loan}, allowed_chat_ids_banks_2: {allowed_chat_ids_banks_2}")

            # 허용된 채팅방이 설정되어 있고, 현재 채팅방이 허용 목록에 없으면 무시
            if allowed_chat_ids and chat_id not in allowed_chat_ids:
                print(f"[WEBHOOK] Chat {chat_id} is NOT in allowed list, ignoring", file=sys.stderr, flush=True)
                logger.warning(f"Chat {chat_id} is not in allowed list, ignoring update")
                self._send_response(200, {"ok": True, "skipped": "chat not allowed"})
                return

            print(f"[WEBHOOK] Chat {chat_id} is allowed, processing message", file=sys.stderr, flush=True)

            # 텔레그램 재시도 루프 방지: 처리 전에 즉시 200 OK 반환
            # (Vercel 60초 타임아웃으로 응답이 전달되지 않으면 텔레그램이 수 시간 재시도함)
            self._send_response(200, {"ok": True})
            print("[WEBHOOK] 200 OK sent immediately (before processing)", file=sys.stderr, flush=True)

            async def process():
                try:
                    print("[WEBHOOK] Starting async process", file=sys.stderr, flush=True)
                    if not app._initialized:
                        print("[WEBHOOK] Initializing application", file=sys.stderr, flush=True)
                        await app.initialize()
                    if hasattr(app, '_handle_message'):
                        print("[WEBHOOK] Processing update with _handle_message", file=sys.stderr, flush=True)
                        await app._handle_message(update, None)
                    else:
                        logger.warning("_handle_message not found, using process_update")
                        await app.process_update(update)
                    print("[WEBHOOK] Message processing completed", file=sys.stderr, flush=True)
                    logger.info("Message processing completed")
                except Exception as e:
                    print(f"[WEBHOOK] Error in process() - reply NOT sent: {str(e)}", file=sys.stderr, flush=True)
                    logger.error(f"Error in process(): {str(e)}", exc_info=True)
                    import traceback
                    traceback.print_exc()

            # 위에서 이미 생성한 루프로 process 실행
            try:
                loop.run_until_complete(process())
            except Exception as e:
                print(f"[WEBHOOK] run_until_complete error: {str(e)}", file=sys.stderr, flush=True)
                logger.error(f"run_until_complete error: {str(e)}", exc_info=True)
            finally:
                try:
                    loop.close()
                except Exception:
                    pass

            try:
                global _last_request_time
                _last_request_time = time.time()
            except Exception:
                pass
            print("[WEBHOOK] Processing completed", file=sys.stderr, flush=True)
            # 200 OK는 이미 처리 시작 전에 전송됨

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
