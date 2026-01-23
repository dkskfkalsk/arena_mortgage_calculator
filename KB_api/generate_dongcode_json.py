# -*- coding: utf-8 -*-
"""
법정동코드 전체자료.txt 파일을 JSON 형식으로 변환하는 스크립트
기존 kb_price_api.py와 호환되는 형식으로 생성
"""

import json
import re
from pathlib import Path
from collections import defaultdict

def parse_dongcode_file(file_path):
    """
    법정동코드 전체자료.txt 파일을 파싱
    
    Args:
        file_path: 법정동코드 전체자료.txt 파일 경로
    
    Returns:
        {
            "regions": {
                "서울특별시": {
                    "districts": {
                        "종로구": {
                            "dongs": {
                                "청운동": {
                                    "code": "1111010100",
                                    "fullName": "서울특별시 종로구 청운동"
                                }
                            }
                        }
                    }
                }
            }
        }
    """
    print(f"파일 읽기 시작: {file_path}")
    
    regions = defaultdict(lambda: defaultdict(lambda: defaultdict(dict)))
    
    with open(file_path, 'r', encoding='utf-8') as f:
        # 헤더 스킵
        next(f)
        
        line_count = 0
        for line in f:
            line = line.strip()
            if not line:
                continue
            
            parts = line.split('\t')
            if len(parts) < 3:
                continue
            
            code = parts[0].strip()
            full_name = parts[1].strip()
            status = parts[2].strip()
            
            # 폐지된 동은 제외
            if status == '폐지':
                continue
            
            # 법정동명 파싱
            # 예: "서울특별시 종로구 청운동"
            # 예: "경기도 수원시 권선구 곡반정동"
            name_parts = full_name.split()
            
            if len(name_parts) < 2:
                continue
            
            # 시/도 추출
            region = name_parts[0]
            
            # 구/시/군 추출
            if len(name_parts) >= 3:
                district = name_parts[1]
                dong = ' '.join(name_parts[2:])  # 나머지가 동명
            elif len(name_parts) == 2:
                # "서울특별시 종로구" 같은 경우
                district = name_parts[1]
                dong = None
            else:
                continue
            
            # 데이터 구조에 추가
            if dong:
                # 동 단위 데이터
                regions[region][district]['dongs'][dong] = {
                    "code": code,
                    "fullName": full_name
                }
            else:
                # 구/시/군 단위 데이터 (동이 없는 경우)
                regions[region][district]['code'] = code
                regions[region][district]['fullName'] = full_name
            
            line_count += 1
            if line_count % 10000 == 0:
                print(f"  처리 중... {line_count:,} 줄")
    
    print(f"파싱 완료: 총 {line_count:,} 줄 처리")
    
    # defaultdict를 일반 dict로 변환
    result = {}
    for region, districts in regions.items():
        result[region] = {
            "districts": {}
        }
        for district, data in districts.items():
            if 'dongs' in data:
                result[region]["districts"][district] = {
                    "dongs": dict(data['dongs'])
                }
            else:
                result[region]["districts"][district] = {
                    "code": data.get('code'),
                    "fullName": data.get('fullName')
                }
    
    return {"regions": result}


def save_json(data, output_path):
    """JSON 파일로 저장"""
    print(f"\nJSON 파일 저장 중: {output_path}")
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(f"저장 완료!")
    
    # 통계 출력
    total_regions = len(data['regions'])
    total_districts = sum(len(v['districts']) for v in data['regions'].values())
    total_dongs = 0
    for region_data in data['regions'].values():
        for district_data in region_data['districts'].values():
            if 'dongs' in district_data:
                total_dongs += len(district_data['dongs'])
    
    print(f"\n통계:")
    print(f"  시/도: {total_regions}개")
    print(f"  구/시/군: {total_districts}개")
    print(f"  동/읍/면: {total_dongs}개")


if __name__ == "__main__":
    # 파일 경로
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    
    input_file = project_root / "법정동코드 전체자료_1.txt"
    output_file = project_root / "kbland_price-main" / "static" / "전국_dongcode_data.json"
    
    if not input_file.exists():
        print(f"오류: 파일을 찾을 수 없습니다: {input_file}")
    else:
        # JSON 변환
        data = parse_dongcode_file(str(input_file))
        
        # 메타데이터 추가
        final_data = {
            "metadata": {
                "created_at": "2025-01-23",
                "version": "2.0",
                "source": "법정동코드 전체자료_1.txt",
                "description": "전국 법정동코드 기반 지역 데이터 (최신)",
                "generator": "generate_dongcode_json.py",
                "dongcode_based": True,
                "accuracy": "100%"
            },
            **data
        }
        
        # 저장
        output_file.parent.mkdir(parents=True, exist_ok=True)
        save_json(final_data, str(output_file))
        
        print(f"\n완료! 출력 파일: {output_file}")
