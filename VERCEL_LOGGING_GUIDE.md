# Vercel 로그 확인 가이드

## 로그가 안 보일 때 확인할 사항

### 1. Vercel 대시보드에서 로그 확인 위치

1. **Vercel 대시보드 접속**
   - https://vercel.com/dashboard

2. **프로젝트 선택**
   - 해당 프로젝트 클릭

3. **Functions 탭**
   - 상단 메뉴에서 "Functions" 탭 클릭
   - `api/webhook.py` 함수 클릭

4. **Logs 탭**
   - 함수 상세 페이지에서 "Logs" 탭 클릭
   - 또는 상단 메뉴에서 "Logs" 탭 클릭

5. **Runtime Logs 확인**
   - 왼쪽 사이드바에서 "Runtime Logs" 확인
   - 실시간 로그 스트림 확인

### 2. 로그 확인 방법

#### 방법 1: Functions 탭에서 확인
```
Vercel 대시보드 → 프로젝트 → Functions → api/webhook.py → Logs
```

#### 방법 2: Deployments 탭에서 확인
```
Vercel 대시보드 → 프로젝트 → Deployments → 최신 배포 → Functions → api/webhook → Logs
```

#### 방법 3: Runtime Logs에서 확인
```
Vercel 대시보드 → 프로젝트 → 상단 "Logs" 메뉴 → Runtime Logs
```

### 3. 테스트 방법

#### GET 요청으로 테스트
```bash
curl https://your-app.vercel.app/api/webhook
```

이 요청 후 Vercel 로그에 다음이 나타나야 합니다:
```
[2024-XX-XX XX:XX:XX] GET REQUEST - Health check
```

#### 텔레그램 메시지로 테스트
1. 텔레그램 봇에 메시지 전송
2. Vercel 로그 확인
3. 다음 로그들이 나타나야 합니다:
   - `WEBHOOK.PY MODULE LOADED - START`
   - `POST REQUEST RECEIVED`
   - `Received update - update_id: ...`

### 4. 로그가 여전히 안 보일 때

#### 확인 사항:
1. **배포가 완료되었는지 확인**
   - Deployments 탭에서 최신 배포 상태 확인
   - "Ready" 상태인지 확인

2. **함수가 실행되는지 확인**
   - GET 요청으로 헬스체크
   - 응답이 오는지 확인

3. **환경 변수 확인**
   - Settings → Environment Variables
   - `TELEGRAM_BOT_TOKEN` 설정 확인

4. **함수 경로 확인**
   - `api/webhook.py` 파일이 올바른 위치에 있는지 확인
   - Vercel은 `api/` 폴더의 파일을 자동으로 서버리스 함수로 인식

5. **Python 버전 확인**
   - `vercel.json`에서 Python 런타임 설정 확인

### 5. 디버깅 팁

#### 로그 레벨 확인
- 현재 모든 로그는 `DEBUG` 레벨로 설정되어 있습니다
- `log_print()` 함수는 stderr와 stdout 모두로 출력합니다

#### 강제 로그 출력
- 모듈 로드 시 즉시 로그 출력
- 함수 호출 시 즉시 로그 출력
- 모든 주요 단계에서 로그 출력

#### 로그 형식
```
[2024-XX-XX XX:XX:XX] 메시지 내용
```

### 6. 문제 해결

만약 여전히 로그가 보이지 않는다면:

1. **Vercel CLI로 로컬 테스트**
   ```bash
   vercel dev
   ```
   로컬에서 로그 확인

2. **간단한 테스트 함수 생성**
   ```python
   # api/test.py
   def handler(request):
       print("TEST LOG - This should appear in Vercel logs")
       return {"ok": True}
   ```

3. **Vercel 지원팀에 문의**
   - 로그 시스템 문제일 수 있음
   - 프로젝트 설정 문제일 수 있음
