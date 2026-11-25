# 실행·배포

## 현재: 로컬 개발 실행

README의 설치 후 `./scripts/dev.sh`. 백엔드 `127.0.0.1:8000`, 웹 `127.0.0.1:3000`.

## 로컬 운영 실행(빌드본)

```bash
npm run build                                  # apps/web/dist
apps/server/.venv/bin/ai-org-server &          # API
npx --workspace @ai-org/web vite preview       # 127.0.0.1:3000에서 dist 제공 + /api 프록시
```

백엔드가 정적 파일을 직접 제공하는 단일 프로세스 모드는 Planned.

## 데이터

`~/.ai-org/`(ai-org.db, uploads/, workspaces/, designer/). 백업은 서버를 멈춘 뒤 폴더를 복사한다.
스키마 변경 시 마이그레이션 정책은 DATABASE.md.

## 데스크톱 패키징(TBD)

Tauri 검토 중: Python 백엔드를 사이드카 바이너리(PyInstaller 등)로 묶고 웹을 Tauri 창에서 연다. 결정 전 확인할 것:
Claude Agent SDK 휠 크기(약 170MB, 번들 CLI 포함) 처리, aarch64/Windows 빌드, 자동 업데이트·서명. 결정은 ADR로 남긴다.

## 라이선스

배포물에는 LICENSE(Apache-2.0), NOTICE, THIRD_PARTY_NOTICES.md를 함께 넣는다(Apache-2.0 §4, MIT 고지 유지).

## 하지 않는 것

원격 서버 배포, 외부 노출(리버스 프록시 포함). 루프백 바인딩만 지원한다.
