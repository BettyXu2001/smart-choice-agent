from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.schema import CreateColumn

from choice_agent.config import Settings


class Base(DeclarativeBase):
    pass


class Database:
    def __init__(self, settings: Settings):
        connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
        self.engine = create_engine(settings.database_url, connect_args=connect_args)
        self.session_factory = sessionmaker(bind=self.engine, expire_on_commit=False)

    def create_all(self) -> None:
        from choice_agent import db_models  # noqa: F401

        Base.metadata.create_all(self.engine)
        self._ensure_agent_run_observability_columns()

    def _ensure_agent_run_observability_columns(self) -> None:
        from choice_agent.db_models import AgentRunRecord

        inspector = inspect(self.engine)
        if "agent_run" not in inspector.get_table_names():
            return
        existing = {column["name"] for column in inspector.get_columns("agent_run")}
        required = (
            "provider",
            "prompt_version",
            "input_tokens",
            "output_tokens",
            "total_tokens",
            "estimated_cost",
            "retry_count",
            "fallback_used",
            "fallback_reason",
        )
        table_name = self.engine.dialect.identifier_preparer.quote("agent_run")
        with self.engine.begin() as connection:
            for name in required:
                if name in existing:
                    continue
                column = AgentRunRecord.__table__.columns[name]
                definition = str(CreateColumn(column).compile(dialect=self.engine.dialect))
                connection.exec_driver_sql(f"ALTER TABLE {table_name} ADD COLUMN {definition}")

    def session(self) -> Generator[Session, None, None]:
        db = self.session_factory()
        try:
            yield db
        finally:
            db.close()
