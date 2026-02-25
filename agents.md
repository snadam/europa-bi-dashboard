# Agent Instructions

## Project Overview

Local BI Dashboard - A self-contained, locally hosted Business Intelligence tool that enables non-technical users to generate reports using plain English. Users drop data files (CSV/Excel) into a folder, the app auto-ingests them, and users can create reports by pasting AI-generated Python code.

## Tech Stack

- **Backend**: Python 3.x
- **Frontend**: Gradio (local web UI)
- **Database**: SQLite (serverless, file-based)
- **Data Processing**: Pandas, OpenPyXL
- **PDF Export**: FPDF2
- **Packaging**: PyInstaller (--onedir for Windows)

## Directory Structure

```
europa-bi-dashboard/
├── config.py           # Path constants, security config
├── db_manager.py       # SQLite ingestion, schema evolution, deduplication
├── main.py             # Gradio UI, execution engine
├── requirements.txt    # Dependencies
├── .gitignore
├── data-in/            # Drop zone for CSV/XLSX
├── data-archive/       # Processed files moved here
├── data/               # SQLite database
├── reports/            # Saved report scripts (JSON in DB)
└── logs/               # Audit logs
```

## Key Patterns

### Security Layers (for AI-generated code execution)

1. **AST Scanner** - Validates code before execution, blocks forbidden imports/patterns
2. **Isolated Namespace** - `exec()` runs with restricted globals (only pandas, sqlite3)
3. **Read-Only SQLite** - Connection string uses `?mode=ro` for read-only access
4. **Timeout** - 45 second timeout via multiprocessing
5. **Blocked Patterns** - No file writes (`.to_csv()`, `.to_excel()`), no dangerous imports

### Database Schema

- `data_files` - Tracks imported files
- `data_records` - Stores rows with SHA256 hash for deduplication
- `reports` - Stores user-created report scripts (JSON metadata + code)

### Workflow

1. User drops file in `data-in/`
2. App auto-ingests on startup/refresh
3. User creates report prompt (Dashboard → Create Report)
4. User copies prompt → pastes to external LLM (ChatGPT/Gemini)
5. User pastes AI code back → Dashboard → Import Code
6. Report appears in dropdown → Run → View results

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run locally
python main.py

# Package for Windows (on Windows host)
pyinstaller --onedir main.spec

# Run tests (if available)
pytest
```

## Adding New Features

1. Follow existing code style (no comments, concise)
2. Keep security layers in mind for any code execution features
3. Update this file if adding new patterns or conventions
4. Test locally before committing

## Important Notes

- The app is designed for local Windows use (PyInstaller target)
- External LLMs never have direct access - all code is user-pasted
- Audit logging captures all report executions
