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

        # 허용된 채팅방 ID 가져오기 (1번방: banks, 2번방: loan, 3번방: banks_2 - PDF 등기부등본 분석)
        ALLOWED_CHAT_IDS_BANKS_STR = os.getenv("ALLOWED_CHAT_IDS_BANKS")
        ALLOWED_CHAT_IDS_LOAN_STR = os.getenv("ALLOWED_CHAT_IDS_LOAN")
        ALLOWED_CHAT_IDS_BANKS_2_STR = os.getenv("ALLOWED_CHAT_IDS_BANKS_2")
        
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
        
        # 전체 허용된 채팅방 ID (모두 합침)
        allowed_chat_ids = allowed_chat_ids_banks + allowed_chat_ids_loan + allowed_chat_ids_banks_2
        
        print(f"[WEBHOOK] Application initializing - allowed_chat_ids_banks: {allowed_chat_ids_banks}, allowed_chat_ids_loan: {allowed_chat_ids_loan}, allowed_chat_ids_banks_2: {allowed_chat_ids_banks_2}", file=sys.stderr, flush=True)
        logger.info(f"Application initialized - allowed_chat_ids_banks: {allowed_chat_ids_banks}, allowed_chat_ids_loan: {allowed_chat_ids_loan}, allowed_chat_ids_banks_2: {allowed_chat_ids_banks_2}")

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
                "/help - 도움말 보기\n\n"
                "이제 담보물건 정보를 보내주시면 계산해드리겠습니다! 🚀"
            )
            try:
                await message.reply_text(welcome_message)
            except Exception as e:
                logger.error(f"Error sending welcome message: {str(e)}", exc_info=True)

        async def handle_document(update, context=None):
            """PDF 문서 처리 핸들러 (등기부등본 분석)"""
            message = update.message or update.channel_post or update.edited_message or update.edited_channel_post
            
            if not message:
                return
            
            chat_id = get_chat_id(update)
            if not is_allowed_chat(chat_id):
                return
            
            chat_type = get_chat_type(chat_id)
            
            # banks_2 채팅방에서만 PDF 분석 수행
            if chat_type != "banks_2":
                return
            
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
            
            processing_msg = None  # 분석 중 메시지 저장용
            try:
                # 파일 다운로드
                processing_msg = await message.reply_text(f"📄 등기부등본 분석 중... ({file_name})")
                
                file = await document.get_file()
                file_bytes = await file.download_as_bytearray()
                
                # PDF 분석
                import tempfile
                from parsers.registry_parser import analyze_pdf
                
                # 임시 파일로 저장 후 분석
                with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp_file:
                    tmp_file.write(file_bytes)
                    tmp_path = tmp_file.name
                
                try:
                    result = analyze_pdf(tmp_path)
                    
                    # 메시지에 함께 온 텍스트 (캡션) 확인
                    caption = message.caption or ""
                    
                    # 결과 포맷팅
                    response = format_registry_result(result, caption, file_name)
                    
                    # "분석 중" 메시지 삭제
                    if processing_msg:
                        try:
                            await processing_msg.delete()
                        except Exception as del_err:
                            print(f"[WEBHOOK] Failed to delete processing message: {str(del_err)}", file=sys.stderr, flush=True)
                    
                    await message.reply_text(response)
                    
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
                
                await message.reply_text(f"❌ PDF 분석 중 오류가 발생했습니다.\n\n오류: {str(e)}")

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
            # 가라사업자는 별도 처리
            if re.search(r'가라\s*사업자', caption):
                info['job'] = '사업자'
                info['special_notes'].append('즉발보유(부가세 누락신고 조건)')
            else:
                job_patterns = [
                    (r'사업자', '사업자'),
                    (r'직장인', '직장인'),
                    (r'프리랜서', '프리랜서'),
                    (r'무직', '무직'),
                    (r'자영업', '자영업'),
                    (r'공무원', '공무원'),
                    (r'전문직', '전문직'),
                ]
                for pattern, job_name in job_patterns:
                    if re.search(pattern, caption):
                        info['job'] = job_name
                        break
            
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
            
            # 거주여부 추출
            if re.search(r'거주|실거주|본인\s*거주', caption):
                info['residence'] = '거주'
            elif re.search(r'비거주|임대|전세', caption):
                info['residence'] = '비거주'
            
            # 세대수 추출 (세대수 700, 700세대 등)
            households_patterns = [
                r'세대\s*[수]*\s*[:：]?\s*(\d+)',
                r'(\d+)\s*세대',
            ]
            for pattern in households_patterns:
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
            
            # KB시세 추출 (일반가 7000만, kb시세 7000, 시세 7000만원 등)
            kb_patterns = [
                r'(?:kb\s*)?(?:시세|일반\s*가?)\s*[:：]?\s*(\d+(?:,\d+)?)\s*만?\s*(?:원)?',
                r'(\d+(?:,\d+)?)\s*만\s*원?\s*(?:시세|일반)',
            ]
            for pattern in kb_patterns:
                match = re.search(pattern, caption, re.IGNORECASE)
                if match:
                    price = match.group(1).replace(',', '')
                    info['kb_price'] = f"{int(price):,}"
                    break
            
            # KB시세 하한 추출 (하한 6500, 하한가 6500만, KB하한가 240,000만 등)
            kb_low_patterns = [
                r'(?:kb\s*)?하한\s*[가]?\s*[:：]?\s*(\d+(?:,\d+)?)\s*만?\s*(?:원)?',
            ]
            for pattern in kb_low_patterns:
                match = re.search(pattern, caption, re.IGNORECASE)
                if match:
                    price = match.group(1).replace(',', '')
                    info['kb_price_low'] = f"{int(price):,}"
                    break
            
            return info

        def format_registry_result(result, caption, file_name):
            """등기부등본 분석 결과를 텔레그램 메시지 형식으로 포맷"""
            import re
            
            # 캡션에서 추가 정보 추출
            caption_info = parse_caption_info(caption)
            
            lines = []
            
            # 소유자 정보 (이름, 나이)
            # 차주/담보제공자 구분이 있는 경우 처리
            borrower = caption_info.get('borrower_name', '')
            collateral_provider = caption_info.get('collateral_provider', '')
            
            if result.소유자목록:
                owner = result.소유자목록[0]
                # 생년월일에서 나이 계산
                age = ""
                if owner.생년월일:
                    try:
                        birth_year = int(owner.생년월일.split('.')[0])
                        from datetime import datetime
                        current_year = datetime.now().year
                        calculated_age = current_year - birth_year
                        age = f"({calculated_age})"  # 만 나이
                    except:
                        age = ""
                
                # 차주/담보제공자 구분이 있는 경우
                if borrower and collateral_provider:
                    # 담보제공자 나이 (등기부 소유자 = 담보제공자)
                    name_display = f"{borrower}(차), {collateral_provider}(담) {age}"
                elif borrower:
                    # 차주만 있는 경우 (담보제공자는 등기부 소유자)
                    name_display = f"{borrower}(차), {owner.성명}(담) {age}"
                else:
                    # 일반적인 경우 (등기부 소유자가 차주)
                    name_display = f"{owner.성명} {age}"
                
                lines.append(f"성   명 : {name_display}")
                lines.append(f"직   업 : {caption_info['job']}")
                lines.append(f"신용점수 : {caption_info['credit_score']}")
                lines.append(f"거주여부 : {caption_info['residence']}")
                
                # 소유현황
                share = owner.지분 if owner.지분 else "단독소유"
                lines.append(f"소유현황 : {share}")
            else:
                # 등기부에서 소유자를 못 찾은 경우
                if borrower and collateral_provider:
                    name_display = f"{borrower}(차), {collateral_provider}(담)"
                elif borrower:
                    name_display = f"{borrower}(차)"
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
            
            # 층수 정보에서 총층수 추출
            total_floor = ""
            unit_info = ""
            if floor_info:
                # "15층 중 2층 203호" 또는 "17층 1802호" 형태에서 파싱
                # 총층수: 첫번째 숫자+층
                floor_match = re.search(r'(\d+)층\s*중', floor_info)
                if floor_match:
                    total_floor = f"{floor_match.group(1)}층"
                else:
                    # "17층 1802호" 형태에서 17층 추출
                    floor_match = re.search(r'^(\d+)층', floor_info)
                    if floor_match:
                        total_floor = f"{floor_match.group(1)}층"
                
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
            
            # 면적
            lines.append(f"면   적 : {result.면적 or ''}")
            
            # 세대수, 구분, KB시세 (캡션에서 추출한 정보 사용)
            lines.append(f"세대수 : {caption_info['households']}")
            lines.append(f"구   분 : {caption_info['property_type']}")
            
            kb_price = caption_info['kb_price']
            kb_price_low = caption_info['kb_price_low']
            lines.append(f"KB시세 : 일반 {kb_price}만원" if kb_price else f"KB시세 : 일반      만원")
            lines.append(f"KB시세 : 하한 {kb_price_low}만원" if kb_price_low else f"KB시세 : 하한      만원")
            
            # 근저당권 설정 내역
            lines.append(f"=========설정내역=========")
            
            if result.근저당권목록:
                total_amount = 0
                for i, m in enumerate(result.근저당권목록, 1):
                    # 금액을 만원 단위로 변환
                    amount_match = re.search(r'([\d,]+)\s*원', m.채권최고액)
                    if amount_match:
                        amount_won = int(amount_match.group(1).replace(',', ''))
                        amount_man = amount_won // 10000  # 만원 단위
                        total_amount += amount_won
                        amount_str = f"{amount_man:,}만원"
                    else:
                        amount_str = m.채권최고액
                    
                    # 근저당권자 이름 간소화 (주식회사, 유한회사 등 제거)
                    creditor = m.근저당권자
                    creditor = re.sub(r'^주식회사', '', creditor)
                    creditor = re.sub(r'^유한회사', '', creditor)
                    creditor = re.sub(r'^사단법인', '', creditor)
                    creditor = creditor.strip()
                    
                    lines.append(f"{i}순위 : {creditor}")
                    lines.append(f"           {amount_str}")
            else:
                lines.append("설정된 근저당권 없음")
            
            lines.append(f"========================")
            
            # 압류/가압류 및 경매 정보 (특이사항에 포함)
            special_notes = []
            
            # 캡션에서 추출한 특이사항 추가 (즉발보유 등)
            if caption_info.get('special_notes'):
                special_notes.extend(caption_info['special_notes'])
            
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
            
            # 특이사항
            lines.append(f"특이사항 : {' / '.join(special_notes) if special_notes else ''}")
            lines.append(f"요청사항 : ")
            
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
            
            # 채팅방 타입 확인 (banks, loan, 또는 banks_2)
            chat_type = get_chat_type(chat_id)
            print(f"[WEBHOOK] Chat type: {chat_type}", file=sys.stderr, flush=True)
            logger.info(f"handle_message - chat_type: {chat_type}")
            
            # banks_2 채팅방에서 문서(PDF)가 있으면 문서 핸들러로 처리
            if chat_type == "banks_2" and message.document:
                await handle_document(update, context)
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
            
            # 특정 양식이 있는 메시지만 처리
            # '성   명' 또는 '성명', '직   업' 또는 '직업', '거주여부' 모두 포함되어야 함
            required_keywords = [
                ['성   명', '성명'],  # 둘 중 하나만 있으면 됨
                ['직   업', '직업'],  # 둘 중 하나만 있으면 됨
                ['거주여부']  # 정확히 일치해야 함
            ]
            
            # 각 키워드 그룹에서 최소 하나는 포함되어야 함
            has_all_keywords = True
            for keyword_group in required_keywords:
                found = False
                for keyword in keyword_group:
                    if keyword in message_text:
                        found = True
                        break
                if not found:
                    has_all_keywords = False
                    break
            
            if not has_all_keywords:
                print(f"[WEBHOOK] Message does not contain required format, ignoring", file=sys.stderr, flush=True)
                logger.info("handle_message - Message does not contain required format (성명, 직업, 거주여부)")
                # 양식이 없는 메시지는 무시 (회신하지 않음)
                return
            
            try:
                print(f"[WEBHOOK] Parsing message text...", file=sys.stderr, flush=True)
                parser = MessageParser()
                property_data = parser.parse(message_text)
                print(f"[WEBHOOK] Parsed - kb_price: {property_data.get('kb_price')}", file=sys.stderr, flush=True)
                logger.info(f"handle_message - property_data parsed: kb_price={property_data.get('kb_price')}")
                
                print(f"[WEBHOOK] Calculating results for chat_type: {chat_type}...", file=sys.stderr, flush=True)
                # 채팅방 타입에 따라 다른 계산 함수 호출
                if chat_type == "loan":
                    results = BaseCalculator.calculate_all_loans(property_data)
                else:  # banks 또는 None (기본값)
                    results = BaseCalculator.calculate_all_banks(property_data)
                print(f"[WEBHOOK] Results count: {len(results) if results else 0}", file=sys.stderr, flush=True)
                logger.info(f"handle_message - results count: {len(results) if results else 0}")
                
                formatted_result = format_all_results(results, property_data)
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

            # 허용된 채팅방 ID 확인 (1번방: banks, 2번방: loan, 3번방: banks_2 - PDF 등기부등본 분석)
            ALLOWED_CHAT_IDS_BANKS_STR = os.getenv("ALLOWED_CHAT_IDS_BANKS")
            ALLOWED_CHAT_IDS_LOAN_STR = os.getenv("ALLOWED_CHAT_IDS_LOAN")
            ALLOWED_CHAT_IDS_BANKS_2_STR = os.getenv("ALLOWED_CHAT_IDS_BANKS_2")
            
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

            allowed_chat_ids_banks = []
            if ALLOWED_CHAT_IDS_BANKS_STR:
                allowed_chat_ids_banks = [int(chat_id.strip()) for chat_id in ALLOWED_CHAT_IDS_BANKS_STR.split(",") if chat_id.strip()]

            allowed_chat_ids_loan = []
            if ALLOWED_CHAT_IDS_LOAN_STR:
                allowed_chat_ids_loan = [int(chat_id.strip()) for chat_id in ALLOWED_CHAT_IDS_LOAN_STR.split(",") if chat_id.strip()]

            allowed_chat_ids_banks_2 = []
            if ALLOWED_CHAT_IDS_BANKS_2_STR:
                allowed_chat_ids_banks_2 = [int(chat_id.strip()) for chat_id in ALLOWED_CHAT_IDS_BANKS_2_STR.split(",") if chat_id.strip()]

            # 전체 허용된 채팅방 ID (모두 합침)
            allowed_chat_ids = allowed_chat_ids_banks + allowed_chat_ids_loan + allowed_chat_ids_banks_2

            print(f"[WEBHOOK] Allowed chat IDs - banks: {allowed_chat_ids_banks}, loan: {allowed_chat_ids_loan}, banks_2: {allowed_chat_ids_banks_2}", file=sys.stderr, flush=True)
            logger.info(f"chat_id: {chat_id}, allowed_chat_ids_banks: {allowed_chat_ids_banks}, allowed_chat_ids_loan: {allowed_chat_ids_loan}, allowed_chat_ids_banks_2: {allowed_chat_ids_banks_2}")

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
