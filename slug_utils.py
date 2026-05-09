import re

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,78}[a-z0-9]$")


def normalize_slug(slug: str) -> str:
    s = slug.strip().lower()
    if not _SLUG_RE.match(s):
        raise ValueError("Invalid slug: use lowercase letters, numbers, hyphens (2–80 chars)")
    return s
