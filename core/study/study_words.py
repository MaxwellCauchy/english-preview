"""从分析词频筛选学习词；显式目标词不经过基础词过滤。"""

from ..models import TargetWord, WordFrequency
from . import dictionary, wordlist
from .exams import load_exam_words, LABELS
from .models import StudyConfig, StudyWord


def _ensure_dictionary(config: StudyConfig) -> None:
    if config.use_dictionary and not dictionary.is_loaded():
        try:
            dictionary.load_ecdict(dictionary.DEFAULT_PATH)
        except (OSError, ValueError):
            pass


def _make_word(word: str, display: str, count: int, locations: list[int],
               pos: str, config: StudyConfig, collocations: list[str] | None = None) -> StudyWord:
    entry = dictionary.lookup(word) if config.use_dictionary else None
    fields = dictionary.entry_fields(entry) if entry is not None else {}
    return StudyWord(word=word, display=display or word, count=count, locations=list(locations),
                     pos=fields.pop("pos", "") or pos, collocations=list(collocations or []),
                     source="ecdict" if entry is not None else "candidate", **fields)


def _score(word: StudyWord) -> float:
    value = word.count * (1 + word.collins_star)
    return value * 1.5 if word.oxford_flag else value


def select_study_words(frequencies: list[WordFrequency], config: StudyConfig, *, keywords: set[str] | None = None) -> list[StudyWord]:
    """过滤基础词、停用词、短词和纯数字，再按约定分数排序；不修改输入。"""
    if config.exam_level != "general":
        return _select_exam_words(frequencies, config, keywords=keywords)
    _ensure_dictionary(config)
    selected: list[StudyWord] = []
    for item in frequencies:
        if (len(item.word) < 4 or item.word.isdigit()
                or wordlist.is_basic_word(item.word, use_top2000=config.use_wordlists)
                or wordlist.is_stopword(item.word)
                or (item.pos in ("NNP", "NNPS") and item.display[:1].isupper())):
            continue
        selected.append(_make_word(item.word, item.display, item.count, item.locations, item.pos, config))
    selected.sort(key=lambda word: (-_score(word), -word.count, word.word.casefold(), word.word))
    return selected[:config.top_study_words]


def select_target_words(targets: list[TargetWord], config: StudyConfig) -> list[StudyWord]:
    """保留正式目标词（含基础词），补释义并按同一分数选取指定数量。"""
    if config.exam_level != "general":
        words = _select_exam_words(targets, config, explicit=True)
        return words
    _ensure_dictionary(config)
    selected = [_make_word(item.word, item.word, item.count, item.locations, "", config, item.collocations)
                for item in targets]
    selected.sort(key=lambda word: (-_score(word), -word.count, word.word.casefold(), word.word))
    return selected[:config.top_study_words]


def _select_exam_words(items, config: StudyConfig, explicit: bool = False, keywords: set[str] | None = None) -> list[StudyWord]:
    """使用小型分级资源补释义；不要求载入百万条全词典。"""
    import math
    target = load_exam_words(config.exam_level)
    other_level = "cet6" if config.exam_level == "cet4" else "cet4"
    other = load_exam_words(other_level)
    selected = []
    for item in items:
        key = item.word.lower()
        if not explicit and (len(key) < 4 or wordlist.is_stopword(key)
                or wordlist.is_basic_word(key, use_top2000=config.use_wordlists)
                or (getattr(item, "pos", "") in ("NNP", "NNPS") and getattr(item, "display", key)[:1].isupper())):
            continue
        row = target.get(key) or other.get(key)
        fields = {}
        if row and config.use_dictionary:
            fields = dictionary.entry_fields(dict(pos=row.get("pos", ""), translation=row.get("meaning_cn", ""),
                definition=row.get("meaning_en", ""), collins=row.get("collins_star", ""), oxford=row.get("oxford_flag", "")))
        else:
            entry = dictionary.lookup(key) if config.use_dictionary else None
            if entry: fields = dictionary.entry_fields(entry)
        levels = [level for level, data in ((config.exam_level, target), (other_level, other)) if key in data]
        reasons = ["用户指定词"] if explicit else []
        if key in target: reasons.append(LABELS[config.exam_level] + "词典标签匹配")
        elif levels: reasons.append("另一等级词汇，作为补充")
        else: reasons.append("文章补充词，未标考试等级")
        star = fields.get("collins_star", 0)
        # 星级越高通常越常用，不再将其当成难度正向指标；无星级只称线索。
        difficulty = 2 if star == 0 else (5 - star) * 0.6
        score = (12 if key in target else 2) + difficulty + min(4, math.log2(item.count + 1))
        if key in (keywords or set()):
            score += 3
            reasons.append("文章关键词线索")
        if item.count > 1: reasons.append("原文反复出现")
        if star <= 2: reasons.append("低常用度线索；不等同于官方难度")
        word = StudyWord(word=key, display=getattr(item, "display", key), count=item.count,
            locations=list(item.locations), collocations=list(getattr(item, "collocations", [])),
            source="exam_resource" if row else "candidate", exam_levels=sorted(levels),
            selection_reasons=reasons, score=score, **fields)
        selected.append(word)
    selected.sort(key=lambda word: (-word.score, -word.count, word.word))
    return selected[:config.top_study_words]
