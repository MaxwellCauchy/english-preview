"""用用户持有的 Lexicon Quest PDF 重跑验证；原文件不会被修改。"""

import argparse
import json
import logging
import re
import sys
from collections import Counter
from dataclasses import asdict
from pathlib import Path

import pdfplumber

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.analyzer import analyze_document, load_target_words
from core.analysis.report import save_analysis
from core.analysis.sentence import word_tokens
from core.exporter import save_markdown
from core.models import AnalysisConfig
from core.pdf_reader import read_pdf


def main() -> int:
    parser = argparse.ArgumentParser(description="核对 Lexicon Quest 的读取与双模式分析")
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--output-dir", type=Path, default=ROOT/"output"/"lexicon_check")
    args = parser.parse_args()
    logging.getLogger("pdfminer").setLevel(logging.ERROR)
    out = args.output_dir.resolve(); out.mkdir(parents=True, exist_ok=True)
    conversion = read_pdf(args.pdf, output_dir=out/"work")
    saved = save_markdown(conversion, out/"lexiconquest_read.md")
    automatic = analyze_document(conversion.document)
    assert automatic.mode == "vocabulary", "自动模式未识别 Lexicon Quest"
    assert automatic.vocabulary_progress.total_targets is None, "无清单时不应声称目标总数已知"
    targets = load_target_words(ROOT/"examples/lexicon_check_targets.txt")
    focused = analyze_document(conversion.document, AnalysisConfig(target_words=targets))
    expected = {"abandon": 1, "abandonment": 1, "abasement": 1, "above-mentioned": 1,
                "absent-minded": 1, "adapt": 2, "adhere": 1, "adjacent": 1, "zzmissing": 0}
    assert {w.word: w.count for w in focused.target_words} == expected, "核对词次数变化，请核实是否为同一版 PDF"
    assert focused.vocabulary_progress.seen_targets == 8
    assert focused.vocabulary_progress.total_targets == 9
    bodies = [p.text for section in conversion.document.sections for p in section.paragraphs]
    body = " ".join(bodies)
    assert "\x01" not in body and not re.search(r" {2,}", body)
    assert not any(text.strip() == "&" for text in bodies)
    assert all(word in body for word in ("A.M.", "A.D.", "B.C.", "above-mentioned", "absent-minded"))
    with pdfplumber.open(args.pdf) as pdf:
        raw = " ".join((page.extract_text() or "").replace("\x01", " ") for page in pdf.pages)
    raw_counts = Counter(w.lower() for w in word_tokens(raw))
    extracted_counts = Counter(w.lower() for w in word_tokens(body))
    # 标题本来就不计入正文；其他英文词应逐词完全一致。
    raw_counts.subtract(Counter(w.lower() for w in word_tokens(conversion.document.title)))
    assert +raw_counts == extracted_counts, "正文与文字层的英文词多重集合不一致"
    for entry in focused.target_words:
        assert all(example in body for example in entry.examples)
        assert all(span in body for span in entry.collocations)
    save_analysis(automatic, out/"lexiconquest_candidate_analysis.md")
    save_analysis(focused, out/"lexiconquest_target_check.md")
    save_analysis(focused, out/"lexiconquest_target_check.json")
    verification = {
        "input_name": args.pdf.name, "page_count": conversion.page_count,
        "stats": asdict(automatic.stats), "candidate_count": len(automatic.target_words),
        "long_sentence_count": len(automatic.long_sentences), "checked_counts": expected,
        "check_list_note": "仅 9 个核对词，含 1 个故意未出现的占位词；不是正式 312 词清单。",
        "raw_body_word_multiset_equal": True, "reader_warnings": conversion.warnings,
    }
    (out/"verification.json").write_text(json.dumps(verification, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(f"验证通过：{conversion.page_count} 页；正文 {automatic.stats.total_words} 词；核对清单 8/9 已出现。")
    print(f"测试结果：{out}\n正文：{saved}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
