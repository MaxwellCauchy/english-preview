"""离线规则分析、目标覆盖和读取清洗回归；不依赖用户 PDF。"""

import copy
import json
import math
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from core.analyzer import (
    AnalysisCancelled, AnalysisError, analyze_document, analyze_word_frequency,
    compute_stats, detect_long_sentences, extract_keywords, load_target_words,
    segment_sentences, summarize_paragraphs,
)
from core.analysis.report import analysis_to_json, analysis_to_markdown, save_analysis
from core.analysis.sentence import document_sentences, word_tokens
from core.layout import join_lines, normalize_text
from core.models import (
    AnalysisConfig, Block, Document, ImageNode, ListItem, ListNode, Page, Paragraph,
    Section, SentenceRecord, TableNode,
)
from core.pdf_reader import build_structure, clean_blocks


def document(*paragraphs: str, title: str = "A classroom article") -> Document:
    return Document(title, [Section("Introduction", content=[Paragraph(p, 1) for p in paragraphs])], page_count=1)


class SentenceTests(unittest.TestCase):
    def test_titles_abbreviations_and_dates(self):
        text = "Dr. Smith arrived at 7 A.M. in A.D. 2023. He studied B.C. history."
        self.assertEqual(segment_sentences(text), ["Dr. Smith arrived at 7 A.M. in A.D. 2023.", "He studied B.C. history."])

    def test_examples_and_semicolon_are_not_boundaries(self):
        text = "She likes fruit, e.g. apples; he agrees, i.e. yes. We use tools, etc. for work."
        self.assertEqual(len(segment_sentences(text)), 2)

    def test_decimal_quotes_questions_and_exclamations(self):
        self.assertEqual(segment_sentences('He said, "Measure 3.14 units." Can we proceed? Yes!'),
                         ['He said, "Measure 3.14 units."', 'Can we proceed?', 'Yes!'])

    def test_compounds_and_contractions_are_whole_tokens(self):
        self.assertEqual(word_tokens("A.M. above-mentioned absent-minded can't teacher’s"),
                         ["A.M.", "above-mentioned", "absent-minded", "can't", "teacher’s"])

    def test_empty_noise_and_short_sentence_policy(self):
        self.assertEqual(segment_sentences("\u200b & 1234 !!!"), [])
        self.assertEqual(segment_sentences("Yes. We agree."), ["Yes.", "We agree."])
        self.assertEqual(segment_sentences("Yes. We agree.", min_words=2), ["We agree."])


