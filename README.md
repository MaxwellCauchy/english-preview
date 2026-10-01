# English Preview v0.4

## v0.4：四六级预习与离线翻译

预习页每次可选择四级／六级，新增重点短语和重点句入选原因，采用 OPUS-MT 生成本地参考译文。选句消费完整正文，既包含复杂句，也包含有学习价值的短句。默认保留上次选择，生成前可切换。

已附 ECDICT 历史标签派生词表（四级 3849 条、六级 5407 条）和 70 条通用教学短语／句型。不是最新官方大纲、完整考试短语库或真题考频；专四、专八不在本轮范围内。四六级释义无需载入大词典，基础依赖不变。

翻译是可选功能，需首次安装 requirements-translation.txt 并下载模型，之后仅本地加载。更新不包含约 301 MiB 模型文件；下载工具会固定版本和核验文件。未准备翻译时，选词、短语、选句和导出仍可使用。

完整更新、安装和使用步骤见 [docs/v04_usage.md](docs/v04_usage.md)，文件树、模型和接口见 [docs/project_handoff_v04.md](docs/project_handoff_v04.md)，验证见 [docs/verification_v04.md](docs/verification_v04.md)。以下 v0.3/v0.2 内容保留为历史说明，以本节及 v0.4 文档为当前行为。

## v0.3：离线预习单（历史说明）

新增第三个标签页“预习单”。读取完成后可直接生成：尚未分析时自动分析；已有结果且分析配置未变时复用缓存。调整目标清单或分析选项后，会重新分析再生成。预习页可调整必学词数量、长句数量和关键段数量，选择项目查看完整文字，复制整份清单，或保存 Markdown、自包含 HTML。

结构保持分层：`Document → AnalysisResult → StudyList`。读取和分析代码保持兼容；新数据结构位于 `core/study/models.py`。本轮没有新增 pip 依赖，不使用大模型或 spaCy。

### 合并到已有 v0.2

本轮文件仍按 `01_新增文件`、`02_替换文件`、`03_测试结果` 分类，前两个目录保留项目相对路径。关闭程序后，按同名相对路径合并前两个目录，或在交付目录运行：

```sh
python apply_update.py "原项目/english-preview"
```

更新脚本先核验和备份，再复制；自行修改过的文件会列出冲突，不静默覆盖。测试结果目录用于核对，不复制到项目中。依赖与 v0.2 相同，仍使用原虚拟环境启动 `main.py`。

### 学习词和指定重点词

文章模式过滤基础词、停用词、短词、数字、可辨识的专有名字和仅出现在完整舞台说明中的词，然后按 `count * (1 + collins_star)` 排序；Oxford 标记乘 1.5。词汇模式沿用目标词，不过滤你明确导入的基础词，两种模式都遵守词数上限。

这套分数衡量频次和词典标记，不等于难度判断，不能保证任何低频词都进入默认前 15。针对 Why I’m building libraries inside prisons，附有 `examples/libraries_targets.txt`：在分析页保持“自动识别”或选择“词汇材料”，导入清单后生成，五个指定词都会保留。手动“通用文章”仍走文章筛选。

主干和从句类型是规则候选，需对照原句核对；无标题文章的“引入、发展、核心、转折/高潮、总结”按位置分组，不代表自动理解内容。首句线索不等于摘要。界面行动清单只读，HTML 中的勾选也不会写回持久化进度。

### 数据仓库

`resources/dictionary/ecdict.csv` 已附，实际 82,871,515 字节（约 79.0 MiB）。它从官方完整 stardict 数据派生为项目词条版，含 1,146,124 条 CSV 记录、1,146,124 个规范化拼写；保留单词、连字符词、撇号词和缩写，省略短语及未标注的自动词形。原字段和上游大小写条目顺序保留。词典首次使用时在后台加载，之后复用缓存；不应把此文件提交 git。

四份词表已提供：BNC 排名派生 2000/3000 个不同拼写、AWL 570 个 headword、ECDICT CET4/CET6 标签词 5805 个。top3000 不是 Oxford 3000，CET 表不是最新官方考试大纲；AWL/CET 加载入口已就绪，本版不额外将它们加入打分。来源、派生口径及 SHA-256 见 `resources/study_resources.json`。

词典缺失时保留候选词、释义留空并显示提示；词表缺失时降级过滤。替换资源后重启程序，或在代码中调用缓存清理接口。资源已随交付文件提供，日常使用无需联网。

### 预习层验证

```sh
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
python tools/check_study.py --pdf "你的文章.pdf" --output output/study_check
```

本轮 111 项自动测试通过。源码及接口全文见 `docs/project_handoff_v03.md`，验证记录见 `docs/verification_v03.md`。当前环境不能启动显示服务，新增窗口的真实点击和跨平台视觉效果尚未验证；界面状态、缓存、复制、保存、取消已做无显示流程测试。

