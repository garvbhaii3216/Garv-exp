import os
import shutil
from datetime import datetime
from dotenv import load_dotenv
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import declarative_base, sessionmaker

# Load environment variables from .env
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./expense_tracker.db")

connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args["check_same_thread"] = False

engine = create_engine(DATABASE_URL, connect_args=connect_args)


def create_database_backup():
    """Create an automated rolling backup of SQLite database to prevent accidental data loss."""
    if not DATABASE_URL.startswith("sqlite"):
        return
    db_file = DATABASE_URL.replace("sqlite:///", "").replace("sqlite://", "").split("?")[0]
    if os.path.exists(db_file) and os.path.getsize(db_file) > 0:
        backup_dir = "backups"
        os.makedirs(backup_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = os.path.join(backup_dir, f"expense_tracker_backup_{timestamp}.db")
        shutil.copy2(db_file, backup_filename)
        # Keep latest 15 backups to prevent infinite disk growth
        existing_backups = sorted(
            [os.path.join(backup_dir, f) for f in os.listdir(backup_dir) if f.startswith("expense_tracker_backup_")],
            key=os.path.getmtime
        )
        if len(existing_backups) > 15:
            for old_b in existing_backups[:-15]:
                try:
                    os.remove(old_b)
                except OSError:
                    pass


# Enable SQLite Foreign Key constraints, WAL mode, and Account Immutability Triggers
@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    if DATABASE_URL.startswith("sqlite"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")

        # Guarantee Account Immutability:
        # Trigger 1: Disallow ANY deletion of user records
        cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS prevent_user_deletion
            BEFORE DELETE ON users
            BEGIN
                SELECT RAISE(ABORT, 'ACCOUNT IMMUTABILITY: User accounts cannot be deleted once created.');
            END;
        """)

        # Trigger 2: Disallow modification of core identity fields (id, email, created_at)
        cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS prevent_user_identity_modification
            BEFORE UPDATE OF id, email, created_at ON users
            BEGIN
                SELECT RAISE(ABORT, 'ACCOUNT IMMUTABILITY: Immutable user identity fields (id, email, created_at) cannot be modified.');
            END;
        """)
        cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

