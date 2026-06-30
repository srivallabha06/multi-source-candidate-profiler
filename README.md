# Multi-Source Candidate Data Transformer & Deduplicator

A production-grade candidate profile aggregation system that ingests candidate resumes, scrapers, and datasets from heterogeneous sources, resolves candidate identity, deduplicates records, and exports clean canonical profiles according to custom schemas.

---

## 1. Quick Start & Execution

### Installation
Clone the repository and install the dependencies listed in `requirements.txt`:

```bash
# Install dependencies
pip install -r requirements.txt
```

### Running the Web dashboard UI
The system includes an interactive web dashboard to upload profiles, edit output configuration schemas, trigger Apify LinkedIn scrapers, and preview merged output files side-by-side.

```bash
# Start Flask server
python app.py
```
1. Open your browser and navigate to **`http://localhost:5000`**.
2. Upload test candidate records (PDFs, JSON, CSV).
3. Optionally enter a LinkedIn URL or edit the output configuration schema in the sidebar.
4. Click **Run Pipeline** to view results.

### Running the Command Line Interface (CLI)
You can run the pipeline directly from the command line by supplying input files or folders:

```bash
# Process single files or directories
python main.py \
  --inputs sample_data/ \
  --config config/output_config.json \
  --output output.json \
  --report report.json \
  --log-level INFO
```

### Running Unit Tests
Validate the system logic using the pytest suite (111 tests covering all normalizers, adapters, and engines):

```bash
python -m pytest tests/ -v
```

---

## 2. Ingestion & Adapter Registry

The system employs a pluggable adapter architecture to convert various candidate formats into unified `RawCandidateRecord` objects:

| Source Type | Adapter | Target Inputs / Formats |
|---|---|---|
| `resume_json` | `ResumeJsonAdapter` | JSON files containing resume data |
| `linkedin_json` | `LinkedInJsonAdapter` | Scraped LinkedIn profile JSON exports & direct profile URLs (using Apify Scraper APIs) |
| `github` | `GitHubAdapter` | Github profile details & repo language metrics (GitHub REST APIs) |
| `ats_csv` | `ATSCsvAdapter` | CSV files containing tabular candidates data (autodetects headers) |
| `ats_json` | `ATSJsonAdapter` | JSON database exports containing single/lists of candidates |
| `pdf` | `PDFAdapter` | Resume PDFs (text-extraction & regex timelines grouping logic) |
| `portfolio_web` | `PortfolioWebAdapter` | Portfolio websites URL scrapers |

---

## 3. Input & Output Mappings (Data Examples)

The pipeline transforms raw heterogeneous inputs into standardized, clean structures.

### Example: ATS JSON Input (`sample_data/ats_test.json`)
```json
{
  "candidateId": "ATS-1001",
  "firstName": "Rama",
  "lastName": "Dahagam",
  "email": "rama.d@example.com",
  "phone": "+91 9876543210",
  "location": { "city": "Hyderabad", "state": "Telangana", "country": "India" },
  "headline": "Software Engineer",
  "skills": ["Java", "Spring Boot", "AWS"],
  "experience": [
    {
      "company": "ABC Technologies",
      "title": "Software Engineer",
      "startDate": "2022-06",
      "endDate": null,
      "current": true
    }
  ],
  "education": [
    {
      "institution": "JNTU Hyderabad",
      "degree": "B.Tech",
      "field": "Computer Science",
      "graduationYear": 2022
    }
  ],
  "socialProfiles": {
    "linkedin": "https://linkedin.com/in/rama-dahagam"
  }
}
```

### Example: Standard Output Schema (`output/rama_dahagam.json`)
Each candidate is outputted in their own dedicated JSON file named after them inside the `output/` folder:
```json
{
  "candidate_id": "30216b22-125a-5848-b46a-726b1ac3b0d7",
  "full_name": "Rama Dahagam",
  "emails": [
    "rama.d@example.com"
  ],
  "phones": [
    "+919876543210"
  ],
  "location": {
    "city": "Hyderabad",
    "region": null,
    "country": "IN"
  },
  "links": {
    "linkedin": "https://linkedin.com/in/rama-dahagam",
    "github": null,
    "portfolio": null,
    "other": []
  },
  "headline": "Software Engineer",
  "years_experience": null,
  "skills": [
    {
      "name": "Java",
      "confidence": 0.5,
      "sources": ["ats_json"]
    },
    {
      "name": "Spring",
      "confidence": 0.5,
      "sources": ["ats_json"]
    }
  ],
  "experience": [
    {
      "company": "ABC Technologies",
      "title": "Software Engineer",
      "start": "2022-06",
      "end": "present",
      "summary": null
    }
  ],
  "education": [
    {
      "institution": "JNTU Hyderabad",
      "degree": "B.Tech",
      "field": "Computer Science",
      "end_year": "2022"
    }
  ],
  "overall_confidence": 0.77
}
```

---

## 4. Entity Resolution & Safeguards

The deduplication engine matches candidates by generating blocking index collisions on unique attributes (Email, Phone, LinkedIn, GitHub URLs) and calculating weighted scores:

*   **Email Match**: +100 (Strong Signal)
*   **Phone Match**: +80 (Strong Signal)
*   **LinkedIn/GitHub Match**: +100 (Strong Signal)
*   **Name Similarity**: +30 (Weak Signal)
*   **Company Overlap**: +20 (Weak Signal)
*   **Education Overlap**: +15 (Weak Signal)

> [!IMPORTANT]
> **Deduplication Safeguard**: Candidates are **never** merged on names/weak signals alone. At least one strong signal (colliding email, phone, or social URL) must match to prevent false-positive merges.

---

## 5. Adding New Adapters

To extend the system to ingest other data sources:
1. Inherit from `BaseAdapter` in `src/adapters/base.py`.
2. Implement `can_handle(source_path)` and `ingest(source_path)`.
3. Register the new class instantiation inside `src/pipeline.py`.
