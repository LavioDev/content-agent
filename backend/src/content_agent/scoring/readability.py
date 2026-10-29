import re

import textstat

from .text import strip_markdown, words

PASS_SCORE = 60


def _clamp(x: float) -> float:
    return max(0.0, min(100.0, x))


def score_readability(text: str, language: str = "vi") -> dict:
    """Điểm 0-100. EN: Flesch Reading Ease. VI: tự định nghĩa từ câu/đoạn (Flesch không hợp tiếng Việt)."""
    plain = strip_markdown(text)
    paragraphs = [p for p in re.split(r"\n\s*\n", plain) if p.strip()]
    sentences = [s for s in re.split(r"(?<=[.!?…])\s+|\n+", plain) if words(s)]
    n_words = len(words(plain))
    if not sentences or n_words == 0:
        return {"score": 0.0, "passed": False, "language": language, "details": {"error": "empty text"}}

    avg_sentence = n_words / len(sentences)
    long_ratio = sum(len(words(s)) > 35 for s in sentences) / len(sentences)
    sent_per_para = len(sentences) / max(len(paragraphs), 1)
    details = {
        "words": n_words,
        "sentences": len(sentences),
        "avg_sentence_words": round(avg_sentence, 1),
        "avg_sentences_per_paragraph": round(sent_per_para, 1),
        "long_sentence_ratio": round(long_ratio, 3),
    }
    if language == "en":
        score = _clamp(textstat.flesch_reading_ease(plain))
        details["flesch_reading_ease"] = round(score, 1)
    else:
        # 100 trừ phạt: câu TB > 20 từ, đoạn > 4 câu, tỉ lệ câu > 35 từ
        score = _clamp(
            100
            - min(40, max(0, avg_sentence - 20) * 4)
            - min(30, max(0, sent_per_para - 4) * 10)
            - min(30, long_ratio * 100)
        )
    return {"score": round(score, 1), "passed": score >= PASS_SCORE, "language": language, "details": details}
