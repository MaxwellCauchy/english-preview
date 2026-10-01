"""自制测试资料，不需要外部文档，也不含个人信息。"""

from pathlib import Path

from PIL import Image, ImageDraw
import reportlab
from reportlab.lib.pdfencrypt import StandardEncryption
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas

WIDTH, HEIGHT = 612, 792
FONT_DIR = Path(reportlab.__file__).resolve().parent / "fonts"
pdfmetrics.registerFont(TTFont("FixtureSans", str(FONT_DIR / "Vera.ttf")))
pdfmetrics.registerFont(TTFont("FixtureSans-Bold", str(FONT_DIR / "VeraBd.ttf")))


def _text(canvas: Canvas, x: float, top: float, value: str, size: int = 11, bold: bool = False) -> None:
    canvas.setFont("FixtureSans-Bold" if bold else "FixtureSans", size)
    canvas.drawString(x, HEIGHT - top, value)


def _furniture(canvas: Canvas, number: int) -> None:
    _text(canvas, 50, 28, "ENGLISH CLASS HANDOUT", 9)
    _text(canvas, 260, 765, f"Page {number} of 3", 9)


def make_image(folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (480, 180), "#eaf0ff")
    draw = ImageDraw.Draw(image)
    draw.rectangle((16, 16, 464, 164), outline="#3568b3", width=4)
    draw.text((45, 50), "READ -> UNDERSTAND -> REVIEW", fill="#17243a", font_size=22)
    path = folder / "fixture_image.png"
    image.save(path)
    return path


