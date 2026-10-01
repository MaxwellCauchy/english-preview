"""PDF → 坐标文本块 → 清洗 → 有序文档 → Markdown。"""

import copy
import math
import re
import shutil
import tempfile
from collections import defaultdict
from pathlib import Path
from threading import Event
from typing import Callable

import pdfplumber
from pdfplumber.utils.exceptions import PdfminerException
from pdfminer.pdfdocument import PDFPasswordIncorrect, PDFTextExtractionNotAllowed
from pdfminer.pdfparser import PDFSyntaxError

from .layout import (
    LIST_PATTERN, PAGE_NUMBER_PATTERN, body_font_size, can_join, group_words,
    join_lines, normalize_text, order_page, split_row, words_to_block,
)
from .markdown_builder import to_markdown
from .models import (
    Block, ConversionResult, Document, ImageNode, ListItem, ListNode, Page,
    Paragraph, ReaderConfig, Section, TableNode,
)

ProgressCallback = Callable[[int, int, str], None]
PROJECT_ROOT = Path(__file__).resolve().parent.parent


class PDFReadError(Exception):
    """可以直接向用户显示的读取错误。"""


class PasswordRequiredError(PDFReadError):
    pass


class OCRRequiredError(PDFReadError):
    pass


class CancelledError(PDFReadError):
    pass


def _check_cancel(cancel_event: Event | None) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise CancelledError("读取已取消。")


def _inside(word: dict, bbox: tuple) -> bool:
    x = (word["x0"] + word["x1"]) / 2
    y = (word["top"] + word["bottom"]) / 2
    return bbox[0] - 1 <= x <= bbox[2] + 1 and bbox[1] - 1 <= y <= bbox[3] + 1


def _table_header(rows: list[list[str]]) -> bool:
    return bool(rows and any(re.search(r"[A-Za-z\u3400-\u9fff]", cell or "") for cell in rows[0]))


def _borderless_tables(words: list[dict]) -> list[tuple[tuple, list[list[str]]]]:
    """至少三行、列起点对齐、含数值或三列短文本才推断无框线表。"""
    candidates: list[tuple[tuple, list[list[str]]]] = []
    run: list[tuple[list[list[dict]], float]] = []

    def finish() -> None:
        if len(run) < 3:
            return
        rows = [[words_to_block(cell).text for cell in cells] for cells, _ in run]
        numeric_rows = sum(
            any(re.fullmatch(r"[-+]?\d[\d,.%:/\- ]*", cell.strip()) for cell in row)
            for row in rows[1:]
        )
        header_bold = sum(words_to_block(cell).is_bold for cell in run[0][0])
        short_three_columns = (
            len(rows[0]) >= 3 and header_bold > 0
            and all(len(cell.split()) <= 2 for row in rows for cell in row)
        )
        if numeric_rows == 0 and not short_three_columns:
            return
        flat = [word for cells, _ in run for cell in cells for word in cell]
        bbox = (
            min(w["x0"] for w in flat), min(w["top"] for w in flat),
            max(w["x1"] for w in flat), max(w["bottom"] for w in flat),
        )
        candidates.append((bbox, rows))

    for row in group_words(words):
        cells = split_row(row)
        valid = 2 <= len(cells) <= 8 and all(
            len(words_to_block(cell).text) <= 40 and len(cell) <= 6 for cell in cells
        )
        compatible = valid and (not run or (
            len(cells) == len(run[0][0])
            and all(abs(a[0]["x0"] - b[0]["x0"]) <= 7 for a, b in zip(cells, run[0][0]))
            and 0 < row[0]["top"] - run[-1][1] <= 28
        ))
        if not compatible:
            finish()
            run = []
        if valid:
            run.append((cells, row[0]["top"]))
    finish()
    return candidates


