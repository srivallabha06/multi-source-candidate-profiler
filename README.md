# Multi-Source Candidate Data Transformer

A production-grade Python system that ingests candidate records from heterogeneous sources, normalizes data, resolves identity, builds canonical profiles with provenance tracking and confidence scoring, and produces configurable output schemas.

## Features

- **Multi-source ingestion** — Resume JSON, LinkedIn JSON, GitHub API, ATS CSV, PDF, Portfolio websites, HR systems
- **Pluggable adapter architecture** — Add new sources without modifying the core engine
- **Data normalization** — Names (title-case), phones (E.164), countries (ISO-3166), skills (taxonomy), dates (YYYY-MM), URLs
- **Entity resolution** — Index-based blocking + weighted signal scoring. Never merges on name alone
- **Conflict resolution** — Configurable trust hierarchy. Never silently overwrites
- **Provenance tracking** — Every field value is traceable to its source
- **Confidence scoring** — Deterministic per-field and overall scores
- **Configurable output** — Runtime JSON config for field renaming, selection, nesting, arrays
- **Explainability reports** — Why records were merged, confidence breakdowns, conflict resolution details
- **Fault tolerant** — Malformed inputs, missing fields, API failures never crash the pipeline

## Quick Start

### Install dependencies

```bash
pip install -r requirements.txt
```

### Run the pipeline

```bash
python main.py \
  --inputs sample_data/ \
  --config config/output_config.json \
  --output output.json \
  --report report.json \
  --log-level INFO
```

### Run tests

```bash
python -m pytest tests/ -v
```

## Project Structure

```
├── main.py                          # CLI entry point
├── requirements.txt                 # Dependencies
├── config/
│   ├── default_config.json          # Pipeline configuration
│   ├── output_config.json           # Output schema configuration
│   └── skill_taxonomy.json          # Skill canonicalization taxonomy
├── src/
│   ├── models/                      # Data models (CanonicalProfile, Provenance)
│   ├── adapters/                    # Source adapters (7 types)
│   ├── normalizers/                 # Data normalizers (6 types)
│   ├── engine/                      # Core engine (entity resolution, merger, confidence)
│   ├── output/                      # Output configurator + explainability reports
│   └── pipeline.py                  # Pipeline orchestrator
├── tests/                           # Unit + integration tests (105 tests)
└── sample_data/                     # Sample data for testing
```

## CLI Options

| Option | Description | Default |
|---|---|---|
| `--inputs` | Input files or directories (required) | — |
| `--config` | Output schema config JSON | None (full profile) |
| `--pipeline-config` | Pipeline config JSON | `config/default_config.json` |
| `--output` | Output JSON file path | `output.json` |
| `--report` | Explainability report JSON path | None |
| `--report-text` | Human-readable report path | None |
| `--log-level` | Logging level | `INFO` |

## Configuration

### Pipeline Config (`config/default_config.json`)

Controls merge threshold, trust hierarchy, confidence weights, phone region defaults, and GitHub API settings.

### Output Config (`config/output_config.json`)

Runtime-configurable output schema:

```json
{
  "fields": [
    {"path": "name", "from": "full_name"},
    {"path": "email", "from": "emails[0]"},
    {"path": "skills", "from": "skills[*].name"}
  ],
  "include_confidence": true,
  "on_missing": "null"
}
```

### Skill Taxonomy (`config/skill_taxonomy.json`)

Configurable skill name canonicalization with ~150 canonical skills and ~440 aliases.

## Entity Resolution

Uses index-based blocking on strong signals (email, phone, LinkedIn URL, GitHub URL) to avoid O(n²) comparisons, then scores candidate pairs with weighted signals:

| Signal | Weight | Type |
|---|---|---|
| Email match | 100 | Strong |
| Phone match | 80 | Strong |
| LinkedIn URL match | 100 | Strong |
| GitHub URL match | 100 | Strong |
| Name similarity | 30 | Weak |
| Company overlap | 20 | Weak |
| Education overlap | 15 | Weak |
| Location match | 10 | Weak |
| Skill overlap | 10 | Weak |

**Key rule**: Never merge candidates using names alone. At least one strong signal is required.

## Adding New Source Adapters

Create a new adapter by inheriting from `BaseAdapter`:

```python
from src.adapters.base import BaseAdapter

class MyCustomAdapter(BaseAdapter):
    @property
    def source_type(self) -> str:
        return "my_custom_source"

    def can_handle(self, source_path: str) -> bool:
        return source_path.endswith(".myformat")

    def ingest(self, source_path: str):
        # Parse and return List[RawCandidateRecord]
        ...
```

Then register it in the pipeline's adapter registry.

## License

MIT
