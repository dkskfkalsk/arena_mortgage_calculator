# -*- coding: utf-8 -*-
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from KB_api.kb_price_api import KBPriceAPI
api = KBPriceAPI()
info = api.get_complex_info("14094")
print("get_complex_info(14094):", info)
if info:
    print("법정동코드:", info.get("법정동코드"))
    print("단지명:", info.get("단지명"))
