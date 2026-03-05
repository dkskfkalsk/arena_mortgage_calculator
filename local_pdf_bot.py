#!/usr/bin/env python3
"""
로컬 PDF 처리 전용 텔레그램 봇 (Polling 방식)
- 등기부 PDF를 받아서 파싱하고 KB 시세 조회
- Vercel webhook과 독립적으로 실행
"""

import os
import sys
import logging
from pathlib import Path
from datetime import datetime
import tempfile
import re
import asyncio
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

from utils.mortgage_calculator import calculate_principal, extract_manual_ratios, extract_manual_principals

# .env.local 로드
load_dotenv('.env.local')

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s - %(name)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('pdf_bot.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

# Telegram 봇 토큰
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_PDF_BOT_TOKEN')

if not TELEGRAM_BOT_TOKEN:
    raise ValueError("TELEGRAM_PDF_BOT_TOKEN이 .env.local 파일에 설정되지 않았습니다!")

# temp 폴더 생성
TEMP_DIR = Path(__file__).parent / 'temp'
TEMP_DIR.mkdir(exist_ok=True)


def parse_complex_amount(text):
    """복합 금액 파싱 → 만원 단위 정수 (웹훅과 동일)"""
    if not text:
        return None
    text_clean = text.replace(',', '').replace('，', '')
    text_no_space = text_clean.replace(' ', '').replace('　', '')
    # 억+천만
    m = re.search(r'(\d+)\s*억\s*(\d+)\s*천\s*만\s*원?', text_clean) or re.search(r'(\d+)억(\d+)천만원?', text_no_space)
    if m:
        return int(m.group(1)) * 10000 + int(m.group(2)) * 1000
    # 억+만
    m = re.search(r'(\d+)\s*억\s*(\d+)\s*만\s*원?', text_clean) or re.search(r'(\d+)억(\d+)만원?', text_no_space)
    if m:
        return int(m.group(1)) * 10000 + int(m.group(2))
    # 억+원
    m = re.search(r'(\d+)\s*억\s*(\d+)\s*원', text_clean)
    if m:
        return int(m.group(1)) * 10000 + int(m.group(2)) // 10000
    # 억
    m = re.search(r'(\d+)\s*억\s*원?', text_clean)
    if m:
        return int(m.group(1)) * 10000
    # 천만
    m = re.search(r'(\d+)\s*천\s*만\s*원?', text_clean)
    if m:
        return int(m.group(1)) * 1000
    # 만
    m = re.search(r'(\d+)\s*만\s*원?', text_clean)
    if m:
        return int(m.group(1))
    # 원
    m = re.search(r'(\d+)\s*원', text_clean)
    if m:
        return int(m.group(1)) // 10000
    # 숫자만
    m = re.search(r'^(\d+)$', text_clean)
    if m:
        return int(m.group(1))
    return None


def parse_caption_info(caption):
    """캡션에서 고객 정보 추출 (웹훅과 동일 항목: trust_amount, special_notes 포함)"""
    info = {
        'job': '',
        'credit_score': '',
        'residence': '',
        'borrower_name': '',
        'collateral_provider': '',
        'request': '',
        'trust_amount': '',   # 신탁 금액 (만원 단위 문자열)
        'special_notes': [],  # 특이사항
    }
    
    if not caption:
        return info
    
    # 차주/담보제공자 구분 추출
    borrower_match = re.search(r'([가-힣]+)\s*\(\s*(?:차주?|차)\s*\)', caption)
    if borrower_match:
        info['borrower_name'] = borrower_match.group(1)
    
    collateral_match = re.search(r'([가-힣]+)\s*\(\s*(?:담보?|담)\s*\)', caption)
    if collateral_match:
        info['collateral_provider'] = collateral_match.group(1)
    
    # 직업 추출
    job_patterns = [
        (r'직장인', '직장인'),
        (r'사업자', '사업자'),
        (r'프리랜서', '프리랜서'),
        (r'무직', '무직'),
    ]
    for pattern, job_name in job_patterns:
        if re.search(pattern, caption):
            info['job'] = job_name
            break
    
    # 신용등급 추출
    grade_match = re.search(r'(\d{1,2})\s*등급', caption)
    if grade_match:
        grade = int(grade_match.group(1))
        if 1 <= grade <= 10:
            info['credit_score'] = f"{grade}등급"
    
    # 신용점수 추출 (등급이 없는 경우)
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
                if 300 <= score <= 1000:
                    info['credit_score'] = str(score)
                    break
    
    # 거주여부 추출
    if re.search(r'거주|실거주|본인\s*거주', caption):
        info['residence'] = '거주'
    elif re.search(r'비거주|임대|전세', caption):
        info['residence'] = '비거주'

    # 신탁 금액 추출 (신탁금액, 신탁원금, 신탁대환, 신탁 뒤에 금액) - 웹훅과 동일
    trust_patterns = [
        r'신탁\s*금액\s*[:：]?\s*([\d,\s억천만원]+)',
        r'신탁\s*원금\s*[:：]?\s*([\d,\s억천만원]+)',
        r'신탁\s*대환\s*[:：]?\s*([\d,\s억천만원]+)',
        r'신탁\s*[:：]?\s*([\d,\s억천만원]+)',
    ]
    for pattern in trust_patterns:
        match = re.search(pattern, caption, re.IGNORECASE)
        if match:
            price_text = match.group(1).strip()
            price_man = parse_complex_amount(price_text)
            if price_man is not None:
                info['trust_amount'] = f"{price_man:,}"
                break

    # 특이사항 추출 (캡션)
    special_notes_match = re.search(r'특이사항\s*[:：]?\s*(.+?)(?=\n요청사항|\n\n|$)', caption, re.IGNORECASE | re.DOTALL)
    if special_notes_match:
        special_note_text = re.sub(r'\s+', ' ', special_notes_match.group(1).strip()).strip()
        if special_note_text:
            info['special_notes'].append(special_note_text)

    # 요청사항 추출 (웹훅과 동일)
    request_match = re.search(r'요청사항\s*[:：]?\s*(.+?)(?=\n특이사항|\n\n|$)', caption, re.IGNORECASE | re.DOTALL)
    if request_match:
        info['request'] = re.sub(r'\s+', ' ', request_match.group(1).strip())

    return info


def extract_name_from_filename(file_name):
    """파일명에서 고객 이름 추출"""
    if not file_name:
        return ""
    name_without_ext = file_name.replace('.pdf', '').replace('.PDF', '')
    match = re.match(r'^([가-힣A-Za-z]+)', name_without_ext)
    if match:
        return match.group(1).strip()
    return ""


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """시작 명령어"""
    await update.message.reply_text(
        "📋 로컬 PDF 분석 봇입니다.\n\n"
        "등기부등본 PDF 파일을 전송하면 자동으로 분석합니다.\n"
        "KB 시세 조회 및 대출 정보를 제공합니다."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """도움말 명령어"""
    await update.message.reply_text(
        "📋 사용법:\n"
        "1. 등기부등본 PDF 파일을 전송\n"
        "2. 자동으로 분석 후 결과 회신\n\n"
        "⚡ 로컬 처리로 빠른 응답!"
    )


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """문서(PDF) 처리"""
    message = update.message
    document = message.document
    
    # PDF 파일만 처리
    if not document.file_name.lower().endswith('.pdf'):
        await message.reply_text("❌ PDF 파일만 처리 가능합니다.")
        return
    
    logger.info(f"📥 PDF 파일 수신: {document.file_name}")
    
    # "분석 중" 메시지
    processing_msg = await message.reply_text("📊 PDF 분석 중...")
    
    try:
        # PDF 다운로드
        file = await document.get_file()
        pdf_path = TEMP_DIR / document.file_name
        await file.download_to_drive(pdf_path)
        
        logger.info(f"📥 PDF 다운로드 완료: {pdf_path}")
        
        # PDF 파싱
        from parsers.registry_parser import analyze_pdf
        parsed_doc = analyze_pdf(str(pdf_path))
        
        if not parsed_doc:
            await processing_msg.edit_text("❌ PDF 파일을 파싱할 수 없습니다.")
            pdf_path.unlink(missing_ok=True)
            return
        
        logger.info(f"✅ PDF 파싱 완료: {parsed_doc.부동산_주소}")
        
        # 캡션 정보 추출 (1순위 120%, 2순위 130% 등 수동 비율 + 감액등기 원금)
        caption = message.caption or ""
        caption_info = parse_caption_info(caption)
        caption_info['manual_ratios'] = extract_manual_ratios(caption)
        caption_info['manual_principals'] = extract_manual_principals(caption)
        file_name = document.file_name
        
        # 결과 포맷팅
        response = await format_registry_result(parsed_doc, caption_info, file_name)
        
        # "분석 중" 메시지 삭제
        try:
            await processing_msg.delete()
        except:
            pass
        
        # 결과 전송
        await message.reply_text(response)
        
        # 임시 파일 삭제
        pdf_path.unlink(missing_ok=True)
        logger.info(f"✅ PDF 처리 완료 및 임시 파일 삭제")
        
    except Exception as e:
        logger.error(f"❌ PDF 처리 오류: {str(e)}", exc_info=True)
        await processing_msg.edit_text(f"❌ 처리 중 오류가 발생했습니다: {str(e)}")


async def format_registry_result(result, caption_info, file_name):
    """등기부등본 분석 결과를 텔레그램 메시지 형식으로 포맷 (webhook.py 스타일)"""
    lines = []
    
    # 소유자 정보
    borrower = caption_info.get('borrower_name', '')
    collateral_provider = caption_info.get('collateral_provider', '')
    
    # 수탁자 여부
    is_trustee = result.수탁자여부 if hasattr(result, '수탁자여부') else False
    
    if is_trustee:
        customer_name = extract_name_from_filename(file_name)
        if customer_name:
            lines.append(f"성   명 : {customer_name}")
        else:
            lines.append(f"성   명 : {borrower or '확인불가'}")
        lines.append(f"직   업 : {caption_info['job']}")
        lines.append(f"신용점수 : {caption_info['credit_score']}")
        lines.append(f"거주여부 : {caption_info['residence']}")
        lines.append(f"소유현황 : 신탁")
    elif result.소유자목록:
        owners = result.소유자목록[:2]
        
        # 나이 계산
        age = ""
        if owners[0].생년월일:
            try:
                birth_parts = owners[0].생년월일.split('.')
                birth_year = int(birth_parts[0])
                birth_month = int(birth_parts[1]) if len(birth_parts) > 1 else 1
                birth_day = int(birth_parts[2]) if len(birth_parts) > 2 else 1
                
                today = datetime.now().date()
                calculated_age = today.year - birth_year
                if (today.month, today.day) < (birth_month, birth_day):
                    calculated_age -= 1
                
                age = f"({calculated_age})"
            except:
                age = ""
        
        # 이름 표시
        if borrower and collateral_provider:
            name_display = f"{borrower}(차), {collateral_provider}(담) {age}"
        elif borrower:
            if len(owners) == 1:
                name_display = f"{borrower}(차), {owners[0].성명}(담) {age}"
            else:
                owner_names = ", ".join([o.성명 for o in owners])
                name_display = f"{borrower}(차), {owner_names}(담) {age}"
        else:
            if len(owners) == 1:
                name_display = f"{owners[0].성명} {age}"
            else:
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
            share = "공동소유"
        lines.append(f"소유현황 : {share}")
    else:
        name_from_file = extract_name_from_filename(file_name)
        if borrower and collateral_provider:
            name_display = f"{borrower}(차), {collateral_provider}(담)"
        elif borrower:
            name_display = f"{borrower}(차)"
        elif name_from_file:
            name_display = name_from_file
        else:
            name_display = "확인불가"
        
        lines.append(f"성   명 : {name_display}")
        lines.append(f"직   업 : {caption_info['job']}")
        lines.append(f"신용점수 : {caption_info['credit_score']}")
        lines.append(f"거주여부 : {caption_info['residence']}")
        lines.append(f"소유현황 : ")
    
    # 주소 및 층수
    address = result.부동산_주소 or "확인불가"
    floor_info = result.층수정보 or ""
    
    total_floor = ""
    if floor_info:
        floor_match = re.search(r'(\d+)층\s*중', floor_info)
        if floor_match:
            total_floor = f"{floor_match.group(1)}층"
        else:
            floor_match = re.search(r'^(\d+)층', floor_info)
            if floor_match:
                total_floor = f"{floor_match.group(1)}층"
    
    lines.append(f"주   소 : {address}")
    
    # 총층수만 표시 (호수 정보 제외)
    if total_floor:
        lines.append(f"총층수 : {total_floor}")
    else:
        lines.append(f"총층수 : ")
    
    # 면적
    area = result.면적 or ''
    lines.append(f"면   적 : {area}")
    
    # KB 시세 조회
    kb_result = None
    kb_price = ""
    kb_price_low = ""
    kb_complex_id = None
    households = ""
    property_type = ""
    
    if address and address != "확인불가" and area:
        try:
            logger.info(f"KB 시세 자동 조회 시작 - 주소: {address}, 면적: {area}")
            
            # 로컬 봇은 ThreadPoolExecutor로 동기 함수 실행
            from KB_api.kb_price_api import get_kb_price_from_registry
            loop = asyncio.get_event_loop()
            with ThreadPoolExecutor() as executor:
                kb_result = await loop.run_in_executor(
                    executor, 
                    get_kb_price_from_registry, 
                    address, 
                    area
                )
            
            if kb_result:
                logger.info(f"🔍 KB 결과: {kb_result}")
                
                kb_price_num = kb_result.get('kb_price')
                kb_price_min_num = kb_result.get('kb_price_min')
                kb_complex_id = kb_result.get('complex_id')
                
                if kb_price_num:
                    # float를 int로 변환하여 소수점 제거
                    kb_price = f"{int(float(kb_price_num)):,}"
                    logger.info(f"✅ KB 시세 조회 성공: 일반 {kb_price}만원")
                
                if kb_price_min_num:
                    # float를 int로 변환하여 소수점 제거
                    kb_price_low = f"{int(float(kb_price_min_num)):,}"
                    logger.info(f"✅ KB 시세 하한 조회 성공: {kb_price_low}만원")
                
                # 세대수 정보
                kb_households = kb_result.get('households')
                kb_buildings = kb_result.get('buildings')
                if kb_households is not None:
                    households = f"{kb_households}세대"
                    if kb_buildings is not None:
                        households = f"{kb_households}세대"  # buildings는 아래에서 추가
                
                # 구분 정보 (스크래핑 단지유형 우선)
                kb_complex_type = kb_result.get('complex_type')
                if kb_complex_type:
                    property_type = kb_complex_type
                else:
                    property_type = "아파트"
            else:
                logger.warning("KB 시세 조회 실패 (결과 없음)")
        except Exception as e:
            logger.error(f"KB 시세 조회 중 오류: {str(e)}", exc_info=True)
    
    # 세대수 / 동수, 구분 표시
    buildings_str = ""
    if kb_result:
        logger.info(f"📊 동수 확인: buildings={kb_result.get('buildings')}")
        if kb_result.get('buildings') is not None:
            buildings_str = f" / {kb_result.get('buildings')}개동"
            logger.info(f"✅ 동수 추가: {buildings_str}")
    
    # households에 "세대"가 이미 붙어있으면 그대로, 없으면 추가
    households_display = households
    if households and not households.endswith('세대'):
        households_display = f"{households}세대"
    
    lines.append(f"세대수 : {households_display}{buildings_str}")
    lines.append(f"구   분 : {property_type}")
    
    # 사용승인일
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
            def _parse_date(d):
                try:
                    parts = d.split('.')
                    if len(parts) == 3:
                        return (int(parts[0]), int(parts[1]), int(parts[2]))
                except (ValueError, AttributeError):
                    pass
                return (0, 0, 0)
            latest = max(stages_with_date, key=lambda s: _parse_date(s.get('date', '')))
            step = latest.get('step')
            name = latest.get('name', '')
            date_val = latest.get('date', '')
            redevelop_line = f"재건축 : {step}단계{name}'{date_val}"
            lines.append(redevelop_line)
            logger.info(f"✅ 재건축 (최근 1건): {redevelop_line}")
    
    # KB 시세 표시
    if kb_price:
        lines.append(f"KB시세 : 일반 {kb_price}만원")
        lines.append(f"KB시세 : 하한 {kb_price_low}만원" if kb_price_low else f"KB시세 : 하한      만원")
        if kb_complex_id:
            kb_price_url = f"https://kbland.kr/c/{kb_complex_id}"
            lines.append(f"KB시세 참고 : {kb_price_url}")
    else:
        lines.append("KB시세 : 없음")
        lines.append("KB시세 : 하한      만원")
    
    # 근저당권 설정 내역 (캡션의 1순위 120%, 2순위 130% 등 수동 비율 적용)
    lines.append(f"=========설정내역=========")
    trust_amount = caption_info.get('trust_amount', '')
    trust_amount_man = None
    if is_trustee and trust_amount:
        try:
            trust_amount_man = int(trust_amount.replace(',', ''))
            lines.append(f"1순위 : 신탁")
            lines.append(f"           {trust_amount_man:,}만원")
        except (ValueError, TypeError):
            pass

    manual_ratios = caption_info.get('manual_ratios', {})
    manual_principals = caption_info.get('manual_principals', {})
    needs_principal_check = False
    start_rank = 2 if (is_trustee and trust_amount_man) else 1
    gamak_excluded_creditors = []  # 1천만원 미만 차이로 감액등기 미적용된 금융사

    if result.근저당권목록:
        mortgage_amounts = []
        principal_amounts = []

        for i, m in enumerate(result.근저당권목록, start=start_rank):
            gamak_applied = False
            manual_ratio = manual_ratios.get(str(i))
            amount_match = re.search(r'금?\s*([\d,]+)\s*원', m.채권최고액)
            if amount_match:
                amount_won = int(amount_match.group(1).replace(',', ''))
                amount_man = amount_won // 10000
                mortgage_amounts.append(amount_man)

                principal_won, used_ratio, is_clean = calculate_principal(
                    amount_won, m.근저당권자, manual_ratio
                )
                principal_man = principal_won // 10000
                principal_amounts.append(principal_man)
                if not is_clean and not manual_ratio:
                    needs_principal_check = True

                creditor_raw = m.근저당권자
                creditor = re.sub(r'주식회사', '', creditor_raw)
                creditor = re.sub(r'유한회사', '', creditor)
                creditor = re.sub(r'사단법인', '', creditor)
                creditor = creditor.strip()

                # 감액등기: 고객이 원금을 보냈을 때 채권최고액 역산 (차이 1000만원 이상일 때만)
                manual_principal_man = manual_principals.get(str(i))
                if manual_principal_man is None:
                    for key, val in manual_principals.items():
                        if key.isdigit():
                            continue
                        if key in creditor or creditor in key:
                            manual_principal_man = val
                            break

                if manual_principal_man is not None and not (hasattr(m, '권리종류') and m.권리종류 == "전세권"):
                    new_max_claim_man = int(manual_principal_man * used_ratio / 100)
                    diff_man = abs(amount_man - new_max_claim_man)
                    if diff_man >= 1000:
                        amount_man = new_max_claim_man
                        principal_man = manual_principal_man
                        mortgage_amounts[-1] = amount_man
                        principal_amounts[-1] = principal_man
                        amount_str = f"{amount_man:,}만({principal_man:,})만원({used_ratio}%)"
                        gamak_applied = True
                    elif manual_principal_man < principal_man:
                        # 보낸 원금이 계산 원금보다 적을 때만 (감액 의도 있으나 1천만원 미만 차이)
                        gamak_excluded_creditors.append(creditor)

                if not gamak_applied:
                    if hasattr(m, '권리종류') and m.권리종류 == "전세권":
                        amount_str = f"{amount_man:,} ({amount_man:,})만원(100%)"
                    else:
                        amount_str = f"{amount_man:,} ({principal_man:,})만원({used_ratio}%)"
            else:
                man_match = re.search(r'([\d,]+)\s*만', m.채권최고액)
                if man_match:
                    amount_man = int(man_match.group(1).replace(',', ''))
                    mortgage_amounts.append(amount_man)
                    principal_man = int(amount_man * 0.833)
                    principal_amounts.append(principal_man)
                    amount_str = f"{amount_man:,} ({principal_man:,})만원(120%)"
                else:
                    amount_str = m.채권최고액

                creditor_raw = m.근저당권자
                creditor = re.sub(r'주식회사', '', creditor_raw)
                creditor = re.sub(r'유한회사', '', creditor)
                creditor = re.sub(r'사단법인', '', creditor)
                creditor = creditor.strip()
                gamak_applied = False

            # 채무자 정보 + 감액등기 표시
            debtor = m.채무자 if m.채무자 else ""
            creditor_line = f"{i}순위 : {creditor}"
            if debtor:
                creditor_line += f"({debtor})"
            if gamak_applied:
                creditor_line += " 감액등기"
            lines.append(creditor_line)
            lines.append(f"           {amount_str}")
        
        if is_trustee and trust_amount_man:
            mortgage_amounts.insert(0, trust_amount_man)
            principal_amounts.insert(0, trust_amount_man)
        # LTV 계산
        if kb_price and mortgage_amounts:
            try:
                kb_price_man = int(kb_price.replace(',', ''))
                total_mortgage_man = sum(mortgage_amounts)
                total_principal_man = sum(principal_amounts)
                if kb_price_man > 0:
                    ratio_mortgage = (total_mortgage_man / kb_price_man) * 100
                    ratio_principal = (total_principal_man / kb_price_man) * 100
                    lines.append(f"{ratio_mortgage:.2f}% / {ratio_principal:.2f}%")
            except Exception:
                pass
    elif is_trustee and trust_amount_man:
        mortgage_amounts = [trust_amount_man]
        principal_amounts = [trust_amount_man]
        if kb_price:
            try:
                kb_price_man = int(kb_price.replace(',', ''))
                if kb_price_man > 0:
                    ratio = (trust_amount_man / kb_price_man) * 100
                    lines.append(f"{ratio:.2f}% / {ratio:.2f}%")
            except (ValueError, ZeroDivisionError):
                pass
    else:
        lines.append("설정된 근저당권 없음")
    
    lines.append(f"========================")
    
    # 압류/가압류 정보 (캡션 특이사항 먼저)
    special_notes = []
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
    
    # 경매 정보 (웹훅과 동일: 종류(채권자))
    if result.경매목록:
        auction_info = []
        for a in result.경매목록:
            auction_info.append(f"{getattr(a, '종류', '경매')}({getattr(a, '채권자', '')})")
        special_notes.append("경매: " + ", ".join(auction_info))

    # 환매특약/전매제한 (웹훅과 동일)
    if hasattr(result, '환매특약') and result.환매특약:
        special_notes.append(result.환매특약)

    # 별도등기 (웹훅과 동일 문구)
    if hasattr(result, '별도등기') and result.별도등기:
        special_notes.append("별도등기 있음")

    lines.append(f"특이사항 : {' / '.join(special_notes) if special_notes else ''}")
    lines.append(f"요청사항 : {caption_info.get('request', '')}")

    if not kb_price:
        lines.append("KB시세 없음. 다른 시세 첨부 바랍니다.")
    if needs_principal_check:
        lines.append("*근저당권 원금설정 확인 필요*")
    if is_trustee and not trust_amount:
        lines.append("신탁 금액 기재 바랍니다.")

    return '\n'.join(lines)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """일반 텍스트 메시지 처리"""
    await update.message.reply_text(
        "📋 등기부등본 PDF 파일을 전송해주세요.\n"
        "자동으로 분석하여 결과를 회신합니다."
    )


def main():
    """메인 함수"""
    logger.info("=" * 60)
    logger.info("🤖 로컬 PDF 분석 봇 시작")
    logger.info(f"📱 Bot Token: {TELEGRAM_BOT_TOKEN[:10]}...")
    logger.info("=" * 60)
    
    # Application 생성
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # 핸들러 등록
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.Document.PDF, handle_document))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # 봇 실행 (Polling)
    logger.info("✅ 봇이 실행되었습니다. PDF 파일을 전송하세요!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
