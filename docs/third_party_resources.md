# 随包英文资源来源

Python 依赖通过 requirements.txt 安装。离线资源从 NLTK 官方 nltk_data 仓库的固定地址下载，原始下载 SHA-256 和上游元数据保存在 resources/nltk_data/SOURCES.json。

| 资源 | 随包内容 | 来源/声明 |
| --- | --- | --- |
| punkt_tab | 仅 English 表及原 README | Jan Strunk，NLTK 官方 Punkt 模型；保留原 README 的作者、训练来源与文献 |
| stopwords | English 表及原 README | NLTK 官方停用词包；保留原 README 来源 |
| wordnet | 原 wordnet.zip | Princeton WordNet 3.0，许可证另存 WORDNET_LICENSE.txt，原包内同样保留 |
| averaged_perceptron_tagger_eng | 英文 JSON 模型 | 上游声明 MIT；保留 TAGGER_LICENSE.txt |
| nltk 代码许可 | 许可文本 | 保留 NLTK_LICENSE.txt；代码仍通过 pip 安装 |

未为上游未声明的资源补造许可证。英文分句及词性模型不包含用户上传的 PDF。

词缀规则是少量人工确认的学习提示，来源记录在 resources/affixes.json。分组按拼写处理，词缀解释仅使用明确例词，不自动给所有同前缀词套用含义。


## v0.3 学习资源

- ECDICT 上游：<https://github.com/skywind3000/ECDICT>，固定提交 `bc015ed2e24a7abef49fc6dbbb7fe32c1dadaf8b`。从该提交的 stardict.7z 解出完整 stardict.csv，生成项目词条版 ecdict.csv；保留原许可证 resources/dictionary/ECDICT_LICENSE.txt。仓库根部精简 ecdict.csv 缺少本轮核对词，因此没有将它直接作为完整词典使用。
- 派生口径：保留分析器可识别的单词、连字符词、撇号词和缩写；去除未统计标注的自动派生词；不包含短语条目。保留上游大小写条目顺序，查词时按小写匹配，规范化重复项以后者优先。
- 高频表依据同一完整数据的 bnc 字段排序，取前 2000/3000 个不同的有效拼写，不是词族版频率表，也不是 Oxford 3000。
- CET 表依据 tag 中 cet4/cet6 标签派生，共 5805 个词，不宣称对应当前官方考试大纲。
- AWL 来自 Averil Coxhead / Victoria University of Wellington 的官方 headwords PDF：<https://www.wgtn.ac.nz/lals/resources/academicwordlist/awl-headwords/Headwords-of-the-Academic-Word-List.pdf>。保留 570 个 headword 和来源记录，不把它标成 ECDICT 的 MIT 资源。
- 上游原文件和交付派生文件的 SHA-256、记录数、方法位于 resources/study_resources.json；重建工具为 tools/prepare_study_resources.py，需要已下载的完整上游 CSV、许可证及 AWL PDF。

验证 TED 材料时仅保存指标和词汇核对结果，未在交付文件中复制公开演讲全文或大段摘录。


## v0.4 新增素材与翻译

resources/exams/cet4_words.csv 与 cet6_words.csv 从已固定的 ECDICT 标签派生，保留 MIT 许可证；sources.json 记录来源、条数和哈希，不称为当前官方大纲。phrases.json 中的 70 条教学表达和中文学习释义由本项目整理，使用 CC0，未标官方考试级别；见 PHRASES_LICENSE.txt。

OPUS-MT：Helsinki-NLP/opus-mt-en-zh，官方模型卡标记 Apache-2.0。固定 revision：408d9bc410a388e1d9aef112a2daba955b945255，来源 https://huggingface.co/Helsinki-NLP/opus-mt-en-zh 。权重不随代码更新交付，首次显式下载时附官方 README；下载器按上游 Git blob / LFS SHA-256 验证。离线运行仅加载本地权重，不使用 trust_remote_code。

翻译依赖与基础依赖分开，实际验证 CPU torch 2.8.0、Transformers 4.57.6、sentencepiece 0.2.2、sacremoses 0.1.1、safetensors 0.8.0。日常模型推理与缓存不访问网络。
