# Medical Terminology Mapper

Healthcare systems use inconsistent terminology—one system calls it "heart attack," another "myocardial infarction," another "MI." This breaks interoperability. This tool standardizes medical terms to SNOMED CT, LOINC, and RxNorm so systems can actually talk to each other.

## How It Works

The mapper processes terms through a priority-based pipeline:

```
Input Term → External APIs → Local Database Fallback → Fuzzy Matching → Ranked Results
```

**External APIs (Primary)**
| Source | Terminology | Data Provided |
|--------|-------------|---------------|
| NIH RxNorm API | RxNorm | Medication names, NDC codes, drug classes |
| Clinical Tables API | LOINC, RxTerms | Lab tests, clinical observations |
| SNOMED Browser | SNOMED CT | Clinical findings, procedures, conditions |

**Local Fallback**
| Database | Records | Purpose |
|----------|---------|---------|
| SNOMED CT | 633 | Common conditions and procedures |
| LOINC | 208 | Frequent lab tests |
| RxNorm | 237 | Common medications |

When external APIs fail or return no results, the system queries local SQLite databases, then applies fuzzy matching algorithms.

## Confidence Scoring

Confidence reflects how well the search term matches the result display name:

```python
# Exact match
"diabetes mellitus" → "Diabetes mellitus" = 100%

# Containment match (term within result or vice versa)
"chest pain" → "Acute chest pain" = max(85%, string_similarity)

# Fuzzy match (best of three algorithms)
"diabtes" → "Diabetes" = max(ratio, token_sort_ratio, token_set_ratio)
```

Results below 60% confidence are filtered out—below this threshold, matches are often false positives or tangentially related terms that would require manual review anyway. Batch processing returns maximum 3 results per terminology system (9 total per term) because more results create noise without adding value; if the correct match exists, it's almost always in the top 3.

## Matching Pipeline

Each term passes through these stages in order:

1. **API Search** — Query external APIs with configurable timeout (5s per source)
2. **Local Lookup** — If no API results, search indexed SQLite databases
3. **Fuzzy Matching** — RapidFuzz algorithms with length-ratio validation to prevent false positives

The length-ratio check (minimum 30% overlap) prevents short substrings from matching long terms. Without this, "ra" would match "Pneumonoultramicroscopicsilicovolcanoconiosis" via partial_ratio.

## System Design

### API Integration

The `ThreadSafeTerminologyMapper` creates per-thread mapper instances to handle concurrent FastAPI requests:

```
Request → Thread Pool → Thread-Local Mapper → External Service → Response
```

External API calls use a fallback chain:
- RxNorm: NIH API → Clinical Tables RxTerms
- LOINC: Clinical Tables → LOINC FHIR
- SNOMED: SNOMED Browser API

### Batch Processing

Batch jobs run asynchronously via FastAPI `BackgroundTasks`:

1. File uploaded → Job created with UUID
2. Background task processes terms in batches of 5 (500ms delay between batches)
3. Client polls `/batch/status/{job_id}` for progress
4. Results stored in memory, retrieved via `/batch/result/{job_id}`

Rate limiting between batches prevents overwhelming external APIs.

### Data Flow

```
┌──────────────┐     ┌──────────────┐     ┌───────────────────┐
│ React Client │────▶│ FastAPI      │────▶│ TerminologyService│
│              │     │ /api/v1/*    │     │                   │
└──────────────┘     └──────────────┘     └─────────┬─────────┘
                                                    │
                            ┌───────────────────────┼───────────────────────┐
                            ▼                       ▼                       ▼
                     ┌─────────────┐         ┌─────────────┐         ┌─────────────┐
                     │ RxNorm API  │         │ SNOMED API  │         │ LOINC API   │
                     └──────┬──────┘         └──────┬──────┘         └──────┬──────┘
                            │                       │                       │
                            └───────────────────────┼───────────────────────┘
                                                    ▼
                                          ┌─────────────────┐
                                          │ Local SQLite    │
                                          │ (fallback)      │
                                          └─────────────────┘
```

## Project Structure

