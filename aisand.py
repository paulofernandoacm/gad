# aisand.py
import time
import threading
from collections import defaultdict
import json

from gad_token import validate_token
from ndlogger import write_event

_LOCK = threading.Lock()
_LAST_REQUEST = defaultdict(list)
_BLACKLIST = set()

RATE_LIMIT_WINDOW = 10
RATE_LIMIT_MAX = 5
MIN_TTL = 1
MAX_TTL = 60 * 60

def _prune_timestamps(origin, now):
    lst = _LAST_REQUEST.get(origin, [])
    cutoff = now - RATE_LIMIT_WINDOW
    lst = [t for t in lst if t >= cutoff]
    _LAST_REQUEST[origin] = lst
    return lst

def record_request(origin):
    now = int(time.time())
    with _LOCK:
        lst = _prune_timestamps(origin, now)
        lst.append(now)
        _LAST_REQUEST[origin] = lst
        return len(lst)

def token_schema_ok(token):
    if not isinstance(token, dict):
        return False
    if "payload" not in token or "signature" not in token or "ttl" not in token:
        return False
    try:
        created = json.loads(token["payload"])["created"]
        if not isinstance(created, int):
            return False
    except Exception:
        return False
    ttl = token.get("ttl")
    if not isinstance(ttl, int):
        return False
    if ttl < MIN_TTL or ttl > MAX_TTL:
        return False
    return True

def basic_token_checks(token, origin):
    if origin in _BLACKLIST:
        return False, "origin_blacklisted"
    if not token_schema_ok(token):
        return False, "invalid_token_schema"
    count = record_request(origin)
    if count > RATE_LIMIT_MAX:
        with _LOCK:
            _BLACKLIST.add(origin)
        return False, "rate_limit_exceeded_and_blacklisted"
    return True, "ok"

def aisand_validate_before_execution(token, origin, trace_id=None):
    """
    Validações pré-execução com registro NDJSON e mascaramento de token.
    """
    if trace_id is None:
        trace_id = "none"
    evt_base = {"trace_id": trace_id, "component": "AISand", "origin": origin, "token": token}
    try:
        ok, reason = basic_token_checks(token, origin)
        write_event({**evt_base, "action": "basic_checks", "result": reason})
        if not ok:
            return False, reason

        sig_ok = validate_token(token, require_pubkey=False)
        write_event({**evt_base, "action": "signature_check", "result": "valid" if sig_ok else "invalid"})
        if not sig_ok:
            if "pubkey" not in token:
                return False, "signature_invalid_or_missing_pubkey"
            return False, "signature_invalid"

        write_event({**evt_base, "action": "aisand_final", "result": "ok"})
        return True, "ok"
    except Exception as e:
        write_event({**evt_base, "action": "exception", "result": str(e)})
        return False, f"aisand_error:{str(e)}"