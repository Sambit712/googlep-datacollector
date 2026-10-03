import re

log_path = r"C:\Users\kumar\.gemini\antigravity-ide\brain\24f75818-376e-472d-b394-8001ca5c417e\.system_generated\tasks\task-58.log"

total = 0
queries_done = 0
with open(log_path, "r", encoding="utf-8") as f:
    for line in f:
        m = re.search(r"(\d+) new records collected", line)
        if m:
            total += int(m.group(1))
            queries_done += 1

print(f"Successful queries: {queries_done}")
print(f"Total records collected: {total}")
print(f"Avg records per query: {total/queries_done:.1f}" if queries_done else "N/A")
