"""Check that memory finds the right past incidents."""
from memory import recall_similar

tests = {
    "cache bug": "KeyError: 'amount' reading cached object 'pay:txn:v1:9931' right after deploy",
    "database": "FATAL: remaining connection slots are reserved, max_connections=200",
}

for name, error in tests.items():
    print(f"\n=== {name.upper()} ===\nError: {error}")
    matches = recall_similar(error)
    if not matches:
        print("  No similar incident in memory")
    for m in matches:
        print(f"  -> Incident #{m['incident_id']} (match {m['match']:.0%}): {m['facts'][0][:100]}")
