# English Preview v0.4 项目交接

## 完整源码文件树

以下为源码及既有离线资源；output 和首次下载生成的模型单独说明。

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
      - `exams.py`
      - `main_structure.py`
      - `models.py`
      - `outline.py`
      - `paragraph_rank.py`
      - `phrases.py`
      - `render.py`
      - `sentence_rank.py`
      - `study_words.py`
      - `translation.py`
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
    - `project_handoff_v04.md`
    - `third_party_resources.md`
    - `v04_usage.md`
    - `verification.md`
    - `verification_v02.md`
    - `verification_v03.md`
    - `verification_v04.md`
  - `examples/`
    - `article.txt`
    - `exam_study_article.txt`
    - `lexicon_check_targets.txt`
    - `libraries_targets.txt`
  - `resources/`
    - `dictionary/`
      - `.gitkeep`
      - `ECDICT_LICENSE.txt`
      - `ecdict.csv`
    - `exams/`
      - `PHRASES_LICENSE.txt`
      - `cet4_words.csv`
      - `cet6_words.csv`
      - `phrases.json`
      - `sources.json`
    - `icons/`
      - `.gitkeep`
    - `models/opus-mt-en-zh/`：首次下载生成，不随更新交付。
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
    - `test_study_v04.py`
  - `tools/`
    - `check_lexicon.py`
    - `check_study.py`
    - `check_translation.py`
    - `download_translation_model.py`
    - `prepare_exam_resources.py`
    - `prepare_study_resources.py`
  - `ui/`
    - `__init__.py`
    - `analysis_panel.py`
    - `main_window.py`
    - `study_panel.py`
    - `study_preferences.py`
    - `widgets.py`
  - `.gitignore`
  - `README.md`
  - `main.py`
  - `requirements-dev.txt`
  - `requirements-translation.txt`
  - `requirements.txt`
  - `run_windows.bat`
  - `output/`：运行结果、译文缓存及用户偏好，不提交 git。

## 层次与布局

`Document → AnalysisResult → StudyList`。PDF 读取与分析接口不变；考试素材、短语和选句在 core/study，界面调度在 ui/main_window.py，展示在 ui/study_panel.py。OPUS-MT 依赖与基础依赖分开，按需本地加载。

