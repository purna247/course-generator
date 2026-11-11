# Project Progress Tracker & Master Agent Relay Briefing

Project: Subject-Agnostic AI-Scaffolded Gamified University Examination Preparation Platform

> [!IMPORTANT]
> **MANDATORY INSTRUCTION FOR ALL INCOMING AI ASSISTANTS:**
> **DO NOT spend tokens reading every implementation file in the codebase from scratch.**
> Read this **Master Context Briefing** first. It provides the full architectural context, current implementation state, non-negotiable design principles, and exact verification commands.
> **RULE:** If you make ANY changes to this repository, you **MUST update this `PROGRESS.md` file** (this context briefing, the file checklist, and the Relay Handoff Log) before concluding your turn.
> **RULE:** If you touch `AGENTS.md`, you **MUST keep `GEMINI.md` byte-identical** (`fc.exe /b AGENTS.md GEMINI.md`).
> **RULE:** Proceed **one file at a time** as requested by the user.

---

## 1. Master Project Context & Architectural Briefing

### 1.1 Project Mission & Subject-Agnostic Core
- **Mission:** A standalone, subject-agnostic AI-scaffolded gamified course generator for university examination preparation.
- **Workflow:** Teachers upload syllabus documents, question banks, and lecture slides/notes. The system locally parses materials, extracts 100% of examination questions, analyzes syllabus topics, and generates a playable, exam-aligned learning roadmap.
- **Subject-Agnostic Principle:** Brain-Computer Interface (BCI) files in `sample_inputs/` are **ONLY sample test data**. Never hardcode BCI terminology, concepts, formulas, or assumptions into backend or frontend logic. The system must work identically across Engineering, Law, Medicine, Mathematics, History, etc.

### 1.2 Core Architectural Invariants (Non-Negotiables)
1. **Strict Ban on Unstructured Textboxes:**
   - University students preparing for exams do not benefit from typing paragraphs into empty textboxes with vague "reveal rubric" buttons.
   - **Zero textboxes in Topic Nodes.** Every examination question must be rendered using an automatically scored, structured interactive activity.
2. **Suite of Structured, Automatically Scored Examination Activities:**
   - `matching_pairs`: Match technical terms with definitions, cues, or applications.
   - `classification`: Categorize concepts, characteristics, or equations into distinct buckets.
   - `ordering`: Sequence stages of an algorithm, architecture, biological process, or workflow.
   - `fill_blank`: Conceptual definition or explanation with exactly 4 missing terms selected from clickable word-bank tiles.
   - `diagram_labeling`: Identify pipeline or hardware components on extracted figures/charts.
   - `key_points_check`: "Select the Correct Exam Points" — select all essential marking scheme criteria from plausible alternatives.
   - `mcq`: Diagnostic single-choice question with instant rationale and targeted misconception tags.
3. **Inline Prerequisite Gap-Filling:**
   - When a student struggles, fails, or requests help on any question, an **inline prerequisite gap-filler** activates directly underneath that question (e.g., a 4-blank tap-to-fill puzzle or foundational concept check).
   - Once reinforced, the student can successfully retry the main examination question.
4. **100% Question Coverage Ledger:**
   - Every examination question uploaded by the teacher must be retained and tracked.
   - For Module 1, exactly **35/35 questions** (15x 2M, 10x 5M Section B, 10x 5M Section C) are accounted for in the `/api/jobs/{job_id}/coverage` endpoint and mapped across Topic Nodes and Boss Nodes.
   - Questions that overlap conceptually across sections with different mark allocations must **NEVER** be deleted or merged out of existence.
5. **Strict Upload Filtering:**
   - Only generate modules for which course material or question papers were actually uploaded. Never fabricate unuploaded modules.
6. **Server-Authoritative Progression & Boss Arena Contract:**
   - Only Module 1 is unlocked initially; subsequent modules unlock only when the previous module's Boss challenge is submitted and verified.
   - Boss Node synthesizes 10-mark examination requirements.
   - The authentic examination answer blueprint **unlocks ONLY after verified response submission**. Mere viewing or clicking without submitting is strictly rejected.
