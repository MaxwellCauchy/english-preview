"""首句线索和本段高频词；首句不等同于自动生成的段落主旨。"""

from collections import Counter, defaultdict

from ..models import AnalysisConfig, Document, ParagraphSummary, SectionOverview
from .frequency import PreparedSentence, prepare
from .sentence import document_sentences, text_units, word_tokens


def summaries(document: Document, prepared: list[PreparedSentence], config: AnalysisConfig) -> list[ParagraphSummary]:
    by_paragraph: dict[int, list[PreparedSentence]] = defaultdict(list)
    for sentence in prepared:
        by_paragraph[sentence.record.paragraph_index].append(sentence)
    result: list[ParagraphSummary] = []
    for paragraph, _, page, text in text_units(document, config):
        sentences = by_paragraph[paragraph]
        counts = Counter(term for item in sentences for term, _, _ in item.terms)
        top = sorted(counts, key=lambda word: (-counts[word], word.casefold(), word))[:3]
        result.append(ParagraphSummary(paragraph, sentences[0].record.text if sentences else "", top,
                                       len(word_tokens(text)), page))
    return result


def summarize_paragraphs(document: Document, config: AnalysisConfig | None = None) -> list[ParagraphSummary]:
    config = config or AnalysisConfig()
    return summaries(document, prepare(document_sentences(document, config), config), config)


def article_map(document: Document, config: AnalysisConfig) -> list[SectionOverview]:
    units = text_units(document, config)
    return [SectionOverview(section.heading or "正文", section.level,
                            [p for p, s, _, _ in units if s == index],
                            sum(len(word_tokens(text)) for _, s, _, text in units if s == index),
                            sorted({page for _, s, page, _ in units if s == index and page}))
            for index, section in enumerate(document.sections) if section.content or section.heading]
