import ast
import importlib
import io
import json
import logging
import multiprocessing
import sys
import time
import traceback
from datetime import datetime

import gradio as gr
from gradio import Theme
import pandas as pd
import sqlite3

import config
import db_manager

custom_css = """
:root {
    --primary: #2563eb;
    --primary-hover: #1d4ed8;
    --secondary: #64748b;
    --bg-main: #f8fafc;
    --bg-card: #ffffff;
    --text-primary: #1e293b;
    --text-secondary: #64748b;
    --border: #e2e8f0;
    --success: #10b981;
    --warning: #f59e0b;
    --danger: #ef4444;
}

body {
    background: var(--bg-main) !important;
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif !important;
}

.gradio-container {
    max-width: 1400px !important;
    margin: 0 auto !important;
}

/* Header styling */
.header {
    background: linear-gradient(135deg, #1e293b 0%, #334155 100%);
    padding: 1.5rem 2rem;
    border-radius: 12px;
    margin-bottom: 1.5rem;
    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
}

.header h1 {
    color: #ffffff !important;
    font-size: 1.75rem !important;
    font-weight: 600 !important;
    margin: 0 !important;
}

.header p {
    color: #94a3b8 !important;
    font-size: 0.9rem !important;
    margin: 0.5rem 0 0 0 !important;
}

/* Card styling */
.card {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 1.25rem;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
    margin-bottom: 1rem;
}

.card-header {
    font-size: 1rem;
    font-weight: 600;
    color: var(--text-primary);
    margin-bottom: 1rem;
    padding-bottom: 0.75rem;
    border-bottom: 1px solid var(--border);
}

/* Button styling */
.btn-primary {
    background: var(--primary) !important;
    border: none !important;
    border-radius: 8px !important;
    font-weight: 500 !important;
    transition: all 0.2s !important;
}

.btn-primary:hover {
    background: var(--primary-hover) !important;
    transform: translateY(-1px);
    box-shadow: 0 4px 12px rgba(37, 99, 235, 0.3) !important;
}

/* Placeholder cards */
.placeholder {
    background: linear-gradient(135deg, #f1f5f9 0%, #e2e8f0 100%);
    border: 2px dashed #cbd5e1;
    border-radius: 12px;
    padding: 2rem;
    text-align: center;
    color: #94a3b8;
}

.placeholder-icon {
    font-size: 2.5rem;
    margin-bottom: 0.5rem;
    opacity: 0.5;
}

.placeholder-label {
    font-size: 0.875rem;
    font-weight: 500;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}

/* Status indicators */
.status-badge {
    display: inline-flex;
    align-items: center;
    gap: 0.375rem;
    padding: 0.25rem 0.75rem;
    border-radius: 9999px;
    font-size: 0.75rem;
    font-weight: 500;
}

.status-success {
    background: #d1fae5;
    color: #065f46;
}

.status-warning {
    background: #fef3c7;
    color: #92400e;
}

.status-error {
    background: #fee2e2;
    color: #991b1b;
}

/* Stats cards */
.stat-card {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 1.25rem;
    text-align: center;
}

.stat-value {
    font-size: 2rem;
    font-weight: 700;
    color: var(--primary);
}

.stat-label {
    font-size: 0.875rem;
    color: var(--text-secondary);
    margin-top: 0.25rem;
}

/* Tab styling */
.tab-nav .tab-nav-item {
    font-weight: 500 !important;
    padding: 0.75rem 1.5rem !important;
}

.tab-nav .tab-nav-item.selected {
    background: var(--primary) !important;
    color: white !important;
}
"""

logging.basicConfig(
    filename=config.LOGS_DIR / "main.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def _scan_code_safety(code: str) -> tuple[bool, str]:
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return False, f"Syntax error: {e}"

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name not in config.ALLOWED_IMPORTS:
                    return False, f"Forbidden import: {alias.name}"
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.module not in config.ALLOWED_IMPORTS:
                return False, f"Forbidden import: {node.module}"

    code_check = code
    for pattern in config.FORBIDDEN_PATTERNS:
        if pattern in code_check:
            return False, f"Forbidden pattern detected: {pattern}"

    return True, ""


def _execute_report_in_process(code: str, db_path: str, result_queue: multiprocessing.Queue):
    try:
        import pandas
        import sqlite3
        import json

        restricted_globals = {
            "__builtins__": {},
            "pandas": pandas,
            "sqlite3": sqlite3,
            "json": json,
            "db_path": db_path,
        }

        conn = sqlite3.connect(db_path + "?mode=ro", uri=True)
        restricted_locals = {}

        exec(code, restricted_globals, restricted_locals)

        if "generate_report" in restricted_locals:
            result = restricted_locals["generate_report"](db_path)
            result_queue.put(("success", result))
        else:
            result_queue.put(("error", "Function 'generate_report(db_path)' not found"))
        
        conn.close()

    except Exception as e:
        result_queue.put(("error", f"{type(e).__name__}: {str(e)}\n{traceback.format_exc()}"))


def _execute_report(code: str) -> tuple[bool, any, str]:
    is_safe, error_msg = _scan_code_safety(code)
    if not is_safe:
        return False, None, f"Security scan failed: {error_msg}"

    result_queue = multiprocessing.Queue()
    process = multiprocessing.Process(
        target=_execute_report_in_process,
        args=(code, str(config.DB_PATH), result_queue)
    )
    process.start()
    process.join(timeout=config.REPORT_TIMEOUT_SECONDS)

    if process.is_alive():
        process.terminate()
        process.join()
        return False, None, f"Execution timeout ({config.REPORT_TIMEOUT_SECONDS}s). The report took too long to generate."

    if result_queue.empty():
        return False, None, "No result returned from report function"

    status, result = result_queue.get()
    if status == "error":
        return False, None, result

    return True, result, ""


def _log_execution(report_name: str, code: str, success: bool, error: str = ""):
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "report_name": report_name,
        "success": success,
        "error": error[:500] if error else None,
    }
    with open(config.LOGS_DIR / "execution_audit.jsonl", "a") as f:
        f.write(json.dumps(log_entry) + "\n")