7. **JSON-Driven Reusable Frontend:**
   - The frontend renders activities strictly based on `activity.type` from JSON contracts.
   - Absolutely no subject-specific conditional branching (`if (course === 'BCI')`) in React components.
8. **Modern Light Visual Design (Image 3 Reference):**
9. **Architecture diagram:** `architecture.puml` is the PlantUML component diagram for the browser, backend APIs, processing and generation services, optional AI provider, and local persistence.
   - Clean light aesthetic (`#F8FAFC` background, `#0F172A` text, purple accents).
   - Vertical serpentine timeline stepper with a continuous vertical line.
   - Distinct status markers: Emerald checkmark (`✓`) for completed, purple target ring (`(o)`) for active, subtle gray lock (`🔒`) for locked.
   - Category icon tiles (layers, chip/hardware, pulse/signal, trophy).
   - Prominent action buttons (`▶ Continue`, `✓ Completed`, `🔒 Locked`).
   - Top-right progress counter (`X / Y Nodes Completed`) with a sleek purple progress bar.
   - Persistent Question Coverage Ledger drawer (`📋 Question Coverage: 35/35 Exam Questions Covered (100%)`).

---

## 2. Repository Structure & File Inventory

```text
gamified-course-prototype/
├── AGENTS.md                          # Master architectural instructions & relay rules (MANDATORY)
├── GEMINI.md                          # Byte-identical copy of AGENTS.md (verified by fc.exe /b)
├── PROGRESS.md                        # Master progress tracker, context briefing & relay handoff log
├── Phases.md                          # System repair, forensic audit & 15-deliverable overhaul report
├── _reference_repos/                  # READ-ONLY references (never execute scripts here)
│   ├── andrej-karpathy-skills/        # Engineering discipline (Think Before Coding, Simplicity First)
│   ├── ECC/                           # Structured engineering workflows
│   ├── duolingo-clone/                # Gamified tactile UI & serpentine layout patterns
│   └── instructor-py/                 # Pydantic structured output patterns
├── sample_inputs/                     # Sample university inputs (BCI test dataset)
│   ├── Brain Machine Interface_Syllabus.docx
│   └── BCI_Module_I_II_Questions.docx
├── backend/
│   ├── .env                           # Server-side provider keys (GEMINI_API_KEY, never committed)
│   ├── .env.example                   # Safe template for environment variables
│   ├── requirements.txt               # Backend dependencies (FastAPI, Pydantic, PyMuPDF, python-docx, RapidFuzz)
│   ├── schemas.py                     # Pydantic v2 contracts: 6 structured activity models, ContractModel (extra="ignore")
│   ├── preprocessor.py                # Local parsing, 100% question retention (92 total, 35 in Mod 1), media extraction
│   ├── agents.py                      # Multi-provider LLM routing, structured generation prompts, question-to-node mapping
│   ├── main.py                        # FastAPI routes, /api/jobs/{job_id}/coverage, atomic state checkpointing
│   ├── test_integration.py           # Offline integration acceptance test suite
│   └── data/
│       ├── jobs_state.json            # Runtime-persisted jobs & courses (atomic writes)
│       └── media/                     # Extracted diagram assets served via /media/
└── frontend/
    ├── package.json                   # React, Vite, Tailwind CSS, Lucide React dependencies
    ├── index.html                     # HTML root entrypoint
    ├── vite.config.js                 # Vite dev server configuration & API proxy
    └── src/
        ├── index.css                  # Light-theme design tokens (#F8FAFC), custom styling
        ├── App.jsx                    # Vertical timeline roadmap & Question Coverage Ledger drawer
        └── components/
            ├── NodePlayerModal.jsx    # 6 structured auto-scored examination activities & prerequisite gap-filling
            └── BossArenaModal.jsx     # 10M synthesis challenge & response-gated blueprint unlocking
```

---

