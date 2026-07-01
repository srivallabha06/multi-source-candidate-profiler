"""
Unit/integration tests for the main CLI entrypoint (main.py).
"""

import json
import os
import sys
import unittest.mock
from pathlib import Path
import pytest

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from main import main


def test_main_cli_saves_separate_reports(tmp_path):
    """
    Running main.py CLI should output separate profiles,
    JSON reports, and optional TXT reports for each candidate.
    """
    output_json = tmp_path / "output.json"
    report_json = tmp_path / "report.json"
    report_txt = tmp_path / "report.txt"
    sample_data_dir = os.path.join(project_root, "sample_data")
    pipeline_config = os.path.join(project_root, "config", "default_config.json")
    output_config = os.path.join(project_root, "config", "output_config.json")

    # Mock command line arguments
    test_args = [
        "main.py",
        "--inputs",
        sample_data_dir,
        "--config",
        output_config,
        "--pipeline-config",
        pipeline_config,
        "--output",
        str(output_json),
        "--report",
        str(report_json),
        "--report-text",
        str(report_txt),
    ]

    with unittest.mock.patch("sys.argv", test_args):
        exit_code = main()

    assert exit_code == 0

    # Main reports should exist
    assert report_json.exists()
    assert report_txt.exists()

    # The separate profiles should be saved in the 'output' subdirectory
    # relative to the output JSON file parent directory
    output_dir = tmp_path / "output"
    assert output_dir.exists()

    # Find generated files
    files = list(output_dir.iterdir())
    filenames = [f.name for f in files]
    print("Generated filenames in output_dir:", filenames)

    # There should be profile json, report json, and report txt for candidates
    # e.g., rahul_sharma.json, rahul_sharma_report.json, rahul_sharma_report.txt
    assert any(name.endswith("_report.json") for name in filenames)
    assert any(name.endswith("_report.txt") for name in filenames)
    assert any(name.endswith(".json") and not name.endswith("_report.json") for name in filenames)

    # Let's inspect one specific candidate's report JSON
    # Find any report file that ends with _report.json
    report_files = [name for name in filenames if name.endswith("_report.json")]
    assert len(report_files) > 0
    rahul_report_file = output_dir / report_files[0]
    
    assert rahul_report_file.exists()
    with open(rahul_report_file, "r", encoding="utf-8") as f:
        rahul_report = json.load(f)
    assert rahul_report.get("candidate_id") is not None

    # Let's inspect one specific candidate's report TXT
    txt_report_files = [name for name in filenames if name.endswith("_report.txt")]
    assert len(txt_report_files) > 0
    rahul_report_txt = output_dir / txt_report_files[0]
    
    assert rahul_report_txt.exists()
    with open(rahul_report_txt, "r", encoding="utf-8") as f:
        text_content = f.read()
    assert "CANDIDATE EXPLAINABILITY REPORT" in text_content
