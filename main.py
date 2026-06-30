#!/usr/bin/env python3
"""
Multi-Source Candidate Data Transformer — CLI Entry Point

Usage:
    python main.py --inputs sample_data/ --config config/output_config.json --output output.json

    python main.py \\
        --inputs sample_data/ \\
        --config config/output_config.json \\
        --pipeline-config config/default_config.json \\
        --output output.json \\
        --report report.json \\
        --log-level INFO
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Ensure project root is on sys.path
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.pipeline import Pipeline


def setup_logging(level: str = "INFO") -> None:
    """Configure logging for the pipeline."""
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Multi-Source Candidate Data Transformer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py --inputs sample_data/ --output output.json
  python main.py --inputs sample_data/ --config config/output_config.json --output output.json --report report.json
  python main.py --inputs file1.json file2.csv --output output.json --log-level DEBUG
        """,
    )
    parser.add_argument(
        "--inputs",
        nargs="+",
        required=True,
        help="Input file(s) or directory(ies) containing candidate data",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Path to output schema config JSON (optional)",
    )
    parser.add_argument(
        "--pipeline-config",
        default=None,
        help="Path to pipeline config JSON (default: config/default_config.json)",
    )
    parser.add_argument(
        "--output",
        default="output.json",
        help="Output JSON file path (default: output.json)",
    )
    parser.add_argument(
        "--report",
        default=None,
        help="Explainability report JSON file path (optional)",
    )
    parser.add_argument(
        "--report-text",
        default=None,
        help="Human-readable report text file path (optional)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: INFO)",
    )
    return parser.parse_args()


def main() -> int:
    """Main entry point."""
    args = parse_args()

    # Setup logging
    setup_logging(args.log_level)
    logger = logging.getLogger("main")

    logger.info("Multi-Source Candidate Data Transformer")
    logger.info("=" * 50)

    # Validate inputs
    for input_path in args.inputs:
        # Check if the input is a web URL
        is_url = (
            input_path.lower().startswith(("http://", "https://"))
            or "github.com/" in input_path.lower()
            or "linkedin.com/" in input_path.lower()
        )
        if not is_url and not Path(input_path).exists():
            logger.error("Input path not found: %s", input_path)
            return 1

    # Load pipeline config
    pipeline_config = None
    if args.pipeline_config:
        config_path = args.pipeline_config
    else:
        # Try default location
        config_path = os.path.join(project_root, "config", "default_config.json")

    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                pipeline_config = json.load(f)
            logger.info("Loaded pipeline config: %s", config_path)
        except Exception as e:
            logger.warning("Could not load pipeline config '%s': %s", config_path, e)

    # Load output config
    output_config = None
    if args.config:
        if not Path(args.config).exists():
            logger.error("Output config not found: %s", args.config)
            return 1
        try:
            with open(args.config, "r", encoding="utf-8") as f:
                output_config = json.load(f)
            logger.info("Loaded output config: %s", args.config)
        except Exception as e:
            logger.error("Invalid output config '%s': %s", args.config, e)
            return 1

    # Run pipeline
    try:
        pipeline = Pipeline(config=pipeline_config)
        result = pipeline.run(
            input_paths=args.inputs,
            output_config=output_config,
        )
    except Exception as e:
        logger.error("Pipeline failed: %s", e, exc_info=True)
        return 1

    # Write each candidate to a separate profile file
    try:
        output_data = result.get("output", result.get("profiles", []))
        
        output_path = Path(args.output)
        if output_path.suffix.lower() == '.json':
            output_dir = output_path.parent / "output"
        else:
            output_dir = output_path
            
        os.makedirs(output_dir, exist_ok=True)
        
        for p in output_data:
            if isinstance(p, dict):
                cid = p.get("candidate_id") or p.get("id")
                name = p.get("full_name") or p.get("name") or cid
                
                clean_name = "".join(c if c.isalnum() else "_" for c in str(name)).lower().strip("_")
                if not clean_name:
                    clean_name = str(cid) if cid else "unknown"
                
                file_name = f"{clean_name}.json"
                file_path = os.path.join(output_dir, file_name)
                
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(p, f, indent=2, default=str)
                logger.info("Candidate profile saved separately to: %s", file_path)
    except Exception as e:
        logger.error("Failed to write output: %s", e)
        return 1

    # Write report (JSON)
    if args.report:
        try:
            with open(args.report, "w", encoding="utf-8") as f:
                json.dump(result.get("report", {}), f, indent=2, default=str)
            logger.info("Report written to: %s", args.report)
        except Exception as e:
            logger.error("Failed to write report: %s", e)

    # Write report (text)
    if args.report_text:
        try:
            from src.output.report import ExplainabilityReport
            from src.models.candidate import CanonicalProfile
            from src.engine.entity_resolution import CandidateCluster

            # Reconstruct profiles for text report
            profiles_data = result.get("profiles", [])
            profiles = [CanonicalProfile.from_dict(p) for p in profiles_data if p]

            report_data = result.get("report", {})

            with open(args.report_text, "w", encoding="utf-8") as f:
                # Write a simplified text report from the JSON report
                f.write("CANDIDATE DATA TRANSFORMER — EXPLAINABILITY REPORT\n")
                f.write("=" * 70 + "\n\n")

                summary = report_data.get("summary", {})
                f.write(f"Total Profiles: {summary.get('total_profiles', 0)}\n")
                f.write(f"Clusters with Merges: {summary.get('clusters_with_merges', 0)}\n\n")

                for candidate in report_data.get("candidates", []):
                    f.write("-" * 50 + "\n")
                    f.write(f"Candidate: {candidate.get('full_name', 'Unknown')}\n")
                    f.write(f"Confidence: {candidate.get('overall_confidence', 0):.4f}\n")

                    merge = candidate.get("merge_explanation", {})
                    if merge.get("merged"):
                        f.write("Merge Reason:\n")
                        for detail in merge.get("match_details", []):
                            for exp in detail.get("explanation", []):
                                f.write(f"  • {exp}\n")
                    f.write("\n")

                f.write("=" * 70 + "\n")
                f.write("END OF REPORT\n")

            logger.info("Text report written to: %s", args.report_text)
        except Exception as e:
            logger.error("Failed to write text report: %s", e)

    # Print summary
    profiles = result.get("profiles", [])
    logger.info("=" * 50)
    logger.info("SUMMARY")
    logger.info("  Profiles generated: %d", len(profiles))
    for p in profiles:
        name = p.get("full_name", "Unknown")
        conf = p.get("overall_confidence", 0)
        emails = len(p.get("emails", []))
        skills = len(p.get("skills", []))
        logger.info(
            "  • %s (confidence=%.2f, emails=%d, skills=%d)",
            name, conf, emails, skills,
        )
    logger.info("=" * 50)

    return 0


if __name__ == "__main__":
    sys.exit(main())
