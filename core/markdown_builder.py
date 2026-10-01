"""把有序文档节点转换为 Markdown，不依赖 PDF 或界面。"""

import re
from urllib.parse import quote

from .models import Document, ImageNode, ListNode, Paragraph, TableNode


def _inline(text: str) -> str:
    """PDF 文本按字面输出，避免星号或 HTML 被解释为格式。"""
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return re.sub(r"([\\\x60*_\[\]])", r"\\\1", text)


def _paragraph(text: str) -> str:
    text = _inline(text)
    return re.sub(r"^(\s*)(#{1,6}\s|>\s|[-+]\s|\d+[.)]\s)", r"\1\\\2", text)


def _table(node: TableNode) -> str:
    if not node.rows:
        return ""
    width = max(len(row) for row in node.rows)
    if width == 0:
        return ""
    rows = [
        [
            _inline(cell or "").replace("|", r"\|").replace("\n", "<br>")
            for cell in row
        ] + [""] * (width - len(row))
        for row in node.rows
    ]
    if not node.has_header:
        rows.insert(0, [f"列 {i + 1}" for i in range(width)])
    rows.insert(1, ["---"] * width)
    return "\n".join("| " + " | ".join(row) + " |" for row in rows)


def to_markdown(document: Document) -> str:
    parts: list[str] = []
    if document.title:
        parts.append("# " + _inline(document.title))
    for section in document.sections:
        if section.heading:
            level = min(6, max(2, section.level))
            parts.append("#" * level + " " + _inline(section.heading))
        for node in section.content:
            if isinstance(node, Paragraph):
                parts.append(_paragraph(node.text))
            elif isinstance(node, ListNode):
                lines = []
                for item in node.items:
                    marker = f"{item.number if item.number is not None else 1}." if node.ordered else "-"
                    lines.append("    " * item.level + marker + " " + _inline(item.text))
                parts.append("\n".join(lines))
            elif isinstance(node, TableNode):
                parts.append(_table(node))
            elif isinstance(node, ImageNode):
                alt = _inline(node.alt)
                path = quote(node.path.replace("\\", "/"), safe="/-._~")
                parts.append(f"![{alt}]({path})")
    return "\n\n".join(part.strip() for part in parts if part.strip()) + "\n"
