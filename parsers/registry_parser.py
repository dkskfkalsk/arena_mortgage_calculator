# -*- coding: utf-8 -*-
"""
등기부등본 PDF 파싱 모듈
- 9가지 핵심 정보 자동 추출
- 일반 등기부등본 및 경매 물건지 등기부등본 지원
- PyMuPDF(fitz) 사용으로 빠른 텍스트 추출
"""

import fitz  # PyMuPDF
import re
import os
import json
import sys
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict

# 로깅 설정 - Vercel 환경에서 stderr로 출력
is_vercel = os.getenv('VERCEL') == '1' or os.getenv('VERCEL_ENV') is not None
handlers = [logging.StreamHandler(sys.stderr)]

if not is_vercel:
    try:
        handlers.append(logging.FileHandler('registry_parser_debug.log', encoding='utf-8'))
    except Exception:
        pass

logging.basicConfig(
    level=logging.INFO if is_vercel else logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=handlers
)
logger = logging.getLogger(__name__)
if is_vercel:
    logger.setLevel(logging.INFO)


@dataclass
class MortgageInfo:
    """근저당권/전세권 설정 정보"""
    순위번호: str
    근저당권자: str
    채무자: str
    채권최고액: str
    설정일: str
    권리종류: str = "근저당권"  # "근저당권" 또는 "전세권"


@dataclass
class OwnerInfo:
    """소유자 정보"""
    성명: str
    주민번호: str
    생년월일: str
    주소: str
    지분: str = "단독소유"


@dataclass
class SeizureInfo:
    """압류/가압류 정보"""
    종류: str  # 압류, 가압류
    권리자: str
    접수일: str
    원인: str = ""


@dataclass
class AuctionInfo:
    """경매 정보"""
    종류: str  # 임의경매, 강제경매
    채권자: str
    접수일: str
    사건번호: str = ""


@dataclass
class RegistryDocument:
    """등기부등본 파싱 결과"""
    # 기본 정보
    고유번호: str = ""
    부동산_주소: str = ""
    면적: str = ""
    층수정보: str = ""  # 예: "15층 중 2층"
    
    # 소유자 정보
    소유자목록: List[OwnerInfo] = None
    소유권이전일: str = ""
    
    # 근저당권 정보
    근저당권목록: List[MortgageInfo] = None
    
    # 압류/가압류 정보
    압류목록: List[SeizureInfo] = None
    
    # 경매 정보
    경매목록: List[AuctionInfo] = None
    
    # 환매특약/전매제한 정보
    환매특약: str = ""
    
    # 별도등기 정보
    별도등기: bool = False  # True면 별도등기 있음, False면 없거나 말소됨
    
    # 수탁자 여부 (신탁인 경우)
    수탁자여부: bool = False  # True면 수탁자가 있음 (신탁)
    
    # 원본 텍스트
    원본텍스트: str = ""
    
    def __post_init__(self):
        if self.소유자목록 is None:
            self.소유자목록 = []
        if self.근저당권목록 is None:
            self.근저당권목록 = []
        if self.압류목록 is None:
            self.압류목록 = []
        if self.경매목록 is None:
            self.경매목록 = []
    
    def to_dict(self) -> Dict:
        """딕셔너리로 변환"""
        return {
            "고유번호": self.고유번호,
            "부동산_주소": self.부동산_주소,
            "면적": self.면적,
            "층수정보": self.층수정보,
            "소유권이전일": self.소유권이전일,
            "소유자목록": [asdict(o) for o in self.소유자목록],
            "근저당권목록": [asdict(m) for m in self.근저당권목록],
            "압류목록": [asdict(s) for s in self.압류목록],
            "경매목록": [asdict(a) for a in self.경매목록],
            "환매특약": self.환매특약,
        }
    
    def summary(self) -> str:
        """요약 정보 출력"""
        lines = []
        lines.append("=" * 60)
        lines.append("【 등기부등본 분석 결과 】")
        lines.append("=" * 60)
        
        lines.append(f"\n▶ 고유번호: {self.고유번호}")
        lines.append(f"▶ 부동산 주소: {self.부동산_주소}")
        lines.append(f"▶ 면적: {self.면적}")
        lines.append(f"▶ 층수: {self.층수정보}")
        lines.append(f"▶ 소유권이전일: {self.소유권이전일}")
        
        lines.append(f"\n【 소유자 정보 】 ({len(self.소유자목록)}명)")
        for i, owner in enumerate(self.소유자목록, 1):
            lines.append(f"  {i}. {owner.성명} ({owner.생년월일}) - {owner.지분}")
            lines.append(f"     주소: {owner.주소}")
        
        lines.append(f"\n【 근저당권 설정 내역 】 ({len(self.근저당권목록)}건)")
        for i, m in enumerate(self.근저당권목록, 1):
            lines.append(f"  {i}. [{m.순위번호}] 채권최고액: {m.채권최고액}")
            lines.append(f"     근저당권자: {m.근저당권자}")
            lines.append(f"     채무자: {m.채무자}")
            lines.append(f"     설정일: {m.설정일}")
        
        if self.압류목록:
            lines.append(f"\n【 압류/가압류 】 ({len(self.압류목록)}건)")
            for i, s in enumerate(self.압류목록, 1):
                lines.append(f"  {i}. [{s.종류}] 권리자: {s.권리자}")
                lines.append(f"     접수일: {s.접수일}")
        else:
            lines.append(f"\n【 압류/가압류 】 없음")
        
        if self.경매목록:
            lines.append(f"\n【 경매 정보 】 ({len(self.경매목록)}건)")
            for i, a in enumerate(self.경매목록, 1):
                lines.append(f"  {i}. [{a.종류}] 채권자: {a.채권자}")
                lines.append(f"     접수일: {a.접수일}")
                if a.사건번호:
                    lines.append(f"     사건번호: {a.사건번호}")
        else:
            lines.append(f"\n【 경매 정보 】 없음")
        
        lines.append("\n" + "=" * 60)
        return "\n".join(lines)


