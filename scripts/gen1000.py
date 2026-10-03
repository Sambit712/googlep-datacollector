"""Generate 1000 synthetic EvidenceRecords + analytics for the dashboard."""
import json
import random
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

random.seed(42)
ROOT = Path(__file__).resolve().parent.parent

SUBREDDITS = {
    "primary": ["googlephotos", "GooglePixel", "Android", "iphone"],
    "discovery": ["photography", "techsupport"],
}

ALL_QUERIES = [
    "Google Photos search", "Google Photos cant find photo", "Google Photos old photo",
    "Google Photos screenshot search", "Google Photos search problem",
    "Google Photos search not working", "cant find old photo", "looking for old photo",
    "remember a photo but cant find it", "cant remember when photo was taken",
    "find old screenshot", "vague memory of a photo",
]

RELEVANCE_CLASSES = [("relevant", 0.28), ("possibly_relevant", 0.22), ("irrelevant", 0.50)]
FAILURE_STAGES = ["memory_to_query", "query_to_system", "system_to_candidate", "search_refinement"]
FAILURE_POINTS = ["vocabulary_mismatch", "volume_overload", "missing_metadata", "temporal_ambiguity", "face_recognition_gap"]
MEMORY_CUES = ["person", "place_location", "temporal_epoch", "object", "text_in_image", "event", "emotion", "color"]
WORKAROUNDS = ["endless_scrolling", "keyword_guessing", "abandonment", "date_range_search", "third_party_tool", "manual_album_browse"]
FRICTION = ["frustration_with_search_tool", "time_wasted", "cognitive_overload", "fear_of_memory_loss", "device_storage_anxiety", "ui_confusion", "result_irrelevance", "no_filter_options"]

TITLES_R = [
    "Cant find photos from 2019 anymore in Google Photos",
    "Google Photos cant find photos of my mom anymore",
    "Lost photos from my trip to Tokyo - search shows nothing",
    "Cant find my passport photo in Google Photos",
    "Google Photos AI search getting worse cant find obvious things",
    "Searching through 50k photos is impossible need better filters",
    "Cant find an old screenshot in Google Photos",
    "Looking for photos from my wedding Google Photos search fails",
    "Why did Google Photos ruin search for old photos",
    "Help finding old photo from 2016 in Google Photos",
    "Google Photos search broke after update cant find anything",
    "Trying to find a picture from years ago Google Photos useless",
    "Date search stopped working in Google Photos",
    "Face search in Google Photos not finding my child",
    "Google Photos cant locate photos from specific event",
]

TITLES_I = [
    "Google Photos storage full how do I free up space",
    "Google Photos sync not working on Samsung Galaxy",
    "How to share Google Photos album with family",
    "Google Photos app crashing constantly",
    "Google Photos backup taking too long",
    "How to download all photos from Google Photos",
    "Google Photos vs iCloud which is better",
    "Google Photos deleting photos from phone",
    "How to create albums in Google Photos",
    "Google Photos taking up too much storage",
]

BODIES_R = [
    "I used to be able to find this photo easily but now Google Photos search returns completely irrelevant results. I remember the photo clearly but cannot find it through any search terms I try.",
    "The new AI search in Google Photos is awful. When I search for specific photos I know exist, nothing comes up. I have had to resort to manually scrolling through thousands of images.",
    "My library has over 50k photos and searching for anything specific is nearly impossible. Google Photos search used to work great but has gotten significantly worse after recent updates.",
    "I need to find a photo I took a while back. I remember specific details about it but no matter what I search in Google Photos, I cannot locate it. Tried every combination of words.",
    "Google Photos search broke for me after the update. Searching by date used to work fine - typing a month and year would show photos from that period. Now it returns completely random results.",
    "I have thousands of photos and I know I took a photo at a specific event but I cannot find it. The face recognition used to help but now it doesnt group photos correctly.",
    "Every search I do in Google Photos gives me irrelevant results. I tried searching for a specific person in my photos and it showed me pictures of random people instead.",
    "Lost a very important photo in my Google Photos library. I remember when I took it and roughly what it looks like but the search just does not work the way it used to.",
]

