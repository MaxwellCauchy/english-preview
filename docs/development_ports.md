# v0.2 项目报告与后续接口

本轮完成读取清洗修复、离线规则分析、通用文章/词汇材料模式判断、目标清单核对和桌面/命令行接入。分析与读取独立：PDF 先变成 Document，分析模块仅消费 Document，界面仅组装配置与展示结果。

## 如何实现

读取层按页保留坐标、字号和类型，清洗特殊空格、不可见字符和结尾噪声。图片保持独立节点，放在页末，不参与正文合并。满足严格几何及小写续接条件的单栏跨页段落会合并。

分析层统一分句和词边界，再用停用词与 POS 辅助词形还原生成统计词。文章模式提供 TF-IDF 关键词、词数长句、首句线索、全局统计和标题/段落地图。词汇模式在相同底层统计上增加目标匹配、字母分组、原文例句和搭配窗口、人工确认的词缀提示与清单覆盖率。

分析结果用类型化的数据结构返回；Markdown/JSON 由报告模块转换。界面工作线程只处理核心任务，进度与结果经队列交回 Tk 主线程，因此读取和分析不会直接在后台修改窗口。

## 后续从哪里接入

| 后续工作 | 入口 | 接收/返回约定 |
| --- | --- | --- |
| 新分析功能或双模式规则 | core/analyzer.py、core/analysis/ | analyze_document(Document, AnalysisConfig) → AnalysisResult；保持不修改输入 |
| 修改分句/复合词规则 | core/analysis/sentence.py | segment_sentences 与 word_tokens；会同时影响词数、频率和例句 |
| 新的目标词匹配方法 | core/analysis/vocabulary.py | validate_targets/load_target_words；匹配结果仍用 TargetWord |
| 扩展词缀提示 | resources/affixes.json | affix、meaning、明确例词列表、来源；不能用首字母推断词源 |
| 离线释义/翻译 | resources/dictionary/，再新增 core/analysis/dictionary.py | 按词形查词，明确来源；可给 TargetWord 新增有默认值的释义字段 |
| 学习者掌握进度 | 建议新增 core/progress_store.py 和独立数据文件 | 以清单词为主键保存状态/时间；与材料的 VocabularyProgress 覆盖率区分 |
| 大模型补强首句/长句解释 | core/llm_client.py | 读取 Document/AnalysisResult，返回有来源位置的附加解释；规则结果仍可独立使用 |
| 句法主干分析 | 新增 core/analysis/syntax.py | 消费 SentenceRecord；将句法结果单列，不改变 LongSentence 的词数含义 |
| 预习单 | templates/preview_template.html、style.css | 消费 AnalysisResult；报告模块已提供结构化 JSON 和纯文本 |
| PDF 导出 | core/exporter.py | 在现有保存入口之外新增 export_preview，不让 UI 处理排版逻辑 |
| 显示新分类 | ui/analysis_panel.py、core/analysis/report.py | report_sections 返回“分类名→报告文本”；Panel 按分类显示 |
| 其他客户端 | main.py 或新 CLI/API 层 | 直接调用读取与分析入口，core 无 tkinter 依赖 |

现有读取接口仍兼容 v0.1：extract_text_blocks、clean_blocks、build_structure、to_markdown、pdf_to_markdown、read_pdf、save_markdown。

不使用同时存在的 core/analyzer.py 与 core/analyzer/，以免 Python 导入冲突。实际子包为 core/analysis/。扩展模型字段应有默认值，以保留已有构造与调用方式。

## 本轮尚未落地的功能

自动中文释义、持久化掌握状态、OCR、句法主干、LLM 解释、HTML 预习单和 PDF 导出仍是后续功能。当前的“目标覆盖”表示原文是否出现目标词，不代表学生已经学会。


## v0.3：预习层接口

调用链为 `Document → core/analyzer.py → AnalysisResult → core/study/builder.py → StudyList`。没有修改 `core/models.py`、`core/analyzer.py` 或读取模块，StudyList 与 AnalysisResult 分别缓存。

