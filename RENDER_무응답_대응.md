# Render가 잘 주다가 계속 안 줄 때

## 원인 후보

1. **슬립(Spin-down)**  
   무료 플랜은 15분 무활동 시 프로세스를 종료합니다.  
   그 다음 들어오는 **첫 요청**은 콜드 스타트(30초~1분)라 Telegram이 타임아웃할 수 있어 회신이 안 갈 수 있습니다.

2. **처리 중 예외**  
   PDF 파싱, KB 시세, Telegram API 호출 등에서 예외가 나면 로그에는 남지만 사용자에게는 회신이 가지 않습니다.

---

## Render 로그로 확인

- `[WEBHOOK] Sending PDF result to user`  
  → 직후에 `PDF result sent successfully` 가 있으면 정상 전송된 것.
- `Error in process() - reply NOT sent:` 또는 `Thread error - reply NOT sent:`  
  → 처리/스레드에서 예외 발생. 아래 traceback으로 원인 확인.

---

## 권장 대응

### 슬립 방지 (가장 효과적)
[UptimeRobot](https://uptimerobot.com) 등에서 **Render 서비스 URL**을 **14분 간격**으로 GET 호출하도록 설정하면, 무활동 종료를 줄일 수 있어 응답이 훨씬 안정됩니다.

### 예외인 경우
로그의 traceback과 환경 변수(`TELEGRAM_BOT_TOKEN`, `PLAYWRIGHT_SCRAPER_URL` 등)를 확인해 네트워크/토큰/외부 API 문제를 해결하세요.
