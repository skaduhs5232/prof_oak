
CHARS_PER_TOKEN = 4


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // CHARS_PER_TOKEN)
