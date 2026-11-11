"""Local, subject-agnostic document preprocessing for the course generator.

This module extracts useful text from teacher-uploaded DOCX, PDF, and PPTX
files before any LLM call. It performs conservative cleanup, syllabus module
recognition, exam-question extraction, and fuzzy duplicate removal. It does
not infer a subject or embed subject-specific academic rules.

Public entry point
------------------
``preprocess_documents([...])`` accepts ``DocumentInput`` records and returns
an instance of ``PreprocessedCourseContext`` from :mod:`backend.schemas`.

Example::

    from pathlib import Path
    from backend.preprocessor import DocumentInput, preprocess_documents

    context = preprocess_documents([
        DocumentInput(Path("sample_inputs/syllabus.docx"), "syllabus"),
        DocumentInput(Path("sample_inputs/questions.docx"), "exam_questions"),
        DocumentInput(Path("sample_inputs/notes.pdf"), "lecture_material"),
    ])

The caller is responsible for saving uploaded files to a controlled temporary
or project upload directory before passing their paths here.
"""

from __future__ import annotations

import logging
import hashlib
import mimetypes
import re
import shutil
import unicodedata
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Literal, Sequence

from docx import Document as DocxDocument
from docx.document import Document as DocxDocumentType
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.table import Table
from docx.text.paragraph import Paragraph
try:
    import fitz
except Exception:
    fitz = None

try:
    import pypdf
except Exception:
    pypdf = None
from pptx import Presentation
from rapidfuzz import fuzz, process

from backend.schemas import (
    ExamPattern,
    ExamQuestion,
    ExtractedModule,
    ExtractedTopic,
    MediaAsset,
    QuestionCoverageEntry,
    PreprocessedCourseContext,
    SourceReference,
    UploadedDocumentInfo,
)


logger = logging.getLogger(__name__)

DocumentRole = Literal["syllabus", "exam_questions", "lecture_material", "other"]
SUPPORTED_EXTENSIONS = {".docx", ".pdf", ".pptx"}
DEFAULT_MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024
DEFAULT_DUPLICATE_SIMILARITY = 93
MAX_LECTURE_CONTENT_CHARS = 250_000
MAX_QUESTION_TEXT_CHARS = 4_000
MAX_MODULE_OVERVIEW_CHARS = 3_000
MAX_TOPIC_DESCRIPTION_CHARS = 2_000


@dataclass(frozen=True, slots=True)
class DocumentInput:
    """A saved upload and its teacher-selected document role.

    ``path`` must point to a file already stored by the API layer. The role is
    metadata supplied by the uploader; it is not inferred from the filename.
    """

    path: Path | str
    role: DocumentRole = "other"
    document_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", Path(self.path))
        if self.role not in {
            "syllabus",
            "exam_questions",
            "lecture_material",
            "other",
        }:
            raise ValueError(f"Unsupported document role: {self.role!r}")
        if self.document_id is not None and not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", self.document_id
        ):
            raise ValueError("document_id must be a valid schema Identifier.")


@dataclass(frozen=True, slots=True)
class _TextUnit:
    """A paragraph, PDF page, or slide text fragment with its provenance."""

    text: str
    document_name: str
    page_number: int | None = None
    section_title: str | None = None
    style_name: str | None = None
    document_id: str | None = None
    source_hash: str | None = None


@dataclass(slots=True)
class _ModuleDraft:
    number: int
    title: str
    source_ref: SourceReference
    overview_parts: list[str]
    topics: list[ExtractedTopic]
    topic_keys: set[str]


@dataclass(slots=True)
class _QuestionDraft:
    text: str
    number: str | None
    marks: int | None
    source_refs: list[SourceReference]
    module_number: int | None
    similarity_kind: Literal["none", "exact_duplicate", "near_duplicate", "related"] = "none"
    duplicate_cluster_id: str | None = None
    related_indexes: list[int] | None = None


# Administrative material is removed only when its wording is strongly
# indicative of document administration. Broad headings such as "Course
# Outcomes" are intentionally retained because they may contain learning
# objectives relevant to the course.
_ADMINISTRATIVE_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"^\s*(?:co\s*[-/]\s*po|co\s+po)\s+mapping\b",
        r"^\s*(?:co\s*[-/]\s*po|co\s+po)\s+attainment\b",
        r"^\s*(?:document\s+control|revision\s+history|change\s+log)\b",
        r"^\s*(?:prepared|verified|approved|reviewed)\s+by\s*[:：]",
        r"^\s*(?:signature|signatory|office\s+use\s+only)\b",
        r"^\s*(?:confidentiality\s+notice|internal\s+administration)\b",
        r"^\s*page\s+\d+\s*(?:of\s+\d+)?\s*$",
    )
)

_MODULE_HEADING_RE = re.compile(
    r"^\s*(?:module|unit|chapter|part)\s*[-–—:]?\s*"
    r"(?P<number>[0-9]{1,2}|[ivxlcdm]{1,8})\b\s*"
    r"(?:[.:–—-]\s*)?(?P<title>.*)$",
    re.IGNORECASE,
)