def on_app_load():
    logger.info("Application starting, checking for new files...")
    results = db_manager.ingest_new_files()
    logger.info(f"Ingestion results: {results}")
    return f"Loaded. Processed {len(results['processed'])} files, {len(results['errors'])} errors."


def generate_master_prompt():
    schema = db_manager.get_schema()
    schema_str = json.dumps(schema, indent=2)
    
    prompt = f'''You are an expert Python data analyst. Write a single Python function named generate_report(db_path). You must use sqlite3 to connect to the database and pandas to manipulate the data. Return either a Pandas DataFrame or a Gradio-compatible chart object.

CRITICAL: Output ONLY raw, executable Python code. Do not include markdown formatting, backticks (```), explanations, or example usage. The code must be immediately executable by the Python exec() function.

Database Schema (columns in data_records table):
{schema_str}

Requirements:
1. Use sqlite3.connect(db_path + "?mode=ro", uri=True) for read-only access
2. Query data from the 'data_records' table (data_json column contains JSON)
3. Parse JSON data using: pd.read_json or json.loads
4. Return a pandas DataFrame or a Gradio-compatible chart object
5. Do NOT use: import os, import sys, subprocess, shutil, open(), .to_csv(), .to_excel(), requests, socket, threading
6. Do NOT write any code that modifies the database'''
    
    return prompt


def get_report_choices():
    reports = db_manager.get_reports()
    return [r["name"] for r in reports]


def run_selected_report(report_name: str):
    if not report_name or report_name == "Please select a report.":
        return "Please select a report from the dropdown."
    
    reports = db_manager.get_reports()
    report = next((r for r in reports if r["name"] == report_name), None)
    
    if not report:
        return f"Report '{report_name}' not found."
    
    success, result, error = _execute_report(report["code"])
    _log_execution(report_name, report["code"], success, error)
    
    if not success:
        return f"""❌ Error executing report: {error}

**To fix this:**
1. Copy the error message above
2. Paste it back into your AI (ChatGPT/Gemini)
3. Ask: "Fix the Python code with this error: [paste error]"
4. Paste the corrected code into the 'Import Code' tab"""

    return result


def import_new_code(code: str, name: str):
    if not code or not name:
        return "Please provide both code and a report name.", gr.update(choices=get_report_choices())
    
    is_safe, error_msg = _scan_code_safety(code)
    if not is_safe:
        return f"Security scan failed: {error_msg}", gr.update(choices=get_report_choices())
    
    success = db_manager.save_report(name, code)
    if success:
        return f"Report '{name}' saved successfully!", gr.update(choices=get_report_choices())
    else:
        return f"Report '{name}' already exists. Please use a different name.", gr.update(choices=get_report_choices())


