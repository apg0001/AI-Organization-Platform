# 컴포넌트 가이드라인

## 폴더

```
src/components/
  ui/       Button·IconButton(button.tsx) · Input·Textarea·Select·Label·Field·Switch(form.tsx) · Dialog·Menu·Tabs·Tooltip(overlay.tsx)
  common/   states.tsx: AgentStatus · PageHeader · Section · EmptyState · LoadingState · ErrorState · DeptChip
  layout/   AppShell(사이드바·조직 전환·시스템 상태)
  agent/    AgentAvatar(픽셀 아바타) · AgentEditor(설정 편집기)
  org/      OrgChart(React Flow 조직도) · ChartLegend · orgAsSpec
src/features/<화면>/   화면 전용 컴포넌트(다른 화면에서 쓰이면 components로 올린다)
```

## 공통 컴포넌트와 책임

| 컴포넌트 | 책임 | 주요 props |
|---|---|---|
| `Button` | 행동. variant: primary(화면당 하나)·secondary·ghost·danger·warning, size: sm·md·lg·icon·icon-sm | `asChild`(링크) |
| `IconButton` | 아이콘만 있는 버튼 | `label`(필수, aria-label·title) |
| `Field` | 라벨·컨트롤·도움말/오류 연결 | `label`, `hint`, `error`, `children(id)` |
| `Switch` | 켜기/끄기 + 설명 | `label`, `description` |
| `Dialog/DialogContent` | 집중이 필요한 작업(검토·생성) | `title`, `description`, `wide` |
| `Menu*` | 선택지 목록(조직 전환·컨텍스트 추가) | Radix DropdownMenu |
| `Tabs*` | 한 화면의 보기 전환 | Radix Tabs |
| `Tooltip` | 보조 설명(첫 지연 400ms, 연속 즉시) | `content` |
| `AgentStatus` | 상태 표시(아이콘+글자+색) | `status`, `compact` |
| `PageHeader` / `Section` | 페이지 머리 / 구획(카드 대신) | `title`, `description`, `actions` |
| `EmptyState`·`LoadingState`·`ErrorState` | 상태 화면 | `title`·`action` / `label` / `error`, `retry` |
| `DeptChip` | 부서 표시(점 + 이름, 부서 색) | `name`, `color` |
| `AgentAvatar` | 시그니처 픽셀 아바타 | `id`(옷 색 해시), `lead`(왕관), `size`, `dim` |
| `AgentEditor` | 에이전트 설정(설계·운영 공용), 추천 vs 허용, 권한 제안 수락 | `agent: SpecAgent`, `onChange`, `onAcceptSuggestion` |
| `OrgChart` | 조직도(설계: 편집, 운영: 상태 표시) | `spec`, `statuses`, `onChange`(있으면 편집 가능), `onSelect` |
| `MessageView`·`Composer`·`ActivityList` | 채팅 메시지·입력·도구 사용 목록 | features/command |

## Props 규칙

- 데이터는 API 타입(`lib/api.ts`)을 그대로 받는다. 같은 개념을 위해 새 타입을 만들지 않는다(운영 조직 → `orgAsSpec`로 명세 형태 변환).
- 편집 가능 여부는 콜백 유무로 표현한다(`onChange` 없으면 읽기 전용).
- 스타일 확장은 `className`(마지막에 `cn`으로 병합). 색은 토큰 클래스만.
- 서버 상태는 컴포넌트가 직접 fetch하지 않고 `lib/queries.ts` 훅을 쓴다. 변경은 `useMutation` + 쿼리 무효화.

## 상태별 표현

- 비활성: `opacity` + `disabled`(포커스 불가). 비활성 에이전트는 아바타 흑백.
- 선택: `surface-3` 배경 또는 주색 테두리 + 3px 소프트 링(노드).
- 위험·대기 영역: 앰버 테두리 + 어두운 앰버 배경(#2a2213) — 승인·권한 제안에만.
- 오류 영역: 빨강 테두리 + 어두운 빨강 배경 + `role="alert"`.

## 재사용·확장 원칙

1. 두 화면 이상에서 쓰이면 `components/`로 올린다. 페이지마다 비슷한 컴포넌트를 따로 만들지 않는다.
2. 새 UI 라이브러리를 추가하기 전에 Radix + 토큰으로 만들 수 있는지 본다.
3. 새 상태·색이 필요하면 먼저 `globals.css` 토큰과 DESIGN_SYSTEM.md에 추가한다.
4. 접근성(라벨·포커스·키보드)은 컴포넌트가 기본으로 보장한다.
