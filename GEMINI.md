# AGENTS.md — Master Project Instructions

## 1. Project Mission

Build a standalone, subject-agnostic AI-scaffolded and gamified course generator for college and university examination preparation.

Teachers upload course materials. The system locally extracts and organises the academic content, analyses the syllabus and examination requirements, and generates a playable, gamified learning roadmap with interactive activities and examination-oriented support.

The platform must work across academic domains. Brain–Computer Interface (BCI) is only an optional sample dataset in `sample_inputs/`; it is not the product domain and must not shape the architecture.

## 2. Non-Negotiable Product Principles

1. **Subject agnostic:** Never hardcode a particular subject, course, topic, discipline, technical pipeline, or academic vocabulary into shared application logic.
2. **Exam aligned:** Ground learning content and answer guidance in the uploaded syllabus, lecture materials, examination questions, and marking scheme when provided.
3. **Pedagogically structured:** Every Stepping-Stone Node follows the four-screen contract defined below.
4. **Dynamic activities:** Select activity types according to the learning objective and academic content. Do not assume every subject needs diagrams, definitions, formulas, code, or numerical problems.
5. **Reusable, JSON-driven frontend:** The frontend must render activities from their structured JSON `type`. It must not contain subject-specific conditions. This rule is mandatory.
6. **Validated AI output:** Treat model responses as untrusted input. Parse and validate them against Pydantic contracts before using or returning them.
7. **Token efficient:** Parse and clean supported documents locally before invoking an AI provider.
8. **Fault tolerant:** Handle provider failures, rate limits, retries, partial generation, and interrupted jobs without silently losing progress.
9. **Prototype focused:** Prefer a small, clear, working implementation over premature production infrastructure or unnecessary abstractions.

## 3. Expected Repository Structure

Keep the repository aligned with this target structure:

```text
gamified-course-prototype/
├── AGENTS.md
├── GEMINI.md
├── PROGRESS.md
├── Phases.md
├── _reference_repos/                  # Read-only references; never execute their scripts
│   ├── andrej-karpathy-skills/
│   ├── ECC/
│   ├── duolingo-clone/
│   └── instructor-py/
├── sample_inputs/
│   ├── Brain Machine Interface_Syllabus.docx
│   └── BCI_Module_I_II_Questions.docx
├── backend/
│   ├── requirements.txt
│   ├── schemas.py
│   ├── preprocessor.py
│   ├── agents.py
│   ├── main.py
│   └── data/
│       └── jobs_state.json            # Runtime-generated state; do not treat as source code
└── frontend/
    ├── package.json
    └── src/
        ├── App.jsx
        └── components/
            ├── NodePlayerModal.jsx
            └── BossArenaModal.jsx
```

Do not create extra files or directories unless they are necessary for the requested functionality. If an additional file is genuinely required, explain its purpose in the relevant implementation handoff and update the inventory deliberately.

`GEMINI.md` must be an exact copy of this file or a symlink to it, according to the environment's supported workflow. Do not let the two instruction files drift apart.

`PROGRESS.md` is the sequential relay tracker. Use `[ ]` for not started, `[~]` for in progress, and `[x]` for completed and checked. Whenever a project file is created or updated, also update only that file's status row and its concise entry in the `Relay Handoff Log` at the bottom of `PROGRESS.md`. This tracker bookkeeping is the sole routine companion-file exception to the one-file rule; it does not authorize edits to any other project file. When `PROGRESS.md` itself is the requested target, update its relevant sections directly.

## 4. Academic Inputs and Course Generation

### Supported source material

The initial prototype should support:

- Syllabus documents containing modules, units, topics, subtopics, or learning outcomes.
- Important examination questions, including 2-mark, 5-mark, and 10-mark questions where that pattern is used.
- Lecture notes and slides, initially including DOCX, PDF, and PPT/PPTX where supported by the implementation.

The 2M/5M/10M structure is a configurable prototype default, not a universal assumption. Do not reject other mark patterns or question formats solely because they differ from this default.

### Generation relationship