class RegistryParser:
    """등기부등본 PDF 파서"""
    
    def __init__(self):
        self.text = ""
        self.pages_text = []
    
    def extract_text_from_pdf(self, pdf_path: str) -> str:
        """PDF에서 텍스트 추출 (PyMuPDF 사용 - 고속)"""
        all_text = []
        self.pages_text = []
        
        doc = fitz.open(pdf_path)
        try:
            for page in doc:
                text = page.get_text() or ""
                all_text.append(text)
                self.pages_text.append(text)
        finally:
            doc.close()
        
        self.text = "\n".join(all_text)
        return self.text
    
    def parse(self, pdf_path: str) -> RegistryDocument:
        """PDF 파싱하여 RegistryDocument 반환"""
        self.extract_text_from_pdf(pdf_path)
        
        doc = RegistryDocument()
        doc.원본텍스트 = self.text
        
        # 각 항목 추출
        doc.고유번호 = self._extract_document_number()
        doc.부동산_주소 = self._extract_address()
        doc.면적 = self._extract_area()
        doc.층수정보 = self._extract_floor_info()
        doc.소유자목록 = self._extract_owners()
        doc.소유권이전일 = self._extract_ownership_transfer_date()
        doc.근저당권목록 = self._extract_mortgages()
        doc.압류목록 = self._extract_seizures()
        doc.경매목록 = self._extract_auctions()
        doc.환매특약 = self._extract_special_conditions()
        doc.별도등기 = self._extract_separate_registry()
        
        # 수탁자 여부 확인 (갑구에 수탁자 키워드가 있는지 확인)
        doc.수탁자여부 = self._check_trustee()
        
        return doc
    
    def _extract_document_number(self) -> str:
        """고유번호 추출"""
        # 패턴: 고유번호 1234-1234-123456
        pattern = r'고유번호\s*(\d{4}-\d{4}-\d+)'
        match = re.search(pattern, self.text)
        if match:
            return match.group(1)
        return ""
    
    def _extract_address(self) -> str:
        """부동산 주소 추출"""
        # [집합건물] 또는 [토지] 또는 [건물] 뒤의 주소
        pattern = r'\[집합건물\]\s*(.+?)(?:\n|표)'
        match = re.search(pattern, self.text)
        if match:
            addr = match.group(1).strip()
            addr = re.sub(r'\s+', ' ', addr)
            if len(addr) > 5:
                return addr
        
        # 소재지 / 소재지번 다음 줄
        pattern = r'소재지번[^\n]*\n\s*(.+?)(?:\n|$)'
        match = re.search(pattern, self.text)
        if match:
            addr = match.group(1).strip()
            addr = re.sub(r'\s+', ' ', addr)
            if len(addr) > 5:
                return addr
        
        # 소재지 : 주소 (한 줄)
        pattern = r'소재지\s*[:：]\s*(.+?)(?:\n|$)'
        match = re.search(pattern, self.text)
        if match:
            addr = match.group(1).strip()
            addr = re.sub(r'\s+', ' ', addr)
            if len(addr) > 5:
                return addr
        
        return ""
    
    def _extract_area(self) -> str:
        """면적 추출 (전용면적) - 표제부 '전유부분의 건물의 표시'에 기재된 면적 사용"""

        # 1순위: ( 전유부분의 건물의 표시 ) 블록에서 추출 (층별 면적 240㎡ 등과 구분)
        building_section = ""
        m_building_full = re.search(
            r'\(\s*전유부분의\s*건물의\s*표시\s*\)\s*([\s\S]*?)(?=\(\s*[^)]*\)|【|$)',
            self.text
        )
        if m_building_full:
            building_section = m_building_full.group(1)
        if building_section:
            for row_pattern in [
                r'제\s*\d+층\s*제\s*\d+호[\s\S]{0,120}?(\d+\.?\d*)\s*㎡',
                r'제\s*\d+동\s*제\s*\d+호[\s\S]{0,120}?(\d+\.?\d*)\s*㎡',
            ]:
                match_row = re.search(row_pattern, building_section)
                if match_row:
                    area = match_row.group(1)
                    try:
                        area_float = float(area)
                        if 10 <= area_float <= 300:
                            return f"{area}㎡"
                    except ValueError:
                        pass
            area_matches = list(re.finditer(r'(\d+\.?\d*)\s*㎡', building_section))
            non_floor_areas = []
            for ma in area_matches:
                try:
                    area_float = float(ma.group(1))
                except ValueError:
                    continue
                if not (10 <= area_float <= 300):
                    continue
                start = max(0, ma.start() - 12)
                prefix = building_section[start:ma.start()]
                if re.search(r'\d+층\s*$', prefix):
                    continue
                non_floor_areas.append((area_float, ma.group(1)))
            if non_floor_areas:
                non_floor_areas.sort(key=lambda x: x[0], reverse=True)
                return f"{non_floor_areas[0][1]}㎡"

        # 2순위: "제N층 제N호" 직후 150자 이내 첫 XX㎡ (층별 면적 "N층 XX㎡" 제외)
        for m in re.finditer(r'제\s*\d+층\s*제\s*\d+호', self.text):
            snippet = self.text[m.end():m.end() + 150]
            area_m = re.search(r'(\d+\.?\d*)\s*㎡', snippet)
            if area_m:
                start = max(0, area_m.start() - 15)
                prefix = snippet[start:area_m.start()]
                if re.search(r'\d+층\s*$', prefix):
                    continue
                try:
                    a = float(area_m.group(1))
                    if 10 <= a <= 300:
                        return f"{area_m.group(1)}㎡"
                except ValueError:
                    pass

        # 공급/전용 형태: "51㎡/37.85㎡" 또는 "51/37.85" → 두 번째(전용면적) 사용
        slash_patterns = [
            r'(\d+\.?\d*)\s*㎡\s*/\s*(\d+\.?\d*)\s*㎡',
            r'(\d+\.?\d*)\s*m²\s*/\s*(\d+\.?\d*)\s*m²',
            r'(\d+\.?\d*)\s*/\s*(\d+\.?\d*)\s*㎡',
            r'(\d+\.?\d*)\s*/\s*(\d+\.?\d*)\s*(?:㎡|m²)',
        ]
        for pattern in slash_patterns:
            match = re.search(pattern, self.text, re.IGNORECASE)
            if match:
                area_second = match.group(2)
                try:
                    area_float = float(area_second)
                    if 10 <= area_float <= 300:
                        return f"{area_second}㎡"
                except ValueError:
                    pass

        # 공급 37.85 형태: "51㎡ 37.85㎡" 또는 "51 37.85 ㎡" (공백 구분) → 두 번째(전용) 사용
        space_pair_patterns = [
            r'(\d+\.?\d*)\s*㎡\s+(\d+\.?\d*)\s*㎡',
            r'(\d+\.?\d*)\s+(\d+\.?\d*)\s*㎡',
            r'(\d+\.?\d*)\s+(\d+\.?\d*)\s*[㎡m²]',
        ]
        for pattern in space_pair_patterns:
            match = re.search(pattern, self.text)
            if match:
                first_num = float(match.group(1))
                second_num = float(match.group(2))
                # 전용이 보통 더 작음: 두 번째가 10~300이면 사용
                if 10 <= second_num <= 300:
                    return f"{match.group(2)}㎡"
                if 10 <= first_num <= 300:
                    return f"{match.group(1)}㎡"

        # "전용면적 37.85" / "전용 37.85㎡" 등 명시적 전용 키워드
        dedicated_patterns = [
            r'전용\s*면적\s*[:\s]*(\d+\.?\d*)\s*[㎡m²]?',
            r'전용\s*[:\s]*(\d+\.?\d*)\s*[㎡m²]',
            r'\(?\s*전용\s*\)?\s*(\d+\.?\d*)\s*[㎡m²]',
        ]
        for pattern in dedicated_patterns:
            match = re.search(pattern, self.text, re.IGNORECASE)
            if match:
                try:
                    area_float = float(match.group(1))
                    if 10 <= area_float <= 300:
                        return f"{match.group(1)}㎡"
                except ValueError:
                    pass

        # 표제부 구간: 【 표 제 부 】와 【 갑 구 】 사이 텍스트만 사용. 그 구간에 있는 "㎡" 앞 숫자로 면적 후보 확인
        table_section_for_building = ""
        m_table = re.search(
            r'【\s*표\s*제\s*부\s*】[\s\S]*?(?=【\s*갑\s*구\s*】|【|$)',
            self.text, re.IGNORECASE
        )
        if m_table:
            table_section_for_building = m_table.group(0)
        search_for_building = table_section_for_building if table_section_for_building else self.text

        building_section = ""
        m_building = re.search(
            r'\(\s*전유부분의\s*건물의\s*표시\s*\)\s*([\s\S]*?)(?=\(\s*[^)]*\)|【|$)', search_for_building
        )
        if m_building:
            building_section = m_building.group(1)
        # PDF 추출 순서상 ( 전유부분의 건물의 표시 )가 표제부~갑구 구간 밖(다른 페이지)에 있을 수 있음 → 전체 텍스트에서 재탐색
        if not building_section:
            m_building_full = re.search(
                r'\(\s*전유부분의\s*건물의\s*표시\s*\)\s*([\s\S]*?)(?=\(\s*[^)]*\)|【|$)',
                self.text
            )
            if m_building_full:
                building_section = m_building_full.group(1)
        if building_section:
            # 표제부 표에서 해당 호실 행의 면적 우선: "제N층 제N호" 또는 "제N동 제N호" + 건물내역(철근콘크리트/목조/철골 등) + XX㎡
            # 건물내역 문구는 다양하므로 구조 종류에 의존하지 않고, 호실 직후 ~80자 이내 첫 면적 사용
            for row_pattern in [
                r'제\s*\d+층\s*제\s*\d+호[\s\S]{0,80}?(\d+\.?\d*)\s*㎡',
                r'제\s*\d+동\s*제\s*\d+호[\s\S]{0,80}?(\d+\.?\d*)\s*㎡',
            ]:
                match_row = re.search(row_pattern, building_section)
                if match_row:
                    area = match_row.group(1)
                    try:
                        area_float = float(area)
                        if 10 <= area_float <= 300:
                            return f"{area}㎡"
                    except ValueError:
                        pass
            # 도면편철장 제N책 제N호 뒤에 오는 면적 (같은 줄 또는 다음 줄)
            match_doyoung = re.search(r'도면편철장\s*제\d+책\s*제\d+호[\s\S]*?(\d+\.?\d*)\s*㎡', building_section)
            if match_doyoung:
                area = match_doyoung.group(1)
                area_float = float(area)
                if 10 <= area_float <= 300:
                    return f"{area}㎡"
            # 전유부분 블록 내 'N층 XX㎡'가 아닌 면적만 수집 (층별 면적 제외)
            area_matches = list(re.finditer(r'(\d+\.?\d*)\s*㎡', building_section))
            non_floor_areas = []
            for ma in area_matches:
                area_float = None
                try:
                    area_float = float(ma.group(1))
                except ValueError:
                    continue
                if not (10 <= area_float <= 300):
                    continue
                # 직전 10자 안에 'N층 '이 있으면 층별 면적으로 간주하고 제외
                start = max(0, ma.start() - 12)
                prefix = building_section[start:ma.start()]
                if re.search(r'\d+층\s*$', prefix):
                    continue
                non_floor_areas.append((area_float, ma.group(1)))
            if non_floor_areas:
                # 전유부분 블록에서는 전용면적 1개가 보통이므로 가장 큰 값 사용 (층별 제외 후)
                non_floor_areas.sort(key=lambda x: x[0], reverse=True)
                return f"{non_floor_areas[0][1]}㎡"

        # 1. (전 1) 63.81㎡ 형태: 전유 1호기 전용면적 명시 (동문아파트 등)
        match = re.search(r'\(전\s*\d+\)\s*(\d+\.?\d*)\s*㎡', self.text)
        if match:
            area = match.group(1)
            area_float = float(area)
            if 10 <= area_float <= 300:
                return f"{area}㎡"

        # 2. 전유부분 표시 섹션에서 찾기 (제X동 제X호 근처의 면적)
        patterns = [
            r'제?\d+호\s+\S*\s+(\d+\.?\d*)\s*㎡\s*철근',
            r'제?\d+호.*?(\d{2,3}\.?\d*)\s*㎡',
            r'전용면적[:\s]*(\d+\.?\d*)\s*㎡',
        ]
        for pattern in patterns:
            match = re.search(pattern, self.text, re.DOTALL)
            if match:
                area = match.group(1)
                area_float = float(area)
                if 10 <= area_float <= 300:
                    return f"{area}㎡"

        # 3. 표제부 전체: 【 표 제 부 】 ~ 【 갑 구 】 사이에서만 "㎡" 앞 숫자 사용, 'N층 XX㎡' 제외
        # 10~300 범위. 공급/전용 둘 다 있으면 작은 값(전용) 우선, 아니면 가장 큰 값
        table_section = ""
        m = re.search(
            r'【\s*표\s*제\s*부\s*】[\s\S]*?(?=【\s*갑\s*구\s*】|【|$)',
            self.text, re.IGNORECASE
        )
        if m:
            table_section = m.group(0)
        search_text = table_section if table_section else self.text

        # ㎡ 외 m², m2 등도 매칭
        area_matches = list(re.finditer(r'(\d+\.?\d*)\s*(?:㎡|m²|m2)', search_text, re.IGNORECASE))
        valid_areas = []
        for ma in area_matches:
            try:
                area_float = float(ma.group(1))
                if not (10 <= area_float <= 300):
                    continue
                start = max(0, ma.start() - 12)
                prefix = search_text[max(0, ma.start() - 20):ma.start()]
                if re.search(r'\d+층\s*$', prefix):
                    continue
                valid_areas.append((area_float, ma.group(1)))
            except ValueError:
                continue

        if valid_areas:
            # 공급/전용 쌍(비율 약 1.2~1.5)이 있으면 작은 값(전용) 사용
            sorted_areas = sorted(valid_areas, key=lambda x: x[0])
            for i, (a_val, a_str) in enumerate(sorted_areas):
                for b_val, b_str in sorted_areas[i + 1:]:
                    ratio = b_val / a_val if a_val > 0 else 0
                    if 1.2 <= ratio <= 1.5 and 10 <= a_val <= 80:
                        return f"{a_str}㎡"
            # 쌍 없으면 기존처럼 가장 큰 값 (단일 면적인 경우)
            valid_areas.sort(key=lambda x: x[0], reverse=True)
            return f"{valid_areas[0][1]}㎡"

        return ""
    
    def _extract_floor_info(self) -> str:
        """층수 정보 추출 (표제부 섹션에서 마지막 층수 추출)"""
        # JavaScript 로직 참고: 【 표 제 부 】 섹션에서 층수+면적 패턴 찾기
        # JavaScript: text.match(/【\s*표\s*제\s*부\s*】[\s\S]*?(\d+)층\s+\d+(\.\d+)?㎡/g)
        # 마지막 매치에서 층수 추출
        
        # 표제부 섹션 찾기 (다음 【 섹션 전까지)
        table_section_pattern = r'【\s*표\s*제\s*부\s*】[\s\S]*?(?=【|$)'
        table_match = re.search(table_section_pattern, self.text, re.IGNORECASE)
        
        if table_match:
            table_text = table_match.group(0)
            # 표제부 안에서 층수+면적 패턴: "15층 3518.21㎡"
            # 지하1층, 지하2층은 마지막에 있어 마지막 매치가 지하가 됨 → 지하 제외
            floor_area_pattern = r'(\d+)층\s+\d+(?:\.\d+)?\s*㎡'
            matches = list(re.finditer(floor_area_pattern, table_text))
            non_basement = []
            for m in matches:
                # "지하N층", "지1층", "지2층" 등 지하층 제외
                start = max(0, m.start() - 3)
                prefix = table_text[start:m.start()]
                # "지하" 또는 "지" + 숫자 (지1층, 지2층 축약형) 제외
                is_basement = '지하' in prefix or (m.start() > 0 and table_text[m.start() - 1] == '지')
                if not is_basement:
                    non_basement.append(m)
            use_matches = non_basement if non_basement else matches
            
            if use_matches:
                last_match = use_matches[-1]
                total_floor = last_match.group(1)
                
                # 해당 호수의 층 정보 찾기
                unit_floor_pattern = r'제?(\d+)층.*?제?(\d+)호'
                unit_match = re.search(unit_floor_pattern, self.text)
                
                if unit_match:
                    floor = unit_match.group(1)
                    unit = unit_match.group(2)
                    return f"{total_floor}층 중 {floor}층 {unit}호"
                else:
                    return f"{total_floor}층"
        
        # 표제부에서 못 찾은 경우 기존 로직 사용
        total_floor_patterns = [
            r'지상\s*(\d+)층',  # 지상 18층
            r'(\d+)층\s*(?:아파트|연립|다세대|오피스텔|빌라|공동주택)',  # 18층 아파트
            r'총\s*(\d+)층',  # 총 18층
            r'(\d+)층\s*건물',  # 18층 건물
            r'지하\s*\d+층\s*지상\s*(\d+)층',  # 지하 3층 지상 18층
        ]
        
        total_match = None
        for pattern in total_floor_patterns:
            total_match = re.search(pattern, self.text, re.IGNORECASE)
            if total_match:
                break
        
        # 해당 호수의 층
        unit_floor_pattern = r'제?(\d+)층.*?제?(\d+)호'
        unit_match = re.search(unit_floor_pattern, self.text)
        
        if total_match and unit_match:
            total = total_match.group(1)
            floor = unit_match.group(1)
            unit = unit_match.group(2)
            return f"{total}층 중 {floor}층 {unit}호"
        elif unit_match:
            floor = unit_match.group(1)
            unit = unit_match.group(2)
            return f"{floor}층 {unit}호"
        elif total_match:
            # 총층수만 있는 경우
            total = total_match.group(1)
            return f"{total}층"
        
        return ""
    
    def _extract_owners(self) -> List[OwnerInfo]:
        """소유자 정보 추출 - 간단하고 명확한 패턴만 사용"""
        logger.debug("🔍 소유자 정보 추출 시작")
        
        # 수탁자 여부 확인 (신탁인 경우)
        if '수탁자' in self.text:
            logger.debug("⚠️ 수탁자 감지 - 빈 리스트 반환")
            return []
        
        owner_matches = []
        
        # 제외할 키워드
        exclude_keywords = ['최종지분', '순위번호', '근저당권', '채권최고액', '설정일', 
                           '소유권', '이전', '등기', '접수', '말소', '갑구', '을구',
                           '출력일시', '고유번호', '소재지', '면적', '층수', '호수']
        
        def is_valid_name(name):
            """이름 유효성 검사"""
            if not name or len(name) < 2 or len(name) > 4:
                return False
            if not re.match(r'^[가-힣]+$', name):
                return False
            for keyword in exclude_keywords:
                if keyword in name:
                    return False
            return True
        
        # 패턴 1: "이름 (소유자)" 또는 "이름 (공유자)" 패턴 - 가장 명확함
        # 예: "김지은 (소유자)", "김연정 (공유자)"
        owner_patterns = [
            r'([가-힣]{2,4})\s*\(\s*소유자\s*\)',  # "김지은 (소유자)"
            r'([가-힣]{2,4})\s*\(\s*공유자\s*\)',  # "이름 (공유자)"
        ]
        
        for pattern in owner_patterns:
            matches = re.finditer(pattern, self.text)
            for match in matches:
                name = match.group(1).strip()
                logger.debug(f"🔍 패턴 매칭 발견: '{name}' (패턴: {pattern})")
                
                if is_valid_name(name):
                    # 이름 근처에서 주민번호 찾기 (매치 위치 기준 앞뒤 200자)
                    start = max(0, match.start() - 200)
                    end = min(len(self.text), match.end() + 200)
                    context = self.text[start:end]
                    
                    resident_match = re.search(r'(\d{6})-[\d\*]+', context)
                    if resident_match:
                        resident_num = resident_match.group(1)
                        if len(resident_num) == 6 and resident_num.isdigit():
                            try:
                                mm = int(resident_num[2:4])
                                dd = int(resident_num[4:6])
                                if 1 <= mm <= 12 and 1 <= dd <= 31:
                                    # 중복 체크
                                    if not any(n == name and r == resident_num for n, r in owner_matches):
                                        owner_matches.append((name, resident_num))
                                        logger.info(f"✅ 소유자 추출 성공: {name} (주민번호: {resident_num}-*******)")
                                    else:
                                        logger.debug(f"⚠️ 중복 소유자 무시: {name}")
                            except Exception as e:
                                logger.debug(f"⚠️ 주민번호 검증 실패: {e}")
                    else:
                        logger.debug(f"⚠️ '{name}' 근처에서 주민번호를 찾을 수 없음")
                else:
                    logger.debug(f"⚠️ '{name}' 이름 유효성 검사 실패")
        
        # OwnerInfo로 변환
        owners = []
        for name, resident_num in owner_matches:
            birth = self._convert_birth_date(resident_num)
            share = "공동소유" if len(owner_matches) > 1 else "단독소유"
            
            owner = OwnerInfo(
                성명=name,
                주민번호=f"{resident_num}-*******",
                생년월일=birth,
                주소="",
                지분=share
            )
            owners.append(owner)
        
        # 중복 제거 (이름 기준)
        seen_names = set()
        unique_owners = []
        for owner in owners:
            if owner.성명 not in seen_names:
                seen_names.add(owner.성명)
                unique_owners.append(owner)
        
        if unique_owners:
            logger.info(f"✅ 총 {len(unique_owners)}명의 소유자 추출 완료: {[o.성명 for o in unique_owners]}")
        else:
            logger.warning("⚠️ 소유자를 찾을 수 없음")
        
        return unique_owners
    
    def _check_trustee(self) -> bool:
        """수탁자 여부 확인 (갑구에 수탁자 키워드가 있는지 확인)"""
        # 마지막 페이지 또는 마지막에서 2번째 페이지의 요약본 확인
        pages_to_check = []
        if len(self.pages_text) >= 1:
            pages_to_check.append(self.pages_text[-1])  # 마지막 페이지
        if len(self.pages_text) >= 2:
            pages_to_check.append(self.pages_text[-2])  # 마지막에서 2번째 페이지
        
        for page_text in pages_to_check:
            # 갑구 섹션 찾기
            gapgu_pattern = r'갑\s*구[\s\S]*?(?=을\s*구|출력일시|$)'
            gapgu_match = re.search(gapgu_pattern, page_text, re.DOTALL | re.IGNORECASE)
            
            if gapgu_match:
                gapgu_text = gapgu_match.group(0)
                # 수탁자 키워드 확인
                if '수탁자' in gapgu_text:
                    return True
        
        return False
    
    def _convert_birth_date(self, yymmdd: str) -> str:
        """주민번호 앞자리를 생년월일로 변환"""
        if len(yymmdd) != 6:
            return yymmdd
        
        yy = int(yymmdd[:2])
        mm = yymmdd[2:4]
        dd = yymmdd[4:6]
        
        # 1900년대 vs 2000년대 판단
        if yy >= 0 and yy <= 26:  # 2000~2026년생
            year = 2000 + yy
        else:  # 1927~1999년생
            year = 1900 + yy
        
        return f"{year}.{mm}.{dd}"
    
    def _extract_ownership_transfer_date(self) -> str:
        """소유권이전일 추출"""
        # 가장 최근 소유권이전 날짜 찾기
        # 패턴: 소유권이전 YYYY년MM월DD일
        pattern = r'소유권이전\s+(\d{4})년(\d{1,2})월(\d{1,2})일'
        matches = list(re.finditer(pattern, self.text))
        
        if matches:
            # 마지막(가장 최근) 매치 사용
            last_match = matches[-1]
            year = last_match.group(1)
            month = last_match.group(2).zfill(2)
            day = last_match.group(3).zfill(2)
            return f"{year}.{month}.{day}"
        
        return ""
    
    def _extract_mortgages(self) -> List[MortgageInfo]:
        """근저당권 설정 내역 추출"""
        mortgages = []
        
        # 을구 섹션 찾기 (근저당권 변경 확인용)
        eulgu_pattern = r'을\s*구[\s\S]*?(?=출력일시|$)'
        eulgu_match = re.search(eulgu_pattern, self.text, re.DOTALL | re.IGNORECASE)
        eulgu_text = eulgu_match.group(0) if eulgu_match else ""
        
        # 방법 1: 주요 등기사항 요약에서 추출 (가장 정확)
        # "3. (근)저당권 및 전세권 등 ( 을구 )" 섹션 찾기
        # [ 참 고 사 항 ] 또는 출력일시 전까지 포함 (2순위 등 모두 포함)
        summary_section_pattern = r'\(근\)저당권\s*및\s*전세권\s*등[\s\S]*?(?=\[\s*참\s*고|출력일시|$)'
        summary_match = re.search(summary_section_pattern, self.text, re.DOTALL | re.IGNORECASE)
        
        if summary_match:
            summary_text = summary_match.group(0)
            # 방법: 모든 "N 근저당권설정" 패턴을 먼저 찾고, 각 순위별로 블록 추출
            # 순위 패턴: "14 근저당권설정" 또는 "14\n근저당권설정" (줄바꿈 허용)
            rank_pattern = r'(\d+)\s+근저당권설정'
            rank_matches = list(re.finditer(rank_pattern, summary_text))
            
            # 디버깅: 찾은 순위 개수 확인
            # print(f"DEBUG: Found {len(rank_matches)} rank matches")
            
            for i, rank_match in enumerate(rank_matches):
                rank = rank_match.group(1)
                start_pos = rank_match.start()
                
                # 다음 순위 또는 [ 참 고 전까지의 블록 추출
                # 다음 rank_match가 있으면 그 전까지, 없으면 [ 참 고 또는 끝까지
                if i + 1 < len(rank_matches):
                    # 다음 순위까지
                    end_pos = rank_matches[i + 1].start()
                else:
                    # 마지막 순위: [ 참 고 또는 끝까지
                    remaining_text = summary_text[start_pos:]
                    next_ref_match = re.search(r'\[\s*참\s*고', remaining_text)
                    if next_ref_match:
                        end_pos = start_pos + next_ref_match.start()
                    else:
                        end_pos = len(summary_text)
                
                rank_block = summary_text[start_pos:end_pos]
                
                # 해당 블록에서 채권최고액 추출 (초기 설정 금액)
                amount_pattern = r'채권최고액[\s\S]*?금?\s*([\d,]+)\s*원'
                amount_match = re.search(amount_pattern, rank_block)
                if not amount_match:
                    continue  # 채권최고액 못 찾으면 건너뛰기
                initial_amount = amount_match.group(1)
                
                # 같은 순위의 근저당권 변경 사항 확인 (요약 블록 내 + 을구)
                # 패턴: "N-M 근저당권 변경" 또는 "N-M 근저당권증액" 또는 "N-M 근저당권감액"
                change_pattern = rf'{rank}\s*-\s*\d+\s*근저당권\s*(?:변경|증액|감액)'
                change_amounts = []
                # 1) 요약 블록 내 변경 사항 (4-2 근저당권변경 등)
                for change_match in re.finditer(change_pattern, rank_block, re.IGNORECASE):
                    change_start = change_match.start()
                    change_block = rank_block[change_start:change_start + 300]
                    change_amount_match = re.search(r'채권최고액[\s\S]*?금?\s*([\d,]+)\s*원', change_block)
                    if change_amount_match:
                        change_amounts.append(change_amount_match.group(1))
                # 2) 을구에서도 변경 사항 확인
                for change_match in re.finditer(change_pattern, eulgu_text, re.IGNORECASE):
                    change_start = change_match.start()
                    change_block = eulgu_text[change_start:change_start + 500]
                    change_amount_match = re.search(r'채권최고액[\s\S]*?금?\s*([\d,]+)\s*원', change_block)
                    if change_amount_match:
                        change_amounts.append(change_amount_match.group(1))
                
                # 가장 마지막 변경 금액이 있으면 그것을 사용, 없으면 초기 설정 금액 사용
                amount = change_amounts[-1] if change_amounts else initial_amount
                
                # 날짜 추출
                date_pattern = r'(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일'
                date_match = re.search(date_pattern, rank_block)
                if date_match:
                    year = date_match.group(1)
                    month = date_match.group(2).zfill(2)
                    day = date_match.group(3).zfill(2)
                else:
                    year = ""
                    month = ""
                    day = ""
                
                # 근저당권자 찾기 (순위 블록에서 직접 추출)
                # rank_block은 이미 다음 순위 전까지만 포함하므로, "근저당권자" 뒤의 텍스트 추출
                # 패턴: "근저당권자 주식회사XXX" (줄바꿈이나 숫자로 시작하는 줄 전까지)
                creditor_match = re.search(r'근저당권자\s*[:：]?\s*([가-힣a-zA-Z0-9]+(?:\s+[가-힣a-zA-Z0-9]+)*)', rank_block)
                if creditor_match:
                    creditor = creditor_match.group(1).strip()
                    # 줄바꿈이나 숫자로 시작하는 부분 제거
                    creditor = re.split(r'\n\s*\d+|\n\s*[가-힣]+\s*근저당권', creditor)[0]
                    creditor = creditor.strip()
                    # 공백 제거
                    creditor = re.sub(r'\s+', '', creditor)
                    # 너무 짧거나 숫자만 있으면 제외
                    if len(creditor) < 2 or creditor.isdigit():
                        creditor = ""
                else:
                    creditor = ""
                
                if not creditor:
                    # Fallback: 전체 텍스트에서 찾기
                    creditor = self._find_creditor_for_mortgage(rank)
                
                if not creditor or len(creditor) < 2:
                    continue  # 근저당권자 못 찾으면 해당 순위 제외
                
                # 채무자: 을구에서 해당 순위의 채무자 찾기 (우선)
                # 을구에서는 "채무자" 뒤에 이름만 나오고, 그 다음 줄에 주소가 나옴
                debtor = ""
                if eulgu_text:
                    # 을구에서 해당 순위의 블록 찾기
                    eulgu_rank_match = re.search(rf'^{rank}\s+근저당권설정', eulgu_text, re.MULTILINE)
                    if eulgu_rank_match:
                        eulgu_start = eulgu_rank_match.start()
                        # 다음 순위번호나 변경 항목 전까지
                        next_rank_match = re.search(rf'^{int(rank)+1}\s+근저당권설정|^{rank}\s*-\s*\d+\s*근저당권', eulgu_text[eulgu_start+1:], re.MULTILINE)
                        if next_rank_match:
                            eulgu_end = eulgu_start + 1 + next_rank_match.start()
                        else:
                            eulgu_end = min(eulgu_start + 1000, len(eulgu_text))
                        
                        eulgu_rank_block = eulgu_text[eulgu_start:eulgu_end]
                        # 을구 블록에서 채무자 찾기 (이름만, 주소 제외)
                        # 패턴: "채무자 이름" (줄바꿈 전까지, 또는 주소 패턴 전까지)
                        debtor_pattern = r'채무자\s+([가-힣]{2,4}(?:\s+[가-힣]{2,4})*?)(?=\s*\n\s*[가-힣]{2,4}\s*(?:시|도|구|동|로|길)|$|\n\s*\d+|\n\s*[가-힣]+\s*근저당권|\n\s*제\d+호)'
                        debtor_match = re.search(debtor_pattern, eulgu_rank_block, re.DOTALL)
                        if debtor_match:
                            debtor = debtor_match.group(1).strip()
                            # 공백 정리
                            debtor = re.sub(r'\s+', ' ', debtor)
                            # 이름이 너무 길면 (주소 포함 가능성) 첫 줄만
                            if len(debtor) > 10:
                                debtor = debtor.split('\n')[0].strip()
                                debtor = re.sub(r'\s+', ' ', debtor)
                
                # 을구에서 못 찾으면 요약의 대상소유자 사용
                if not debtor:
                    debtor = self._find_target_owner_in_section(summary_text, rank)
                
                # 그래도 못 찾으면 순위 블록에서 찾기
                if not debtor:
                    debtor_pattern = r'채무자\s+([가-힣a-zA-Z0-9]+)'
                    debtor_match = re.search(debtor_pattern, rank_block, re.DOTALL)
                    if debtor_match:
                        debtor = debtor_match.group(1).strip()
                    else:
                        debtor = self._find_debtor_for_mortgage(rank)
                
                # 설정일 처리
                if year and month and day:
                    설정일 = f"{year}.{month}.{day}"
                else:
                    설정일 = ""
                
                mortgage = MortgageInfo(
                    순위번호=rank,
                    근저당권자=creditor,
                    채무자=debtor,
                    채권최고액=f"금 {amount}원",
                    설정일=설정일
                )
                mortgages.append(mortgage)
        
        # 방법 1-2: 전체 텍스트에서도 추출 시도 (요약 섹션이 없는 경우)
        # 단, 요약에 "기록사항 없음"이 있으면 근저당권이 모두 말소된 것이므로 추출 생략
        has_no_records = summary_match and "기록사항 없음" in summary_match.group(0)
        if not mortgages and not has_no_records:
            summary_pattern = r'(\d+)\s+근저당권설정\s+(\d{4})년(\d{1,2})월(\d{1,2})일[\s\S]*?채권최고액\s*금?\s*([\d,]+)\s*원'
            
            matches = re.finditer(summary_pattern, self.text)
            for match in matches:
                rank = match.group(1)
                year = match.group(2)
                month = match.group(3).zfill(2)
                day = match.group(4).zfill(2)
                amount = match.group(5)
                
                creditor = self._find_creditor_for_mortgage(rank)
                if not creditor:
                    continue  # 근저당권자 못 찾으면 해당 순위 제외
                debtor = self._find_debtor_for_mortgage(rank)
                
                mortgage = MortgageInfo(
                    순위번호=rank,
                    근저당권자=creditor,
                    채무자=debtor,
                    채권최고액=f"금 {amount}원",
                    설정일=f"{year}.{month}.{day}"
                )
                mortgages.append(mortgage)
        
        # 방법 2: 을구 본문에서 추출 (주요 등기사항 요약이 없는 경우)
        if not mortgages and not has_no_records:
            # 을구에서 근저당권설정 블록 찾기
            # 패턴: 순위번호 근저당권설정 날짜 날짜 채권최고액 금XXX원
            mortgage_block_pattern = r'(\d+)\s+근저당권설정\s+(\d{4})년(\d{1,2})월(\d{1,2})일.*?채권최고액\s*금?\s*([\d,]+)\s*원.*?채무자\s+(\S+).*?근저당권자\s+(\S+)'
            
            matches = re.finditer(mortgage_block_pattern, self.text, re.DOTALL)
            for match in matches:
                rank = match.group(1)
                year = match.group(2)
                month = match.group(3).zfill(2)
                day = match.group(4).zfill(2)
                amount = match.group(5)
                debtor = match.group(6)
                creditor = match.group(7)
                
                mortgage = MortgageInfo(
                    순위번호=rank,
                    근저당권자=creditor,
                    채무자=debtor,
                    채권최고액=f"금 {amount}원",
                    설정일=f"{year}.{month}.{day}"
                )
                mortgages.append(mortgage)
        
        # 말소된 근저당권 제외
        # 별도등기(다른 토지) 문맥 제외: "1토지(을구 3번 근저당권 설정등기" 등은 현재 건물의 을구가 아님
        # → 【 을 구 】 섹션 + (근)저당권 요약에서만 검색하여 오매칭 방지
        eulgu_section_pattern = r'【\s*을\s*구\s*】[\s\S]*?(?=출력일시|$)'
        eulgu_section_match = re.search(eulgu_section_pattern, self.text, re.DOTALL | re.IGNORECASE)
        eulgu_for_cancel = eulgu_section_match.group(0) if eulgu_section_match else eulgu_text
        if not eulgu_for_cancel:
            eulgu_for_cancel = self.text
        summary_for_cancel = summary_match.group(0) if summary_match else ""
        cancel_search_text = (eulgu_for_cancel + "\n" + summary_for_cancel) if summary_for_cancel else eulgu_for_cancel

        active_mortgages = []
        for m in mortgages:
            # 해당 순위번호의 근저당권말소 여부 확인
            # PDF 텍스트 예시: 
            # - "1번근저당권설정등 2011년9월19일 2011년9월19일\n기말소 제60200호 해지"
            # - "1번근저당권설정, 2번근저당권설정등기말소"
            # - "1번근저당권설정등기말소"
            # - "1번근저당권설정\n등기말소"
            rank_num = m.순위번호
            # (?<!\d)로 앞자리 숫자 제외: "4번"이 "14번"에 오매칭되는 것 방지
            # (?<!을구\s): "1토지(을구 3번 근저당권 설정등기" 등 별도등기 문맥 제외 (다른 토지 참조)
            rank_boundary = r'(?<!\d)' if rank_num.isdigit() else ''
            exclude_other_land = r'(?<!을구\s)'  # "을구 3번" = 다른 토지의 을구 3번
            cancel_patterns = [
                # 기본 패턴들 (정확한 매칭)
                rf'{exclude_other_land}{rank_boundary}{rank_num}번\s*근저당권\s*설정\s*등\s*기\s*말\s*소',  # "16번근저당권설정등기말소"
                rf'{exclude_other_land}{rank_boundary}{rank_num}번\s*근저당권\s*설정\s*등.*?\n\s*기\s*말\s*소',  # 줄바꿈으로 분리된 경우
                rf'{exclude_other_land}{rank_boundary}{rank_num}번\s*근저당권\s*설정\s*등\s*기.*?말\s*소',  # 설정등기 뒤 말소
                # 여러 순위가 함께 말소되는 경우: "1번근저당권설정, 2번근저당권설정등기말소"
                rf'{exclude_other_land}{rank_boundary}{rank_num}번\s*근저당권\s*설정[,\s]*.*?등\s*기\s*말\s*소',
                # 순위번호가 나열된 후 말소: "1번, 2번근저당권설정등기말소"
                # .*? 대신 [,\s\d번]* 사용: 주소 "9번 30" 등과의 오매칭 방지
                rf'{exclude_other_land}{rank_boundary}{rank_num}번[,\s]*(?:[,\s]|\d+번)*근저당권\s*설정\s*등\s*기\s*말\s*소',
                # "16번근저당권말소" (설정 없이 직접 말소)
                rf'{exclude_other_land}{rank_boundary}{rank_num}번\s*근저당권\s*말\s*소(?!\s*[가-힣a-zA-Z])',  # 말소 뒤에 다른 텍스트가 오지 않는 경우
            ]

            is_cancelled = False
            for pattern in cancel_patterns:
                if re.search(pattern, cancel_search_text, re.DOTALL | re.IGNORECASE):
                    is_cancelled = True
                    break

            if not is_cancelled:
                active_mortgages.append(m)
        
        # 중복 제거 (순위번호와 채권최고액 기준)
        seen = set()
        unique = []
        for m in active_mortgages:
            key = (m.순위번호, m.채권최고액)
            if key not in seen:
                seen.add(key)
                unique.append(m)
        
        # 전세권 추출 및 통합 (500만원 초과만 포함, 500만원 이하는 표시 안 함)
        jeonse_list = self._extract_jeonse()
        for j in jeonse_list:
            amount_str = re.sub(r'[^\d]', '', j.채권최고액)
            try:
                amount = int(amount_str) if amount_str else 0
                if amount > 5_000_000:  # 500만원 초과 전세권만 표시
                    unique.append(j)
            except ValueError:
                pass
        
        # 순위번호로 정렬
        unique.sort(key=lambda x: int(x.순위번호) if x.순위번호.isdigit() else 999)
        
        return unique
    
    def _extract_jeonse(self) -> List[MortgageInfo]:
        """전세권 추출 (근저당권과 동일한 형식으로 반환)"""
        jeonse_list = []
        
        # 방법 1: 주요 등기사항 요약 섹션에서 전세권 추출
        summary_pattern = r'\(근\)저당권\s*및\s*전세권\s*등[\s\S]*?(?=\[\s*참\s*고|출력일시|$)'
        summary_match = re.search(summary_pattern, self.text, re.DOTALL | re.IGNORECASE)
        
        if summary_match:
            summary_section = summary_match.group(0)
            # 패턴: 순위번호 전세권설정 날짜 전세금 금XXX원 전세권자 XXX
            jeonse_pattern = r'(\d+)\s+전세권설정\s+(\d{4})년(\d{1,2})월(\d{1,2})일[\s\S]*?전세금\s*금?\s*([\d,]+)\s*원[\s\S]*?전세권자\s+(\S+)'
            
            matches = re.finditer(jeonse_pattern, summary_section)
            for match in matches:
                rank = match.group(1)
                year = match.group(2)
                month = match.group(3).zfill(2)
                day = match.group(4).zfill(2)
                amount = match.group(5)
                jeonse_holder = match.group(6).strip()
                
                # 대상소유자 찾기 (채무자 역할)
                debtor = self._find_jeonse_target_owner(summary_section, rank)
                
                jeonse = MortgageInfo(
                    순위번호=rank,
                    근저당권자=jeonse_holder,
                    채무자=debtor,
                    채권최고액=f"금 {amount}원",
                    설정일=f"{year}.{month}.{day}",
                    권리종류="전세권"
                )
                jeonse_list.append(jeonse)
        
        # 방법 2: 을구 본문에서 추출 (요약이 없는 경우)
        if not jeonse_list:
            jeonse_pattern = r'(\d+)\s+전세권설정\s+(\d{4})년(\d{1,2})월(\d{1,2})일.*?전세금\s*금?\s*([\d,]+)\s*원.*?전세권자\s+(\S+)'
            
            matches = re.finditer(jeonse_pattern, self.text, re.DOTALL)
            for match in matches:
                rank = match.group(1)
                year = match.group(2)
                month = match.group(3).zfill(2)
                day = match.group(4).zfill(2)
                amount = match.group(5)
                jeonse_holder = match.group(6).strip()
                
                # 대상소유자 추출 시도 (등기사항증명서에 명시된 경우)
                debtor = self._find_jeonse_debtor(rank)
                
                jeonse = MortgageInfo(
                    순위번호=rank,
                    근저당권자=jeonse_holder,
                    채무자=debtor,
                    채권최고액=f"금 {amount}원",
                    설정일=f"{year}.{month}.{day}",
                    권리종류="전세권"
                )
                jeonse_list.append(jeonse)
        
        # 말소된 전세권 제외
        active_jeonse = []
        for j in jeonse_list:
            # 말소 패턴 확인
            cancel_patterns = [
                rf'{j.순위번호}\s+전세권설정등기말소',
                rf'{j.순위번호}번\s*전세권.*?말소',
                rf'순위번호\s*{j.순위번호}[\s\S]{{0,100}}말소'
            ]
            
            is_cancelled = False
            for pattern in cancel_patterns:
                if re.search(pattern, self.text, re.DOTALL | re.IGNORECASE):
                    is_cancelled = True
                    break
            
            if not is_cancelled:
                active_jeonse.append(j)
        
        return active_jeonse
    
    def _find_jeonse_target_owner(self, section_text: str, rank: str) -> str:
        """요약 섹션에서 전세권의 대상소유자 찾기"""
        pattern = rf'{rank}\s+전세권설정[\s\S]*?전세금\s*금?\s*[\d,]+\s*원[\s\n]*([가-힣]{{2,4}}(?:\s*등)?)(?=\s*\n|제\d+호|전세권자|$)'
        match = re.search(pattern, section_text, re.DOTALL)
        if match:
            name = match.group(1).strip()
            name = re.sub(r'\s+', ' ', name)
            if name and len(name) >= 2:
                return name
        return ""
    
    def _find_jeonse_debtor(self, rank: str) -> str:
        """을구 본문에서 전세권의 대상소유자(임대인) 찾기"""
        # 전세권은 대상소유자 명시가 없는 경우가 많음
        pattern = rf'{rank}\s+전세권설정[\s\S]*?대상소유자\s+([가-힣a-zA-Z0-9\s]+?)(?=\n|$|전세권자|\d+\s+전세권)'
        match = re.search(pattern, self.text, re.DOTALL)
        if match:
            debtor = match.group(1).strip()
            debtor = re.sub(r'\s+', '', debtor)
            if debtor:
                return debtor
        return ""
    
    def _find_target_owner_in_section(self, section_text: str, rank: str) -> str:
        """요약 섹션에서 해당 순위의 대상소유자(채무자 표시용) 찾기"""
        # "N 근저당권설정 ... 채권최고액 금 X원" 뒤 "주수현 등" / "김지은" (줄바꿈 가능)
        pattern = rf'{rank}\s+근저당권설정[\s\S]*?채권최고액\s*금?\s*[\d,]+\s*원[\s\n]*([가-힣]{{2,4}}(?:\s*등)?)(?=\s*\n|제\d+호|근저당권자|$)'
        match = re.search(pattern, section_text, re.DOTALL)
        if match:
            name = match.group(1).strip()
            name = re.sub(r'\s+', ' ', name)
            if name and len(name) >= 2:
                return name
        return ""
    
    def _find_creditor_in_section(self, section_text: str, rank: str) -> str:
        """특정 섹션 내에서 순위번호의 근저당권자 찾기"""
        # 패턴: "N 근저당권설정 ... 근저당권자 XXX" (다음 순위 또는 [ 참 고 전까지)
        # 더 포괄적인 패턴: rank부터 근저당권자까지, 다음 rank나 [ 참 전까지
        pattern = rf'{rank}\s+근저당권설정[\s\S]*?근저당권자\s+([가-힣a-zA-Z0-9]+(?:\s*[가-힣a-zA-Z0-9]+)*?)(?=\s*\d+\s+근저당권설정|\[\s*참|$)'
        match = re.search(pattern, section_text, re.DOTALL)
        if match:
            creditor = match.group(1).strip()
            creditor = re.sub(r'\s+', '', creditor)
            if creditor and len(creditor) >= 2:
                return creditor
        return ""
    
    def _find_debtor_in_section(self, section_text: str, rank: str) -> str:
        """특정 섹션 내에서 순위번호의 채무자 찾기"""
        # 패턴: "1 근저당권설정 ... 채무자 주수현"
        pattern = rf'{rank}\s+근저당권설정[\s\S]*?채무자\s+([가-힣a-zA-Z0-9\s]+?)(?=\n|$|근저당권자|다음|\d+\s+근저당권)'
        match = re.search(pattern, section_text, re.DOTALL)
        if match:
            debtor = match.group(1).strip()
            debtor = re.sub(r'\s+', '', debtor)
            if debtor:
                return debtor
        return ""
    
    def _find_creditor_for_mortgage(self, rank: str) -> str:
        """특정 순위번호의 근저당권자 찾기 (전체 텍스트)"""
        # 을구 본문에서 찾기: "2 근저당권설정 ... 근저당권자 에이피엘대부"
        pattern = rf'{rank}\s+근저당권설정[\s\S]*?근저당권자\s+([가-힣a-zA-Z0-9\s]+?)(?=\n\s*\n|\s*\d+\s+근저당권|채무자|대상소유자|\[|$)'
        match = re.search(pattern, self.text, re.DOTALL)
        if match:
            creditor = match.group(1).strip()
            creditor = re.sub(r'\s+', '', creditor)
            if creditor and len(creditor) >= 2:
                return creditor
        return ""
    
    def _find_debtor_for_mortgage(self, rank: str) -> str:
        """특정 순위번호의 근저당권 채무자 찾기"""
        # 주요 등기사항 요약에서 찾기
        pattern = rf'{rank}\s+근저당권설정[\s\S]*?채무자\s+([가-힣a-zA-Z0-9\s]+?)(?=\n|$|근저당권자|다음)'
        match = re.search(pattern, self.text, re.DOTALL)
        if match:
            debtor = match.group(1).strip()
            debtor = re.sub(r'\s+', '', debtor)
            if debtor:
                return debtor
        
        # 을구 본문에서 찾기
        pattern2 = rf'{rank}\s+근저당권설정[\s\S]*?채무자\s+([가-힣a-zA-Z0-9\s]+?)(?=\n|$|근저당권자|다음)'
        match2 = re.search(pattern2, self.text, re.DOTALL)
        if match2:
            debtor = match2.group(1).strip()
            debtor = re.sub(r'\s+', '', debtor)
            if debtor:
                return debtor
        
        return ""
    
    def _extract_seizures(self) -> List[SeizureInfo]:
        """압류/가압류 정보 추출"""
        seizures = []
        
        # 압류 패턴 - 순위번호 포함하여 더 정확하게
        seizure_pattern = r'(\d+)\s+(압류|가압류)\s+(\d{4})년(\d{1,2})월(\d{1,2})일.*?(?:권리자|채권자)\s+(\S+)'
        
        matches = re.finditer(seizure_pattern, self.text)
        for match in matches:
            rank = match.group(1)
            seizure_type = match.group(2)
            year = match.group(3)
            month = match.group(4).zfill(2)
            day = match.group(5).zfill(2)
            creditor = match.group(6)
            
            seizure = SeizureInfo(
                종류=seizure_type,
                권리자=creditor,
                접수일=f"{year}.{month}.{day}"
            )
            seizures.append(seizure)
        
        # 중복 제거 (종류, 권리자, 접수일 기준)
        seen = set()
        unique = []
        for s in seizures:
            key = (s.종류, s.권리자, s.접수일)
            if key not in seen:
                seen.add(key)
                unique.append(s)
        
        return unique
    
    def _extract_auctions(self) -> List[AuctionInfo]:
        """경매 정보 추출 (말소되지 않은 것만)"""
        auctions = []
        
        # 임의경매, 강제경매 패턴
        auction_pattern = r'(\d+)\s+(임의경매개시결정|강제경매개시결정)\s+(\d{4})년(\d{1,2})월(\d{1,2})일.*?(?:채권자|신청인)\s+(\S+)'
        
        matches = re.finditer(auction_pattern, self.text)
        for match in matches:
            rank = match.group(1)
            auction_type = match.group(2).replace("개시결정", "")
            year = match.group(3)
            month = match.group(4).zfill(2)
            day = match.group(5).zfill(2)
            creditor = match.group(6)
            
            # 해당 경매가 말소되었는지 확인
            cancel_patterns = [
                rf'{rank}번임의경매개시결.*?등기말소',
                rf'{rank}번강제경매개시결.*?등기말소',
                rf'{rank}번\s*임의경매.*?말소',
                rf'{rank}번\s*강제경매.*?말소',
            ]
            
            is_cancelled = False
            for pattern in cancel_patterns:
                if re.search(pattern, self.text, re.DOTALL):
                    is_cancelled = True
                    break
            
            if not is_cancelled:
                auction = AuctionInfo(
                    종류=auction_type,
                    채권자=creditor,
                    접수일=f"{year}.{month}.{day}"
                )
                auctions.append(auction)
        
        return auctions
    
    def _extract_special_conditions(self) -> str:
        """환매특약/전매제한 정보 추출 (요약본 기준 - 말소된 사항 제외, 유효한 사항만)"""
        special_conditions = []
        
        # 요약본에서 환매특약/전매제한 확인
        summary_pattern = r'주요\s*등기사항\s*요약[\s\S]*?(?=\[\s*참\s*고|출력일시|$)'
        summary_match = re.search(summary_pattern, self.text, re.DOTALL | re.IGNORECASE)
        if summary_match:
            summary_text = summary_match.group(0)
            # 환매특약 (줄바꿈 허용: "환매특\n약")
            if re.search(r'환매\s*특\s*약', summary_text, re.DOTALL):
                special_conditions.append("환매특약")
            # 전매제한
            if re.search(r'전매\s*제한|전매제한', summary_text):
                special_conditions.append("전매제한")
        else:
            # 요약본이 없으면 전체 텍스트에서 환매특약 확인 (폴백)
            if re.search(r'환매\s*특\s*약', self.text, re.DOTALL):
                special_conditions.append("환매특약")
        
        # 금지사항 (소유권 제한) - 줄바꿈 허용
        # 단, 신탁등기가 말소된 경우 또는 소유권 이전이 있으면 제외 (소유권 제한이 해소된 경우)
        if re.search(r'금지\s*사항.*?소유권.*?제한', self.text, re.DOTALL):
            # 신탁등기 말소 여부 확인 (갑구에서 확인)
            trust_cancelled = re.search(
                r'신탁\s*등\s*기\s*말\s*소|신탁\s*등기\s*의?\s*말소',
                self.text, re.DOTALL | re.IGNORECASE
            )
            # 소유권 이전이 있으면 해소된 것으로 봄 (신탁등기 말소 후 소유권 이전이 있는 경우가 많음)
            ownership_transfer_exists = re.search(r'소유권\s*이전', self.text, re.DOTALL)
            # 신탁등기 말소 또는 소유권 이전이 있으면 소유권 제한으로 표시하지 않음
            if not trust_cancelled and not ownership_transfer_exists:
                special_conditions.append("소유권제한")
        
        return ", ".join(special_conditions) if special_conditions else ""
    
    def _extract_separate_registry(self) -> bool:
        """별도등기 추출 (말소되지 않은 경우만 True)"""
        # 별도등기/별지등기 패턴 (줄바꿈 허용)
        separate_patterns = [
            r'별\s*도\s*등\s*기',
            r'별\s*지\s*등\s*기',
            r'별\s*지',
        ]
        
        has_separate = False
        for pattern in separate_patterns:
            if re.search(pattern, self.text, re.DOTALL):
                has_separate = True
                break
        
        if not has_separate:
            return False
        
        # 말소 패턴 확인
        cancel_patterns = [
            r'별\s*도\s*등\s*기\s*말\s*소',
            r'별\s*지\s*등\s*기\s*말\s*소',
            r'별\s*지\s*말\s*소',
            r'별\s*도\s*등\s*기\s*등\s*기\s*말\s*소',
            r'별\s*지\s*등\s*기\s*등\s*기\s*말\s*소',
        ]
        
        is_cancelled = False
        for pattern in cancel_patterns:
            if re.search(pattern, self.text, re.DOTALL):
                is_cancelled = True
                break
        
        # 별도등기가 있고 말소되지 않았으면 True
        return has_separate and not is_cancelled