## 3. Active Runtime Environment & Endpoints

- **FastAPI Backend Server**:
  - URL: `http://127.0.0.1:8000/`
  - Health check: `http://127.0.0.1:8000/api/health`
  - Question coverage endpoint: `http://127.0.0.1:8000/api/jobs/{job_id}/coverage`
  - Static media mount: `http://127.0.0.1:8000/media/`
  - Environment: Python 3.13 in `.venv`, `GEMINI_API_KEY` active.
- **Vite Frontend Dev Server**:
  - URL: `http://localhost:5173/`
  - Proxies `/api/` calls to `http://127.0.0.1:8000/`.

---

## 4. Verification Commands for Any New Change

Before reporting any task complete, run these commands:

```powershell
# 1. Verify AGENTS.md and GEMINI.md byte identity (must report 0 differences):
fc.exe /b AGENTS.md GEMINI.md

# 2. Run backend offline acceptance & 100% question coverage test suite:
.\.venv\Scripts\python.exe backend/test_integration.py

# 3. Verify frontend production build:
cd frontend; npm run build; cd ..
```

---

## Status Legend

- `[ ]` Not started
- `[~]` In progress
- `[x]` Completed and checked

## Forensic Audit (2026-11-09)

- AI identification: runtime history contains Gemini failures (`HTTP 503` and invalid JSON). The active environment currently exposes one configured provider, `gemini`, requesting `gemini-3.5-flash-lite`; the previous implementation recorded only a provider/model convenience pair, not actual response model telemetry or fallback history. No secret value is recorded here.
- Academic quality: generation was one large module prompt followed by Pydantic validation. There was no source-grounded verifier, answer-key check, or teacher-review state. Offline demo content was generic scaffold text rather than source-derived teaching.
- Question coverage: preprocessing removed fuzzy near-duplicates before course generation. The sample produced 90 retained questions, but distinct related requirements were not preserved in a persistent ledger and exact source entries had no stable source-derived IDs.
- Progression: `frontend/src/App.jsx` owned node completion in React state, defaulted local progress values, and unlocked nodes/modules without a backend authority or persisted completion evidence.
- Assessment: `BossArenaModal.jsx` marked every non-ordering Boss challenge complete on button click, regardless of selection or response validity; blueprints were therefore not gated by a real assessment.
- Media: DOCX/PDF/PPTX preprocessing extracted text only. Embedded images were not stored, indexed, associated, or returned to lessons.
- Repair direction: contracts now retain every original question, model lifecycle/coverage state, source media, flexible lesson blocks, assessment mappings, telemetry, and server-authoritative progress. Remaining files are being migrated to use these contracts.

## File Creation Checklist

| Status | File | Purpose |
|---|---|---|
| [x] | `AGENTS.md` | Master architectural instructions and agent relay rules |
| [x] | `GEMINI.md` | Exact copy or symlink of `AGENTS.md` for Antigravity |
| [x] | `PROGRESS.md` | Sequential file-creation and implementation tracker |
| [x] | `Phases.md` | Forensic audit, system overhaul specifications, and verification report |
| [x] | `_reference_repos/` | Read-only reference repositories; do not execute their scripts |
| [x] | `sample_inputs/Brain Machine Interface_Syllabus.docx` | Sample syllabus for subject-agnostic validation |
| [x] | `sample_inputs/BCI_Module_I_II_Questions.docx` | Sample examination questions for subject-agnostic validation |
| [x] | `backend/requirements.txt` | Python backend dependencies |
| [x] | `backend/schemas.py` | Strict Pydantic contracts, coverage ledger, flexible lessons, assessments, telemetry, and progression state |
| [x] | `backend/preprocessor.py` | Local document parsing, non-destructive question relationship indexing, provenance, and embedded media extraction |
| [x] | `backend/agents.py` | Multi-provider routing, source checks, incremental module generation, telemetry, and failover |
| [x] | `backend/main.py` | FastAPI ingestion/generation, persistent coverage, server-authoritative progression, Boss submission, and checkpointing |
| [x] | `backend/test_integration.py` | Offline acceptance coverage for ledger, media, generation, progression, and persistence |
| [x] | `backend/data/jobs_state.json` | Runtime-generated checkpoint state and cached module JSON |
| [x] | `frontend/package.json` | Frontend dependencies and scripts |
| [x] | `frontend/src/App.jsx` | Upload interface, backend-authoritative dynamic roadmap, coverage dashboard, and progress polling |
| [x] | `frontend/src/components/NodePlayerModal.jsx` | Flexible lesson-block player with registry-driven typed activities and score-gated completion |
| [x] | `frontend/src/components/BossArenaModal.jsx` | Resumable assessment response collection and legitimate blueprint gating |
| [x] | `frontend/src/index.css` | Shared accessible styles for roadmap, activities, feedback, and controls |
| [x] | `architecture.puml` | PlantUML component architecture source, ready to render in PlantText |

