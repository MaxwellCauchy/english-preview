"""总词数/TTR 使用未去停用词、未还原的英文词；不作难度评级。"""

from ..models import AnalysisConfig, AnalysisStats, Document
from .sentence import SentenceInput, as_records, text_units, word_tokens


def compute_stats(document: Document, sentences: SentenceInput,
                  config: AnalysisConfig | None = None) -> AnalysisStats:
    config = config or AnalysisConfig()
    records = as_records(sentences)
    tokens = [token for item in records for token in word_tokens(item.text)]
    distinct = {token.lower() if config.ignore_case else token for token in tokens}
    count = len(tokens)
    return AnalysisStats(count, len(records), len(text_units(document, config)),
                         count / len(records) if records else 0.0,
                         len(distinct), len(distinct) / count if count else 0.0)
