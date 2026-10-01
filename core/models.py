"""各阶段共用的数据结构。坐标单位为 PDF 点，原点在页面左上角。"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


@dataclass
class Block:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    font_size: float = 10.0
    is_bold: bool = False
    kind: Literal["text", "table", "image"] = "text"
    column: int = 0
    region: int = 0
    rows: list[list[str]] = field(default_factory=list)
    image_path: str = ""
    has_header: bool = True
    line_count: int = 1
    last_x0: float | None = None
    last_x1: float | None = None
    last_y1: float | None = None


@dataclass
class Page:
    page_number: int
    width: float
    height: float
    blocks: list[Block] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    column_bounds: dict[int, tuple[float, float]] = field(default_factory=dict)


@dataclass
class Paragraph:
    text: str
    page_number: int = 0


@dataclass
class ListItem:
    text: str
    level: int = 0
    number: int | None = None


@dataclass
class ListNode:
    ordered: bool
    items: list[ListItem] = field(default_factory=list)
    page_number: int = 0


@dataclass
class TableNode:
    rows: list[list[str]]
    has_header: bool = True
    page_number: int = 0


@dataclass
class ImageNode:
    path: str
    alt: str = ""
    page_number: int = 0


ContentNode = Paragraph | ListNode | TableNode | ImageNode


@dataclass
class Section:
    heading: str | None = None
    level: int = 2
    # 一个有序列表保留正文、列表、表格、图片的原始穿插次序。
    content: list[ContentNode] = field(default_factory=list)

    @property
    def paragraphs(self) -> list[Paragraph]:
        return [node for node in self.content if isinstance(node, Paragraph)]

    @property
    def lists(self) -> list[ListNode]:
        return [node for node in self.content if isinstance(node, ListNode)]

    @property
    def tables(self) -> list[TableNode]:
        return [node for node in self.content if isinstance(node, TableNode)]

    @property
    def images(self) -> list[ImageNode]:
        return [node for node in self.content if isinstance(node, ImageNode)]


@dataclass
class Document:
    title: str = ""
    sections: list[Section] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    page_count: int = 0


@dataclass
class ReaderConfig:
    columns: Literal["auto", "single", "double"] = "auto"
    remove_headers: bool = True
    dehyphenate: bool = True
    extract_images: bool = True
    detect_borderless_tables: bool = True
    margin_ratio: float = 0.08
    repeat_ratio: float = 0.6
    heading_ratio: float = 1.2

    def __post_init__(self) -> None:
        if self.columns not in ("auto", "single", "double"):
            raise ValueError("columns 必须为 auto、single 或 double。")
        if not 0 < self.margin_ratio < 0.25:
            raise ValueError("margin_ratio 必须在 0 与 0.25 之间。")
        if not 0 < self.repeat_ratio <= 1:
            raise ValueError("repeat_ratio 必须在 0 与 1 之间。")
        if self.heading_ratio <= 1:
            raise ValueError("heading_ratio 必须大于 1。")


@dataclass
class ConversionResult:
    markdown: str
    document: Document
    warnings: list[str]
    work_dir: Path
    assets_dir: Path

    @property
    def page_count(self) -> int:
        return self.document.page_count


@dataclass
class AnalysisConfig:
    max_words_per_sentence: int = 25
    top_keywords: int = 15
    min_word_length: int = 3
    use_lemmatization: bool = True
    min_frequency: int = 2
    ignore_case: bool = True
    mode: Literal["auto", "article", "vocabulary"] = "auto"
    target_words: list[str] | None = None
    prefix_length: int = 2
    max_examples: int = 3
    include_lists: bool = False

    def __post_init__(self) -> None:
        for name in ("max_words_per_sentence", "top_keywords", "min_word_length", "min_frequency", "max_examples"):
            if not isinstance(getattr(self, name), int) or getattr(self, name) < 1:
                raise ValueError(f"{name} 必须为正整数。")
        if self.mode not in ("auto", "article", "vocabulary"):
            raise ValueError("mode 必须为 auto、article 或 vocabulary。")
        if not 1 <= self.prefix_length <= 5:
            raise ValueError("prefix_length 必须在 1 到 5 之间。")
        if self.target_words is not None and not isinstance(self.target_words, list):
            raise ValueError("target_words 必须为词列表或 None。")


@dataclass(frozen=True)
class SentenceRecord:
    text: str
    paragraph_index: int
    sentence_index: int = 1
    page_number: int = 0


@dataclass
class WordFrequency:
    word: str
    display: str
    count: int
    pos: str = ""
    locations: list[int] = field(default_factory=list)


@dataclass
class Keyword:
    word: str
    score: float
    count: int
    locations: list[int] = field(default_factory=list)


@dataclass
class LongSentence:
    text: str
    word_count: int
    paragraph_index: int
    sentence_index: int
    page_number: int = 0


@dataclass
class ParagraphSummary:
    index: int
    first_sentence: str
    topic_words: list[str]
    word_count: int
    page_number: int = 0


@dataclass
class AnalysisStats:
    total_words: int = 0
    total_sentences: int = 0
    total_paragraphs: int = 0
    avg_sentence_length: float = 0.0
    unique_words: int = 0
    type_token_ratio: float = 0.0


@dataclass
class SectionOverview:
    heading: str
    level: int
    paragraph_indices: list[int]
    word_count: int
    page_numbers: list[int] = field(default_factory=list)


@dataclass
class TargetWord:
    word: str
    count: int = 0
    examples: list[str] = field(default_factory=list)
    collocations: list[str] = field(default_factory=list)
    locations: list[int] = field(default_factory=list)


@dataclass
class PrefixGroup:
    prefix: str
    words: list[str]
    word_count: int
    seen_count: int
    occurrence_count: int


@dataclass
class AffixHint:
    affix: str
    meaning: str
    examples: list[str]
    source: str


@dataclass
class VocabularyProgress:
    source: Literal["provided", "candidate"] = "candidate"
    total_targets: int | None = None
    seen_targets: int = 0
    coverage: float | None = None
    missing_words: list[str] = field(default_factory=list)


@dataclass
class AnalysisResult:
    word_frequencies: list[WordFrequency] = field(default_factory=list)
    keywords: list[Keyword] = field(default_factory=list)
    long_sentences: list[LongSentence] = field(default_factory=list)
    paragraph_summaries: list[ParagraphSummary] = field(default_factory=list)
    stats: AnalysisStats = field(default_factory=AnalysisStats)
    mode: Literal["article", "vocabulary"] = "article"
    mode_reason: str = ""
    article_title: str = ""
    article_map: list[SectionOverview] = field(default_factory=list)
    target_words: list[TargetWord] = field(default_factory=list)
    prefix_groups: list[PrefixGroup] = field(default_factory=list)
    affix_hints: list[AffixHint] = field(default_factory=list)
    vocabulary_progress: VocabularyProgress = field(default_factory=VocabularyProgress)
    warnings: list[str] = field(default_factory=list)
