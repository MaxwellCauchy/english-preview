"""几何阅读顺序与文本规则。使用保守启发式，不宣称理解任意 PDF 排版。"""

import re
import unicodedata
from collections import Counter
from statistics import median

from .models import Block, Page, ReaderConfig

LIST_PATTERN = re.compile(r"^(?:([•●▪◦‣\-+*])\s+|(?:\((\d+)\)|(\d+)[.)])\s+)(.+)$")
PAGE_NUMBER_PATTERN = re.compile(
    r"^(?:[-–—]?\s*\d{1,5}\s*[-–—]?|"
    r"page\s+\d+(?:\s+(?:of|/)\s+\d+)?|"
    r"\d+\s*/\s*\d+|第\s*\d+\s*页(?:\s*共\s*\d+\s*页)?)$",
    re.IGNORECASE,
)
CJK = r"\u3400-\u9fff"


def normalize_text(text: str) -> str:
    for source, replacement in {
        "ﬁ": "fi", "ﬂ": "fl", "ﬀ": "ff", "ﬃ": "ffi", "ﬄ": "ffl",
        "\u00a0": " ", "\u200b": "", "\u00ad": "",
        "\u2010": "-", "\u2011": "-",
        "\x01": " ",
    }.items():
        text = text.replace(source, replacement)
    text = "".join(char for char in text if char.isspace() or unicodedata.category(char) not in ("Cf", "Cc"))
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(fr"(?<=[{CJK}])\s+(?=[{CJK}])", "", text)
    return re.sub(r"\s+([,.;!?，。；！？])", r"\1", text)


def body_font_size(pages: list[Page]) -> float:
    counts: Counter[float] = Counter()
    for page in pages:
        for block in page.blocks:
            if block.kind == "text" and block.text.strip():
                counts[round(block.font_size * 2) / 2] += len(block.text.strip())
    return counts.most_common(1)[0][0] if counts else 10.0


def group_words(words: list[dict]) -> list[list[dict]]:
    rows: list[list[dict]] = []
    for word in sorted(words, key=lambda w: (w["top"], w["x0"])):
        tolerance = max(2.0, min(4.0, (word["bottom"] - word["top"]) * 0.28))
        target = None
        for row in reversed(rows[-3:]):
            if abs(row[0]["top"] - word["top"]) <= tolerance:
                target = row
                break
        if target is None:
            rows.append([word])
        else:
            target.append(word)
    for row in rows:
        row.sort(key=lambda w: w["x0"])
    return sorted(rows, key=lambda row: row[0]["top"])


def word_font(word: dict) -> float:
    chars = word.get("chars", [])
    return median([c.get("size", 10.0) for c in chars]) if chars else float(word.get("size", 10))


def words_to_block(words: list[dict]) -> Block:
    chars = [char for word in words for char in word.get("chars", [])]
    sizes = Counter(round(c.get("size", 10) * 2) / 2 for c in chars)
    font_size = sizes.most_common(1)[0][0] if sizes else word_font(words[0])
    bold_count = sum(
        any(token in str(c.get("fontname", "")).lower() for token in ("bold", "black", "heavy", "semibold"))
        for c in chars
    )
    text = words[0]["text"]
    for previous, current in zip(words, words[1:]):
        gap = current["x0"] - previous["x1"]
        separator = "" if gap < max(0.7, font_size * 0.12) else " "
        text += separator + current["text"]
    return Block(
        text=text,
        x0=min(w["x0"] for w in words),
        y0=min(w["top"] for w in words),
        x1=max(w["x1"] for w in words),
        y1=max(w["bottom"] for w in words),
        font_size=font_size,
        is_bold=bool(chars) and bold_count / len(chars) >= 0.5,
    )


def split_row(row: list[dict]) -> list[list[dict]]:
    """大水平间隙拆成片段，防止同一高度的左右栏串成一行。"""
    groups = [[row[0]]]
    for previous, current in zip(row, row[1:]):
        threshold = max(16.0, 2.2 * min(word_font(previous), word_font(current)))
        if current["x0"] - previous["x1"] > threshold:
            groups.append([current])
        else:
            groups[-1].append(current)
    return groups


def _gutter(page: Page, body_size: float, mode: str) -> float | None:
    if mode == "single":
        return None
    text = [
        b for b in page.blocks
        if b.kind == "text" and len(b.text) >= 20 and b.font_size < body_size * 1.25
    ]
    best = None
    best_score = -1.0
    for step in range(25, 76):
        x = page.width * step / 100
        left = [b for b in text if b.x1 < x]
        right = [b for b in text if b.x0 > x]
        crossing = len(text) - len(left) - len(right)
        if len(left) < 3 or len(right) < 3:
            continue
        gap = min(b.x0 for b in right) - max(b.x1 for b in left)
        vertical_overlap = min(max(b.y1 for b in left), max(b.y1 for b in right)) - max(
            min(b.y0 for b in left), min(b.y0 for b in right)
        )
        if gap < body_size or vertical_overlap < body_size * 2:
            continue
        if crossing > len(text) * 0.4:
            continue
        score = min(len(left), len(right)) * 3 - crossing - abs(x / page.width - 0.5)
        if score > best_score:
            best_score = score
            best = (max(b.x1 for b in left) + min(b.x0 for b in right)) / 2
    if best is None and mode == "double":
        return page.width / 2
    return best


