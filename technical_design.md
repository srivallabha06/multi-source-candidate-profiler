# Technical Design: Multi-Source Candidate Profiler & Deduplicator

This document frames the candidate identity resolution and profile synthesis problem and outlines the architectural design plan.

---

## 1. Pipeline & Step Breakdown

The pipeline runs sequentially to safely ingest multiple candidate resumes/profiles and resolve them into a single golden record:

$$\text{Ingest/Detect} \longrightarrow \text{Normalize} \longrightarrow \text{Block \& Pair} \longrightarrow \text{Resolve} \longrightarrow \text{Merge/De-conflict} \longrightarrow \text{Score Confidence} \longrightarrow \text{Project \& Validate}$$

1.  **Ingest / Detect**: Scans the input list. Type-detection matches files (JSON, CSV, PDF) and URLs (GitHub, LinkedIn) to their corresponding ingestion adapters.
2.  **Normalize**: Standardizes messy raw text fields (e.g., date text, raw phone numbers, country strings) using regex normalizers and matches skills against a canonical taxonomy database.
3.  **Block & Pair**: Creates a blocking index using unique strong identifiers (email, phone, LinkedIn, GitHub URLs) to avoid O(N²) candidate pairs comparisons.
4.  **Resolve**: Evaluates matching candidates by calculating similarity scores (name token similarity, location overlap, company overlap). If a pair scores above a threshold (80) and shares a strong identifier, a match is confirmed.
5.  **Merge & De-conflict**: Combines matched records. Resolves field conflicts using a source trust hierarchy and tracks value provenance.
6.  **Score Confidence**: Computes an overall profile quality score (0.0 to 1.0) based on source authority and field completeness.
7.  **Project & Validate**: Projects the merged profile against custom runtime configurations (field renames, attribute exclusions) and validates the JSON output format.

---

## 2. Canonical Output Schema & Normalizations

### Canonical Schema Structure
*   `candidate_id` (UUID string)
*   `full_name` (Title Case string, or `null`)
*   `emails` / `phones` (Unique normalized string arrays)
*   `location` (Object containing `city`, `region`, and ISO country code)
*   `links` (Object with `linkedin`, `github`, `portfolio` URL handles)
*   `skills` (Array of objects tracking: `name`, `confidence`, and `sources`)
*   `experience` / `education` (Arrays of timeline records with dates, title, and organization)
*   `overall_confidence` (Float score between `0.0` and `1.0`)
*   `merged_from` (Array of source file/URL strings)

### Field Normalization Standards
*   **Dates**: Normalized to standard `YYYY-MM` format (or `"present"`) using regex patterns matching various textual strings (e.g. `"March 2022"`, `"03/22"`).
*   **Phone Numbers**: Stripped of symbols, parentheses, and spaces. Default country-code formatting prefix applied.
*   **Country**: Parsed against ISO-3166-1 lists to yield standard Alpha-2 codes (e.g. `"US"`, `"IN"`).
*   **Skills**: Cleaned of casing differences and matching variations (e.g., `"JDK"`, `"Core Java"` match to canonical `"Java"`).

---

## 3. Merge, Conflict Resolution & Confidence Policies

### Match Decision & Deduplication
Records are merged if their weighted similarities aggregate above a threshold of `80`. The configuration requires **at least one strong signal collision** (matching email, phone, github, or linkedin) to merge, preventing false positive merges on common names alone.

### Scalar Conflict-Resolution (Trust Hierarchy)
When multiple records provide different scalar values, the value from the highest trusted source type is selected:
$$\text{resume\_json} > \text{linkedin\_json} > \text{github} > \text{ats\_json} > \text{ats\_csv} > \text{hr\_system} > \text{portfolio\_web} > \text{pdf}$$

### Profile Confidence Scoring
Computed as:
$$\text{Confidence} = \sum (\text{Field Importance Weight} \times \text{Field Source Reliability}) \times \text{Completeness Penalty}$$

---

## 4. Runtime Custom-Output Config (Projection & Validation)

*   **Projection**: Supports dynamic schemas specified via a JSON configuration (e.g., `output_config.json`). It uses JSON-Path expressions to rename, nest, or exclude fields on the fly (e.g., mapping `full_name` $\rightarrow$ `candidate_name`, extracting only top skills, or dropping contact arrays).
*   **Validation**: The projected dictionary is validated against the schema requirements. Any missing required fields default to `null` or skip based on configuration policies.

---

## 5. Edge Cases & Scope Limits

### Handled Edge Cases
1.  **Reversed Names**: `"Nikhil Kalluri"` vs `"Kalluri Nikhil"` tokenizes, matches and yields a `1.0` similarity.
2.  **Date Standardizations**: Correctly normalizes textual inputs like `"present"` and `"current"` to allow accurate years of experience calculations.
3.  **Conflict Logging**: Every resolution choice logs provenance detailing the winner and the superseded values.

### Out of Scope (Deliberate Omissions)
1.  **Real-Time Browser Login Scraping**: Scraping behind private LinkedIn auth walls is omitted to avoid account bans; the system relies on external API tokens (e.g. Apify).
2.  **Continuous DB Syncing**: Active database mirroring is excluded. The pipeline operates as a stateless ETL batch processor.
