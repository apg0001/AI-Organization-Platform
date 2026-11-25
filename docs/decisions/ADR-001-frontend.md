# ADR-001: 프론트엔드 — React + TypeScript + Vite + Tailwind v4 + Radix(shadcn 방식)

- 날짜: 2026-11-25 · 상태: 채택

## 배경
조직도 편집, 채팅, 설정 화면이 많은 SaaS형 UI와 Phaser 사무실을 한 제품에 담아야 한다. Agent Office는 React 19 + Vite + Phaser 4(CSS 직접 작성)다.

## 대안
1. Agent Office 방식(직접 작성 CSS, 컴포넌트 라이브러리 없음) 2. Next.js 3. React + Vite + Tailwind + shadcn/ui 방식(Radix) 4. Svelte/Vue

## 결정
React 19 + TS 7 + Vite 8(Agent Office와 같은 버전대) + Tailwind v4(토큰을 `@theme`로 노출) + Radix 프리미티브로 shadcn 방식 컴포넌트를 직접 작성.
조직도는 React Flow 13 + dagre, 서버 상태는 TanStack Query, 라우팅은 React Router, 아이콘 lucide.

## 이유
사무실 코드를 그대로 쓰려면 React + Phaser가 유리하다. 로컬 앱이라 SSR(Next.js)이 필요 없다. shadcn 방식은 접근성 있는 프리미티브를
소스로 소유해 디자인 토큰에 맞추기 쉽다. CLI 생성 대신 필요한 컴포넌트만 작성해 의존성을 줄였다.

## 영향
+ 디자인 시스템을 토큰 한 곳에서 관리. + 사무실·조직도 재사용. − Tailwind·Radix 학습 비용. − 초기 번들(라우트 단위 지연 로딩으로 완화).