class ArticleAnalysisTests(unittest.TestCase):
    def test_frequency_locations_and_stopwords(self):
        sentences = [SentenceRecord("The forest grows; forest trees thrive.", 2),
                     SentenceRecord("Also, the forest would grow, she said.", 7)]
        items = {item.word: item for item in analyze_word_frequency(sentences)}
        self.assertEqual(items["forest"].count, 3)
        self.assertEqual(items["forest"].locations, [2, 7])
        for stop in ("the", "also", "would", "said"):
            self.assertNotIn(stop, items)

    def test_pos_aware_lemma_and_derivations(self):
        words = {item.word: item.count for item in analyze_word_frequency(
            ["We are running each morning and run every evening. Abandonment differs from abandon."])}
        self.assertEqual(words["run"], 2)
        self.assertEqual(words["abandonment"], 1)
        self.assertEqual(words["abandon"], 1)

    def test_disable_lemma_and_keep_case(self):
        config = AnalysisConfig(use_lemmatization=False, ignore_case=False)
        words = {item.word for item in analyze_word_frequency(["Apple apple iPhone iphone running run."], config)}
        self.assertTrue({"Apple", "apple", "iPhone", "iphone", "running", "run"} <= words)

    def test_tfidf_formula_and_frequency_filter(self):
        config = AnalysisConfig(use_lemmatization=False, min_frequency=1)
        items = {item.word: item for item in extract_keywords(["Forest forest river.", "Forest mountain."], config)}
        self.assertAlmostEqual(items["forest"].score, (2 / 3 + 1 / 2) / 2)
        self.assertAlmostEqual(items["river"].score, (1 / 3) / 2 * (math.log(3 / 2) + 1))
        self.assertEqual([item.word for item in extract_keywords(["Forest forest river.", "Forest mountain."],
                                                                AnalysisConfig(use_lemmatization=False))], ["forest"])

    def test_stopword_only_and_single_sentence_keywords(self):
        self.assertEqual(extract_keywords(["The and is."]), [])
        self.assertEqual(extract_keywords(["Forest forest."], AnalysisConfig())[0].score, 1.0)

    def test_long_sentences_strict_threshold_and_positions(self):
        doc = document("We study words. We study interesting words every morning.", "We read many books every evening together.")
        items = detect_long_sentences(doc, AnalysisConfig(max_words_per_sentence=3))
        self.assertEqual({(item.paragraph_index, item.sentence_index) for item in items}, {(1, 2), (2, 1)})
        self.assertEqual(items[0].word_count, 7)

    def test_paragraph_first_sentence_and_topics(self):
        summaries = summarize_paragraphs(document("Forests shelter birds. Forests protect soil."))
        self.assertEqual(summaries[0].first_sentence, "Forests shelter birds.")
        self.assertEqual(summaries[0].topic_words[0], "forest")
        self.assertEqual(summaries[0].word_count, 6)

    def test_stats_are_unfiltered_and_zero_safe(self):
        doc = document("The forest is green. The forest grows.")
        stats = compute_stats(doc, document_sentences(doc, AnalysisConfig()))
        self.assertEqual((stats.total_words, stats.total_sentences, stats.total_paragraphs, stats.unique_words), (7, 2, 1, 5))
        self.assertEqual(stats.type_token_ratio, 5 / 7)
        empty = analyze_document(Document())
        self.assertEqual(empty.stats.total_words, 0)
        self.assertEqual(empty.stats.type_token_ratio, 0)
        self.assertEqual(empty.word_frequencies, [])

    def test_only_body_nodes_and_optional_lists(self):
        doc = Document("FOREST", [Section("RIVER", content=[Paragraph("Birds sing."),
            ImageNode("forest.png", "FOREST"), TableNode([["FOREST", "RIVER"]]),
            ListNode(False, [ListItem("River flows.")])])])
        self.assertEqual(analyze_document(doc).stats.total_words, 2)
        self.assertEqual(analyze_document(doc, AnalysisConfig(include_lists=True)).stats.total_words, 4)

    def test_article_map_and_input_immutability(self):
        doc = document("Forests protect soil.")
        config = AnalysisConfig()
        before = copy.deepcopy((doc, config))
        result = analyze_document(doc, config)
        self.assertEqual((doc, config), before)
        self.assertEqual(result.article_map[0].paragraph_indices, [1])
        self.assertEqual(result.article_map[0].word_count, 3)
        self.assertEqual(result.mode, "article")

    def test_cancel_and_progress(self):
        event = threading.Event(); event.set()
        with self.assertRaises(AnalysisCancelled):
            analyze_document(document("A forest grows."), cancel_event=event)
        steps = []
        analyze_document(document("A forest grows."), progress_callback=lambda done, total, msg: steps.append((done, total)))
        self.assertEqual(steps, [(i, 5) for i in range(6)])

    def test_missing_resources_have_human_message(self):
        with patch("core.analysis.sentence.sentence_tokenizer", side_effect=LookupError("missing")):
            with self.assertRaisesRegex(AnalysisError, "resources/nltk_data"):
                segment_sentences("We read books.")

    def test_invalid_config(self):
        for kwargs in ({"mode": "wrong"}, {"min_frequency": 0}, {"prefix_length": 0}, {"top_keywords": -1}):
            with self.assertRaises(ValueError):
                AnalysisConfig(**kwargs)


