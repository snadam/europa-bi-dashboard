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
import pandas as pd
import sqlite3

import config
import db_manager

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
        allowed_modules = {
            "pandas": pandas,
            "sqlite3": sqlite3,
            "gradio": None,
        }
        allowed_modules["pandas"] = importlib.import_module("pandas")

        restricted_globals = {
            "__builtins__": {},
            "pandas": allowed_modules["pandas"],
            "sqlite3": sqlite3,
            "db_path": db_path,
        }

        conn = sqlite3.connect(db_path + "?mode=ro", uri=True)
        restricted_globals["sqlite3"] = sqlite3
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
    if not report_name:
        return "Please select a report."
    
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
        return "Please provide both code and a report name."
    
    is_safe, error_msg = _scan_code_safety(code)
    if not is_safe:
        return f"Security scan failed: {error_msg}"
    
    success = db_manager.save_report(name, code)
    if success:
        return f"Report '{name}' saved successfully!"
    else:
        return f"Report '{name}' already exists. Please use a different name."


with gr.Blocks(title="BI Dashboard", theme=gr.themes.Soft()) as app:
    gr.Markdown("# 📊 Local BI Dashboard")
    gr.Markdown("Drop Excel or CSV files into `data-in/` to get started.")
    
    with gr.Tab("Dashboard"):
        with gr.Row():
            load_status = gr.Textbox(label="Status", interactive=False)
        
        with gr.Row():
            report_dropdown = gr.Dropdown(
                choices=get_report_choices(),
                label="Select Report",
                interactive=True
            )
            run_btn = gr.Button("Run Report", variant="primary")
        
        with gr.Row():
            with gr.Column():
                gr.Markdown("### Report Output")
                output = gr.Component()  # Placeholder for dynamic component
        
        with gr.Row():
            export_pdf_btn = gr.Button("Export to PDF", variant="secondary")
        
        run_btn.click(fn=run_selected_report, inputs=report_dropdown, outputs=output)
        
        with gr.Row():
            gr.Markdown("*Refresh the page to update report list*")

    with gr.Tab("Create Report"):
        gr.Markdown("### Generate a Master Prompt")
        gr.Markdown("Click below to create a prompt for your AI. Copy it, paste into ChatGPT/Gemini, then import the result.")
        
        prompt_btn = gr.Button("Generate Master Prompt", variant="primary")
        master_prompt = gr.Textbox(label="Master Prompt", lines=15, interactive=False)
        
        prompt_btn.click(fn=generate_master_prompt, outputs=master_prompt)

    with gr.Tab("Import Code"):
        gr.Markdown("### Import AI-Generated Code")
        gr.Markdown("Paste the Python code from your AI here.")
        
        with gr.Row():
            report_name = gr.Textbox(label="Report Name", placeholder="e.g., Monthly Sales Summary")
            import_btn = gr.Button("Save Report", variant="primary")
        
        code_input = gr.Code(label="Python Code", language="python", lines=20)
        import_result = gr.Textbox(label="Result", interactive=False)
        
        import_btn.click(fn=import_new_code, inputs=[code_input, report_name], outputs=import_result)

    app.load(fn=on_app_load, outputs=load_status)

if __name__ == "__main__":
    print("Starting BI Dashboard...")
    print(f"Data directory: {config.DATA_IN_DIR}")
    print(f"Database: {config.DB_PATH}")
    app.launch(server_name="127.0.0.1", server_port=7860, share=False)
