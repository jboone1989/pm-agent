from sqlalchemy import inspect, text
from sqlalchemy.engine import make_url
from sqlmodel import Session, SQLModel, create_engine

from app.config import DATABASE_URL
from app.services import operation_log as op_log


def _ensure_database_exists() -> None:
    if not DATABASE_URL.startswith("mysql"):
        return
    url = make_url(DATABASE_URL)
    db_name = url.database
    if not db_name:
        return
    import pymysql

    conn = pymysql.connect(
        host=url.host,
        port=url.port or 3306,
        user=url.username,
        password=url.password or "",
        charset="utf8mb4",
    )
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"CREATE DATABASE IF NOT EXISTS `{db_name}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
        conn.commit()
    finally:
        conn.close()


_ensure_database_exists()
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
