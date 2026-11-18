"""Render eval/corpus_text.py into real PDFs (one page of text = one PDF page).

python -m eval.build_corpus          # writes eval/corpus/*.pdf (committed, so CI needs no fpdf2 step)
"""

from pathlib import Path

from fpdf import FPDF

from eval.corpus_text import DOCS

OUT = Path(__file__).parent / "corpus"


def build() -> list[Path]:
    OUT.mkdir(exist_ok=True)
    paths = []
    for stem, pages in DOCS.items():
        pdf = FPDF(format="A4")
        pdf.set_auto_page_break(False)
        for text in pages:
            pdf.add_page()
            pdf.set_font("Helvetica", size=11)
            pdf.set_margins(20, 20, 20)
            pdf.set_xy(20, 20)
            pdf.multi_cell(0, 6, text)
            assert pdf.get_y() < 277, f"{stem}: a page of text overflows one PDF page"
        path = OUT / f"{stem}.pdf"
        pdf.output(str(path))
        paths.append(path)
    return paths


if __name__ == "__main__":
    for p in build():
        print("wrote", p)
