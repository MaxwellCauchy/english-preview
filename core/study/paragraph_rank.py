"""按段落长度及关键词密度给出阅读顺序建议。"""

import re

from ..models import AnalysisResult
from .models import RankedParagraph, StudyConfig


def rank_paragraphs(result: AnalysisResult, config: StudyConfig) -> list[RankedParagraph]:
    """沿用全局段号；舞台说明只能依据现有模型保留的首句判断。"""
    keywords = {item.word.casefold() for item in result.keywords}
    ranked: list[RankedParagraph] = []
    for paragraph in result.paragraph_summaries:
        if paragraph.word_count < config.min_paragraph_words:
            continue
        if config.exclude_stage_directions and re.fullmatch(r"\(.*\)", paragraph.first_sentence.strip(), re.S):
            continue
        hits = len({word.casefold() for word in paragraph.topic_words} & keywords)
        reason = ("关键词密集" if hits >= 2 else "长段落，信息量大" if paragraph.word_count >= 25
                  else "开头段，点题" if paragraph.index <= 3 else "内容完整")
        ranked.append(RankedParagraph(index=paragraph.index, first_sentence=paragraph.first_sentence,
                                      topic_words=list(paragraph.topic_words), word_count=paragraph.word_count,
                                      score=float(paragraph.word_count + 3 * hits), reason=reason))
    ranked.sort(key=lambda item: (-item.score, item.index))
    return ranked[:config.max_key_paragraphs]
