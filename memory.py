"""DejaVu memory layer.

Hindsight is DejaVu's long-term memory:
- save_incident()  -> RETAIN: store a past incident (error, cause, fix, outcome)
- recall_similar() -> RECALL: find past incidents that look like a new error
"""
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from hindsight_client import Hindsight

load_dotenv()

BANK_ID = "dejavu-incidents"
DATA_FILE = Path(__file__).parent / "incidents.json"

client = Hindsight(base_url=os.getenv("HINDSIGHT_BASE_URL", "http://localhost:8888"))


def load_incidents():
    """Read the past incidents from incidents.json."""
    return json.loads(DATA_FILE.read_text(encoding="utf-8"))


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
    client.create_bank(
        bank_id=BANK_ID,
        name="DejaVu incident memory",
        mission=(
            "Remember every production incident: the error signature, the root cause, "
            "the exact fix and whether it worked, so future outages are solved faster."
        ),
    )


def save_incident(inc):
    """RETAIN one incident in Hindsight memory."""
    client.retain(
        bank_id=BANK_ID,
        content=incident_to_text(inc),
        context="past production incident and how it was resolved",
        timestamp=inc["occurred_at"],
        document_id=f"incident-{inc['id']}",
        metadata={"incident_id": str(inc["id"]), "service": inc["service"]},
    )


def recall_similar(error_text, max_incidents=5):
    """RECALL past incidents similar to a new error.

    Returns a list like: [{"incident_id": 12, "facts": ["...", "..."]}, ...]
    ordered from best match to weakest.
    """
    response = client.recall(
        bank_id=BANK_ID,
        query=f"Past incidents similar to this error, with root cause and fix: {error_text}",
        budget="mid",
    )
    matches = {}
    for fact in response.results:
        incident_id = (fact.metadata or {}).get("incident_id")
        if not incident_id and fact.document_id:
            incident_id = fact.document_id.replace("incident-", "")
        if not incident_id or not str(incident_id).isdigit():
            continue
        matches.setdefault(int(incident_id), []).append(fact.text)
    return [
        {"incident_id": iid, "facts": facts}
        for iid, facts in list(matches.items())[:max_incidents]
    ]
