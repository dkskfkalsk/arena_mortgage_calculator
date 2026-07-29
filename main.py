# -*- coding: utf-8 -*-
"""
로컬 Polling 진입점은 비활성화되었습니다.

운영은 Vercel 웹훅만 사용합니다. PC·터널(polling/ngrok/inkognit 등)로
텔레그램 업데이트를 받지 않도록 원천 차단합니다.
"""

import sys


def main() -> int:
    print(
        "로컬 봇(Polling)은 비활성화되어 있습니다.\n"
        "운영은 Vercel 웹훅만 사용하세요.\n\n"
        "웹훅 확인: python scripts/set_webhook.py --check\n"
        "웹훅 설정: python scripts/set_webhook.py https://<app>.vercel.app/api/webhook\n"
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