def _extract_tables(source, words: list[dict], target: Page, config: ReaderConfig) -> list[tuple]:
    boxes = []
    offset_x, offset_y = source.bbox[:2]
    for table in source.find_tables():
        rows = table.extract()
        if len(rows) < 2 or max((len(row) for row in rows), default=0) < 2:
            continue
        if sum(bool(cell and cell.strip()) for row in rows for cell in row) < 4:
            continue
        clean_rows = [[normalize_text(cell or "") for cell in row] for row in rows]
        bbox = table.bbox
        boxes.append(bbox)
        target.blocks.append(Block(
            "", bbox[0] - offset_x, bbox[1] - offset_y,
            bbox[2] - offset_x, bbox[3] - offset_y,
            kind="table", rows=clean_rows, has_header=_table_header(clean_rows),
        ))
        if any(cell is None for row in rows for cell in row):
            target.warnings.append(f"第 {target.page_number} 页表格有空格或合并单元格，请核对。")

    if config.detect_borderless_tables:
        remaining = [word for word in words if not any(_inside(word, bbox) for bbox in boxes)]
        for bbox, rows in _borderless_tables(remaining):
            boxes.append(bbox)
            target.blocks.append(Block(
                "", bbox[0] - offset_x, bbox[1] - offset_y,
                bbox[2] - offset_x, bbox[3] - offset_y,
                kind="table", rows=rows, has_header=_table_header(rows),
            ))
            target.warnings.append(f"第 {target.page_number} 页检测到无框线表格，请核对行列。")
    return boxes


def _extract_images(source, target: Page, assets_dir: Path, cancel_event: Event | None) -> None:
    seen = set()
    px0, py0, px1, py1 = source.bbox
    for index, image in enumerate(source.images, 1):
        _check_cancel(cancel_event)
        bbox = (
            max(px0, image["x0"]), max(py0, image["top"]),
            min(px1, image["x1"]), min(py1, image["bottom"]),
        )
        width, height = bbox[2] - bbox[0], bbox[3] - bbox[1]
        key = tuple(round(value, 1) for value in bbox)
        # 不导出小装饰，也不把整页扫描背景当作普通插图。
        if width < 12 or height < 12 or key in seen:
            continue
        if width * height > source.width * source.height * 0.85:
            continue
        seen.add(key)
        name = f"page_{target.page_number:04d}_image_{index:02d}.png"
        assets_dir.mkdir(parents=True, exist_ok=True)
        try:
            resolution = min(144, 4096 * 72 / max(width, height))
            source.crop(bbox).to_image(resolution=resolution, antialias=True).original.save(assets_dir / name)
        except (OSError, ValueError, RuntimeError):
            target.warnings.append(f"第 {target.page_number} 页第 {index} 张图片无法导出。")
            continue
        target.blocks.append(Block(
            "", bbox[0] - px0, bbox[1] - py0, bbox[2] - px0, bbox[3] - py0,
            kind="image", image_path="assets/" + name,
        ))


