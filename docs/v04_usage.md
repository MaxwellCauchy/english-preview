# v0.4：四六级重点词、短语与 OPUS-MT 离线译文

## 更新和启动

本轮只更新 v0.3 的预习层及相关界面、模板；原读取与分析模型保持不变。
交付仍分为 `01_新增文件`、`02_替换文件`、`03_测试结果`，无需 ZIP。
下载并运行 `生成v0.4分类文件.py` 后，在终端执行（路径按自己的实际情况调整）：

```bat
py "C:\Users\35514\Desktop\V4\english-preview-v0.4-update\apply_update.py" "C:\Users\35514\Desktop\Version\english-preview" --dry-run
py "C:\Users\35514\Desktop\V4\english-preview-v0.4-update\apply_update.py" "C:\Users\35514\Desktop\Version\english-preview"
```

更新器以交付的 v0.3 为基线，先校验全部文件和冲突，再备份和更新；不会静默覆盖自行修改的文件。提示冲突时先核对差异，不要盲目使用强制覆盖参数。原有 ecdict.csv、NLTK 数据和 PDF 不必重下。完成后仍用原来的环境启动 main.py。

## 第一次准备翻译

基础依赖 requirements.txt 不变。只有需要离线译文时才安装额外依赖。关闭程序，在原项目目录、使用原来的 Python 环境运行：

```bat
py -m pip install torch==2.8.0 --index-url https://download.pytorch.org/whl/cpu
py -m pip install -r requirements-translation.txt
py tools/download_translation_model.py
py tools/check_translation.py
```

如果原程序通过虚拟环境运行，上述 `py` 应换成该环境的 Python，例如 `.venv\Scripts\python.exe`；不能把依赖装在一个环境、用另一个环境启动程序。实际验证环境为 Python 3.12。首次安装需要联网；权重约 298 MiB，随同分词文件约 301 MiB，不包含在更新文件中。下载工具固定官方版本并核验 Git blob／LFS SHA-256；已核验文件会跳过，可重新运行失败的下载。

默认模型目录为 `resources/models/opus-mt-en-zh/`。程序中可以选择另一份完整本地模型目录。日常生成预习单不会下载文件或调用在线翻译 API。

若访问 Hugging Face 失败，可在浏览器访问固定版本：
https://huggingface.co/Helsinki-NLP/opus-mt-en-zh/tree/408d9bc410a388e1d9aef112a2daba955b945255

需要 config.json、generation_config.json、tokenizer_config.json、source.spm、target.spm、vocab.json、pytorch_model.bin；将它们放入同一模型目录。注意保存真实文件，不是网页 HTML。模型许可证以官方 README.md 的 Apache-2.0 标记为准，不修改上游权重。

## 在界面使用

1. 选择 PDF，完成读取。
2. 打开“预习单”，选择四级或六级；设置词、句、段、短语数量。
3. 根据需要勾选离线参考译文，点击“生成预习单”。没有有效分析缓存时会自动分析。
4. 点击单词看释义和入选原因，点击短语看原文形式、例句和位置，点击句子看原文、译文、前文参考、主干及入选原因。
5. 复制完整 Markdown，或保存 Markdown／自包含 HTML。

考试目标、模型目录和翻译开关会保存在 output/study_preferences.json，作为下次默认值；每次生成前仍可切换。配置变化不会篡改已导出的报告，需重新生成。生成时冻结配置，取消会在步骤或当前句推理完成后生效；不能强行中断已开始的模型推理。

## 素材与规则

- 四级表 3849 条、六级表 5407 条来自固定版本 ECDICT 的历史标签。两表有重叠；六级模式匹配六级标签，未简单把全部四级词附加为六级词。不是最新官方大纲或真题考频。
- 70 条短语／句型是本项目整理的基础教学素材，释义自编、CC0；没有官方等级归属，不冒充完整四六级短语大纲。来源与 SHA-256 在 resources/exams/sources.json。
- 完整正文重新做词形还原及词频统计，不因旧报告频次门槛漏掉一次出现的词；图片、表格、标题仍不作正文。列表是否包含沿用分析页配置。
- 文章选词优先等级匹配，过滤基础词、停用词及可辨识专有名词；再按低常用度线索、反复出现和文章关键词排序。词典星级越高不再直接当作难度加分，无星级也不代表官方难词。匹配不足时补充文章词，并标明“未标考试等级／另一等级词汇”。
- 词汇材料模式保留明确目标词，不按基础词过滤，仍遵守输出数量上限。
- 四六级释义使用随包小型分级 CSV，无需先载入百万条大词典。补充词只有命中分级词库或已有词典缓存才有释义，否则留空。
- 短语支持词形变化、最长重叠优先、部分模板中的 1–6 词插入成分；不跨标点。相邻搭配会漏检，离散短语匹配也可能误检，需核对原句。
- 从全部正文句子选句，结合重点词、短语、从句／分词／连接词线索、文章关键词、长度及跨段覆盖。不会保证不同等级总选出不同句子：同一文章的重要句可能重合。
- 主干和结构说明为规则候选，不是完整句法解析；没有熟词生义识别或官方难度判定。

## 翻译状态与缓存

译文为 OPUS-MT 逐句参考译文，不是标准答案。否定、指代、专业词、习惯表达和标点均需核对。前一句只供界面阅读，未加入模型输入，避免把上下文译文冒充原句译文。

`translated`：本次推理；`cached`：命中本地缓存；`unavailable`：模型或依赖未准备；`too_long`：原句或译文超过长度限制，未截断保存；`failed`：该句推理失败；`not_requested`：未启用翻译。

模型和依赖缺失时其他学习内容照常生成。重新生成可重试失败句。缓存位于 output/translation_cache.sqlite3，按模型内容、生成设置和原句区分，包含译文内容；删除该文件即可清空。无需联网即可命中缓存和重新推理。

## 复现检查

```bat
py -m unittest discover -s tests -v
py tools/check_study.py --pdf "你的PDF.pdf" --exam cet4 --translate
py tools/check_study.py --article examples/exam_study_article.txt --exam cet6 --translate
```

测试依赖沿用 requirements-dev.txt。Windows/macOS 桌面视觉和点击尚未在本环境实机验证；详见 docs/verification_v04.md。