把文字型 PDF 整理为 Markdown，再独立分析正文。v0.2 支持通用文章和词汇材料两种模式，使用离线 NLTK 规则，不接大模型。

## v0.1 → v0.2 历史升级说明

本轮增量包分为 `01_新增文件`、`02_替换文件`、`03_测试结果`。前两个目录内部均保留项目相对路径。

先关闭正在运行的程序。推荐在解压后的增量包目录运行：

```sh
python apply_update.py "原项目/english-preview"
```

脚本会核验文件、备份需要覆盖的旧文件，再复制更新。原文件若已自行修改，默认停止并列出冲突；可根据包内说明手动合并。`03_测试结果`用于查看，不需要复制进项目。

升级后重新安装依赖：

```bat
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe main.py
```

macOS/Linux：

```sh
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python main.py
```

首次建立环境时先运行 `python -m venv .venv`。项目需要 Python 3.10+；正常依赖为 pdfplumber、tkinterdnd2、nltk。tkinter 使用带 Tcl/Tk 的 Python 安装；Linux 可能需要系统的 python3-tk。

安装 Python 依赖需要网络；分析模型已放在 `resources/nltk_data/`，使用时无需下载数据。该目录必须整体保留。

## 窗口操作

1. 拖入一份 PDF，或通过按钮选择文件，点击“开始读取”。
2. 在 Markdown 标签页核对、编辑、复制或保存正文。图片会另存到 Markdown 旁的资源目录。
3. 打开“分析”标签页，选择自动识别、通用文章或词汇材料。
4. 按需导入目标词 TXT/CSV，调整长句阈值、关键词最低频次，点击“分析正文”。
5. 在左侧选择统计、目标词、字母分组、词缀提示、目标覆盖、关键词、长句、段落线索、文章地图或词频。可复制整份报告，或保存为 Markdown/JSON。

读取和分析都在工作线程执行，支持取消。分析使用读取所得的 `Document`；Markdown 编辑区的改动不会回写 Document。调整分析选项或词清单后，点击重新分析才会更新结果。

自动模式：导入清单、标题含 Lexicon Quest/词汇等标记时采用词汇模式；大量不同内容词集中于同一首字母也会提示为词汇材料。其他材料采用文章模式。规则判断可被手动选择覆盖。

## 目标词清单及统计口径

TXT：UTF-8，每行一个英文词，支持连字符；以 `#` 开头的行作注释。

```text
abandon
abandonment
above-mentioned
absent-minded
```

CSV：UTF-8，第一列是目标词，可有 `word` 表头。其他列暂不用于词义生成。重复项和大小写差异去重。

```csv
word,meaning
abandon,放弃
abandonment,放弃行为
```

- 导入清单后显示全部目标词，按字母排序，包括未出现的词；覆盖率是已出现词数/清单词数。
- 没有清单时显示正文候选词，不推断目标总数，也不显示虚构的“312/312”。
- 默认按词性辅助还原时态、单复数等变化；abandon 和 abandonment 保持独立。若清单同时包含原形与变化形式，精确拼写优先，一处出现只计一次。
- 候选词会过滤停用词和短词；明确导入的目标词不受此过滤影响，例如 ad、about 仍可核对。
- 例句是原文完整句子；“原文搭配候选”是原文的连续词窗口，不是自动生成的搭配词典。
- `ab-`、`ac-` 等字母分组只是拼写分组；真正的词缀提示使用人工确认的例词，不能将 abroad 等词强行解释为 ab-。
- “目标覆盖”记录材料有没有包含某个词；学习者的掌握状态尚未存储。
- 分析报告仍不生成自动中文释义；v0.3 预习层查询随包 ECDICT，未命中时留空。

`examples/lexicon_check_targets.txt` 是 9 词核对示例（含一个故意未出现的词），不是正式 312 词清单。

## 命令行

```sh
python main.py article.pdf -o output/article.md
python main.py article.pdf --analyze
python main.py article.pdf --analyze --mode article --max-sentence-words 25 --min-frequency 2
python main.py lexicon.pdf --targets examples/lexicon_check_targets.txt --analysis-output output/lexicon_analysis.json
python main.py article.pdf --columns double --no-images
python main.py protected.pdf --ask-password
```

`--analyze`、`--targets` 或 `--analysis-output` 都会启用分析。默认报告保存到正文旁的 `<正文名>_analysis.md`，可指定 `.json` 导出结构化数据。分析失败时已保存的正文仍可使用。

`--include-lists` 把列表项视为独立正文单元。默认只分析段落，标题、表格、图片说明均不计入词数。GUI 的“计入列表”采用相同规则。

## 当前布局

