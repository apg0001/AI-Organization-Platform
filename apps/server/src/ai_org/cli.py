"""관리 명령.

`ai-org-admin reset-auth` — 계정·세션을 지워 첫 계정 생성 화면으로 되돌린다(비밀번호를 잊었을 때).
"""

from __future__ import annotations

import argparse

from sqlalchemy import delete, func, select

from ai_org.config import Settings
from ai_org.db import init_db, make_engine, session_factory
from ai_org.models import AuthSession, User


def main() -> None:
    parser = argparse.ArgumentParser(prog="ai-org-admin")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("reset-auth", help="로그인 계정과 세션을 모두 지운다(조직·대화 데이터는 유지)")
    args = parser.parse_args()
    settings = Settings()
    if not (settings.home / "ai-org.db").is_file():
        print(f"데이터가 없습니다({settings.home}). 지울 계정이 없습니다.")
        return
    engine = make_engine(settings.database_url)
    init_db(engine)
    if args.command == "reset-auth":
        with session_factory(engine)() as db:
            removed = db.scalar(select(func.count()).select_from(User)) or 0
            db.execute(delete(AuthSession))
            db.execute(delete(User))
            db.commit()
        print(f"계정 {removed}개와 모든 세션을 지웠습니다. 웹을 열면 새 계정을 만들 수 있습니다.")