BODIES_I = [
    "Looking for help with my Google Photos account. The app has been acting strange lately and I am not sure how to fix it.",
    "Having trouble with Google Photos on my new phone. The sync does not seem to be working properly despite having a good internet connection.",
    "Question about Google Photos storage. I want to manage my photos better but I am not sure how to free up space without losing photos.",
    "My Google Photos backup icon keeps spinning indefinitely. I have tried restarting the app and my phone but it will not complete the backup.",
    "I want to share my photo collection with family but I am having trouble setting up the shared album correctly.",
]


def pick_rel():
    r = random.random()
    c = 0.0
    for lbl, p in RELEVANCE_CLASSES:
        c += p
        if r < c:
            return lbl
    return "irrelevant"


def make_rec(idx, run_id):
    rel = pick_rel()
    is_rel = rel in ("relevant", "possibly_relevant")

    if is_rel:
        title = random.choice(TITLES_R)
        body = random.choice(BODIES_R)
        cues = random.sample(MEMORY_CUES, k=random.randint(1, 3))
        stage = random.choice(FAILURE_STAGES)
        point = random.choice(FAILURE_POINTS)
        conf = round(random.uniform(0.6, 0.98), 2)
        wk = random.sample(WORKAROUNDS, k=random.randint(1, 2))
        fr = random.sample(FRICTION, k=random.randint(1, 3))
    else:
        title = random.choice(TITLES_I)
        body = random.choice(BODIES_I)
        cues = []
        stage = ""
        point = ""
        conf = round(random.uniform(0.7, 0.99), 2)
        wk = []
        fr = random.sample(FRICTION[:3], k=random.randint(0, 1))

    tier = "primary" if random.random() < 0.75 else "discovery"
    sub = random.choice(SUBREDDITS[tier])
    days_ago = random.randint(30, 1000)
    dt = datetime.now(timezone.utc) - timedelta(days=days_ago)
    created = dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    ph = uuid.uuid4().hex[:8]

    return {
        "record_id": "RD_{:06d}".format(idx),
        "source": "reddit", "source_type": "reddit", "content_type": "post",
        "source_id": "t3_" + ph, "post_id": "t3_" + ph,
        "subreddit": sub, "subreddit_tier": tier,
        "title": title, "raw_text": body, "cleaned_text": body,
        "preview_text": body[:150], "author": "user_" + uuid.uuid4().hex[:6],
        "created_at": created, "retrieved_at": created,
        "url": "https://reddit.com/r/{}/comments/{}/".format(sub, ph),
        "queries_matched": [random.choice(ALL_QUERIES)],
        "query_used": random.choice(ALL_QUERIES),
        "run_id": run_id, "parent_id": None,
        "score": random.randint(0, 500), "num_comments": random.randint(0, 120),
        "top_comments": [],
        "ai_relevance": rel, "relevance_confidence": conf, "evidence_status": "analyzed",
        "analysis": {
            "is_relevant": is_rel,
            "relevance_classification": rel,
            "relevance_confidence": conf,
            "relevance_reasoning": "Classified as {} based on content analysis.".format(rel),
            "target_media": "personal_photo",
            "memory_cues_present": cues,
            "memory_cue_details": {c: "Evidence of {} in record".format(c) for c in cues},
            "retrieval_failure_stage": stage,
            "retrieval_failure_point": point,
            "failure_evidence": body[:200] if is_rel else "",
            "workarounds_used": wk,
            "friction_experienced": fr,
            "desired_outcome": "Retrieve specific photo: {}".format(title.lower()[:80]),
        },
    }


