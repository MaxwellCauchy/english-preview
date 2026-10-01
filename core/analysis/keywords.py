"""每句为一个文档，TF×平滑 IDF 的全文均值；不依赖 sklearn。"""

import math
from collections import Counter, defaultdict

from ..models import AnalysisConfig, Keyword
from .frequency import PreparedSentence, prepare
from .sentence import SentenceInput


def keywords(prepared: list[PreparedSentence], config: AnalysisConfig) -> list[Keyword]:
    if not prepared:
        return []
    counts: Counter[str] = Counter()
    df: Counter[str] = Counter()
    tf_sum: dict[str, float] = defaultdict(float)
    locations: dict[str, set[int]] = defaultdict(set)
    for sentence in prepared:
        local = Counter(word for word, _, _ in sentence.terms)
        counts.update(local)
        df.update(local.keys())
        length = sum(local.values())
        for word, count in local.items():
            tf_sum[word] += count / length
            locations[word].add(sentence.record.paragraph_index)
    size = len(prepared)
    result = [Keyword(word, tf_sum[word] / size * (math.log((1 + size) / (1 + df[word])) + 1),
                      count, sorted(locations[word]))
              for word, count in counts.items() if count >= config.min_frequency]
    return sorted(result, key=lambda item: (-item.score, -item.count, item.word.casefold(), item.word))[:config.top_keywords]


def extract_keywords(sentences: SentenceInput, config: AnalysisConfig | None = None) -> list[Keyword]:
    config = config or AnalysisConfig()
    return keywords(prepare(sentences, config), config)
