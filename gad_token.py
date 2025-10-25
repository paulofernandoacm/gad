# gad_token.py
"""
Geração e validação de tokens GAD-Q usando Ed25519 (PyNaCl).
Cria um par de chaves local em keys/ se não existir.
O token contém: payload (JSON str), signature (hex) e pubkey (hex), ttl (int).
"""

import json
import time
from pathlib import Path
from nacl.signing import SigningKey, VerifyKey
from nacl.exceptions import BadSignatureError

KEY_DIR = Path("keys")
PRIV_KEY_FILE = KEY_DIR / "ed25519_private.key"
PUB_KEY_FILE = KEY_DIR / "ed25519_public.key"

def _now_seconds():
    return int(time.time())

def _ensure_keys():
    KEY_DIR.mkdir(parents=True, exist_ok=True)
    if PRIV_KEY_FILE.exists() and PUB_KEY_FILE.exists():
        sk = SigningKey(PRIV_KEY_FILE.read_bytes())
        vk = VerifyKey(PUB_KEY_FILE.read_bytes())
        return sk, vk
    sk = SigningKey.generate()
    vk = sk.verify_key
    PRIV_KEY_FILE.write_bytes(sk.encode())
    PUB_KEY_FILE.write_bytes(vk.encode())
    return sk, vk

def generate_token(origin, target, permissions, ttl=5, use_embedded_pubkey=True):
    """
    Gera token com payload assinado por Ed25519.
    - origin, target: strings
    - permissions: list[str]
    - ttl: int (segundos)
    - use_embedded_pubkey: se True inclui pubkey no token para verificação
    """
    sk, vk = _ensure_keys()
    payload_obj = {
        "origin": origin,
        "target": target,
        "permissions": permissions,
        "created": _now_seconds()
    }
    payload = json.dumps(payload_obj, separators=(",", ":"), sort_keys=True)
    sig = sk.sign(payload.encode()).signature.hex()
    token = {
        "payload": payload,
        "signature": sig,
        "ttl": int(ttl)
    }
    if use_embedded_pubkey:
        token["pubkey"] = vk.encode().hex()
    return token

def validate_token(token, require_pubkey=False):
    """
    Valida:
    - esquema do token
    - assinatura Ed25519 (se pubkey presente, usa-a; senao usa local pubkey)
    - TTL baseado em campo created do payload
    Retorna True/False.
    """
    try:
        if not isinstance(token, dict):
            return False
        for k in ("payload", "signature", "ttl"):
            if k not in token:
                return False
        payload = token["payload"]
        signature = bytes.fromhex(token["signature"])
        ttl = int(token["ttl"])
        payload_obj = json.loads(payload)
        created = int(payload_obj.get("created", 0))

        # Escolhe verify key: embedded pubkey tem prioridade
        if "pubkey" in token:
            vk_bytes = bytes.fromhex(token["pubkey"])
            vk = VerifyKey(vk_bytes)
        else:
            # Se não houver pubkey embutida, tenta usar local keypair
            sk, vk = _ensure_keys()

        # Verifica assinatura
        try:
            vk.verify(payload.encode(), signature)
        except BadSignatureError:
            return False

        now = _now_seconds()
        if now - created >= ttl:
            return False

        return True
    except Exception:
        return False

if __name__ == "__main__":
    # Demo rápido
    t = generate_token("user:paulo", "chain_python", ["vision"], ttl=10)
    print("Token gerado:")
    print(json.dumps(t, indent=2))
    print("Validação:", validate_token(t))