from __future__ import annotations

import re
import unicodedata

_STOP_WORDS = (
    "a an and are at be by for from has in is it of on or the to was with this that de do da em no na o e"
)
_STOP = frozenset(_STOP_WORDS.split(" "))


def tokenize(text: str) -> list[str]:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return [t for t in re.findall(r"[a-z0-9_.:]+", text) if t not in _STOP and len(t) > 1]