with gr.Blocks(title="BI Dashboard", css=custom_css) as app:
    gr.Markdown("""
    <div class="header">
        <div style="display: flex; align-items: center; gap: 1rem;">
            <img src="file/../static/logo.svg" alt="Europa Eyewear" style="height: 48px; width: auto;">
            <div>
                <h1>BI Dashboard</h1>
                <p>Self-hosted Business Intelligence for everyone</p>
            </div>
        </div>
    </div>
    """)
    
    with gr.Tab("Dashboard"):
        with gr.Row():
            with gr.Column(scale=1):
                gr.Markdown("### 📈 Quick Stats")
                with gr.Row():
                    gr.Markdown("""
                    <div class="stat-card">
                        <div class="stat-value">500</div>
                        <div class="stat-label">Records</div>
                    </div>
                    """)
                with gr.Row():
                    gr.Markdown("""
                    <div class="stat-card">
                        <div class="stat-value">1</div>
                        <div class="stat-label">Data Files</div>
                    </div>
                    """)
                with gr.Row():
                    gr.Markdown("""
                    <div class="stat-card">
                        <div class="stat-value">1</div>
                        <div class="stat-label">Reports</div>
                    </div>
                    """)
                
                gr.Markdown("### ⚡ Actions")
                load_status = gr.Textbox(label="Status", interactive=False)
                refresh_btn = gr.Button("🔄 Refresh Data", variant="secondary", size="sm")
                
                gr.Markdown("### 📋 Reports")
                report_dropdown = gr.Dropdown(
                    choices=get_report_choices(),
                    label="Select Report",
                    interactive=True
                )
                run_btn = gr.Button("▶ Run Report", variant="primary")
                
            with gr.Column(scale=3):
                gr.Markdown("### 📊 Report Output")
                output = gr.Dataframe(label="", wrap=True, visible=True)
                
                gr.Markdown("### 📈 Charts")
                gr.Markdown("""
                <div class="placeholder">
                    <div class="placeholder-icon">📊</div>
                    <div class="placeholder-label">Chart Visualization Coming Soon</div>
                    <p style="margin-top: 0.5rem; font-size: 0.8rem;">Connect to your AI to generate insights</p>
                </div>
                """)
                
                gr.Markdown("### 📤 Export")
                with gr.Row():
                    export_pdf_btn = gr.Button("📄 Export to PDF", variant="secondary")
                    export_csv_btn = gr.Button("📊 Export to CSV", variant="secondary")

        run_btn.click(fn=run_selected_report, inputs=report_dropdown, outputs=output)
        refresh_btn.click(fn=on_app_load, outputs=load_status)

    with gr.Tab("Create Report"):
        gr.Markdown("### 🤖 AI Report Generator")
        gr.Markdown("Generate a prompt for your AI assistant, then import the generated code.")
        
        with gr.Row():
            with gr.Column(scale=2):
                prompt_btn = gr.Button("✨ Generate Master Prompt", variant="primary", size="lg")
                master_prompt = gr.Textbox(
                    label="Master Prompt", 
                    lines=18, 
                    interactive=False
                )
            with gr.Column(scale=1):
                gr.Markdown("""
                <div class="card">
                    <div class="card-header">📋 Instructions</div>
                    <ol style="padding-left: 1.25rem; color: var(--text-secondary); font-size: 0.9rem; line-height: 1.8;">
                        <li>Click <strong>Generate Master Prompt</strong></li>
                        <li>Copy the prompt</li>
                        <li>Paste into ChatGPT/Gemini</li>
                        <li>Copy the code response</li>
                        <li>Go to <strong>Import Code</strong> tab</li>
                        <li>Paste and save the code</li>
                    </ol>
                </div>
                """)
        
        prompt_btn.click(fn=generate_master_prompt, outputs=master_prompt)

    with gr.Tab("Import Code"):
        gr.Markdown("### 💾 Import AI-Generated Code")
        
        with gr.Row():
            report_name = gr.Textbox(
                label="Report Name", 
                placeholder="e.g., Monthly Sales Summary",
                scale=1
            )
            import_btn = gr.Button("💾 Save Report", variant="primary", scale=1)
        
        code_input = gr.Code(
            label="Python Code", 
            language="python", 
            lines=15
        )
        
        import_result = gr.Textbox(label="Result", interactive=False, visible=True)
        
        with gr.Row():
            gr.Markdown("""
            <div class="placeholder" style="padding: 1rem;">
                <div class="placeholder-icon">🔒</div>
                <div class="placeholder-label" style="font-size: 0.75rem;">Security: Code is scanned before execution</div>
            </div>
            """)
        
        import_btn.click(fn=import_new_code, inputs=[code_input, report_name], outputs=[import_result, report_dropdown])

    with gr.Tab("Settings"):
        gr.Markdown("### ⚙️ Dashboard Settings")
        
        with gr.Row():
            with gr.Column():
                gr.Markdown("""
                <div class="card">
                    <div class="card-header">📁 Data Directories</div>
                    <p style="color: var(--text-secondary); font-size: 0.9rem;">
                        <strong>data-in/</strong> - Drop CSV/XLSX files here<br>
                        <strong>data-archive/</strong> - Processed files
                    </p>
                </div>
                """)
            with gr.Column():
                gr.Markdown("""
                <div class="card">
                    <div class="card-header">🔌 AI Connection</div>
                    <p style="color: var(--text-secondary); font-size: 0.9rem;">
                        Uses external AI (ChatGPT/Gemini)<br>
                        No API keys required
                    </p>
                </div>
                """)
        
        gr.Markdown("### 🔮 Coming Soon")
        gr.Markdown("""
        <div class="placeholder" style="padding: 1.5rem;">
            <div class="placeholder-icon">✨</div>
            <div class="placeholder-label">Scheduled Reports</div>
            <p style="margin-top: 0.5rem; font-size: 0.8rem;">Automatically run reports on a schedule</p>
        </div>
        """)

    app.load(fn=on_app_load, outputs=load_status)

if __name__ == "__main__":
    print("Starting BI Dashboard...")
    print(f"Data directory: {config.DATA_IN_DIR}")
    print(f"Database: {config.DB_PATH}")
    app.launch(server_name="127.0.0.1", server_port=7860, share=False)
