# English Preview v0.3 工程交接

以已交付 v0.2 为基础。保持读取、分析入口不变，新增独立预习层。

## 完整文件树（运行生成目录另计）

- `english-preview/`
  - `core/`
    - `analysis/`
      - `__init__.py`
      - `frequency.py`
      - `keywords.py`
      - `long_sentences.py`
      - `paragraph.py`
      - `report.py`
      - `runtime.py`
      - `sentence.py`
      - `stats.py`
      - `vocabulary.py`
    - `study/`
      - `__init__.py`
      - `builder.py`
      - `dictionary.py`
      - `main_structure.py`
      - `models.py`
      - `outline.py`
      - `paragraph_rank.py`
      - `render.py`
      - `study_words.py`
      - `wordlist.py`
    - `__init__.py`
    - `analyzer.py`
    - `exporter.py`
    - `layout.py`
    - `llm_client.py`
    - `markdown_builder.py`
    - `models.py`
    - `pdf_reader.py`
  - `docs/`
    - `development_ports.md`
    - `project_handoff_v03.md`
    - `third_party_resources.md`
    - `verification.md`
    - `verification_v02.md`
    - `verification_v03.md`
  - `examples/`
    - `article.txt`
    - `lexicon_check_targets.txt`
    - `libraries_targets.txt`
  - `resources/`
    - `dictionary/`
      - `.gitkeep`
      - `ECDICT_LICENSE.txt`
      - `ecdict.csv`
    - `icons/`
      - `.gitkeep`
    - `nltk_data/`
      - `corpora/`
        - `stopwords/`
          - `README`
          - `english`
        - `wordnet.zip`
      - `taggers/`
        - `averaged_perceptron_tagger_eng/`
          - `averaged_perceptron_tagger_eng.classes.json`
          - `averaged_perceptron_tagger_eng.tagdict.json`
          - `averaged_perceptron_tagger_eng.weights.json`
      - `tokenizers/`
        - `punkt_tab/`
          - `english/`
            - `abbrev_types.txt`
            - `collocations.tab`
            - `ortho_context.tab`
            - `sent_starters.txt`
          - `README`
      - `NLTK_LICENSE.txt`
      - `SOURCES.json`
      - `TAGGER_LICENSE.txt`
      - `WORDNET_LICENSE.txt`
    - `study_templates/`
      - `study_list.html`
    - `wordlists/`
      - `awl.txt`
      - `cet4_cet6.txt`
      - `top2000.txt`
      - `top3000.txt`
    - `affixes.json`
    - `study_resources.json`
  - `templates/`
    - `preview_template.html`
    - `style.css`
  - `tests/`
    - `__init__.py`
    - `fixture_image.png`
    - `fixtures.py`
    - `sample.pdf`
    - `test_analyzer.py`
    - `test_pdf_reader.py`
    - `test_study.py`
  - `tools/`
    - `check_lexicon.py`
    - `check_study.py`
    - `prepare_study_resources.py`
  - `ui/`
    - `__init__.py`
    - `analysis_panel.py`
    - `main_window.py`
    - `study_panel.py`
    - `widgets.py`
  - `.gitignore`
  - `README.md`
  - `main.py`
  - `requirements-dev.txt`
  - `requirements.txt`
  - `run_windows.bat`
  - `output/`：运行生成的 Markdown、图片及临时文件。

## core/models.py 全文

```python
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
```

## core/study/models.py 全文

```python
"""预习清单数据模型；全部字段有默认值，独立于 core.models。"""

from dataclasses import dataclass, field

from ..models import AnalysisStats


@dataclass
class StudyConfig:
    """预习输出数量和过滤选项；数量范围为 1..1000。"""

    use_dictionary: bool = True
    use_wordlists: bool = True
    top_study_words: int = 15
    max_long_sentences: int = 5
    max_key_paragraphs: int = 8
    min_sentence_words: int = 25
    exclude_stage_directions: bool = True
    min_paragraph_words: int = 5

    def __post_init__(self) -> None:
        for name in ("top_study_words", "max_long_sentences", "max_key_paragraphs",
                     "min_sentence_words", "min_paragraph_words"):
            value = getattr(self, name)
            if type(value) is not int or not 1 <= value <= 1000:
                raise ValueError(f"{name} 必须为 1 到 1000 之间的整数。")
        for name in ("use_dictionary", "use_wordlists", "exclude_stage_directions"):
            if type(getattr(self, name)) is not bool:
                raise ValueError(f"{name} 必须为布尔值。")


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
```

## 分析函数签名

### core/analyzer.py

```python
def analyze_document(document: Document, config: AnalysisConfig | None=None, *, progress_callback: Callable[[int, int, str], None] | None=None, cancel_event: Event | None=None) -> AnalysisResult: ...```

### core/analysis/frequency.py