class VocabularyTests(unittest.TestCase):
    def test_targets_counts_derivations_and_missing_words(self):
        doc = document("Lila decided to abandon her mundane library job. She abandoned a dream.",
                       "Her abandonment surprised everyone; she became absent-minded.", title="Lexicon Quest")
        config = AnalysisConfig(target_words=["abandonment", "abandon", "absent-minded", "abasement"])
        result = analyze_document(doc, config)
        words = {item.word: item for item in result.target_words}
        self.assertEqual(list(words), ["abandon", "abandonment", "abasement", "absent-minded"])
        self.assertEqual(words["abandon"].count, 2)
        self.assertEqual(words["abandonment"].count, 1)
        self.assertEqual(result.vocabulary_progress.total_targets, 4)
        self.assertEqual(result.vocabulary_progress.seen_targets, 3)
        self.assertEqual(result.vocabulary_progress.coverage, .75)
        self.assertEqual(result.vocabulary_progress.missing_words, ["abasement"])

    def test_exact_surface_wins_over_other_target_lemma(self):
        result = analyze_document(document("We are running. We run."), AnalysisConfig(target_words=["run", "running"]))
        self.assertEqual({w.word: w.count for w in result.target_words}, {"run": 1, "running": 1})

    def test_explicit_targets_override_stop_and_length_filters(self):
        result = analyze_document(document("An ad appeared. We read about it."), AnalysisConfig(target_words=["ad", "about"]))
        self.assertEqual({w.word: w.count for w in result.target_words}, {"about": 1, "ad": 1})

    def test_candidates_are_not_claimed_as_formal_targets(self):
        result = analyze_document(document("Abandon the job. Abandonment matters.", title="LexiconQuest"))
        self.assertEqual(result.mode, "vocabulary")
        self.assertIsNone(result.vocabulary_progress.total_targets)
        self.assertIsNone(result.vocabulary_progress.coverage)
        self.assertTrue(result.warnings)
        self.assertIn("abandonment", [w.word for w in result.target_words])

    def test_manual_article_override(self):
        result = analyze_document(document("We study words.", title="Lexicon Quest"), AnalysisConfig(mode="article"))
        self.assertEqual(result.mode, "article")
        self.assertEqual(result.target_words, [])

    def test_examples_and_collocations_are_literal_source_spans(self):
        text = "Lila decided to abandon her mundane library job. She will abandon a dream."
        result = analyze_document(document(text), AnalysisConfig(target_words=["abandon"]))
        entry = result.target_words[0]
        self.assertEqual(entry.count, 2)
        self.assertTrue(all(example in text for example in entry.examples))
        self.assertTrue(all(span in text for span in entry.collocations))
        self.assertIn("abandon a dream", entry.collocations)

    def test_prefix_group_counts_are_distinct_words(self):
        result = analyze_document(document("Abandon abandon academic adjacent."),
                                  AnalysisConfig(target_words=["abandon", "abnormal", "academic", "adjacent"]))
        groups = {g.prefix: g for g in result.prefix_groups}
        self.assertEqual((groups["ab-"].word_count, groups["ab-"].seen_count, groups["ab-"].occurrence_count), (2, 1, 2))

    def test_affix_whitelist_does_not_claim_abroad_is_ab_prefix(self):
        result = analyze_document(document("Abnormal events happen abroad. We adapt and adhere to adjacent customs."),
                                  AnalysisConfig(target_words=["abnormal", "abroad", "adapt", "adhere", "adjacent"]))
        hints = {hint.affix: hint for hint in result.affix_hints}
        self.assertEqual(hints["ab-"].examples, ["abnormal"])
        self.assertNotIn("abroad", hints["ab-"].examples)
        self.assertEqual(hints["ad-"].examples, ["adapt", "adhere", "adjacent"])

    def test_utf8_txt_csv_import_and_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/"targets.txt"
            path.write_text("\ufeff# example\nabandon\nAbandon\nabsent-minded\n", encoding="utf-8")
            self.assertEqual(load_target_words(path), ["abandon", "absent-minded"])
            csv_path = Path(tmp)/"targets.csv"
            csv_path.write_text('word,meaning\nacademic,学术的\nabandon,放弃\n', encoding="utf-8")
            self.assertEqual(load_target_words(csv_path), ["abandon", "academic"])
            path.write_text("abandon a dream", encoding="utf-8")
            with self.assertRaises(ValueError):
                load_target_words(path)
        with self.assertRaises(ValueError):
            analyze_document(document("We read."), AnalysisConfig(target_words=[]))

    def test_report_json_round_trip_and_save(self):
        result = analyze_document(document("Abandon the dream."), AnalysisConfig(target_words=["abandon", "academic"]))
        payload = json.loads(analysis_to_json(result))
        self.assertEqual(payload["vocabulary_progress"]["seen_targets"], 1)
        self.assertIn("目标词清单", analysis_to_markdown(result))
        with tempfile.TemporaryDirectory() as tmp:
            path = save_analysis(result, Path(tmp)/"nested/report.json")
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), payload)


