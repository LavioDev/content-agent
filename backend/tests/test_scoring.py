from content_agent.scoring import score_readability, score_seo
from content_agent.scoring.text import fold, slugify

from .conftest import GOOD_IMAGES, GOOD_META, KW, make_article


def seo(md, **over):
    args = {"focus_keyword": KW, **GOOD_META, "image_prompts": GOOD_IMAGES, "language": "vi"} | over
    return score_seo(md, **args)


def test_fold_and_slug():
    assert fold("Chuyển Đổi Số Đà Nẵng") == "chuyen doi so da nang"
    assert slugify("Chuyển đổi số!") == "chuyen-doi-so"


def test_seo_perfect_article_scores_100():
    r = seo(make_article())
    failed = [i["label"] for i in r["items"] if not i["passed"]]
    assert r["score"] == 100, failed
    assert r["word_count"] >= 1200


def test_seo_without_keyword_fails_keyword_checks():
    r = seo(make_article(with_kw=False))
    ids = {i["id"] for i in r["items"] if not i["passed"]}
    assert {"kw_h1", "kw_first100", "kw_h2", "density"} <= ids
    assert r["score"] < 80


def test_seo_accent_insensitive():
    assert seo(make_article(), focus_keyword="CHUYEN DOI SO")["items"][0]["passed"]


def test_seo_no_links_and_few_h2():
    r = seo(make_article(links=False, h2=2))
    ids = {i["id"] for i in r["items"] if not i["passed"]}
    assert {"ext_links", "h2_count"} <= ids


def test_seo_missing_alt_text():
    r = seo(make_article(), image_prompts=[{"prompt": "x", "alt": ""}])
    assert "image_alt" in {i["id"] for i in r["items"] if not i["passed"]}


def test_readability_vi_short_vs_long_sentences():
    short = score_readability("Câu ngắn thôi. Rất dễ đọc. Chỉ vài từ.", "vi")
    long = score_readability(" ".join(["từ"] * 80) + ".", "vi")
    assert short["passed"] and short["score"] > long["score"]
    assert not long["passed"]


def test_readability_vi_counts_syllables_not_words():
    # câu 20 âm tiết (~14 từ thật) là câu bình thường tiếng Việt, không bị trừ điểm
    sentence = " ".join(["âm"] * 20) + "."
    normal = "\n\n".join(f"{sentence} {sentence}" for _ in range(5))
    r = score_readability(normal, "vi")
    assert r["score"] == 100 and r["details"]["long_examples"] == []
    assert score_readability(" ".join(["âm"] * 50) + ".", "vi")["details"]["long_examples"]


def test_readability_paragraphs_flag_long_sentence_and_paragraph():
    long_s, short = " ".join(["âm"] * 50) + ".", "Câu ngắn."
    paras = score_readability(f"{long_s} {short}\n\n" + " ".join([short] * 5), "vi")["details"]["paragraphs"]
    assert paras[0] == {"long": False, "sentences": [[long_s, True], [short, False]]}
    assert paras[1]["long"] and len(paras[1]["sentences"]) == 5


def test_readability_en_uses_flesch():
    r = score_readability("The cat sat on the mat. It was a sunny day. We had fun.", "en")
    assert "flesch_reading_ease" in r["details"] and r["passed"]


def test_readability_empty():
    assert score_readability("", "vi")["score"] == 0
