# Deployment Guide

## Development Environment

- **Platform**: Linux (WSL) for development
- **Target Platform**: Windows (via PyInstaller)
- **Python**: 3.x

## Local Development

```bash
# Clone and setup
git clone https://github.com/snadam/europa-bi-dashboard.git
cd europa-bi-dashboard

# Create virtual environment (optional but recommended)
python -m venv venv
source venv/bin/activate  # Linux or: venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Run locally
python main.py
# Access at http://127.0.0.1:7860
```

## GitHub Actions Workflow

Create `.github/workflows/main.yml`:

```yaml
name: CI

on:
  push:
    branches: [main, master]
  pull_request:
    branches: [main, master]

jobs:
  test:
    runs-on: ubuntu-latest
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install pytest
          
      - name: Run tests
        run: |
          pytest tests/ -v
          # If no tests exist, this will pass silently
          
      - name: Lint check (optional)
        run: |
          pip install ruff
          ruff check .
```

## Windows Packaging (PyInstaller)

On a **Windows host** (not WSL):

```powershell
# Install dependencies
pip install -r requirements.txt
pip install pyinstaller

# Build as --onedir (recommended for AV compatibility)
pyinstaller --onedir --name="BI Dashboard" --add-data "config.py;." --add-data "db_manager.py;." main.py

# Output in dist/BI Dashboard/
# Run: dist\BI Dashboard\BI Dashboard.exe
```

### PyInstaller Configuration (main.spec)

```python
# main.spec
a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('config.py', '.'),
        ('db_manager.py', '.'),
    ],
    hiddenimports=['pandas', 'openpyxl', 'gradio', 'fpdf2'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='BI Dashboard',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
```

## Testing

### Unit Tests

Create `tests/` directory and add tests:

```python
# tests/test_db_manager.py
import pytest
import sys
sys.path.insert(0, '.')

from db_manager import _normalize_column_name, _get_file_hash

def test_normalize_column_name():
    assert _normalize_column_name("First Name") == "first_name"
    assert _normalize_column_name("  Date  ") == "date"

def test_get_file_hash():
    hash1 = _get_file_hash({"a": 1, "b": 2})
    hash2 = _get_file_hash({"b": 2, "a": 1})
    assert hash1 == hash2  # Order-independent
```

Run tests:
```bash
pytest tests/ -v
```

### Manual Testing Checklist

1. **Data Ingestion**
   - Drop CSV file in `data-in/` → refresh app → verify data appears
   - Drop XLSX file → verify ingestion
   - Re-drop same file → verify duplicates are skipped

2. **Report Execution**
   - Create prompt → copy to LLM → paste code → save report
   - Run report → verify DataFrame displays
   - Test timeout by creating infinite loop in report

3. **Security**
   - Try importing code with `import os` → should fail
   - Try importing code with `.to_csv()` → should fail

## Distribution

### Portable Windows Executable

1. Build on Windows with PyInstaller (see above)
2. Distribute the entire `dist/BI Dashboard/` folder
3. User runs `BI Dashboard.exe`
4. No installation required

### Directory Structure for Distribution

```
BI Dashboard/
├── BI Dashboard.exe
├── pandas/
├── gradio/
├── sqlite3.dll
└── (other dependencies)
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| App blocked by AV | Use `--onedir` instead of `--onefile` |
| Database locked | Close app, delete `data/bi_dashboard.db` |
| Import errors | Run `pip install -r requirements.txt` |
| Port 7860 in use | Change port in `main.py`: `server_port=7861` |

## CI/CD for Other AI Agents

To replicate this setup:

1. Clone the repo
2. Install: `pip install -r requirements.txt`
3. Run: `python main.py`
4. Test: Create workflow file in `.github/workflows/`
5. Deploy: Build on Windows with PyInstaller
