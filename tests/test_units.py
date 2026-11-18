import pytest
from fpdf import FPDF

from app.answer import NO_ANSWER, answer, extractive_answer, is_relevant
from app.loaders import UnsupportedFile, load_pages
from app.search import Hit, rrf


def _pdf(*pages: str) -> bytes:
    pdf = FPDF()
    for text in pages:
        pdf.add_page()
        pdf.set_font("Helvetica", size=12)
        pdf.multi_cell(0, 8, text)
    return bytes(pdf.output())


def test_rrf_rewards_agreement_between_channels():
    scores = rrf([[1, 2, 3], [3, 4, 1]], k=60)
    assert scores[1] > scores[2] and scores[3] > scores[2]  # in both lists beats in one
    assert scores[1] == pytest.approx(1 / 61 + 1 / 63)


def test_rrf_empty():
    assert rrf([], 60) == {}


def test_pdf_pages_are_numbered_and_blank_pages_dropped():
    pages = load_pages("a.pdf", _pdf("first page text", "   ", "third page text"))
    assert [n for n, _ in pages] == [1, 3]


def test_text_file_is_cut_into_numbered_sections():
    big = "\n\n".join(f"paragraph {i} " + "x" * 800 for i in range(10))
    pages = load_pages("notes.md", big.encode())
    assert len(pages) > 1 and [n for n, _ in pages] == list(range(1, len(pages) + 1))


def test_nul_bytes_are_stripped():
    assert load_pages("a.txt", b"abc\x00def")[0][1] == "abcdef"


@pytest.mark.parametrize(
    "name,data", [("evil.exe", b"MZ"), ("noext", b"hi"), ("bad.pdf", b"not a pdf")]
)
def test_unsupported_files_rejected(name, data):
    with pytest.raises(UnsupportedFile):
        load_pages(name, data)


def test_empty_text_rejected():
    with pytest.raises(UnsupportedFile):
        load_pages("a.txt", b"  \n\n ")


def _hit(content: str, rerank: float | None = 5.0, page: int = 1) -> Hit:
    return Hit(1, 1, "Doc", page, content, rerank_score=rerank)


def test_refuses_without_hits_or_below_threshold():
    assert answer("anything", []).text == NO_ANSWER
    low = answer("anything", [_hit("irrelevant", rerank=-9.0)])
    assert low.text == NO_ANSWER and not low.grounded and not low.citations


def test_relevance_gate_is_skipped_for_unranked_modes():
    assert is_relevant([_hit("x", rerank=None)])


def test_extractive_picks_the_sentence_that_matches_the_question():
    hit = _hit(
        "Nothing here. Snapshots are deleted after 14 days by default. Unrelated closing line."
    )
    a = extractive_answer("How long are snapshots kept?", [hit])
    assert "14 days" in a.text and a.text.endswith("[1]")
    assert a.citations[0].page == 1
