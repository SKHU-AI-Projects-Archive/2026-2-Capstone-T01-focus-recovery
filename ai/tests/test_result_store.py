"""Issue #116: durable v2 analysis results, embedding-score reuse and retraction deletion."""
import os
import sqlite3
import uuid

import pytest

import main
from conftest import FakeContext, FakeEmbedding, analysis_request, signed
from v2.contracts import V2Error, check
from v2.model import PageAnalysisModel
from v2.retractions import RetractionJournal
from v2.service import V2Service
from v2.store import AnalysisResultStore, result_store_from_env

ANALYZE = "/api/ai/analyses"
INSUFFICIENT = '{"error":"INSUFFICIENT_EVIDENCE"}'


@pytest.fixture
def stored(client, tmp_path):
    http, service = client
    service.result_store = AnalysisResultStore(tmp_path / "results.db")
    return http, service, service.result_store


def restart(monkeypatch, store, context=None):
    """A fresh process: empty memory receipts and embedding cache, same result DB."""
    service = V2Service(main.state.inference_lock, result_store=store)
    service.model = PageAnalysisModel(FakeEmbedding(), context or FakeContext())
    monkeypatch.setattr(main, "v2_service", service)
    return service


def renamed(body):
    body = dict(body, analysisId=str(uuid.uuid4()))
    return signed(body)


def status_of(store, analysis_id):
    stored = store.get_analysis(analysis_id)
    return stored and stored[1]


def test_completed_result_persisted_with_page_rows(stored):
    http, _, store = stored
    body = analysis_request()
    response = http.post(ANALYZE, json=body)
    assert response.status_code == 200, response.text
    fingerprint, status, saved = store.get_analysis(body["analysisId"])
    assert (fingerprint, status, saved) == (body["inputFingerprint"], "COMPLETED", response.json())
    rows = store.page_results(body["analysisId"])
    assert [(r[0], r[1], r[2]) for r in rows] == [
        (p["position"], p["visitId"], p["label"]) for p in response.json()["pageResults"]]
    assert [r[3] for r in rows] == [p["semanticRelevance"] for p in response.json()["pageResults"]]


def test_replay_after_restart_without_inference(stored, monkeypatch):
    http, _, store = stored
    body = analysis_request()
    first = http.post(ANALYZE, json=body).json()
    context = FakeContext()
    context.outputs = [RuntimeError("must not run")]
    service = restart(monkeypatch, store, context)
    response = http.post(ANALYZE, json=body)
    assert response.status_code == 200 and response.json() == first
    assert context.calls == [] and service.model.embedding.calls == []
    check("AnalysisResponse", response.json())


def test_different_fingerprint_conflicts_after_restart(stored, monkeypatch):
    http, _, store = stored
    body = analysis_request()
    assert http.post(ANALYZE, json=body).status_code == 200
    restart(monkeypatch, store)
    changed = dict(body, windowIndex=body["windowIndex"] + 1)
    response = http.post(ANALYZE, json=signed(changed))
    assert response.status_code == 409 and response.json()["code"] == "ANALYSIS_ID_CONFLICT"


def test_embedding_scores_reused_across_windows(stored, monkeypatch):
    http, _, store = stored
    body = analysis_request()
    first = http.post(ANALYZE, json=body).json()
    service = restart(monkeypatch, store)
    second = http.post(ANALYZE, json=renamed(body))
    assert second.status_code == 200
    assert service.model.embedding.calls == []  # All three pages already scored.
    assert [p["semanticRelevance"] for p in second.json()["pageResults"]] == \
        [p["semanticRelevance"] for p in first["pageResults"]]


def test_changed_page_or_goal_is_rescored(stored, monkeypatch):
    http, _, store = stored
    body = analysis_request()
    assert http.post(ANALYZE, json=body).status_code == 200
    service = restart(monkeypatch, store)
    changed = renamed(body)
    changed["visits"] = [dict(v) for v in body["visits"]]
    changed["visits"][2]["content"] += " 변경된 본문입니다."
    assert http.post(ANALYZE, json=signed(changed)).status_code == 200
    assert len(service.model.embedding.calls) == 1  # Only the edited page.
    other_goal = signed(dict(renamed(body), goalText="다른 공개 문서 정리하기"))
    assert http.post(ANALYZE, json=other_goal).status_code == 200
    assert len(service.model.embedding.calls) == 4


