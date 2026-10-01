"""AnalysisResult → Markdown/JSON；UI、命令行和未来预习单共用。"""

import json
import re
from dataclasses import asdict
from pathlib import Path

from ..models import AnalysisResult


def _literal(text: str) -> str:
    return re.sub(r"([\\`*_{}\[\]<>#|])", r"\\\1", text.replace("\n", " "))


def report_sections(result: AnalysisResult) -> dict[str, str]:
    stats = result.stats
    sections: dict[str, str] = {}
    sections["统计"] = (
        f"模式：{'词汇材料' if result.mode == 'vocabulary' else '通用文章'}\n\n{result.mode_reason}\n\n"
        f"总词数：{stats.total_words} · 句数：{stats.total_sentences} · 段数：{stats.total_paragraphs}\n\n"
        f"平均句长：{stats.avg_sentence_length:.1f} · 不同词数：{stats.unique_words} · TTR：{stats.type_token_ratio:.3f}\n\n"
        "统计对象为正文英文词（含停用词），连字符复合词和缩写各算一个词。TTR 受篇幅影响，不是难度等级。"
    )
    if result.warnings:
        sections["统计"] += "\n\n" + "\n".join(f"- {_literal(warning)}" for warning in dict.fromkeys(result.warnings))
    if result.mode == "vocabulary":
        progress = result.vocabulary_progress
        label = "目标词清单" if progress.source == "provided" else "候选词清单（未导入目标清单）"
        lines = [f"按字母顺序 · 共 {len(result.target_words)} 个 · 例句和搭配候选直接来自原文。"]
        for item in result.target_words:
            lines.extend(["", f"### {_literal(item.word)}", f"出现：{item.count} 次 · 段落：{', '.join(map(str, item.locations)) or '未出现'}"])
            lines.extend(f"- 例句：{_literal(sentence)}" for sentence in item.examples)
            if item.collocations:
                lines.append("- 原文搭配候选：" + " / ".join(_literal(span) for span in item.collocations))
        sections[label] = "\n".join(lines)
        sections["字母分组"] = "按单词开头字母分组；组名不代表每个词的真实词源前缀。\n\n" + "\n\n".join(
            f"### {group.prefix}（共 {group.word_count} 个，出现 {group.seen_count} 个）\n\n" + ", ".join(map(_literal, group.words))
            for group in result.prefix_groups
        )
        sections["词缀提示"] = "只显示人工核实的例词；不把所有同字母开头的词强行拆解。\n\n" + (
            "\n\n".join(f"- **{hint.affix}**：{hint.meaning}\n  例：{', '.join(hint.examples)}\n  来源：{hint.source}"
                         for hint in result.affix_hints) or "当前清单中暂无已核实例词。"
        )
        if progress.total_targets is None:
            body = f"未提供目标词清单。正文候选词：{progress.seen_targets} 个；目标总数及覆盖率未知。"
        else:
            body = f"目标词总数：{progress.total_targets} · 已出现：{progress.seen_targets} · 出现覆盖率：{progress.coverage:.1%}\n\n"
            body += "尚未出现：" + (", ".join(progress.missing_words) or "无")
        body += "\n\n此处记录材料对目标词的覆盖情况；学习者是否掌握这些词需要单独记录。"
        body += "\n\n" + "\n".join(f"- {group.prefix}：{group.seen_count}/{group.word_count} 个已出现" for group in result.prefix_groups)
        sections["目标覆盖"] = body
    sections["关键词"] = "基于句子 TF-IDF 的主题词候选。\n\n" + (
        "\n".join(f"{index}. {_literal(item.word)} · {item.count} 次 · 得分 {item.score:.4f} · 段落 {', '.join(map(str, item.locations))}"
                  for index, item in enumerate(result.keywords, 1)) or "当前阈值下没有关键词，可降低最低频次。"
    )
    sections["长句"] = "按词数筛选的长句，未进行从句或句法主干解析。\n\n" + (
        "\n\n".join(f"### 第 {item.paragraph_index} 段第 {item.sentence_index} 句 · {item.word_count} 词\n\n{_literal(item.text)}"
                      for item in result.long_sentences) or "没有超过阈值的句子。"
    )
    sections["段落线索"] = "首句作为阅读线索，可能不是段落主旨；主题词为本段高频内容词。\n\n" + (
        "\n\n".join(f"### 第 {item.index} 段 · {item.word_count} 词\n\n{_literal(item.first_sentence)}\n\n主题词：{', '.join(item.topic_words) or '无'}"
                      for item in result.paragraph_summaries) or "没有正文段落。"
    )
    sections["文章地图"] = (f"文章：{_literal(result.article_title or '未识别标题')}\n\n" +
        "\n".join(f"- {'  ' * max(0, item.level - 2)}{_literal(item.heading)} · 段落 {', '.join(map(str, item.paragraph_indices)) or '无正文'} · {item.word_count} 词"
                  for item in result.article_map))
    sections["词频"] = "去停用词后的词频；word 为统计形式，display 保留原文拼写。\n\n" + (
        "\n".join(f"- {_literal(item.word)}（原文 {_literal(item.display)}）：{item.count} 次 · 段落 {', '.join(map(str, item.locations))}"
                  for item in result.word_frequencies) or "没有符合过滤规则的内容词。"
    )
    return sections


def analysis_to_markdown(result: AnalysisResult) -> str:
    return "# English Preview 分析报告\n\n" + "\n\n".join(f"## {name}\n\n{body}" for name, body in report_sections(result).items()) + "\n"


def analysis_to_json(result: AnalysisResult) -> str:
    return json.dumps(asdict(result), ensure_ascii=False, indent=2) + "\n"


def save_analysis(result: AnalysisResult, destination: str | Path) -> Path:
    from ..exporter import _atomic_write
    path = Path(destination).expanduser().resolve()
    if path.suffix.lower() not in (".md", ".json"):
        raise ValueError("分析报告请保存为 .md 或 .json。")
    path.parent.mkdir(parents=True, exist_ok=True)
    body = analysis_to_json(result) if path.suffix.lower() == ".json" else analysis_to_markdown(result)
    _atomic_write(path, body.encode("utf-8"))
    return path
