# chains/chain_slow.py
import time
from gad_token import validate_token

def execute_detect(image_repr, token):
    """
    Simula uma chain lenta/instável para testar failover.
    Retorna após 3 segundos; pode exceder timeout do executor.
    """
    if not validate_token(token):
        return {"error": "invalid_or_expired_token", "chain": "chain_slow"}
    time.sleep(3)  # deliberately slow
    return {"chain": "chain_slow", "target": "objeto_detectado_slow", "confidence": 0.85}