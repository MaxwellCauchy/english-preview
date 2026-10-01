"""AnalysisResult → StudyList；各子步骤可降级，取消不会被降级吞掉。"""

from copy import deepcopy
import re
from typing import Callable

from ..models import AnalysisResult, AnalysisConfig, Document, SentenceRecord
from ..analysis.sentence import document_sentences
from ..analysis.frequency import prepare, frequencies as count_frequencies
from .phrases import select_phrases
from .sentence_rank import select_sentences
from ..analysis.sentence import word_tokens
from . import dictionary, wordlist
from .main_structure import extract_main_structure
from .models import StudyConfig, StudyList
from .outline import build_outline
from .paragraph_rank import rank_paragraphs
from .study_words import select_study_words, select_target_words


class StudyCancelled(Exception):
    """由进度回调触发的协作式取消；UI 在当前步骤完成后停止。"""


def build_study_list(result: AnalysisResult, config: StudyConfig | None = None, *,
                     progress_callback: Callable[[int, int, str], None] | None = None,
                     document: Document | None = None, analysis_config: AnalysisConfig | None = None) -> StudyList:
    """独立转换分析结果，不修改 result；失败信息写入 warnings。

    progress_callback(done, 6, message) 在初始和每步完成时调用。
    回调可抛 StudyCancelled 中断；其他回调错误会记入 warnings。
    词汇模式沿用目标词，两个模式都遵守 top_study_words 数量限制。
    """
    config = config or StudyConfig()
    study = StudyList(title=result.article_title, mode=result.mode, stats=deepcopy(result.stats),
                      warnings=list(result.warnings), exam_level=config.exam_level)

    def progress(step: int, message: str) -> None:
        if progress_callback:
            try:
                progress_callback(step, 6, message)
            except StudyCancelled:
                raise
            except Exception as exc:
                study.warnings.append(f"进度通知失败：{exc}")

    def run(name: str, operation):
        try:
            return operation()
        except StudyCancelled:
            raise
        except Exception as exc:
            study.warnings.append(f"{name}未完成：{exc}")
            return None

    progress(0, "正在准备预习清单…")
    if not (result.stats.total_words or result.word_frequencies or result.target_words
            or result.long_sentences or result.paragraph_summaries):
        study.warnings.append("正文为空，没有生成学习任务。")
        progress(6, "正文为空")
        return study
    prepared = []
    if config.exam_level != "general":
        def prepare_body():
            options = deepcopy(analysis_config or AnalysisConfig())
            options.use_lemmatization = True
            options.min_word_length = 3
            options.ignore_case = True
            records = document_sentences(document, options) if document is not None else [
                SentenceRecord(item.text, item.paragraph_index, item.sentence_index, item.page_number)
                for item in result.long_sentences]
            return prepare(records, options)
        prepared = run("完整正文准备", prepare_body) or []
        if document is None:
            study.warnings.append("未提供完整 Document，短语与选句仅覆盖分析结果中的长句；UI 会传完整正文。")
    # 仅剔除可以确认“整段都是舞台说明”的位置；不猜测混合正文的词数。
    stage_indices = {item.index for item in result.paragraph_summaries
                     if re.fullmatch(r"\(.*\)", item.first_sentence.strip(), re.S)
                     and item.word_count == len(word_tokens(item.first_sentence))}
    frequencies = [item for item in result.word_frequencies
                   if not (config.exclude_stage_directions and item.locations
                           and set(item.locations) <= stage_indices)]
    if prepared:
        # 取完整正文中所有频次，避免分析报告门槛漏掉一次出现的难词。
        frequencies = count_frequencies([item for item in prepared if not (
            config.exclude_stage_directions and re.fullmatch(r"\(.*\)", item.record.text.strip(), re.S))])
    words = run("学习词筛选", lambda: select_target_words(result.target_words, config)
                if result.mode == "vocabulary" else select_study_words(frequencies, config,
                    keywords={item.word.lower() for item in result.keywords}))
    study.study_words = words or []
    if config.exam_level == "general" and config.use_dictionary and not dictionary.is_loaded():
        study.warnings.append("离线词典不可用，学习词仍可查看；本次没有补充释义。")
    elif config.exam_level == "general" and config.use_dictionary:
        missing = sum(item.source != "ecdict" for item in study.study_words)
        if missing:
            study.warnings.append(f"有 {missing} 个学习词未在离线词典命中，释义留空。")
    if config.use_wordlists and result.mode == "article":
        basic = run("基础词表检查", wordlist.load_top2000)
        if not basic:
            study.warnings.append("基础词表缺失或为空，本次仅过滤停用词和短词。")
    if config.exam_level != "general" and config.use_dictionary:
        missing = sum(not (item.meaning_cn or item.meaning_en) for item in study.study_words)
        if missing: study.warnings.append(f"{missing} 个补充词未命中分级词库或已加载词典，释义留空。")
    progress(1, "学习词整理完成")
    if config.exam_level != "general":
        study.study_phrases = run("重点短语匹配", lambda: select_phrases(prepared, config)) or []
        study.sentence_breakdowns = run("重点句排序", lambda: select_sentences(prepared, study.study_words,
            study.study_phrases, config, {item.word.lower() for item in result.keywords})) or []
        study.warnings.append("四六级等级来自 ECDICT 历史标签；短语为通用教学素材，未标官方考试等级或真题考频。")
    else:
        sentences = [item for item in result.long_sentences if item.word_count >= config.min_sentence_words]
        for sentence in sentences[:config.max_long_sentences]:
            breakdown = run("长句主干提示", lambda sentence=sentence: extract_main_structure(sentence, config))
            if breakdown is not None: study.sentence_breakdowns.append(breakdown)
    progress(2, "长句阅读提示整理完成")
    paragraphs = run("关键段排序", lambda: rank_paragraphs(result, config))
    study.key_paragraphs = paragraphs or []
    progress(3, "关键段整理完成")
    outline = run("文章结构", lambda: build_outline(result, config))
    if outline is not None:
        study.outline = outline
    if len(result.article_map) < 2 and len(result.paragraph_summaries) >= 5:
        study.warnings.append("文章结构按段落位置划分；引入、转折等标签是阅读位置提示，不是内容判断。")
    progress(4, "文章结构整理完成")
    stats = study.stats
    study.overview = (f"{study.title or '未命名文章'}，共 {stats.total_words} 词，"
                      f"{stats.total_paragraphs} 段，平均句长 {stats.avg_sentence_length:.1f} 词。")
    progress(5, "文章速览整理完成")
    study.action_items = ["通读全文，不查词，标记不懂的地方", f"学 {len(study.study_words)} 个必学词",
                          f"看 {len(study.sentence_breakdowns)} 个长难句的主干",
                          f"重点读 {len(study.key_paragraphs)} 个关键段", "用自己的话写 3 句总结",
                          "标记 2-3 个问题，带去上课"]
    study.warnings = list(dict.fromkeys(study.warnings))
    if config.exam_level != "general":
        study.overview += "目标：" + {"cet4":"四级", "cet6":"六级"}[config.exam_level] + "。"
        study.action_items[1] += f"，掌握 {len(study.study_phrases)} 个重点短语"
        study.action_items[2] = f"精读 {len(study.sentence_breakdowns)} 个重点句，核对原句与参考译文"
    if config.translate_sentences:
        from .translation import translate_study_sentences
        def translation_progress(done, total, message):
            progress(5, f"{message}（{done}/{total}）")
        run("离线翻译", lambda: translate_study_sentences(study, config,
            progress_callback=translation_progress))
    progress(6, "预习清单生成完成")
    return study
