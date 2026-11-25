# 제3자 고지

이 저장소 자체는 Apache License 2.0(LICENSE)이다. 다음 외부 코드·에셋은 각자의 라이선스 조건을 따른다.

## Agent Office (MIT)

`apps/web/src/features/office/` 의 다음 파일은 Agent Office(https://github.com/apg0001/Agent-Office, `apps/web/src/office/`)에서
가져와 일부 수정했다: `iso.ts`, `grid.ts`, `pathfinding.ts`, `camera.ts`, `walls.ts`, `smoothing.ts`, `presence.ts`,
`headline.ts`, `lab.ts`, `furnitureArt.ts`, `behavior.ts`, `sprites.ts`, `types.ts`, `workspace.ts`, `OfficeScene.ts`.
또한 `apps/server/src/ai_org/runtime/activity.py`의 도구 분류·테스트 명령 판별 규칙은 Agent Office Collector
(`collector/core/internal/adapter/claude/claude.go`, `adapter/command.go`)를 Python으로 옮긴 것이다.

```
MIT License

Copyright (c) 2026 apg0001 and Agent Office contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## GigaCharge (MIT)

`apps/server/src/ai_org/services/usage.py`의 Claude·Codex 사용량 수집 방식, 소진 예측(최소제곱 회귀·신뢰도 기준),
임계치 판정은 GigaCharge(https://github.com/apg0001/AI_Agent_Usage_Widget_for_MAC, `src/main/usageProviders.ts`,
`usageInsights.ts`, `usageNotifications.ts`)를 Python으로 옮긴 것이다. 라이선스 전문은 위 Agent Office 항목과 같은 MIT 문구이며
저작권 표기는 `Copyright (c) 2026 apg0001`이다.

## Kenney Furniture Kit 2.0 (CC0)

`apps/web/public/office/kenney/*.png` — Kenney(www.kenney.nl), CC0 1.0. 원문: `apps/web/public/office/kenney/License.txt`.

## Galmuri (SIL OFL 1.1)

`apps/web/public/fonts/galmuri/` — © 2019–2025 Lee Minseo. 원문: `apps/web/public/fonts/galmuri/LICENSE-OFL.md`.

## npm으로 받는 글꼴

Pretendard(SIL OFL 1.1), JetBrains Mono(SIL OFL 1.1) — `node_modules`에서 번들링된다.

## 프로젝트 Claude Code Skills (`.claude/skills/`)

| Skill | 출처(커밋) | 라이선스 |
|---|---|---|
| frontend-design | anthropics/skills `e4bb5d9` | Apache-2.0 (`LICENSE.txt`) |
| ui-ux-pro-max | nextlevelbuilder/ui-ux-pro-max-skill `8db3633` | MIT (`LICENSE`) — 플러그인 경로를 프로젝트 경로로 수정, 테스트 스크립트 제외 |
| impeccable | pbakaus/impeccable `b49177d` | Apache-2.0 (`LICENSE`) — `scripts/` 제외(바이너리 다운로드·텔레메트리 방지) |
| emil-design-eng, review-animations | emilkowalski/skills `64eb3de` | MIT (`LICENSE`) |
| web-design-guidelines | vercel-labs/agent-skills `5a37a63` | README에 MIT 표기(저장소에 LICENSE 파일 없음) |
