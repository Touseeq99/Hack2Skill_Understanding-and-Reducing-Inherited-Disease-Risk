"""Render docs/SUBMISSION.md to docs/SUBMISSION.pdf with ReportLab (headings, paragraphs, bullets, tables, code).

Usage:  python docs/build_submission_pdf.py
Handles the Markdown subset used in SUBMISSION.md; it is not a general Markdown converter.
"""
import re
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import ListFlowable, ListItem, Paragraph, Preformatted, SimpleDocTemplate, Spacer, Table, TableStyle

HERE = Path(__file__).resolve().parent
SRC, OUT = HERE / "SUBMISSION.md", HERE / "SUBMISSION.pdf"

ss = getSampleStyleSheet()
BODY = ParagraphStyle("body", parent=ss["BodyText"], fontSize=9.2, leading=12.5, spaceAfter=4)
H1 = ParagraphStyle("h1", parent=ss["Heading1"], fontSize=17, leading=21, spaceAfter=8, textColor=colors.HexColor("#0f766e"))
H2 = ParagraphStyle("h2", parent=ss["Heading2"], fontSize=12.5, leading=16, spaceBefore=10, spaceAfter=5, textColor=colors.HexColor("#0f172a"))
H3 = ParagraphStyle("h3", parent=ss["Heading3"], fontSize=10.5, leading=14, spaceBefore=6, spaceAfter=3, textColor=colors.HexColor("#334155"))
CELL = ParagraphStyle("cell", parent=BODY, fontSize=7.8, leading=10, spaceAfter=0)
CELLH = ParagraphStyle("cellh", parent=CELL, fontName="Helvetica-Bold", textColor=colors.white)
CODE = ParagraphStyle("code", fontName="Courier", fontSize=7.2, leading=9, backColor=colors.HexColor("#f1f5f9"), borderPadding=4, spaceAfter=6)


def inline(text: str) -> str:
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    text = re.sub(r"`([^`]+)`", r'<font face="Courier" size="8">\1</font>', text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<i>\1</i>", text)
    return text


def table(rows):
    header, body = rows[0], rows[1:]
    ncol = len(header)
    data = [[Paragraph(inline(c), CELLH) for c in header]] + [[Paragraph(inline(c), CELL) for c in (r + [""] * ncol)[:ncol]] for r in body]
    width = A4[0] - 30 * mm
    t = Table(data, colWidths=[width / ncol] * ncol, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f766e")),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
        ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t


def build():
    lines = SRC.read_text(encoding="utf-8").splitlines()
    story, i = [], 0
    while i < len(lines):
        ln = lines[i]
        if ln.startswith("```"):
            i += 1
            block = []
            while i < len(lines) and not lines[i].startswith("```"):
                block.append(lines[i]); i += 1
            story.append(Preformatted("\n".join(block), CODE)); i += 1; continue
        if ln.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-{3,}:?", c) for c in cells):
                    rows.append(cells)
                i += 1
            story += [table(rows), Spacer(1, 6)]; continue
        if ln.startswith("# "):
            story.append(Paragraph(inline(ln[2:]), H1))
        elif ln.startswith("## "):
            story.append(Paragraph(inline(ln[3:]), H2))
        elif ln.startswith("### "):
            story.append(Paragraph(inline(ln[4:]), H3))
        elif re.match(r"^(\d+\.|-) ", ln):
            ordered = ln[0].isdigit()
            items = []
            while i < len(lines) and re.match(r"^(\d+\.|-) ", lines[i]):
                text = re.sub(r"^(\d+\.|-) ", "", lines[i]); i += 1
                while i < len(lines) and lines[i].startswith("   ") and lines[i].strip():
                    text += " " + lines[i].strip(); i += 1
                items.append(ListItem(Paragraph(inline(text), BODY)))
            story.append(ListFlowable(items, bulletType="1" if ordered else "bullet", leftIndent=14, bulletFontSize=8))
            continue
        elif ln.strip():
            para = ln.strip()
            while i + 1 < len(lines) and lines[i + 1].strip() and not re.match(r"^(#|\||```|\d+\. |- )", lines[i + 1]):
                i += 1; para += " " + lines[i].strip()
            story.append(Paragraph(inline(para), BODY))
        i += 1

    def footer(canvas, doc):
        canvas.saveState(); canvas.setFont("Helvetica", 7.5); canvas.setFillColor(colors.HexColor("#64748b"))
        canvas.drawString(15 * mm, 9 * mm, "Inherited disease risk prototype - synthetic data only - DRAFT, requires clinical sign-off")
        canvas.drawRightString(A4[0] - 15 * mm, 9 * mm, f"Page {doc.page}")
        canvas.restoreState()

    SimpleDocTemplate(str(OUT), pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=14 * mm, bottomMargin=16 * mm,
                      title="Understanding and Reducing Inherited Disease Risk - prototype submission").build(story, onFirstPage=footer, onLaterPages=footer)
    print("wrote", OUT)


if __name__ == "__main__":
    build()
