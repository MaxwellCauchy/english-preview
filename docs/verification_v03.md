# v0.3 验证记录

日期：2026-09-30。环境：Linux，Python 3.12.14，原项目依赖版本不变。Windows/macOS 未实机验证。

## 自动回归

`python -m unittest discover -s tests -v`：111 项通过。原 v0.2 60 项全部保留，新增预习与界面流程 51 项。涵盖模型默认值和校验、词典错误和路径缓存、字段提取、四种词表、基础词/缩合词/名字过滤、固定打分、输入不变、原句位置和否定保留、解析失败回退、舞台说明和短段排除、关键词段落排序、结构区间完整性、短文单块、两种模式、空文档、子步骤失败、取消、数量阈值、Markdown/HTML 转义、一次性模板替换、保存及失败不覆盖。

新增界面流程测试不需要显示器：配置校验、按钮状态、显示/清除、复制完整报告、取消保存、双格式保存、分析缓存复用、目标改变失效、工作线程提前取消、取消后的晚到结果不展示。测试源为 tests/test_study.py，构造资料复用 tests/fixtures.py。

## Why I’m building libraries inside prisons

来源是 TED 官方英文 transcript 页面：<https://www.ted.com/talks/reginald_dwayne_betts_why_i_m_building_libraries_inside_prisons/transcript>，读取该页面的数据段，按官方段落拼接 cue。它可能与老师整理的讲义分段不同。没有取得老师的此篇 PDF，不把此验证称为老师版 PDF 验证。

| 项目 | 实测 |
| --- | --- |
| 英文词 / 段落 / 句数 | 1626 / 21 / 136 |
| 自动模式 | article |
| 默认学习词 / 长句 / 关键段 / 结构块 | 15 / 5 / 8 / 5 |
| 导入五词清单 | 五词全部输出，全部取得释义 |
| 目标词频 | felony 2；paralegal 2；perpetual 1；crucible 1；penitentiary 1 |

默认 article 的规定分数不保证五个低频词进入前 15；它们没有被短词/基础词规则过滤掉，但排位靠后。附 examples/libraries_targets.txt 供指定阅读重点，在自动/词汇模式导入后保证纳入预习单。没有在算法中写死这五个单词，也没有改动规定打分或伪造默认排序。

交付仅含此篇指标 JSON，不包含演讲全文、大段原句或全文预习报告。

## Lexicon Quest

使用用户提供的 16 页 PDF。正文 8230 词、40 段；v0.2 读取与分析计数保持一致。导入原 9 词核对清单，预习输出 9 词，其中 8 个已出现词均取得释义，zzmissing 仍为 0 次且没有编造释义；输出 5 条长句提示、8 个关键段、5 个结构块、6 项行动任务。保留 above-mentioned、absent-minded 完整拼写。生成 Markdown 与自包含 HTML。

## 资源核对

从官方完整上游 3,402,564 条记录生成项目词条版，而非误用缺少常用词的精简文件。核对 prison、library、people、time 及五个指定目标词，全部查到。输出 CSV 1,146,124 条记录，1,146,124 个规范化拼写，82,871,515 字节。

top2000=2000，top3000=3000，AWL=570，CET=5805。CSV 不提交 git；许可证及来源、派生规则和校验值随包保存。资源生成过程使用标准库与既有 pdfplumber，应用运行没有联网步骤。

## 界面实测限制

本轮尝试启动 Xvfb，但当前环境不允许创建显示服务，扩展权限申请也被环境策略拒绝。未实际打开 v0.3 窗口点测，未声称取得新界面截图；无显示流程测试通过不等同于实机验证。此前 v0.2 的界面实测记录只属于 v0.2。

HTML 已验证六个内容部分、UTF-8、文本转义、样式内联及无外部依赖；没有取得浏览器截图。可打开交付的 study_sample.html 或 lexicon_study.html 人工核对布局。

## 交付核验

core/models.py、core/analyzer.py、requirements.txt 与 v0.2 基线字节一致。新增和替换文件保留相对路径；更新脚本、重复更新、冲突停止和备份恢复的核验结果另见交付的安装核验 JSON。