| 路径 | 职责 |
| --- | --- |
| main.py | 桌面启动和命令行读取/分析 |
| core/models.py | Document、ConversionResult 和 AnalysisConfig/AnalysisResult 等模型 |
| core/pdf_reader.py | PDF 抽取、清洗、结构识别和读取总接口 |
| core/layout.py | 分栏排序、空格、断行和连字符规则 |
| core/markdown_builder.py | 有序文档节点转 Markdown |
| core/exporter.py | 原有正文与图片保存、原子写入 |
| core/analyzer.py | 稳定分析入口；不能改为同名 analyzer/ 文件夹 |
| core/analysis/ | sentence、frequency、keywords、long_sentences、paragraph、stats、vocabulary、report、runtime 子模块 |
| ui/main_window.py | 主窗口、工作线程、队列、读取与分析调度 |
| ui/analysis_panel.py | 分析选项及分类结果显示 |
| ui/widgets.py | 拖拽区、Markdown 编辑区 |
| resources/nltk_data/ | 随包英文模型、来源信息和许可证 |
| resources/affixes.json | 可扩展的人工确认词缀提示 |
| examples/ | 自制文章和小范围核对词清单 |
| tools/check_lexicon.py | 对用户持有的真实 PDF 重跑读取与分析核对 |
| tests/ | 读取、规则分析、词汇覆盖和 CLI 回归测试 |
| docs/ | 验证记录及后续开发接口说明 |
| core/study/ | AnalysisResult 到 StudyList 的预习逻辑 |
| ui/study_panel.py | 第三个预习单标签页 |
| resources/dictionary/、resources/wordlists/ | 已提供的离线词典与词表 |
| templates/ | 自包含预习单 HTML 与样式 |
| core/llm_client.py | 后续模型调用预留入口，当前未使用 |
| output/ | 正文、报告和读取工作目录 |

## 稳定编程接口

```python
from core.pdf_reader import read_pdf
from core.analyzer import analyze_document, load_target_words
from core.models import AnalysisConfig
from core.analysis.report import save_analysis

conversion = read_pdf("lexicon.pdf")
analysis = analyze_document(
    conversion.document,
    AnalysisConfig(target_words=load_target_words("targets.txt")),
)
save_analysis(analysis, "output/report.md")
```

`read_pdf()` 只负责读取，返回结构化 Document 和 Markdown。`analyze_document(document, config=None, *, progress_callback=None, cancel_event=None)` 返回 AnalysisResult，不修改输入。

`core.analyzer` 还导出：segment_sentences、analyze_word_frequency、extract_keywords、detect_long_sentences、summarize_paragraphs、compute_stats、load_target_words。报告转换在 `core.analysis.report`：analysis_to_markdown、analysis_to_json、save_analysis。

传词频/关键词接口时可传 `list[str]`；每个字符串默认视为独立段。需要准确位置时传 `SentenceRecord(text, paragraph_index, sentence_index, page_number)`。段号、句号、页号都从 1 开始；长句句号是段内编号。

## 规则和边界

读取修复：连续空白规范化；本样本中表示空格的 U+0001 转空格；零宽和其他不可见控制字符清除；文档末尾单独的 `&` 去掉，内部的 R&D/A & B 保留。图片从正文排序中移出，放到所在页正文之后。单栏中，页底未结束且下一页以小写续接的正文可合并；其他跨页情况保持保守。

句子用英文 Punkt 模型加缩写表切分，保留 A.M./A.D./B.C./Dr./e.g./i.e./etc. 和小数点，分号不是边界。有效单词句 Yes. 默认保留，以保持句数与长句统计一致；需要原规格的“两词以上”过滤时调用 `segment_sentences(text, min_words=2)`。

分词使用 NLTK RegexpTokenizer：撇号词、缩写、连字符复合词各算一个词；纯数字不计为英文词。词频用 NLTK 停用词表，加 said/also/would，使用 POS 辅助的 WordNetLemmatizer。词频不受关键词最低频次限制。

TF-IDF 按句计算：`TF = 本句该词数/本句过滤后词数`；`IDF = log((1+句数)/(1+含词句数))+1`；全文得分是各句 TF×IDF 的均值。按最低频次过滤后取前 15 个。它是文内主题词候选排序，不是跨教材训练的语义重要度。

长句严格按词数大于阈值标记，不等同于句法困难。段落线索保留首句和本段前三个高频内容词，不声称首句必然是主旨。总词数/TTR 使用未去停用词、未还原的正文词，TTR 受长度影响，不做难度认证。

无 OCR、完整句法解析或大模型解释；预习层仅提供主干规则候选。三栏、复杂表格、公式、脚注和特殊跨页排版仍需人工核对。

## 验证

```sh
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
python tools/check_lexicon.py "词汇探秘之旅-原文7601200994240873450.pdf"
```

v0.2 历史验证为 60 项测试以及读取、分析 GUI 流程；v0.3 当前为 111 项测试，新增预习单窗口未实机点击验证。真实 16 页 Lexicon Quest 已跑通。详细口径及复现步骤见 `docs/verification_v02.md`，开发端口见 `docs/development_ports.md`。Windows/macOS 未在本环境实机验证。
