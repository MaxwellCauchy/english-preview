"""离线验证预习层；使用 PDF、UTF-8 正文或已下载的 TED transcript HTML。

TED 模式只保存统计，不输出公开文章的全文或大段摘录。
"""

import argparse
import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.analyzer import analyze_document, load_target_words
from core.models import AnalysisConfig, Document, Paragraph, Section
from core.pdf_reader import read_pdf
from core.study.builder import build_study_list
from core.study.models import StudyConfig
from core.study.render import save_study_list
from core.study.study_words import select_study_words


def main() -> None:
    parser = argparse.ArgumentParser(description="验证离线预习单并输出指标及可选预习文件")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--pdf", type=Path)
    source.add_argument("--article", type=Path)
    source.add_argument("--ted-html", type=Path)
    parser.add_argument("--title", default="")
    parser.add_argument("--targets", type=Path)
    parser.add_argument("--exam", choices=("general", "cet4", "cet6"), default="cet4")
    parser.add_argument("--translate", action="store_true")
    parser.add_argument("--model-dir", type=Path)
    parser.add_argument("--study-words", type=int, default=15)
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "output" / "study_check")
    parser.add_argument("--metrics-only", action="store_true")
    args = parser.parse_args()
    if args.pdf:
        document = read_pdf(args.pdf).document
    elif args.ted_html:
        html = args.ted_html.read_text(encoding="utf-8")
        match = re.search(r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
        if match is None:
            raise ValueError("HTML 中没有 TED transcript 数据。")
        translation = json.loads(match.group(1))["props"]["pageProps"]["transcriptData"]["translation"]
        if translation["language"]["internalLanguageCode"] != "en":
            raise ValueError("请使用英文 transcript。")
        paragraphs = [" ".join(cue["text"] for cue in part["cues"]) for part in translation["paragraphs"]]
        document = Document(title=args.title or "Why I’m building libraries inside prisons",
                            sections=[Section(content=[Paragraph(text) for text in paragraphs])])
    else:
        body = args.article.read_text(encoding="utf-8-sig")
        paragraphs = [text.strip() for text in re.split(r"\n\s*\n", body) if text.strip()]
        document = Document(title=args.title or args.article.stem,
                            sections=[Section(content=[Paragraph(text) for text in paragraphs])])
    targets = load_target_words(args.targets) if args.targets else None
    result = analyze_document(document, AnalysisConfig(target_words=targets))
    study = build_study_list(result, StudyConfig(top_study_words=args.study_words, exam_level=args.exam,
        translate_sentences=args.translate, translation_model_dir=str(args.model_dir) if args.model_dir else ""), document=document)
    pool = select_study_words(result.word_frequencies, StudyConfig(top_study_words=1000, exam_level=args.exam))
    expected = ("penitentiary", "crucible", "felony", "paralegal", "perpetual")
    positions = {item.word: index for index, item in enumerate(pool, 1)}
    info = {"title": study.title, "mode": study.mode, "exam_level":study.exam_level,
            "phrase_count":len(study.study_phrases), "phrases":[p.phrase for p in study.study_phrases],
            "translation_statuses":[s.translation_status for s in study.sentence_breakdowns], "total_words": study.stats.total_words,
            "total_paragraphs": study.stats.total_paragraphs, "total_sentences": study.stats.total_sentences,
            "study_words": [{"word": word.word, "count": word.count, "source": word.source,
                              "has_definition": bool(word.meaning_cn or word.meaning_en)} for word in study.study_words],
            "sentence_breakdowns": len(study.sentence_breakdowns), "key_paragraphs": len(study.key_paragraphs),
            "outline_blocks": len(study.outline.blocks), "action_items": len(study.action_items),
            "expected_word_candidate_ranks": {word: positions.get(word) for word in expected},
            "warnings": study.warnings}
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "verification.json").write_text(json.dumps(info, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not args.metrics_only and not args.ted_html:
        save_study_list(study, args.output / "study.md", "md")
        save_study_list(study, args.output / "study.html", "html")
    print(json.dumps(info, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
