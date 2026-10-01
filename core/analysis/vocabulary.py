"""目标词、原文例句/搭配窗口、字母分组和出现覆盖率。"""

import csv
import io
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from ..models import AffixHint, AnalysisConfig, Document, PrefixGroup, TargetWord, VocabularyProgress
from .frequency import PreparedSentence
from .runtime import AnalysisError
from .sentence import WORD_RE

AFFIX_PATH = Path(__file__).resolve().parents[2] / "resources" / "affixes.json"
TARGET_RE = re.compile(r"[A-Za-z]+(?:[-'][A-Za-z]+)*|[A-Za-z](?:\.[A-Za-z])+\.?", re.ASCII)


def validate_targets(words: list[str]) -> list[str]:
    result: set[str] = set()
    for word in words:
        if not isinstance(word, str):
            raise ValueError("目标词清单只能包含字符串。")
        cleaned = word.strip().replace("’", "'").replace("\u2011", "-").lower()
        if not TARGET_RE.fullmatch(cleaned):
            raise ValueError(f"目标词格式无效：{word!r}。每项应为一个英文词或连字符复合词。")
        result.add(cleaned)
    if not result:
        raise ValueError("目标词清单为空。")
    return sorted(result)


def load_target_words(path: str | Path) -> list[str]:
    """UTF-8 TXT 一行一词；CSV 第一列为词，可带 word/词汇 表头。"""
    path = Path(path)
    if path.suffix.lower() not in (".txt", ".csv"):
        raise ValueError("目标词清单仅支持 .txt 或 .csv。")
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeError as exc:
        raise ValueError("目标词清单请保存为 UTF-8 编码。") from exc
    if path.suffix.lower() == ".csv":
        words = [row[0].strip() for row in csv.reader(io.StringIO(text)) if row and row[0].strip()]
    else:
        words = [line.strip() for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")]
    if words and words[0].casefold() in {"word", "words", "target", "target_word", "词汇", "目标词"}:
        words.pop(0)
    return validate_targets(words)


def choose_mode(document: Document, prepared: list[PreparedSentence], config: AnalysisConfig) -> tuple[str, str]:
    if config.mode != "auto":
        return config.mode, "按用户选择的模式分析。"
    if config.target_words is not None:
        return "vocabulary", "已导入目标词清单，自动采用词汇模式。"
    headings = " ".join([document.title] + [s.heading or "" for s in document.sections]).lower()
    if re.search(r"lexicon\s*quest|vocabulary|word\s*list|lexicon|词汇|目标词", headings):
        return "vocabulary", "标题或小标题包含明确的词汇材料标记。"
    words = {surface.lower() for item in prepared for _, surface, _ in item.terms}
    initials = Counter(word[:1] for word in words)
    concentration = max(initials.values(), default=0) / max(1, len(words))
    if len(words) >= 80 and concentration >= 0.55:
        return "vocabulary", "大量不同内容词集中在同一首字母下，推测为词汇材料；可手动切换。"
    return "article", "未发现明确词汇材料标记，采用通用文章模式。"


def _collocation(sentence: PreparedSentence, position: int) -> str:
    """截取目标词后的连续原文窗口；属于搭配候选，不生成不存在的表达。"""
    matches = list(WORD_RE.finditer(sentence.record.text))
    end = position
    for candidate in range(position + 1, min(position + 5, len(matches))):
        gap = sentence.record.text[matches[candidate - 1].end():matches[candidate].start()]
        if re.search(r"[.,;:!?—–]", gap):
            break
        end = candidate
        if sentence.tags[candidate].startswith("N"):
            break
    if end == position:
        return ""
    while end > position and sentence.tokens[end].lower() in {"a", "an", "the", "her", "his", "of", "to", "and", "in", "with"}:
        end -= 1
    if end == position:
        return ""
    return sentence.record.text[matches[position].start():matches[end].end()]


def vocabulary(prepared: list[PreparedSentence], config: AnalysisConfig) -> tuple[
    list[TargetWord], list[PrefixGroup], list[AffixHint], VocabularyProgress, list[str]
]:
    provided = config.target_words is not None
    targets = validate_targets(config.target_words or []) if provided else sorted({
        term.lower().replace("’", "'") for item in prepared for term, _, _ in item.terms
    })
    entries = {word: TargetWord(word) for word in targets}
    locations: dict[str, set[int]] = defaultdict(set)
    for sentence in prepared:
        for position, (surface, lemma) in enumerate(zip(sentence.tokens, sentence.lemmas)):
            raw = surface.lower().replace("’", "'")
            key = raw if raw in entries else lemma if config.use_lemmatization and lemma in entries else None
            if key is None:
                continue
            entry = entries[key]
            entry.count += 1
            locations[key].add(sentence.record.paragraph_index)
            if sentence.record.text not in entry.examples and len(entry.examples) < config.max_examples:
                entry.examples.append(sentence.record.text)
            span = _collocation(sentence, position)
            if span and span not in entry.collocations and len(entry.collocations) < config.max_examples:
                entry.collocations.append(span)
    for word, entry in entries.items():
        entry.locations = sorted(locations[word])
    groups: dict[str, list[TargetWord]] = defaultdict(list)
    for word, entry in entries.items():
        groups[word[:config.prefix_length]].append(entry)
    prefix_groups = [PrefixGroup(prefix + "-", [e.word for e in items], len(items),
                                 sum(e.count > 0 for e in items), sum(e.count for e in items))
                     for prefix, items in sorted(groups.items())]
    hints: list[AffixHint] = []
    try:
        data = json.loads(AFFIX_PATH.read_text(encoding="utf-8"))
        for rule in data["hints"]:
            examples = [word for word in rule["examples"] if word in entries and entries[word].count]
            if examples:
                hints.append(AffixHint(rule["affix"], rule["meaning"], examples, rule["source"]))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise AnalysisError("词缀提示资源缺失或格式错误，请完整复制 resources/affixes.json。") from exc
    seen = sum(e.count > 0 for e in entries.values())
    progress = VocabularyProgress("provided" if provided else "candidate",
                                   len(entries) if provided else None, seen,
                                   seen / len(entries) if provided and entries else None,
                                   [e.word for e in entries.values() if e.count == 0])
    warnings = [] if provided else ["未导入正式目标词清单：以下是正文候选词，目标总数与出现覆盖率暂不计算。"]
    return list(entries.values()), prefix_groups, hints, progress, warnings
