import os
import threading
from collections import OrderedDict
from copy import deepcopy

from v2.contracts import V2Error, check, compose, request_dto
from v2.store import relevance_key


def synthetic_enabled():
    # Existing synthetic gate or a separately mounted, reviewed deployment artifact.
    from v2.deployment import approved_release
    return os.getenv("AI_V2_PROFILE") == "synthetic-test" and os.getenv("AI_V2_ENABLED") == "1" or approved_release()


class RequestRegistry:
    """Bounded process-local receipts; failures keep identity until eviction/restart."""
    def __init__(self, capacity=1000):
        self.capacity, self.entries = capacity, OrderedDict()

    def begin(self, request_id, fingerprint, prefix):
        entry = self.entries.get(request_id)
        if entry is not None:
            if entry["fingerprint"] != fingerprint:
                raise V2Error(409, prefix + "_ID_CONFLICT")
            if entry["running"]:
                raise V2Error(409, prefix + "_IN_PROGRESS")
            self.entries.move_to_end(request_id)
            if entry["response"] is not None:
                return deepcopy(entry["response"]), entry
        else:
            while len(self.entries) >= self.capacity:
                key = next((k for k, v in self.entries.items() if not v["running"]), None)
                if key is None:
                    raise V2Error(503, "AI_NOT_READY")
                del self.entries[key]
            entry = {"fingerprint": fingerprint, "response": None, "running": False}
            self.entries[request_id] = entry
        entry["running"] = True
        return None, entry