def order_page(page: Page, config: ReaderConfig, body_size: float) -> None:
    gutter = _gutter(page, body_size, config.columns)
    if gutter is None:
        page.blocks.sort(key=lambda b: (b.y0, b.x0))
        for block in page.blocks:
            block.column, block.region = 0, 0
        texts = [b for b in page.blocks if b.kind == "text"]
        page.column_bounds = {0: (
            min((b.x0 for b in texts), default=0),
            max((b.x1 for b in texts), default=page.width),
        )}
        return

    spans = sorted([b for b in page.blocks if b.x0 < gutter < b.x1], key=lambda b: (b.y0, b.x0))
    sides = [b for b in page.blocks if b not in spans]
    for block in sides:
        block.column = 0 if (block.x0 + block.x1) / 2 < gutter else 1
    page.column_bounds = {}
    for column in (0, 1):
        texts = [b for b in sides if b.column == column and b.kind == "text"]
        page.column_bounds[column] = (
            min((b.x0 for b in texts), default=0 if column == 0 else gutter),
            max((b.x1 for b in texts), default=gutter if column == 0 else page.width),
        )
    page.column_bounds[-1] = (
        min((b.x0 for b in page.blocks), default=0),
        max((b.x1 for b in page.blocks), default=page.width),
    )

    ordered: list[Block] = []
    region = 0
    previous_was_span = False
    for span in spans:
        before = [b for b in sides if (b.y0 + b.y1) / 2 < (span.y0 + span.y1) / 2]
        if before:
            if previous_was_span:
                region += 1
            for block in sorted(before, key=lambda b: (b.column, b.y0, b.x0)):
                block.region = region
                ordered.append(block)
            sides = [b for b in sides if b not in before]
            region += 1
        span.column, span.region = -1, region
        ordered.append(span)
        previous_was_span = True
    if sides:
        if spans:
            region += 1
        for block in sorted(sides, key=lambda b: (b.column, b.y0, b.x0)):
            block.region = region
            ordered.append(block)
    page.blocks = ordered


def join_lines(previous: str, following: str, dehyphenate: bool = True) -> str:
    if previous.endswith("-") and re.match(r"^[a-z]", following):
        fragment_match = re.search(r"([A-Za-z]+(?:-[A-Za-z]+)*)-$", previous)
        fragment = fragment_match.group(1).lower() if fragment_match else ""
        preserve_prefixes = {
            "well", "self", "non", "co", "re", "pre", "post", "cross", "long",
            "short", "high", "low", "part", "full", "half", "ex",
            "above", "absent",
        }
        if dehyphenate and fragment and "-" not in fragment and fragment not in preserve_prefixes:
            return previous[:-1] + following
        return previous + following
    if re.search(fr"[{CJK}]$", previous) and re.match(fr"^[{CJK}]", following):
        return previous + following
    return previous + " " + following


def can_join(previous: Block, current: Block, page: Page, body_size: float, config: ReaderConfig) -> bool:
    if previous.kind != "text" or current.kind != "text":
        return False
    if (previous.column, previous.region) != (current.column, current.region):
        return False
    if max(previous.font_size, current.font_size) >= body_size * config.heading_ratio:
        return False
    if previous.is_bold != current.is_bold or (previous.is_bold and len(previous.text) < 100):
        return False
    if abs(previous.font_size - current.font_size) > 1:
        return False
    bottom = previous.last_y1 if previous.last_y1 is not None else previous.y1
    gap = current.y0 - bottom
    if gap < -1 or gap > max(4.0, body_size * 0.8):
        return False
    if LIST_PATTERN.match(current.text):
        return False
    previous_is_list = LIST_PATTERN.match(previous.text) is not None
    indent = current.x0 - previous.x0
    if previous_is_list:
        return body_size * 0.5 <= indent <= body_size * 4
    if indent > body_size * 0.8 or indent < -body_size * 3:
        return False
    left, right = page.column_bounds.get(previous.column, (0, page.width))
    last_left = previous.last_x0 if previous.last_x0 is not None else previous.x0
    last_right = previous.last_x1 if previous.last_x1 is not None else previous.x1
    short_line = last_right - last_left < max(1, right - left) * 0.62
    if short_line and re.search(r'[.!?。！？:：]["\')”’]?\s*$', previous.text):
        return False
    return True
