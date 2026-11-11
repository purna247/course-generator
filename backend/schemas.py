"""Pydantic contracts for the subject-agnostic gamified course prototype.

The models in this file define the backend/frontend JSON boundary. Activity
rendering is selected by each activity's ``type`` discriminator, never by a
course or subject name.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Any, Literal, Union

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    StringConstraints,
    field_validator,
    model_validator,
)


# ---------------------------------------------------------------------------
# Shared constrained types and base model
# ---------------------------------------------------------------------------

NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
ShortText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=160),
]
Identifier = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=80,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$",
    ),
]


class ContractModel(BaseModel):
    """Base for API and LLM contracts; unexpected fields are safely ignored."""

    model_config = ConfigDict(
        extra="ignore",
        str_strip_whitespace=True,
        validate_assignment=True,
    )


# ---------------------------------------------------------------------------
# Source provenance and examination input models
# ---------------------------------------------------------------------------


class SourceReference(ContractModel):
    """Location in an uploaded document that supports generated content."""

    document_id: Identifier | None = None
    document_name: NonEmptyText
    page_number: int | None = Field(default=None, ge=1)
    slide_number: int | None = Field(default=None, ge=1)
    section_title: ShortText | None = None
    excerpt: str | None = Field(default=None, max_length=1600)
    source_hash: str | None = Field(default=None, max_length=128)


class MediaAsset(ContractModel):
    """A persisted image or diagram extracted from uploaded source material."""

    asset_id: Identifier
    document_id: Identifier | None = None
    original_filename: NonEmptyText
    media_type: NonEmptyText
    storage_path: NonEmptyText
    source_page: int | None = Field(default=None, ge=1)
    source_slide: int | None = Field(default=None, ge=1)
    asset_kind: Literal["image", "diagram", "chart", "unknown"] = "unknown"
    surrounding_text: str | None = Field(default=None, max_length=3000)
    caption: str | None = Field(default=None, max_length=1000)
    extracted_labels: list[NonEmptyText] = Field(default_factory=list, max_length=100)
    module_id: Identifier | None = None
    topic_id: Identifier | None = None
    content_hash: str = Field(min_length=8, max_length=128)


class ExamPattern(ContractModel):
    """Configurable assessment structure; 2/5/10 marks are only defaults."""

    name: ShortText = "University semester examination"
    question_mark_values: list[int] = Field(default_factory=lambda: [2, 5, 10])
    notes: str | None = Field(default=None, max_length=1200)

    @field_validator("question_mark_values")
    @classmethod
    def validate_mark_values(cls, values: list[int]) -> list[int]:
        if any(value <= 0 for value in values):
            raise ValueError("Question mark values must be positive integers.")
        if len(values) != len(set(values)):
            raise ValueError("Question mark values must not contain duplicates.")
        return sorted(values)


class ExamQuestion(ContractModel):
    """A question extracted from teacher-provided examination material."""

    question_id: Identifier
    question_text: NonEmptyText
    marks: int | None = Field(default=None, ge=1)
    question_number: str | None = Field(default=None, max_length=40)
    module_id: Identifier | None = None
    topic: ShortText | None = None
    question_kind: Literal[
        "short_answer", "long_answer", "problem", "case_study", "unknown"
    ] = "unknown"
    source_refs: list[SourceReference] = Field(default_factory=list)
    source_type: Literal["teacher_provided", "ai_generated_supplementary"] = "teacher_provided"
    source_entry_id: Identifier | None = None
    duplicate_cluster_id: Identifier | None = None
    similarity_kind: Literal["none", "exact_duplicate", "near_duplicate", "related"] = "none"
    related_question_ids: list[Identifier] = Field(default_factory=list, max_length=100)
    expected_answer_depth: Literal["brief", "moderate", "extended", "unknown"] = "unknown"
    related_concepts: list[NonEmptyText] = Field(default_factory=list, max_length=30)
    learning_objectives: list[NonEmptyText] = Field(default_factory=list, max_length=20)
    prerequisite_concepts: list[NonEmptyText] = Field(default_factory=list, max_length=30)
    lifecycle_status: Literal[
        "IMPORTED",
        "CLASSIFIED",
        "PREREQUISITES_IDENTIFIED",
        "TAUGHT",
        "PRACTISED",
        "BOSS_ASSESSED",
        "MASTERED",
    ] = "IMPORTED"
    learning_content_refs: list[Identifier] = Field(default_factory=list, max_length=100)
    practice_refs: list[Identifier] = Field(default_factory=list, max_length=100)
    boss_assessment_refs: list[Identifier] = Field(default_factory=list, max_length=100)
    verification_status: Literal["unreviewed", "single_model_reviewed", "independent_reviewed", "teacher_review_required"] = "unreviewed"
    coverage_status: Literal["unmapped", "mapped", "taught", "practised", "assessed", "mastered"] = "unmapped"
    attempts: int = Field(default=0, ge=0)
    best_score: float = Field(default=0.0, ge=0.0, le=1.0)


class QuestionCoverageEntry(ContractModel):
    """Persistent ledger row; original questions are never discarded."""

    question_id: Identifier
    source_type: Literal["teacher_provided", "ai_generated_supplementary"]
    original_question_text: NonEmptyText
    source_refs: list[SourceReference] = Field(default_factory=list)
    module_id: Identifier | None = None
    marks_as_supplied: int | None = Field(default=None, ge=1)
    question_number: str | None = Field(default=None, max_length=40)
    question_kind: Literal["short_answer", "long_answer", "problem", "case_study", "unknown"] = "unknown"
    expected_answer_depth: Literal["brief", "moderate", "extended", "unknown"] = "unknown"
    related_concepts: list[NonEmptyText] = Field(default_factory=list, max_length=30)
    learning_objectives: list[NonEmptyText] = Field(default_factory=list, max_length=20)
    prerequisite_concepts: list[NonEmptyText] = Field(default_factory=list, max_length=30)
    related_question_ids: list[Identifier] = Field(default_factory=list, max_length=100)
    duplicate_cluster_id: Identifier | None = None
    similarity_kind: Literal["none", "exact_duplicate", "near_duplicate", "related"] = "none"
    learning_content_refs: list[Identifier] = Field(default_factory=list, max_length=100)
    practice_question_refs: list[Identifier] = Field(default_factory=list, max_length=100)
    boss_assessment_refs: list[Identifier] = Field(default_factory=list, max_length=100)
    attempts: int = Field(default=0, ge=0)
    best_score: float = Field(default=0.0, ge=0.0, le=1.0)
    verification_status: Literal["unreviewed", "single_model_reviewed", "independent_reviewed", "teacher_review_required"] = "unreviewed"
    lifecycle_status: Literal[
        "IMPORTED", "CLASSIFIED", "PREREQUISITES_IDENTIFIED", "TAUGHT",
        "PRACTISED", "BOSS_ASSESSED", "MASTERED"
    ] = "IMPORTED"
    coverage_status: Literal["unmapped", "mapped", "taught", "practised", "assessed", "mastered"] = "unmapped"


class CoverageStats(ContractModel):
    total_original_entries: int = Field(default=0, ge=0)
    exact_duplicates: int = Field(default=0, ge=0)
    near_duplicates: int = Field(default=0, ge=0)
    related_clusters: int = Field(default=0, ge=0)
    unique_examination_questions: int = Field(default=0, ge=0)
    questions_mapped: int = Field(default=0, ge=0)
    questions_taught: int = Field(default=0, ge=0)
    questions_practised: int = Field(default=0, ge=0)
    questions_assessed: int = Field(default=0, ge=0)
    questions_mastered: int = Field(default=0, ge=0)
    questions_requiring_attention: int = Field(default=0, ge=0)
    supplementary_questions: int = Field(default=0, ge=0)


class GenerationTelemetry(ContractModel):
    provider: NonEmptyText
    requested_model_id: NonEmptyText
    actual_model_id: str | None = None
    task_type: NonEmptyText
    prompt_version: NonEmptyText
    schema_version: NonEmptyText
    source_document_ids: list[Identifier] = Field(default_factory=list)
    source_content_hashes: list[str] = Field(default_factory=list, max_length=100)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    token_usage: dict[str, int] | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    fallback_history: list[NonEmptyText] = Field(default_factory=list, max_length=30)
    verification_result: Literal["awaiting_review", "single_model_reviewed", "independent_reviewed", "teacher_review_required"] = "awaiting_review"


class LessonBlock(ContractModel):
    """Flexible lesson content rendered by block_type, with generic payload."""

    block_id: Identifier
    block_type: ShortText
    heading: NonEmptyText
    content: str = Field(default="", max_length=12_000)
    activity: Activity | None = None
    source_refs: list[SourceReference] = Field(default_factory=list)
    media_asset_ids: list[Identifier] = Field(default_factory=list, max_length=30)
    linked_question_ids: list[Identifier] = Field(default_factory=list, max_length=100)
    metadata: dict[str, str] = Field(default_factory=dict, max_length=30)


class UploadedDocumentInfo(ContractModel):
    """Metadata for a document received by the upload endpoint."""

    document_id: Identifier
    file_name: NonEmptyText
    media_type: NonEmptyText
    file_size_bytes: int = Field(ge=0)
    document_role: Literal[
        "syllabus", "exam_questions", "lecture_material", "other"
    ] = "other"


class ExtractedTopic(ContractModel):
    topic_id: Identifier
    title: NonEmptyText
    description: str | None = Field(default=None, max_length=2000)
    learning_outcomes: list[NonEmptyText] = Field(default_factory=list)
    source_refs: list[SourceReference] = Field(default_factory=list)


class ExtractedModule(ContractModel):
    module_id: Identifier
    module_number: int = Field(ge=1)
    title: NonEmptyText
    overview: str | None = Field(default=None, max_length=3000)
    topics: list[ExtractedTopic] = Field(default_factory=list)
    learning_objectives: list[NonEmptyText] = Field(default_factory=list)
    source_refs: list[SourceReference] = Field(default_factory=list)


class PreprocessedCourseContext(ContractModel):
    """Clean local-parser output passed to course-generation agents."""

    course_title: ShortText | None = None
    subject_area: ShortText | None = None
    exam_pattern: ExamPattern = Field(default_factory=ExamPattern)
    documents: list[UploadedDocumentInfo] = Field(default_factory=list)
    modules: list[ExtractedModule] = Field(default_factory=list)
    exam_questions: list[ExamQuestion] = Field(default_factory=list)
    question_coverage_ledger: list[QuestionCoverageEntry] = Field(default_factory=list, max_length=5000)
    media_assets: list[MediaAsset] = Field(default_factory=list, max_length=5000)
    lecture_content: str = Field(default="", max_length=250_000)
    extraction_warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_unique_source_ids(self) -> "PreprocessedCourseContext":
        module_ids = [module.module_id for module in self.modules]
        if len(module_ids) != len(set(module_ids)):
            raise ValueError("Extracted module IDs must be unique.")

        question_ids = [question.question_id for question in self.exam_questions]
        if len(question_ids) != len(set(question_ids)):
            raise ValueError("Exam question IDs must be unique.")
        ledger_ids = [entry.question_id for entry in self.question_coverage_ledger]
        if ledger_ids and set(ledger_ids) != set(question_ids):
            raise ValueError("Preprocessed coverage ledger must retain every extracted question.")
        return self


# ---------------------------------------------------------------------------
# Reusable activity payloads (discriminated by JSON field: `type`)
# ---------------------------------------------------------------------------


class FillBlankField(ContractModel):
    blank_id: Identifier
    accepted_answers: list[NonEmptyText] = Field(min_length=1)
    explanation: str | None = Field(default=None, max_length=1000)
    hint: str | None = Field(default=None, max_length=1000)

    @field_validator("accepted_answers", mode="before")
    @classmethod
    def validate_unique_answers(cls, values: Any) -> list[str]:
        if isinstance(values, list):
            seen = set()
            unique = []
            for v in values:
                if isinstance(v, str):
                    cleaned = v.strip()
                    cf = cleaned.casefold()
                    if cf and cf not in seen:
                        seen.add(cf)
                        unique.append(cleaned)
            return unique
        return values


class FillBlankActivity(ContractModel):
    type: Literal["fill_blank"] = "fill_blank"
    instruction: NonEmptyText
    template: NonEmptyText = Field(
        description="Use [blank_id] or {{blank_id}} markers for each missing answer."
    )
    blanks: list[FillBlankField] = Field(min_length=1, max_length=20)
    word_bank: list[NonEmptyText] = Field(min_length=1, max_length=60)
    shuffle_word_bank: bool = True

    @model_validator(mode="before")
    @classmethod
    def auto_repair_word_bank(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # Map common alternative field names and remove the extra keys
            if "template" not in data:
                if "sentence" in data:
                    data["template"] = data.pop("sentence")
                elif "text" in data:
                    data["template"] = data.pop("text")
            else:
                data.pop("sentence", None)
                data.pop("text", None)

            if "blanks" not in data and "fields" in data:
                data["blanks"] = data.pop("fields")
            else:
                data.pop("fields", None)

            if "instruction" not in data:
                if "instructions" in data:
                    data["instruction"] = data.pop("instructions")
                elif "title" in data:
                    data["instruction"] = data.pop("title")
            else:
                data.pop("instructions", None)
                data.pop("title", None)

            # In case title is still present as an extra key, remove it
            data.pop("title", None)

            blanks = data.get("blanks", [])
            word_bank = list(data.get("word_bank", []))
            bank_lower = {w.casefold() for w in word_bank if isinstance(w, str)}
            for b in blanks:
                if isinstance(b, dict):
                    for ans in b.get("accepted_answers", []):
                        if isinstance(ans, str) and ans.casefold() not in bank_lower:
                            word_bank.append(ans)
                            bank_lower.add(ans.casefold())
            data["word_bank"] = word_bank
        return data

    @model_validator(mode="after")
    def validate_template_markers(self) -> "FillBlankActivity":
        blank_ids = [blank.blank_id for blank in self.blanks]
        if len(blank_ids) != len(set(blank_ids)):
            raise ValueError("Fill-in-the-blank IDs must be unique.")
        for blank_id in blank_ids:
            marker_curly = "{{" + blank_id + "}}"
            marker_square = "[" + blank_id + "]"
            count_curly = self.template.count(marker_curly)
            count_square = self.template.count(marker_square)
            if (count_curly + count_square) != 1:
                raise ValueError(
                    f"Template must contain exactly one {marker_square} or {marker_curly} placeholder."
                )

        # Verify word bank includes at least one accepted answer for each blank
        bank_casefolded = {w.casefold() for w in self.word_bank}
        for blank in self.blanks:
            if not any(ans.casefold() in bank_casefolded for ans in blank.accepted_answers):
                raise ValueError(
                    f"Word bank must include a valid answer for blank '{blank.blank_id}'."
                )
        return self


class MatchingPair(ContractModel):
    pair_id: Identifier
    left_text: NonEmptyText
    right_text: NonEmptyText
    explanation: str | None = Field(default=None, max_length=1000)


class MatchingPairsActivity(ContractModel):
    type: Literal["matching_pairs"] = "matching_pairs"
    instruction: NonEmptyText
    pairs: list[MatchingPair] = Field(min_length=2, max_length=30)
    shuffle_right_column: bool = True

    @model_validator(mode="after")
    def validate_pairs(self) -> "MatchingPairsActivity":
        pair_ids = [pair.pair_id for pair in self.pairs]
        if len(pair_ids) != len(set(pair_ids)):
            raise ValueError("Matching pair IDs must be unique.")
        left_values = [pair.left_text.casefold() for pair in self.pairs]
        right_values = [pair.right_text.casefold() for pair in self.pairs]
        if len(left_values) != len(set(left_values)):
            raise ValueError("Matching left-side values must be unique.")
        if len(right_values) != len(set(right_values)):
            raise ValueError("Matching right-side values must be unique.")
        return self


class OrderingItem(ContractModel):
    item_id: Identifier
    label: NonEmptyText
    detail: str | None = Field(default=None, max_length=1000)


class OrderingActivity(ContractModel):
    type: Literal["ordering"] = "ordering"
    instruction: NonEmptyText
    items: list[OrderingItem] = Field(min_length=2, max_length=30)
    correct_order: list[Identifier] = Field(min_length=2, max_length=30)
    explanation: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def validate_order(self) -> "OrderingActivity":
        item_ids = [item.item_id for item in self.items]
        if len(item_ids) != len(set(item_ids)):
            raise ValueError("Ordering item IDs must be unique.")
        if len(self.correct_order) != len(set(self.correct_order)):
            raise ValueError("Correct order must not repeat item IDs.")
        if set(self.correct_order) != set(item_ids):
            raise ValueError("Correct order must contain every item ID exactly once.")
        return self


class ActivityOption(ContractModel):
    option_id: Identifier
    text: NonEmptyText
    feedback: str | None = Field(default=None, max_length=1000)
    misconception_tag: str | None = Field(default=None, max_length=100)


class MCQActivity(ContractModel):
    type: Literal["mcq"] = "mcq"
    instruction: NonEmptyText
    question: NonEmptyText
    options: list[ActivityOption] = Field(min_length=2, max_length=6)
    correct_option_id: Identifier
    explanation: NonEmptyText

    @model_validator(mode="after")
    def validate_options(self) -> "MCQActivity":
        option_ids = [option.option_id for option in self.options]
        if len(option_ids) != len(set(option_ids)):
            raise ValueError("MCQ option IDs must be unique.")
        if self.correct_option_id not in option_ids:
            raise ValueError("correct_option_id must identify one supplied option.")
        return self


class FormulaBlank(ContractModel):
    blank_id: Identifier
    accepted_answers: list[NonEmptyText] = Field(min_length=1)
    unit: str | None = Field(default=None, max_length=50)


class FormulaCompletionActivity(ContractModel):
    type: Literal["formula_completion"] = "formula_completion"
    instruction: NonEmptyText
    expression_template: NonEmptyText = Field(
        description="Use {{blank_id}} markers for missing expression parts."
    )
    blanks: list[FormulaBlank] = Field(min_length=1, max_length=15)
    symbol_legend: list[NonEmptyText] = Field(default_factory=list, max_length=30)
    explanation: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def validate_formula_markers(self) -> "FormulaCompletionActivity":
        blank_ids = [blank.blank_id for blank in self.blanks]
        if len(blank_ids) != len(set(blank_ids)):
            raise ValueError("Formula blank IDs must be unique.")
        for blank_id in blank_ids:
            marker = "{{" + blank_id + "}}"
            if self.expression_template.count(marker) != 1:
                raise ValueError(
                    f"Expression template must contain exactly one {marker} marker."
                )
        return self


class CodeTraceStep(ContractModel):
    step_number: int = Field(ge=1)
    prompt: NonEmptyText
    expected_result: NonEmptyText
    explanation: str | None = Field(default=None, max_length=1200)


class CodeTracingActivity(ContractModel):
    type: Literal["code_tracing"] = "code_tracing"
    instruction: NonEmptyText
    language: ShortText | None = None
    code: NonEmptyText = Field(max_length=20_000)
    trace_steps: list[CodeTraceStep] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def validate_step_numbers(self) -> "CodeTracingActivity":
        numbers = [step.step_number for step in self.trace_steps]
        if len(numbers) != len(set(numbers)):
            raise ValueError("Code-tracing step numbers must be unique.")
        if numbers != sorted(numbers):
            raise ValueError("Code-tracing steps must be in ascending order.")
        return self


class DiagramTarget(ContractModel):
    target_id: Identifier
    placeholder: NonEmptyText
    hint: str | None = Field(default=None, max_length=500)


class DiagramMapping(ContractModel):
    target_id: Identifier
    label_id: Identifier


class DiagramLabelingActivity(ContractModel):
    type: Literal["diagram_labeling"] = "diagram_labeling"
    instruction: NonEmptyText
    diagram_description: NonEmptyText
    image_url: HttpUrl | None = None
    targets: list[DiagramTarget] = Field(min_length=1, max_length=30)
    label_bank: list[ActivityOption] = Field(min_length=1, max_length=40)
    correct_mapping: list[DiagramMapping] = Field(min_length=1, max_length=30)
    explanation: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def validate_diagram_mapping(self) -> "DiagramLabelingActivity":
        target_ids = [target.target_id for target in self.targets]
        label_ids = [label.option_id for label in self.label_bank]
        mapped_targets = [mapping.target_id for mapping in self.correct_mapping]
        mapped_labels = [mapping.label_id for mapping in self.correct_mapping]
        if len(target_ids) != len(set(target_ids)):
            raise ValueError("Diagram target IDs must be unique.")
        if len(label_ids) != len(set(label_ids)):
            raise ValueError("Diagram label IDs must be unique.")
        if len(mapped_targets) != len(set(mapped_targets)):
            raise ValueError("Each diagram target must be mapped once.")
        if set(mapped_targets) != set(target_ids):
            raise ValueError("Every diagram target must have one correct mapping.")
        if not set(mapped_labels).issubset(set(label_ids)):
            raise ValueError("Diagram mappings must use labels from label_bank.")
        return self


class NumericalProblemActivity(ContractModel):
    type: Literal["numerical_problem"] = "numerical_problem"
    instruction: NonEmptyText
    problem_statement: NonEmptyText
    expected_answer: NonEmptyText
    accepted_alternatives: list[NonEmptyText] = Field(default_factory=list)
    unit: str | None = Field(default=None, max_length=60)
    tolerance: float | None = Field(default=None, ge=0)
    solution_steps: list[NonEmptyText] = Field(min_length=1, max_length=30)
    final_explanation: str | None = Field(default=None, max_length=2000)


class ClassificationCategory(ContractModel):
    category_id: Identifier
    label: NonEmptyText
    description: str | None = Field(default=None, max_length=800)


class ClassificationItem(ContractModel):
    item_id: Identifier
    text: NonEmptyText
    correct_category_id: Identifier
    explanation: str | None = Field(default=None, max_length=1000)


class ClassificationActivity(ContractModel):
    type: Literal["classification"] = "classification"
    instruction: NonEmptyText
    categories: list[ClassificationCategory] = Field(min_length=2, max_length=20)
    items: list[ClassificationItem] = Field(min_length=2, max_length=40)

    @model_validator(mode="after")
    def validate_classification(self) -> "ClassificationActivity":
        category_ids = [category.category_id for category in self.categories]
        item_ids = [item.item_id for item in self.items]
        if len(category_ids) != len(set(category_ids)):
            raise ValueError("Classification category IDs must be unique.")
        if len(item_ids) != len(set(item_ids)):
            raise ValueError("Classification item IDs must be unique.")
        if any(item.correct_category_id not in category_ids for item in self.items):
            raise ValueError("Every item must reference an existing category.")
        return self


class KeyPointsCheckOption(ContractModel):
    point_id: Identifier
    text: NonEmptyText
    is_essential: bool
    explanation: str | None = Field(default=None, max_length=1000)


class KeyPointsCheckActivity(ContractModel):
    type: Literal["key_points_check"] = "key_points_check"
    instruction: NonEmptyText
    question: NonEmptyText
    options: list[KeyPointsCheckOption] = Field(min_length=3, max_length=15)
    min_required: int = Field(default=1, ge=1)
    explanation: str | None = Field(default=None, max_length=2000)


class ShortAnswerActivity(ContractModel):
    type: Literal["short_answer"] = "short_answer"
    instruction: NonEmptyText
    prompt: NonEmptyText
    key_points: list[NonEmptyText] = Field(min_length=1, max_length=20)
    sample_response: str | None = Field(default=None, max_length=4000)
    self_check_guidance: NonEmptyText


class CaseAnalysisQuestion(ContractModel):
    question_id: Identifier
    prompt: NonEmptyText
    expected_considerations: list[NonEmptyText] = Field(min_length=1, max_length=15)


class CaseAnalysisActivity(ContractModel):
    type: Literal["case_analysis"] = "case_analysis"
    instruction: NonEmptyText
    case_text: NonEmptyText = Field(max_length=12_000)
    questions: list[CaseAnalysisQuestion] = Field(min_length=1, max_length=10)
    overall_feedback: str | None = Field(default=None, max_length=2500)


Activity = Annotated[
    Union[
        FillBlankActivity,
        MatchingPairsActivity,
        OrderingActivity,
        MCQActivity,
        FormulaCompletionActivity,
        CodeTracingActivity,
        DiagramLabelingActivity,
        NumericalProblemActivity,
        ClassificationActivity,
        KeyPointsCheckActivity,
        ShortAnswerActivity,
        CaseAnalysisActivity,
    ],
    Field(discriminator="type"),
]


# ---------------------------------------------------------------------------
# Four-screen Stepping-Stone node contract
# ---------------------------------------------------------------------------


class ConceptExample(ContractModel):
    title: ShortText
    explanation: NonEmptyText


class VisualAid(ContractModel):
    """Optional generic visual description; no subject-specific UI behaviour."""

    kind: Literal["diagram", "sequence", "table", "image", "other"]
    title: ShortText | None = None
    description: NonEmptyText
    image_url: HttpUrl | None = None
    alt_text: str | None = Field(default=None, max_length=500)


class ConceptHookScreen(ContractModel):
    screen_type: Literal["concept_hook"] = "concept_hook"
    heading: NonEmptyText
    explanation: NonEmptyText = Field(max_length=5000)
    analogy: str | None = Field(default=None, max_length=2000)
    examples: list[ConceptExample] = Field(default_factory=list, max_length=8)
    visual_aid: VisualAid | None = None
    source_refs: list[SourceReference] = Field(default_factory=list)


class ExamRubricPoint(ContractModel):
    keyword: NonEmptyText
    explanation: NonEmptyText
    importance: Literal["essential", "supporting"] = "essential"


class ExamRubricScreen(ContractModel):
    screen_type: Literal["exam_rubric"] = "exam_rubric"
    heading: NonEmptyText
    purpose: NonEmptyText
    points: list[ExamRubricPoint] = Field(min_length=1, max_length=25)
    suggested_answer_structure: list[NonEmptyText] = Field(
        default_factory=list, max_length=20
    )
    linked_question_ids: list[Identifier] = Field(default_factory=list, max_length=100)
    source_refs: list[SourceReference] = Field(default_factory=list)


class QuestionPracticeItem(ContractModel):
    """One important examination question or explicitly generated prerequisite."""

    question_id: Identifier
    question_text: NonEmptyText
    source_type: Literal["teacher_provided", "ai_generated_supplementary"] = "teacher_provided"
    marks: int | None = Field(default=None, ge=1)
    activity: Activity
    source_refs: list[SourceReference] = Field(default_factory=list)
    linked_original_question_id: Identifier | None = None
    struggle_feedback: str | None = Field(default=None, max_length=1200)


class ActiveRecallScreen(ContractModel):
    screen_type: Literal["active_recall"] = "active_recall"
    heading: NonEmptyText
    question_items: list[QuestionPracticeItem] = Field(default_factory=list, max_length=500)
    # Backward-compatible single activity for legacy generated payloads.
    activity: Activity | None = None

    @model_validator(mode="after")
    def validate_question_items(self) -> "ActiveRecallScreen":
        if not self.question_items and self.activity is None:
            self.activity = MCQActivity(
                instruction="Recall the core concept for this topic:",
                question=self.heading or "Topic Recall",
                options=[
                    ActivityOption(option_id="opt_1", text="Primary Concept"),
                    ActivityOption(option_id="opt_2", text="Secondary Concept"),
                ],
                correct_option_id="opt_1",
                explanation="Grounded in topic materials.",
            )
        return self


class AssessmentItem(ContractModel):
    """One final-assessment item mapped to at least one original question."""

    assessment_item_id: Identifier
    item_type: Literal[
        "mcq", "fill_blank", "matching_pairs", "ordering", "classification",
        "diagram_labeling", "formula_completion", "numerical_problem",
        "short_answer", "long_answer", "case_analysis"
    ]
    prompt: NonEmptyText
    marks: int | None = Field(default=None, ge=1)
    original_question_ids: list[Identifier] = Field(min_length=1, max_length=100)
    activity: Activity | None = None
    rubric_points: list[NonEmptyText] = Field(default_factory=list, max_length=30)
    correct_answer: str | None = Field(default=None, max_length=4000)
    accepted_answers: list[NonEmptyText] = Field(default_factory=list, max_length=30)
    feedback: str | None = Field(default=None, max_length=3000)
    source_refs: list[SourceReference] = Field(default_factory=list)


class BossAssessment(ContractModel):
    """A resumable, mixed-format module assessment."""

    assessment_id: Identifier
    sections: list[NonEmptyText] = Field(min_length=1, max_length=10)
    items: list[AssessmentItem] = Field(min_length=1, max_length=1000)
    question_to_item: dict[Identifier, Identifier] = Field(default_factory=dict)
    passing_score: float = Field(default=0.7, ge=0.0, le=1.0)
    require_all_items: bool = True
    source_refs: list[SourceReference] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_mappings(self) -> "BossAssessment":
        item_ids = {item.assessment_item_id for item in self.items}
        if len(item_ids) != len(self.items):
            raise ValueError("Boss assessment item IDs must be unique.")
        for question_id, item_id in self.question_to_item.items():
            if item_id not in item_ids:
                raise ValueError(f"Question {question_id} maps to an unknown assessment item.")
        for item in self.items:
            if not set(item.original_question_ids).issuperset(
                {question_id for question_id, item_id in self.question_to_item.items() if item_id == item.assessment_item_id}
            ):
                raise ValueError("Assessment mapping must agree with each item's original_question_ids.")
        return self


class DiagnosticOption(ContractModel):
    option_id: Identifier
    text: NonEmptyText
    misconception_tag: Identifier | None = None
    feedback: NonEmptyText


class DiagnosticMCQScreen(ContractModel):
    screen_type: Literal["diagnostic_mcq"] = "diagnostic_mcq"
    heading: NonEmptyText
    question: NonEmptyText
    options: tuple[
        DiagnosticOption,
        DiagnosticOption,
        DiagnosticOption,
        DiagnosticOption,
    ]
    correct_option_id: Identifier
    explanation: NonEmptyText

    @model_validator(mode="after")
    def validate_diagnostic_options(self) -> "DiagnosticMCQScreen":
        option_ids = [option.option_id for option in self.options]
        if len(option_ids) != 4:
            raise ValueError("A diagnostic MCQ must contain exactly four options.")
        if len(option_ids) != len(set(option_ids)):
            raise ValueError("Diagnostic MCQ option IDs must be unique.")
        if self.correct_option_id not in option_ids:
            raise ValueError("correct_option_id must identify one supplied option.")

        for option in self.options:
            if option.option_id == self.correct_option_id:
                if option.misconception_tag is not None:
                    object.__setattr__(option, "misconception_tag", None)
            elif not option.misconception_tag:
                object.__setattr__(option, "misconception_tag", f"misconception_{option.option_id}")
        return self


SteppingStoneScreens = tuple[
    ConceptHookScreen,
    ExamRubricScreen,
    ActiveRecallScreen,
    DiagnosticMCQScreen,
]


# ---------------------------------------------------------------------------
# Boss challenge and examination-answer blueprint contracts
# ---------------------------------------------------------------------------


class AnswerBlueprintSection(ContractModel):
    heading: NonEmptyText
    key_points: list[NonEmptyText] = Field(min_length=1, max_length=25)
    suggested_content: str | None = Field(default=None, max_length=4000)
    suggested_marks: int | None = Field(default=None, ge=1)
    visual_or_working_guidance: str | None = Field(default=None, max_length=2000)


class AnswerBlueprint(ContractModel):
    title: NonEmptyText
    question_text: NonEmptyText
    total_marks: int | None = Field(default=None, ge=1)
    introduction_guidance: str | None = Field(default=None, max_length=2000)
    sections: list[AnswerBlueprintSection] = Field(min_length=1, max_length=20)
    conclusion_guidance: str | None = Field(default=None, max_length=2000)
    essential_keywords: list[NonEmptyText] = Field(default_factory=list, max_length=40)
    common_omissions: list[NonEmptyText] = Field(default_factory=list, max_length=20)
    source_refs: list[SourceReference] = Field(default_factory=list)
    marking_note: str | None = Field(
        default=None,
        max_length=1200,
        description="Clarify when mark allocation is inferred or unavailable.",
    )

    @model_validator(mode="after")
    def validate_suggested_marks(self) -> "AnswerBlueprint":
        if self.total_marks is not None:
            suggested = [
                section.suggested_marks
                for section in self.sections
                if section.suggested_marks is not None
            ]
            if suggested and sum(suggested) > self.total_marks:
                raise ValueError(
                    "Section suggested_marks cannot exceed total_marks."
                )
        return self


class BossCompletionRule(ContractModel):
    minimum_score: float = Field(default=0.7, ge=0.0, le=1.0)
    attempts_allowed: int | None = Field(default=None, ge=1)
    require_all_steps: bool = False


# ---------------------------------------------------------------------------
# Course roadmap and node contracts
# ---------------------------------------------------------------------------


class NodeBase(ContractModel):
    node_id: Identifier
    title: NonEmptyText
    description: NonEmptyText
    order: int = Field(ge=1)
    estimated_minutes: int = Field(default=5, ge=1, le=180)
    learning_objectives: list[NonEmptyText] = Field(default_factory=list, max_length=12)
    unlock_after: list[Identifier] = Field(default_factory=list, max_length=10)
    question_ids: list[Identifier] = Field(default_factory=list, max_length=200)
    source_refs: list[SourceReference] = Field(default_factory=list)


class TopicQuestion(ContractModel):
    """An important examination question directly solved within a Topic Node."""

    question_id: Identifier
    prompt: NonEmptyText
    marks: int | None = Field(default=2, ge=1, le=100)
    original_question_id: Identifier | None = None
    activity: Activity
    prerequisite_gap_filler: Activity | None = None
    explanation: str | None = Field(default=None, max_length=2000)
    source_refs: list[SourceReference] = Field(default_factory=list, max_length=20)


class SteppingStoneNode(NodeBase):
    node_type: Literal["stepping_stone"] = "stepping_stone"
    topic_name: ShortText | None = None
    questions: list[TopicQuestion] = Field(default_factory=list, max_length=100)
    screens: SteppingStoneScreens | None = None
    lesson_blocks: list[LessonBlock] = Field(default_factory=list, max_length=100)
    mastery_threshold: float = Field(default=0.7, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_node_questions_or_screens(self) -> "SteppingStoneNode":
        if not self.questions and self.screens is None and not self.lesson_blocks:
            raise ValueError("A SteppingStoneNode must contain questions, screens, or lesson_blocks.")
        return self


class BossNode(NodeBase):
    node_type: Literal["boss"] = "boss"
    challenge: Activity | None = None
    assessment: BossAssessment | None = None
    completion_rule: BossCompletionRule = Field(default_factory=BossCompletionRule)
    answer_blueprint: AnswerBlueprint | None = None
    blueprint_question_ids: list[Identifier] = Field(default_factory=list, max_length=200)

    @model_validator(mode="after")
    def validate_boss_content(self) -> "BossNode":
        if self.challenge is None and self.assessment is None:
            raise ValueError("A Boss node requires a challenge or assessment.")
        if self.assessment is None and self.answer_blueprint is None:
            raise ValueError("A Boss node needs an answer blueprint when no assessment is supplied.")

        # Ensure assessment is always populated for the frontend client
        if self.assessment is None:
            prompt_text = self.answer_blueprint.question_text if self.answer_blueprint else self.title
            bp_qids = self.blueprint_question_ids or ["q_boss_1"]
            item = AssessmentItem(
                assessment_item_id=f"boss_item_{self.node_id}",
                item_type="long_answer",
                prompt=prompt_text,
                marks=10,
                original_question_ids=bp_qids,
                activity=self.challenge,
                rubric_points=[kp for sec in (self.answer_blueprint.sections if self.answer_blueprint else []) for kp in sec.key_points][:10],
            )
            self.assessment = BossAssessment(
                assessment_id=f"assess_{self.node_id}",
                sections=["Extended Answer Synthesis"],
                items=[item],
                question_to_item={qid: item.assessment_item_id for qid in bp_qids},
            )
        return self


Node = Annotated[Union[SteppingStoneNode, BossNode], Field(discriminator="node_type")]


class CourseModule(ContractModel):
    module_id: Identifier
    module_number: int = Field(ge=1)
    title: NonEmptyText
    overview: str | None = Field(default=None, max_length=4000)
    learning_objectives: list[NonEmptyText] = Field(default_factory=list, max_length=20)
    nodes: list[Node] = Field(min_length=1, max_length=1000)
    source_refs: list[SourceReference] = Field(default_factory=list)
    completion_requirements: list[NonEmptyText] = Field(
        default_factory=lambda: [
            "Complete required learning content",
            "Submit the module Boss assessment",
            "Meet the configured Boss passing score",
            "Assess all required original questions",
        ],
        max_length=20,
    )
    dependency_module_ids: list[Identifier] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def validate_node_structure(self) -> "CourseModule":
        total = len(self.nodes)

        node_ids = [node.node_id for node in self.nodes]
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("Node IDs must be unique within a module.")

        orders = [node.order for node in self.nodes]
        if len(orders) != len(set(orders)):
            raise ValueError("Node order values must be unique within a module.")
        if orders != list(range(1, total + 1)):
            raise ValueError("Node order must be sequential from 1 to the node count.")

        order_by_id = {node.node_id: node.order for node in self.nodes}
        for node in self.nodes:
            if len(node.unlock_after) != len(set(node.unlock_after)):
                raise ValueError(
                    f"Node {node.node_id} contains duplicate unlock dependencies."
                )
            for dependency_id in node.unlock_after:
                if dependency_id not in order_by_id:
                    raise ValueError(
                        f"Node {node.node_id} depends on unknown node {dependency_id}."
                    )
                if order_by_id[dependency_id] >= node.order:
                    raise ValueError(
                        f"Node {node.node_id} can only depend on an earlier node."
                    )
        return self


class GeneratedCourse(ContractModel):
    """Complete generated course returned to the frontend."""

    schema_version: Literal["1.0", "2.0"] = "2.0"
    course_id: Identifier
    title: NonEmptyText
    subject_area: ShortText | None = Field(
        default=None,
        description="Descriptive metadata only; never controls frontend rendering.",
    )
    academic_level: ShortText | None = None
    institution_name: ShortText | None = None
    exam_pattern: ExamPattern = Field(default_factory=ExamPattern)
    modules: list[CourseModule] = Field(min_length=1, max_length=100)
    question_bank: list[ExamQuestion] = Field(default_factory=list, max_length=1000)
    question_coverage_ledger: list[QuestionCoverageEntry] = Field(default_factory=list, max_length=5000)
    coverage_stats: CoverageStats = Field(default_factory=CoverageStats)
    media_assets: list[MediaAsset] = Field(default_factory=list, max_length=5000)
    generation_telemetry: list[GenerationTelemetry] = Field(default_factory=list, max_length=1000)
    verification_summary: str | None = Field(default=None, max_length=3000)
    teacher_review_required: bool = False
    source_documents: list[UploadedDocumentInfo] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @model_validator(mode="after")
    def validate_course_references(self) -> "GeneratedCourse":
        module_ids = [module.module_id for module in self.modules]
        module_numbers = [module.module_number for module in self.modules]
        if len(module_ids) != len(set(module_ids)):
            raise ValueError("Module IDs must be unique within a course.")
        if len(module_numbers) != len(set(module_numbers)):
            raise ValueError("Module numbers must be unique within a course.")

        question_ids = [question.question_id for question in self.question_bank]
        if len(question_ids) != len(set(question_ids)):
            raise ValueError("Question bank IDs must be unique.")
        if question_ids:
            known_question_ids = set(question_ids)
            for module in self.modules:
                for node in module.nodes:
                    if isinstance(node, SteppingStoneNode) and node.screens:
                        linked_ids = node.screens[1].linked_question_ids
                        unknown_ids = set(linked_ids) - known_question_ids
                        if unknown_ids:
                            raise ValueError(
                                "Exam rubric references unknown question IDs: "
                                + ", ".join(sorted(unknown_ids))
                            )
        ledger_ids = [entry.question_id for entry in self.question_coverage_ledger]
        if len(ledger_ids) != len(set(ledger_ids)):
            raise ValueError("Question coverage ledger IDs must be unique.")
        if ledger_ids and set(ledger_ids) != set(question_ids):
            raise ValueError("Coverage ledger must retain every question-bank entry exactly once.")
        all_asset_ids = [asset.asset_id for asset in self.media_assets]
        if len(all_asset_ids) != len(set(all_asset_ids)):
            raise ValueError("Media asset IDs must be unique.")
        return self


class CourseGenerationRequest(ContractModel):
    """Generation options supplied after local preprocessing."""

    course_id: Identifier
    course_title: ShortText | None = None
    subject_area: ShortText | None = Field(
        default=None,
        description="Optional descriptive metadata; not a generation rule.",
    )
    academic_level: ShortText | None = None
    exam_pattern: ExamPattern = Field(default_factory=ExamPattern)
    target_language: ShortText = "English"
    learner_starting_level: Literal["beginner", "mixed", "advanced"] = "beginner"
    additional_instructions: str | None = Field(default=None, max_length=4000)


class NodeProgress(ContractModel):
    node_id: Identifier
    opened: bool = False
    completed: bool = False
    score: float = Field(default=0.0, ge=0.0, le=1.0)
    attempts: int = Field(default=0, ge=0)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class BossProgress(ContractModel):
    assessment_id: Identifier
    started: bool = False
    submitted: bool = False
    score: float | None = Field(default=None, ge=0.0, le=1.0)
    passed: bool = False
    answered_item_ids: list[Identifier] = Field(default_factory=list, max_length=1000)
    responses: dict[Identifier, str] = Field(default_factory=dict, max_length=1000)
    submitted_at: datetime | None = None
    blueprint_unlocked: bool = False


class ModuleProgress(ContractModel):
    module_id: Identifier
    unlocked: bool = False
    unlock_reason: NonEmptyText = "Waiting for prerequisite module completion."
    node_progress: list[NodeProgress] = Field(default_factory=list, max_length=1000)
    boss_progress: BossProgress | None = None
    required_question_ids: list[Identifier] = Field(default_factory=list, max_length=1000)
    assessed_question_ids: list[Identifier] = Field(default_factory=list, max_length=1000)
    mastered_question_ids: list[Identifier] = Field(default_factory=list, max_length=1000)
    completion_requirements: list[NonEmptyText] = Field(default_factory=list, max_length=20)
    completed: bool = False
    completed_at: datetime | None = None


class CourseProgress(ContractModel):
    course_id: Identifier
    modules: list[ModuleProgress] = Field(default_factory=list, max_length=1000)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ProgressEventRequest(ContractModel):
    event_type: Literal["open_node", "complete_node", "start_boss", "submit_boss", "record_struggle"]
    node_id: Identifier | None = None
    assessment_id: Identifier | None = None
    question_id: Identifier | None = None
    responses: dict[Identifier, str] = Field(default_factory=dict, max_length=1000)
    score: float | None = Field(default=None, ge=0.0, le=1.0)


class CourseProgressResponse(ContractModel):
    course_id: Identifier
    progress: CourseProgress
    coverage: CoverageStats
    blueprint_unlocked: bool = False
    course: GeneratedCourse | None = None


# ---------------------------------------------------------------------------
# Upload and generation job lifecycle contracts
# ---------------------------------------------------------------------------


class JobError(ContractModel):
    code: Identifier
    message: NonEmptyText = Field(max_length=1000)
    retryable: bool = False


class GenerationJobState(ContractModel):
    job_id: Identifier
    status: Literal[
        "uploaded",
        "preprocessing",
        "generating",
        "validating",
        "completed",
        "failed",
    ] = "uploaded"
    progress_percent: int = Field(default=0, ge=0, le=100)
    stage_message: str | None = Field(default=None, max_length=500)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    uploaded_documents: list[UploadedDocumentInfo] = Field(default_factory=list)
    error: JobError | None = None
    course: GeneratedCourse | None = None
    progress: CourseProgress | None = None
    generation_telemetry: list[GenerationTelemetry] = Field(default_factory=list, max_length=1000)
    checkpoint_stage: str | None = Field(default=None, max_length=160)
    source_fingerprints: dict[Identifier, str] = Field(default_factory=dict, max_length=1000)

    @model_validator(mode="after")
    def validate_terminal_state(self) -> "GenerationJobState":
        if self.status == "completed":
            if self.progress_percent != 100:
                raise ValueError("Completed jobs must have progress_percent=100.")
            if self.course is None:
                raise ValueError("Completed jobs must include the generated course.")
            if self.error is not None:
                raise ValueError("Completed jobs cannot contain an error.")
        if self.status == "failed" and self.error is None:
            raise ValueError("Failed jobs must include a safe error summary.")
        if self.status != "failed" and self.error is not None:
            raise ValueError("Only failed jobs may contain an error.")
        return self


class UploadResponse(ContractModel):
    job_id: Identifier
    status: Literal["uploaded"] = "uploaded"
    uploaded_documents: list[UploadedDocumentInfo] = Field(min_length=1)


class JobStatusResponse(ContractModel):
    job_id: Identifier
    status: Literal[
        "uploaded",
        "preprocessing",
        "generating",
        "validating",
        "completed",
        "failed",
    ]
    progress_percent: int = Field(ge=0, le=100)
    stage_message: str | None = None
    error: JobError | None = None
    checkpoint_stage: str | None = None
    course_id: Identifier | None = None


class GeneratedCourseResponse(ContractModel):
    job_id: Identifier
    course: GeneratedCourse


# ``LessonBlock`` is declared before the activity union in source order so it
# can be referenced by node contracts without weakening the JSON boundary.
# Rebuild the deferred annotations once every contract has been declared.
LessonBlock.model_rebuild()
CourseProgressResponse.model_rebuild()
