"""基于词性和连接词的主干候选；不是完整句法解析器。"""

import re

from ..analysis.runtime import pos_tagger
from ..analysis.sentence import WORD_RE, word_tokens
from ..models import LongSentence
from .models import SentenceBreakdown, StudyConfig

_RELATIVE = {"that", "which", "who", "whom", "whose"}
_ADVERBIAL = {"because", "although", "when", "if", "while", "unless", "since"}


def extract_main_structure(sentence: LongSentence, config: StudyConfig) -> SentenceBreakdown:
    """返回完整字段；资源缺失或规则失败时保留原句并退回前八词。

    优先找有限动词或情态动词，保留助动词和否定；跳过逗号界定的
    前置状语。无逗号的嵌套从句仍可能判断不准，输出仅供阅读核对。
    """
    breakdown = SentenceBreakdown(text=sentence.text, word_count=sentence.word_count,
                                  paragraph_index=sentence.paragraph_index,
                                  sentence_index=sentence.sentence_index)
    try:
        tokens = word_tokens(sentence.text)
        spans = list(WORD_RE.finditer(sentence.text))
        tags = [tag for _, tag in pos_tagger().tag(tokens)]
        if not tokens or len(tokens) != len(tags):
            raise ValueError("没有可解析的词。")
        lower = [token.casefold() for token in tokens]
        start = 0
        if lower[0] in _ADVERBIAL:
            comma = sentence.text.find(",")
            if comma >= 0:
                start = next((index for index, span in enumerate(spans) if span.start() > comma), len(tokens))
        verbs = [index for index in range(start, len(tokens)) if tags[index] in ("VBD", "VBP", "VBZ", "MD")]
        if not verbs:
            verbs = [index for index in range(start, len(tokens)) if tags[index].startswith("VB")]
        if not verbs:
            raise ValueError("没有动词。")
        predicate = verbs[0]
        relative = next((index for index in range(start + 1, predicate) if lower[index] in _RELATIVE), None)
        subject_end = predicate
        if relative is not None and len(verbs) > 1:
            # 有限动词前含关系词时，把关系词之前视为主语候选。
            predicate = next((index for index in verbs[1:]
                              if lower[index] not in {"be", "is", "are", "was", "were", "have", "has", "had"}), verbs[-1])
            subject_end = relative
        subject = tokens[start:subject_end]
        if not subject or not any(tag.startswith("NN") or tag.startswith("PRP") for tag in tags[start:subject_end]):
            raise ValueError("主语不明确。")
        end = predicate + 1
        while end < len(tokens) and (tags[end].startswith("VB") or lower[end] in {"not", "never"}):
            end += 1
        phrase_end = end
        while phrase_end < len(tokens):
            gap = sentence.text[spans[phrase_end - 1].end():spans[phrase_end].start()]
            if (re.search(r"[,;:.!?]", gap) or tags[phrase_end] in ("IN", "TO", "CC")
                    or lower[phrase_end] in _RELATIVE | _ADVERBIAL):
                break
            if tags[phrase_end].startswith("VB"):
                break
            phrase_end += 1
        breakdown.main_clause = " ".join(subject + tokens[predicate:phrase_end])
        modifiers: list[str] = []
        clause_pattern = r"\b(so\s+that|because|although|when|if|while|unless|since|that|which|who|whom|whose)\b[^,;.!?]*"
        for match in re.finditer(clause_pattern, sentence.text, re.I):
            marker = match.group(1).lower()
            label = "定语从句候选" if marker in _RELATIVE else "状语从句候选"
            modifiers.append(f"{label}：{match.group().strip()}")
        for index, tag in enumerate(tags):
            if tag != "IN" or lower[index] in _RELATIVE | _ADVERBIAL:
                continue
            stop = index + 1
            while stop < len(tokens) and (tags[stop].startswith(("NN", "JJ", "PRP")) or tags[stop] in ("DT", "CD", "POS")):
                if re.search(r"[,;.!?]", sentence.text[spans[stop - 1].end():spans[stop].start()]):
                    break
                stop += 1
            if stop > index + 1:
                modifiers.append("介词短语：" + " ".join(tokens[index:stop]))
        for match in re.finditer(r",\s*([^,]+?)\s*,", sentence.text):
            modifiers.append("插入语候选：" + match.group(1).strip())
        breakdown.modifiers = list(dict.fromkeys(modifiers))
        breakdown.note = "先读主干，再加修饰。"
    except Exception:
        # 本入口的约定是任何解析异常都降级，不让单句阻断预习单。
        try:
            preview = word_tokens(sentence.text)[:8]
        except Exception:
            preview = sentence.text.split()[:8]
        breakdown.main_clause = " ".join(preview) + "..."
        breakdown.modifiers = []
        breakdown.note = "规则解析失败，请人工判断主干。"
    return breakdown
