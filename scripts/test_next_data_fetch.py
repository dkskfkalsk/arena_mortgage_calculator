# -*- coding: utf-8 -*-
"""
kbland.kr _next/data JSON 방식 테스트
1. HTML에서 buildId 추출
2. _next/data/{buildId}/c/{complexId}.json 호출
3. 사용승인일, 재건축 정보 파싱
"""
import re
import json
import requests

HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://kbland.kr/",
}


def fetch_html(url: str) -> str:
    r = requests.get(url, headers=HEADERS, timeout=15)
    r.raise_for_status()
    return r.text


def extract_build_id(html: str) -> str | None:
    # __NEXT_DATA__ 스크립트에서 buildId 추출
    m = re.search(r'<script[^>]*id=["\']__NEXT_DATA__["\'][^>]*>([^<]+)</script>', html)
    if m:
        try:
            data = json.loads(m.group(1))
            return data.get("buildId")
        except json.JSONDecodeError:
            pass
    # _buildManifest 또는 다른 패턴
    m = re.search(r'/_next/static/([^/]+)/', html)
    if m:
        return m.group(1)
    return None


def fetch_next_data(build_id: str, complex_id: str) -> dict | None:
    url = f"https://kbland.kr/_next/data/{build_id}/c/{complex_id}.json"
    r = requests.get(url, headers={**HEADERS, "Accept": "application/json"}, timeout=15)
    if not r.ok:
        return None
    return r.json()


def extract_from_next_data(data: dict) -> dict:
    """Next.js 페이지 데이터에서 사용승인일, 재건축, 세대수 추출"""
    result = {
        "approval_date": None,
        "years_since_completion": None,
        "redevelop_stages": [],
        "households": None,
        "buildings": None,
    }

    def find_in_obj(obj, keys, parse_fn=None):
        if obj is None:
            return None
        if isinstance(obj, dict):
            for k in keys:
                v = obj.get(k)
                if v is not None and str(v).strip():
                    return parse_fn(v) if parse_fn else v
        elif isinstance(obj, list):
            for item in obj:
                v = find_in_obj(item, keys, parse_fn)
                if v is not None:
                    return v
        return None

    def find_recursive(obj, target_keys):
        """재귀적으로 객체에서 키 찾기"""
        if obj is None:
            return None
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k in target_keys and v is not None:
                    return v
                r = find_recursive(v, target_keys)
                if r is not None:
                    return r
        elif isinstance(obj, list):
            for item in obj:
                r = find_recursive(item, target_keys)
                if r is not None:
                    return r
        return None

    # pageProps가 일반적인 Next.js 구조
    page_props = data.get("pageProps", {})

    # 사용승인일 패턴: "1987.08.03" 또는 "1987-08-03" + 년차
    def parse_approval(text):
        if not text:
            return None, None
        text = str(text)
        m = re.search(r"(\d{4}[.-]\d{2}[.-]\d{2})", text)
        if m:
            date_str = m.group(1).replace("-", ".")
            years_m = re.search(r"(\d+)\s*년\s*차", text)
            years = int(years_m.group(1)) if years_m else None
            return date_str, years
        return None, None

    # 페이지 텍스트에서 사용승인일 검색 (JSON 내 텍스트 블록)
    def search_text_in_obj(obj, pattern):
        if obj is None:
            return None
        if isinstance(obj, str):
            m = re.search(pattern, obj)
            return m if m else None
        if isinstance(obj, dict):
            for v in obj.values():
                r = search_text_in_obj(v, pattern)
                if r:
                    return r
        elif isinstance(obj, list):
            for item in obj:
                r = search_text_in_obj(item, pattern)
                if r:
                    return r
        return None

    # JSON 전체를 문자열로 변환해 검색 (사용승인일 패턴)
    json_str = json.dumps(data, ensure_ascii=False)
    approval_m = re.search(r"사용\s*승인\s*일\s*(\d{4}[.-]\d{2}[.-]\d{2})\s*(?:\(\s*(\d+)\s*년\s*차\s*\))?", json_str)
    if approval_m:
        result["approval_date"] = approval_m.group(1).replace("-", ".")
        if approval_m.group(2):
            result["years_since_completion"] = int(approval_m.group(2))

    # 재건축 단계: N단계단계명'YYYY.MM.DD
    for m in re.finditer(r"(\d+)단계\s*([가-힣]+)['\s]*(\d{4}\.\d{2}\.\d{2})", json_str):
        result["redevelop_stages"].append({
            "step": int(m.group(1)),
            "name": m.group(2),
            "date": m.group(3),
        })
    if result["redevelop_stages"]:
        result["redevelop_stages"] = list({s["step"]: s for s in result["redevelop_stages"]}.values())
        result["redevelop_stages"].sort(key=lambda x: x["step"])

    # 세대수
    h = find_recursive(data, ["세대수", "총세대수", "총호수", "호수", "households"])
    if h is not None:
        try:
            result["households"] = int(float(str(h).replace(",", "")))
        except (ValueError, TypeError):
            pass

    # 동수
    b = find_recursive(data, ["동수", "총동수", "개동", "buildings"])
    if b is not None:
        try:
            result["buildings"] = int(float(str(b).replace(",", "")))
        except (ValueError, TypeError):
            pass

    return result


def main():
    complex_id = "4024"
    print(f"=== kbland.kr _next/data 테스트 (complex_id={complex_id}) ===\n")

    try:
        print("1. HTML fetch (메인 페이지에서 buildId 획득 시도)...")
        # 메인 페이지가 __NEXT_DATA__ 포함할 가능성 높음
        html = fetch_html("https://kbland.kr/")
        print(f"   메인 HTML 길이: {len(html)} chars")
        if len(html) < 1000:
            print("   메인 페이지 실패, /c/ 페이지 시도...")
            html = fetch_html(f"https://kbland.kr/c/{complex_id}")
            print(f"   /c/ HTML 길이: {len(html)} chars")

        print("\n2. buildId 추출...")
        build_id = extract_build_id(html)
        if not build_id:
            for pattern in [
                r'"buildId"\s*:\s*"([^"]+)"',
                r'buildId["\']?\s*[:=]\s*["\']([^"\']+)["\']',
                r'/_next/static/([a-zA-Z0-9_-]+)/',
            ]:
                m = re.search(pattern, html)
                if m:
                    build_id = m.group(1)
                    print(f"   buildId (pattern): {build_id}")
                    break
        if build_id:
            print(f"   buildId: {build_id}")
        if not build_id:
            print("   buildId 없음. HTML 샘플 저장...")
            with open("debug_html_sample.txt", "w", encoding="utf-8") as f:
                f.write(html[:5000])
            print("   debug_html_sample.txt 저장됨")
            return

        print("\n3. _next/data JSON fetch...")
        next_data = fetch_next_data(build_id, complex_id)
        if not next_data:
            print("   실패")
            return
        print(f"   JSON keys: {list(next_data.keys())}")

        print("\n4. 데이터 추출...")
        extracted = extract_from_next_data(next_data)
        print(f"   approval_date: {extracted['approval_date']}")
        print(f"   years_since_completion: {extracted['years_since_completion']}")
        print(f"   redevelop_stages: {extracted['redevelop_stages']}")
        print(f"   households: {extracted['households']}")
        print(f"   buildings: {extracted['buildings']}")

        print("\n=== 완료 ===")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
