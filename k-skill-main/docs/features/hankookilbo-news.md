---
title: 한국일보 뉴스 조회 가이드
description: 한국일보 공식 원격 MCP 서버를 인증 없이 curl 로 직접 호출해 기사 메타데이터를 조회하는 방법
---

# 한국일보 뉴스 조회 가이드

## 이 기능으로 할 수 있는 일

- 한국일보 편집 헤드라인·많이 본·꼼꼼히 본·시간대 추천·최신 기사 목록 조회
- 섹션(정치·경제·사회·국제·문화·스포츠·라이프·사람·지역·오피니언)별 편집 추천 기사 조회
- 주제·인물·사건 기준 기사 검색
- 오늘의 운세·MBTI 운세 기사 링크 조회

## 가장 중요한 규칙

기본 경로는 `https://mcp.hankookilbo.com/mcp` 이고 **인증이 필요 없다**. 한국일보가 직접 운영하는 공개 MCP 서버이므로 `k-skill-proxy` 를 경유하지 않고 사용자 머신에서 바로 호출한다.

서버가 무상태라 `initialize` 핸드셰이크와 세션 ID 없이 단일 POST 로 `tools/call` 이 동작한다. 따라서 MCP SDK 없이 `curl` 만 쓴다.

본 스킬은 **기사 메타데이터와 짧은 발췌만** 다룬다. 기사 본문 전문은 반환되지 않으며 원문 링크에서만 볼 수 있다.

## 먼저 필요한 것

- 인터넷 연결
- `curl`
- 응답 정리용 `python3` (선택)

## 지원 도구

| 도구 | 설명 | 필수 인자 |
| --- | --- | --- |
| `list_top_headlines` | 편집부가 비중 있게 배치한 머리기사 | 없음 |
| `list_popular_news` | 조회수 기준 인기("많이 본") 순위 | 없음 |
| `list_most_read_news` | 홈이 별도 선정한 "꼼꼼히 본 뉴스" | 없음 |
| `list_timely_news` | 시간대에 맞춘 추천 | 없음 |
| `list_latest_news` | 최근 발행 순 | 없음 |
| `list_recommended_articles` | 섹션별 편집 추천(순위 없음) | `section_cd` |
| `search_news` | 주제·인물·사건 검색 | `query` |
| `list_sections` | 섹션 코드 목록 | 없음 |
| `get_daily_horoscope` | 오늘의 운세 기사 | 없음 |
| `get_mbti_horoscope` | MBTI 운세 기사 | 없음 |

## 기본 호출

```bash
curl -fsS --max-time 35 https://mcp.hankookilbo.com/mcp \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -H 'User-Agent: k-skill-hankookilbo/1.0' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"list_top_headlines","arguments":{}}}'
```

`Accept` 헤더에 `application/json` 과 `text/event-stream` 을 둘 다 넣는다. MCP Streamable HTTP 규격이 클라이언트에 요구하는 사항이고, 서버 응답이 나중에 SSE 로 바뀌어도 깨지지 않는다. 헤더를 아예 빼면 406 이다.

섹션별 인기 기사를 뽑아 정리하는 예시:

```bash
curl -fsS --max-time 35 https://mcp.hankookilbo.com/mcp \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -H 'User-Agent: k-skill-hankookilbo/1.0' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"list_popular_news","arguments":{"section_cd":"economy","page_size":5}}}' \
  | python3 -c 'import json,sys
for i in json.load(sys.stdin)["result"]["structuredContent"]["items"]:
    print(i["published_at"], "|", i["title"], "|", i["url"])'
```

## 응답 구조

- `result.structuredContent.items` — 기사 배열. 목록 정리에는 이쪽을 쓴다
- `result.content[0].text` — 사람이 읽는 요약본
- `items[].article_id` / `title` / `url` / `image_url` / `published_at` / `article_type_label` / `view_type` / `excerpt`

`url` 에는 서버가 `?did=mcp` 유입 파라미터를 붙여 돌려준다. 링크를 제시할 때 지우지 않는다.

`view_type` 이 `LoginWall` 이면 원문 열람에 로그인이 필요하다.

`published_at` 표기는 도구별로 다를 수 있다(`2026.07.29 15:20`, `2026-07-28 10:27:02` 등). 문자열을 그대로 쓰거나 필요하면 사용자에게 보여줄 형식으로 다시 포맷한다.

## 운영 팁

- "많이 본"은 `list_popular_news`, "헤드라인"은 `list_top_headlines`, "섹션 추천"은 `list_recommended_articles` 다. 세 목록의 선정 기준이 서로 다르다.
- `section_cd` 를 추측하지 말고 불확실하면 `list_sections` 로 확인한다.
- `search_news` 는 응답이 30초에 가까울 수 있다. `--max-time 35` 를 주고 타임아웃되면 재시도 대신 질의를 좁힌다.
- 기사 제목은 원문을 그대로 인용한다. 요약·의역·말줄임을 거치면 실제 보도 제목과 달라진다.
- `excerpt` 는 도입부 일부이고 기사 전체 요약이 아니다.
- 이 스킬은 한국일보 기사만 반환한다. 언론사를 가리지 않는 일반 뉴스 검색에는 맞지 않는다.

## 실패 모드

- `406`: `Accept` 헤더 누락
- `405`: POST 가 아닌 메서드
- `result.isError: true`: 도구 인자 오류(`section_cd` 오타, `query` 누락)
- `504`: `search_news` 제한 시간 초과. 재시도 루프 금지
- 빈 `items`: 해당 조건의 기사 없음
- 연결 실패: 서버 장애. 재시도 루프 금지

## 출처/참고

- 한국일보 공식 MCP 엔드포인트: https://mcp.hankookilbo.com/mcp
- 공식 MCP Registry 등재: `com.hankookilbo.mcp/hankookilbo-mcp`
- Smithery: https://smithery.ai/servers/hankookilbo/hankookilbo-mcp
- Glama: https://glama.ai/mcp/connectors/com.hankookilbo.mcp/hankookilbo-mcp
- MCP Streamable HTTP 전송 규격: https://modelcontextprotocol.io/specification/2025-06-18/basic/transports