```
├── backend/
│   ├── api/
│   │   └── v1/
│   │       ├── routers/
│   │       │   ├── terminology.py      # Single term mapping endpoint
│   │       │   └── batch.py            # Batch upload and status endpoints
│   │       ├── services/
│   │       │   ├── terminology_service.py    # Orchestrates mapping logic
│   │       │   ├── batch_service.py          # Background job management
│   │       │   └── thread_safe_mapper.py     # Thread-local mapper instances
│   │       └── models/                 # Pydantic request/response schemas
│   │
│   ├── app/
│   │   └── standards/
│   │       └── terminology/
│   │           ├── mapper.py           # Core mapping logic
│   │           ├── fuzzy_matcher.py    # RapidFuzz algorithm implementations
│   │           ├── embedded_db.py      # SQLite database manager
│   │           └── external_service.py # API client for NIH, Clinical Tables
│   │
│   └── data/
│       └── terminology/
│           ├── snomed_concepts.db      # 633 SNOMED CT concepts
│           ├── loinc_concepts.db       # 208 LOINC observations
│           └── rxnorm_concepts.db      # 237 RxNorm medications
│
├── frontend/
│   └── src/
│       ├── App.tsx                     # Main application component
│       ├── services/api.ts             # Axios client configuration
│       └── utils/exportUtils.ts        # CSV/JSON export functions
│
├── docker-compose.yml                  # Container orchestration
├── start.sh                            # One-command startup script
└── stop.sh                             # Cleanup script with options
```

## Tech Stack

| Layer | Technology | Purpose |
|-------|------------|---------|
| Frontend | React 18, TypeScript, Vite | Single-page application |
| Backend | FastAPI, Python 3.11 | REST API with async support |
| Matching | RapidFuzz | Fuzzy string matching algorithms |
| Database | SQLite | Local terminology fallback |
| Deployment | Docker Compose | Container orchestration |

## Setup

```bash
git clone https://github.com/Brandon12200/medical-terminology-mapper.git
cd medical-terminology-mapper
docker-compose up -d

# Frontend: http://localhost:3000
# API docs: http://localhost:8000/api/docs
```

## API Endpoints

```bash
# Map single term
POST /api/v1/map
Body: { "term": "diabetes", "systems": ["snomed", "loinc", "rxnorm"] }

# Upload batch file
POST /api/v1/batch/upload
Body: FormData with CSV file (requires "term" column)

# Check batch status
GET /api/v1/batch/status/{job_id}

# Get batch results
GET /api/v1/batch/result/{job_id}
```

## Sample Datasets

Six pre-built CSV files for testing (724+ terms total):

| File | Terms | Focus |
|------|-------|-------|
| hospital_discharge_summary.csv | 120 | Multi-specialty conditions |
| comprehensive_lab_tests.csv | 115 | Hematology, chemistry, microbiology |
| comprehensive_medications.csv | 140 | Drug classes from analgesics to biologics |
| emergency_department_cases.csv | 81 | Triage scenarios by severity |
| surgical_procedures.csv | 117 | Procedures by complexity |
| rare_diseases_comprehensive.csv | 151 | Genetic conditions and syndromes |

## Design Decisions

**Polling over WebSockets for batch status**. WebSockets would provide real-time updates, but add client complexity and connection management overhead. Batch jobs take 30-120 seconds; polling every 2 seconds is acceptable latency and simpler to implement and debug.

**SQLite over PostgreSQL**. The local databases are read-only fallbacks containing ~1,000 static records. SQLite requires no server process, ships with Python, and makes the entire application deployable with `docker-compose up`. A production system with user-contributed mappings would need PostgreSQL.

**In-memory job storage over Redis**. Batch results are stored in a Python dictionary. This loses jobs on server restart, but eliminates an infrastructure dependency. Acceptable for a tool where users process files and export results in a single session.

**Thread-local mappers over connection pooling**. FastAPI runs in a thread pool. Rather than implement connection pooling for the mapper's database connections, each thread gets its own mapper instance via `threading.local()`. Trades memory for simplicity.

**At 10x scale**, the bottleneck would be external API rate limits, not internal architecture. I'd add: response caching with TTL (most medical terms map to the same codes), request queuing to smooth traffic spikes, and async HTTP calls to parallelize API requests within a single term lookup.

## License

MIT
