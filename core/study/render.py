"""预习清单的 Markdown/自包含 HTML 渲染与原子保存。"""

import html
import os
import re
import tempfile
from pathlib import Path

from .models import StudyList

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_PATH = PROJECT_ROOT / "templates" / "preview_template.html"
STYLE_PATH = PROJECT_ROOT / "templates" / "style.css"
FALLBACK_TEMPLATE_PATH = PROJECT_ROOT / "resources" / "study_templates" / "study_list.html"


def _md(text: str) -> str:
    value = " ".join(str(text).split())
    return re.sub(r"([\\`*_{}\[\]<>|#])", r"\\\1", value)


def study_list_to_markdown(study: StudyList) -> str:
    """输出六个预习部分；所有内容按文本转义，空项明确标明。"""
    parts = [f"# 预习清单：{_md(study.title or '未命名文章')}", "## 文章速览",
             _md(study.overview) or "暂无正文。", "## 必学词"]
    if study.study_words:
        rows = ["| 词 | 词性 | 释义 | 次数 | 段落 |", "| --- | --- | --- | ---: | --- |"]
        for word in study.study_words:
            meaning = word.meaning_cn or word.meaning_en or "暂无释义"
            rows.append(f"| {_md(word.display or word.word)} | {_md(word.pos)} | {_md(meaning)} | {word.count} | "
                        + ", ".join(map(str, word.locations)) + " |")
        parts.append("\n".join(rows))
        for word in study.study_words:
            if word.selection_reasons:
                parts.append(f"{_md(word.word)} · 入选原因：" + "；".join(_md(v) for v in word.selection_reasons))
            if word.collocations:
                parts.append(f"{_md(word.word)} · 原文搭配候选：" + " / ".join(_md(value) for value in word.collocations))
    else:
        parts.append("暂无学习词。")
    if study.exam_level != "general":
        parts.append("## 重点短语")
        for item in study.study_phrases:
            parts.extend([f"### {_md(item.phrase)} · {item.count} 次", _md(item.meaning_cn),
                "原文形式：" + " / ".join(_md(v) for v in item.forms),
                "原文例句：" + " / ".join(_md(v) for v in item.examples),
                "段落：" + ", ".join(map(str,item.locations)),
                "入选原因：" + "；".join(_md(v) for v in item.selection_reasons), "来源：" + _md(item.source)])
        if not study.study_phrases: parts.append("暂无匹配的重点短语。")
    parts.append("## 重点句与参考译文" if study.exam_level != "general" else "## 长难句")
    if study.sentence_breakdowns:
        parts.append("主干和从句分类为规则候选，请对照原句核对。")
        for item in study.sentence_breakdowns:
            parts.extend([f"### 第 {item.paragraph_index} 段 · 第 {item.sentence_index} 句 · {item.word_count} 词",
                          f"原句：{_md(item.text)}", f"主干候选：{_md(item.main_clause)}"])
            if item.context_before: parts.append("前文参考：" + _md(item.context_before))
            if item.selection_reasons: parts.append("入选原因：" + "；".join(_md(v) for v in item.selection_reasons))
            parts.append("参考译文：" + (_md(item.translation) if item.translation else "尚未取得译文"))
            parts.append("翻译状态：" + _md(item.translation_status) + " · " + _md(item.translation_note))
            if item.modifiers:
                parts.append("\n".join(f"- {_md(value)}" for value in item.modifiers))
            parts.append(_md(item.note))
    else:
        parts.append("暂无符合条件的长句。")
    parts.append("## 关键段")
    for item in study.key_paragraphs:
        parts.extend([f"### 第 {item.index} 段 · {item.word_count} 词 · {_md(item.reason)}",
                      _md(item.first_sentence), "主题词：" + " / ".join(_md(word) for word in item.topic_words)])
    if not study.key_paragraphs:
        parts.append("暂无关键段。")
    parts.append("## 文章结构")
    for item in study.outline.blocks:
        first, last = item.paragraph_range
        parts.append(f"- **{_md(item.title)}** · 第 {first}–{last} 段 · {item.word_count} 词：{_md(item.summary)}")
    if not study.outline.blocks:
        parts.append("暂无文章结构。")
    parts.append("## 行动清单")
    parts.append("\n".join(f"- [ ] {_md(item)}" for item in study.action_items) or "暂无学习任务。")
    if study.warnings:
        parts.extend(["## 提示", "\n".join(f"- {_md(value)}" for value in study.warnings)])
    return "\n\n".join(part for part in parts if part) + "\n"


