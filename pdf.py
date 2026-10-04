"""The PDF of accepted entries: words then phrases, alphabetical, with a linked contents page."""
from datetime import date
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import BaseDocTemplate, Frame, PageBreak, PageTemplate, Paragraph, Spacer
from reportlab.platypus.tableofcontents import TableOfContents

import vocab
from build_vocab import fold

ROOT = Path(__file__).parent
FONTS = ROOT / "fonts"
PDF_PATH = ROOT / "output" / "vocabulary.pdf"
MARGIN = 2.2 * cm
BLUE = colors.HexColor("#1e40af")
VIOLET = colors.HexColor("#7c3aed")
INK = colors.HexColor("#1e293b")
MUTED = colors.HexColor("#64748b")
FONT_FILES = {"Serif": "DejaVuSerif.ttf", "Serif-Bold": "DejaVuSerif-Bold.ttf",
              "Serif-Italic": "DejaVuSerif-Italic.ttf", "Sans": "DejaVuSans.ttf",
              "Sans-Bold": "DejaVuSans-Bold.ttf"}
LEVELS = {"Section": 0, "Entry": 1}

for font_name, file_name in FONT_FILES.items():
    pdfmetrics.registerFont(TTFont(font_name, FONTS / file_name))


def style(name, **options):
    """Return a paragraph style based on the body serif font."""
    return ParagraphStyle(name, **{"fontName": "Serif", "fontSize": 10.5, "leading": 15,
                                   "textColor": INK, **options})


STYLES = {
    "title": style("Title", fontName="Serif-Bold", fontSize=30, leading=38, alignment=TA_CENTER),
    "subtitle": style("Subtitle", fontName="Sans", fontSize=11, leading=18, alignment=TA_CENTER,
                      textColor=MUTED),
    "contents": style("Contents", fontName="Serif-Bold", fontSize=18, leading=24, spaceAfter=12),
    "section": style("Section", fontName="Serif-Bold", fontSize=24, leading=30, textColor=BLUE,
                     spaceAfter=10),
    "entry": style("Entry", fontName="Serif-Bold", fontSize=16, leading=21, textColor=BLUE,
                   spaceBefore=16, keepWithNext=True),
    "pron": style("Pron", fontName="Sans", fontSize=9, leading=13, textColor=VIOLET, keepWithNext=True),
    "meaning": style("Meaning", fontName="Serif-Italic", textColor=MUTED, spaceAfter=2, keepWithNext=True),
    "label": style("Label", fontName="Sans-Bold", fontSize=7.5, leading=11, textColor=MUTED,
                   spaceBefore=6, keepWithNext=True),
    "item": style("Item", leftIndent=12, spaceAfter=1),
    "source": style("Source", fontName="Sans", fontSize=7.5, leading=10, textColor=MUTED,
                    leftIndent=12, spaceAfter=4),
    "toc0": style("TOC0", fontName="Serif-Bold", fontSize=12, leading=20),
    "toc1": style("TOC1", fontSize=10, leading=13, leftIndent=16),
}


def page_footer(canvas, doc):
    """Draw the running footer with the page number."""
    canvas.saveState()
    canvas.setFont("Sans", 8)
    canvas.setFillColor(MUTED)
    canvas.drawCentredString(A4[0] / 2, MARGIN * 0.5, f"Word Hoard  ·  Page {doc.page}")
    canvas.restoreState()


class JournalDoc(BaseDocTemplate):
    """Document template that turns section and entry headings into contents entries."""

    def __init__(self, path):
        super().__init__(str(path), pagesize=A4, title="Word Hoard", leftMargin=MARGIN,
                         rightMargin=MARGIN, topMargin=MARGIN, bottomMargin=MARGIN)
        frame = Frame(MARGIN, MARGIN, A4[0] - 2 * MARGIN, A4[1] - 2 * MARGIN, id="main")
        self.addPageTemplates([PageTemplate(id="main", frames=frame, onPage=page_footer)])

    def afterFlowable(self, flowable):
        """Bookmark headings and register them in the contents and the PDF outline."""
        level = LEVELS.get(getattr(getattr(flowable, "style", None), "name", None))
        if level is None:
            return
        text = flowable.getPlainText()
        key = f"{level}-{text}"
        self.canv.bookmarkPage(key)
        self.canv.addOutlineEntry(text, key, level=level)
        self.notify("TOCEntry", (level, text, self.page, key))


def para(text, style_name):
    """Return a paragraph of plain text, escaped for ReportLab markup."""
    return Paragraph(escape(text), STYLES[style_name])


def source_line(example):
    """Return the attribution paragraph for an example."""
    if not example["source"]:
        return para("— Example sentence", "source")
    when = date.fromisoformat(example["date"]).strftime("%d %b %Y")
    link = f'<a href="{escape(example["url"])}" color="#2563eb">{escape(example["source"])}, {when}</a>'
    return Paragraph(f"— {link}", STYLES["source"])


def entry_story(entry):
    """Return the flowables for one accepted entry."""
    detail = entry["detail"]
    story = [para(entry["entry"], "entry")]
    if entry["respelling"]:
        story.append(para(f"{entry['respelling']}    {entry['pronunciation']}", "pron"))
    story += [para(entry["meaning"], "meaning"), para("MEANINGS", "label")]
    for n, sense in enumerate(detail["senses"], 1):
        pos = f'<font name="Sans-Bold" color="#7c3aed">{escape(sense["part_of_speech"])}</font>'
        story.append(Paragraph(f"{n}. {pos} {escape(sense['definition'])}", STYLES["item"]))
    story.append(para("EXAMPLES", "label"))
    for example in detail["examples"]:
        story += [para(example["text"], "item"), source_line(example)]
    for label, words in (("SYNONYMS", detail["synonyms"]), ("ANTONYMS", detail["antonyms"])):
        if words:
            story += [para(label, "label"), para(", ".join(words), "item")]
    return story


def section_story(title, entries):
    """Return a section heading followed by its entries, or nothing if there are none."""
    if not entries:
        return []
    story = [PageBreak(), para(title, "section")]
    for entry in sorted(entries, key=lambda e: fold(e["entry"])):
        story += entry_story(entry)
    return story


def front_matter(count):
    """Return the title page and the contents page."""
    contents = TableOfContents()
    contents.levelStyles = [STYLES["toc0"], STYLES["toc1"]]
    updated = date.today().strftime("%d %B %Y")
    return [Spacer(1, 6 * cm), para("Word Hoard", "title"),
            para("Accepted words and phrases for advanced learners of English", "subtitle"),
            para(f"{count} {'entry' if count == 1 else 'entries'}  ·  updated {updated}", "subtitle"),
            PageBreak(), para("Contents", "contents"), contents]


def build(entries):
    """Rebuild the PDF from all accepted entries, or remove it when there are none."""
    if not entries:
        PDF_PATH.unlink(missing_ok=True)
        return
    PDF_PATH.parent.mkdir(exist_ok=True)
    words = [e for e in entries if not vocab.is_phrase(e["entry"])]
    phrases = [e for e in entries if vocab.is_phrase(e["entry"])]
    story = front_matter(len(entries)) + section_story("Words", words) + section_story("Phrases", phrases)
    JournalDoc(PDF_PATH).multiBuild(story)
