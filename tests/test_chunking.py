import pytest

from app.chunking import chunk_text, split_sentences


def _text(n_sentences: int, words_per: int = 10) -> str:
    return " ".join(
        f"Sentence{i} " + " ".join(f"w{i}_{j}" for j in range(words_per - 1)) + "."
        for i in range(n_sentences)
    )


def test_short_text_is_one_chunk():
    assert chunk_text("One short sentence. Another one.") == ["One short sentence. Another one."]


def test_empty_text_gives_no_chunks():
    assert chunk_text("   \n\n ") == []


def test_chunks_respect_max_words():
    for c in chunk_text(_text(60), max_words=50, overlap_words=10):
        assert len(c.split()) <= 50


def test_consecutive_chunks_overlap():
    chunks = chunk_text(_text(40), max_words=50, overlap_words=20)
    assert len(chunks) > 2
    for a, b in zip(chunks, chunks[1:], strict=False):
        last_sentence_of_a = split_sentences(a)[-1]
        assert last_sentence_of_a in b, "tail of a chunk must reappear at the start of the next"


def test_every_sentence_is_covered():
    text = _text(55)
    covered = " ".join(chunk_text(text, max_words=40, overlap_words=10))
    for s in split_sentences(text):
        assert s in covered


def test_no_tail_chunk_made_only_of_overlap():
    chunks = chunk_text(_text(20), max_words=50, overlap_words=20)
    assert chunks[-1] != chunks[-2]
    last_new = split_sentences(_text(20))[-1]
    assert chunks[-1].endswith(last_new)


def test_oversized_sentence_is_hard_split():
    giant = " ".join(f"x{i}" for i in range(300)) + "."
    chunks = chunk_text(giant, max_words=100, overlap_words=0)
    assert all(len(c.split()) <= 100 for c in chunks)
    assert len(chunks) == 3


def test_invalid_params():
    with pytest.raises(ValueError):
        chunk_text("a b c", max_words=10, overlap_words=10)
    with pytest.raises(ValueError):
        chunk_text("a b c", max_words=0)
