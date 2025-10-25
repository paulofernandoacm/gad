# chains/chain_rust.py
import time
from gad_token import validate_token

def execute_detect(image_repr, token):
    """
    Simula uma chain 'rust' com resposta rápida e confiável.
    """
    if not validate_token(token):
        return {"error": "invalid_or_expired_token", "chain": "chain_rust"}
    # Simula processamento
    time.sleep(0.1)
    return {"chain": "chain_rust", "target": "objeto_detectado_rust", "confidence": 0.90}