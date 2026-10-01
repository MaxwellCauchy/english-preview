"""停用词、POS 辅助词形还原与可追溯词频。"""

from collections import Counter, defaultdict
from dataclasses import dataclass
from threading import Event

from ..models import AnalysisConfig, SentenceRecord, WordFrequency
from .runtime import AnalysisCancelled, lemmatizer, pos_tagger, resource_error, stop_words
from .sentence import SentenceInput, as_records, word_tokens


@dataclass
class PreparedSentence:
    record: SentenceRecord
    tokens: list[str]
    tags: list[str]
    lemmas: list[str]
    terms: list[tuple[str, str, str]]


def check_cancel(cancel_event: Event | None) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise AnalysisCancelled("分析已取消。")


def prepare(sentences: SentenceInput, config: AnalysisConfig,
            cancel_event: Event | None = None) -> list[PreparedSentence]:
    result: list[PreparedSentence] = []
    try:
        ignored = stop_words()
        tagger = pos_tagger() if config.use_lemmatization else None
        lemma = lemmatizer() if config.use_lemmatization else None
        for record in as_records(sentences):
            check_cancel(cancel_event)
            tokens = word_tokens(record.text)
            tags = [tag for _, tag in tagger.tag(tokens)] if tagger and tokens else [""] * len(tokens)
            lemmas: list[str] = []
            terms: list[tuple[str, str, str]] = []
            for token, tag in zip(tokens, tags):
                lower = token.lower().replace("’", "'")
                pos = {"J": "a", "V": "v", "N": "n", "R": "r"}.get(tag[:1], "n")
                base = lemma.lemmatize(lower, pos=pos) if lemma else lower
                lemmas.append(base)
                if lower in ignored or base in ignored or len(lower.replace("-", "").replace("'", "")) < config.min_word_length:
                    continue
                if config.ignore_case:
                    term = base
                elif base == lower:
                    term = token.replace("’", "'")
                elif token.isupper():
                    term = base.upper()
                elif token.istitle():
                    term = base[:1].upper() + base[1:]
                else:
                    term = base
                terms.append((term, token, tag))
            result.append(PreparedSentence(record, tokens, tags, lemmas, terms))
    except LookupError as exc:
        raise resource_error(exc) from exc
    return result


def frequencies(prepared: list[PreparedSentence]) -> list[WordFrequency]:
    counts: Counter[str] = Counter()
    display: dict[str, Counter[str]] = defaultdict(Counter)
    poses: dict[str, Counter[str]] = defaultdict(Counter)
    locations: dict[str, set[int]] = defaultdict(set)
    for sentence in prepared:
        for word, surface, pos in sentence.terms:
            counts[word] += 1
            display[word][surface] += 1
            poses[word][pos] += 1
            locations[word].add(sentence.record.paragraph_index)
    return [WordFrequency(word, display[word].most_common(1)[0][0], count,
                          poses[word].most_common(1)[0][0], sorted(locations[word]))
            for word, count in sorted(counts.items(), key=lambda item: (-item[1], item[0].casefold(), item[0]))]


def analyze_word_frequency(sentences: SentenceInput, config: AnalysisConfig | None = None) -> list[WordFrequency]:
    return frequencies(prepare(sentences, config or AnalysisConfig()))
