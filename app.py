import os
import io
import sys
import logging
import shutil
import tempfile
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename

# Ensure project root is in sys.path
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Load env variables from .env
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from src.pipeline import Pipeline
from src.models.candidate import CanonicalProfile
from src.engine.entity_resolution import CandidateCluster

app = Flask(__name__, static_folder='static', static_url_path='')

# Configure upload directory
UPLOAD_FOLDER = os.path.join(project_root, 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Configure logging capture handler
class LogCaptureHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.log_buffer = io.StringIO()
        self.setFormatter(logging.Formatter('%(asctime)s [%(levelname)-5s] %(name)s: %(message)s', '%H:%M:%S'))

    def emit(self, record):
        self.log_buffer.write(self.format(record) + '\n')

    def get_logs(self) -> str:
        return self.log_buffer.getvalue()

@app.route('/')
def index():
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/api/config', methods=['GET'])
def get_config():
    """Read output_config.json from disk."""
    import json
    config_path = os.path.join(project_root, 'config', 'output_config.json')
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return jsonify(json.load(f))
        except Exception:
            pass
    # Fallback default
    return jsonify({
        "fields": [
            {"path": "candidate_id", "from": "candidate_id"},
            {"path": "full_name", "from": "full_name"},
            {"path": "emails", "from": "emails[*]"},
            {"path": "phones", "from": "phones[*]"},
            {"path": "location.city", "from": "location.city"},
            {"path": "location.region", "from": "location.region"},
            {"path": "location.country", "from": "location.country"},
            {"path": "links.linkedin", "from": "links.linkedin"},
            {"path": "links.github", "from": "links.github"},
            {"path": "links.portfolio", "from": "links.portfolio"},
            {"path": "links.other", "from": "links.other[*]"},
            {"path": "headline", "from": "headline"},
            {"path": "years_experience", "from": "years_experience"},
            {"path": "skills", "from": "skills[*]"},
            {"path": "experience", "from": "experience[*]"},
            {"path": "education", "from": "education[*]"}
        ],
        "include_confidence": True,
        "include_provenance": True,
        "on_missing": "null"
    })

@app.route('/api/samples', methods=['GET'])
def get_samples():
    """List sample data files in sample_data/ directory."""
    samples_dir = os.path.join(project_root, 'sample_data')
    if not os.path.exists(samples_dir):
        return jsonify([])
    
    files = []
    for root, _, filenames in os.walk(samples_dir):
        for name in filenames:
            if not name.startswith('.'):
                full_path = os.path.join(root, name)
                rel_path = os.path.relpath(full_path, samples_dir)
                size = os.path.getsize(full_path)
                files.append({
                    'name': rel_path,
                    'size': size,
                    'type': Path(name).suffix.lower().replace('.', '')
                })
    return jsonify(sorted(files, key=lambda x: x['name']))

@app.route('/api/process', methods=['POST'])
def process_candidates():
    """
    Ingest uploaded files and/or sample files and run the processing pipeline.
    """
    temp_dir = tempfile.mkdtemp(dir=app.config['UPLOAD_FOLDER'])
    input_paths = []
    
    # Capture pipeline logs
    capture_handler = LogCaptureHandler()
    root_logger = logging.getLogger()
    # Ensure root logger can receive debug/info
    old_level = root_logger.level
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(capture_handler)
    
    try:
        # 1. Process uploaded files
        if 'files' in request.files:
            uploaded_files = request.files.getlist('files')
            for f in uploaded_files:
                if f.filename:
                    filename = secure_filename(f.filename)
                    dest_path = os.path.join(temp_dir, filename)
                    f.save(dest_path)
                    input_paths.append(dest_path)
        
        # 2. Process sample files if requested
        samples_param = request.form.get('samples')
        if samples_param:
            import json
            try:
                selected_samples = json.loads(samples_param)
                for sample_rel in selected_samples:
                    sample_path = os.path.join(project_root, 'sample_data', sample_rel)
                    if os.path.exists(sample_path):
                        input_paths.append(sample_path)
            except Exception as e:
                logging.error("Failed to parse samples parameter: %s", e)

        # 3. Process URL links if requested
        urls_param = request.form.get('urls')
        if urls_param:
            import json
            try:
                selected_urls = json.loads(urls_param)
                for url in selected_urls:
                    if url.strip():
                        input_paths.append(url.strip())
            except Exception as e:
                logging.error("Failed to parse urls parameter: %s", e)

        # If no inputs provided
        if not input_paths:
            return jsonify({
                'success': False,
                'error': 'No input files were provided.'
            }), 400

        # Load configs
        pipeline_config = None
        default_config_path = os.path.join(project_root, 'config', 'default_config.json')
        if os.path.exists(default_config_path):
            try:
                with open(default_config_path, 'r', encoding='utf-8') as f:
                    pipeline_config = json.load(f)
            except Exception as e:
                logging.warning("Could not load default pipeline config: %s", e)

        # Load output config from request if provided
        output_config = None
        output_config_param = request.form.get('output_config')
        if output_config_param:
            try:
                import json
                output_config = json.loads(output_config_param)
            except Exception as e:
                logging.error("Failed to parse custom output_config parameter: %s", e)

        # Run pipeline
        pipeline = Pipeline(config=pipeline_config)
        result = pipeline.run(input_paths=input_paths, output_config=output_config)
        
        # Save profiles and reports to separate JSON files on the server disk
        try:
            import json
            output_dir = os.path.join(project_root, 'output')
            os.makedirs(output_dir, exist_ok=True)
            
            # Fetch report candidates
            report_data = result.get('report', {})
            candidate_reports_list = report_data.get('candidates', [])
            
            for i, p in enumerate(result.get('output', result.get('profiles', []))):
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
                    logging.info("Candidate profile saved separately from Web UI: %s", file_path)
                    
                    # Save candidate report separately too
                    candidate_report = None
                    if cid:
                        for rep in candidate_reports_list:
                            if rep.get("candidate_id") == cid:
                                candidate_report = rep
                                break
                    if not candidate_report and i < len(candidate_reports_list):
                        candidate_report = candidate_reports_list[i]
                    
                    if candidate_report:
                        report_file_name = f"{clean_name}_report.json"
                        report_file_path = os.path.join(output_dir, report_file_name)
                        with open(report_file_path, "w", encoding="utf-8") as f:
                            json.dump(candidate_report, f, indent=2, default=str)
                        logging.info("Candidate report saved separately from Web UI: %s", report_file_path)
        except Exception as e:
            logging.error("Failed to save profiles or reports to disk in Web UI run: %s", e)
        
        # Remove capture handler
        root_logger.removeHandler(capture_handler)
        root_logger.setLevel(old_level)
        logs = capture_handler.get_logs()

        # Build response
        return jsonify({
            'success': True,
            'profiles': result.get('profiles', []),
            'report': result.get('report', {}),
            'output': result.get('output', []),
            'logs': logs
        })

    except Exception as e:
        # Fallback to remove handler on error
        if capture_handler in root_logger.handlers:
            root_logger.removeHandler(capture_handler)
        root_logger.setLevel(old_level)
        
        logging.error("Pipeline run failed: %s", e, exc_info=True)
        logs = capture_handler.get_logs()
        return jsonify({
            'success': False,
            'error': str(e),
            'logs': logs
        }), 500

    finally:
        # Clean up temporary uploads
        try:
            shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception:
            pass

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