def test_unjudgeable_and_failed_are_distinct_and_retryable(stored):
    http, service, store = stored
    body = analysis_request()
    service.model.context.outputs = [INSUFFICIENT, INSUFFICIENT]
    response = http.post(ANALYZE, json=body)
    assert response.status_code == 500 and response.json()["code"] == "AI_ANALYSIS_FAILED"
    assert status_of(store, body["analysisId"]) == "UNJUDGEABLE"
    assert [r[2] for r in store.page_results(body["analysisId"])] == [None, None, None]

    service.model.context.outputs = ["not json", INSUFFICIENT]
    assert http.post(ANALYZE, json=body).status_code == 500
    assert status_of(store, body["analysisId"]) == "ANALYSIS_FAILED"

    # A stored failure never blocks the same request from being retried.
    assert http.post(ANALYZE, json=body).status_code == 200
    assert status_of(store, body["analysisId"]) == "COMPLETED"
    service.model.context.outputs = [INSUFFICIENT, INSUFFICIENT]
    service.analyses.entries.clear()
    assert http.post(ANALYZE, json=body).status_code == 200  # Completed replay, not downgraded.
    assert status_of(store, body["analysisId"]) == "COMPLETED"


def test_inference_exception_recorded_as_failed(stored):
    http, service, store = stored
    body = analysis_request()
    service.model.context.outputs = [RuntimeError("PRIVATE_TITLE")]
    assert http.post(ANALYZE, json=body).status_code == 500
    assert status_of(store, body["analysisId"]) == "ANALYSIS_FAILED"


def test_page_text_and_goal_never_written(stored, tmp_path):
    http, _, store = stored
    body = analysis_request()
    assert http.post(ANALYZE, json=body).status_code == 200
    raw = (tmp_path / "results.db").read_bytes()
    for text in [body["goalText"], *(v["title"] for v in body["visits"]),
                 *(v["content"][:20] for v in body["visits"])]:
        assert text.encode("utf-8") not in raw


def test_visit_retraction_deletes_results(stored):
    http, service, store = stored
    body = analysis_request()
    assert http.post(ANALYZE, json=body).status_code == 200
    service.invalidate_visits({body["visits"][1]["visitId"]})
    assert store.get_analysis(body["analysisId"]) is None
    with sqlite3.connect(store.path) as db:
        assert db.execute("SELECT COUNT(*) FROM page_result").fetchone()[0] == 0
        visits = {r[0] for r in db.execute("SELECT visit_id FROM page_relevance")}
    assert body["visits"][1]["visitId"] not in visits
    response = http.post(ANALYZE, json=body)
    assert response.status_code == 409 and response.json()["code"] == "PRIVACY_RETRACTED"


def test_journal_session_retraction_deletes_results(stored, tmp_path):
    http, service, store = stored
    body = analysis_request()
    assert http.post(ANALYZE, json=body).status_code == 200
    journal = RetractionJournal(tmp_path / "journal.db")
    service.privacy_store = journal
    journal.retract(str(uuid.uuid4()), body["sessionId"], str(uuid.uuid4()))
    service.refresh_privacy()
    with sqlite3.connect(store.path) as db:
        assert db.execute("SELECT COUNT(*) FROM window_analysis").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM page_relevance").fetchone()[0] == 0


def test_store_failure_fails_closed(stored, monkeypatch):
    http, _, store = stored

    def broken(*args, **kwargs):
        raise V2Error(503, "AI_NOT_READY")
    monkeypatch.setattr(store, "save_completed", broken)
    response = http.post(ANALYZE, json=analysis_request())
    assert response.status_code == 503 and response.json()["code"] == "AI_NOT_READY"


def test_schema_version_and_permissions(tmp_path):
    path = tmp_path / "results.db"
    AnalysisResultStore(path)
    AnalysisResultStore(path)  # Reopening an existing DB is idempotent.
    with sqlite3.connect(path) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 1
        db.execute("PRAGMA user_version = 99")
    with pytest.raises(V2Error) as error:
        AnalysisResultStore(path)
    assert error.value.code == "AI_NOT_READY"
    if os.name != "nt":
        assert path.stat().st_mode & 0o777 == 0o600


def test_persistence_is_opt_in(monkeypatch, tmp_path):
    monkeypatch.delenv("AI_V2_RESULT_DB", raising=False)
    assert result_store_from_env() is None
    monkeypatch.setenv("AI_V2_RESULT_DB", str(tmp_path / "env.db"))
    assert isinstance(result_store_from_env(), AnalysisResultStore)
