# chains/chain_python.py

def detect(image_repr, token):
    # Simulação simples: valida token e processa "imagem" representada por string
    from gad_token import validate_token
    if not validate_token(token):
        return {"error": "invalid_or_expired_token"}
    # Resultado simulado
    return {"target": "objeto_detectado", "confidence": 0.92, "image": image_repr}