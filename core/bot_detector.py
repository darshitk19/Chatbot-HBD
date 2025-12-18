import re

def is_bot(text: str) -> bool:
    if not text or len(text.split()) < 2:
        return True
    if re.search(r"(.)\1{6,}", text):
        return True
    return False
