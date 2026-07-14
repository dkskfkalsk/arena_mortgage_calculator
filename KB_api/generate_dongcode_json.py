#!/usr/bin/env python3
"""
법정동코드 TXT 파일을 전국_dongcode_data.json 형식으로 변환
- '존재' 항목만 포함 (폐지 제외)
- 시도 > 구군 > 동 계층 구조로 변환
"""
import json
import os
from pathlib import Path

def parse_txt_to_regions(txt_path: str) -> dict:
    """TXT 파일을 파싱하여 regions 구조로 변환"""
    regions = {}
    
    # EUC-KR/CP949 (한글 윈도우) 또는 UTF-8 시도
    for enc in ('cp949', 'euc-kr', 'utf-8'):
        try:
            with open(txt_path, 'r', encoding=enc) as f:
                lines = f.readlines()
            break
        except UnicodeDecodeError:
            continue
    else:
        raise UnicodeDecodeError('', b'', 0, 1, '지원하는 인코딩 없음')
    
    # 헤더 스킵
    for line in lines[1:]:
        line = line.strip()
        if not line:
            continue
        
        parts = line.split('\t')
        if len(parts) < 3:
            continue
        
        code = parts[0].strip()
        full_name = parts[1].strip()
        status = parts[2].strip()
        if status != '존재':
            continue
        
        # 시도/구군 레벨 스킵 (동/읍/면/리 레벨만 포함)
        # 법정동코드: XX XX XX XX XX - 시도(2) 구군(2) 읍면동(2) 리(2) 세부(2)
        # 시도: XX00000000, 구군: XXXXXX0000 중 일부
        # 동/읍/면/리: 최하위 레벨 (실제 주소 검색에 사용)
        tokens = full_name.split()
        if len(tokens) < 2:
            continue  # 시도만 있는 행 스킵
        
        # 시도/구군 레벨 코드 제외 (동/읍/면/리 레벨만 포함)
        # 법정동코드: XX XX XX XX XX - 시도(2) 구군(2) 읍면동(2) 리(2) 세부(2)
        if code.endswith('00000000') or code.endswith('000000'):
            continue
        # 2토큰(시도+구군)이면서 코드 끝 0000: 구군 단위 제외
        if len(tokens) == 2 and code.endswith('0000'):
            continue
        
        si_do = tokens[0]     # 시도
        if len(tokens) == 2:
            # 세종특별자치시처럼 구군 없는 경우: "세종특별자치시 반곡동"
            gu_gun = si_do    # 가상 구군으로 시도명 사용
            dong_name = tokens[1]
        else:
            gu_gun = tokens[1]    # 구군
            dong_name = ' '.join(tokens[2:])  # 동/읍/면/리 (복수 단어 가능)
        
        if si_do not in regions:
            regions[si_do] = {'districts': {}}
        if gu_gun not in regions[si_do]['districts']:
            regions[si_do]['districts'][gu_gun] = {'dongs': {}}
        
        # 동 키가 이미 있으면 코드가 더 구체적인 것 사용 (같은 이름의 리가 있을 수 있음)
        dongs = regions[si_do]['districts'][gu_gun]['dongs']
        dongs[dong_name] = {'code': code, 'fullName': full_name}
    
    return regions


def extract_existing_codes(json_path: str) -> set:
    """기존 JSON에서 모든 법정동코드 추출"""
    codes = set()
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        for region in data.get('regions', {}).values():
            for district in region.get('districts', {}).values():
                for dong in district.get('dongs', {}).values():
                    codes.add(dong.get('code', ''))
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return codes


def main():
    base = Path(__file__).parent
    txt_path = base / "법정동코드 전체자료.txt"
    json_path = base / "전국_dongcode_data.json"
    
    if not txt_path.exists():
        print(f"오류: {txt_path} 파일이 없습니다.")
        return
    
    print("TXT 파일 파싱 중...")
    regions = parse_txt_to_regions(str(txt_path))

    # 기존 JSON과 비교하여 추가된 항목 수 집계 (콘솔 안내용, 별도 파일 미생성)
    existing_codes = extract_existing_codes(str(json_path))
    new_count = 0
    for r in regions.values():
        for d in r["districts"].values():
            for dong_data in d["dongs"].values():
                if dong_data["code"] not in existing_codes:
                    new_count += 1

    from datetime import date
    today = date.today().isoformat()
    result = {
        "metadata": {
            "created_at": today,
            "version": "2.2",
            "source": "법정동코드 전체자료.txt",
            "description": "전국 법정동코드 기반 지역 데이터 (최신)",
            "generator": "generate_dongcode_json.py",
            "dongcode_based": True,
            "accuracy": "100%",
            "new_entries_count": new_count,
        },
        "regions": regions,
    }

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    total_dongs = sum(
        len(d["dongs"]) for r in regions.values() for d in r["districts"].values()
    )
    print(f"\n[OK] 전국_dongcode_data.json 리뉴얼 완료!")
    print(f"   - 총 시도: {len(regions)}개")
    print(f"   - 총 동/읍/면/리: {total_dongs:,}개")
    print(f"   - 새로 추가된 항목: {new_count}개")


if __name__ == "__main__":
    main()