默认 UI 四级；每次可选四级／六级，记住上次选项。核心 StudyConfig 的 general 默认值保留 v0.3 编程调用行为。

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
```

## 分析函数签名

### core/analyzer.py

```python
def analyze_document(document: Document, config: AnalysisConfig | None=None, *, progress_callback: Callable[[int, int, str], None] | None=None, cancel_event: Event | None=None) -> AnalysisResult: ...
```

### core/analysis/frequency.py

```python
def check_cancel(cancel_event: Event | None) -> None: ...
def prepare(sentences: SentenceInput, config: AnalysisConfig, cancel_event: Event | None=None) -> list[PreparedSentence]: ...
def frequencies(prepared: list[PreparedSentence]) -> list[WordFrequency]: ...
def analyze_word_frequency(sentences: SentenceInput, config: AnalysisConfig | None=None) -> list[WordFrequency]: ...
```

### core/analysis/keywords.py

```python
def keywords(prepared: list[PreparedSentence], config: AnalysisConfig) -> list[Keyword]: ...
def extract_keywords(sentences: SentenceInput, config: AnalysisConfig | None=None) -> list[Keyword]: ...
```

### core/analysis/long_sentences.py

```python
def long_sentences(records: list[SentenceRecord], config: AnalysisConfig) -> list[LongSentence]: ...
def detect_long_sentences(document: Document, config: AnalysisConfig | None=None) -> list[LongSentence]: ...
```

### core/analysis/paragraph.py

```python
def summaries(document: Document, prepared: list[PreparedSentence], config: AnalysisConfig) -> list[ParagraphSummary]: ...
def summarize_paragraphs(document: Document, config: AnalysisConfig | None=None) -> list[ParagraphSummary]: ...
def article_map(document: Document, config: AnalysisConfig) -> list[SectionOverview]: ...
```

### core/analysis/report.py

```python
def report_sections(result: AnalysisResult) -> dict[str, str]: ...
def analysis_to_markdown(result: AnalysisResult) -> str: ...
def analysis_to_json(result: AnalysisResult) -> str: ...
def save_analysis(result: AnalysisResult, destination: str | Path) -> Path: ...
```

### core/analysis/runtime.py

```python
def sentence_tokenizer() -> PunktTokenizer: ...
def stop_words() -> frozenset[str]: ...
def pos_tagger() -> PerceptronTagger: ...
def lemmatizer() -> WordNetLemmatizer: ...
def resource_error(exc: LookupError) -> AnalysisError: ...
```

### core/analysis/sentence.py

```python
def word_tokens(text: str) -> list[str]: ...
def segment_sentences(text: str, *, min_words: int=1) -> list[str]: ...
def text_units(document: Document, config: AnalysisConfig) -> list[tuple[int, int, int, str]]: ...
def document_sentences(document: Document, config: AnalysisConfig) -> list[SentenceRecord]: ...
def as_records(sentences: SentenceInput) -> list[SentenceRecord]: ...
```

### core/analysis/stats.py

```python
def compute_stats(document: Document, sentences: SentenceInput, config: AnalysisConfig | None=None) -> AnalysisStats: ...
```

### core/analysis/vocabulary.py

```python
def validate_targets(words: list[str]) -> list[str]: ...
def load_target_words(path: str | Path) -> list[str]: ...
def choose_mode(document: Document, prepared: list[PreparedSentence], config: AnalysisConfig) -> tuple[str, str]: ...
def vocabulary(prepared: list[PreparedSentence], config: AnalysisConfig) -> tuple[list[TargetWord], list[PrefixGroup], list[AffixHint], VocabularyProgress, list[str]]: ...
```

## 预习层及工具函数签名

### core/study/builder.py

```python
def build_study_list(result: AnalysisResult, config: StudyConfig | None=None, *, progress_callback: Callable[[int, int, str], None] | None=None, document: Document | None=None, analysis_config: AnalysisConfig | None=None) -> StudyList: ...
```

### core/study/dictionary.py

```python
def load_ecdict(path: Path) -> dict[str, dict]: ...
def lookup(word: str) -> dict | None: ...
def entry_fields(entry: dict) -> dict: ...
def is_loaded() -> bool: ...
def clear_cache() -> None: ...
```

### core/study/exams.py

```python
def load_exam_words(level: str) -> dict[str, dict]: ...
def clear_cache() -> None: ...
```

### core/study/main_structure.py

```python
def extract_main_structure(sentence: LongSentence, config: StudyConfig) -> SentenceBreakdown: ...
```

### core/study/outline.py

```python
def build_outline(result: AnalysisResult, config: StudyConfig) -> ArticleOutline: ...
```

### core/study/paragraph_rank.py

```python
def rank_paragraphs(result: AnalysisResult, config: StudyConfig) -> list[RankedParagraph]: ...
```

### core/study/phrases.py

```python
def load_phrases() -> tuple[dict, ...]: ...
def match_phrases(sentence: PreparedSentence, entries: tuple[dict, ...], level: str) -> list[PhraseMatch]: ...
def select_phrases(prepared: list[PreparedSentence], config: StudyConfig) -> list[StudyPhrase]: ...
```

### core/study/render.py

```python
def study_list_to_markdown(study: StudyList) -> str: ...
def study_list_to_html(study: StudyList) -> str: ...
def save_study_list(study: StudyList, destination: Path, fmt: str='md') -> Path: ...
```

### core/study/sentence_rank.py

```python
def select_sentences(prepared: list[PreparedSentence], words: list[StudyWord], phrases: list[StudyPhrase], config: StudyConfig, keywords: set[str] | None=None) -> list[SentenceBreakdown]: ...
```

### core/study/study_words.py

```python
def select_study_words(frequencies: list[WordFrequency], config: StudyConfig, *, keywords: set[str] | None=None) -> list[StudyWord]: ...
def select_target_words(targets: list[TargetWord], config: StudyConfig) -> list[StudyWord]: ...
```

### core/study/translation.py

```python
def model_fingerprint(folder: Path) -> str: ...
def OpusTranslator.__init__(self, model_dir: Path=DEFAULT_MODEL_DIR, cache_path: Path=DEFAULT_CACHE): ...
def OpusTranslator.translate(self, text: str) -> tuple[str, str]: ...
def get_translator(model_dir: Path) -> OpusTranslator: ...
def translate_study_sentences(study: StudyList, config: StudyConfig, *, progress_callback: Callable[[int, int, str], None] | None=None, translator=None) -> None: ...
```

### core/study/wordlist.py

```python
def load_wordlist(path: Path) -> frozenset[str]: ...
def load_top2000() -> frozenset[str]: ...
def load_top3000() -> frozenset[str]: ...
def load_awl() -> frozenset[str]: ...
def load_cet() -> frozenset[str]: ...
def is_basic_word(word: str, *, use_top2000: bool=True) -> bool: ...
def is_stopword(word: str) -> bool: ...
def clear_cache() -> None: ...
```

### tools/check_translation.py

```python
def main(): ...
```

### tools/download_translation_model.py

```python
def fetch(url): ...
def verify(path, item): ...
def download(destination): ...
def main(): ...
```

### tools/prepare_exam_resources.py

```python
def prepare(dictionary: Path, destination: Path) -> dict: ...
def main(): ...
```

### ui/study_preferences.py

```python
def load_preferences(path: Path=DEFAULT_PATH) -> dict: ...
def save_preferences(value: dict, path: Path=DEFAULT_PATH) -> None: ...
```

## UI 标签页与生成流程

- Markdown：读取结果、保存正文。
- 分析：原词频、目标清单、长句及结构统计。
- 预习单：四级／六级选择、词句段短语数量、离线译文开关、模型目录和安装说明；单词、短语、句子详情、关键段、大纲、行动清单、复制和导出。

主窗口复用有效分析缓存，始终传完整 Document 和当前 AnalysisConfig 给预习层；配置变化重新生成。工作线程只调用核心函数，主线程更新控件。取消在步骤／当前句推理边界生效。

## requirements.txt 全文

```text
pdfplumber==0.11.8
tkinterdnd2==0.6.3
nltk==3.10.3
```

## requirements-dev.txt 全文

```text
-r requirements.txt
reportlab>=4.2,<5
Pillow>=10.1,<13
```

## requirements-translation.txt 全文

```text
# 可选翻译依赖；以下版本已实际完成 CPU 离线推理验证。
# 先安装 CPU torch：py -m pip install torch==2.8.0 --index-url https://download.pytorch.org/whl/cpu
torch==2.8.0
transformers==4.57.6
sentencepiece==0.2.2
sacremoses==0.1.1
safetensors==0.8.0
```

## resources 现状

ECDICT、NLTK 和既有四份词表沿用 v0.3，不重新交付大文件。新增 exams 下的两份带释义 CSV、70 条短语、来源元数据与许可证。models 下的 OPUS-MT 由首次下载工具生成。

```json
{
  "version": "0.4",
  "dictionary_source": "https://github.com/skywind3000/ECDICT",
  "commit": "bc015ed2e24a7abef49fc6dbbb7fe32c1dadaf8b",
  "license": "MIT; 原许可证保留在 resources/dictionary/ECDICT_LICENSE.txt",
  "wordlists": {
    "cet4": {
      "records": 3849,
      "sha256": "290437e79363a1be3c0c71c0470692111560bf1e165c488e5f6e1488eca4b1a5",
      "meaning": "词典历史考试标签，不是最新官方大纲，未使用或声称真题考频"
    },
    "cet6": {
      "records": 5407,
      "sha256": "9cad082635426593ca204c5cc5dbbadab39d237e4a029863af89820c753d5cac",
      "meaning": "词典历史考试标签，不是最新官方大纲，未使用或声称真题考频"
    }
  },
  "phrases": {
    "source": "项目作者整理的通用学习短语，释义为本项目编写；不含官方考试等级或考频标注",
    "applicability": "四级和六级均可使用，属于教学适用范围，不代表考试归属",
    "records": 70,
    "license": "CC0-1.0；见 PHRASES_LICENSE.txt",
    "sha256": "01b7ffe3e9fb63515f4c70fa37e2168134fdecd31077974c375da86cb64d2ca0"
  }
}
```

## exporter.py 签名

```python
def save_markdown(result: ConversionResult, destination: str | Path, *, markdown: str | None=None) -> Path: ...
```

```python
def _atomic_write(target: Path, data: bytes) -> None: ...
```

exporter.py 的 PDF 导出仍为后续入口，本版未实现；预习导出使用 core/study/render.py 的 Markdown 和 HTML 接口。

## docs 内容索引

- `development_ports.md`：各版本扩展接口与兼容边界。
- `project_handoff_v03.md`：既有版本说明，保留历史记录。
- `project_handoff_v04.md`：本文件：完整树、模型全文、接口、UI、资源与依赖。
- `third_party_resources.md`：资源来源、许可证与固定模型版本。
- `v04_usage.md`：更新、首次模型准备、界面操作、规则、状态和缓存。
- `verification.md`：既有版本说明，保留历史记录。
- `verification_v02.md`：既有版本说明，保留历史记录。
- `verification_v03.md`：既有版本说明，保留历史记录。
- `verification_v04.md`：143 项测试、真实推理、两份材料与未验证范围。