def extract_text_blocks(
    pdf_path: str | Path,
    *,
    config: ReaderConfig | None = None,
    password: str | None = None,
    assets_dir: str | Path | None = None,
    progress_callback: ProgressCallback | None = None,
    cancel_event: Event | None = None,
) -> list[Page]:
    """抽取带坐标的行、表格和图片块；页面编号从 1 开始。

    独立调用时不传 assets_dir 就不写图片。read_pdf 会提供此目录。
    """
    config = config or ReaderConfig()
    path = Path(pdf_path).expanduser()
    if not path.is_file():
        raise PDFReadError(f"找不到文件：{path.name}")
    if path.suffix.lower() != ".pdf":
        raise PDFReadError("请选择 .pdf 文件。")
    _check_cancel(cancel_event)
    try:
        with path.open("rb") as stream:
            if b"%PDF-" not in stream.read(1024):
                raise PDFReadError("文件内容不是有效的 PDF。")
        pages = []
        with pdfplumber.open(path, password=password or "", unicode_norm="NFC") as pdf:
            if not pdf.pages:
                raise PDFReadError("PDF 没有可读取的页面。")
            total = len(pdf.pages)
            for index, original_page in enumerate(pdf.pages, 1):
                _check_cancel(cancel_event)
                if progress_callback:
                    progress_callback(index - 1, total, f"正在读取第 {index}/{total} 页")
                source = original_page.dedupe_chars(tolerance=1)
                page = Page(index, float(source.width), float(source.height))
                # 不使用 PDF 内部文字流顺序；词与字符保留位置和字体。
                words = source.extract_words(
                    x_tolerance=2, y_tolerance=3, use_text_flow=False,
                    return_chars=True, expand_ligatures=True,
                )
                words = [word for word in words if word.get("text", "").strip()]
                if not words:
                    if source.images:
                        page.warnings.append(f"第 {index} 页没有文字层，可能是扫描页，需要 OCR。")
                    else:
                        page.warnings.append(f"第 {index} 页没有可提取文字，可能为空白页或轮廓文字。")
                    pages.append(page)
                    original_page.close()
                    continue
                table_boxes = _extract_tables(source, words, page, config)
                remaining = [word for word in words if not any(_inside(word, bbox) for bbox in table_boxes)]
                offset_x, offset_y = source.bbox[:2]
                for row in group_words(remaining):
                    for fragment in split_row(row):
                        block = words_to_block(fragment)
                        block.x0 -= offset_x
                        block.x1 -= offset_x
                        block.y0 -= offset_y
                        block.y1 -= offset_y
                        page.blocks.append(block)
                _check_cancel(cancel_event)
                if config.extract_images and assets_dir is not None:
                    _extract_images(source, page, Path(assets_dir), cancel_event)
                if any(not char.get("upright", True) for char in source.chars):
                    page.warnings.append(f"第 {index} 页有旋转文字，请核对阅读顺序。")
                pages.append(page)
                original_page.close()
            size = body_font_size(pages)
            for page in pages:
                order_page(page, config, size)
            if progress_callback:
                progress_callback(total, total, "抽取完成，正在清洗并还原结构")
            return pages
    except PdfminerException as exc:
        cause = exc.args[0] if exc.args else exc.__cause__
        if isinstance(cause, PDFPasswordIncorrect):
            raise PasswordRequiredError("PDF 已加密，请输入正确的打开密码。") from exc
        if isinstance(cause, PDFTextExtractionNotAllowed):
            raise PDFReadError("此 PDF 不允许提取文字，请使用允许读取的版本。") from exc
        raise PDFReadError("PDF 文件损坏、格式不完整或文字层无法解析。") from exc
    except PDFPasswordIncorrect as exc:
        raise PasswordRequiredError("PDF 已加密，请输入正确的打开密码。") from exc
    except PDFTextExtractionNotAllowed as exc:
        raise PDFReadError("此 PDF 不允许提取文字，请使用允许读取的版本。") from exc
    except PDFSyntaxError as exc:
        raise PDFReadError("PDF 文件损坏或格式不完整，无法读取。") from exc
    except PermissionError as exc:
        raise PDFReadError("没有文件访问权限，或输出目录不可写。") from exc
    except OSError as exc:
        raise PDFReadError("无法读取文件或保存图片，请检查文件和目录。") from exc
    except (ValueError, IndexError, TypeError) as exc:
        raise PDFReadError("PDF 内部数据异常，无法完整解析。") from exc


def _margin_key(block: Block, page: Page, config: ReaderConfig) -> tuple | None:
    if block.kind != "text":
        return None
    center = (block.y0 + block.y1) / 2
    if center <= page.height * config.margin_ratio:
        side = "top"
    elif center >= page.height * (1 - config.margin_ratio):
        side = "bottom"
    else:
        return None
    # 大字号标题保留；页眉数字归一化，只在相近纵坐标匹配。
    text = re.sub(r"\d+", "{n}", normalize_text(block.text).casefold())
    return side, round(center / page.height * 50), text