Use the syllabus to establish scope and topic breakdown. Use uploaded lecture materials to ground explanations. Use uploaded examination questions to directly populate the topic questions, answer guidance, rubrics, and answer blueprints.

**Strict Upload Filtering:** Only generate modules that actually have source material or examination questions uploaded. If a syllabus document outlines 4 modules but question papers or lecture notes are only uploaded for Modules 1 and 2, generate ONLY Modules 1 and 2. Never fabricate questions or courses for unuploaded modules.

Do not invent facts, citations, teacher expectations, mark allocations, or course requirements absent from the supplied material. Where input is missing or ambiguous, represent that uncertainty explicitly instead of fabricating it.

## 5. Roadmap, Visual Design, and Question Coverage Constraints

Generate a modern, gamified learning roadmap for each uploaded module with complete examination question coverage.

### Clean Modern Visual Design (Vertical Timeline Roadmap)
The user interface follows a crisp, high-end educational design (light slate aesthetic, spacious typography, uncluttered cards):
- **Header:** Displays Module tag, large bold module title, descriptive subtitle, and top-right progress indicator (`X / Y Nodes Completed` with a sleek purple fill progress bar).
- **Question Coverage Ledger Trigger:** A persistent header action giving immediate visibility into question coverage (e.g., `📋 Question Coverage: 35/35 Exam Questions Covered (100%)`).
- **Vertical Timeline Serpentine Stepper:**
  - Continuous vertical connecting timeline running on the left.
  - Distinct status markers:
    - **Completed:** Emerald circle with checkmark (`✓`).
    - **Current / Active:** Vibrant purple target ring (`(o)`).
    - **Locked:** Subtle gray circle with lock icon (`🔒`).
  - **Category Icon Tiles:** Rounded square icon badges (e.g., layers for foundations, hardware/chip for architecture, pulse/activity for signal analysis, trophy for Boss).
  - **Node Content:** Bold topic title, concise subtitle describing syllabus scope, and question count badge.
  - **Action Status:**
    - Completed nodes show `✓ Completed`.
    - Current node displays a prominent purple primary pill button (`▶ Continue`).
    - Locked nodes show `🔒 Locked`.
  - **Active Node Card Highlight:** The current playable node is highlighted with a soft, rounded light indigo/purple container card.

### Complete Question Coverage Ledger
Every single examination question uploaded by the teacher must be retained and tracked in a question-by-question coverage ledger.
- For example, if Module 1 contains 35 questions (15x 2M, 10x 5M Section B, 10x 5M Section C), **all 35 questions must be retained in the coverage ledger and taught/assessed across the module's topic nodes and Boss node**.
- Questions that overlap conceptually across sections with different mark allocations (e.g., 2-mark brief definition vs. 5-mark comparison vs. 10-mark architecture design) must NEVER be deleted or merged out of existence. Each represents a distinct examination requirement.
- The platform provides a full question-by-question coverage ledger view detailing the question prompt, marks, section, mapped topic node, activity type, and student mastery state.

## 6. Topic Node: Direct-Question Solving Architecture (Zero Textboxes)

Students learn by directly solving real examination questions, not by reading long paragraph walls or typing into unstructured textboxes.

### Strict Ban on Unstructured Free-Text Textboxes
University students preparing for exams do not benefit from typing paragraphs into empty textboxes with vague "reveal rubric" buttons. Every examination question in a Topic Node must be an **automatically scored, structured examination activity**.

### Suite of 6 Structured, Automatically Scored Examination Activities
Every question is rendered using one of the following subject-agnostic, structured interactive types:
1. **Match the Following (`matching_pairs`):** Automatically scored matching between terms and their meanings/cues.
2. **Categorization / Drag-and-Drop / Tap-to-Sort (`classification`):** Sort concepts, statements, or characteristics into corresponding categories.
3. **Ordering (`ordering`):** Arrange the stages of an architecture, algorithm, workflow, or biological/technical process in sequence.
4. **Fill in the Blanks with Word Bank (`fill_blank`):** Conceptual explanation with exactly 4 missing technical terms selected from clickable word-bank tiles.
5. **Diagram Labelling (`diagram_labeling`):** Identify components or pipeline stages on extracted figures and structural charts.
6. **Select the Correct Exam Points (`key_points_check`):** Given a university exam prompt, select all the essential marking points needed for full marks from a list of plausible alternatives.
7. **Diagnostic Single-Choice MCQ (`mcq`):** Concept check with targeted misconception tags and immediate rationale.

