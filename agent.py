"""DejaVu agent brain.

Flow: new error -> RECALL similar incidents from Hindsight -> GPT (via Groq)
reasons over them -> structured answer the UI can show.
"""
import json
import os

from dotenv import load_dotenv
from groq import Groq

from memory import load_incidents, recall_similar

load_dotenv()

MODEL = "openai/gpt-oss-120b"
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

SYSTEM_PROMPT = """You are DejaVu, an incident-response assistant with long-term memory
of past production incidents. You receive a NEW error plus PAST incidents recalled
from memory. Reply ONLY with JSON in exactly this shape:
{
  "probable_cause": "one or two sentences",
  "confidence": 0-100,
  "evidence": [{"incident_id": 12, "why": "short reason it matches"}],
  "fix_steps": ["step 1", "step 2", "step 3"],
  "estimated_minutes": 5,
  "summary": "one punchy sentence for the on-call engineer"
}
Rules:
- Never invent incidents. Only cite incident_id values that appear in PAST INCIDENTS.
- Confidence must come from evidence. Use this scale:
  * 3 or more past incidents with the SAME root cause whose fix WORKED -> 90 to 98
  * 2 such incidents -> 75 to 89
  * 1 such incident -> 55 to 74
  * only loosely related incidents -> 31 to 54
- Cite EVERY past incident that shares the root cause in evidence, not just one.
- If PAST INCIDENTS is empty or nothing truly matches: evidence = [], confidence <= 30,
  and summary must start with "No similar incident in memory".
- estimated_minutes: base it on the resolve times of matching incidents (recent ones count more).
"""


def get_incident(incident_id):
    """Look up the full record of an incident (including ones learned live)."""
    return next((inc for inc in load_incidents() if inc["id"] == incident_id), None)


def describe(incident_id):
    inc = get_incident(incident_id)
    if not inc:
        return None
    return (
        f"Incident #{inc['id']} ({inc['service']}, {inc['occurred_at'][:10]}): {inc['title']}\n"
        f"  Error: {inc['error_signature'][:300]}\n"
        f"  Root cause: {inc['root_cause']}\n"
        f"  Fix: {' | '.join(inc['resolution_steps'])}\n"
        f"  Fix worked: {inc['fix_successful']}, resolved in {inc['time_to_resolve_minutes']} min"
    )


def analyse(error_text, use_memory=True):
    """Return (answer_dict, recalled_matches)."""
    matches = recall_similar(error_text) if use_memory else []
    past = "\n\n".join(filter(None, (describe(m["incident_id"]) for m in matches))) or "(none)"

    reply = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"NEW ERROR:\n{error_text}\n\nPAST INCIDENTS:\n{past}"},
        ],
        response_format={"type": "json_object"},
        temperature=0.2,
    )
    answer = json.loads(reply.choices[0].message.content)

    # Safety net: drop any incident the model cited that memory did not recall.
    recalled_ids = {m["incident_id"] for m in matches}
    answer["evidence"] = [e for e in answer.get("evidence", []) if e.get("incident_id") in recalled_ids]
    answer["confidence"], answer["confidence_basis"] = calibrate(answer)
    return answer, matches


def calibrate(answer):
    """Ground the confidence in what memory proves, using the same scale as the prompt.

    Counts the cited past incidents whose fix actually worked. Repeat outages with a
    proven fix earn high confidence; anything unproven is capped low.
    """
    cited = [get_incident(e["incident_id"]) for e in answer.get("evidence", [])]
    cited = [c for c in cited if c]
    proven = sum(1 for c in cited if c["fix_successful"])
    model = int(answer.get("confidence", 0) or 0)
    if proven >= 3:
        conf = min(98, max(model, 88 + 2 * proven))
    elif proven == 2:
        conf = min(max(model, 75), 89)
    elif proven == 1:
        conf = min(max(model, 55), 74)
    else:
        conf = min(model, 30)
    if not cited:
        basis = "No matching incident in memory"
    else:
        basis = f"{proven} of {len(cited)} matching past incidents were fixed this way"
    return conf, basis


def write_postmortem(error_text, answer):
    """Write a short blameless postmortem for a resolved incident."""
    reply = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": (
                "You write short blameless incident postmortems in Markdown with exactly these "
                "sections: ### Summary, ### Timeline, ### Root cause, ### Fix, ### Prevention. "
                "Max 160 words. Use bullet points.")},
            {"role": "user", "content": f"Error: {error_text}\n\nAnalysis: {json.dumps(answer)}"},
        ],
        temperature=0.3,
    )
    return reply.choices[0].message.content


if __name__ == "__main__":
    samples = {
        "cache bug (should match)": "KeyError: 'amount' reading cached object 'pay:txn:v1:9931' right after the v3.2 deploy",
        "database (should match)": "FATAL: remaining connection slots are reserved, max_connections=200 active=200",
        "unknown (should say no match)": "Printer on floor 3 is out of magenta ink",
    }
    for name, error in samples.items():
        answer, matches = analyse(error)
        print(f"\n=== {name} ===")
        print(f"Recalled incidents: {[m['incident_id'] for m in matches]}")
        print(json.dumps(answer, indent=2))