class V2Service:
    def __init__(self, inference_lock=None, capacity=1000, privacy_store=None, result_store=None):
        self.model = None
        self.lock = threading.RLock()
        self.inference_lock = inference_lock or threading.Lock()
        self.compositions, self.analyses = RequestRegistry(capacity), RequestRegistry(capacity)
        self.generation = 0
        self.blocked_visits = set()
        self.blocked_sessions = set()
        self.privacy_store = privacy_store
        self.privacy_revision = -1
        # Optional durable results (v2.store.AnalysisResultStore); None keeps memory-only receipts.
        self.result_store = result_store

    def load(self, legacy_state):
        if not synthetic_enabled():
            return
        try:
            from models.context import LocalContextModel
            from models.embedding import LocalSemanticEmbeddingModel
            from v2.model import PageAnalysisModel
            pipeline = legacy_state.pipeline
            embedding = pipeline.embedding_model if pipeline else LocalSemanticEmbeddingModel()
            context = (pipeline.context_model if pipeline and pipeline.context_model is not None
                       else LocalContextModel())
            with self.inference_lock:
                if not pipeline:
                    embedding.warm_up()
                model = PageAnalysisModel(embedding, context)
                model.warm_up()
            with self.lock:
                self.model = model
        except Exception:
            # Model exceptions can carry source text or paths; no exception dump.
            print("[API v2] AI_NOT_READY")

    def refresh_privacy(self):
        if self.privacy_store is None:
            return
        with self.lock:
            revision, sessions, visits = self.privacy_store.snapshot()
            if revision != self.privacy_revision:
                self.blocked_sessions.update(sessions)
                self.invalidate_visits(visits)
                if self.result_store is not None:
                    # Raises AI_NOT_READY on failure; the revision stays stale so it is retried.
                    self.result_store.delete_retracted(session_ids=sessions)
                self.privacy_revision = revision

    def _privacy_check(self, body):
        self.refresh_privacy()
        if body["sessionId"] in self.blocked_sessions or any(v["visitId"] in self.blocked_visits for v in body["visits"]):
            raise V2Error(409, "PRIVACY_RETRACTED")

    def execute(self, kind, payload):
        body = request_dto("CompositionRequest" if kind == "compose" else "AnalysisRequest", payload)
        if not synthetic_enabled():
            raise V2Error(503, "AI_NOT_READY")
        prefix = "COMPOSE" if kind == "compose" else "ANALYSIS"
        key = body["composeRequestId" if kind == "compose" else "analysisId"]
        registry = self.compositions if kind == "compose" else self.analyses
        with self.lock:
            self._privacy_check(body)  # Quarantine before receipt replay.
            model = self.model
            if kind != "compose" and model is None:
                raise V2Error(503, "AI_NOT_READY")
            store = self.result_store if kind != "compose" else None
            if store is not None:
                stored = store.get_analysis(key)
                if stored is not None:
                    if stored[0] != body["inputFingerprint"]:
                        raise V2Error(409, "ANALYSIS_ID_CONFLICT")
                    if stored[1] == "COMPLETED":
                        return check("AnalysisResponse", stored[2])  # Durable replay after restart.
            cached, token = registry.begin(key, body["inputFingerprint"], prefix)
            if cached is not None:
                return cached
            generation = self.generation
            cache_generation = model.embedding.cache_generation if model is not None else None
        try:
            if kind == "compose":
                response = compose(body)
            else:
                # Bounded queue wait. generate(max_time) is a soft per-step timeout.
                if not self.inference_lock.acquire(timeout=model.timeout_seconds):
                    raise V2Error(500, "AI_ANALYSIS_FAILED")
                try:
                    with self.lock:
                        self._privacy_check(body)
                        if generation != self.generation:
                            raise V2Error(409, "PRIVACY_RETRACTED")
                    if store is None:
                        response = model.analyze(body, cache_generation)
                    else:
                        embedding_model = model.embedding.model_name
                        response = model.analyze(body, cache_generation, cached_relevance=lambda v: store.get_relevance(
                            relevance_key(body["sessionId"], body["goalText"], v, embedding_model)))
                finally:
                    self.inference_lock.release()
            response = check("CompositionResponse" if kind == "compose" else "AnalysisResponse", response)
            echo_fields = ("apiContractVersion", "sessionId", "inputFingerprint",
                           "composeRequestId" if kind == "compose" else "analysisId")
            if any(response[k] != body[k] for k in echo_fields):
                raise ValueError("invalid response identity")
            if kind != "compose":
                if response["windowId"] != body["windowId"] or any(
                        (p["position"], p["visitId"]) != (v["position"], v["visitId"])
                        for p, v in zip(response["pageResults"], body["visits"])):
                    raise ValueError("invalid response pairing")
            with self.lock:
                self._privacy_check(body)
                if generation != self.generation:
                    raise V2Error(409, "PRIVACY_RETRACTED")
                if store is not None:
                    # Persist inside the privacy-checked section so a retraction cannot race it.
                    store.save_completed(body, response, model.embedding.model_name)
                token["response"], token["running"] = deepcopy(response), False
            return response
        except BaseException as exc:
            with self.lock:
                token["running"] = False
            if store is not None and isinstance(exc, Exception):
                self._record_failure(store, body, exc, generation)
            if isinstance(exc, V2Error) and exc.status != 422:
                raise
            if not isinstance(exc, Exception):
                raise
            raise V2Error(500, "AI_COMPOSITION_FAILED" if kind == "compose" else "AI_ANALYSIS_FAILED") from None

    def _record_failure(self, store, body, exc, generation):
        """Keep UNJUDGEABLE (insufficient evidence) apart from ANALYSIS_FAILED (error/timeout).
        Privacy, conflict, readiness and request errors are not analysis outcomes."""
        from v2.model import Unjudgeable
        if isinstance(exc, V2Error) and exc.code != "AI_ANALYSIS_FAILED":
            return
        status = "UNJUDGEABLE" if isinstance(exc, Unjudgeable) else "ANALYSIS_FAILED"
        with self.lock:
            try:
                self._privacy_check(body)
                if generation != self.generation:
                    return
                store.save_failure(body, status, "AI_ANALYSIS_FAILED")
            except V2Error:
                pass  # The original analysis error is still returned unchanged.

    def invalidate_visits(self, visit_ids):
        """Internal quarantine hook, NOT deletion or an authenticated BE retraction API.

        Conservatively clears all v2 receipts and all shared embedding entries.
        A configured shared journal restores tombstones and clears stale local caches on use.
        Other processes/GPU memory are not physically erased by this acknowledgement.
        """
        with self.lock:
            self.blocked_visits.update(visit_ids)
            self.generation += 1
            self.compositions.entries.clear()
            self.analyses.entries.clear()
            if self.model is not None:
                self.model.embedding.invalidate_cache()
            if self.result_store is not None:
                self.result_store.delete_retracted(visit_ids=visit_ids)
