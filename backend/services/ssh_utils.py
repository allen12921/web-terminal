def validate_private_key(key: str) -> bool:
    key = key.strip()
    if not key:
        return True
    return key.startswith("-----BEGIN") and "PRIVATE KEY-----" in key
