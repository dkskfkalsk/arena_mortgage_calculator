# -*- coding: utf-8 -*-
"""PDF 원문 텍스트 추출 (디버깅용)"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import fitz

def main():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    pdf_dir = os.path.join(base, "pdf_Parsing_example")

    # 김지은, 이근혁, 주수현만
    for name in ["김지은 260123.pdf", "이근혁.pdf", "인천광역시_남동구_논현동_755_4_에코메트로12단지_1210_1001_주수현.pdf"]:
        path = os.path.join(pdf_dir, name)
        if not os.path.exists(path):
            continue
        out = os.path.join(base, "debug_" + name.replace(" ", "_").replace(".pdf", "") + ".txt")
        doc = fitz.open(path)
        text = "\n".join([p.get_text() or "" for p in doc])
        doc.close()
        with open(out, "w", encoding="utf-8") as f:
            f.write(text)
        print("wrote", out)

if __name__ == "__main__":
    main()
