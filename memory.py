"""DejaVu memory layer.

Hindsight is DejaVu's long-term memory:
- save_incident()  -> RETAIN: store a past incident (error, cause, fix, outcome)
- recall_similar() -> RECALL: find past incidents that look like a new error
- reflect_lessons() -> REFLECT: reason over ALL incidents to answer a big-picture question
"""
import asyncio
import json
import os
from contextlib import contextmanager
from pathlib import Path

from dotenv import load_dotenv
from hindsight_client import Hindsight

load_dotenv()

BANK_ID = "dejavu-incidents"
DATA_FILE = Path(__file__).parent / "incidents.json"
LEARNED_FILE = Path(__file__).parent / "learned_incidents.json"  # new incidents learned live

BASE_URL = os.getenv("HINDSIGHT_BASE_URL", "http://localhost:8888")


@contextmanager
def memory_client():
    """Open a Hindsight connection for one operation, then close it.

    Streamlit runs every click in a new thread with its own event loop, so one
    shared client breaks ("Timeout context manager should be used inside a task").
    A short-lived client per call works everywhere: scripts and the web app.
    """
    client = Hindsight(base_url=BASE_URL)
    try:
        yield client
    finally:
        client.close()


def load_incidents():
    """All incidents DejaVu knows: the history file plus anything learned live."""
    incidents = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    if LEARNED_FILE.exists():
        incidents += json.loads(LEARNED_FILE.read_text(encoding="utf-8"))
    return incidents


def learn_new_incident(inc):
    """LEARNING STEP: keep a new resolved incident locally and retain it in Hindsight.

    retain_async=True lets the memory server do the heavy reading in the
    background (and retry if the free tier is busy) so the UI never freezes.
    """
    save_incident(inc, background=True)  # first, so a memory-server error saves nothing half-way
    learned = json.loads(LEARNED_FILE.read_text(encoding="utf-8")) if LEARNED_FILE.exists() else []
    learned.append(inc)
    LEARNED_FILE.write_text(json.dumps(learned, indent=2), encoding="utf-8")


def incident_to_text(inc):
    """Turn one incident into a plain-English memory."""
    steps = " ".join(f"({i}) {s}." for i, s in enumerate(inc["resolution_steps"], 1))
    outcome = "The fix WORKED." if inc["fix_successful"] else "The fix FAILED."
    return (
        f"Incident #{inc['id']} on service {inc['service']}: {inc['title']}.\n"
        f"Error seen: {inc['error_signature']}\n"
        f"Root cause: {inc['root_cause']}\n"
        f"Resolution steps: {steps}\n"
        f"{outcome} Time to resolve: {inc['time_to_resolve_minutes']} minutes."
    )


def setup_bank():
    """Create the memory bank and tell it what it is for."""
    with memory_client() as client:
        client.create_bank(
            bank_id=BANK_ID,
            name="DejaVu incident memory",
            mission=(
                "Remember every production incident: the error signature, the root cause, "
                "the exact fix and whether it worked, so future outages are solved faster."
            ),
        )


def save_incident(inc, background=False):
    """RETAIN one incident in Hindsight memory."""
    with memory_client() as client:
        client.retain(
            bank_id=BANK_ID,
            content=incident_to_text(inc),
            context="past production incident and how it was resolved",
            timestamp=inc["occurred_at"],
            document_id=f"incident-{inc['id']}",
            metadata={"incident_id": str(inc["id"]), "service": inc["service"]},
            retain_async=background,
        )


def recall_similar(error_text, max_incidents=5):
    """RECALL past incidents similar to a new error.

    Returns the best matches first, like:
    [{"incident_id": 12, "match": 0.91, "facts": ["...", "..."]}, ...]
    "match" is Hindsight's relevance score (0 to 1) for the best fact of that incident.
    """
    with memory_client() as client:
        response = client.recall(bank_id=BANK_ID, query=error_text, budget="mid")
    matches = {}
    for fact in response.results:
        incident_id = (fact.metadata or {}).get("incident_id")
        if not incident_id and fact.document_id:
            incident_id = fact.document_id.replace("incident-", "")
        if not incident_id or not str(incident_id).isdigit():
            continue
        # Rank by pure relevance (reranker), not recency, so old incidents still win.
        scores = fact.scores
        score = 0.0
        if scores is not None:
            score = scores.reranker if scores.reranker is not None else scores.final
        entry = matches.setdefault(int(incident_id), {"incident_id": int(incident_id), "match": 0.0, "facts": []})
        entry["match"] = max(entry["match"], float(score or 0.0))
        entry["facts"].append(fact.text)
    ranked = sorted(matches.values(), key=lambda m: m["match"], reverse=True)
    return ranked[:max_incidents]


LIGHT_REFLECT = dict(  # keep reflect inside Groq's free tier (about 8k tokens a minute)
    budget="low", max_tokens=700, exclude_mental_models=True,
    reflect_search_observations_max_tokens=1500, reflect_search_observations_include_entities=False,
)


def reflect_lessons(question):
    """REFLECT: Hindsight reasons over the whole memory and answers in plain English.

    recall() returns the facts closest to one error; reflect() looks across every
    incident, so it can spot what keeps breaking and which fixes never stick.
    Returns (markdown_answer, number_of_memories_it_used).

    Reflect runs several AI steps, so it uses the async client inside its own fresh
    event loop: Streamlit's worker threads can hold a stale loop that breaks the
    sync wrapper for long calls.
    """
    async def run():
        client = Hindsight(base_url=BASE_URL)
        try:
            try:
                call = client.areflect(bank_id=BANK_ID, query=question, include_facts=True, **LIGHT_REFLECT)
            except TypeError:  # older hindsight-client without the token-saving options
                call = client.areflect(bank_id=BANK_ID, query=question, budget="low")
            return await asyncio.wait_for(call, timeout=120)
        finally:
            await client.aclose()

    response = asyncio.run(run())
    based_on = getattr(response, "based_on", None)
    return response.text, len(getattr(based_on, "memories", None) or [])