_QUESTION_PREFIX_RE = re.compile(
    r"^\s*(?:(?P<prefix>question\s*|q\.?\s*)"
    r"(?P<qnumber>\d{1,3})\s*[).:–—-]?\s+|"
    r"(?P<number>\d{1,3})\s*[).:–—-]\s+)"
    r"(?P<body>\S.*)$",
    re.IGNORECASE,
)
_QUESTION_WORD_RE = re.compile(
    r"^(?:(?:critically|briefly|clearly|concisely|properly)\s+)?"
    r"(?:define|state|list|name|identify|mention|write|explain|describe|"
    r"discuss|compare|differentiate|distinguish|illustrate|derive|prove|"
    r"calculate|compute|solve|evaluate|analyse|analyze|design|outline|"
    r"justify|comment|enumerate|elaborate|propose|suggest|show|what|why|"
    r"how|when|where|which|who|under\s+what|give\s+an\s+account|"
    r"a\s+user|a\s+patient|a\s+system|a\s+researcher|consider|suppose|assume)\b",
    re.IGNORECASE,
)
_MARKS_RE = re.compile(
    r"(?:\(\s*(\d{1,3})\s*(?:marks?|m)\s*\)|"
    r"\[\s*(\d{1,3})\s*(?:marks?|m)\s*\]|"
    r"\b(\d{1,3})\s*marks?\b|"
    r"\bmarks?\s*[:=]\s*(\d{1,3})\b|"
    r"\b(\d{1,3})\s*M\b)",
    re.IGNORECASE,
)
_TOPIC_NUMBER_RE = re.compile(r"^\s*\d{1,2}(?:\.\d{1,2}){1,3}[.)]?\s+\S+")
_TOPIC_BULLET_RE = re.compile(r"^\s*(?:[•▪◦‣]|[-*])\s+\S+")
_QUESTION_ADMIN_RE = re.compile(
    r"^\s*(?:section\s+[a-z0-9]+|answer\s+all|attempt\s+any|"
    r"time\s*:\s*|maximum\s+marks|total\s+marks)\b",
    re.IGNORECASE,
)