```python
def check_cancel(cancel_event: Event | None) -> None: ...
def prepare(sentences: SentenceInput, config: AnalysisConfig, cancel_event: Event | None=None) -> list[PreparedSentence]: ...
def frequencies(prepared: list[PreparedSentence]) -> list[WordFrequency]: ...
def analyze_word_frequency(sentences: SentenceInput, config: AnalysisConfig | None=None) -> list[WordFrequency]: ...```

### core/analysis/keywords.py

```python
def keywords(prepared: list[PreparedSentence], config: AnalysisConfig) -> list[Keyword]: ...
def extract_keywords(sentences: SentenceInput, config: AnalysisConfig | None=None) -> list[Keyword]: ...```

### core/analysis/long_sentences.py

```python
def long_sentences(records: list[SentenceRecord], config: AnalysisConfig) -> list[LongSentence]: ...
def detect_long_sentences(document: Document, config: AnalysisConfig | None=None) -> list[LongSentence]: ...```

### core/analysis/paragraph.py

```python
def summaries(document: Document, prepared: list[PreparedSentence], config: AnalysisConfig) -> list[ParagraphSummary]: ...
def summarize_paragraphs(document: Document, config: AnalysisConfig | None=None) -> list[ParagraphSummary]: ...
def article_map(document: Document, config: AnalysisConfig) -> list[SectionOverview]: ...```

### core/analysis/report.py

```python
def _literal(text: str) -> str: ...
def report_sections(result: AnalysisResult) -> dict[str, str]: ...
def analysis_to_markdown(result: AnalysisResult) -> str: ...
def analysis_to_json(result: AnalysisResult) -> str: ...
def save_analysis(result: AnalysisResult, destination: str | Path) -> Path: ...```

### core/analysis/runtime.py

```python
class AnalysisError(Exception): ...
class AnalysisCancelled(AnalysisError): ...
def sentence_tokenizer() -> PunktTokenizer: ...
def stop_words() -> frozenset[str]: ...
def pos_tagger() -> PerceptronTagger: ...
def lemmatizer() -> WordNetLemmatizer: ...
def resource_error(exc: LookupError) -> AnalysisError: ...```

### core/analysis/sentence.py

```python
def word_tokens(text: str) -> list[str]: ...
def segment_sentences(text: str, *, min_words: int=1) -> list[str]: ...
def text_units(document: Document, config: AnalysisConfig) -> list[tuple[int, int, int, str]]: ...
def document_sentences(document: Document, config: AnalysisConfig) -> list[SentenceRecord]: ...
def as_records(sentences: SentenceInput) -> list[SentenceRecord]: ...```

### core/analysis/stats.py

```python
def compute_stats(document: Document, sentences: SentenceInput, config: AnalysisConfig | None=None) -> AnalysisStats: ...```

### core/analysis/vocabulary.py

```python
def validate_targets(words: list[str]) -> list[str]: ...
def load_target_words(path: str | Path) -> list[str]: ...
def choose_mode(document: Document, prepared: list[PreparedSentence], config: AnalysisConfig) -> tuple[str, str]: ...
def _collocation(sentence: PreparedSentence, position: int) -> str: ...
def vocabulary(prepared: list[PreparedSentence], config: AnalysisConfig) -> tuple[list[TargetWord], list[PrefixGroup], list[AffixHint], VocabularyProgress, list[str]]: ...```

## 预习函数签名

### core/study/builder.py

```python
class StudyCancelled(Exception): ...
def build_study_list(result: AnalysisResult, config: StudyConfig | None=None, *, progress_callback: Callable[[int, int, str], None] | None=None) -> StudyList: ...```

### core/study/dictionary.py

```python
def load_ecdict(path: Path) -> dict[str, dict]: ...
def lookup(word: str) -> dict | None: ...
def entry_fields(entry: dict) -> dict: ...
def is_loaded() -> bool: ...
def clear_cache() -> None: ...```

### core/study/main_structure.py

```python
def extract_main_structure(sentence: LongSentence, config: StudyConfig) -> SentenceBreakdown: ...```

### core/study/outline.py

```python
def build_outline(result: AnalysisResult, config: StudyConfig) -> ArticleOutline: ...```

### core/study/paragraph_rank.py

```python
def rank_paragraphs(result: AnalysisResult, config: StudyConfig) -> list[RankedParagraph]: ...```

### core/study/render.py

```python
def _md(text: str) -> str: ...
def study_list_to_markdown(study: StudyList) -> str: ...
def study_list_to_html(study: StudyList) -> str: ...
def save_study_list(study: StudyList, destination: Path, fmt: str='md') -> Path: ...```

### core/study/study_words.py

```python
def _ensure_dictionary(config: StudyConfig) -> None: ...
def _make_word(word: str, display: str, count: int, locations: list[int], pos: str, config: StudyConfig, collocations: list[str] | None=None) -> StudyWord: ...
def _score(word: StudyWord) -> float: ...
def select_study_words(frequencies: list[WordFrequency], config: StudyConfig) -> list[StudyWord]: ...
def select_target_words(targets: list[TargetWord], config: StudyConfig) -> list[StudyWord]: ...```

### core/study/wordlist.py

