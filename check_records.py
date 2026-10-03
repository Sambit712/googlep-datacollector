import json

with open("data/output/reddit_evidence.json", "r", encoding="utf-8") as f:
    data = json.load(f)

if isinstance(data, dict):
    print("Keys:", list(data.keys()))
    if "records" in data:
        print("Total records:", len(data["records"]))
    elif "posts" in data:
        print("Total posts:", len(data["posts"]))
    else:
        print("Dict structure - top-level keys:", list(data.keys())[:10])
elif isinstance(data, list):
    print("Total records (list):", len(data))
