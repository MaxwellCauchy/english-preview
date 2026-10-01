"""稳定入口：Document → 离线规则分析。读取、界面与分析彼此独立。"""

from threading import Event
from typing import Callable

from .analysis.frequency import analyze_word_frequency, check_cancel, frequencies, prepare
from .analysis.keywords import extract_keywords, keywords
from .analysis.long_sentences import detect_long_sentences, long_sentences
from .analysis.paragraph import article_map, summaries, summarize_paragraphs
from .analysis.runtime import AnalysisCancelled, AnalysisError
from .analysis.sentence import document_sentences, segment_sentences
from .analysis.stats import compute_stats
from .analysis.vocabulary import choose_mode, load_target_words, vocabulary
from .models import AnalysisConfig, AnalysisResult, Document

__all__ = ["analyze_document", "segment_sentences", "analyze_word_frequency", "extract_keywords",
           "detect_long_sentences", "summarize_paragraphs", "compute_stats", "load_target_words",
           "AnalysisError", "AnalysisCancelled"]


def analyze_document(document: Document, config: AnalysisConfig | None = None, *,
                     progress_callback: Callable[[int, int, str], None] | None = None,
                     cancel_event: Event | None = None) -> AnalysisResult:
    config = config or AnalysisConfig()

    def progress(step: int, message: str) -> None:
        check_cancel(cancel_event)
        if progress_callback:
            progress_callback(step, 5, message)

    progress(0, "正在切分正文句子…")
    records = document_sentences(document, config)
    progress(1, "正在分词、过滤停用词并还原词形…")
    prepared = prepare(records, config, cancel_event)
    mode, reason = choose_mode(document, prepared, config)
    progress(2, "正在统计词频和计算 TF-IDF…")
    result = AnalysisResult(
        word_frequencies=frequencies(prepared), keywords=keywords(prepared, config),
        long_sentences=long_sentences(records, config),
        paragraph_summaries=summaries(document, prepared, config),
        stats=compute_stats(document, records, config), mode=mode,
        mode_reason=reason, article_title=document.title, article_map=article_map(document, config),
    )
    progress(3, "正在整理目标词、例句和字母分组…" if mode == "vocabulary" else "正在整理首句线索与文章地图…")
    if mode == "vocabulary":
        result.target_words, result.prefix_groups, result.affix_hints, result.vocabulary_progress, warnings = vocabulary(prepared, config)
        result.warnings.extend(warnings)
    if not result.stats.total_words:
        result.warnings.append("正文中没有可分析的英文词；标题、图片和表格不计入正文。")
    progress(4, "正在生成分析结果…")
    result.warnings.extend(document.warnings)
    progress(5, "分析完成")
    return result
