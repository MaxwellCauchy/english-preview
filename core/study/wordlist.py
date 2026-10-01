"""项目内的 UTF-8 词表；缺失资源降级为空集合。"""

import threading
from pathlib import Path

from ..analysis.runtime import stop_words

WORDLIST_ROOT = Path(__file__).resolve().parents[2] / "resources" / "wordlists"
_CACHE: dict[Path, frozenset[str]] = {}
_LOCK = threading.RLock()


def load_wordlist(path: Path) -> frozenset[str]:
    """每行一个词，忽略空行及 # 注释；成功读取后按路径缓存。"""
    path = Path(path).expanduser().resolve()
    with _LOCK:
        if path in _CACHE:
            return _CACHE[path]
        if not path.is_file():
            return frozenset()
        with path.open(encoding="utf-8-sig") as stream:
            words = frozenset(line.strip().lower() for line in stream
                              if line.strip() and not line.lstrip().startswith("#"))
        _CACHE[path] = words
        return words


def load_top2000() -> frozenset[str]:
    """加载前 2000 高频词。"""
    return load_wordlist(WORDLIST_ROOT / "top2000.txt")


def load_top3000() -> frozenset[str]:
    """加载前 3000 高频词。"""
    return load_wordlist(WORDLIST_ROOT / "top3000.txt")


def load_awl() -> frozenset[str]:
    """加载 Academic Word List 词族的 headwords。"""
    return load_wordlist(WORDLIST_ROOT / "awl.txt")


def load_cet() -> frozenset[str]:
    """加载 ECDICT 标注的 CET4/CET6 词汇。"""
    return load_wordlist(WORDLIST_ROOT / "cet4_cet6.txt")


def is_basic_word(word: str, *, use_top2000: bool = True) -> bool:
    """短于三字符，或启用的 top2000 中包含该词时视为基础词。"""
    lower = word.lower()
    return len(lower) < 3 or (use_top2000 and lower in load_top2000())


def is_stopword(word: str) -> bool:
    """复用停用词；that's/we've 等缩合形式同时核对撇号前的功能词。"""
    lower = word.lower().replace("’", "'")
    ignored = stop_words()
    return lower in ignored or ("'" in lower and lower.split("'", 1)[0] in ignored)


def clear_cache() -> None:
    """清空词表缓存，供测试或资源替换后调用。"""
    with _LOCK:
        _CACHE.clear()
