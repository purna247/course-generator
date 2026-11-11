"""Offline acceptance checks for coverage, media, assessment, and progression."""

from __future__ import annotations

import json
import py_compile
import sys
from collections import Counter
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi.testclient import TestClient

from backend.main import app
from backend.preprocessor import DocumentInput, preprocess_documents


def main() -> None:
    print("=== 1. BACKEND COMPILATION ===")
    for source in Path("backend").glob("*.py"):
        py_compile.compile(str(source), doraise=True)
    print("[PASS] backend source compiles.")

    print("=== 2. SOURCE INVENTORY AND LEDGER ===")
    documents = [
        DocumentInput(Path("sample_inputs/Brain Machine Interface_Syllabus.docx"), "syllabus", "doc_syllabus"),
        DocumentInput(Path("sample_inputs/BCI_Module_I_II_Questions.docx"), "exam_questions", "doc_questions"),
    ]
    first = preprocess_documents(documents)
    second = preprocess_documents(documents)
    assert len(first.modules) == 2  # Modules with uploaded questions (Modules 1 and 2) are retained; unuploaded modules are filtered out
    assert len(first.exam_questions) == len(first.question_coverage_ledger) > 0
    assert [question.question_id for question in first.exam_questions] == [question.question_id for question in second.exam_questions]
    assert all(question.source_type == "teacher_provided" for question in first.exam_questions)
    assert len(first.exam_questions) == 92
    assert Counter(question.marks for question in first.exam_questions) == Counter({2: 32, 5: 32, 10: 28})
    assert any(question.similarity_kind == "related" for question in first.exam_questions)
    assert len(first.media_assets) >= 1
    print(f"[PASS] {len(first.exam_questions)} original entries retained; {len(first.media_assets)} embedded asset(s) indexed; IDs are stable.")

    print("=== 3. OFFLINE GENERATION AND SERVER PROGRESSION ===")
    client = TestClient(app)
    with patch("backend.main.load_provider_configs", return_value=[]):
        load = client.post("/api/load-sample")
        assert load.status_code == 200
        job_id = load.json()["job_id"]
        generate = client.post(f"/api/generate/{job_id}", json={"course_id": "acceptance_course", "course_title": "Acceptance Course"})
        assert generate.status_code == 200
        status = client.get(f"/api/jobs/{job_id}")
        assert status.json()["status"] == "completed", status.json()
        course_response = client.get(f"/api/jobs/{job_id}/course")
        assert course_response.status_code == 200
        course = course_response.json()["course"]
        assert len(course["question_bank"]) == len(course["question_coverage_ledger"]) == len(first.exam_questions)
        assert all(module["nodes"] for module in course["modules"])
        assert all(any(node["node_type"] == "boss" for node in module["nodes"]) for module in course["modules"])
        assert course["coverage_stats"]["questions_mapped"] == len(first.exam_questions)

        progress = client.get("/api/courses/acceptance_course/progress").json()["progress"]
        assert progress["modules"][0]["unlocked"] is True
        assert all(module["unlocked"] is False for module in progress["modules"][1:])

        first_module = course["modules"][0]
        first_node = first_module["nodes"][0]
        opened = client.post("/api/courses/acceptance_course/progress", json={"event_type": "open_node", "node_id": first_node["node_id"]})
        assert opened.status_code == 200
        refreshed = client.get("/api/courses/acceptance_course/progress").json()["progress"]
        assert refreshed["modules"][1]["unlocked"] is False
        assert client.post("/api/courses/acceptance_course/progress", json={"event_type": "complete_node", "node_id": first_node["node_id"]}).status_code == 422

        boss = next(node for node in first_module["nodes"] if node["node_type"] == "boss")
        assert client.post("/api/courses/acceptance_course/progress", json={"event_type": "submit_boss", "assessment_id": boss["assessment"]["assessment_id"], "responses": {}}).status_code == 403
        assert client.get("/api/courses/acceptance_course/progress").json()["blueprint_unlocked"] is False

    print("[PASS] Dynamic modules publish with complete coverage, only Module I unlocks, node opening is insufficient, and empty Boss submission cannot unlock a blueprint.")

    print("=== 4. PERSISTENCE CHECK ===")
    state_file = Path("backend/data/jobs_state.json")
    saved = json.loads(state_file.read_text(encoding="utf-8"))
    assert job_id in saved and saved[job_id]["status"] == "completed"
    assert saved[job_id]["progress"]["modules"][0]["unlocked"] is True
    print("[PASS] Atomic JSON checkpoint contains the published course and authoritative progress.")
    print("\nALL OFFLINE ACCEPTANCE CHECKS PASSED")


if __name__ == "__main__":
    main()
