# ndlogger.py
"""
NDJSON logger com rotação por tamanho e compressão gzip.

Comportamento:
- Escreve eventos NDJSON em logs/events.ndjson
- Ao ultrapassar MAX_BYTES, o arquivo atual é fechado, renomeado com timestamp,
  comprimido para .ndjson.gz e removido o .ndjson original
- Mantém até BACKUP_COUNT arquivos rotacionados (mais antigos são removidos)
- Fornece write_event(event) thread-safe e rotate_now() para forçar rotação
- Preserva os mesmos contratos do logger anterior (adiciona meta e máscara de token)
"""
import json
import time
import uuid
from pathlib import Path
from threading import Lock, Thread, Event
import os
import getpass
import socket
import gzip
import shutil
from typing import Optional

LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)
BASE_FILE = LOG_DIR / "events.ndjson"
MAX_BYTES = 1024 * 1024 * 5  # 5 MB por padrão; ajuste conforme necessário
BACKUP_COUNT = 5
CHECK_INTERVAL_S = 30  # se usar thread de verificação periódica

_LOCK = Lock()

def now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

def new_trace_id():
    return uuid.uuid4().hex

def _system_meta():
    return {
        "host": socket.gethostname(),
        "pid": os.getpid(),
        "user": getpass.getuser()
    }

def _mask_string(s: str, keep_prefix=3, keep_suffix=3):
    s = str(s)
    if len(s) <= keep_prefix + keep_suffix + 2:
        return "***"
    return s[:keep_prefix] + "..." + s[-keep_suffix:]

def _mask_token(token: dict, keep_prefix_len=6, keep_suffix_len=6):
    if not isinstance(token, dict):
        return token
    safe = {}
    for k, v in token.items():
        if k in ("signature", "pubkey"):
            s = str(v)
            if len(s) > (keep_prefix_len + keep_suffix_len):
                safe[k] = s[:keep_prefix_len] + "..." + s[-keep_suffix_len:]
            else:
                safe[k] = "****"
        elif k == "payload":
            try:
                p = json.loads(v)
                if isinstance(p, dict):
                    if "origin" in p:
                        p["origin"] = _mask_string(p["origin"])
                safe[k] = json.dumps(p, separators=(",", ":"), ensure_ascii=False)
            except Exception:
                safe[k] = "****"
        else:
            safe[k] = v
    return safe

def _prepare_event(event: dict):
    e = dict(event)
    if "ts" not in e:
        e["ts"] = now_iso()
    if "meta" not in e:
        e["meta"] = _system_meta()
    if "token" in e:
        e["token"] = _mask_token(e["token"])
    if "token_summary" in e and isinstance(e["token_summary"], dict):
        ts = dict(e["token_summary"])
        if "signature" in ts:
            ts["signature"] = _mask_string(ts["signature"])
        e["token_summary"] = ts
    return e

def _rotate_filename(base: Path, ts: Optional[str] = None) -> Path:
    if ts is None:
        ts = time.strftime("%Y%m%dT%H%M%S", time.gmtime())
    return base.with_name(f"{base.stem}.{ts}{base.suffix}")

def _compress_file(path: Path):
    gz_path = path.with_suffix(path.suffix + ".gz")
    with path.open("rb") as f_in, gzip.open(gz_path, "wb") as f_out:
        shutil.copyfileobj(f_in, f_out)
    try:
        path.unlink()
    except Exception:
        pass
    return gz_path

def _prune_backups(base: Path):
    # listar backups: base.stem.YYYYMMDDTHHMMSS.ndjson.gz
    files = sorted([p for p in base.parent.iterdir() if p.is_file() and p.name.startswith(base.stem + ".") and p.name.endswith(base.suffix + ".gz")],
                   key=lambda p: p.stat().st_mtime,
                   reverse=True)
    for old in files[BACKUP_COUNT:]:
        try:
            old.unlink()
        except Exception:
            pass

def rotate_now():
    """
    Força rotação imediata: fecha e comprime o arquivo atual se existir e tiver conteúdo.
    Thread-safe.
    """
    with _LOCK:
        if not BASE_FILE.exists():
            return
        try:
            if BASE_FILE.stat().st_size == 0:
                return
        except Exception:
            return
        ts = time.strftime("%Y%m%dT%H%M%S", time.gmtime())
        rotated = _rotate_filename(BASE_FILE, ts)
        try:
            BASE_FILE.rename(rotated)
        except Exception:
            # fallback: copy+truncate
            try:
                shutil.copy2(BASE_FILE, rotated)
                with BASE_FILE.open("w", encoding="utf-8"):
                    pass
            except Exception:
                return
        gz = _compress_file(rotated)
        _prune_backups(BASE_FILE)

def _should_rotate_after_write():
    try:
        return BASE_FILE.exists() and BASE_FILE.stat().st_size >= MAX_BYTES
    except Exception:
        return False

def write_event(event: dict):
    """
    Escreve evento NDJSON com mascaramento e realiza rotação se necessário.
    Thread-safe.
    """
    if "ts" not in event:
        event["ts"] = now_iso()
    prepared = _prepare_event(event)
    line = json.dumps(prepared, ensure_ascii=False, separators=(",", ":"))
    with _LOCK:
        # abrir em append garante que múltiplos processos/threads não truncam (threads OK, multiprocess pode ter race)
        with BASE_FILE.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
        # checar rotação
        if _should_rotate_after_write():
            try:
                rotate_now()
            except Exception:
                # rotação não crítica: ignore erros
                pass

# Opcional: thread que verifica periodicamente e roda rotate_now() se necessário.
_rotate_thread: Optional[Thread] = None
_stop_event = Event()

def start_background_rotator(check_interval: int = CHECK_INTERVAL_S):
    global _rotate_thread
    if _rotate_thread and _rotate_thread.is_alive():
        return
    _stop_event.clear()
    def _worker():
        while not _stop_event.is_set():
            try:
                if BASE_FILE.exists() and BASE_FILE.stat().st_size >= MAX_BYTES:
                    with _LOCK:
                        rotate_now()
                _stop_event.wait(check_interval)
            except Exception:
                # swallow to keep thread alive
                _stop_event.wait(check_interval)
    _rotate_thread = Thread(target=_worker, daemon=True, name="ndlogger-rotator")
    _rotate_thread.start()

def stop_background_rotator():
    _stop_event.set()
    global _rotate_thread
    if _rotate_thread:
        _rotate_thread.join(timeout=2)
        _rotate_thread = None