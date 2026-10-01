"""预习清单数据模型；全部字段有默认值，独立于 core.models。"""

from dataclasses import dataclass, field

from ..models import AnalysisStats


@dataclass
class StudyConfig:
    """预习输出数量、考试目标和可选翻译；general 保留 v0.3 接口行为。"""

    use_dictionary: bool = True
    use_wordlists: bool = True
    top_study_words: int = 15
    max_long_sentences: int = 5
    max_key_paragraphs: int = 8
    min_sentence_words: int = 25
    exclude_stage_directions: bool = True
    min_paragraph_words: int = 5
    exam_level: str = "general"
    max_phrases: int = 12
    translate_sentences: bool = False
    translation_model_dir: str = ""


    def __post_init__(self) -> None:
        for name in ("top_study_words", "max_long_sentences", "max_key_paragraphs",
                     "min_sentence_words", "min_paragraph_words", "max_phrases"):
            value = getattr(self, name)
            if type(value) is not int or not 1 <= value <= 1000:
                raise ValueError(f"{name} 必须为 1 到 1000 之间的整数。")
        for name in ("use_dictionary", "use_wordlists", "exclude_stage_directions", "translate_sentences"):
            if type(getattr(self, name)) is not bool:
                raise ValueError(f"{name} 必须为布尔值。")

        if self.exam_level not in ("general", "cet4", "cet6"):
            raise ValueError("exam_level 必须为 general、cet4 或 cet6。")
        if not isinstance(self.translation_model_dir, str):
            raise ValueError("translation_model_dir 必须为路径字符串。")


@dataclass
class StudyWord:
    """一个待学词；释义空串表示未取得词典条目，不生成虚构释义。"""

    word: str = ""
    display: str = ""
    count: int = 0
    locations: list[int] = field(default_factory=list)
    pos: str = ""
    meaning_cn: str = ""
    meaning_en: str = ""
    collocations: list[str] = field(default_factory=list)
    collins_star: int = 0
    oxford_flag: bool = False
    source: str = ""
    exam_levels: list[str] = field(default_factory=list)
    selection_reasons: list[str] = field(default_factory=list)
    score: float = 0.0


@dataclass
class StudyPhrase:
    phrase: str = ""
    meaning_cn: str = ""
    count: int = 0
    locations: list[int] = field(default_factory=list)
    examples: list[str] = field(default_factory=list)
    forms: list[str] = field(default_factory=list)
    exam_levels: list[str] = field(default_factory=list)
    source: str = ""
    selection_reasons: list[str] = field(default_factory=list)
    score: float = 0.0


@dataclass
class SentenceBreakdown:
    """规则提取的主干候选，保留原句和原分析中的段号、句号。"""

    text: str = ""
    word_count: int = 0
    paragraph_index: int = 0
    sentence_index: int = 0
    main_clause: str = ""
    modifiers: list[str] = field(default_factory=list)
    note: str = ""
    selection_reasons: list[str] = field(default_factory=list)
    matched_words: list[str] = field(default_factory=list)
    matched_phrases: list[str] = field(default_factory=list)
    translation: str = ""
    translation_status: str = "not_requested"
    translation_note: str = ""
    context_before: str = ""
    page_number: int = 0
    score: float = 0.0


@dataclass
class RankedParagraph:
    """按词数和关键词命中排序的段落，首句是原文线索。"""

    index: int = 0
    first_sentence: str = ""
    topic_words: list[str] = field(default_factory=list)
    word_count: int = 0
    score: float = 0.0
    reason: str = ""


@dataclass
class OutlineBlock:
    """一个文章结构块；paragraph_range 两端均包含在区间内。"""

    title: str = ""
    paragraph_range: tuple[int, int] = (0, 0)
    word_count: int = 0
    summary: str = ""


@dataclass
class ArticleOutline:
    """文章结构块的有序列表；空文章返回空列表。"""

    blocks: list[OutlineBlock] = field(default_factory=list)


@dataclass
class StudyList:
    """可供 UI、Markdown 和 HTML 共用的预习清单。"""

    title: str = ""
    mode: str = "article"
    overview: str = ""
    study_words: list[StudyWord] = field(default_factory=list)
    sentence_breakdowns: list[SentenceBreakdown] = field(default_factory=list)
    key_paragraphs: list[RankedParagraph] = field(default_factory=list)
    outline: ArticleOutline = field(default_factory=ArticleOutline)
    action_items: list[str] = field(default_factory=list)
    stats: AnalysisStats = field(default_factory=AnalysisStats)
    warnings: list[str] = field(default_factory=list)
    exam_level: str = "general"
    study_phrases: list[StudyPhrase] = field(default_factory=list)
