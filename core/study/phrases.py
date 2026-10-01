"""本地短语词库匹配：词形归一、限长空位、最长匹配、不跨标点。"""
import json
import re
from pathlib import Path
from dataclasses import dataclass
from functools import lru_cache
from ..analysis.frequency import prepare, PreparedSentence
from ..models import AnalysisConfig, SentenceRecord
from ..analysis.sentence import WORD_RE
from .models import StudyConfig, StudyPhrase

PHRASE_PATH = Path(__file__).resolve().parents[2] / "resources" / "exams" / "phrases.json"

@dataclass(frozen=True)
class PhraseMatch:
    phrase: str
    start: int
    end: int
    form: str
    entry: dict

@lru_cache(maxsize=4)
def _load(path: str, stamp: int) -> tuple[dict, ...]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    entries = data.get("entries", [])
    if not isinstance(entries, list): raise ValueError("短语库 entries 必须为列表。")
    for entry in entries:
        if not all(isinstance(entry.get(k), str) and entry[k] for k in ("phrase", "meaning_cn", "source")):
            raise ValueError("短语词条缺少名称、释义或来源。")
        if not isinstance(entry.get("patterns"), list) or not all(isinstance(p, str) for p in entry["patterns"]):
            raise ValueError("短语匹配形式必须为字符串列表。")
    return tuple(entries)

def load_phrases() -> tuple[dict, ...]:
    if not PHRASE_PATH.is_file(): raise FileNotFoundError("重点短语库缺失，请复制 resources/exams/phrases.json。")
    return _load(str(PHRASE_PATH.resolve()), PHRASE_PATH.stat().st_mtime_ns)

def match_phrases(sentence: PreparedSentence, entries: tuple[dict, ...], level: str) -> list[PhraseMatch]:
    text = sentence.record.text
    offsets = list(WORD_RE.finditer(text))
    lemmas = [token.lower() for token in sentence.lemmas]
    tokens = [token.lower() for token in sentence.tokens]
    found = []
    def walk(pattern, index, current):
        if index == len(pattern): return [current]
        if pattern[index] == "{gap}":
            # 插入成分为 1..6 个完整单词，不跨句或标点。
            return [end for gap in range(1, 7) if current+gap <= len(tokens)
                    for end in walk(pattern, index+1, current+gap)]
        if current < len(tokens) and pattern[index] in (tokens[current], lemmas[current]):
            return walk(pattern,index+1,current+1)
        return []
    for entry in entries:
        if level != "general" and level not in entry.get("applicable_levels", []): continue
        for pattern in entry["patterns"]:
            parts = pattern.lower().split()
            for start in range(len(tokens)):
                for end in walk(parts,0,start):
                    if end <= start: continue
                    between = [text[offsets[i].end():offsets[i+1].start()] for i in range(start,end-1)]
                    if any(re.search(r"[^\s]", value) for value in between): continue
                    if "{gap}" in parts:
                        literal = sum(part != "{gap}" for part in parts)
                        if end-start <= literal: continue
                    found.append(PhraseMatch(entry['phrase'],start,end,text[offsets[start].start():offsets[end-1].end()],entry))
    # 长表达优先；同一跨度可由多个变形模式匹配，保持去重。
    used = set(); selected=[]
    for item in sorted(found,key=lambda m:(-(m.end-m.start),m.start,m.phrase)):
        span=set(range(item.start,item.end))
        if span & used: continue
        selected.append(item); used |= span
    return sorted(selected,key=lambda m:m.start)

def select_phrases(prepared: list[PreparedSentence], config: StudyConfig) -> list[StudyPhrase]:
    entries = load_phrases(); grouped={}
    for sentence in prepared:
        if config.exclude_stage_directions and re.fullmatch(r"\(.*\)",sentence.record.text.strip(),re.S): continue
        for match in match_phrases(sentence,entries,config.exam_level):
            item = grouped.setdefault(match.phrase, StudyPhrase(phrase=match.phrase,meaning_cn=match.entry['meaning_cn'],
                source=match.entry['source'],exam_levels=list(match.entry.get('exam_levels',[])),
                selection_reasons=['已收录的固定表达／句型','通用教学短语，未标官方考试等级']))
            item.count += 1
            if sentence.record.paragraph_index not in item.locations: item.locations.append(sentence.record.paragraph_index)
            if match.form not in item.forms: item.forms.append(match.form)
            if len(item.examples)<3 and sentence.record.text not in item.examples: item.examples.append(sentence.record.text)
    common={'for example','for instance','in fact','according to','as well as','at the same time'}
    for item in grouped.values():
        item.score = (2 if item.phrase in common else 6) + min(item.count,4) + ('…' in item.phrase)*2
    return sorted(grouped.values(),key=lambda item:(-item.score,-item.count,item.phrase))[:config.max_phrases]
