# -*- coding: utf-8 -*-
"""KB 페이지 구조 분석 - 재건축 정보 위치 확인"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from playwright.sync_api import sync_playwright
import time

def analyze_page():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)  # 브라우저 표시
        page = browser.new_page(
            viewport={"width": 1280, "height": 720},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
        )
        
        url = "https://kbland.kr/c/4024"
        print(f"페이지 로드: {url}")
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        
        # 초기 대기
        print("10초 대기 중...")
        page.wait_for_timeout(10000)
        
        # body 텍스트 확인
        body_text = page.inner_text("body") or ""
        print(f"\n=== 초기 body_text (길이: {len(body_text)}) ===")
        print(body_text[:500])
        
        # "4단계" 검색
        if "4단계" in body_text:
            print("\n[OK] '4단계' 텍스트 발견!")
            idx = body_text.find("4단계")
            print(f"위치: {idx}")
            print(f"주변 텍스트: ...{body_text[max(0, idx-50):idx+150]}...")
        else:
            print("\n[FAIL] '4단계' 텍스트 없음")
        
        # "재건축" 검색
        if "재건축" in body_text:
            print("\n[OK] '재건축' 텍스트 발견!")
            idx = body_text.find("재건축")
            print(f"위치: {idx}")
            print(f"주변 텍스트: ...{body_text[max(0, idx-50):idx+100]}...")
        
        # 페이지 스크롤 (추가 컨텐츠 로드 유도)
        print("\n\n페이지 스크롤 중...")
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(3000)
        
        # 스크롤 후 body 텍스트 재확인
        body_text_after = page.inner_text("body") or ""
        print(f"\n=== 스크롤 후 body_text (길이: {len(body_text_after)}) ===")
        
        if "4단계" in body_text_after:
            print("\n[OK] 스크롤 후 '4단계' 텍스트 발견!")
            idx = body_text_after.find("4단계")
            print(f"주변 텍스트: ...{body_text_after[max(0, idx-50):idx+150]}...")
        else:
            print("\n[FAIL] 스크롤 후에도 '4단계' 텍스트 없음")
        
        # 특정 엘리먼트 찾기
        try:
            print("\n\n특정 엘리먼트 찾기 시도...")
            # "재건축 진행 현황" 또는 유사 텍스트가 있는 엘리먼트
            elements = page.query_selector_all("text=/재건축/")
            print(f"'재건축' 텍스트 포함 엘리먼트 수: {len(elements)}")
            
            for i, elem in enumerate(elements[:5]):  # 최대 5개만
                try:
                    text = elem.inner_text()
                    print(f"  [{i}] {text[:200]}")
                except:
                    pass
        except Exception as e:
            print(f"엘리먼트 검색 오류: {e}")
        
        print("\n\n브라우저 열린 상태 유지 (수동 확인 가능). 30초 후 종료...")
        time.sleep(30)
        browser.close()

if __name__ == "__main__":
    analyze_page()