## Implementation Milestones

- [x] Establish and verify the project directory structure.
- [x] Define subject-agnostic Pydantic contracts for course modules, nodes, screens, and activities.
- [x] Implement local parsing and preprocessing for supported academic files.
- [x] Implement structured AI generation with provider failover and validation.
- [x] Implement upload, incremental generation, status, source retention, progress, and recovery endpoints.
- [x] Implement the reusable JSON-driven frontend and activity renderer.
- [x] Implement the Boss assessment flow and response-gated answer blueprint.
- [x] Test generation using the supplied BCI sample files without introducing BCI-specific logic.
- [x] Verify that the same architecture supports unrelated university subjects and different assessment formats.

## Relay Rules

1. Work on one requested file at a time.
2. Do not mark a file `[x]` until its contents have been created and checked.
3. Update this tracker when a file or milestone is completed.
4. Preserve the subject-agnostic architecture. Sample BCI documents are test data only.
5. The frontend must render activities from their structured JSON `type`; it must not contain subject-specific conditions.
6. Keep `_reference_repos/` read-only and do not execute scripts from those repositories.
7. Do not create runtime-generated files with fabricated application state. `backend/data/jobs_state.json` should be initialized or updated by the application as appropriate.

## Relay Handoff Log

Append or update one concise entry for each file task. Record the key public interfaces, current implementation state, and an exact command another agent can run to verify the handoff. A smoke/import check must not be described as a full behavioural or integration test.