def make_sample(folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "sample.pdf"
    image = make_image(folder)
    canvas = Canvas(str(path), pagesize=(WIDTH, HEIGHT))
    canvas.setTitle("English Preview Demo")
    _furniture(canvas, 1)
    _text(canvas, 50, 100, "Reading Before Class", 23, True)
    _text(canvas, 50, 145, "1. Getting started", 15, True)
    _text(canvas, 50, 178, "Reading before class makes the lesson easier. This inter-")
    _text(canvas, 50, 194, "national example explains how ideas form a paragraph.")
    _text(canvas, 50, 228, "A well-")
    _text(canvas, 50, 244, "known method is to write short notes while reading.")
    _text(canvas, 50, 288, "2. A simple plan", 15, True)
    _text(canvas, 50, 320, "1. Read the title and predict the topic.")
    _text(canvas, 50, 346, "2. Underline useful words.")
    _text(canvas, 72, 362, "Keep their meanings in a notebook.")
    _text(canvas, 50, 388, "3. Summarise the article in two sentences.")
    _text(canvas, 50, 435, "Study schedule", 14, True)
    xpoints = [50, 210, 360, 560]
    for x in xpoints:
        canvas.line(x, HEIGHT - 464, x, HEIGHT - 554)
    for top in [464, 494, 524, 554]:
        canvas.line(50, HEIGHT - top, 560, HEIGHT - top)
    for row, values in enumerate([
        ("Activity", "Minutes", "Purpose"),
        ("Preview", "10", "Find the topic"),
        ("Review", "5", "Recall key ideas"),
    ]):
        for x, value in zip(xpoints, values):
            _text(canvas, x + 10, 484 + row * 30, value, 11, row == 0)
    _text(canvas, 50, 592, "This sentence follows the table.")
    canvas.showPage()

    _furniture(canvas, 2)
    # 居中的通栏标题，以及通栏段落分隔的两个双栏区域。
    _text(canvas, 150, 100, "Two-column Reading Practice", 19, True)
    for row in range(6):
        _text(canvas, 50, 155 + row * 16, f"LEFT-A{row + 1} introduces a useful idea.")
        _text(canvas, 330, 155 + row * 16, f"RIGHT-A{row + 1} develops another idea.")
    _text(canvas, 50, 315, "A full-width bridge comes after both upper columns and before the next pair.")
    for row in range(5):
        _text(canvas, 50, 365 + row * 16, f"LEFT-B{row + 1} starts the next passage.")
        _text(canvas, 330, 365 + row * 16, f"RIGHT-B{row + 1} closes the discussion.")
    canvas.showPage()

    _furniture(canvas, 3)
    _text(canvas, 50, 105, "Vocabulary and illustration", 16, True)
    _text(canvas, 50, 145, "The number below is part of the lesson, not a page number.")
    _text(canvas, 50, 180, "2026")
    _text(canvas, 50, 225, "A table without border lines", 14, True)
    for row, values in enumerate([
        ("Word", "Hits", "Note"), ("preview", "4", "important"),
        ("context", "7", "useful"), ("lecture", "2", "review"),
    ]):
        for x, value in zip((50, 230, 330), values):
            _text(canvas, x, 260 + row * 22, value, 11, row == 0)
    _text(canvas, 50, 395, "The illustration belongs here.")
    canvas.drawImage(str(image), 50, HEIGHT - 500, width=240, height=90)
    _text(canvas, 50, 540, "This sentence follows the image.")
    canvas.save()
    return path


def make_scan(folder: Path) -> Path:
    image = make_image(folder)
    path = folder / "scanned.pdf"
    canvas = Canvas(str(path), pagesize=(WIDTH, HEIGHT))
    canvas.drawImage(str(image), 0, 0, width=WIDTH, height=HEIGHT)
    canvas.save()
    return path


def make_encrypted(folder: Path) -> Path:
    path = folder / "protected.pdf"
    encryption = StandardEncryption("reader", ownerPassword="owner", canCopy=1)
    canvas = Canvas(str(path), pagesize=(WIDTH, HEIGHT), encrypt=encryption)
    _text(canvas, 50, 120, "A password-protected reading.")
    canvas.save()
    return path


def make_mixed_scan(folder: Path) -> Path:
    path = folder / "mixed.pdf"
    image = make_image(folder)
    canvas = Canvas(str(path), pagesize=(WIDTH, HEIGHT))
    _text(canvas, 50, 120, "The first page contains selectable text.")
    canvas.showPage()
    canvas.drawImage(str(image), 0, 0, width=WIDTH, height=HEIGHT)
    canvas.save()
    return path


def make_study_analysis(mode: str = "article"):
    """构造独立的预习测试结果，不读取真实 PDF，也不调用分析模型。"""
    from core.models import (AnalysisResult, AnalysisStats, Keyword, LongSentence,
                             ParagraphSummary, SectionOverview, TargetWord, WordFrequency)
    text = ("Students read complex books in the old library because they need reliable information "
            "and want to understand how people overcome difficult circumstances while building "
            "a more peaceful and hopeful community together.")
    count = len(text.split())
    second = "Volunteers discuss the crucible of change and offer paralegal support."
    return AnalysisResult(
        article_title="Study fixture", mode=mode,
        word_frequencies=[WordFrequency("penitentiary", "penitentiary", 3, "NN", [1]),
                          WordFrequency("crucible", "crucible", 2, "NN", [2]),
                          WordFrequency("felony", "felony", 1, "NN", [1]),
                          WordFrequency("one", "one", 20, "CD", [1]),
                          WordFrequency("get", "get", 20, "VB", [1])],
        keywords=[Keyword("crucible", 2.0, 2, [2]), Keyword("support", 1.0, 1, [2])],
        long_sentences=[LongSentence(text, count, 1, 1, 1)],
        paragraph_summaries=[ParagraphSummary(1, text, ["penitentiary"], count, 1),
                             ParagraphSummary(2, second, ["crucible", "support"], len(second.split()), 1),
                             ParagraphSummary(3, "(Applause)", [], 1, 1)],
        article_map=[SectionOverview("Reading", 2, [1, 2, 3], count + len(second.split()) + 1, [1])],
        target_words=[TargetWord("one", 1, ["One person offered support."], ["one person"], [1]),
                      TargetWord("penitentiary", 3, [text], ["the penitentiary"], [1])]
                     if mode == "vocabulary" else [],
        stats=AnalysisStats(total_words=count + len(second.split()) + 1, total_sentences=3,
                            total_paragraphs=3, avg_sentence_length=(count + len(second.split()) + 1) / 3),
    )


if __name__ == "__main__":
    location = Path(__file__).resolve().parent
    make_sample(location)
