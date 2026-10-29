import re
import unicodedata

_WORD = re.compile(r"\w+", re.UNICODE)


def fold(s: str) -> str:
    """Lowercase + bỏ dấu, để so khớp keyword có dấu/không dấu."""
    s = unicodedata.normalize("NFD", s.lower().replace("đ", "d"))
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", fold(s)).strip("-")


def strip_markdown(md: str) -> str:
    md = re.sub(r"```.*?```", " ", md, flags=re.S)
    md = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", md)
    md = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", md)
    md = re.sub(r"^\s{0,3}#{1,6}\s*", "", md, flags=re.M)
    md = re.sub(r"^\s*([-*+]|\d+\.)\s+", "", md, flags=re.M)
    return re.sub(r"[*_`>|]", "", md)


def words(text: str) -> list[str]:
    return _WORD.findall(text)


def headings(md: str, level: int) -> list[str]:
    return re.findall(rf"^{'#' * level}\s+(.+?)\s*$", md, flags=re.M)
