"""Response formatting only; never used to decide compatibility or confidence."""
import re
import unicodedata


def unique_messages(messages):
    """Keep the first wording; accents, punctuation and spaces do not add alerts."""
    result, seen = [], set()
    for message in messages:
        key = unicodedata.normalize("NFKD", message.casefold())
        key = "".join(char for char in key if not unicodedata.combining(char))
        key = " ".join(re.sub(r"[^\w]+", " ", key).split())
        if key not in seen:
            seen.add(key)
            result.append(message)
    return result
