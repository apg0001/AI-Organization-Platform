# AI 사용량(Claude·Codex)

웹 `사용량` 화면(`/usage`)과 사이드바 아래 미니 막대에서 Claude·Codex 사용률, 초기화까지 남은 시간, 소진 예측을 본다.
수집·예측 방식은 소유자의 GigaCharge(apg0001/AI_Agent_Usage_Widget_for_MAC, MIT)를 Python으로 옮긴 것이다
(`apps/server/src/ai_org/services/usage.py`).

## 출처

| 제공자 | 출처 | 기본값 | 네트워크 |
|---|---|---|---|
| Claude | `GET https://api.anthropic.com/api/oauth/usage`(헤더 `anthropic-beta: oauth-2025-04-20`). Claude Code CLI 로그인 토큰(`~/.claude/.credentials.json`, macOS 키체인 `Claude Code-credentials`)을 **읽기만** 한다 | **꺼짐**(설정에서 켠다) | 있음, 최소 60초 간격 |
| Codex | Codex CLI 세션 기록 `$CODEX_HOME/sessions/**/*.jsonl`(기본 `~/.codex`)의 `rate_limits` | 켜짐 | 없음 |

- Claude 사용량 API는 **비공개 API**다. 형식이 바뀌면 조회가 멈출 수 있고, 화면에 오류 상태로 표시한다.
- 토큰은 DB·로그·API 응답에 남기지 않고 **갱신(refresh)하지 않는다**(갱신하면 CLI 쪽 로그인이 깨질 수 있다). 만료되면
  `claude`를 한 번 실행해 다시 로그인하라고 안내한다. 429면 Retry-After를 지킨다.
- Codex 값은 CLI를 쓸 때만 갱신된다. 마지막 기록의 한도 기간이 지났으면 그 날짜와 함께 "값 없음"으로 보인다.

## 화면에 보이는 것

- 기간별 막대: 채움 = 사용률, 세로선 = 기간 경과율(막대가 선보다 앞서면 시간보다 빨리 쓰는 중). 75% 이상 '주의', 90% 이상 '위험'(아이콘·글자 함께).
- 초기화까지 남은 시간, 시간당 소진 속도, 초기화 시점 예상 사용률, 소진 예상 시각.
- 소진 예측: 같은 초기화 주기의 기록에 최소제곱 회귀. 기록 2개·5분 이상부터 표시, 4개·30분 이상이면 신뢰도 높음. 그 전에는 '학습 중'.
- 이력 그래프(24시간·7일·30일)와 표 보기. 이력은 값이 바뀌거나 5분마다 기록하고 30일 보관한다.

## 알림

설정의 임계치(기본 75·90·100%)를 처음 넘으면 WebSocket `usage.threshold` 이벤트와 활동 기록을 남기고, 웹은 토스트로 알린다.
여러 임계치를 한 번에 넘으면 가장 높은 것만 알린다.

## 설정

| 항목 | 위치 |
|---|---|
| Claude 조회 켜기·Codex 읽기·임계치 | 사용량 화면 → 설정(`PUT /api/v1/usage/settings`, DB `app_settings`) |
| 조회 주기(초, 0이면 자동 조회 끔) | `AI_ORG_USAGE_POLL`(기본 60) |
| Codex 데이터 폴더 | `CODEX_HOME`(기본 `~/.codex`) |
