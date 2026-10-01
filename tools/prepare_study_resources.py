"""从已下载的完整上游 CSV 重建 v0.3 学习资源，应用运行时完全离线。

python tools/prepare_study_resources.py --source-directory 已下载的上游文件目录
目录需要 stardict.csv（官方 stardict.7z 内）、ECDICT_LICENSE.txt 和 awl.pdf。
"""

import argparse
import csv
import hashlib
import json
import re
import shutil
import tempfile
import os
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ECDICT_COMMIT = "bc015ed2e24a7abef49fc6dbbb7fe32c1dadaf8b"
ECDICT_BASE = f"https://raw.githubusercontent.com/skywind3000/ECDICT/{ECDICT_COMMIT}/"
AWL_URL = "https://www.wgtn.ac.nz/lals/resources/academicwordlist/awl-headwords/Headwords-of-the-Academic-Word-List.pdf"


def digest(path: Path) -> str:
    sha = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            sha.update(chunk)
    return sha.hexdigest()


def prepare(source: Path, project: Path = PROJECT_ROOT) -> dict:
    """从 ECDICT BNC 排名派生两份高频词表，从考试标签派生 CET 词表。"""
    import pdfplumber
    required = ("stardict.csv", "ECDICT_LICENSE.txt", "awl.pdf")
    for name in required:
        if not (source / name).is_file():
            raise FileNotFoundError(f"上游资源缺失：{source / name}")
    ranks: dict[str, int] = {}
    cet: set[str] = set()
    count = 0
    selected = 0
    seen: set[str] = set()
    found: set[str] = set()
    required_words = {"the", "one", "people", "time", "library", "prison", "penitentiary",
                      "paralegal", "perpetual", "crucible", "felony"}
    resources = project / "resources"
    dictionary = resources / "dictionary"
    dictionary.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".ecdict-", dir=dictionary)
    temporary_path = Path(temporary)
    try:
        with (source / "stardict.csv").open(encoding="utf-8-sig", newline="") as stream, os.fdopen(descriptor, "w", encoding="utf-8", newline="") as outgoing:
            reader = csv.DictReader(stream)
            if not {"word", "bnc", "tag", "exchange"} <= set(reader.fieldnames or []):
                raise ValueError("ECDICT 缺少 word、bnc、tag 或 exchange 列。")
            writer = csv.DictWriter(outgoing, fieldnames=reader.fieldnames, lineterminator="\n")
            writer.writeheader()
            for row in reader:
                count += 1
                word = row["word"].strip().lower()
                if not re.fullmatch(r"[a-z](?:\.[a-z])+\.?|[a-z]+(?:['’-][a-z]+)*", word):
                    continue
                marked = any(row.get(key) and row[key] != "0" for key in ("collins", "oxford", "tag", "bnc", "frq"))
                derived = re.search(r"(?:^|/)0:", row.get("exchange") or "")
                # 单词分析不使用短语；未标注的自动词形可通过词形还原查主词条。
                if derived and not marked:
                    continue
                writer.writerow(row)
                seen.add(word)
                selected += 1
                if word in required_words:
                    found.add(word)
                if set((row.get("tag") or "").split()) & {"cet4", "cet6"}:
                    cet.add(word)
                try:
                    rank = int(row.get("bnc") or "0")
                except ValueError:
                    continue
                if rank > 0:
                    ranks[word] = min(rank, ranks.get(word, rank))
        if found != required_words:
            raise ValueError("输入词典缺少核对词，请使用完整 stardict.csv，而非精简 ecdict.csv：" + ", ".join(sorted(required_words - found)))
        os.replace(temporary_path, dictionary / "ecdict.csv")
    finally:
        temporary_path.unlink(missing_ok=True)
    ordered = sorted(ranks, key=lambda word: (ranks[word], word))
    if len(ordered) < 3000:
        raise ValueError("BNC 排名不足 3000 个有效词，未生成不完整词表。")
    awl: set[str] = set()
    with pdfplumber.open(source / "awl.pdf") as pdf:
        for page in pdf.pages:
            # 官方 PDF 为“headword + sublist 序号”；大小写筛掉页首的 Sublist 8。
            awl.update(word for word in re.findall(r"\b([A-Za-z]+)\s+(?:10|[1-9])\b", page.extract_text() or "")
                       if word.islower())
    if len(awl) != 570:
        raise ValueError(f"官方 AWL 应有 570 个 headword，本次得到 {len(awl)} 个，暂未写入。")
    wordlists = resources / "wordlists"
    dictionary.mkdir(parents=True, exist_ok=True)
    wordlists.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source / "ECDICT_LICENSE.txt", dictionary / "ECDICT_LICENSE.txt")
    lists = {"top2000.txt": (ordered[:2000], "由 ECDICT 的正值 bnc 排名排序，取前 2000 个不同拼写；不是词族表。"),
             "top3000.txt": (ordered[:3000], "由 ECDICT 的正值 bnc 排名排序，取前 3000 个不同拼写；不是 Oxford 3000。"),
             "awl.txt": (sorted(awl), "Averil Coxhead AWL：570 个词族的 headwords；不是全部派生词。"),
             "cet4_cet6.txt": (sorted(cet), "ECDICT tag 含 cet4 或 cet6 的不同拼写；不是官方最新考试大纲。")}
    for name, (words, note) in lists.items():
        (wordlists / name).write_text("# " + note + "\n" + "\n".join(words) + "\n", encoding="utf-8")
    info = {"prepared_date": date.today().isoformat(), "ecdict_commit": ECDICT_COMMIT,
            "ecdict_url": ECDICT_BASE + "stardict.7z", "upstream_rows": count, "ecdict_rows": selected,
            "ecdict_unique_words": len(seen),
            "upstream_csv_sha256": digest(source / "stardict.csv"),
            "derivation": "保留分析器可识别的单词、连字符词、撇号词和缩写；去除未统计标注的自动派生词；不包含短语条目。保留上游大小写条目顺序，查词时按小写匹配，规范化重复项以后者优先。",
            "ecdict_sha256": digest(dictionary / "ecdict.csv"), "ecdict_license": "MIT（保留上游原许可证）",
            "awl_url": AWL_URL, "awl_original_sha256": digest(source / "awl.pdf"),
            "awl_attribution": "Averil Coxhead, Victoria University of Wellington, Academic Word List (2000)",
            "wordlists": {name: {"words": len(words), "method": note, "sha256": digest(wordlists / name)}
                          for name, (words, note) in lists.items()}}
    (resources / "study_resources.json").write_text(json.dumps(info, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return info


def main() -> None:
    parser = argparse.ArgumentParser(description="从完整上游 CSV 准备离线预习词典与词表")
    parser.add_argument("--source-directory", type=Path, required=True)
    args = parser.parse_args()
    info = prepare(args.source_directory)
    print(json.dumps({"ecdict_rows": info["ecdict_rows"], "wordlists": info["wordlists"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