def clean_blocks(pages: list[Page], *, config: ReaderConfig | None = None) -> list[Page]:
    """文档级清洗，需要所有页面以检测重复页眉；不修改输入对象。"""
    config = config or ReaderConfig()
    result = copy.deepcopy(pages)
    body_size = body_font_size(result)
    repeats: dict[tuple, set[int]] = defaultdict(set)
    for page in result:
        for block in page.blocks:
            key = _margin_key(block, page, config)
            if key and block.font_size < body_size * config.heading_ratio:
                repeats[key].add(page.page_number)
    threshold = max(2, math.ceil(len(result) * config.repeat_ratio))
    for page in result:
        retained = []
        for block in page.blocks:
            if block.kind != "text":
                retained.append(block)
                continue
            block.text = normalize_text(block.text)
            if not block.text:
                continue
            key = _margin_key(block, page, config)
            if config.remove_headers and key:
                if PAGE_NUMBER_PATTERN.fullmatch(block.text):
                    continue
                if len(repeats.get(key, set())) >= threshold and block.font_size < body_size * config.heading_ratio:
                    continue
            retained.append(block)
        # 图片作为页末独立资源保留，不参与分栏和正文合并，避免插图打断句子。
        images = sorted((b for b in retained if b.kind == "image"), key=lambda b: (b.y0, b.x0))
        page.blocks = [b for b in retained if b.kind != "image"]
        # 去掉页眉后重排，防止通栏页眉改变正文区域划分。
        order_page(page, config, body_size)
        merged: list[Block] = []
        for block in page.blocks:
            if merged and can_join(merged[-1], block, page, body_size, config):
                previous = merged[-1]
                previous.text = join_lines(previous.text, block.text, config.dehyphenate)
                previous.last_x0, previous.last_x1, previous.last_y1 = block.x0, block.x1, block.y1
                previous.x0 = min(previous.x0, block.x0)
                previous.x1 = max(previous.x1, block.x1)
                previous.y1 = max(previous.y1, block.y1)
                previous.line_count += block.line_count
            else:
                merged.append(block)
        page.blocks = merged + images
    # 只清除文档结尾独立的 & 噪声，保留正文里的 R&D / A & B。
    for page in reversed(result):
        texts = [b for b in page.blocks if b.kind == "text"]
        if not texts:
            continue
        for block in texts[-6:]:
            if re.fullmatch(r"&+", block.text):
                page.blocks.remove(block)
        texts = [b for b in page.blocks if b.kind == "text"]
        if not texts:
            break
        final = texts[-1]
        final.text = re.sub(r"(?:\s*&)+$", "", final.text).rstrip()
        if not final.text:
            page.blocks.remove(final)
        break
    return result


def _heading(block: Block, page: Page, body_size: float, config: ReaderConfig) -> bool:
    if block.kind != "text" or block.line_count > 2 or len(block.text) > 160:
        return False
    if block.font_size >= body_size * config.heading_ratio:
        return True
    if LIST_PATTERN.match(block.text):
        return False
    short_bold = block.is_bold and len(block.text) <= 90 and not re.search(r"[.!?。！？]$", block.text)
    return short_bold and block.line_count == 1


