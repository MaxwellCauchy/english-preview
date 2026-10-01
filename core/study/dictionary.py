"""用标准库读取 ECDICT，缓存成功加载的 CSV，不在运行中访问网络。"""

import csv
import re
import threading
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "resources" / "dictionary" / "ecdict.csv"
_CACHE: dict[Path, dict[str, dict]] = {}
_ACTIVE: dict[str, dict] | None = None
_LOCK = threading.RLock()


def load_ecdict(path: Path) -> dict[str, dict]:
    """加载并激活一个词典；同一路径第二次加载复用缓存。

    首列须为 word，使用 UTF-8（兼容 BOM）。加载失败不留下半成品缓存。
    """
    global _ACTIVE
    path = Path(path).expanduser().resolve()
    with _LOCK:
        if path in _CACHE:
            _ACTIVE = _CACHE[path]
            return _ACTIVE
        if not path.is_file():
            raise FileNotFoundError(f"离线词典不存在：{path}。请把 ecdict.csv 放入 resources/dictionary/。")
        entries: dict[str, dict] = {}
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as stream:
                reader = csv.DictReader(stream)
                if not reader.fieldnames or reader.fieldnames[0].strip().lower() != "word":
                    raise ValueError("ECDICT CSV 第一列必须为 word。")
                for line, row in enumerate(reader, 2):
                    if None in row:
                        raise ValueError(f"ECDICT 第 {line} 条记录的列数超过表头。")
                    word = (row.get(reader.fieldnames[0]) or "").strip()
                    if word:
                        entries[word.lower()] = {key: value or "" for key, value in row.items()}
        except (UnicodeError, csv.Error) as exc:
            raise ValueError(f"ECDICT 读取失败，请检查 UTF-8 编码和 CSV 格式：{path.name}。") from exc
        except OSError as exc:
            raise OSError(f"无法读取离线词典：{path}。") from exc
        _CACHE[path] = entries
        _ACTIVE = entries
        return entries


def lookup(word: str) -> dict | None:
    """在已激活词典中先查原拼写，再查小写；未加载或未命中返回 None。"""
    with _LOCK:
        if _ACTIVE is None:
            return None
        word = word.strip()
        return _ACTIVE.get(word) or _ACTIVE.get(word.lower())


def entry_fields(entry: dict) -> dict:
    """提取学习用字段，兼容缺失值、转义换行和非标准星级值。"""
    def text(name: str) -> str:
        return str(entry.get(name) or "").replace("\\n", "\n").strip()

    pos = re.split(r"[/;,]", text("pos"))[0].strip()
    try:
        star = max(0, min(5, int(text("collins") or "0")))
    except (ValueError, OverflowError):
        star = 0
    return {"pos": pos, "meaning_cn": text("translation"), "meaning_en": text("definition"),
            "collins_star": star, "oxford_flag": text("oxford").lower() in ("1", "true", "yes")}


def is_loaded() -> bool:
    """是否存在一个成功加载的活动词典。"""
    with _LOCK:
        return _ACTIVE is not None


def clear_cache() -> None:
    """清空模块缓存；供测试及更换词典时使用。"""
    global _ACTIVE
    with _LOCK:
        _CACHE.clear()
        _ACTIVE = None
