# gad_executor.py
import sys
import json
import logging
import time
from pathlib import Path

from gad_parser import parse_gad_file
from gad_token import generate_token, validate_token
from aisand import aisand_validate_before_execution
from ndlogger import write_event, new_trace_id

from chains.chain_python import detect as python_detect

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("gad_executor")

DEFAULT_IMAGE = "simulated.jpg"
DEFAULT_ORIGIN = "user:paulo"
DEFAULT_TTL = 10

def _choose_chain_callable(parsed):
    imports = parsed.get("imports", [])
    if not imports:
        return python_detect, "python:detect"
    first = imports[0]
    chain = first.get("chain")
    target = first.get("target")
    key = f"{chain}:{target}"
    if chain == "python":
        return python_detect, key
    return python_detect, "python:detect"

def executar_gad_file(filepath, image_repr=DEFAULT_IMAGE, origin=DEFAULT_ORIGIN, ttl=DEFAULT_TTL):
    trace_id = new_trace_id()
    start_ts = time.time()
    write_event({"trace_id": trace_id, "component": "executor", "action": "start", "file": filepath, "origin": origin})

    path = Path(filepath)
    if not path.exists():
        write_event({"trace_id": trace_id, "component": "executor", "action": "error", "result": "file_not_found"})
        raise FileNotFoundError(f"Arquivo não encontrado: {filepath}")

    parsed = parse_gad_file(str(path))
    write_event({"trace_id": trace_id, "component": "executor", "action": "parsed", "imports": parsed.get("imports"), "functions": parsed.get("functions")})

    chain_callable, chain_alias = _choose_chain_callable(parsed)
    write_event({"trace_id": trace_id, "component": "executor", "action": "choose_chain", "chosen": chain_alias})

    token = generate_token(origin, chain_alias, ["vision"], ttl=ttl)
    write_event({"trace_id": trace_id, "component": "executor", "action": "token_generated", "token": token})

    if not validate_token(token):
        write_event({"trace_id": trace_id, "component": "executor", "action": "error", "result": "token_validation_failed", "token": token})
        raise RuntimeError("Token validation failed immediately after generation")

    ok, reason = aisand_validate_before_execution(token, origin, trace_id=trace_id)
    write_event({"trace_id": trace_id, "component": "executor", "action": "aisand_result", "ok": ok, "reason": reason})
    if not ok:
        raise RuntimeError(f"Execution blocked by AISand: {reason}")

    write_event({"trace_id": trace_id, "component": "executor", "action": "call_chain", "chain": chain_alias, "image": str(image_repr)})
    try:
        start_call = time.time()
        result = chain_callable(image_repr, token)
        elapsed = time.time() - start_call
        write_event({"trace_id": trace_id, "component": "executor", "action": "chain_result", "chain": chain_alias, "elapsed_s": elapsed, "result": result})
    except Exception as e:
        write_event({"trace_id": trace_id, "component": "executor", "action": "chain_exception", "chain": chain_alias, "error": str(e)})
        result = {"error": "chain_execution_error", "details": str(e)}

    output = {"parsed": parsed, "token": token, "result": result, "trace_id": trace_id}
    write_event({"trace_id": trace_id, "component": "executor", "action": "end", "duration_s": time.time() - start_ts})
    return output