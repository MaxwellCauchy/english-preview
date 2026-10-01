"""词数严格超过阈值才标记长句，不推断句法难度。"""

from ..models import AnalysisConfig, Document, LongSentence, SentenceRecord
from .sentence import document_sentences, word_tokens


def long_sentences(records: list[SentenceRecord], config: AnalysisConfig) -> list[LongSentence]:
    result = [LongSentence(item.text, len(word_tokens(item.text)), item.paragraph_index,
                           item.sentence_index, item.page_number)
              for item in records if len(word_tokens(item.text)) > config.max_words_per_sentence]
    return sorted(result, key=lambda item: (-item.word_count, item.paragraph_index, item.sentence_index))


def detect_long_sentences(document: Document, config: AnalysisConfig | None = None) -> list[LongSentence]:
    config = config or AnalysisConfig()
    return long_sentences(document_sentences(document, config), config)
