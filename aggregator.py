# aggregator.py
"""
Agregador NDJSON para logs/events.ndjson
Gera um resumo por action, latências médias e bloqueios por origin.
Salva saída em logs/summary.json e imprime resumo compacto no console.
"""
import json
from pathlib import Path
from collections import defaultdict, Counter

LOG_FILE = Path("logs/events.ndjson")
OUT_FILE = Path("logs/summary.json")

def read_events(path):
    if not path.exists():
        raise FileNotFoundError(f"Log file not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except Exception:
                # skip malformed lines
                continue

def safe_get_num(d, *keys):
    for k in keys:
        v = d.get(k)
        if isinstance(v, (int, float)):
            return float(v)
    return None

def aggregate(events):
    action_counts = Counter()
    action_latency_sum = defaultdict(float)
    action_latency_count = defaultdict(int)

    origin_counts = Counter()
    aisand_block_counts = Counter()
    total_events = 0

    for ev in events:
        total_events += 1
        action = ev.get("action", "unknown")
        action_counts[action] += 1

        # Collect latency from possible fields
        latency = None
        latency = safe_get_num(ev, "duration_s", "elapsed_s")
        if latency is None:
            # check nested result elapsed_s
            res = ev.get("result") or {}
            if isinstance(res, dict):
                latency = safe_get_num(res, "elapsed_s", "duration_s")
        if latency is not None:
            action_latency_sum[action] += float(latency)
            action_latency_count[action] += 1

        # origin tracking
        origin = ev.get("origin")
        if origin:
            origin_counts[origin] += 1

        # AISand block detection: actions or results indicating block
        comp = ev.get("component", "").lower()
        if comp == "aisand":
            if ev.get("result") and str(ev.get("result")).lower() not in ("ok","valid"):
                aisand_block_counts[ev.get("origin","unknown")] += 1
        # executor recorded aisand_result with ok flag
        if action == "aisand_result":
            ok = ev.get("ok")
            if ok is False:
                aisand_block_counts[ev.get("reason","unknown")] += 1

    # compute latency averages
    action_latency_avg = {}
    for a, s in action_latency_sum.items():
        c = action_latency_count.get(a, 0)
        action_latency_avg[a] = s / c if c > 0 else None

    summary = {
        "total_events": total_events,
        "actions": [],
        "top_origins": origin_counts.most_common(10),
        "aisand_blocks_by_origin": aisand_block_counts.most_common(),
    }

    for action, cnt in action_counts.most_common():
        summary["actions"].append({
            "action": action,
            "count": cnt,
            "latency_avg_s": action_latency_avg.get(action)
        })

    return summary

def main():
    events = list(read_events(LOG_FILE))
    if not events:
        print("No events found.")
        return
    summary = aggregate(events)
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with OUT_FILE.open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    # Print compact summary
    print(f"Total events: {summary['total_events']}")
    print("Top actions (count, avg_latency_s):")
    for a in summary["actions"][:10]:
        lat = a["latency_avg_s"]
        lat_str = f"{lat:.4f}" if isinstance(lat, (int, float)) else "n/a"
        print(f" - {a['action']}: {a['count']}, avg={lat_str}")
    print("Top origins:")
    for origin, cnt in summary["top_origins"]:
        print(f" - {origin}: {cnt}")
    if summary["aisand_blocks_by_origin"]:
        print("AISand blocks by origin or reason:")
        for item, cnt in summary["aisand_blocks_by_origin"]:
            print(f" - {item}: {cnt}")
    print(f"Summary written to {OUT_FILE}")

if __name__ == "__main__":
    main()