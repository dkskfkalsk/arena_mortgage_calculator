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
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict


@dataclass
class MortgageInfo:
    """근저당권 설정 정보"""
    순위번호: str
    근저당권자: str
    채무자: str
    채권최고액: str
    설정일: str


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
            # 불필요한 부분 제거
            addr = re.sub(r'\s+', ' ', addr)
            return addr
        
        # 대안 패턴
        pattern = r'소재지번[^\n]*\n\s*(.+?)(?:\n|$)'
        match = re.search(pattern, self.text)
        if match:
            return match.group(1).strip()
        
        return ""
    
    def _extract_area(self) -> str:
        """면적 추출 (전용면적)"""
        # 전유부분의 건물의 표시 섹션에서 전용면적 찾기
        # 표제부 > 전유부분의 건물의 표시에 나오는 면적이 전용면적
        
        # 1. 전유부분 표시 섹션에서 찾기 (제X동 제X호 근처의 면적)
        # 패턴: 제2동 제203호 ... XX.XX㎡ 철근콘크리트
        patterns = [
            # 전유부분 건물표시에서 철근콘크리트 앞의 면적
            r'제?\d+호\s+\S*\s+(\d+\.?\d*)\s*㎡\s*철근',
            # 호수 뒤 면적
            r'제?\d+호.*?(\d{2,3}\.?\d*)\s*㎡',
            # 전용면적 명시
            r'전용면적[:\s]*(\d+\.?\d*)\s*㎡',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, self.text, re.DOTALL)
            if match:
                area = match.group(1)
                area_float = float(area)
                # 전용면적 범위 체크 (일반적으로 10~300㎡)
                if 10 <= area_float <= 300:
                    return f"{area}㎡"
        
        # 2. 표제부에서 모든 ㎡ 찾아서 전용면적 범위에 맞는 것 선택
        all_areas = re.findall(r'(\d+\.?\d*)\s*㎡', self.text)
        valid_areas = []
        for area in all_areas:
            area_float = float(area)
            # 전용면적 범위 (보통 20~200㎡, 대형은 300㎡까지)
            if 20 <= area_float <= 200:
                valid_areas.append(area)
        
        # 가장 작은 값이 보통 전용면적 (대지권비율 등 제외)
        if valid_areas:
            # 빈도가 높은 값 또는 첫 번째 적합한 값
            return f"{valid_areas[0]}㎡"
        
        return ""
    
    def _extract_floor_info(self) -> str:
        """층수 정보 추출"""
        # 건물 전체 층수 패턴 (다양한 형태)
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
        """소유자 정보 추출"""
        owners = []
        
        # 갑구에서 최신 소유권이전 찾기
        # 패턴: 소유자 이름 주민번호-******* 주소
        # 주요 등기사항 요약에서 찾기 (더 정확함)
        summary_pattern = r'소유현황.*?(\w+)\s*\(?\s*(?:소유자)?\s*\)?\s*(\d{6})-\*+\s*(단독소유|공동소유|[\d/]+)?\s*([^\n]+)'
        
        # 갑구에서 소유권이전 패턴
        owner_pattern = r'소유권이전\s+\d+년\d+월\d+일\s+\d+년\d+월\d+일\s+매매\s+소유자\s+(\S+)\s+(\d{6})-[\d\*]+\s*\n?\s*([^\n]+)'
        
        # 주요 등기사항 요약 페이지에서 추출 시도
        summary_owner_pattern = r'(\S{2,4})\s*\(?\s*소유자\s*\)?\s*(\d{6})-\*+\s*(단독소유|[\d/]+지분)?\s*([가-힣\s\d\-\(\),]+?)(?=\d+\s|$|\n\n)'
        
        matches = re.finditer(summary_owner_pattern, self.text)
        for match in matches:
            name = match.group(1).strip()
            resident_num = match.group(2)
            share = match.group(3) or "단독소유"
            address = match.group(4).strip() if match.group(4) else ""
            
            # 생년월일 변환 (YYMMDD -> YYYY.MM.DD)
            birth = self._convert_birth_date(resident_num)
            
            owner = OwnerInfo(
                성명=name,
                주민번호=f"{resident_num}-*******",
                생년월일=birth,
                주소=address,
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
        
        return unique_owners
    
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
        
        # 방법 1: 주요 등기사항 요약에서 추출 (가장 정확)
        # 패턴: "1 근저당권설정 2025년12월11일 채권최고액 금70,000,000원 김인아"
        #       "제6520871호 근저당권자 황순나"
        summary_pattern = r'(\d+)\s+근저당권설정\s+(\d{4})년(\d{1,2})월(\d{1,2})일\s*\n?\s*제?\d*호?\s*채권최고액\s*금?([\d,]+)원\s+(\S+)'
        
        matches = re.finditer(summary_pattern, self.text)
        for match in matches:
            rank = match.group(1)
            year = match.group(2)
            month = match.group(3).zfill(2)
            day = match.group(4).zfill(2)
            amount = match.group(5)
            # 이 위치의 이름은 대상소유자(채무자)
            debtor = match.group(6)
            
            # 근저당권자 찾기
            creditor = self._find_creditor_for_mortgage(rank)
            
            mortgage = MortgageInfo(
                순위번호=rank,
                근저당권자=creditor,
                채무자=debtor,
                채권최고액=f"금 {amount}원",
                설정일=f"{year}.{month}.{day}"
            )
            mortgages.append(mortgage)
        
        # 방법 2: 을구 본문에서 추출 (주요 등기사항 요약이 없는 경우)
        if not mortgages:
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
        active_mortgages = []
        for m in mortgages:
            # 해당 순위번호의 근저당권말소 여부 확인
            # PDF 텍스트 예시: 
            # - "1번근저당권설정등 2011년9월19일 2011년9월19일\n기말소 제60200호 해지"
            # - "1번근저당권설정, 2번근저당권설정등기말소"
            # - "1번근저당권설정등기말소"
            # - "1번근저당권설정\n등기말소"
            rank_num = m.순위번호
            cancel_patterns = [
                # 기본 패턴들
                rf'{rank_num}번\s*근저당권\s*설정\s*등\s*기\s*말\s*소',  # 한 줄로 된 경우
                rf'{rank_num}번\s*근저당권\s*설정\s*등.*?\n\s*기\s*말\s*소',  # 줄바꿈으로 분리된 경우
                rf'{rank_num}번\s*근저당권\s*말\s*소',  # 간단한 형태
                rf'{rank_num}번\s*근저당권\s*설정.*?말\s*소',  # 설정 뒤 말소
                rf'{rank_num}번\s*근저당권\s*설정\s*등\s*기.*?말\s*소',  # 설정등기 뒤 말소
                # 여러 순위가 함께 말소되는 경우: "1번근저당권설정, 2번근저당권설정등기말소"
                rf'{rank_num}번\s*근저당권\s*설정[,\s]*.*?등\s*기\s*말\s*소',
                # 순위번호가 나열된 후 말소: "1번, 2번근저당권설정등기말소"
                rf'{rank_num}번[,\s]*.*?근저당권\s*설정\s*등\s*기\s*말\s*소',
                # 더 포괄적인 패턴
                rf'{rank_num}번.*?근저당권.*?말\s*소',
            ]
            
            is_cancelled = False
            for pattern in cancel_patterns:
                if re.search(pattern, self.text, re.DOTALL | re.IGNORECASE):
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
        
        return unique
    
    def _find_creditor_for_mortgage(self, rank: str) -> str:
        """특정 순위번호의 근저당권자 찾기"""
        # 주요 등기사항 요약에서 찾기
        pattern = rf'{rank}\s+근저당권설정.*?근저당권자\s+(\S+)'
        match = re.search(pattern, self.text, re.DOTALL)
        if match:
            return match.group(1)
        
        # 을구 본문에서 찾기
        pattern2 = rf'근저당권설정.*?제\d+호.*?근저당권자\s+(\S+)'
        match2 = re.search(pattern2, self.text, re.DOTALL)
        if match2:
            return match2.group(1)
        
        return ""
    
    def _find_debtor_for_mortgage(self, rank: str) -> str:
        """특정 순위번호의 근저당권 채무자 찾기"""
        pattern = rf'{rank}\s+근저당권설정.*?채무자\s+(\S+)'
        match = re.search(pattern, self.text, re.DOTALL)
        if match:
            return match.group(1)
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
        """환매특약/전매제한 정보 추출"""
        special_conditions = []
        
        # 환매특약 패턴 (줄바꿈이 중간에 들어가는 경우도 처리: "환매특\n약")
        if re.search(r'환매\s*특\s*약', self.text, re.DOTALL):
            special_conditions.append("환매특약")
        
        # 전매제한 (주택법 관련) - 줄바꿈 허용
        if re.search(r'주택법.*?제\d+조.*?기간.*?지나기\s*전', self.text, re.DOTALL):
            special_conditions.append("전매제한")
        
        # 금지사항 (소유권 제한) - 줄바꿈 허용
        # 단, 신탁등기가 말소된 경우는 제외 (소유권 이전으로 해소된 경우)
        if re.search(r'금지\s*사항.*?소유권.*?제한', self.text, re.DOTALL):
            # 신탁등기 말소 여부 확인
            trust_cancelled = re.search(r'신탁\s*등\s*기\s*말\s*소', self.text, re.DOTALL | re.IGNORECASE)
            # 소유권 이전으로 해소된 경우 확인
            ownership_transfer_after = re.search(r'소유권\s*이전.*?신탁\s*등\s*기\s*말\s*소|신탁\s*등\s*기\s*말\s*소.*?소유권\s*이전', self.text, re.DOTALL | re.IGNORECASE)
            
            # 신탁등기가 말소되고 소유권 이전이 있으면 소유권 제한으로 표시하지 않음
            if not (trust_cancelled and ownership_transfer_after):
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
        print(f"폴더를 찾을 수 없음: {folder_path}")
        return results
    
    pdf_files = [f for f in os.listdir(folder_path) if f.lower().endswith('.pdf')]
    
    for pdf_file in pdf_files:
        pdf_path = os.path.join(folder_path, pdf_file)
        print(f"\n분석 중: {pdf_file}")
        try:
            doc = analyze_pdf(pdf_path)
            results[pdf_file] = doc
            print(doc.summary())
        except Exception as e:
            print(f"  에러: {e}")
    
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
    
    print(f"분석 결과가 저장되었습니다: {output_file}")
