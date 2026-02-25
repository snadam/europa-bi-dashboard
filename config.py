import os
from pathlib import Path

BASE_DIR = Path(__file__).parent

DATA_IN_DIR = BASE_DIR / "data-in"
DATA_ARCHIVE_DIR = BASE_DIR / "data-archive"
DATA_DIR = BASE_DIR / "data"
REPORTS_DIR = BASE_DIR / "reports"
LOGS_DIR = BASE_DIR / "logs"

DB_PATH = DATA_DIR / "bi_dashboard.db"

ALLOWED_EXTENSIONS = {".csv", ".xlsx"}

REPORT_TIMEOUT_SECONDS = 45

ALLOWED_IMPORTS = {"pandas", "sqlite3", "gradio", "json"}

FORBIDDEN_PATTERNS = [
    "import os",
    "import sys",
    "import subprocess",
    "import shutil",
    "import requests",
    "import urllib",
    "import socket",
    "import threading",
    "import ctypes",
    "import eval",
    "import compile",
    "open(",
    ".to_csv(",
    ".to_excel(",
    ".to_pickle(",
    ".to_json(",
]

for dir_path in [DATA_IN_DIR, DATA_ARCHIVE_DIR, DATA_DIR, REPORTS_DIR, LOGS_DIR]:
    dir_path.mkdir(parents=True, exist_ok=True)
