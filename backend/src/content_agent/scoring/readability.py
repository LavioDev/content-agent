import re

import textstat

from .text import strip_markdown, words

PASS_SCORE = 60
# words() tách theo khoảng trắng: tiếng Việt ra ÂM TIẾT (~1.4 âm tiết/từ), tiếng Anh ra từ
# shortcut: ngưỡng VI chọn theo kinh nghiệm (~16 từ / ~28 từ thật), hiệu chỉnh lại khi có điểm human rating
LIMITS = {"vi": (22, 40), "en": (20, 25)}  # (câu TB tối đa, ngưỡng câu dài)


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

    max_avg, long_at = LIMITS.get(language, LIMITS["vi"])
    avg_sentence = n_words / len(sentences)
    long = [s.strip() for s in sentences if len(words(s)) > long_at]
    long_ratio = len(long) / len(sentences)
    sent_per_para = len(sentences) / max(len(paragraphs), 1)
    details = {
        "words": n_words,
        "sentences": len(sentences),
        "avg_sentence_words": round(avg_sentence, 1),
        "avg_sentences_per_paragraph": round(sent_per_para, 1),
        "long_sentence_ratio": round(long_ratio, 3),
        "long_sentence_limit": long_at,
        "long_examples": [s[:200] for s in long[:5]],  # để Editor biết sửa câu nào
        # để UI tô câu dài / đoạn dài; cùng regex tách câu nên khớp với phần bị trừ điểm
        "paragraphs": [
            {"long": len(ss) > 4, "sentences": [[s.strip(), len(words(s)) > long_at] for s in ss]}
            for p in paragraphs
            if (ss := [s for s in re.split(r"(?<=[.!?…])\s+|\n+", p) if words(s)])
        ],
    }
    if language == "en":
        score = _clamp(textstat.flesch_reading_ease(plain))
        details["flesch_reading_ease"] = round(score, 1)
    else:
        # 100 trừ phạt: câu TB > 22 âm tiết, đoạn > 4 câu, tỉ lệ câu > 40 âm tiết
        score = _clamp(
            100
            - min(40, max(0, avg_sentence - max_avg) * 4)
            - min(30, max(0, sent_per_para - 4) * 10)
            - min(30, long_ratio * 100)
        )
    return {"score": round(score, 1), "passed": score >= PASS_SCORE, "language": language, "details": details}
