# ADR-002: 백엔드 — Python FastAPI

- 날짜: 2026-11-25 · 상태: 채택

## 배경
Claude Code 실행 관리, 파일 시스템 접근, WebSocket이 필요하다. Agent Office 서버는 FastAPI다.

## 대안
1. FastAPI(Python) 2. Node(Express/Fastify) + TypeScript Agent SDK 3. Go

## 결정
FastAPI + Pydantic 2 + SQLAlchemy 2. Claude Agent SDK는 Python 패키지를 쓴다.

## 이유
공식 Agent SDK가 Python·TypeScript 모두 있어 런타임 측면은 비슷하다. Agent Office 서버 경험·도구(Ruff, mypy strict, pytest)를 그대로 쓰고,
asyncio로 실행·승인 대기·WebSocket을 한 프로세스에서 다룰 수 있다. Tauri 사이드카로 묶기도 가능하다.

## 영향
+ 검증된 도구 체인. − 웹과 언어가 달라 타입을 수동으로 맞춤(`lib/api.ts`) — OpenAPI 기반 타입 생성은 후속 검토.
