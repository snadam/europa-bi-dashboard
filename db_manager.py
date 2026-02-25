import hashlib
import json
import logging
import sqlite3
import shutil
from datetime import datetime
from pathlib import Path

import pandas as pd

import config

logging.basicConfig(
    filename=config.LOGS_DIR / "db_manager.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)


def _init_db():
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS data_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            imported_at TEXT NOT NULL,
            row_count INTEGER
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS data_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id INTEGER NOT NULL,
            row_hash TEXT NOT NULL,
            data_json TEXT NOT NULL,
            FOREIGN KEY (file_id) REFERENCES data_files(id),
            UNIQUE(row_hash)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            code TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def _get_file_hash(row_data):
    row_str = json.dumps(row_data, sort_keys=True, default=str)
    return hashlib.sha256(row_str.encode()).hexdigest()


def _get_table_columns(conn, table_name):
    cursor = conn.execute(f"PRAGMA table_info({table_name})")
    return {row[1] for row in cursor.fetchall()}


def _normalize_column_name(col):
    return col.strip().replace(" ", "_").lower()


def _infer_sql_type(dtype):
    if pd.api.types.is_integer_dtype(dtype):
        return "INTEGER"
    elif pd.api.types.is_float_dtype(dtype):
        return "REAL"
    elif pd.api.types.is_datetime64_any_dtype(dtype):
        return "TEXT"
    else:
        return "TEXT"


def _process_file(file_path: Path) -> tuple[int, int]:
    suffix = file_path.suffix.lower()
    if suffix == ".csv":
        df = pd.read_csv(file_path)
    elif suffix == ".xlsx":
        df = pd.read_excel(file_path)
    else:
        raise ValueError(f"Unsupported file type: {suffix}")

    df.columns = df.columns.map(_normalize_column_name)

    conn = sqlite3.connect(config.DB_PATH)
    cursor = conn.cursor()

    table_name = "data_records"
    existing_cols = _get_table_columns(conn, table_name)
    existing_cols.discard("id")
    existing_cols.discard("file_id")
    existing_cols.discard("row_hash")
    existing_cols.discard("data_json")

    new_cols = set(df.columns) - existing_cols
    for col in new_cols:
        col_type = _infer_sql_type(df[col].dtype)
        alter_sql = f'ALTER TABLE {table_name} ADD COLUMN "{col}" {col_type}'
        cursor.execute(alter_sql)
        logger.info(f"Schema evolution: Added column {col} ({col_type})")

    conn.commit()

    cursor.execute("SELECT MAX(id) FROM data_files")
    max_file_id = cursor.fetchone()[0] or 0
    file_id = max_file_id + 1

    cursor.execute(
        "INSERT INTO data_files (filename, imported_at, row_count) VALUES (?, ?, ?)",
        (file_path.name, datetime.now().isoformat(), len(df))
    )
    conn.commit()

    imported_count = 0
    skipped_count = 0

    for _, row in df.iterrows():
        row_data = row.to_dict()
        row_hash = _get_file_hash(row_data)

        try:
            cursor.execute(
                "INSERT INTO data_records (file_id, row_hash, data_json) VALUES (?, ?, ?)",
                (file_id, row_hash, json.dumps(row_data, default=str))
            )
            imported_count += 1
        except sqlite3.IntegrityError:
            skipped_count += 1

    conn.commit()
    conn.close()

    logger.info(f"Processed {file_path.name}: {imported_count} imported, {skipped_count} skipped (duplicates)")
    return imported_count, skipped_count


def ingest_new_files() -> dict:
    _init_db()

    results = {
        "processed": [],
        "errors": []
    }

    for file_path in config.DATA_IN_DIR.iterdir():
        if file_path.is_file() and file_path.suffix.lower() in config.ALLOWED_EXTENSIONS:
            try:
                imported, skipped = _process_file(file_path)
                archive_path = config.DATA_ARCHIVE_DIR / file_path.name
                counter = 1
                while archive_path.exists():
                    stem = file_path.stem
                    suffix = file_path.suffix
                    archive_path = config.DATA_ARCHIVE_DIR / f"{stem}_{counter}{suffix}"
                    counter += 1
                shutil.move(str(file_path), str(archive_path))
                results["processed"].append({
                    "file": file_path.name,
                    "imported": imported,
                    "skipped": skipped,
                    "archived": archive_path.name
                })
            except Exception as e:
                logger.error(f"Error processing {file_path.name}: {e}")
                results["errors"].append({"file": file_path.name, "error": str(e)})

    return results


def get_schema() -> dict:
    _init_db()
    conn = sqlite3.connect(config.DB_PATH)
    cursor = conn.execute("PRAGMA table_info(data_records)")
    columns = {row[1]: row[2] for row in cursor.fetchall()}
    conn.close()
    return columns


def get_all_data() -> pd.DataFrame:
    _init_db()
    conn = sqlite3.connect(config.DB_PATH)
    df = pd.read_sql_query("SELECT data_json FROM data_records", conn)
    conn.close()
    if not df.empty:
        df["data"] = df["data_json"].apply(json.loads)
        df = df["data"].apply(pd.Series)
        df = df.drop(columns=["data_json"], errors="ignore")
    return df


def save_report(name: str, code: str) -> bool:
    _init_db()
    conn = sqlite3.connect(config.DB_PATH)
    now = datetime.now().isoformat()
    try:
        conn.execute(
            "INSERT INTO reports (name, code, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (name, code, now, now)
        )
        conn.commit()
        conn.close()
        logger.info(f"Report saved: {name}")
        return True
    except sqlite3.IntegrityError:
        conn.close()
        logger.warning(f"Report already exists: {name}")
        return False


def get_reports() -> list[dict]:
    _init_db()
    conn = sqlite3.connect(config.DB_PATH)
    cursor = conn.execute("SELECT id, name, code, created_at, updated_at FROM reports ORDER BY name")
    reports = []
    for row in cursor.fetchall():
        reports.append({
            "id": row[0],
            "name": row[1],
            "code": row[2],
            "created_at": row[3],
            "updated_at": row[4]
        })
    conn.close()
    return reports
