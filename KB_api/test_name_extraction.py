# -*- coding: utf-8 -*-
"""
등기부 이름 추출 테스트 스크립트
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from parsers.registry_parser import RegistryParser

def test_name_extraction(pdf_path):
    """등기부에서 이름 추출 테스트"""
    print(f"\n{'='*60}")
    print(f"테스트 파일: {pdf_path}")
    print(f"{'='*60}\n")
    
    parser = RegistryParser()
    doc = parser.parse(pdf_path)
    
    print("📋 추출된 정보:")
    print(f"  고유번호: {doc.고유번호}")
    print(f"  주소: {doc.부동산_주소}")
    print(f"  면적: {doc.면적}")
    print(f"  층수: {doc.층수정보}")
    print(f"\n👤 소유자 정보 ({len(doc.소유자목록)}명):")
    
    if doc.소유자목록:
        for i, owner in enumerate(doc.소유자목록, 1):
            print(f"  {i}. 성명: {owner.성명}")
            print(f"     생년월일: {owner.생년월일}")
            print(f"     지분: {owner.지분}")
    else:
        print("  ❌ 소유자 정보를 찾을 수 없습니다.")
    
    # 갑구 텍스트 일부 출력 (디버깅용)
    if parser.pages_text:
        last_page = parser.pages_text[-1]
        import re
        gapgu_match = re.search(r'갑\s*구[\s\S]*?(?=을\s*구|출력일시|$)', last_page, re.DOTALL | re.IGNORECASE)
        if gapgu_match:
            gapgu_text = gapgu_match.group(0)
            print(f"\n📄 갑구 텍스트 (처음 500자):")
            print(gapgu_text[:500])
            print("...")
    
    return doc

if __name__ == "__main__":
    # 테스트할 PDF 파일
    test_file = "pdf_Parsing_example/문영순 260108.pdf"
    
    if os.path.exists(test_file):
        test_name_extraction(test_file)
    else:
        print(f"❌ 파일을 찾을 수 없습니다: {test_file}")
        print("\n사용 가능한 PDF 파일:")
        example_dir = "pdf_Parsing_example"
        if os.path.exists(example_dir):
            for f in os.listdir(example_dir):
                if f.endswith('.pdf'):
                    print(f"  - {os.path.join(example_dir, f)}")
