# -*- coding: utf-8 -*-
"""등기부등본 파서 검수: pdf_Parsing_example 폴더 내 모든 PDF 분석"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from parsers.registry_parser import analyze_pdf


def main():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    pdf_dir = os.path.join(base, "pdf_Parsing_example")
    out_path = os.path.join(base, "registry_parser_verify_result.txt")

    pdf_files = sorted([f for f in os.listdir(pdf_dir) if f.lower().endswith(".pdf")])

    lines = []
    lines.append("=" * 70)
    lines.append("등기부등본 파서 검수 결과")
    lines.append("=" * 70)

    for i, name in enumerate(pdf_files, 1):
        path = os.path.join(pdf_dir, name)
        lines.append("")
        lines.append(f"[{i}/{len(pdf_files)}] {name}")
        lines.append("-" * 50)
        try:
            doc = analyze_pdf(path)
            lines.append(f"  고유번호: {doc.고유번호}")
            lines.append(f"  주소: {doc.부동산_주소}")
            lines.append(f"  면적: {doc.면적}")
            lines.append(f"  층수: {doc.층수정보}")
            lines.append(f"  소유권이전일: {doc.소유권이전일}")
            lines.append(f"  소유자: {len(doc.소유자목록)}명")
            for o in doc.소유자목록:
                lines.append(f"    - {o.성명} ({o.생년월일}) {o.지분} {o.주소[:40]}...")
            lines.append(f"  근저당권: {len(doc.근저당권목록)}건")
            for m in doc.근저당권목록:
                lines.append(f"    - {m.순위번호}순위 {m.근저당권자}({m.채무자}) {m.채권최고액}")
            lines.append(f"  압류: {len(doc.압류목록)}건")
            for s in doc.압류목록:
                lines.append(f"    - {s.종류} {s.권리자}")
            lines.append(f"  경매: {len(doc.경매목록)}건")
            for a in doc.경매목록:
                lines.append(f"    - {a.종류} {a.채권자}")
            lines.append(f"  환매특약: {doc.환매특약}")
            lines.append(f"  별도등기: {doc.별도등기}")
        except Exception as e:
            lines.append(f"  ERROR: {e}")

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"Result written to: {out_path}")


if __name__ == "__main__":
    main()