def analyze_pdf(pdf_path: str) -> RegistryDocument:
    """PDF 파일 분석 (메인 함수)"""
    parser = RegistryParser()
    return parser.parse(pdf_path)


def analyze_all_pdfs_in_folder(folder_path: str) -> Dict[str, RegistryDocument]:
    """폴더 내 모든 PDF 분석"""
    results = {}
    
    if not os.path.exists(folder_path):
        logger.error(f"폴더를 찾을 수 없음: {folder_path}")
        return results
    
    pdf_files = [f for f in os.listdir(folder_path) if f.lower().endswith('.pdf')]
    
    for pdf_file in pdf_files:
        pdf_path = os.path.join(folder_path, pdf_file)
        logger.info(f"분석 중: {pdf_file}")
        try:
            doc = analyze_pdf(pdf_path)
            results[pdf_file] = doc
            logger.info(f"파싱 결과:\n{doc.summary()}")
        except Exception as e:
            logger.error(f"에러: {e}", exc_info=True)
    
    return results


# 테스트 실행
if __name__ == "__main__":
    base_dir = os.path.dirname(os.path.abspath(__file__))
    # parsers 폴더에서 상위 폴더로 이동
    project_dir = os.path.dirname(base_dir)
    pdf_dir = os.path.join(project_dir, "pdf_Parsing_example")
    output_file = os.path.join(project_dir, "pdf_analysis_result.txt")
    
    # 결과를 파일로 저장
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("=" * 60 + "\n")
        f.write("등기부등본 PDF 파싱 테스트\n")
        f.write("=" * 60 + "\n")
        
        if not os.path.exists(pdf_dir):
            f.write(f"폴더를 찾을 수 없음: {pdf_dir}\n")
        else:
            pdf_files = [file for file in os.listdir(pdf_dir) if file.lower().endswith('.pdf')]
            f.write(f"발견된 PDF 파일: {len(pdf_files)}개\n\n")
            
            for pdf_file in pdf_files:
                pdf_path = os.path.join(pdf_dir, pdf_file)
                f.write(f"\n분석 중: {pdf_file}\n")
                try:
                    doc = analyze_pdf(pdf_path)
                    f.write(doc.summary() + "\n")
                except Exception as e:
                    f.write(f"  에러: {e}\n")
    
    logger.info(f"분석 결과가 저장되었습니다: {output_file}")
