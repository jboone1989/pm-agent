from sqlalchemy import inspect, text
from sqlmodel import Session, SQLModel, create_engine

from app.config import DATABASE_URL
from app.services import operation_log as op_log

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, echo=False, connect_args=connect_args)


def migrate_db() -> None:
    SQLModel.metadata.create_all(engine)
    inspector = inspect(engine)
    if "workitem" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("workitem")}
    with engine.begin() as conn:
        if "progress" not in columns:
            conn.execute(text("ALTER TABLE workitem ADD COLUMN progress INTEGER NOT NULL DEFAULT 0"))
            conn.execute(text("UPDATE workitem SET progress = 100 WHERE status = 'done'"))
            conn.execute(
                text(
                    "UPDATE workitem SET progress = 50 "
                    "WHERE status = 'in_progress' AND progress = 0"
                )
            )
        if "remote_id" not in columns:
            conn.execute(text("ALTER TABLE workitem ADD COLUMN remote_id INTEGER"))


def init_db() -> None:
    migrate_db()
    with Session(engine) as session:
        op_log.backfill_from_activity_logs(session)


def get_session():
    with Session(engine) as session:
        yield session
