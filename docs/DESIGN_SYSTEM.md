# 디자인 시스템

토큰의 단일 출처: `apps/web/src/styles/globals.css`. 컴포넌트는 Tailwind 유틸리티로 노출된 토큰만 쓰고 임의 색을 쓰지 않는다.

## 1. 컨셉

**Professional Developer Tool + AI Organization Simulator.** 이 제품의 장면은 '밤에 불 켜진 사무실의 운영 책상'이다.
업무 화면은 조용하고 촘촘한 도구(Linear 같은 정돈, 개발 도구의 정보 밀도)로 두고, 개성은 **한 곳에만** 쓴다:

> **시그니처: 픽셀 캐릭터 아바타.** 사무실 캐릭터와 같은 픽셀 그림(`sprites.ts`)을 SVG로 그려 모든 화면의 에이전트 표시에 쓴다.
> 이니셜 원 대신 '사무실 속 그 사람'이 보이게 해 SaaS 화면과 아이소메트릭 사무실을 하나의 제품으로 잇는다.

그 밖의 장식(그라데이션, 카드 그림자, 유리 효과, 장식 애니메이션)은 쓰지 않는다.

설계 과정(frontend-design Skill의 2단계): 토큰 계획 → '어떤 비슷한 제품에도 나올 기본값인가?' 검토 → 수정. 수정한 점:
흔한 '거의 검정 + 형광 강조' 대신 아주 약한 청색 차콜 + 브리프가 지정한 청·인디고 주색, 경고 앰버는 '당신을 기다림'(승인)에만 써서
사무실 머리 위 `!` 표식과 의미를 맞췄다. 카드 격자 대신 섹션 제목 + 구분선 + 표·목록.

## 2. 색

| 토큰 | 값 | 용도 | 대비(bg 대비) |
|---|---|---|---|
| `--bg` | #0e1015 | 바탕 | — |
| `--surface-1` | #14171e | 사이드바·패널 | — |
| `--surface-2` | #1a1e27 | 입력·팝오버 | — |
| `--surface-3` | #222734 | 선택·hover | — |
| `--border` / `--border-strong` | #262b37 / #353b4a | 구분선 / 컨트롤 테두리 | 장식(텍스트 아님) |
| `--text` | #e6e8ee | 본문 | 15.5:1 |
| `--text-muted` | #a0a6b6 | 보조 | 7.8:1 |
| `--text-faint` | #7d8496 | 메타·힌트 | 5.1:1 (surface-2 4.5:1) |
| `--primary` | #4c63e8 | 채운 주 버튼 배경 | 흰 글자 4.9:1 |
| `--primary-text` | #97a6ff | 링크·강조 글자·포커스 링 | 8.4:1 |
| `--success` | #45c486 | 완료·연결됨 | 8.6:1 |
| `--warning` | #f0b44c | 승인 대기·주의 | 10.3:1 |
| `--danger` / `--danger-solid` | #f47272 / #c93c3c | 오류 글자 / 위험 버튼 배경 | 6.8:1 / 흰 글자 4.2:1(굵은 13px 이상만) |

**에이전트 상태**(항상 아이콘 + 글자와 함께, 색만으로 구분 금지):

| 상태 | 색 토큰 | 아이콘(lucide) | 글자 |
|---|---|---|---|
| idle | `--status-idle` #959cae | CircleDashed | 대기 |
| thinking | `--status-thinking` #b39dfb | Sparkles(펄스) | 생각 중 |
| working | `--status-working` #97a6ff | Wrench(펄스) | 작업 중 |
| waiting | `--status-waiting` #f0b44c | Hand | 승인 대기 |
| reviewing | `--status-reviewing` #55c8dc | Telescope(펄스) | 검토 중 |
| completed | `--status-completed` #45c486 | CheckCircle2 | 완료 |
| failed | `--status-failed` #f47272 | XCircle | 실패 |
| offline | `--status-offline` #5c6273 | MoonStar | 꺼짐 |

**부서 색** `--dept-1..8`: 낮은 채도 8색(조직도 칩의 점과 글자). 명세에는 토큰 이름(`dept-3`)만 저장한다.
**협업 선**: 전달 `dept-2`, 검토 `dept-3`, 자문 `dept-6` + 점선 + 라벨(색만으로 구분하지 않음).

## 3. 타이포그래피