_ROMAN_VALUES = {
    "i": 1,
    "ii": 2,
    "iii": 3,
    "iv": 4,
    "v": 5,
    "vi": 6,
    "vii": 7,
    "viii": 8,
    "ix": 9,
    "x": 10,
    "xi": 11,
    "xii": 12,
    "xiii": 13,
    "xiv": 14,
    "xv": 15,
    "xvi": 16,
    "xvii": 17,
    "xviii": 18,
    "xix": 19,
    "xx": 20,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def preprocess_documents(
    documents: Sequence[DocumentInput],
    *,
    course_title: str | None = None,
    subject_area: str | None = None,
    exam_pattern: ExamPattern | None = None,
    duplicate_similarity_threshold: int = DEFAULT_DUPLICATE_SIMILARITY,
    max_file_size_bytes: int = DEFAULT_MAX_FILE_SIZE_BYTES,
    asset_storage_dir: Path | str | None = None,
) -> PreprocessedCourseContext:
    """Extract and clean uploaded course documents without making an AI call.

    Args:
        documents: Saved file paths and the roles selected by the teacher.
        course_title: Optional title supplied by the teacher or API caller.
        subject_area: Optional descriptive metadata only. It is never used to
            choose parsers, question rules, or learning activity types.
        exam_pattern: Optional configurable examination pattern. Defaults to
            the schema's initial 2/5/10-mark pattern.
        duplicate_similarity_threshold: RapidFuzz ratio cutoff from 0 to 100.
            A higher value is more conservative about merging questions.
        max_file_size_bytes: Per-file safety limit.

    Returns:
        A validated ``PreprocessedCourseContext`` ready for downstream AI
        generation. Extraction gaps are reported in ``extraction_warnings``.

    Notes:
        An unreadable or unsupported file does not discard successfully
        processed files. The failure is recorded as a warning. The function
        does not infer a subject from filenames or course content.
    """

    if not 0 <= duplicate_similarity_threshold <= 100:
        raise ValueError("duplicate_similarity_threshold must be between 0 and 100.")
    if max_file_size_bytes <= 0:
        raise ValueError("max_file_size_bytes must be a positive integer.")

    warnings: list[str] = []
    media_assets: list[MediaAsset] = []
    if asset_storage_dir is not None:
        Path(asset_storage_dir).mkdir(parents=True, exist_ok=True)
    document_infos: list[UploadedDocumentInfo] = []
    extracted_by_role: dict[str, list[_TextUnit]] = {
        "syllabus": [],
        "exam_questions": [],
        "lecture_material": [],
        "other": [],
    }

    for index, spec in enumerate(documents, start=1):
        path = Path(spec.path)
        if not path.exists() or not path.is_file():
            warnings.append(f"File not found or not a regular file: {path.name}")
            continue

        try:
            file_size = path.stat().st_size
        except OSError as exc:
            warnings.append(f"Could not inspect {path.name}: {exc}")
            continue

        if file_size > max_file_size_bytes:
            warnings.append(
                f"Skipped {path.name}: file size {file_size:,} bytes exceeds the "
                f"{max_file_size_bytes:,}-byte limit."
            )
            continue

        extension = path.suffix.lower()
        if extension not in SUPPORTED_EXTENSIONS:
            warnings.append(
                f"Skipped {path.name}: unsupported format {extension or '(no extension)'}. "
                f"Supported formats: DOCX, PDF, PPTX."
            )
            continue

        document_id = spec.document_id or f"doc_{index:03d}"
        media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        document_infos.append(
            UploadedDocumentInfo(
                document_id=document_id,
                file_name=path.name,
                media_type=media_type,
                file_size_bytes=file_size,
                document_role=spec.role,
            )
        )

        try:
            units, parser_warnings = _extract_document(path)
            warnings.extend(parser_warnings)
            source_hash = hashlib.sha256(path.read_bytes()).hexdigest()
            units = [
                _TextUnit(
                    text=unit.text,
                    document_name=unit.document_name,
                    page_number=unit.page_number,
                    section_title=unit.section_title,
                    style_name=unit.style_name,
                    document_id=document_id,
                    source_hash=source_hash,
                )
                for unit in units
            ]
            cleaned_units = _clean_units(units)
            if not cleaned_units:
                warnings.append(f"No usable text was extracted from {path.name}.")
            extracted_by_role[spec.role].extend(cleaned_units)
            extracted_assets, asset_warnings = _extract_media_assets(
                path, document_id=document_id, storage_dir=asset_storage_dir
            )
            media_assets.extend(extracted_assets)
            warnings.extend(asset_warnings)
        except Exception as exc:  # Keep other uploads usable when one file is damaged.
            logger.exception("Failed to preprocess uploaded document %s", path.name)
            warnings.append(
                f"Could not process {path.name}: {type(exc).__name__}: {exc}"
            )

    module_records = _extract_modules(extracted_by_role["syllabus"], warnings)
    known_module_numbers = {module.module_number for module in module_records}

    question_drafts = _extract_question_drafts(
        extracted_by_role["exam_questions"], known_module_numbers, warnings
    )
    annotated_questions = _deduplicate_questions(
        question_drafts,
        similarity_threshold=duplicate_similarity_threshold,
        warnings=warnings,
    )

    exam_questions: list[ExamQuestion] = []
    stable_ids = [
        _stable_question_id(draft, index)
        for index, draft in enumerate(annotated_questions, start=1)
    ]
    for index, draft in enumerate(annotated_questions, start=1):
        module_id = (
            f"module_{draft.module_number}"
            if draft.module_number in known_module_numbers
            else None
        )
        related_ids = [
            stable_ids[related_index]
            for related_index in (draft.related_indexes or [])
            if 0 <= related_index < len(stable_ids) and related_index != index - 1
        ]
        expected_depth = _expected_answer_depth(draft.marks, draft.text)
        exam_questions.append(
            ExamQuestion(
                question_id=stable_ids[index - 1],
                question_text=draft.text[:MAX_QUESTION_TEXT_CHARS],
                marks=draft.marks,
                question_number=draft.number,
                module_id=module_id,
                question_kind=_classify_question(draft.text, draft.marks),
                source_refs=draft.source_refs,
                source_type="teacher_provided",
                source_entry_id=stable_ids[index - 1],
                duplicate_cluster_id=draft.duplicate_cluster_id,
                similarity_kind=draft.similarity_kind,
                related_question_ids=related_ids,
                expected_answer_depth=expected_depth,
                lifecycle_status="CLASSIFIED",
                coverage_status="mapped" if module_id else "unmapped",
            )
        )

    question_coverage_ledger = [
        QuestionCoverageEntry(
            question_id=question.question_id,
            source_type=question.source_type,
            original_question_text=question.question_text,
            source_refs=question.source_refs,
            module_id=question.module_id,
            marks_as_supplied=question.marks,
            question_number=question.question_number,
            question_kind=question.question_kind,
            expected_answer_depth=question.expected_answer_depth,
            related_question_ids=question.related_question_ids,
            duplicate_cluster_id=question.duplicate_cluster_id,
            similarity_kind=question.similarity_kind,
            lifecycle_status=question.lifecycle_status,
            coverage_status=question.coverage_status,
        )
        for question in exam_questions
    ]

    lecture_content = _join_lecture_content(extracted_by_role["lecture_material"], warnings)

    # Filter out modules from the syllabus that have zero uploaded questions or materials
    if extracted_by_role["exam_questions"] and exam_questions:
        modules_with_questions = {q.module_id for q in exam_questions if q.module_id}
        if modules_with_questions:
            filtered_modules = [m for m in module_records if m.module_id in modules_with_questions]
            if filtered_modules:
                skipped = [m.title or m.module_id for m in module_records if m.module_id not in modules_with_questions]
                if skipped:
                    warnings.append(
                        f"Skipping modules with no uploaded questions: {', '.join(skipped)}. Only modules with provided examination questions will be generated."
                    )
                module_records = filtered_modules

    if not module_records and extracted_by_role["syllabus"]:
        warnings.append(
            "Syllabus text was extracted, but no explicit Module/Unit/Chapter "
            "boundaries were recognised. The source content is retained for "
            "downstream analysis; module grouping was not guessed."
        )
    if not exam_questions and extracted_by_role["exam_questions"]:
        warnings.append(
            "Exam-question material was extracted, but no question blocks could "
            "be identified confidently. Review the source formatting or provide "
            "questions with clearer numbering or question boundaries."
        )

    # Associate assets conservatively with the module whose source reference
    # points to the same uploaded document. Ambiguous assets remain available
    # for teacher review instead of being assigned randomly.
    associated_assets: list[MediaAsset] = []
    for asset in media_assets:
        candidates = [
            module for module in module_records
            if any(ref.document_id == asset.document_id for ref in module.source_refs)
        ]
        associated_assets.append(asset.model_copy(update={"module_id": candidates[0].module_id if len(candidates) == 1 else None}))
    media_assets = associated_assets

    # De-duplicate warnings while preserving their first-seen order.
    warnings = list(dict.fromkeys(warnings))

    return PreprocessedCourseContext(
        course_title=_optional_clean_text(course_title, max_length=160),
        subject_area=_optional_clean_text(subject_area, max_length=160),
        exam_pattern=exam_pattern or ExamPattern(),
        documents=document_infos,
        modules=module_records,
        exam_questions=exam_questions,
        question_coverage_ledger=question_coverage_ledger,
        media_assets=media_assets,
        lecture_content=lecture_content,
        extraction_warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Document readers
# ---------------------------------------------------------------------------


def _extract_document(path: Path) -> tuple[list[_TextUnit], list[str]]:
    extension = path.suffix.lower()
    if extension == ".docx":
        return _extract_docx(path), []
    if extension == ".pdf":
        return _extract_pdf(path), []
    if extension == ".pptx":
        return _extract_pptx(path), []
    raise ValueError(f"Unsupported document extension: {extension}")


def _iter_docx_blocks(document: DocxDocumentType) -> Iterable[Paragraph | Table]:
    """Yield DOCX paragraphs and tables in their original body order."""

    body = document.element.body
    for child in body.iterchildren():
        if isinstance(child, CT_P):
            yield Paragraph(child, document)
        elif isinstance(child, CT_Tbl):
            yield Table(child, document)


def _extract_docx(path: Path) -> list[_TextUnit]:
    document = DocxDocument(str(path))
    units: list[_TextUnit] = []
    current_section: str | None = None

    for block in _iter_docx_blocks(document):
        if isinstance(block, Paragraph):
            text = block.text.strip()
            if not text:
                continue
            style_name = getattr(block.style, "name", None) if block.style else None
            if style_name and (
                style_name.lower().startswith("heading")
                or style_name.lower() in {"title", "subtitle"}
            ):
                current_section = text[:160]
            units.append(
                _TextUnit(
                    text=text,
                    document_name=path.name,
                    section_title=current_section,
                    style_name=style_name,
                )
            )
        else:
            for row in block.rows:
                cells = [_normalise_text(cell.text) for cell in row.cells]
                cells = [cell for cell in cells if cell]
                if cells:
                    units.append(
                        _TextUnit(
                            text=" | ".join(cells),
                            document_name=path.name,
                            section_title=current_section,
                            style_name="Table Row",
                        )
                    )

    return units


def _extract_pdf(path: Path) -> list[_TextUnit]:
    units: list[_TextUnit] = []
    if fitz is not None:
        try:
            with fitz.open(path) as document:
                for page_index, page in enumerate(document, start=1):
                    text = page.get_text("text", sort=True)
                    if text and text.strip():
                        units.append(
                            _TextUnit(
                                text=text,
                                document_name=path.name,
                                page_number=page_index,
                            )
                        )
            return units
        except Exception as exc:
            logger.warning("PyMuPDF failed to extract %s (%s); trying fallback", path.name, exc)

    if pypdf is not None:
        reader = pypdf.PdfReader(str(path))
        for page_index, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            if text and text.strip():
                units.append(
                    _TextUnit(
                        text=text,
                        document_name=path.name,
                        page_number=page_index,
                    )
                )
        return units

    raise RuntimeError("No PDF extractor available (neither fitz nor pypdf available).")


def _extract_pptx(path: Path) -> list[_TextUnit]:
    presentation = Presentation(str(path))
    units: list[_TextUnit] = []

    for slide_number, slide in enumerate(presentation.slides, start=1):
        slide_title: str | None = None
        for shape in slide.shapes:
            if getattr(shape, "has_text_frame", False):
                text = shape.text.strip()
                if not text:
                    continue
                if getattr(shape, "is_placeholder", False):
                    try:
                        if shape.placeholder_format.type == 1:  # TITLE
                            slide_title = text[:160]
                    except (AttributeError, ValueError):
                        pass
                units.append(
                    _TextUnit(
                        text=text,
                        document_name=path.name,
                        page_number=slide_number,
                        section_title=slide_title,
                        style_name="Slide Text",
                    )
                )
            elif getattr(shape, "has_table", False):
                for row in shape.table.rows:
                    cells = [_normalise_text(cell.text) for cell in row.cells]
                    cells = [cell for cell in cells if cell]
                    if cells:
                        units.append(
                            _TextUnit(
                                text=" | ".join(cells),
                                document_name=path.name,
                                page_number=slide_number,
                                section_title=slide_title,
                                style_name="Slide Table Row",
                            )
                        )

    return units


# ---------------------------------------------------------------------------
# Conservative text cleanup
# ---------------------------------------------------------------------------


def _normalise_text(value: str) -> str:
    value = unicodedata.normalize("NFC", value or "")
    value = value.replace("\u00a0", " ").replace("\u200b", "")
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    lines = [re.sub(r"[\t\f\v ]+", " ", line).strip() for line in value.split("\n")]
    return "\n".join(line for line in lines if line)


def _is_administrative_line(line: str) -> bool:
    if not line.strip():
        return True
    if re.fullmatch(r"(?:page\s*)?\d{1,3}", line.strip(), re.IGNORECASE):
        return True
    return any(pattern.search(line) for pattern in _ADMINISTRATIVE_PATTERNS)


def _clean_units(units: Sequence[_TextUnit]) -> list[_TextUnit]:
    cleaned: list[_TextUnit] = []
    for unit in units:
        normalised = _normalise_text(unit.text)
        if not normalised:
            continue
        kept_lines = [
            line for line in normalised.splitlines() if not _is_administrative_line(line)
        ]
        text = "\n".join(kept_lines).strip()
        if text:
            cleaned.append(
                _TextUnit(
                    text=text,
                    document_name=unit.document_name,
                    page_number=unit.page_number,
                    section_title=unit.section_title,
                    style_name=unit.style_name,
                    document_id=unit.document_id,
                    source_hash=unit.source_hash,
                )
            )
    return cleaned


def _make_source_ref(unit: _TextUnit, excerpt: str | None = None) -> SourceReference:
    source_text = excerpt if excerpt is not None else unit.text
    return SourceReference(
        document_id=unit.document_id,
        document_name=unit.document_name,
        page_number=unit.page_number,
        slide_number=unit.page_number,
        section_title=(unit.section_title[:160] if unit.section_title else None),
        excerpt=_normalise_text(source_text)[:1600] or None,
        source_hash=unit.source_hash,
    )


def _optional_clean_text(value: str | None, *, max_length: int) -> str | None:
    if value is None:
        return None
    cleaned = _normalise_text(value).replace("\n", " ").strip()
    return cleaned[:max_length] or None


# ---------------------------------------------------------------------------
# Syllabus module and topic extraction
# ---------------------------------------------------------------------------


def _parse_module_heading(text: str) -> tuple[int, str] | None:
    match = _MODULE_HEADING_RE.match(text.strip())
    if not match:
        return None
    raw_number = match.group("number").casefold()
    number = int(raw_number) if raw_number.isdigit() else _ROMAN_VALUES.get(raw_number)
    if number is None or number < 1:
        return None
    title = (match.group("title") or "").strip(" .:–—-\t")
    title = re.sub(r"\s*\([^)]*(?:hours?|hrs?|credits?)\s*\)\s*$", "", title, flags=re.I)
    return number, title[:160] or f"Module {number}"


def _is_topic_heading(unit: _TextUnit, text: str) -> bool:
    if len(text) > 180 or len(text.split()) > 22:
        return False
    style = (unit.style_name or "").casefold()
    if style.startswith("heading") and not style.endswith("1"):
        return True
    if _TOPIC_NUMBER_RE.match(text):
        return True
    if _TOPIC_BULLET_RE.match(text) and not re.search(r"[.!?]$", text):
        return True
    return False


def _strip_topic_marker(text: str) -> str:
    text = re.sub(r"^\s*(?:\d{1,2}(?:\.\d{1,2}){1,3}[.)]?|[•▪◦‣]|[-*])\s*", "", text)
    return text.strip(" :–—-\t")


def _extract_modules(
    syllabus_units: Sequence[_TextUnit], warnings: list[str]
) -> list[ExtractedModule]:
    drafts: list[_ModuleDraft] = []
    seen_numbers: set[int] = set()
    current: _ModuleDraft | None = None

    for unit in syllabus_units:
        for raw_line in unit.text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            parsed_heading = _parse_module_heading(line)
            if parsed_heading:
                number, title = parsed_heading
                if number in seen_numbers:
                    warnings.append(
                        f"Repeated module/unit number {number} was found in syllabus "
                        f"material; the later heading was retained as source text but "
                        f"not made into a second module."
                    )
                    current = next((item for item in drafts if item.number == number), current)
                    continue
                seen_numbers.add(number)
                current = _ModuleDraft(
                    number=number,
                    title=title,
                    source_ref=_make_source_ref(unit, line),
                    overview_parts=[],
                    topics=[],
                    topic_keys=set(),
                )
                drafts.append(current)
                continue

            if current is None:
                continue

            if _is_topic_heading(unit, line):
                title = _strip_topic_marker(line)
                key = _normalise_for_comparison(title)
                if title and key and key not in current.topic_keys:
                    current.topic_keys.add(key)
                    topic_id = f"topic_{current.number}_{len(current.topics) + 1}"
                    current.topics.append(
                        ExtractedTopic(
                            topic_id=topic_id,
                            title=title[:160],
                            source_refs=[_make_source_ref(unit, line)],
                        )
                    )
            elif len(" ".join(current.overview_parts)) < MAX_MODULE_OVERVIEW_CHARS:
                current.overview_parts.append(line)

    result: list[ExtractedModule] = []
    for draft in drafts:
        overview = _normalise_text(" ".join(draft.overview_parts))
        result.append(
            ExtractedModule(
                module_id=f"module_{draft.number}",
                module_number=draft.number,
                title=draft.title,
                overview=overview[:MAX_MODULE_OVERVIEW_CHARS] or None,
                topics=draft.topics[:100],
                source_refs=[draft.source_ref],
            )
        )

    return result


# ---------------------------------------------------------------------------
# Examination question extraction and classification
# ---------------------------------------------------------------------------


def _line_starts_question(line: str) -> tuple[bool, str | None, str]:
    """Return (is_start, question_number, body_without_number)."""

    if not line or _QUESTION_ADMIN_RE.search(line):
        return False, None, line

    match = _QUESTION_PREFIX_RE.match(line)
    if match:
        prefix = (match.group("prefix") or "").strip()
        body = match.group("body").strip()
        explicit_question_prefix = bool(prefix)
        looks_academic_question = bool(
            _QUESTION_WORD_RE.match(body)
            or "?" in body
            or re.search(r"\b(?:with|using|from|given)\b", body, re.I)
        )
        # Numbered entries are treated as questions in a teacher-designated
        # question document only when the text resembles an instruction or
        # interrogative. Explicit Q/Question numbering is accepted directly.
        if explicit_question_prefix or looks_academic_question:
            question_number = match.group("qnumber") or match.group("number")
            return True, question_number, body

    if "?" in line or _QUESTION_WORD_RE.match(line):
        return True, None, line
    return False, None, line


def _extract_marks(text: str) -> int | None:
    matches = list(_MARKS_RE.finditer(text))
    if not matches:
        return None
    values = [int(group) for match in matches for group in match.groups() if group]
    return values[-1] if values else None


def _remove_marks_annotation(text: str) -> str:
    cleaned = _MARKS_RE.sub("", text)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    cleaned = re.sub(r"\s+([,.;:])", r"\1", cleaned)
    return cleaned.strip(" \t-–—:;,.()[]")


def _extract_question_drafts(
    question_units: Sequence[_TextUnit],
    known_module_numbers: set[int],
    warnings: list[str],
) -> list[_QuestionDraft]:
    drafts: list[_QuestionDraft] = []
    current_lines: list[str] = []
    current_units: list[_TextUnit] = []
    current_number: str | None = None
    current_module_number: int | None = None
    active_module_number: int | None = None
    active_section_marks: int | None = None

    def add_current_unit(unit: _TextUnit) -> None:
        key = (unit.document_name, unit.page_number, unit.section_title)
        if not any(
            (existing.document_name, existing.page_number, existing.section_title) == key
            for existing in current_units
        ):
            current_units.append(unit)

    def flush_current() -> None:
        nonlocal current_lines, current_units, current_number, current_module_number
        if not current_lines or not current_units:
            current_lines = []
            current_units = []
            current_number = None
            current_module_number = None
            return

        raw_text = _normalise_text(" ".join(current_lines))
        marks = _extract_marks(raw_text)
        if marks is None:
            section_marks = [
                _extract_marks(unit.section_title or "")
                for unit in current_units
            ]
            marks = next((value for value in reversed(section_marks) if value is not None), active_section_marks)
        if marks is None:
            marks = active_section_marks
        question_text = _remove_marks_annotation(raw_text)
        question_text = re.sub(
            r"^(?:question\s*|q\.?\s*)?\d{1,3}\s*[).:–—-]?\s+",
            "",
            question_text,
            flags=re.I,
        )
        question_text = question_text[:MAX_QUESTION_TEXT_CHARS]
        if len(question_text.split()) >= 3:
            source_refs = [
                _make_source_ref(unit, raw_text) for unit in current_units
            ]
            drafts.append(
                _QuestionDraft(
                    text=question_text,
                    number=current_number,
                    marks=marks,
                    source_refs=source_refs,
                    module_number=(
                        current_module_number
                        if current_module_number in known_module_numbers
                        else None
                    ),
                )
            )
        current_lines = []
        current_units = []
        current_number = None
        current_module_number = None

    for unit in question_units:
        for raw_line in unit.text.splitlines():
            line = raw_line.strip()
            if not line:
                continue

            module_heading = _parse_module_heading(line)
            if module_heading:
                flush_current()
                active_module_number = module_heading[0]
                continue

            if _QUESTION_ADMIN_RE.search(line):
                flush_current()
                continue

            # Detect section marks headings (e.g. "Questions — 5 Marks", "Very Short Answer Questions — 2 Marks")
            if _MARKS_RE.search(line) and len(line.split()) <= 8 and not _QUESTION_WORD_RE.search(line):
                flush_current()
                marks_val = _extract_marks(line)
                if marks_val is not None:
                    active_section_marks = marks_val
                continue

            starts_question, number, body = _line_starts_question(line)
            if starts_question:
                flush_current()
                current_lines = [body]
                current_number = number
                current_module_number = active_module_number
                add_current_unit(unit)
            elif current_lines:
                # Numbered answer options such as (a), (b), or 1) remain part
                # of the preceding question instead of becoming new questions.
                current_lines.append(line)
                add_current_unit(unit)
            elif "?" in line and len(line.split()) >= 4:
                current_lines = [line]
                current_module_number = active_module_number
                add_current_unit(unit)

    flush_current()
    return drafts


def _classify_question(
    question_text: str,
    marks: int | None,
) -> Literal["short_answer", "long_answer", "problem", "case_study", "unknown"]:
    text = question_text.casefold()

    if re.search(r"\b(case study|caselet|given scenario|business scenario|case scenario)\b", text):
        return "case_study"
    if re.search(
        r"\b(calculate|compute|solve|derive|prove|find the value|determine the value|"
        r"show that|work out|numerical)\b",
        text,
    ):
        return "problem"
    if (marks is not None and marks >= 8) or re.search(
        r"\b(discuss|evaluate|critically analyse|critically analyze|elaborate|"
        r"design and explain|compare and contrast)\b",
        text,
    ):
        return "long_answer"
    if (marks is not None and marks <= 5) or re.search(
        r"\b(define|state|list|mention|name|briefly|differentiate|distinguish)\b",
        text,
    ):
        return "short_answer"
    return "unknown"


def _normalise_for_comparison(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).casefold()
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def _deduplicate_questions(
    questions: Sequence[_QuestionDraft],
    *,
    similarity_threshold: int,
    warnings: list[str],
) -> list[_QuestionDraft]:
    """Annotate similarity while retaining every original question entry.

    The previous implementation destructively merged fuzzy matches. That made
    official question coverage impossible to audit and could erase questions
    with different marks or answer depth. Similarity is now a relationship,
    not a deletion rule.
    """

    retained = [question for question in questions if _normalise_for_comparison(question.text)]
    normalised = [_normalise_for_comparison(question.text) for question in retained]
    exact_clusters: dict[str, str] = {}
    cluster_members: dict[str, list[int]] = {}
    exact_count = 0
    near_count = 0
    related_pairs = 0

    for index, candidate in enumerate(retained):
        candidate.related_indexes = []
        candidate_norm = normalised[index]
        exact_key = hashlib.sha1(candidate_norm.encode("utf-8")).hexdigest()[:12]
        prior_exact = next((j for j in range(index) if normalised[j] == candidate_norm), None)
        if prior_exact is not None:
            candidate.similarity_kind = "exact_duplicate"
            candidate.duplicate_cluster_id = exact_clusters.setdefault(
                exact_key, f"dup_{exact_key}"
            )
            exact_count += 1
        else:
            match = process.extractOne(
                candidate_norm,
                normalised[:index],
                scorer=fuzz.ratio,
                score_cutoff=similarity_threshold,
            ) if index else None
            if match is not None:
                _, score, matched_index = match
                candidate.similarity_kind = "near_duplicate"
                candidate.duplicate_cluster_id = retained[matched_index].duplicate_cluster_id or f"dup_{hashlib.sha1(normalised[matched_index].encode('utf-8')).hexdigest()[:12]}"
                retained[matched_index].duplicate_cluster_id = candidate.duplicate_cluster_id
                near_count += 1
                logger.debug("Retained near-duplicate question (similarity %.1f): %s", score, candidate.text[:120])

        for prior_index in range(index):
            score = fuzz.token_set_ratio(candidate_norm, normalised[prior_index])
            if score >= 68:
                candidate.related_indexes.append(prior_index)
                retained[prior_index].related_indexes = retained[prior_index].related_indexes or []
                if index not in retained[prior_index].related_indexes:
                    retained[prior_index].related_indexes.append(index)
                related_pairs += 1
                if candidate.similarity_kind == "none":
                    candidate.similarity_kind = "related"
                if retained[prior_index].similarity_kind == "none":
                    retained[prior_index].similarity_kind = "related"

        if candidate.duplicate_cluster_id:
            cluster_members.setdefault(candidate.duplicate_cluster_id, []).append(index)

    # Build non-destructive related-question clusters from the relationship
    # graph. Clusters never replace entries and do not imply identical answers.
    parent = list(range(len(retained)))
    def find(value: int) -> int:
        while parent[value] != value:
            parent[value] = parent[parent[value]]
            value = parent[value]
        return value
    def union(left: int, right: int) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parent[right_root] = left_root
    for index, candidate in enumerate(retained):
        for related_index in candidate.related_indexes or []:
            union(index, related_index)
    groups: dict[int, list[int]] = {}
    for index in range(len(retained)):
        groups.setdefault(find(index), []).append(index)
    for members in groups.values():
        if len(members) < 2:
            continue
        cluster_id = f"related_{hashlib.sha1('|'.join(normalised[index] for index in members).encode('utf-8')).hexdigest()[:12]}"
        for member in members:
            if retained[member].duplicate_cluster_id is None:
                retained[member].duplicate_cluster_id = cluster_id
            if retained[member].similarity_kind == "none":
                retained[member].similarity_kind = "related"

    if exact_count or near_count:
        warnings.append(
            f"Retained all {len(retained)} original examination entries; annotated "
            f"{exact_count} exact duplicate(s) and {near_count} near-duplicate(s) "
            "without deleting distinct requirements."
        )
    if related_pairs:
        warnings.append(f"Linked {related_pairs} related-question relationship(s) for review.")
    return retained


def _stable_question_id(draft: _QuestionDraft, index: int) -> str:
    provenance = "|".join(
        f"{ref.document_name}:{ref.page_number}:{ref.section_title}:{ref.excerpt}"
        for ref in draft.source_refs
    )
    raw = f"{provenance}|{draft.number}|{draft.text}|{index}"
    return f"question_{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16]}"


def _expected_answer_depth(marks: int | None, text: str) -> Literal["brief", "moderate", "extended", "unknown"]:
    if marks is not None:
        if marks <= 3:
            return "brief"
        if marks <= 7:
            return "moderate"
        return "extended"
    if re.search(r"\b(discuss|evaluate|design|derive|prove|compare and contrast|elaborate)\b", text, re.I):
        return "extended"
    if re.search(r"\b(define|state|list|name|mention)\b", text, re.I):
        return "brief"
    return "unknown"


def _asset_path(storage_dir: Path | str | None, asset_id: str, suffix: str) -> str:
    safe_suffix = suffix if re.fullmatch(r"\.[A-Za-z0-9]{1,8}", suffix) else ".bin"
    if storage_dir is None:
        return f"embedded://{asset_id}{safe_suffix}"
    target_dir = Path(storage_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    return str(target_dir / f"{asset_id}{safe_suffix}")


def _write_asset(storage_path: str, content: bytes) -> None:
    if storage_path.startswith("embedded://"):
        return
    target = Path(storage_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(target.suffix + ".tmp")
    temp.write_bytes(content)
    temp.replace(target)


def _make_media_asset(
    *,
    document_id: str,
    original_filename: str,
    content: bytes,
    media_type: str,
    page: int | None,
    slide: int | None,
    storage_dir: Path | str | None,
    surrounding_text: str | None = None,
) -> MediaAsset:
    content_hash = hashlib.sha256(content).hexdigest()
    asset_id = f"asset_{hashlib.sha256((document_id + content_hash).encode('utf-8')).hexdigest()[:16]}"
    suffix = Path(original_filename).suffix.lower() or mimetypes.guess_extension(media_type) or ".bin"
    storage_path = _asset_path(storage_dir, asset_id, suffix)
    _write_asset(storage_path, content)
    return MediaAsset(
        asset_id=asset_id,
        document_id=document_id,
        original_filename=original_filename,
        media_type=media_type,
        storage_path=storage_path,
        source_page=page,
        source_slide=slide,
        asset_kind="image",
        surrounding_text=surrounding_text,
        content_hash=content_hash,
    )


def _extract_media_assets(
    path: Path,
    *,
    document_id: str,
    storage_dir: Path | str | None,
) -> tuple[list[MediaAsset], list[str]]:
    """Extract embedded visuals from DOCX, PDF, and PPTX without AI calls."""

    assets: list[MediaAsset] = []
    warnings: list[str] = []
    try:
        if path.suffix.lower() == ".docx":
            with zipfile.ZipFile(path) as archive:
                for name in archive.namelist():
                    if not name.startswith("word/media/"):
                        continue
                    content = archive.read(name)
                    media_type = mimetypes.guess_type(name)[0] or "application/octet-stream"
                    assets.append(_make_media_asset(
                        document_id=document_id,
                        original_filename=Path(name).name,
                        content=content,
                        media_type=media_type,
                        page=None,
                        slide=None,
                        storage_dir=storage_dir,
                    ))
        elif path.suffix.lower() == ".pdf" and fitz is not None:
            with fitz.open(path) as document:
                for page_index, page in enumerate(document, start=1):
                    for image_index, image in enumerate(page.get_images(full=True), start=1):
                        xref = image[0]
                        extracted = document.extract_image(xref)
                        content = extracted.get("image", b"")
                        if not content:
                            continue
                        filename = f"page_{page_index}_image_{image_index}.{extracted.get('ext', 'bin')}"
                        assets.append(_make_media_asset(
                            document_id=document_id,
                            original_filename=filename,
                            content=content,
                            media_type=extracted.get("mime", "application/octet-stream"),
                            page=page_index,
                            slide=None,
                            storage_dir=storage_dir,
                            surrounding_text=page.get_text("text", sort=True)[:3000] or None,
                        ))
        elif path.suffix.lower() == ".pptx":
            presentation = Presentation(str(path))
            for slide_number, slide in enumerate(presentation.slides, start=1):
                slide_text = " ".join(
                    shape.text.strip()
                    for shape in slide.shapes
                    if getattr(shape, "has_text_frame", False) and shape.text.strip()
                )[:3000] or None
                for image_index, shape in enumerate(
                    (shape for shape in slide.shapes if getattr(shape, "shape_type", None) == 13),
                    start=1,
                ):
                    image = shape.image
                    filename = image.filename or f"slide_{slide_number}_image_{image_index}.{image.ext}"
                    assets.append(_make_media_asset(
                        document_id=document_id,
                        original_filename=filename,
                        content=image.blob,
                        media_type=image.content_type,
                        page=None,
                        slide=slide_number,
                        storage_dir=storage_dir,
                        surrounding_text=slide_text,
                    ))
    except Exception as exc:
        logger.exception("Failed to extract embedded media from %s", path.name)
        warnings.append(f"Could not extract embedded media from {path.name}: {type(exc).__name__}.")
    return list({asset.asset_id: asset for asset in assets}.values()), warnings


# ---------------------------------------------------------------------------
# Lecture content assembly
# ---------------------------------------------------------------------------


def _join_lecture_content(
    units: Sequence[_TextUnit], warnings: list[str]
) -> str:
    parts: list[str] = []
    seen: set[str] = set()
    total_chars = 0

    for unit in units:
        text = unit.text.strip()
        key = _normalise_for_comparison(text)
        if not key or key in seen:
            continue
        seen.add(key)
        provenance = f"[{unit.document_name}"
        if unit.page_number is not None:
            provenance += f", page/slide {unit.page_number}"
        if unit.section_title:
            provenance += f", section: {unit.section_title}"
        provenance += "]"
        chunk = f"{provenance}\n{text}"

        remaining = MAX_LECTURE_CONTENT_CHARS - total_chars
        if remaining <= 0:
            warnings.append(
                f"Lecture content exceeded {MAX_LECTURE_CONTENT_CHARS:,} characters; "
                "additional extracted text was omitted from the context payload."
            )
            break
        if len(chunk) > remaining:
            parts.append(chunk[:remaining])
            warnings.append(
                f"Lecture content was truncated at {MAX_LECTURE_CONTENT_CHARS:,} characters."
            )
            break
        parts.append(chunk)
        total_chars += len(chunk) + 2

    return "\n\n".join(parts)[:MAX_LECTURE_CONTENT_CHARS]


__all__ = [
    "DocumentInput",
    "preprocess_documents",
]