class ReaderCleaningTests(unittest.TestCase):
    def test_control_encoded_spaces_and_invisible_characters(self):
        self.assertEqual(normalize_text("Lexicon\x01Quest\ufeff\u200b  A.M.   above-mentioned\x00"),
                         "Lexicon Quest A.M. above-mentioned")

    def test_image_does_not_interrupt_sentence_merge(self):
        page = Page(1, 600, 800, [Block("Lila decided to", 50, 100, 550, 110),
            Block("", 250, 111, 300, 112, kind="image", image_path="assets/test.png"),
            Block("abandon her job.", 50, 114, 400, 124)])
        cleaned = clean_blocks([page])[0]
        self.assertEqual(cleaned.blocks[0].text, "Lila decided to abandon her job.")
        self.assertEqual(cleaned.blocks[-1].kind, "image")

    def test_trailing_noise_but_internal_ampersand_preserved(self):
        page = Page(1, 600, 800, [Block("R&D and A & B remain. &\u200b", 50, 100, 550, 110)])
        self.assertEqual(clean_blocks([page])[0].blocks[0].text, "R&D and A & B remain.")
        page.blocks.append(Block("&", 50, 500, 60, 510))
        page.blocks.append(Block("（注：说明）", 50, 520, 160, 530))
        self.assertNotIn("&", [b.text for b in clean_blocks([page])[0].blocks])

    def test_cross_page_lowercase_continuation_skips_image(self):
        pages = [Page(1, 600, 800, [Block("She listened with", 50, 710, 550, 730),
                  Block("", 50, 740, 100, 770, kind="image", image_path="a.png")]),
                 Page(2, 600, 800, [Block("a curious mind.", 50, 40, 550, 60)])]
        doc = build_structure(pages)
        self.assertEqual(doc.sections[0].paragraphs[0].text, "She listened with a curious mind.")
        self.assertEqual(len(doc.sections[0].paragraphs), 1)
        self.assertEqual(len(doc.sections[0].images), 1)

    def test_known_compounds_preserved_across_line_break(self):
        self.assertEqual(join_lines("above-", "mentioned"), "above-mentioned")
        self.assertEqual(join_lines("absent-", "minded"), "absent-minded")


class CLIAnalysisTests(unittest.TestCase):
    def test_cli_reads_and_saves_independent_json_analysis(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run([sys.executable, str(root/"main.py"), str(root/"tests/sample.pdf"),
                "--no-images", "-o", str(Path(tmp)/"body.md"), "--analysis-output", str(Path(tmp)/"report.json")],
                capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((Path(tmp)/"body.md").is_file())
            self.assertGreater(json.loads((Path(tmp)/"report.json").read_text())["stats"]["total_words"], 0)


if __name__ == "__main__":
    unittest.main()