def study_list_to_html(study: StudyList) -> str:
    """读取项目模板，一次性替换占位符；内容转义且样式内联。"""
    escape = lambda text: html.escape(str(text), quote=True)
    words = "<p>暂无学习词。</p>"
    if study.study_words:
        rows = []
        for word in study.study_words:
            rows.append("<tr>" + "".join(f"<td>{escape(value)}</td>" for value in
                        (word.display or word.word, word.pos, word.meaning_cn or word.meaning_en or "暂无释义",
                         word.count, ", ".join(map(str, word.locations)))) + "</tr>")
        words = '<div class="table-wrap"><table><thead><tr><th>词</th><th>词性</th><th>释义</th><th>次数</th><th>段落</th></tr></thead><tbody>' + "".join(rows) + "</tbody></table></div>"
        words += "".join(f"<p><strong>{escape(word.word)}</strong> · 原文搭配候选：{escape(' / '.join(word.collocations))}</p>"
                         for word in study.study_words if word.collocations)
    words += "".join(f"<p><strong>{escape(word.word)}</strong> · 入选原因：{escape('；'.join(word.selection_reasons))}</p>"
                     for word in study.study_words if word.selection_reasons)
    phrases = "".join(f'<article class="card"><h3>{escape(item.phrase)} · {item.count} 次</h3>'
        f'<p>{escape(item.meaning_cn)}</p><p>原文形式：{escape(" / ".join(item.forms))}</p>'
        f'<p>原文例句：{escape(" / ".join(item.examples))}</p><p>段落：{escape(", ".join(map(str,item.locations)))}</p>'
        f'<p>入选原因：{escape("；".join(item.selection_reasons))}</p><p class="muted">来源：{escape(item.source)}</p></article>'
        for item in study.study_phrases)
    sentences = "".join(f'<article class="card"><h3>第 {item.paragraph_index} 段 · 第 {item.sentence_index} 句 · {item.word_count} 词</h3>'
                        f'<p class="original">{escape(item.text)}</p><p><strong>参考译文：</strong>{escape(item.translation or "尚未取得译文")}</p>'
                        f'<p class="muted">翻译状态：{escape(item.translation_status)} · {escape(item.translation_note)}</p>'
                        f'<p>前文参考：{escape(item.context_before)}</p><p>入选原因：{escape("；".join(item.selection_reasons))}</p>'
                        f'<p><strong>主干候选：</strong>{escape(item.main_clause)}</p>' 
                        + ("<ul>" + "".join(f"<li>{escape(value)}</li>" for value in item.modifiers) + "</ul>" if item.modifiers else "")
                        + f'<p class="muted">{escape(item.note)}</p></article>' for item in study.sentence_breakdowns)
    if sentences:
        sentences = '<p class="muted">主干和从句分类为规则候选，请对照原句核对。</p>' + sentences
    paragraphs = "".join(f'<article class="card"><h3>第 {item.index} 段 · {item.word_count} 词 · {escape(item.reason)}</h3>'
                         f'<p>{escape(item.first_sentence)}</p><p class="muted">主题词：{escape(" / ".join(item.topic_words))}</p></article>'
                         for item in study.key_paragraphs)
    outline = "".join(f'<li><strong>{escape(item.title)}</strong> · 第 {item.paragraph_range[0]}–{item.paragraph_range[1]} 段 · '
                      f'{item.word_count} 词<p>{escape(item.summary)}</p></li>' for item in study.outline.blocks)
    actions = "".join(f'<li><label><input type="checkbox"> {escape(value)}</label></li>' for value in study.action_items)
    warnings = ("<aside><h2>提示</h2><ul>" + "".join(f"<li>{escape(value)}</li>" for value in study.warnings) + "</ul></aside>"
                if study.warnings else "")
    template_path = TEMPLATE_PATH if TEMPLATE_PATH.is_file() else FALLBACK_TEMPLATE_PATH
    if not template_path.is_file():
        raise FileNotFoundError("预习单模板缺失，请复制 templates/preview_template.html。")
    template = template_path.read_text(encoding="utf-8")
    css = STYLE_PATH.read_text(encoding="utf-8") if STYLE_PATH.is_file() else "body{font-family:sans-serif;max-width:1000px;margin:2rem auto;padding:1rem}"
    fields = {"title": escape(study.title or "未命名文章"), "overview": escape(study.overview or "暂无正文。"),
              "mode": "词汇材料" if study.mode == "vocabulary" else "通用文章", "style": css,
              "study_words": words, "study_phrases": phrases or "<p>暂无匹配的重点短语。</p>",
              "sentence_title": "重点句与参考译文" if study.exam_level != "general" else "长难句",
              "exam_label": {"general":"通用", "cet4":"四级", "cet6":"六级"}.get(study.exam_level,"通用"), "sentence_breakdowns": sentences or "<p>暂无符合条件的长句。</p>",
              "key_paragraphs": paragraphs or "<p>暂无关键段。</p>",
              "outline": "<ol>" + outline + "</ol>" if outline else "<p>暂无文章结构。</p>",
              "action_items": '<ul class="checklist">' + actions + "</ul>" if actions else "<p>暂无学习任务。</p>",
              "warnings": warnings}
    pattern = re.compile(r"\{\{\s*([a-z_]+)\s*\}\}")
    unknown = set(pattern.findall(template)) - fields.keys()
    if unknown:
        raise ValueError("预习模板含未知占位符：" + ", ".join(sorted(unknown)))
    return pattern.sub(lambda match: fields[match.group(1)], template)


def save_study_list(study: StudyList, destination: Path, fmt: str = "md") -> Path:
    """保存 md/html；先完成渲染，再写临时文件并原子替换目标。"""
    if fmt not in ("md", "html"):
        raise ValueError("预习单格式仅支持 md 和 html。")
    target = Path(destination).expanduser().resolve()
    if target.suffix.lower() != "." + fmt:
        target = target.with_suffix("." + fmt)
    content = study_list_to_markdown(study) if fmt == "md" else study_list_to_html(study)
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".study-", dir=target.parent)
    path = Path(temporary)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(path, target)
    finally:
        path.unlink(missing_ok=True)
    return target
