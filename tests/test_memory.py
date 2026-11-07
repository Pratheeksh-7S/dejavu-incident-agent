from types import SimpleNamespace as NS

import memory


def fact(text, incident_id=None, reranker=None, final=None, document_id=None, scores=True):
    return NS(
        text=text,
        metadata={"incident_id": str(incident_id)} if incident_id is not None else None,
        document_id=document_id,
        scores=NS(reranker=reranker, final=final) if scores else None,
    )


class FakeClient:
    def __init__(self, results):
        self.results = results
        self.calls = []
        self.closed = False

    def recall(self, **kwargs):
        self.calls.append(kwargs)
        return NS(results=self.results)

    def close(self):
        self.closed = True


def run_recall(monkeypatch, results, **kwargs):
    fake = FakeClient(results)
    monkeypatch.setattr(memory, "Hindsight", lambda base_url: fake)
    return memory.recall_similar("boom", **kwargs), fake


def test_groups_facts_per_incident(monkeypatch):
    results = [
        fact("a1", 1, reranker=0.5),
        fact("b1", 2, reranker=0.7),
        fact("a2", 1, reranker=0.6),
    ]
    out, fake = run_recall(monkeypatch, results)
    by_id = {m["incident_id"]: m for m in out}
    assert set(by_id) == {1, 2}
    assert by_id[1]["facts"] == ["a1", "a2"]
    assert by_id[2]["facts"] == ["b1"]
    assert by_id[1]["match"] == 0.6  # best fact score
    assert fake.calls[0]["query"] == "boom"
    assert fake.closed


def test_ranked_by_reranker_score_descending(monkeypatch):
    results = [
        fact("low", 1, reranker=0.2, final=0.99),
        fact("high", 2, reranker=0.9, final=0.1),
        fact("mid", 3, reranker=0.5, final=0.5),
    ]
    out, _ = run_recall(monkeypatch, results)
    assert [m["incident_id"] for m in out] == [2, 3, 1]


def test_falls_back_to_final_score_when_no_reranker(monkeypatch):
    results = [fact("a", 1, reranker=None, final=0.3), fact("b", 2, reranker=None, final=0.8)]
    out, _ = run_recall(monkeypatch, results)
    assert [m["incident_id"] for m in out] == [2, 1]


def test_uses_document_id_when_metadata_missing_and_skips_junk(monkeypatch):
    results = [
        fact("doc", document_id="incident-7", reranker=0.4),
        fact("nonnumeric", 0, reranker=0.9),
        fact("no id", reranker=0.9),
    ]
    results[1].metadata = {"incident_id": "abc"}
    out, _ = run_recall(monkeypatch, results)
    assert [m["incident_id"] for m in out] == [7]


def test_limits_to_max_incidents(monkeypatch):
    results = [fact(f"f{i}", i, reranker=i / 10) for i in range(1, 8)]
    out, _ = run_recall(monkeypatch, results, max_incidents=3)
    assert [m["incident_id"] for m in out] == [7, 6, 5]


def test_empty_results(monkeypatch):
    out, _ = run_recall(monkeypatch, [])
    assert out == []


class FakeReflectClient:
    def __init__(self, response):
        self.response, self.calls, self.closed = response, [], False

    async def areflect(self, **kwargs):
        self.calls.append(kwargs)
        return self.response

    async def aclose(self):
        self.closed = True


class OldReflectClient(FakeReflectClient):
    """An older hindsight-client that does not know include_facts."""

    def areflect(self, **kwargs):
        if "include_facts" in kwargs:
            raise TypeError("unexpected keyword argument 'include_facts'")
        return FakeReflectClient.areflect(self, **kwargs)


def test_reflect_returns_text_and_memory_count(monkeypatch):
    response = NS(text="Cache bug keeps coming back", based_on=NS(memories=[1, 2, 3]))
    fake = FakeReflectClient(response)
    monkeypatch.setattr(memory, "Hindsight", lambda base_url: fake)
    assert memory.reflect_lessons("what keeps breaking?") == ("Cache bug keeps coming back", 3)
    assert fake.calls[0]["bank_id"] == memory.BANK_ID
    assert fake.closed


def test_reflect_works_with_older_client(monkeypatch):
    fake = OldReflectClient(NS(text="ok"))
    monkeypatch.setattr(memory, "Hindsight", lambda base_url: fake)
    assert memory.reflect_lessons("q") == ("ok", 0)


def test_reflect_works_inside_a_worker_thread(monkeypatch):
    """Streamlit runs each click in a worker thread; reflect must work there too."""
    import threading
    fake = FakeReflectClient(NS(text="from thread"))
    monkeypatch.setattr(memory, "Hindsight", lambda base_url: fake)
    out = []
    t = threading.Thread(target=lambda: out.append(memory.reflect_lessons("q")))
    t.start()
    t.join()
    assert out == [("from thread", 0)]
