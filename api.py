# api.py
from flask import Flask, jsonify, request, abort
from pathlib import Path
import json
import time

LOG_FILE = Path("logs/events.ndjson")
SUMMARY_FILE = Path("logs/summary.json")

app = Flask("gad_audit_api")

def _load_events():
    events = []
    if not LOG_FILE.exists():
        return events
    with LOG_FILE.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except Exception:
                continue
    return events

def _mask_token_in_event(ev: dict):
    e = dict(ev)
    token = e.get("token")
    if isinstance(token, dict):
        # mask signature/pubkey if present
        for k in ("signature", "pubkey"):
            v = token.get(k)
            if isinstance(v, str):
                if len(v) > 12:
                    token[k] = v[:6] + "..." + v[-6:]
                else:
                    token[k] = "****"
        # mask payload.origin inside payload JSON if possible
        payload = token.get("payload")
        try:
            p = json.loads(payload)
            if "origin" in p:
                o = str(p["origin"])
                if len(o) > 6:
                    p["origin"] = o[:3] + "..." + o[-3:]
                else:
                    p["origin"] = "***"
            token["payload"] = json.dumps(p, separators=(",", ":"))
        except Exception:
            token["payload"] = "****"
        e["token"] = token
    return e

@app.route("/summary", methods=["GET"])
def get_summary():
    if not SUMMARY_FILE.exists():
        return jsonify({"error": "summary_not_found"}), 404
    try:
        data = json.loads(SUMMARY_FILE.read_text(encoding="utf-8"))
        return jsonify(data)
    except Exception as exc:
        return jsonify({"error": "failed_to_read_summary", "details": str(exc)}), 500

@app.route("/events", methods=["GET"])
def list_events():
    """
    Query params:
      - limit (int)
      - action (filter by action string)
      - origin (filter by origin string)
      - since_ts (ISO string, optional)
    """
    events = _load_events()
    action = request.args.get("action")
    origin = request.args.get("origin")
    since_ts = request.args.get("since_ts")
    limit = int(request.args.get("limit") or 0)

    def keep(ev):
        if action and ev.get("action") != action:
            return False
        if origin and ev.get("origin") != origin:
            return False
        if since_ts:
            ts = ev.get("ts")
            if not ts or ts < since_ts:
                return False
        return True

    filtered = [ _mask_token_in_event(ev) for ev in events if keep(ev) ]
    if limit and limit > 0:
        filtered = filtered[-limit:]
    return jsonify({"count": len(filtered), "events": filtered})

@app.route("/event/<trace_id>", methods=["GET"])
def get_by_trace(trace_id):
    events = _load_events()
    matched = [ _mask_token_in_event(ev) for ev in events if ev.get("trace_id") == trace_id ]
    if not matched:
        return jsonify({"error": "trace_id_not_found"}), 404
    # return chronological list
    return jsonify({"trace_id": trace_id, "events": matched})

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})

if __name__ == "__main__":
    # development server; use a WSGI server (gunicorn) for production
    app.run(host="0.0.0.0", port=5000, debug=False)