```python
def load_wordlist(path: Path) -> frozenset[str]: ...
def load_top2000() -> frozenset[str]: ...
def load_top3000() -> frozenset[str]: ...
def load_awl() -> frozenset[str]: ...
def load_cet() -> frozenset[str]: ...
def is_basic_word(word: str, *, use_top2000: bool=True) -> bool: ...
def is_stopword(word: str) -> bool: ...
def clear_cache() -> None: ...```

## UI 标签页

主窗口三个标签页：Markdown、分析、预习单。公共区域保持文件选择/拖拽、读取配置、开始/取消/复制/保存、进度和状态。

分析页保留原分类；预习页为数量设置 → 文章速览 → 学习词 → 长句主干候选和全文详情 → 关键段 → 文章结构 → 只读行动任务，底部复制和 Markdown/HTML 保存。主体可滚动。

MainWindow 缓存 analysis_result、study_result；分析配置快照相同时复用，否则重新分析。切换文件或重新读取清除结果。后台线程只处理核心操作，经队列交给 _poll 更新 Tk。取消后晚到结果被丢弃。Markdown 编辑不改变 Document。

## requirements.txt 全文

```text
pdfplumber==0.11.8
tkinterdnd2==0.6.3
nltk==3.10.3
```

### requirements-dev.txt

```text
-r requirements.txt
reportlab>=4.2,<5
Pillow>=10.1,<13
```

## resources 现状

ECDICT 项目词条版已附，82,871,515 字节。四份词表及 NLTK 英文资源已附；icons/ 仍预留，无 app.ico。affixes.json 保留原规则；study_templates/study_list.html 为备用模板。详细来源如下：

```json
{
  "prepared_date": "2026-09-30",
  "ecdict_commit": "bc015ed2e24a7abef49fc6dbbb7fe32c1dadaf8b",
  "ecdict_url": "https://raw.githubusercontent.com/skywind3000/ECDICT/bc015ed2e24a7abef49fc6dbbb7fe32c1dadaf8b/stardict.7z",
  "upstream_rows": 3402564,
  "ecdict_rows": 1146124,
  "ecdict_unique_words": 1146124,
  "upstream_csv_sha256": "88fce01e0a30524192a62e363d47eeb036fa17820d5826121b3b419fd67a3996",
  "derivation": "保留分析器可识别的单词、连字符词、撇号词和缩写；去除未统计标注的自动派生词；不包含短语条目。保留上游大小写条目顺序，查词时按小写匹配，规范化重复项以后者优先。",
  "ecdict_sha256": "13f866ca6a021242fcffbf592c1b0e48875787aa03ecf20fc0a8d503c3f4cd2f",
  "ecdict_license": "MIT（保留上游原许可证）",
  "awl_url": "https://www.wgtn.ac.nz/lals/resources/academicwordlist/awl-headwords/Headwords-of-the-Academic-Word-List.pdf",
  "awl_original_sha256": "66a54df3d2881921d42704d20e2524c36c2c454fcf3f816170eb06036cf6209b",
  "awl_attribution": "Averil Coxhead, Victoria University of Wellington, Academic Word List (2000)",
  "wordlists": {
    "top2000.txt": {
      "words": 2000,
      "method": "由 ECDICT 的正值 bnc 排名排序，取前 2000 个不同拼写；不是词族表。",
      "sha256": "3fe7df42aeddaed4f2e0566ffac45cd5d863ad47b3520c0b7a139746d824318e"
    },
    "top3000.txt": {
      "words": 3000,
      "method": "由 ECDICT 的正值 bnc 排名排序，取前 3000 个不同拼写；不是 Oxford 3000。",
      "sha256": "441fe01da7361872005ba069210418f08a75d115d3b747e619e23e319ffbcd6b"
    },
    "awl.txt": {
      "words": 570,
      "method": "Averil Coxhead AWL：570 个词族的 headwords；不是全部派生词。",
      "sha256": "393545190cb95e4d9fb01be6df30b856d4395d8cd121f213130b117b254ba0a7"
    },
    "cet4_cet6.txt": {
      "words": 5805,
      "method": "ECDICT tag 含 cet4 或 cet6 的不同拼写；不是官方最新考试大纲。",
      "sha256": "004e67bb0026fcd1633c5a3f0c3a95c2f84f3d7fbf85822c56fe760619ae0f15"
    }
  }
}
```

## exporter.py 签名

```python
def save_markdown(result: ConversionResult, destination: str | Path, *, markdown: str | None=None) -> Path: ...
def _atomic_write(target: Path, data: bytes) -> None: ...```

exporter.py 继续保存正文 Markdown 和图片；分析报告保存由 core/analysis/report.py 处理，预习保存由 core/study/render.py 处理。PDF 导出未实现。

## docs 内容索引

- `development_ports.md`：实现方式与后续接入端口

- `third_party_resources.md`：离线数据来源及许可

- `verification.md`：v0.1 历史验证

- `verification_v02.md`：v0.2 历史验证

- `verification_v03.md`：当前自动测试、真实材料验证和界面限制