- 본문·제목: **Pretendard Variable**(한글·영문 균형, OFL). 코드·경로·ID·명령: **JetBrains Mono Variable** — 실제 코드·데이터에만(장식용 모노 금지).
- 사무실 지도 라벨: Galmuri11(픽셀).
- 스케일(px/행간): 2xs 11/16 · xs 12/18 · sm 13/20 · **base 14/22(기본)** · md 16/24 · lg 20/28(페이지 제목) · xl 24/32.
- 굵기: 400 본문, 500 라벨·이름, 600 제목. 숫자 열은 `tabular` 클래스.
- 제목 `text-wrap: balance`, 본문 최대 폭 70ch, 채팅 응답 최대 폭 3xl(약 72ch).
- 문구: 문장형, 대문자 라벨·눈썹 라벨·장식 번호 금지. 버튼은 동작 이름("조직 생성", "허용"). 로딩은 "…"로 끝낸다.

## 4. 간격·레이아웃

- 4px 그리드: 1(4) 1.5(6) 2(8) 2.5(10) 3(12) 4(16) 5(20) 6(24) 8(32) 10(40).
- 페이지 여백 24px(`px-6`), 섹션 간 32px(`gap-8`), 섹션 안 12px.
- 셸: 사이드바 224px(좁은 화면 56px 아이콘), 본문 유동. 커맨드 센터 3열(240 · 유동 · 320), 설계 작업 공간 2열(380 · 유동) + 오른쪽 설정 서랍 400px.

## 5. 모서리·그림자

- 반경: sm 4(배지·칩) · md 6(컨트롤) · lg 10(패널·대화상자·노드).
- 그림자: 오버레이(팝오버·대화상자·서랍)에만 `--shadow-overlay`(오프셋 + 블러). 평면 요소는 그림자 대신 테두리.

## 6. 아이콘

lucide-react, 16px(컨트롤 안), 14px(메타), 선 굵기 기본값. 이모지를 아이콘으로 쓰지 않는다(사무실 지도 말풍선만 Agent Office 연출 유지).
아이콘만 있는 버튼은 `IconButton`(aria-label + title 필수).

## 7. 모션

- 사용자 행동에 대한 응답만: 버튼 누름(scale 0.98, 100ms), 색 전환 120ms, 오버레이 등장 160ms(`--ease-out`, scale 0.97에서 시작 — 0에서 시작 금지, 트리거 쪽 origin).
- 지속 모션: 작업 중 상태 점 펄스(1.6s)와 스트리밍 커서만. `prefers-reduced-motion`이면 모두 정지.
- 사무실 캐릭터 연출은 별도 영역(Phaser)이며 업무 화면에 섞지 않는다.

## 8. 테마

테마 4종: **다크**(기본, 위 표의 값), **라이트**, **고대비**, **시스템 설정**(OS의 라이트·다크·대비 높임 설정을 따름).
`globals.css`의 `:root[data-theme="light"|"contrast"]`가 같은 토큰 이름에 값만 다시 정한다(자동 반전이 아니라 면마다 고른 값).
선택은 화면 왼쪽 아래 `화면 설정` 메뉴 → localStorage(`ai-org.theme`) + 로그인한 경우 계정 설정(`settings.theme`)에 저장한다.
`index.html`의 인라인 스크립트가 첫 그리기 전에 적용해 깜빡임이 없다.

| 토큰 | 라이트 | 고대비 |
|---|---|---|
| `--bg` / `--surface-1` / `--surface-3` | #f6f7f9 / #ffffff / #eceef3 | #000000 / #0a0a0a / #262626 |
| `--text` / `--text-muted` / `--text-faint` | #171a21(16.2:1) / #4d5465(7.1:1) / #636a7b(5.0:1) | #ffffff / #e0e0e0 / #c2c2c2(모두 7:1 이상) |
| `--primary` / `--primary-text` | #3d55d9(흰 글자 6.0:1) / #3249c4(6.8:1) | #3b55f0 / #b3beff |
| `--success` / `--warning` / `--danger` | #1b8150 / #9a6200 / #c62f2f(모두 4.5:1 이상) | #5fe0a0 / #ffc861 / #ff8f8f |
| `--ring` | #3d55d9 | #ffd84d(노랑, 3px) |

파생 토큰(모든 테마): `--on-warning`(경고 배경 위 글자), `--warning-surface`·`--warning-border`(승인 상자), `--danger-surface`·`--danger-border`(오류 상자),
`--code-bg`·`--code-*`(코드 블록·하이라이트), `--input-hover`, `--scrim`(대화상자 가림막), `--selection`, `--chart-1`(차트 선).
컴포넌트에 `#hex`를 쓰지 않는다. 예외: 사무실 장면(Phaser 캔버스)은 '밤의 사무실' 그림이라 테마와 관계없이 같은 색을 쓴다.

## 9. 브라우저 표면

선택 영역(주색 32%), 캐럿(`--primary-text`), 얇은 스크롤바(`--border-strong`), `:focus-visible` 2px 링, 링크 밑줄 오프셋 3px.