### Direct Problem-First Interaction
- Each Topic Node contains its mapped examination questions (2-mark and 5-mark).
- No forced upfront reading screens or text walls before solving questions.
- Every activity provides instant feedback, automatic score validation, and remediation.

### Inline Prerequisite Gap-Filling
- When a student struggles, answers incorrectly, or requests help on an important question, an **inline prerequisite gap-filler** activates directly underneath that question.
- The prerequisite gap-filler provides targeted foundational scaffolding (e.g., a 4-blank tap-to-fill definition puzzle or conceptual clue) to bridge the missing knowledge.
- Once the prerequisite concept is reinforced, the student can successfully retry the main examination question.

## 7. Boss Node Contract

Boss Nodes are higher-challenge activities that prepare students for extended 10-mark examination responses or multi-step synthesis.

- Mapped directly from 10-mark examination questions and comprehensive learning outcomes in the uploaded materials.
- Contains structured assessment items requiring students to articulate, organize, or solve the extended problem.
- Serpentine unlock: Locked until preceding Topic Nodes in that module are completed.
- Successful submission unlocks an authentic, mark-aligned examination-answer blueprint.

The blueprint should be derived from supplied course materials and may include:

- The question or topic.
- A suggested answer structure and mark breakdown.
- Essential concepts and keywords.
- Relevant steps, formulas, diagrams, examples, or evidence where applicable.
- Common omissions and mistakes to avoid.

Do not claim that a blueprint guarantees a particular mark.

## 8. Mandatory JSON-Driven Frontend Architecture

This requirement is central to the project and must be preserved in every frontend implementation.

**The frontend must remain reusable and render activities based on their structured JSON `type` rather than containing subject-specific conditions.**

The backend defines the activity's educational content and typed data. The frontend renders the activity through reusable UI components.

### Required approach

- Define an explicit JSON contract for every supported activity type.
- Use a reusable activity renderer or registry that maps `type` values to reusable activity components.
- Keep shared interaction state and rendering logic generic wherever possible.
- Keep subject-specific text, questions, examples, choices, formulas, labels, and other academic payloads in the JSON data.
- Add a new activity by adding a type contract and its reusable renderer, not by adding branches for a particular subject.
- Validate activity payloads on the backend before sending them to the frontend.
- Validate or defensively inspect incoming payloads on the frontend as appropriate.
- Provide a graceful unsupported-type or malformed-payload fallback; never crash the whole learning experience because one activity cannot be rendered.
- Keep the four-screen player shell independent of the activity selected for Screen 3 or any other typed activity slot.

Illustrative activity type names include `fill_blank`, `matching_pairs`, `ordering`, `mcq`, `formula_completion`, `code_tracing`, `diagram_labeling`, `numerical_problem`, and `classification`. This list is extensible and must not be treated as a fixed list of subjects.

### Forbidden approach

Do not write frontend logic such as `if subject === "Mathematics"`, `if course === "BCI"`, or `if topic includes "EEG"` to decide which activity component to render. Do not hardcode sample-course concepts, diagrams, pipelines, or answers into generic components.

A generic renderer may branch on a validated activity `type`; it must not branch on an academic subject identity.

## 9. Backend Preprocessing Requirements

The local preprocessing stage should run before any LLM request wherever possible.

Use suitable libraries, initially including:

- `python-docx` for DOCX.
- `PyMuPDF` for PDF.
- A suitable parser such as `python-pptx` if PPT/PPTX parsing is implemented.
- `RapidFuzz` for fuzzy matching and near-duplicate detection.

Responsibilities:

1. Extract text and useful document structure from supported files.
2. Normalise whitespace and remove irrelevant formatting noise.
3. Identify or preserve useful headings, module boundaries, topic labels, and question numbering.
4. Remove administrative material that does not contribute to learning, while avoiding destructive removal of academic content.
5. Extract and classify examination questions when the source supports classification.
6. Detect exact and near-duplicate questions with configurable similarity thresholds.
7. Preserve source-file and page/section provenance when available so generated content can be traced back to inputs.
8. Produce a clean structured representation for downstream generation.

Do not assume that every document uses the same heading style or question numbering. Parsing should be tolerant and report extraction gaps rather than silently discarding content.

## 10. AI Provider Pool and Reliability

The initial design may route structured generation and verification requests across available free-tier or low-cost providers, such as:

- Google Gemini Flash.
- Cerebras.
- Groq.
- Mistral.
- GitHub Models.
- OpenRouter free models.

Provider availability, model identifiers, rate limits, and free-tier terms can change. Keep provider configuration isolated and configurable; do not assume a model or free quota is permanently available.

Required behaviour:

- Use provider adapters or a similarly clear interface so the rest of the application is not coupled to one provider's API format.
- Keep API keys in environment variables; never commit secrets or expose them to the frontend.
- Handle HTTP 429 and other transient failures with bounded retries and provider failover.
- Distinguish rate-limit, authentication, invalid-request, timeout, and malformed-output errors.
- Avoid retry storms. Use sensible limits and delays.
- Validate all structured model output before accepting it.
- Persist job progress so interrupted work can be inspected or resumed safely.
- Do not silently switch to an unrelated or unconfigured model.

Potential provider choices are options, not promises of current free-tier access.

## 11. Job State and API Behaviour

The initial prototype uses local JSON checkpointing at:

`backend/data/jobs_state.json`

Treat this as runtime-generated state, not source code. Ensure the directory exists when the backend starts or before writing. Use safe file-write practices so a crash during persistence does not corrupt the only state copy.

The FastAPI layer should provide clear upload and generation workflows, meaningful status reporting, validation errors, and predictable response contracts. Do not expose internal stack traces, API credentials, or sensitive provider response details to clients.

Make job stages explicit enough to identify whether a job is uploaded, preprocessing, generating, validating, completed, or failed. Preserve useful error context for debugging without leaking secrets.

## 12. Technology Stack

### Backend

- Python.
- FastAPI.
- Pydantic.
- `python-docx`.
- `PyMuPDF`.
- `RapidFuzz`.
- `httpx` for asynchronous HTTP calls where appropriate.
- `uvicorn` for local serving.

### Frontend

- React.
- Vite.
- Tailwind CSS.
- Lucide React.

Use the versions and installation approach selected in `backend/requirements.txt` and `frontend/package.json`. Keep dependencies minimal and avoid adding a library when a small, clear implementation is sufficient.

## 13. Reference Repositories: Read-Only Policy

The `_reference_repos/` directory contains local reference blueprints:

- `andrej-karpathy-skills/` — four Karpathy coding principles: Think Before Coding, Simplicity First, Surgical Changes, and Goal-Driven Execution.
- `ECC/` — structured engineering workflows.
- `duolingo-clone/` — gamified UI patterns, tactile styling, and winding roadmap layout calculations.
- `instructor-py/` — structured LLM output and Pydantic validation patterns.

Treat these repositories as read-only references. Inspect relevant source when useful, but do not execute their install scripts, setup scripts, or other third-party scripts. Do not blindly copy large portions of their code. Reimplement only the patterns needed by this prototype, respecting licences and attribution requirements.

## 14. Engineering and Coding-Agent Discipline

Follow these principles on every task:

1. **Think Before Coding:** Inspect relevant existing files and requirements before making a change. Identify dependencies and expected behaviour.
2. **Simplicity First:** Choose the smallest design that safely solves the problem.
3. **Surgical Changes:** Do not rewrite unrelated code or modify files outside the requested scope.
4. **Goal-Driven Execution:** Verify the specific outcome requested, not merely whether code was written.

Additional rules:

- Do not invent existing files, APIs, dependencies, environment variables, or test results.
- Do not overwrite user work without a clear reason and authorisation.
- Do not introduce hardcoded secrets, sample credentials, or private data.
- Use clear names, small functions, explicit types, and helpful comments where they improve maintainability.
- Handle malformed input and expected failures deliberately.
- Keep UI responsive and avoid needless rendering or expensive computations.
- Preserve accessibility basics, including labels, keyboard interaction, and visible focus states for interactive elements.
- Run relevant validation or tests when the environment permits; report accurately what was and was not checked.
- Never claim a test passed unless it was actually run and passed.

## 15. Sequential File-Creation and Relay Rules

The project is to be authored **one file at a time**, following the user's requested order.

For each file task:

1. Create or update only the explicitly requested target file, plus its status row and concise handoff entry in `PROGRESS.md`.
2. `PROGRESS.md` is the only routine companion file permitted. In it, modify only the matching checklist row and the matching entry under `Relay Handoff Log`; do not change unrelated tracker content during an ordinary one-file task.
3. Do not generate, modify, rename, or delete any other project files as a side effect.
4. Make the requested file complete and internally consistent with this master specification and the agreed project structure.
5. Do not create placeholder content for future files unless the requested file specifically needs a clearly documented interface reference.
6. Do not automatically proceed to the next file.
7. After completing the requested file and its tracker bookkeeping, stop and report completion. Wait for the user to request the next file.
8. If a required dependency or interface is not yet implemented because files are being created sequentially, define a clear contract without secretly creating the missing file.

Paired instruction-file rule: `AGENTS.md` and `GEMINI.md` must remain byte-identical copies (or a valid symlink arrangement). If both are explicitly requested, update both in the same task and verify their equality. Do not use this paired-file rule to justify changes to any other project file.

The `PROGRESS.md` bookkeeping exception is mandatory; a prompt to build or update a project file does not need to separately repeat "and update `PROGRESS.md`". Status meanings:

- `[ ]` — not started.
- `[~]` — currently in progress.
- `[x]` — completed and checked.

Do not mark a file `[x]` merely because it was drafted. Mark it complete only after the relevant syntax, import, or behavioural checks have actually been performed. State exactly which checks were run in the handoff log; do not imply that a smoke check is a full integration test.

## 16. Target File Inventory and Suggested Sequence

The target inventory is:

1. `AGENTS.md` — master architecture and relay rules.
2. `GEMINI.md` — exact copy or symlink of `AGENTS.md`.
3. `PROGRESS.md` — sequential progress tracker.
4. `Phases.md` — system repair, forensic audit, and architectural overhaul specifications.
5. `backend/requirements.txt` — backend dependency list.
6. `backend/schemas.py` — strict Pydantic contracts and generic activity JSON types.
7. `backend/preprocessor.py` — local document parsing and question deduplication.
8. `backend/agents.py` — multi-provider LLM routing and structured generation.
9. `backend/main.py` — FastAPI endpoints, uploads, and job checkpoints.
10. `frontend/package.json` — frontend scripts and dependencies.
11. `frontend/src/App.jsx` — upload UI and gamified serpentine roadmap.
12. `frontend/src/components/NodePlayerModal.jsx` — reusable four-screen player and JSON-driven activity rendering.
13. `frontend/src/components/BossArenaModal.jsx` — reusable Boss challenge and blueprint experience.

The sample files and reference repositories are inputs or local references, not files to generate. The user may change this sequence; follow the user's most recent explicit instruction.

## 17. Definition of Done

A requested file is complete when:

- It exists at the exact requested path.
- Its content serves the file's stated responsibility.
- It follows the subject-agnostic and JSON-driven architecture.
- Its contracts and assumptions are consistent with this document and the current agreed design.
- It does not contain accidental subject-specific behaviour or unsupported claims.
- Relevant syntax, formatting, or validation checks have been run when possible, and their outcomes are reported honestly.
- No unrelated files were modified.

**Overall success criterion:** A teacher should be able to provide course materials from different university subjects and receive a valid, subject-appropriate, exam-oriented gamified learning roadmap, while the same reusable frontend renders all supported activities from validated structured JSON.