def build_structure(pages: list[Page], *, config: ReaderConfig | None = None) -> Document:
    config = config or ReaderConfig()
    body_size = body_font_size(pages)
    document = Document(page_count=len(pages), warnings=[w for page in pages for w in page.warnings])
    current = Section()
    document.sections.append(current)
    blocks = [(page, block) for page in pages for block in page.blocks]
    first_page = pages[0].page_number if pages else 0
    title_seen = False
    list_base_x = 0.0
    last_list_position: tuple[int, int, int] | None = None
    last_text: tuple[Page, Block, Paragraph] | None = None
    for page, block in blocks:
        if _heading(block, page, body_size, config):
            last_text = None
            candidate_title = (
                not title_seen and page.page_number == first_page
                and block.y0 < page.height * 0.35 and not current.content
                and block.font_size >= body_size * config.heading_ratio
            )
            if candidate_title:
                document.title = block.text
                title_seen = True
                continue
            # 第一版只输出两级小标题，避免微小字号差异造成跳级。
            level = 2 if block.font_size >= body_size * 1.35 else 3
            current = Section(heading=block.text, level=level)
            document.sections.append(current)
            last_list_position = None
            continue
        if block.kind == "table":
            current.content.append(TableNode(block.rows, block.has_header, page.page_number))
            last_text = None
        elif block.kind == "image":
            current.content.append(ImageNode(block.image_path, f"第 {page.page_number} 页插图", page.page_number))
        else:
            match = LIST_PATTERN.match(block.text)
            if match:
                last_text = None
                number = int(match.group(2) or match.group(3)) if match.group(2) or match.group(3) else None
                ordered = number is not None
                position = (page.page_number, block.region, block.column)
                if (
                    current.content and isinstance(current.content[-1], ListNode)
                    and current.content[-1].ordered == ordered and last_list_position == position
                ):
                    node = current.content[-1]
                else:
                    node = ListNode(ordered=ordered, page_number=page.page_number)
                    current.content.append(node)
                    list_base_x = block.x0
                level = max(0, min(5, round((block.x0 - list_base_x) / max(12, body_size * 2))))
                node.items.append(ListItem(match.group(4), level, number))
                last_list_position = position
                continue
            previous_page, previous_block, previous_paragraph = last_text if last_text else (None, None, None)
            continues = bool(
                previous_page is not None and previous_block is not None
                and page.page_number == previous_page.page_number + 1
                and previous_block.y1 > previous_page.height * 0.85
                and block.y0 < page.height * 0.12
                and previous_block.column == block.column == 0
                and abs(previous_block.font_size - block.font_size) <= 1
                and not re.search(r'[.!?。！？]["\')”’]?$', previous_block.text)
                and re.match(r"^[a-z]", block.text)
            )
            if continues and previous_paragraph is not None:
                previous_paragraph.text = join_lines(previous_paragraph.text, block.text, config.dehyphenate)
                paragraph = previous_paragraph
            else:
                paragraph = Paragraph(block.text, page.page_number)
                current.content.append(paragraph)
            last_text = page, block, paragraph
        last_list_position = None
    document.sections = [section for section in document.sections if section.heading or section.content]
    return document


def read_pdf(
    pdf_path: str | Path,
    *,
    output_dir: str | Path | None = None,
    config: ReaderConfig | None = None,
    password: str | None = None,
    progress_callback: ProgressCallback | None = None,
    cancel_event: Event | None = None,
) -> ConversionResult:
    """完整转换，返回 Markdown、结构、提示及图片目录。

    每次转换在 output_dir 下创建独立工作目录，不覆盖已有输出。
    """
    _check_cancel(cancel_event)
    config = config or ReaderConfig()
    base = Path(output_dir) if output_dir is not None else PROJECT_ROOT / "output"
    try:
        base.mkdir(parents=True, exist_ok=True)
        work_dir = Path(tempfile.mkdtemp(prefix="read-", dir=base)).resolve()
    except OSError as exc:
        raise PDFReadError("输出目录不可写，请选择可写的目录。") from exc
    assets_dir = work_dir / "assets"
    try:
        pages = extract_text_blocks(
            pdf_path, config=config, password=password, assets_dir=assets_dir,
            progress_callback=progress_callback, cancel_event=cancel_event,
        )
        _check_cancel(cancel_event)
        pages = clean_blocks(pages, config=config)
        _check_cancel(cancel_event)
        document = build_structure(pages, config=config)
        if not any(page.blocks for page in pages):
            raise OCRRequiredError("没有可提取文字。该文件可能是扫描件或轮廓文字，需要先做 OCR。")
        markdown = to_markdown(document)
        _check_cancel(cancel_event)
        return ConversionResult(markdown, document, document.warnings, work_dir, assets_dir)
    except Exception:
        shutil.rmtree(work_dir, ignore_errors=True)
        raise


def pdf_to_markdown(pdf_path: str | Path, **kwargs) -> str:
    """简便接口；图片写入工作目录。需要保存图片时使用 read_pdf + save_markdown。"""
    return read_pdf(pdf_path, **kwargs).markdown
