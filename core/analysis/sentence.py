"""分句与词边界：保留缩写、撇号及连字符复合词。"""

import re
from collections.abc import Sequence

from nltk.tokenize import RegexpTokenizer

from ..layout import normalize_text
from ..models import AnalysisConfig, Document, ListNode, Paragraph, SentenceRecord
from .runtime import resource_error, sentence_tokenizer

WORD_PATTERN = r"[A-Za-z](?:\.[A-Za-z])+\.?|[A-Za-z]+(?:['’\-][A-Za-z]+)*"
WORD_RE = re.compile(WORD_PATTERN)
_WORDS = RegexpTokenizer(WORD_PATTERN)
SentenceInput = Sequence[SentenceRecord | str]


def word_tokens(text: str) -> list[str]:
    return _WORDS.tokenize(text)


def segment_sentences(text: str, *, min_words: int = 1) -> list[str]:
    """保留有效单词句 Yes.；需要规格中的两词过滤时传 min_words=2。"""
    if min_words < 1:
        raise ValueError("min_words 必须为正整数。")
    text = normalize_text(text)
    if not text:
        return []
    try:
        parts = sentence_tokenizer().tokenize(text)
    except LookupError as exc:
        raise resource_error(exc) from exc
    return [part.strip() for part in parts if len(word_tokens(part)) >= min_words]


def text_units(document: Document, config: AnalysisConfig) -> list[tuple[int, int, int, str]]:
    """(全局段号, 小节下标, 页号, 正文)；图片/表格/标题不作正文。"""
    units: list[tuple[int, int, int, str]] = []
    for section_index, section in enumerate(document.sections):
        for node in section.content:
            if isinstance(node, Paragraph) and normalize_text(node.text):
                units.append((len(units) + 1, section_index, node.page_number, normalize_text(node.text)))
            elif config.include_lists and isinstance(node, ListNode):
                for item in node.items:
                    if normalize_text(item.text):
                        units.append((len(units) + 1, section_index, node.page_number, normalize_text(item.text)))
    return units


def document_sentences(document: Document, config: AnalysisConfig) -> list[SentenceRecord]:
    return [
        SentenceRecord(text, paragraph, index, page)
        for paragraph, _, page, body in text_units(document, config)
        for index, text in enumerate(segment_sentences(body), 1)
    ]


def as_records(sentences: SentenceInput) -> list[SentenceRecord]:
    """直接传字符串列表时，每项视为独立段；真实位置应传 SentenceRecord。"""
    return [item if isinstance(item, SentenceRecord) else SentenceRecord(item, index)
            for index, item in enumerate(sentences, 1)]
