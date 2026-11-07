"""Load all past incidents into DejaVu's Hindsight memory (run once).

The free Groq tier allows about 8,000 tokens per minute, and reading one
incident uses about 5,000, so we go slowly: one incident every ~40 seconds.
Re-running is safe: each incident has a fixed document_id, so it is updated,
not duplicated. To continue from a later incident: python load_memory.py 11
"""
import sys
import time

from memory import load_incidents, save_incident, setup_bank

WAIT_BETWEEN = 40  # seconds between incidents (free tier limit)
WAIT_RETRY = 30    # seconds to wait when the free tier says "slow down"

setup_bank()
START_ID = int(sys.argv[1]) if len(sys.argv) > 1 else 1
incidents = [inc for inc in load_incidents() if inc["id"] >= START_ID]
print(f"Teaching DejaVu {len(incidents)} past incidents (about 15 minutes on the free tier)...\n")

failed = []
for inc in incidents:
    for attempt in range(1, 7):
        try:
            save_incident(inc)
            print(f"  [OK] Remembered incident #{inc['id']}: {inc['title']}")
            break
        except Exception as err:
            reason = "free tier busy" if "rate limit" in str(err).lower() or "quota" in str(err).lower() else str(err)[:80]
            print(f"  [..] Incident #{inc['id']}: {reason}, waiting {WAIT_RETRY}s (try {attempt}/6)")
            time.sleep(WAIT_RETRY)
    else:
        failed.append(inc["id"])
        print(f"  [!!] Skipped incident #{inc['id']} - run this script again later to add it")
    time.sleep(WAIT_BETWEEN)

if failed:
    print(f"\nFinished, but these incidents were skipped: {failed}. Run the script again.")
else:
    print("\nDone! DejaVu now remembers every past incident.")
