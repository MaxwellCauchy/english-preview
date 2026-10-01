"""有章节时沿用章节；无章节时仅按位置作阅读分组，不推断叙事含义。"""

from ..models import AnalysisResult
from .models import ArticleOutline, OutlineBlock, StudyConfig


def build_outline(result: AnalysisResult, config: StudyConfig) -> ArticleOutline:
    """按原段号输出不重复、不遗漏的结构；少于五段时输出一块。"""
    paragraphs = sorted(result.paragraph_summaries, key=lambda item: item.index)
    if not paragraphs:
        return ArticleOutline()
    if len(paragraphs) < 5:
        return ArticleOutline([OutlineBlock(title=result.article_title or "全文",
                             paragraph_range=(paragraphs[0].index, paragraphs[-1].index),
                             word_count=sum(item.word_count for item in paragraphs),
                             summary=paragraphs[0].first_sentence)])
    by_index = {item.index: item for item in paragraphs}
    if len(result.article_map) >= 2:
        blocks: list[OutlineBlock] = []
        for index, section in enumerate(result.article_map, 1):
            members = sorted(set(section.paragraph_indices) & by_index.keys())
            if not members:
                continue
            blocks.append(OutlineBlock(title=section.heading or f"第 {index} 部分",
                                       paragraph_range=(members[0], members[-1]),
                                       word_count=sum(by_index[number].word_count for number in members),
                                       summary=by_index[members[0]].first_sentence))
        if blocks and set(number for section in result.article_map for number in section.paragraph_indices) >= by_index.keys():
            return ArticleOutline(blocks)
    blocks = []
    start, total = 0, len(paragraphs)
    for index, (title, ratio) in enumerate(zip(("引入", "发展", "核心", "转折/高潮", "总结"),
                                             (0.15, 0.4, 0.7, 0.9, 1.0))):
        # 每块至少一个段落，且为后面的块预留段落，避免短文的空区间。
        end = min(total - (4 - index), max(start + 1, int(total * ratio + 0.5)))
        members = paragraphs[start:end]
        blocks.append(OutlineBlock(title=title, paragraph_range=(members[0].index, members[-1].index),
                                   word_count=sum(item.word_count for item in members),
                                   summary=members[0].first_sentence))
        start = end
    return ArticleOutline(blocks)