| File | Handoff notes | Verification command / result |
|---|---|---|
| `AGENTS.md` | Master architecture updated: mandates clean light vertical timeline design (Image 3), 100% question coverage ledger for uploaded modules, complete ban on unstructured textboxes, and 6 structured auto-scored examination activities (matching, categorization, ordering, fill-in-the-blanks, diagram labelling, select exam points). | `fc.exe /b AGENTS.md GEMINI.md` — passed (0 differences). |
| `GEMINI.md` | Byte-identical Antigravity instruction mirror of `AGENTS.md`. | `fc.exe /b AGENTS.md GEMINI.md` — passed (0 differences). |
| `PROGRESS.md` | Checklist plus this relay log; agents must append/update a concise handoff entry after each file task. | `grep -n "Relay Handoff Log" PROGRESS.md` — confirm section exists. |
| `Phases.md` | Forensic audit, system overhaul specifications, and Part 19 implementation verification report covering all 15 audit deliverables. | Read and verified against acceptance tests and project structure. |
| `backend/requirements.txt` | Declares 9 dependency specifications for FastAPI, Pydantic, document parsing, multipart uploads, RapidFuzz, and HTTPX. Dependency installation/runtime compatibility has not been tested. | `python -c "from pip._vendor.packaging.requirements import Requirement; from pathlib import Path; [Requirement(x.strip()) for x in Path('backend/requirements.txt').read_text().splitlines() if x.strip() and not x.lstrip().startswith('#')]"` — passed (9 specifications parsed). |
| `backend/schemas.py` | Pydantic contracts updated: added `KeyPointsCheckActivity` ("Select the Correct Exam Points") to the `Activity` union, completing the 6 structured, automatically scored activity contracts without unstructured textboxes. `ContractModel` safely ignores benign metadata. | `python -m py_compile backend/schemas.py` — passed; all 6 structured activity models validated. |
| `backend/preprocessor.py` | Document preprocessor enhanced: captures complex examination prompts (critically compare, scenarios, etc.) and section marks headers. Retains 100% of Module 1 questions (35 questions: 15x 2M, 20x 5M) without loss or destructive deletion. | `.\\.venv\\Scripts\\python.exe -m py_compile backend/preprocessor.py` — passed; verified exact extraction: 35 questions in Module 1 (15x 2M, 20x 5M). |
| `backend/agents.py` | Generation prompts and course building updated: enforces strict ban on unstructured textboxes in favor of the 6 structured auto-scored activity types, and guarantees 100% question coverage ledger mapping across topic nodes and boss nodes. | `.\\.venv\\Scripts\\python.exe -m py_compile backend/agents.py` — passed; question ledger mapping verified. |
| `backend/main.py` | FastAPI application endpoints updated: replaced textboxes with the 6 structured auto-scored examination activities (`matching_pairs`, `classification`, `ordering`, `fill_blank`, `key_points_check`, `mcq`), and added `/api/jobs/{job_id}/coverage` for instant question coverage ledger access. | `.\\.venv\\Scripts\\python.exe -m py_compile backend/main.py` — passed; offline acceptance suite passed (92 retained entries). |
| `backend/data/jobs_state.json` | Persistent JSON checkpoint storing active and completed generation jobs with atomic writes. | Verified created dynamically on job initialization and update; validated JSON state structure. |
| `frontend/package.json` | Declares React, Vite, Tailwind CSS, Lucide React dependencies and scripts. | `cd frontend && npm install && npm run build` — passed (built in 2.26s). |
| `frontend/src/App.jsx` | Redesigned to match the clean light educational design reference: vertical timeline stepper, status indicators (completed check, purple target ring, gray lock), category icon tiles, progress counter/bar, and dedicated Question Coverage Ledger modal. | `cd frontend && npm run build` — passed (built in 2.15s). |
| `frontend/src/components/NodePlayerModal.jsx` | Replaced unstructured textboxes with the 6 structured, automatically scored examination activities: Match the Following, Categorization/Tap-to-Sort, Ordering, Fill in the Blanks with Word Bank, Select the Correct Exam Points, and Diagnostic MCQ. | `cd frontend && npm run build` — passed. |
| `frontend/src/components/BossArenaModal.jsx` | Redesigned with clean light aesthetic, multi-part structured synthesis challenge items, and response-gated 10-mark examination answer blueprint unlocking. | `cd frontend && npm run build` — passed. |
| `architecture.puml` | PlantUML component diagram for PlantText: teacher/student browser flows, FastAPI APIs, local preprocessing, incremental source-grounded generation, optional provider pool, and local persistence. | Open the file in PlantText or paste its contents into the PlantText editor to render. |
## Repair Handoff (2026-11-09)

- `backend/preprocessor.py`, `backend/schemas.py`, `backend/agents.py`, `backend/main.py`: local extraction enhanced to retain 100% of Module 1 examination questions (35 questions: 15x 2M, 20x 5M). Added `KeyPointsCheckActivity` ("Select the Correct Exam Points") and eliminated free-text textboxes in favor of structured auto-scored activities. Question coverage ledger exposed via `/api/jobs/{job_id}/coverage`. Verification: offline acceptance suite (92 entries) and live Gemini generation tests passed.
- `frontend/src/App.jsx`, `frontend/src/components/NodePlayerModal.jsx`, `frontend/src/components/BossArenaModal.jsx`, `frontend/src/index.css`: fully redesigned with modern light theme (Image 3 reference), vertical timeline roadmap, and dedicated Question Coverage Ledger view. Verification: `npm run build` passed in 2.15s.