def compute_analytics(records):
    total = len(records)
    rel_counts = {}
    for r in records:
        cls = r["ai_relevance"]
        rel_counts[cls] = rel_counts.get(cls, 0) + 1

    relevant_recs = [r for r in records if r["ai_relevance"] in ("relevant", "possibly_relevant")]
    relevant_count = len(relevant_recs)

    stage_counts, point_counts, cue_counts, wk_counts, fr_counts = {}, {}, {}, {}, {}
    sub_counts, month_counts, query_counts, crosstab = {}, {}, {}, {}

    for r in records:
        sub_counts[r["subreddit"]] = sub_counts.get(r["subreddit"], 0) + 1
        q = r["query_used"]
        query_counts[q] = query_counts.get(q, 0) + 1
        mo = r["created_at"][:7]
        month_counts[mo] = month_counts.get(mo, 0) + 1

    for r in relevant_recs:
        a = r["analysis"]
        st = a.get("retrieval_failure_stage", "")
        if st:
            stage_counts[st] = stage_counts.get(st, 0) + 1
        pt = a.get("retrieval_failure_point", "")
        if pt:
            point_counts[pt] = point_counts.get(pt, 0) + 1
        for w in a.get("workarounds_used", []):
            wk_counts[w] = wk_counts.get(w, 0) + 1
        for cue in a.get("memory_cues_present", []):
            cue_counts[cue] = cue_counts.get(cue, 0) + 1
            if cue not in crosstab:
                crosstab[cue] = {}
            crosstab[cue][st or "unknown"] = crosstab[cue].get(st or "unknown", 0) + 1

    for r in records:
        for f in r["analysis"].get("friction_experienced", []):
            fr_counts[f] = fr_counts.get(f, 0) + 1

    confs = [r["relevance_confidence"] for r in records]
    avg_conf = round(sum(confs) / len(confs) * 100, 1)
    avg_score = round(sum(r["score"] for r in records) / total, 1)

    return {
        "total_records": total,
        "relevant_count": relevant_count,
        "relevance_rate": round(relevant_count / total * 100, 1),
        "avg_confidence_pct": avg_conf,
        "avg_score": avg_score,
        "distributions": {
            "relevance": rel_counts,
            "failure_stage": stage_counts,
            "failure_point": point_counts,
            "memory_cue": cue_counts,
            "workaround": wk_counts,
            "friction": fr_counts,
            "subreddit": sub_counts,
            "query_top10": dict(sorted(query_counts.items(), key=lambda x: -x[1])[:10]),
            "timeline_monthly": dict(sorted(month_counts.items())),
        },
        "cross_tabulations": {"cue_by_stage": crosstab},
    }


def main():
    print("Generating 1000 records...")
    now_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    run_id = "synth_run_" + now_str
    records = [make_rec(i + 1, run_id) for i in range(1000)]

    out = ROOT / "data" / "output"
    out.mkdir(parents=True, exist_ok=True)

    with open(out / "synthetic_1000_records.json", "w", encoding="utf-8") as f:
        json.dump({
            "metadata": {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "total_records": 1000,
                "run_id": run_id,
            },
            "records": records,
        }, f, ensure_ascii=False, indent=2)
    print("  Records written.")

    analytics = compute_analytics(records)

    with open(out / "analytics_1000.json", "w", encoding="utf-8") as f:
        json.dump(analytics, f, ensure_ascii=False, indent=2)

    print("  Analytics written.")
    print()
    print("=" * 58)
    print("  PIPELINE SUMMARY - 1000 RECORD RUN")
    print("=" * 58)
    d = analytics
    print("  Total Records:     {:>6}".format(d["total_records"]))
    print("  Relevant/Possibly: {:>6}  ({:.1f}%)".format(d["relevant_count"], d["relevance_rate"]))
    print("  Avg Confidence:    {:>6.1f}%".format(d["avg_confidence_pct"]))
    print("  Avg Score:         {:>6.1f}".format(d["avg_score"]))
    print()
    print("  Relevance Distribution:")
    for k, v in sorted(d["distributions"]["relevance"].items(), key=lambda x: -x[1]):
        pct = round(v / d["total_records"] * 100, 1)
        print("    {:28s}  {:4d}  ({:.1f}%)".format(k, v, pct))
    print()
    print("  Failure Stage Breakdown:")
    for k, v in sorted(d["distributions"]["failure_stage"].items(), key=lambda x: -x[1]):
        pct = round(v / max(d["relevant_count"], 1) * 100, 1)
        print("    {:30s}  {:4d}  ({:.1f}% of relevant)".format(k, v, pct))
    print()
    print("  Top Memory Cues:")
    for k, v in sorted(d["distributions"]["memory_cue"].items(), key=lambda x: -x[1])[:5]:
        print("    {:28s}  {:4d}".format(k, v))
    print()
    print("  Top Workarounds:")
    for k, v in sorted(d["distributions"]["workaround"].items(), key=lambda x: -x[1])[:4]:
        print("    {:28s}  {:4d}".format(k, v))
    print("=" * 58)


if __name__ == "__main__":
    main()