| 模块 | 主要接口 | 用途 |
| --- | --- | --- |
| core/study/models.py | StudyConfig、StudyWord、SentenceBreakdown、RankedParagraph、OutlineBlock、ArticleOutline、StudyList | 新模型，全部字段带默认值 |
| dictionary.py | load_ecdict(Path) → dict[str, dict]；lookup(str) → dict 或 None；entry_fields(dict) → dict；is_loaded() → bool；clear_cache() | 离线词典和缓存 |
| wordlist.py | load_wordlist(Path)；load_top2000()；load_top3000()；load_awl()；load_cet() → frozenset[str]；is_basic_word(str, *, use_top2000=True)；is_stopword(str)；clear_cache() | 词表和过滤 |
| study_words.py | select_study_words(list[WordFrequency], StudyConfig) → list[StudyWord]；select_target_words(list[TargetWord], StudyConfig) → list[StudyWord] | 学习词筛选；目标词不受基础词过滤 |
| main_structure.py | extract_main_structure(LongSentence, StudyConfig) → SentenceBreakdown | 词性规则提示，失败回退 |
| paragraph_rank.py | rank_paragraphs(AnalysisResult, StudyConfig) → list[RankedParagraph] | 按词数加关键词命中排序 |
| outline.py | build_outline(AnalysisResult, StudyConfig) → ArticleOutline | 章节或段号位置分组 |
| builder.py | build_study_list(AnalysisResult, StudyConfig=None, *, progress_callback=None) → StudyList | 总入口；回调(done, 6, message)，可抛 StudyCancelled 取消 |
| render.py | study_list_to_markdown(StudyList) → str；study_list_to_html(StudyList) → str；save_study_list(StudyList, Path, fmt='md') → Path | 格式转换、原子保存 |
| ui/study_panel.py | StudyPanel(master, on_build, on_status=None)；config；set_state；show_study_list；clear；copy；save(fmt='md') | 组装配置和展示，不运行学习规则 |
| ui/main_window.py | build_study；_study_worker；_poll | 后台线程、缓存和取消 |

后续学习词打分只改 study_words.py；主干规则改 main_structure.py；模板优先使用 templates/preview_template.html 和 style.css，资源目录的 study_list.html 是同版备用模板。PDF 导出仍未实现，可以在 exporter.py 增加独立入口，消费 StudyList 和自包含 HTML。

LongSentence 只包含分析阶段已识别的长句。StudyConfig.min_sentence_words 可进一步过滤，不能恢复先前被分析阈值排除的句子。ParagraphSummary 不含完整段落，舞台说明判断只能利用已有首句和词数；不对混排正文的频次作猜测。段落主旨、精确句法、真实难度和掌握进度是后续功能，不能从这些规则输出推定。

完整模型、函数签名、文件树、UI 标签页、依赖及资源现状集中于 docs/project_handoff_v03.md。


## v0.4 扩展接口

- StudyConfig 增加 exam_level（general/cet4/cet6）、max_phrases、translate_sentences、translation_model_dir。
- build_study_list 增加 document 和 analysis_config 关键字参数，完整正文供词频、短语和选句使用；未传 document 时明确提示仅使用旧长句。
- exams.load_exam_words(level) 返回词典历史等级记录；load_phrases/select_phrases 提供短语素材和匹配结果。
- sentence_rank.select_sentences 从 PreparedSentence 中排序，保留原始段号、句号、页号及前文参考。
- translation.OpusTranslator 本地加载 MarianMT；translate 返回（译文，状态）。translate_study_sentences 填充译文并保存各句状态。
- UI 使用小型四六级素材；核心 general 配置继续保留 v0.3 规则。只添加字段，不改变 core/models.py 和 core/analyzer.py。
- 短语库可以继续扩充；不把多词词组和单词混入同一个频次字段。翻译服务可换实现，但状态、缓存隔离和无静默截断契约应保留。
