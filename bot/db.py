"""엔진과 세션 팩토리.

동기 세션을 쓴다. SQLite 로컬 파일 기준으로 쿼리가 짧아 이벤트 루프를 막는
시간이 무시할 만하고, 비동기 드라이버를 얹는 것보다 코드가 단순하다.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker


def build_engine(database_url: str) -> Engine:
    connect_args = {}
    if database_url.startswith("sqlite"):
        # 알림 루프와 커맨드 핸들러가 서로 다른 스레드에서 접근할 수 있다.
        connect_args["check_same_thread"] = False

    engine = create_engine(database_url, echo=False, future=True, connect_args=connect_args)

    if database_url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def _enable_foreign_keys(dbapi_connection, _record):  # pragma: no cover - 드라이버 훅
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def build_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


@contextmanager
def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    """커밋/롤백을 감싸는 세션 컨텍스트."""
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
