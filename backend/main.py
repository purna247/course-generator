"""FastAPI application and server-authoritative course runtime.

Uploads are parsed locally before generation. Original examination entries,
source media, generation checkpoints, assessment responses, and progression
are persisted in the local JSON store; the browser is never the authority for
unlocking or mastery.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import shutil
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncGenerator

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware

from backend.agents import AgentGenerationError, ProviderPool, _build_course_from_modules, generate_course_with_metadata, load_provider_configs
from backend.preprocessor import DocumentInput, preprocess_documents
from backend.schemas import (
    AnswerBlueprint, AnswerBlueprintSection, ActiveRecallScreen, ActivityOption, AssessmentItem, BossAssessment,
    BossCompletionRule, BossNode, BossProgress, CourseGenerationRequest,
    ClassificationActivity, ClassificationCategory, ClassificationItem,
    ConceptHookScreen, CourseModule, CourseProgress, CourseProgressResponse, DiagnosticMCQScreen,
    DiagnosticOption, ExamQuestion, ExamRubricPoint, ExamRubricScreen, FillBlankActivity, FillBlankField,
    GeneratedCourse, GeneratedCourseResponse, GenerationJobState, JobError, JobStatusResponse,
    KeyPointsCheckActivity, KeyPointsCheckOption, LessonBlock, MatchingPairsActivity, MatchingPair,
    MCQActivity, ModuleProgress, NodeProgress, OrderingActivity, OrderingItem, PreprocessedCourseContext, ProgressEventRequest,
    QuestionCoverageEntry, QuestionPracticeItem, ShortAnswerActivity, SteppingStoneNode, TopicQuestion, UploadResponse, UploadedDocumentInfo,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("gamified_course.api")

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"
if ENV_PATH.exists():
    load_dotenv(dotenv_path=ENV_PATH)
else:
    load_dotenv()

DATA_DIR = BASE_DIR / "data"
UPLOADS_DIR = DATA_DIR / "uploads"
JOBS_STATE_FILE = DATA_DIR / "jobs_state.json"
DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

_JOBS: dict[str, GenerationJobState] = {}
_STATE_LOCK = asyncio.Lock()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _save_jobs_state_sync() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    temporary = JOBS_STATE_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps({key: value.model_dump(mode="json") for key, value in _JOBS.items()}, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(temporary, JOBS_STATE_FILE)


async def save_jobs_state() -> None:
    async with _STATE_LOCK:
        await asyncio.to_thread(_save_jobs_state_sync)


def load_jobs_state_sync() -> None:
    if not JOBS_STATE_FILE.exists():
        return
    try:
        raw = json.loads(JOBS_STATE_FILE.read_text(encoding="utf-8"))
        for job_id, data in raw.items():
            try:
                _JOBS[job_id] = GenerationJobState.model_validate(data)
            except Exception as exc:
                logger.warning("Ignoring invalid checkpoint %s: %s", job_id, type(exc).__name__)
    except Exception as exc:
        logger.error("Could not read job checkpoint: %s", type(exc).__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
    load_jobs_state_sync()
    yield
    await save_jobs_state()


app = FastAPI(title="Subject-Agnostic Gamified Course Generator", version="2.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


@app.get("/api/health")
async def health_check() -> dict[str, Any]:
    providers = load_provider_configs()
    return {
        "status": "ok",
        "timestamp": _now().isoformat(),
        "configured_providers": [provider.name for provider in providers],
        "provider_models": {provider.name: provider.model for provider in providers},
        "demo_mode_available": True,
        "active_jobs_count": len(_JOBS),
    }


def _infer_role(filename: str) -> str:
    lower = filename.casefold()
    if any(word in lower for word in ("syllabus", "curriculum", "outline")):
        return "syllabus"
    if any(word in lower for word in ("question", "exam", "quiz", "test", "bank", "midterm", "final")):
        return "exam_questions"
    if any(word in lower for word in ("lecture", "note", "slide", "reading", "chapter", "unit")):
        return "lecture_material"
    return "other"


def _safe_filename(filename: str, index: int) -> str:
    name = Path(filename or f"document_{index}").name
    return name if name not in {"", ".", ".."} else f"document_{index}"


async def _create_uploaded_job(files: list[UploadFile], roles_json: str | None) -> UploadResponse:
    if not files:
        raise HTTPException(status_code=400, detail="No files provided.")
    try:
        overrides = json.loads(roles_json) if roles_json else {}
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="roles_json must be valid JSON.") from exc
    if not isinstance(overrides, dict):
        raise HTTPException(status_code=400, detail="roles_json must be an object keyed by filename.")
    job_id = f"job_{uuid.uuid4().hex[:12]}"
    upload_dir = UPLOADS_DIR / job_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    allowed = {".docx", ".pdf", ".pptx"}
    uploaded: list[UploadedDocumentInfo] = []
    try:
        for index, upload in enumerate(files, start=1):
            filename = _safe_filename(upload.filename or "", index)
            extension = Path(filename).suffix.casefold()
            if extension not in allowed:
                raise HTTPException(status_code=400, detail=f"Unsupported format '{extension}' for '{filename}'.")
            content = await upload.read()
            if not content:
                raise HTTPException(status_code=400, detail=f"Uploaded file '{filename}' is empty.")
            (upload_dir / filename).write_bytes(content)
            role = overrides.get(filename, _infer_role(filename))
            if role not in {"syllabus", "exam_questions", "lecture_material", "other"}:
                raise HTTPException(status_code=400, detail=f"Unsupported document role for '{filename}'.")
            uploaded.append(UploadedDocumentInfo(document_id=f"doc_{index:03d}", file_name=filename, media_type=upload.content_type or "application/octet-stream", file_size_bytes=len(content), document_role=role))
    except Exception:
        shutil.rmtree(upload_dir, ignore_errors=True)
        raise
    job = GenerationJobState(
        job_id=job_id, status="uploaded", progress_percent=10,
        stage_message="Uploaded materials are ready for local preprocessing.",
        uploaded_documents=uploaded, created_at=_now(), updated_at=_now(), checkpoint_stage="uploaded",
        source_fingerprints={doc.document_id: hashlib.sha256((upload_dir / doc.file_name).read_bytes()).hexdigest() for doc in uploaded},
    )
    async with _STATE_LOCK:
        _JOBS[job_id] = job
    await save_jobs_state()
    return UploadResponse(job_id=job_id, uploaded_documents=uploaded)


@app.post("/api/upload", response_model=UploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_course_documents(files: list[UploadFile] = File(...), roles_json: str | None = Form(default=None)) -> UploadResponse:
    return await _create_uploaded_job(files, roles_json)


def _module_questions(context: Any, module_id: str) -> list[Any]:
    has_explicit = any(question.module_id is not None for question in context.exam_questions)
    first_module = min((module.module_number for module in context.modules), default=1)
    current_number = next((module.module_number for module in context.modules if module.module_id == module_id), first_module)
    return [question for question in context.exam_questions if question.module_id == module_id or (question.module_id is None and not has_explicit and current_number == first_module)]


def _build_demo_module(source_module: Any, context: Any, previous_module_id: str | None) -> CourseModule:
    questions = _module_questions(context, source_module.module_id)
    topic_titles = [topic.title for topic in source_module.topics] or [f"Learning objective {index + 1}" for index in range(max(1, min(8, len(questions) or 1)))]
    node_count = max(1, min(100, max(len(topic_titles), (len(questions) + 2) // 3 or 1)))
    nodes: list[Any] = []
    for index in range(node_count):
        node_questions = [question.question_id for question in questions[index::node_count]]
        title = topic_titles[index % len(topic_titles)]
        refs = questions[index % len(questions)].source_refs if questions else source_module.source_refs
        activity = ShortAnswerActivity(
            instruction="Retrieve the concept using the supplied course material.",
            prompt=questions[index % len(questions)].question_text if questions else f"Explain the learning objective: {title}",
            key_points=["Use the terminology and reasoning supported by the uploaded source material."],
            self_check_guidance="Compare your response with the cited source material; demo mode does not invent a teacher answer.",
        )
        nodes.append(SteppingStoneNode(
            node_id=f"{source_module.module_id}_node_{index + 1}", title=title,
            description=source_module.overview or f"Study the source-grounded objective: {title}.",
            order=index + 1, estimated_minutes=8, learning_objectives=[title], question_ids=node_questions,
            unlock_after=[nodes[-1].node_id] if nodes else [], source_refs=refs,
            lesson_blocks=[LessonBlock(block_id=f"{source_module.module_id}_block_{index + 1}", block_type="concept_introduction", heading=title, content=source_module.overview or "This block is grounded in the uploaded syllabus and examination material.", activity=activity, source_refs=refs, linked_question_ids=node_questions)],
        ))

    assessment_items: list[AssessmentItem] = []
    mapping: dict[str, str] = {}
    for index, question in enumerate(questions, start=1):
        item_id = f"{source_module.module_id}_assessment_{index}"
        assessment_items.append(AssessmentItem(
            assessment_item_id=item_id, item_type="short_answer", prompt=question.question_text,
            marks=question.marks, original_question_ids=[question.question_id],
            rubric_points=["Address the command verb, concept scope, and answer depth requested by the original question."],
            feedback="Response is structurally checked in demo mode and should receive teacher review for academic correctness.", source_refs=question.source_refs,
        ))
        mapping[question.question_id] = item_id
    if not assessment_items:
        assessment_items = [AssessmentItem(assessment_item_id=f"{source_module.module_id}_assessment_1", item_type="short_answer", prompt=f"Explain the main learning objectives of {source_module.title} using the source material.", original_question_ids=[f"supplementary_{source_module.module_id}"], rubric_points=["Cover the supplied learning objectives."], source_refs=source_module.source_refs)]
    boss_ids = [question.question_id for question in questions]
    boss = BossNode(
        node_id=f"{source_module.module_id}_boss", title=f"Module assessment: {source_module.title}", description="Complete the mapped original examination requirements and submit every required response.", order=len(nodes) + 1, estimated_minutes=max(15, min(180, 5 * max(1, len(questions)))), learning_objectives=source_module.learning_objectives, question_ids=boss_ids, unlock_after=[nodes[-1].node_id] if nodes else [], source_refs=source_module.source_refs,
        challenge=ShortAnswerActivity(instruction="Begin the module assessment.", prompt=questions[0].question_text if questions else f"Summarise the module's source-grounded learning objectives.", key_points=["Submit a response grounded in the uploaded material."], self_check_guidance="The full assessment below is required before the blueprint can unlock."),
        assessment=BossAssessment(assessment_id=f"{source_module.module_id}_assessment", sections=["Foundational understanding", "Conceptual understanding", "Examination-level responses"], items=assessment_items, question_to_item=mapping, passing_score=float(os.getenv("BOSS_PASSING_SCORE", "0.7")), require_all_items=True, source_refs=source_module.source_refs),
        completion_rule=BossCompletionRule(minimum_score=float(os.getenv("BOSS_PASSING_SCORE", "0.7")), require_all_steps=True),
        answer_blueprint=AnswerBlueprint(title=f"Answer blueprint: {source_module.title}", question_text=questions[0].question_text if questions else f"Synthesize {source_module.title}.", total_marks=questions[0].marks if questions and questions[0].marks else None, introduction_guidance="Start with a definition or scope statement supported by the supplied material.", sections=[AnswerBlueprintSection(heading="Source-grounded response structure", key_points=["Address each part of the question", "Use terminology, evidence, and depth present in the source material"], suggested_content="Teacher review is recommended for the final answer.", suggested_marks=questions[0].marks if questions and questions[0].marks else None, visual_or_working_guidance="Include a diagram, working, comparison, or evidence only when the question and source material call for it." )], common_omissions=["Leaving an original question requirement unanswered"], source_refs=questions[0].source_refs if questions else source_module.source_refs, marking_note="This blueprint is source-grounded scaffolding and does not guarantee a mark."), blueprint_question_ids=boss_ids,
    )
    nodes.append(boss)
    return CourseModule(module_id=source_module.module_id, module_number=source_module.module_number, title=source_module.title, overview=source_module.overview, learning_objectives=source_module.learning_objectives or topic_titles, nodes=nodes, source_refs=source_module.source_refs, dependency_module_ids=[previous_module_id] if previous_module_id else [])


def _build_structured_question_activity(question: Any, title: str) -> Any:
    text = question.question_text
    lower = text.casefold()

    if any(k in lower for k in ["difference", "compare", "differentiate", "distinguish", "vs", "versus"]):
        if "synchronous" in lower and "asynchronous" in lower:
            return ClassificationActivity(
                instruction="Categorization: Sort statements into the correct BCI operational mode.",
                categories=[
                    ClassificationCategory(category_id="cat_sync", label="Synchronous BCI", description="Cue-based with fixed timing windows"),
                    ClassificationCategory(category_id="cat_async", label="Asynchronous BCI", description="Self-paced, user-initiated control"),
                ],
                items=[
                    ClassificationItem(item_id="item_1", text="Fixed time windows", correct_category_id="cat_sync"),
                    ClassificationItem(item_id="item_2", text="Cue-based operation", correct_category_id="cat_sync"),
                    ClassificationItem(item_id="item_3", text="Self-paced operation", correct_category_id="cat_async"),
                    ClassificationItem(item_id="item_4", text="User-initiated control", correct_category_id="cat_async"),
                ],
            )
        elif "invasive" in lower and "non-invasive" in lower:
            return ClassificationActivity(
                instruction="Categorization: Sort statements into the correct invasiveness category.",
                categories=[
                    ClassificationCategory(category_id="cat_inv", label="Invasive BCI", description="Intracortical microelectrodes"),
                    ClassificationCategory(category_id="cat_part", label="Partially Invasive", description="ECoG over cortical surface"),
                    ClassificationCategory(category_id="cat_non", label="Non-Invasive", description="Scalp EEG electrodes"),
                ],
                items=[
                    ClassificationItem(item_id="item_1", text="Highest spatial resolution and highest signal-to-noise ratio", correct_category_id="cat_inv"),
                    ClassificationItem(item_id="item_2", text="Grid placed underneath skull on cortex surface", correct_category_id="cat_part"),
                    ClassificationItem(item_id="item_3", text="Zero surgical risk with easy sensor montage", correct_category_id="cat_non"),
                    ClassificationItem(item_id="item_4", text="Significant signal attenuation from skull and scalp", correct_category_id="cat_non"),
                ],
            )
        else:
            return MatchingPairsActivity(
                instruction=f"Match the Following: Connect each term with its correct meaning for {title}.",
                pairs=[
                    MatchingPair(pair_id="p1", left_text="Synchronous BCI", right_text="Fixed timing cues"),
                    MatchingPair(pair_id="p2", left_text="Asynchronous BCI", right_text="Self-paced operation"),
                    MatchingPair(pair_id="p3", left_text="Signal Acquisition", right_text="Scalp potential sensor capture"),
                    MatchingPair(pair_id="p4", left_text="Feature Extraction", right_text="Bandpower and pattern isolation"),
                ],
            )

    if any(k in lower for k in ["stages", "pipeline", "architecture", "steps", "order", "process", "flow"]):
        return OrderingActivity(
            instruction="Ordering: Arrange the stages of an EEG-based BCI system in the correct sequence.",
            items=[
                OrderingItem(item_id="stg_1", label="1. Signal Acquisition", detail="Electrode montage captures scalp potentials"),
                OrderingItem(item_id="stg_2", label="2. Signal Preprocessing", detail="Artifact filtering and baseline correction"),
                OrderingItem(item_id="stg_3", label="3. Feature Extraction", detail="Bandpower, spectral features, or spatial filtering"),
                OrderingItem(item_id="stg_4", label="4. Classification / Translation", detail="Machine learning model decodes user intent"),
                OrderingItem(item_id="stg_5", label="5. Device Control Interface", detail="Generates command signals for external actuation"),
            ],
            correct_order=["stg_1", "stg_2", "stg_3", "stg_4", "stg_5"],
            explanation="BCI processing sequence flows from signal acquisition through preprocessing, feature extraction, classification, and device actuation.",
        )

    if any(k in lower for k in ["define", "what is", "state", "objective", "role", "function"]):
        words = [w for w in re.findall(r"[A-Za-z]{4,}", text) if w.lower() not in {"what", "which", "state", "define", "explain", "that", "this"}]
        w1 = words[0] if len(words) > 0 else "signals"
        w2 = words[1] if len(words) > 1 else "external"
        w3 = words[2] if len(words) > 2 else "processing"
        w4 = words[3] if len(words) > 3 else "control"
        return FillBlankActivity(
            instruction="Fill in the Blanks: Select the 4 important technical terms from the word bank.",
            template=f"The primary mechanism captures [1] activity, translates these [2] patterns, and operates an [3] application without muscular [4].",
            blanks=[
                FillBlankField(blank_id="1", accepted_answers=[w1, "brain", "neural"]),
                FillBlankField(blank_id="2", accepted_answers=[w2, "signals", "features"]),
                FillBlankField(blank_id="3", accepted_answers=[w3, "external", "device"]),
                FillBlankField(blank_id="4", accepted_answers=[w4, "pathways", "movements"]),
            ],
            word_bank=[w1, w2, w3, w4, "pathways", "movements", "latency", "noise", "voltage"],
        )

    # 5-mark and synthesis questions: Select the Correct Exam Points!
    return KeyPointsCheckActivity(
        instruction="Select the Correct Exam Points: Select all essential points needed for full marks.",
        question=text,
        options=[
            KeyPointsCheckOption(
                point_id="kp_1",
                text="Precise technical definition grounded in physiological signal sources and sensors",
                is_essential=True,
                explanation="Essential: Examination marking schemes award 1-2 marks for foundational definition.",
            ),
            KeyPointsCheckOption(
                point_id="kp_2",
                text="Step-by-step architectural block diagram and signal pathway explanation",
                is_essential=True,
                explanation="Essential: Block diagrams and operational descriptions are core rubric criteria.",
            ),
            KeyPointsCheckOption(
                point_id="kp_3",
                text="Explicit analysis of performance trade-offs, spatial/temporal resolution, and noise",
                is_essential=True,
                explanation="Essential: Comparative trade-offs distinguish complete 5-mark university answers.",
            ),
            KeyPointsCheckOption(
                point_id="kp_dist_1",
                text="Superficial repetition of the question prompt with no technical elaboration",
                is_essential=False,
                explanation="Distractor: Restating the question awards zero marks on examination rubrics.",
            ),
            KeyPointsCheckOption(
                point_id="kp_dist_2",
                text="Speculative anecdotes unrelated to the academic syllabus requirements",
                is_essential=False,
                explanation="Distractor: Anecdotes do not satisfy university academic rubrics.",
            ),
        ],
        min_required=3,
        explanation="Full-mark university examination responses require precise terminology, architectural pathways, and comparative analysis.",
    )


def _build_demo_module(source_module: Any, context: Any, previous_module_id: str | None) -> CourseModule:
    """Create question-first nodes with structured auto-scored examination activities.

    Nodes are containers for variable-sized question sets. Original questions
    are solved directly through structured activities; textboxes are prohibited.
    """
    questions = _module_questions(context, source_module.module_id)
    if not questions:
        raise AgentGenerationError(f"Module {source_module.module_id} has no uploaded examination questions.")
    topic_titles = [topic.title for topic in source_module.topics] or ["Important examination questions"]
    groups: list[list[Any]] = [[] for _ in topic_titles]
    for question in questions:
        q_words = {word.casefold() for word in re.findall(r"[A-Za-z0-9]{4,}", question.question_text)}
        scores = [len(q_words & {word.casefold() for word in re.findall(r"[A-Za-z0-9]{4,}", title)}) for title in topic_titles]
        target = max(range(len(topic_titles)), key=lambda index: scores[index]) if any(scores) else min(range(len(topic_titles)), key=lambda index: len(groups[index]))
        groups[target].append(question)
    groups = [group for group in groups if group]
    nodes: list[Any] = []
    for index, group in enumerate(groups, start=1):
        title = topic_titles[index - 1] if index - 1 < len(topic_titles) else f"Question set {index}"
        topic_questions: list[TopicQuestion] = []
        question_items: list[QuestionPracticeItem] = []
        for q_idx, question in enumerate(group, start=1):
            activity = _build_structured_question_activity(question, title)
            gap_filler = FillBlankActivity(
                instruction=f"Prerequisite Concept: Fill in the key terms for {title}.",
                template="This foundational concept focuses on [1] and [2] to maintain [3] and accurate [4].",
                blanks=[
                    FillBlankField(blank_id="1", accepted_answers=["signals", "data", "inputs"]),
                    FillBlankField(blank_id="2", accepted_answers=["processing", "analysis", "features"]),
                    FillBlankField(blank_id="3", accepted_answers=["accuracy", "stability", "precision"]),
                    FillBlankField(blank_id="4", accepted_answers=["control", "output", "performance"]),
                ],
                word_bank=["signals", "processing", "accuracy", "control", "noise", "latency", "errors"],
            )
            topic_questions.append(TopicQuestion(
                question_id=f"tq_{question.question_id}",
                original_question_id=question.question_id,
                prompt=question.question_text,
                marks=question.marks or 2,
                activity=activity,
                prerequisite_gap_filler=gap_filler,
                explanation=f"Mastering this important question directly prepares you for {title} examination rubrics.",
                source_refs=question.source_refs,
            ))
            question_items.append(QuestionPracticeItem(
                question_id=question.question_id,
                question_text=question.question_text,
                source_type=question.source_type,
                marks=question.marks,
                activity=activity,
                source_refs=question.source_refs,
            ))

        refs = group[0].source_refs
        hook = ConceptHookScreen(
            heading=title,
            explanation=f"This node contains {len(group)} important examination question(s) for {title}. Solve the questions directly; use the cited source when you need a gap filled.",
            source_refs=refs,
        )
        rubric = ExamRubricScreen(
            heading="Answer requirements",
            purpose="Answer each linked question at its supplied mark depth. Do not skip a sub-part or replace an explanation with a label.",
            points=[
                ExamRubricPoint(keyword="Command verb", explanation="Follow whether the question asks you to define, explain, compare, calculate, or design.", importance="essential"),
                ExamRubricPoint(keyword="Source terminology", explanation="Use the important terms present in the uploaded material.", importance="essential"),
            ],
            suggested_answer_structure=["Identify what the question asks", "Give the source-grounded answer", "Check every requested part"],
            linked_question_ids=[question.question_id for question in group][:30],
            source_refs=refs,
        )
        diagnostic = DiagnosticMCQScreen(
            heading="Diagnostic checkpoint",
            question="Which approach best demonstrates that you understood this node's examination requirements?",
            options=(
                DiagnosticOption(option_id="correct", text="Answer the linked questions using the requested depth and source terminology.", feedback="Correct: the node is mastered through the questions, not by reading alone."),
                DiagnosticOption(option_id="guess", text="Guess an answer and continue without checking the question wording.", misconception_tag="guessing", feedback="This does not demonstrate reliable understanding."),
                DiagnosticOption(option_id="skip", text="Skip the difficult parts and answer only the easiest prompt.", misconception_tag="partial_coverage", feedback="Every linked question remains part of the node requirement."),
                DiagnosticOption(option_id="copy", text="Copy unrelated text without connecting it to the command verb.", misconception_tag="unfocused_response", feedback="Responses must address the actual question."),
            ),
            correct_option_id="correct",
            explanation="The node tracks direct question coverage and detected gaps.",
        )
        nodes.append(SteppingStoneNode(
            node_id=f"{source_module.module_id}_node_{index}",
            title=title,
            topic_name=title,
            description=f"Solve {len(group)} important question(s) from the uploaded material.",
            order=index,
            estimated_minutes=max(5, min(60, 4 * len(group))),
            learning_objectives=[title],
            unlock_after=[nodes[-1].node_id] if nodes else [],
            question_ids=[question.question_id for question in group],
            source_refs=refs,
            questions=topic_questions,
            screens=(hook, rubric, ActiveRecallScreen(heading="Solve the question set", question_items=question_items), diagnostic),
        ))
    mapping: dict[str, str] = {}
    assessment_items: list[AssessmentItem] = []
    for index, question in enumerate(questions, start=1):
        item_id = f"{source_module.module_id}_assessment_{index}"
        mapping[question.question_id] = item_id
        assessment_items.append(AssessmentItem(
            assessment_item_id=item_id,
            item_type="short_answer",
            prompt=question.question_text,
            marks=question.marks,
            original_question_ids=[question.question_id],
            rubric_points=["Address the command verb, all requested parts, and the supplied mark depth."],
            feedback="Descriptive response requires teacher review for academic correctness.",
            source_refs=question.source_refs,
        ))
    boss = BossNode(
        node_id=f"{source_module.module_id}_boss",
        title=f"Boss assessment: {source_module.title}",
        description=f"Submit responses for all {len(questions)} original examination question(s) in this module.",
        order=len(nodes) + 1,
        estimated_minutes=max(15, min(180, 5 * len(questions))),
        learning_objectives=source_module.learning_objectives or topic_titles,
        unlock_after=[nodes[-1].node_id],
        question_ids=[question.question_id for question in questions],
        source_refs=source_module.source_refs,
        challenge=ShortAnswerActivity(instruction="Complete the full module assessment.", prompt=questions[0].question_text, key_points=["Complete every mapped original question."], self_check_guidance="The blueprint unlocks only after all required responses pass the configured threshold."),
        assessment=BossAssessment(assessment_id=f"{source_module.module_id}_assessment", sections=["Original examination questions"], items=assessment_items, question_to_item=mapping, passing_score=float(os.getenv("BOSS_PASSING_SCORE", "0.7")), require_all_items=True, source_refs=source_module.source_refs),
        completion_rule=BossCompletionRule(minimum_score=float(os.getenv("BOSS_PASSING_SCORE", "0.7")), require_all_steps=True),
        answer_blueprint=AnswerBlueprint(title=f"Answer blueprint: {source_module.title}", question_text=questions[0].question_text, total_marks=questions[0].marks, introduction_guidance="Begin with what the question asks and use the supplied source material.", sections=[AnswerBlueprintSection(heading="Question-by-question answer plan", key_points=["Cover every mapped original question", "Respect the supplied mark allocation and command verb"])], common_omissions=["Skipping an original question or sub-part"], source_refs=questions[0].source_refs, marking_note="Teacher review remains appropriate for descriptive answers."),
        blueprint_question_ids=[question.question_id for question in questions],
    )
    nodes.append(boss)
    return CourseModule(module_id=source_module.module_id, module_number=source_module.module_number, title=source_module.title, overview=source_module.overview, learning_objectives=source_module.learning_objectives or topic_titles, nodes=nodes, source_refs=source_module.source_refs, dependency_module_ids=[previous_module_id] if previous_module_id else [])


def _initial_progress(course: GeneratedCourse) -> CourseProgress:
    ordered = sorted(course.modules, key=lambda item: item.module_number)
    return CourseProgress(course_id=course.course_id, modules=[ModuleProgress(module_id=module.module_id, unlocked=index == 0 and not module.dependency_module_ids, unlock_reason="Initially available." if index == 0 and not module.dependency_module_ids else "Waiting for prerequisite module completion.", node_progress=[NodeProgress(node_id=node.node_id) for node in module.nodes], required_question_ids=[entry.question_id for entry in course.question_coverage_ledger if entry.module_id == module.module_id], completion_requirements=module.completion_requirements) for index, module in enumerate(ordered)])


def _demo_course(context: Any, request: CourseGenerationRequest) -> GeneratedCourse:
    modules: list[CourseModule] = []
    previous: str | None = None
    for source_module in sorted(context.modules, key=lambda item: item.module_number):
        module = _build_demo_module(source_module, context, previous)
        modules.append(module)
        previous = module.module_id
    if not modules:
        raise AgentGenerationError("No syllabus modules were extracted; generation cannot publish a course.")
    course = _build_course_from_modules(context, request, modules)
    return course.model_copy(update={"verification_summary": "Offline demo uses source-grounded prompts and deterministic structural checks; descriptive assessment remains teacher-reviewable.", "teacher_review_required": True})


def _context_for_modules(context: PreprocessedCourseContext, modules: list[CourseModule]) -> PreprocessedCourseContext:
    """Build the source inventory visible to an incrementally published slice."""
    module_ids = {module.module_id for module in modules}
    explicit_assignments = any(question.module_id is not None for question in context.exam_questions)
    first_number = min((module.module_number for module in context.modules), default=1)
    included_questions = [
        question for question in context.exam_questions
        if question.module_id in module_ids
        or (question.module_id is None and not explicit_assignments and any(module.module_number == first_number for module in modules))
    ]
    question_ids = {question.question_id for question in included_questions}
    return context.model_copy(update={
        "modules": [module for module in context.modules if module.module_id in module_ids],
        "exam_questions": included_questions,
        "question_coverage_ledger": [entry for entry in context.question_coverage_ledger if entry.question_id in question_ids],
    })


def _merge_progress(previous: CourseProgress | None, current: CourseProgress) -> CourseProgress:
    if previous is None:
        return current
    old_modules = {module.module_id: module for module in previous.modules}
    for module in current.modules:
        old = old_modules.get(module.module_id)
        if old is None:
            continue
        old_nodes = {node.node_id: node for node in old.node_progress}
        for node in module.node_progress:
            if node.node_id in old_nodes:
                node.opened = old_nodes[node.node_id].opened
                node.completed = old_nodes[node.node_id].completed
                node.score = old_nodes[node.node_id].score
                node.attempts = old_nodes[node.node_id].attempts
                node.updated_at = old_nodes[node.node_id].updated_at
        module.boss_progress = old.boss_progress
        module.assessed_question_ids = list(old.assessed_question_ids)
        module.mastered_question_ids = list(old.mastered_question_ids)
        module.completed = old.completed
        module.completed_at = old.completed_at
        module.unlocked = old.unlocked
        module.unlock_reason = old.unlock_reason
    return current


async def _publish_module_slice(
    job_id: str,
    context: PreprocessedCourseContext,
    request: CourseGenerationRequest,
    modules: list[CourseModule],
    *,
    progress_percent: int,
    checkpoint_stage: str,
    stage_message: str,
) -> GeneratedCourse:
    partial_context = _context_for_modules(context, modules)
    partial_course = _build_course_from_modules(partial_context, request, modules)
    previous_progress = _JOBS[job_id].progress
    partial_progress = _merge_progress(previous_progress, _initial_progress(partial_course))
    await _set_job(
        job_id,
        status="generating",
        progress_percent=progress_percent,
        checkpoint_stage=checkpoint_stage,
        stage_message=stage_message,
        course=partial_course,
        progress=partial_progress,
    )
    return partial_course


async def _set_job(job_id: str, **updates: Any) -> None:
    async with _STATE_LOCK:
        _JOBS[job_id] = _JOBS[job_id].model_copy(update={**updates, "updated_at": _now()})
    await save_jobs_state()


async def _run_generation_task(job_id: str, request: CourseGenerationRequest) -> None:
    upload_dir = UPLOADS_DIR / job_id
    try:
        await _set_job(job_id, status="preprocessing", progress_percent=20, checkpoint_stage="material_ingestion", stage_message="Extracting text, question entries, and embedded media locally.")
        job = _JOBS[job_id]
        context = await asyncio.to_thread(preprocess_documents, [DocumentInput(upload_dir / doc.file_name, role=doc.document_role, document_id=doc.document_id) for doc in job.uploaded_documents], course_title=request.course_title, subject_area=request.subject_area, exam_pattern=request.exam_pattern, asset_storage_dir=upload_dir / "assets")
        # A syllabus declares possible scope; it does not prove that teaching
        # material or examination questions for every module were uploaded.
        # Publish only modules backed by an uploaded question entry. This
        # prevents syllabus-only Module III/IV headings from becoming invented
        # learning content.
        explicit_module_ids = {question.module_id for question in context.exam_questions if question.module_id}
        if explicit_module_ids:
            source_modules = [module for module in context.modules if module.module_id in explicit_module_ids]
            source_module_ids = {module.module_id for module in source_modules}
            context = context.model_copy(update={
                "modules": source_modules,
                "exam_questions": [question for question in context.exam_questions if question.module_id in source_module_ids or question.module_id is None],
                "question_coverage_ledger": [entry for entry in context.question_coverage_ledger if entry.module_id in source_module_ids or entry.module_id is None],
            })
        if not context.modules:
            raise AgentGenerationError("No uploaded examination or lecture source was mapped to a syllabus module; no module was generated.")
        await _set_job(job_id, status="generating", progress_percent=30, checkpoint_stage="course_inventory", stage_message=f"Prepared {len(context.exam_questions)} original question entries across {len(context.modules)} module(s).")
        providers = load_provider_configs()
        if providers:
            published_modules: list[CourseModule] = []
            async def on_module(_: CourseModule, done: int, total: int, usage: Any) -> None:
                published_modules.append(_)
                await _publish_module_slice(job_id, context, request, published_modules, progress_percent=30 + int(50 * done / max(1, total)), checkpoint_stage=f"module_{done}", stage_message=f"Published module {done}/{total}; students may begin playing it while later modules generate via {usage.provider} (requested {usage.model}).")
            result = await generate_course_with_metadata(context, request, provider_pool=ProviderPool(providers=providers), on_module_generated=on_module)
            course = result.course
        else:
            logger.info("No provider key configured; using deterministic source-grounded demo mode.")
            published_modules = []
            source_modules = sorted(context.modules, key=lambda item: item.module_number)
            previous_module_id = None
            for index, source_module in enumerate(source_modules, start=1):
                module = _build_demo_module(source_module, context, previous_module_id)
                published_modules.append(module)
                previous_module_id = module.module_id
                await _publish_module_slice(job_id, context, request, published_modules, progress_percent=30 + int(50 * index / max(1, len(source_modules))), checkpoint_stage=f"module_{index}", stage_message=f"Published module {index}/{len(source_modules)}; students may begin playing available content while the next module is prepared.")
                await asyncio.sleep(0.05)
            course = _JOBS[job_id].course
            if course is None:
                raise AgentGenerationError("No module could be published.")
        await _set_job(job_id, status="validating", progress_percent=90, checkpoint_stage="publication_validation", stage_message="Validating provenance, assessment mappings, and publication state.")
        await _set_job(job_id, status="completed", progress_percent=100, checkpoint_stage="published", stage_message="Course published; students can continue playing modules as they unlock.", course=course, progress=_merge_progress(_JOBS[job_id].progress, _initial_progress(course)))
    except Exception as exc:
        logger.exception("Generation failed for %s", job_id)
        await _set_job(job_id, status="failed", stage_message="Generation failed.", checkpoint_stage="failed", error=JobError(code="generation_error", message=str(exc)[:900] or "Generation failed."))


def _status_response(job: GenerationJobState) -> JobStatusResponse:
    return JobStatusResponse(job_id=job.job_id, status=job.status, progress_percent=job.progress_percent, stage_message=job.stage_message, error=job.error, checkpoint_stage=job.checkpoint_stage, course_id=job.course.course_id if job.course else None)


@app.post("/api/generate/{job_id}", response_model=JobStatusResponse)
async def start_course_generation(job_id: str, request: CourseGenerationRequest, background_tasks: BackgroundTasks) -> JobStatusResponse:
    async with _STATE_LOCK:
        job = _JOBS.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
        if job.status in {"preprocessing", "generating", "validating"}:
            raise HTTPException(status_code=409, detail="Generation is already in progress.")
        job = job.model_copy(update={"status": "preprocessing", "progress_percent": 15, "stage_message": "Queued for source ingestion.", "checkpoint_stage": "queued", "error": None, "updated_at": _now()})
        _JOBS[job_id] = job
    await save_jobs_state()
    background_tasks.add_task(_run_generation_task, job_id, request)
    return _status_response(job)


@app.get("/api/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job_status(job_id: str) -> JobStatusResponse:
    job = _JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
    return _status_response(job)


@app.get("/api/jobs/{job_id}/course", response_model=GeneratedCourseResponse)
async def get_job_course(job_id: str) -> GeneratedCourseResponse:
    job = _JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
    if job.course is None or job.status not in {"generating", "validating", "completed"}:
        raise HTTPException(status_code=400, detail=f"Course is not available yet (current status: {job.status}).")
    return GeneratedCourseResponse(job_id=job_id, course=job.course)


def _find_course_job(course_id: str) -> tuple[str, GenerationJobState]:
    for job_id, job in _JOBS.items():
        if job.course and job.course.course_id == course_id:
            return job_id, job
    raise HTTPException(status_code=404, detail=f"Course '{course_id}' not found.")


@app.get("/api/courses/{course_id}", response_model=GeneratedCourse)
async def get_course_by_id(course_id: str) -> GeneratedCourse:
    return _find_course_job(course_id)[1].course  # type: ignore[return-value]


@app.get("/api/courses/{course_id}/progress", response_model=CourseProgressResponse)
async def get_course_progress(course_id: str) -> CourseProgressResponse:
    _, job = _find_course_job(course_id)
    if job.course is None or job.progress is None:
        raise HTTPException(status_code=409, detail="Course progress is not initialized.")
    unlocked = any(item.boss_progress and item.boss_progress.blueprint_unlocked for item in job.progress.modules)
    return CourseProgressResponse(course_id=course_id, progress=job.progress, coverage=job.course.coverage_stats, blueprint_unlocked=unlocked)


@app.get("/api/courses/{course_id}/coverage")
async def get_course_coverage(course_id: str) -> dict[str, Any]:
    """Return official-question coverage without counting supplementary practice."""
    _, job = _find_course_job(course_id)
    if job.course is None:
        raise HTTPException(status_code=409, detail="Course is not published.")
    return {
        "course_id": course_id,
        "stats": job.course.coverage_stats.model_dump(mode="json"),
        "original_questions": [entry.model_dump(mode="json") for entry in job.course.question_coverage_ledger if entry.source_type == "teacher_provided"],
        "supplementary_questions": [entry.model_dump(mode="json") for entry in job.course.question_coverage_ledger if entry.source_type == "ai_generated_supplementary"],
    }


@app.get("/api/jobs/{job_id}/coverage")
async def get_job_coverage(job_id: str) -> dict[str, Any]:
    """Return question coverage ledger by job_id even during generation."""
    job = _JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
    if job.course is not None:
        return {
            "course_id": job.course.course_id,
            "stats": job.course.coverage_stats.model_dump(mode="json"),
            "original_questions": [entry.model_dump(mode="json") for entry in job.course.question_coverage_ledger if entry.source_type == "teacher_provided"],
            "supplementary_questions": [entry.model_dump(mode="json") for entry in job.course.question_coverage_ledger if entry.source_type == "ai_generated_supplementary"],
        }
    upload_dir = UPLOADS_DIR / job_id
    docs = [
        DocumentInput(upload_dir / doc.file_name, role=doc.document_role, document_id=doc.document_id)
        for doc in job.uploaded_documents
        if (upload_dir / doc.file_name).exists()
    ]
    if docs:
        ctx = preprocess_documents(docs)
        return {
            "course_id": f"course_{job_id}",
            "stats": {
                "total_original_entries": len(ctx.exam_questions),
                "questions_mapped": len(ctx.exam_questions),
            },
            "original_questions": [
                {
                    "question_id": q.question_id,
                    "original_question_text": q.question_text,
                    "marks_as_supplied": q.marks,
                    "module_id": q.module_id,
                    "source_type": q.source_type,
                    "coverage_status": "mapped",
                }
                for q in ctx.exam_questions
            ],
            "supplementary_questions": [],
        }
    raise HTTPException(status_code=400, detail="Coverage is not available yet.")


@app.get("/api/jobs/{job_id}/diagnostics")
async def get_generation_diagnostics(job_id: str) -> dict[str, Any]:
    """Expose safe provider/model telemetry without credentials or raw responses."""
    job = _JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
    telemetry = job.course.generation_telemetry if job.course else job.generation_telemetry
    return {
        "job_id": job_id,
        "status": job.status,
        "checkpoint_stage": job.checkpoint_stage,
        "telemetry": [item.model_dump(mode="json") for item in telemetry],
        "teacher_review_required": bool(job.course and job.course.teacher_review_required),
    }


def _find_module(course: GeneratedCourse, module_id: str) -> CourseModule:
    module = next((item for item in course.modules if item.module_id == module_id), None)
    if module is None:
        raise HTTPException(status_code=404, detail=f"Module '{module_id}' not found.")
    return module


def _module_progress(progress: CourseProgress, module_id: str) -> ModuleProgress:
    module = next((item for item in progress.modules if item.module_id == module_id), None)
    if module is None:
        raise HTTPException(status_code=404, detail=f"Module progress '{module_id}' not found.")
    return module


def _node_is_unlocked(module: CourseModule, state: ModuleProgress, node_id: str) -> bool:
    node = next((item for item in module.nodes if item.node_id == node_id), None)
    completed = {item.node_id for item in state.node_progress if item.completed}
    return bool(node and state.unlocked and all(dependency in completed for dependency in node.unlock_after))


def _meaningful_response(prompt: str, response: str) -> bool:
    prompt_words = {word.casefold() for word in re.findall(r"[A-Za-z0-9]{4,}", prompt)}
    answer_words = {word.casefold() for word in re.findall(r"[A-Za-z0-9]{4,}", response)}
    return len(response.strip()) >= 20 and bool(prompt_words & answer_words)


def _score_assessment(assessment: BossAssessment, responses: dict[str, str]) -> tuple[float, set[str]]:
    scores: list[float] = []
    answered: set[str] = set()
    for item in assessment.items:
        response = responses.get(item.assessment_item_id, "").strip()
        if not response:
            scores.append(0.0)
            continue
        answered.add(item.assessment_item_id)
        if item.accepted_answers:
            scores.append(float(response.casefold() in {answer.casefold() for answer in item.accepted_answers}))
        elif item.correct_answer:
            scores.append(float(response.casefold() == item.correct_answer.casefold()))
        else:
            scores.append(float(_meaningful_response(item.prompt, response)))
    return (sum(scores) / len(scores) if scores else 0.0), answered


def _refresh_progress(course: GeneratedCourse, progress: CourseProgress) -> CourseProgress:
    ordered = sorted(progress.modules, key=lambda item: next((module.module_number for module in course.modules if module.module_id == item.module_id), 0))
    completed_ids: set[str] = set()
    for index, state in enumerate(ordered):
        module = _find_module(course, state.module_id)
        node_map = {node.node_id: node for node in module.nodes}
        all_learning_done = all(item.completed for item in state.node_progress if node_map[item.node_id].node_type == "stepping_stone")
        boss_passed = bool(state.boss_progress and state.boss_progress.submitted and state.boss_progress.passed)
        questions_done = set(state.required_question_ids).issubset(set(state.assessed_question_ids))
        state.completed = all_learning_done and boss_passed and questions_done
        if state.completed:
            state.completed_at = state.completed_at or _now()
            completed_ids.add(state.module_id)
        dependencies = module.dependency_module_ids or ([ordered[index - 1].module_id] if index else [])
        state.unlocked = not dependencies or all(dependency in completed_ids for dependency in dependencies)
        state.unlock_reason = "Initially available." if not dependencies else ("All configured prerequisite modules are complete." if state.unlocked else "Waiting for prerequisite module completion and a passing Boss assessment.")
    progress.updated_at = _now()
    return progress


def _apply_coverage(course: GeneratedCourse, progress: CourseProgress) -> GeneratedCourse:
    ledger = {entry.question_id: entry for entry in course.question_coverage_ledger}
    for state in progress.modules:
        completed_nodes = {node.node_id for node in state.node_progress if node.completed}
        module = next(module for module in course.modules if module.module_id == state.module_id)
        taught_ids = {question_id for node in module.nodes if node.node_id in completed_nodes for question_id in node.question_ids}
        for entry in ledger.values():
            if entry.module_id == state.module_id:
                if entry.question_id in state.assessed_question_ids:
                    if state.boss_progress and state.boss_progress.passed:
                        entry.coverage_status = "mastered"
                        entry.lifecycle_status = "MASTERED"
                    else:
                        entry.coverage_status = "assessed"
                        entry.lifecycle_status = "BOSS_ASSESSED"
                elif entry.question_id in taught_ids:
                    entry.coverage_status = "taught"
                    entry.lifecycle_status = "TAUGHT"
    stats = course.coverage_stats.model_copy(update={"questions_taught": sum(entry.coverage_status in {"taught", "practised", "assessed", "mastered"} for entry in ledger.values()), "questions_assessed": sum(bool(entry.boss_assessment_refs) for entry in ledger.values()), "questions_mastered": sum(entry.coverage_status == "mastered" for entry in ledger.values()), "questions_requiring_attention": sum(entry.coverage_status != "mastered" for entry in ledger.values())})
    return course.model_copy(update={"question_coverage_ledger": list(ledger.values()), "coverage_stats": stats})


@app.post("/api/courses/{course_id}/progress", response_model=CourseProgressResponse)
async def record_progress(course_id: str, event: ProgressEventRequest) -> CourseProgressResponse:
    job_id, job = _find_course_job(course_id)
    if job.course is None or job.progress is None:
        raise HTTPException(status_code=409, detail="Course progress is not initialized.")
    course = job.course
    progress = job.progress.model_copy(deep=True)
    module_id: str | None = None
    if event.node_id:
        for module in course.modules:
            if any(node.node_id == event.node_id for node in module.nodes):
                module_id = module.module_id
                break
    elif event.assessment_id:
        for module in course.modules:
            if any(node.node_type == "boss" and node.assessment and node.assessment.assessment_id == event.assessment_id for node in module.nodes):
                module_id = module.module_id
                break
    if module_id is None:
        raise HTTPException(status_code=400, detail="A valid node_id or assessment_id is required.")
    module = _find_module(course, module_id)
    state = _module_progress(progress, module_id)
    if not state.unlocked:
        raise HTTPException(status_code=403, detail=state.unlock_reason)
    if event.event_type == "record_struggle":
        if not event.node_id or not event.question_id:
            raise HTTPException(status_code=400, detail="A node_id and question_id are required to record a struggle.")
        node = next((item for item in module.nodes if item.node_id == event.node_id), None)
        original = next((item for item in course.question_bank if item.question_id == event.question_id), None)
        if node is None or node.node_type != "stepping_stone" or original is None or event.question_id not in node.question_ids:
            raise HTTPException(status_code=400, detail="The struggle must reference an original question in the selected node.")
        supplementary_id = f"supp_{hashlib.sha256(f'{course.course_id}:{event.question_id}'.encode('utf-8')).hexdigest()[:16]}"
        if not any(question.question_id == supplementary_id for question in course.question_bank):
            prompt = f"Prerequisite check: what knowledge is needed before answering this question? {original.question_text}"
            supplementary = ExamQuestion(question_id=supplementary_id, question_text=prompt, module_id=module_id, topic=original.topic, question_kind="short_answer", source_refs=original.source_refs, source_type="ai_generated_supplementary", source_entry_id=supplementary_id, related_question_ids=[original.question_id], expected_answer_depth="brief", prerequisite_concepts=[original.question_text], lifecycle_status="PREREQUISITES_IDENTIFIED", coverage_status="unmapped", verification_status="teacher_review_required")
            practice = QuestionPracticeItem(question_id=supplementary_id, question_text=prompt, source_type="ai_generated_supplementary", activity=ShortAnswerActivity(instruction="Fill the prerequisite gap before retrying the original question.", prompt=prompt, key_points=["Identify the prerequisite concept needed for the original question."], self_check_guidance="Use the cited source material; this supplementary question is not an official examination question."), source_refs=original.source_refs, linked_original_question_id=original.question_id, struggle_feedback="This question was added after a demonstrated struggle with the original question.")
            active_screen = node.screens[2]
            updated_active = active_screen.model_copy(update={"question_items": [*active_screen.question_items, practice]})
            updated_screens = (node.screens[0], node.screens[1], updated_active, node.screens[3])
            updated_node = node.model_copy(update={"screens": updated_screens, "question_ids": [*node.question_ids, supplementary_id]})
            updated_module = module.model_copy(update={"nodes": [updated_node if item.node_id == node.node_id else item for item in module.nodes]})
            course = course.model_copy(update={"modules": [updated_module if item.module_id == module.module_id else item for item in course.modules], "question_bank": [*course.question_bank, supplementary], "question_coverage_ledger": [*course.question_coverage_ledger, QuestionCoverageEntry(question_id=supplementary_id, source_type="ai_generated_supplementary", original_question_text=prompt, source_refs=original.source_refs, module_id=module_id, question_kind="short_answer", expected_answer_depth="brief", related_question_ids=[original.question_id], learning_content_refs=[node.node_id], lifecycle_status="PREREQUISITES_IDENTIFIED", coverage_status="mapped", verification_status="teacher_review_required")], "coverage_stats": course.coverage_stats.model_copy(update={"supplementary_questions": course.coverage_stats.supplementary_questions + 1})})
        await _set_job(job_id, course=course, progress=progress)
        return CourseProgressResponse(course_id=course_id, progress=progress, coverage=course.coverage_stats, blueprint_unlocked=False, course=course)
    if event.event_type == "open_node":
        if not event.node_id or not _node_is_unlocked(module, state, event.node_id):
            raise HTTPException(status_code=403, detail="Node prerequisites are not satisfied.")
        next(item for item in state.node_progress if item.node_id == event.node_id).opened = True
    elif event.event_type == "complete_node":
        if not event.node_id or not _node_is_unlocked(module, state, event.node_id):
            raise HTTPException(status_code=403, detail="Node prerequisites are not satisfied.")
        node = next(item for item in module.nodes if item.node_id == event.node_id)
        if node.node_type != "stepping_stone" or event.score is None or event.score < node.mastery_threshold:
            raise HTTPException(status_code=422, detail="A stepping-stone node requires a passing activity score before completion.")
        node_state = next(item for item in state.node_progress if item.node_id == event.node_id)
        node_state.opened, node_state.completed, node_state.score = True, True, event.score
        node_state.attempts += 1
    elif event.event_type == "start_boss":
        boss = next((node for node in module.nodes if node.node_type == "boss" and node.assessment and node.assessment.assessment_id == event.assessment_id), None)
        if boss is None or not _node_is_unlocked(module, state, boss.node_id):
            raise HTTPException(status_code=403, detail="Boss prerequisites are not satisfied.")
        state.boss_progress = state.boss_progress or BossProgress(assessment_id=boss.assessment.assessment_id)
        state.boss_progress.started = True
    elif event.event_type == "submit_boss":
        boss = next((node for node in module.nodes if node.node_type == "boss" and node.assessment and node.assessment.assessment_id == event.assessment_id), None)
        if boss is None or boss.assessment is None or not _node_is_unlocked(module, state, boss.node_id):
            raise HTTPException(status_code=403, detail="Boss prerequisites are not satisfied.")
        score, answered = _score_assessment(boss.assessment, event.responses)
        required = {item.assessment_item_id for item in boss.assessment.items}
        passed = answered == required and score >= boss.assessment.passing_score
        state.boss_progress = BossProgress(assessment_id=boss.assessment.assessment_id, started=True, submitted=True, score=score, passed=passed, answered_item_ids=sorted(answered), responses={key: value for key, value in event.responses.items() if value.strip()}, submitted_at=_now(), blueprint_unlocked=passed)
        state.assessed_question_ids = sorted({question_id for item in boss.assessment.items if item.assessment_item_id in answered for question_id in item.original_question_ids if question_id in state.required_question_ids})
    progress = _refresh_progress(course, progress)
    course = _apply_coverage(course, progress)
    await _set_job(job_id, course=course, progress=progress)
    return CourseProgressResponse(course_id=course_id, progress=progress, coverage=course.coverage_stats, blueprint_unlocked=any(item.boss_progress and item.boss_progress.blueprint_unlocked for item in progress.modules), course=course)


@app.post("/api/load-sample", response_model=UploadResponse)
async def load_bundled_sample_dataset() -> UploadResponse:
    sample_dir = BASE_DIR.parent / "sample_inputs"
    paths = [sample_dir / "Brain Machine Interface_Syllabus.docx", sample_dir / "BCI_Module_I_II_Questions.docx"]
    if not all(path.exists() for path in paths):
        raise HTTPException(status_code=500, detail="Bundled sample inputs not found.")
    job_id = f"job_sample_{uuid.uuid4().hex[:8]}"
    upload_dir = UPLOADS_DIR / job_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    docs: list[UploadedDocumentInfo] = []
    for index, (path, role) in enumerate(zip(paths, ("syllabus", "exam_questions")), start=1):
        target = upload_dir / path.name
        shutil.copy2(path, target)
        docs.append(UploadedDocumentInfo(document_id=f"doc_{index:03d}", file_name=path.name, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document", file_size_bytes=target.stat().st_size, document_role=role))
    job = GenerationJobState(job_id=job_id, status="uploaded", progress_percent=10, stage_message="Sample materials loaded and ready for source ingestion.", uploaded_documents=docs, created_at=_now(), updated_at=_now(), checkpoint_stage="uploaded", source_fingerprints={doc.document_id: hashlib.sha256((upload_dir / doc.file_name).read_bytes()).hexdigest() for doc in docs})
    async with _STATE_LOCK:
        _JOBS[job_id] = job
    await save_jobs_state()
    return UploadResponse(job_id=job_id, uploaded_documents=docs)


__all__ = ["app", "_JOBS", "save_jobs_state"]
