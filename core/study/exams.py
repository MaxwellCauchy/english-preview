"""四六级词典标签派生库；不称为官方考试大纲或真实考频。"""
import csv
from functools import lru_cache
from pathlib import Path

RESOURCE_ROOT = Path(__file__).resolve().parents[2] / "resources" / "exams"
LABELS = {"general": "通用", "cet4": "四级", "cet6": "六级"}

@lru_cache(maxsize=8)
def _load(path: str, stamp: int) -> dict[str, dict]:
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not {"word", "meaning_cn", "source"} <= set(reader.fieldnames or []):
            raise ValueError("四六级词表缺少 word、meaning_cn 或 source 列。")
        return {row["word"].strip().lower(): dict(row) for row in reader if row["word"].strip()}

def load_exam_words(level: str) -> dict[str, dict]:
    if level not in ("cet4", "cet6"):
        if level == "general": return {}
        raise ValueError("只支持四级或六级。")
    path = RESOURCE_ROOT / f"{level}_words.csv"
    if not path.is_file():
        raise FileNotFoundError(f"{LABELS[level]}素材库缺失：{path}")
    return _load(str(path.resolve()), path.stat().st_mtime_ns)

def clear_cache() -> None:
    _load.cache_clear()
