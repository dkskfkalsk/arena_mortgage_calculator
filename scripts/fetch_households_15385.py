# -*- coding: utf-8 -*-
"""requests만 사용해 15385 세대수 조회 (get_complex_extra_info requests 폴백)."""
import os
import sys

os.environ["VERCEL"] = "1"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from KB_api.kb_complex_scraper import get_complex_extra_info

if __name__ == "__main__":
    r = get_complex_extra_info("15385")
    print("households:", r.get("households"))
    print("error:", r.get("error"))
