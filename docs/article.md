It's 3 a.m. Your phone buzzes. The payments service is throwing `KeyError: 'amount'` after a deploy, and customers can't pay.

You open the logs, then Slack, then old postmortems. Forty minutes later you find it: a stale Redis cache key from the old version. Then someone says the words every on-call engineer hates: *"Oh yeah, we had this exact problem in March."*

That sentence is the reason I built **DejaVu**, an AI incident agent that remembers every outage your team has ever fixed.

## The real problem: teams forget

Most outages are not new. The same few failures come back again and again: cache bugs, database connections running out, bad config, slow queues. They just look a little different each time. A different service, a different error message, a different person on call.

The fix usually exists somewhere. It's in an old Slack thread, a postmortem nobody reads, or the head of an engineer who is asleep or has left the company.

General AI chatbots don't solve this. They have never seen *your* systems. Ask one about your outage and it will give you a polite, generic guess. What on-call teams need is not a smarter guess. They need **memory**.

## What DejaVu does

DejaVu works in three simple steps: **recall, reason, retain.**

1. **Recall.** A new error comes in. DejaVu searches its long-term memory for past incidents with the same failure pattern, even when the words are completely different.
2. **Reason.** An LLM (GPT-OSS 120B, running on Groq) reads only those recalled incidents and returns a root cause, a step-by-step fix, a time estimate, and the exact past incidents it used as proof. It is not allowed to cite anything memory didn't return.
3. **Retain.** When the engineer clicks **Fix worked** or **Fix failed**, that outcome is saved as a new memory. The next outage gets solved faster.

The memory layer is [Hindsight](https://github.com/vectorize-io/hindsight), an open-source agent memory system by Vectorize. If you're new to the idea, Vectorize has a good explainer on [what agent memory is](https://vectorize.io/what-is-agent-memory) and why it's different from simply stuffing documents into a prompt.

## Same AI, with and without memory

The moment that convinced me this works is the side-by-side test in the app.

I simulate the cache `KeyError` outage and ask the **same model** twice:

- **Without memory:** 20% confidence. *"Likely a schema mismatch after deploy. Check the code and cache."* A reasonable guess, but still a guess.
- **With Hindsight memory:** **98% confidence.** *"Redis cache invalidation bug after the v3.2 deploy, leaving stale v1 keys."* It gives the exact commands to flush the keys and restart the pods, and it cites 5 past incidents where this fix worked.

Same model. Same prompt. The only difference is memory.

## Why keyword search isn't enough

In my dataset of 20 incidents, the cache bug happens 6 times, on 3 different services, with 6 different error messages: `KeyError`, `TypeError` on a cart object, HTTP 500s, *"password reset tokens rejected as expired"*, and *"promo codes ignored at checkout"*.

A keyword search for "KeyError" finds one or two of these. Hindsight's semantic recall finds all of them, because it matches on **meaning**, not on words. That's what lets DejaVu say *"seen this 5 times, and this fix worked every time"*.

## How Hindsight is used

Hindsight is the core of the project, not an add-on. DejaVu uses four of its operations:

- **create_bank** makes a memory bank called `dejavu-incidents`, with a mission: remember each incident's error, root cause, exact fix and whether it worked.
- **retain** stores each incident as plain English, with its real timestamp, a stable `document_id` (so re-runs update instead of duplicating), and metadata like the service name.
- **recall** finds similar past incidents for a new error.
- **reflect** answers big-picture questions across *all* incidents, like *"What keeps breaking?"*

Here is the recall step. Hindsight returns facts, and I group them by incident and rank them by the reranker's relevance score, not by recency, so an old but identical outage still wins:

```python
def recall_similar(error_text, max_incidents=5):
    with memory_client() as client:
        response = client.recall(bank_id=BANK_ID, query=error_text, budget="mid")
    matches = {}
    for fact in response.results:
        incident_id = int((fact.metadata or {}).get("incident_id"))
        scores = fact.scores
        score = scores.reranker if scores.reranker is not None else scores.final
        entry = matches.setdefault(incident_id, {"incident_id": incident_id, "match": 0.0, "facts": []})
        entry["match"] = max(entry["match"], float(score or 0))
        entry["facts"].append(fact.text)
    return sorted(matches.values(), key=lambda m: m["match"], reverse=True)[:max_incidents]
```

The [Hindsight docs](https://hindsight.vectorize.io) cover retain, recall and reflect in detail. I ran the Hindsight server locally, with Groq as its LLM provider, so the whole stack is free to run.

## Confidence you can trust

I didn't want the AI to just *say* it was 98% sure. So the confidence score comes from memory, not from the model's mood:

- 3 or more past incidents where the same fix worked: 90 to 98%
- 2 proven matches: 75 to 89%
- 1 proven match: 55 to 74%
- Nothing proven: 30% or less, and it says *"No similar incident in memory"*

Under the score, the app shows the reason in plain words, like *"5 of 5 matching past incidents were fixed this way."* Engineers can check every claim.

## It learns while you use it

The part I enjoy most is watching it learn. When I click **Fix worked**, the incident is retained in Hindsight in the background. A new green dot appears on the live memory map, and the next time the same alert fires, that fresh incident is often the best match.

The learning curve tells the story. Across the 20 incidents, the average time to fix fell from **44 minutes** for the first 5 to **6 minutes** for the last 5. That's **87% faster** as the memory grew.

There's also a **Lessons from memory** panel. A team lead can ask *"What keeps breaking?"* or *"Which fixes failed, and why?"*, and Hindsight's reflect reasons over every incident to answer, with incident numbers as proof.

## What I learned building it

- **Memory beats a bigger model.** The jump from 20% to 98% came from memory, not from a smarter LLM.
- **Rank by relevance, not recency.** My first version preferred recent incidents, and it missed old outages that were identical. The reranker score fixed that.
- **Ground every claim.** Forcing the model to cite only recalled incidents, and dropping any it made up, made the answers far more trustworthy.
- **Plan for free-tier limits.** Groq's free tier allows about 8,000 tokens a minute, so the loader paces itself and the app has a fallback when reflect is busy.

## Try it

DejaVu is open source and runs on a laptop:

- Code: https://github.com/Pratheeksh-7S/dejavu-incident-agent
- 3-minute demo: https://youtu.be/Nu_sktguGMk
- Hindsight: https://github.com/vectorize-io/hindsight

On-call will always be stressful. But it shouldn't mean solving the same outage twice. With memory, every outage you fix makes the next one easier.

*Every outage, remembered.*
