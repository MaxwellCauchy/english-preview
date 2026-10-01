"""离线 NLTK 资源。运行中不下载模型，也不访问网络。"""

import threading
from functools import lru_cache
from pathlib import Path

import nltk
from nltk.corpus import stopwords, wordnet
from nltk.stem import WordNetLemmatizer
from nltk.tag import PerceptronTagger
from nltk.tokenize.punkt import PunktTokenizer

DATA_ROOT = Path(__file__).resolve().parents[2] / "resources" / "nltk_data"
# 本项目随包模型优先于用户全局模型，避免版本/模型差异。
if str(DATA_ROOT) not in nltk.data.path:
    nltk.data.path.insert(0, str(DATA_ROOT))
_LOCK = threading.RLock()


class AnalysisError(Exception):
    """可以直接向用户显示的分析错误。"""


class AnalysisCancelled(AnalysisError):
    pass


@lru_cache(maxsize=1)
def sentence_tokenizer() -> PunktTokenizer:
    with _LOCK:
        tokenizer = PunktTokenizer("english")
        tokenizer._params.abbrev_types.update({
            "dr", "mr", "mrs", "ms", "prof", "sr", "jr", "e.g", "i.e", "etc",
            "a.m", "p.m", "a.d", "b.c", "u.s", "u.k", "vs", "fig", "no",
        })
        return tokenizer


@lru_cache(maxsize=1)
def stop_words() -> frozenset[str]:
    with _LOCK:
        return frozenset(stopwords.words("english")) | {"said", "also", "would"}


@lru_cache(maxsize=1)
def pos_tagger() -> PerceptronTagger:
    with _LOCK:
        return PerceptronTagger(lang="eng")


@lru_cache(maxsize=1)
def lemmatizer() -> WordNetLemmatizer:
    with _LOCK:
        wordnet.ensure_loaded()
        return WordNetLemmatizer()


def resource_error(exc: LookupError) -> AnalysisError:
    return AnalysisError("英文分析资源缺失。请完整复制增量包中的 resources/nltk_data 文件夹后重试。")
