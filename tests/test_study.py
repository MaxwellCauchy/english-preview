"""预习层回归：构造分析结果、隔离词典缓存，不依赖真实 PDF。"""

import copy
import csv
import queue
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from types import SimpleNamespace

from core.models import AnalysisResult, LongSentence, ParagraphSummary, SectionOverview, WordFrequency
from core.study import dictionary, wordlist
from core.study.builder import StudyCancelled, build_study_list
from core.study.main_structure import extract_main_structure
from core.study.models import StudyConfig, StudyList, StudyWord
from core.study.outline import build_outline
from core.study.paragraph_rank import rank_paragraphs
from core.study.render import save_study_list, study_list_to_html, study_list_to_markdown
from core.study.study_words import select_study_words
from tests.fixtures import make_study_analysis


class StudyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.folder = Path(self.temporary.name)
        dictionary.clear_cache()
        wordlist.clear_cache()
        self.wordlist_patch = patch.object(wordlist, "WORDLIST_ROOT", self.folder)
        self.wordlist_patch.start()
        (self.folder / "top2000.txt").write_text("# test list\none\nget\npeople\ntime\n", encoding="utf-8")
        self.config = StudyConfig(use_dictionary=False)

    def tearDown(self):
        self.wordlist_patch.stop()
        dictionary.clear_cache()
        wordlist.clear_cache()
        self.temporary.cleanup()

    def small_dictionary(self, name="ecdict.csv"):
        path = self.folder / name
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=["word", "definition", "translation", "pos", "collins", "oxford"])
            writer.writeheader()
            writer.writerows([{"word": "Crucible", "definition": "a severe test", "translation": "严峻考验\\n坩埚", "pos": "n./v.", "collins": "2", "oxford": "1"},
                              {"word": "felony", "translation": "重罪", "collins": "0"}])
        return path

    def test_study_config_validation(self):
        for name in ("top_study_words", "max_long_sentences", "max_key_paragraphs", "min_sentence_words", "min_paragraph_words"):
            for value in (0, -1, 1001, True, 1.5):
                with self.subTest(name=name, value=value), self.assertRaises(ValueError):
                    StudyConfig(**{name: value})
        with self.assertRaises(ValueError):
            StudyConfig(use_dictionary="yes")

    def test_all_model_defaults_are_independent(self):
        first, second = StudyList(), StudyList()
        first.study_words.append(StudyWord())
        first.stats.total_words = 10
        self.assertFalse(second.study_words)
        self.assertEqual(second.stats.total_words, 0)

    def test_ecdict_load_missing_file(self):
        with self.assertRaisesRegex(FileNotFoundError, "离线词典不存在"):
            dictionary.load_ecdict(self.folder / "missing.csv")

    def test_ecdict_lookup(self):
        dictionary.load_ecdict(self.small_dictionary())
        self.assertIsNotNone(dictionary.lookup("CRUCIBLE"))
        self.assertIsNone(dictionary.lookup("zzmissing"))
        fields = dictionary.entry_fields(dictionary.lookup("crucible"))
        self.assertEqual(fields["meaning_cn"], "严峻考验\n坩埚")
        self.assertEqual(fields["pos"], "n.")
        self.assertTrue(fields["oxford_flag"])
        self.assertEqual(fields["collins_star"], 2)

    def test_ecdict_caches_by_path(self):
        path = self.small_dictionary()
        first = dictionary.load_ecdict(path)
        self.assertIs(first, dictionary.load_ecdict(path))
        other = self.folder / "other.csv"
        other.write_text("word,translation\nreliable,可靠\n", encoding="utf-8")
        dictionary.load_ecdict(other)
        self.assertIsNone(dictionary.lookup("crucible"))
        dictionary.load_ecdict(path)
        self.assertIsNotNone(dictionary.lookup("crucible"))

    def test_ecdict_invalid_header_and_encoding(self):
        path = self.folder / "bad.csv"
        for content in (b"name,translation\nword,text\n", b"word,translation\nabc,\xff\n"):
            path.write_bytes(content)
            with self.assertRaises(ValueError):
                dictionary.load_ecdict(path)
            self.assertFalse(dictionary.is_loaded())

    def test_entry_fields_defaults(self):
        fields = dictionary.entry_fields({"collins": "bad", "oxford": "0"})
        self.assertEqual(fields["meaning_cn"], "")
        self.assertEqual(fields["collins_star"], 0)
        self.assertFalse(fields["oxford_flag"])

    def test_wordlist_load(self):
        path = self.folder / "custom.txt"
        path.write_text("\ufeff# comment\n Reliable\n\nCRUCIBLE\nreliable\n", encoding="utf-8")
        self.assertEqual(wordlist.load_wordlist(path), frozenset({"reliable", "crucible"}))
        self.assertEqual(wordlist.load_wordlist(self.folder / "absent.txt"), frozenset())

    def test_wordlist_named_loaders_and_clear(self):
        for name, loader in (("top3000.txt", wordlist.load_top3000), ("awl.txt", wordlist.load_awl), ("cet4_cet6.txt", wordlist.load_cet)):
            path = self.folder / name
            path.write_text("Reliable\n", encoding="utf-8")
            self.assertEqual(loader(), frozenset({"reliable"}))
            path.write_text("Crucible\n", encoding="utf-8")
            self.assertEqual(loader(), frozenset({"reliable"}))
            wordlist.clear_cache()
            self.assertEqual(loader(), frozenset({"crucible"}))

    def test_is_basic_word(self):
        self.assertTrue(wordlist.is_basic_word("ONE"))
        self.assertTrue(wordlist.is_basic_word("an", use_top2000=False))
        self.assertFalse(wordlist.is_basic_word("one", use_top2000=False))
        self.assertFalse(wordlist.is_basic_word("penitentiary"))

    def test_select_study_words_excludes_basic(self):
        words = [WordFrequency("people", "people", 9), WordFrequency("12345", "12345", 8),
                 WordFrequency("the", "the", 7), WordFrequency("get", "get", 6)]
        self.assertEqual(select_study_words(words, self.config), [])

    def test_select_study_words_keeps_advanced(self):
        result = make_study_analysis()
        original = copy.deepcopy(result.word_frequencies)
        words = select_study_words(result.word_frequencies, self.config)
        self.assertEqual([item.word for item in words], ["penitentiary", "crucible", "felony"])
        self.assertEqual(result.word_frequencies, original)
        self.assertTrue(all(item.source == "candidate" for item in words))

    def test_contractions_of_stopwords_are_excluded(self):
        self.assertTrue(wordlist.is_stopword("that's"))
        self.assertTrue(wordlist.is_stopword("we’ve"))
        self.assertFalse(wordlist.is_stopword("father's"))

    def test_proper_names_do_not_fill_article_word_slots(self):
        words = select_study_words([WordFrequency("mango", "Mango", 9, "NNP", [1]),
                                    WordFrequency("crucible", "crucible", 1, "NN", [1])], self.config)
        self.assertEqual([word.word for word in words], ["crucible"])

    def test_builder_excludes_words_only_in_stage_directions(self):
        result = make_study_analysis()
        result.word_frequencies.append(WordFrequency("applause", "Applause", 20, "NN", [3]))
        words = build_study_list(result, self.config).study_words
        self.assertNotIn("applause", [word.word for word in words])
        included = build_study_list(result, StudyConfig(use_dictionary=False, exclude_stage_directions=False)).study_words
        self.assertIn("applause", [word.word for word in included])

    def test_study_words_dictionary_score(self):
        dictionary.load_ecdict(self.small_dictionary())
        words = select_study_words([WordFrequency("felony", "felony", 5), WordFrequency("crucible", "crucible", 2)], StudyConfig(top_study_words=1))
        self.assertEqual(words[0].word, "crucible")
        self.assertEqual(words[0].source, "ecdict")

    def test_study_words_missing_dictionary_degrades(self):
        with patch.object(dictionary, "DEFAULT_PATH", self.folder / "missing.csv"):
            words = select_study_words([WordFrequency("penitentiary", "penitentiary", 1)], StudyConfig())
        self.assertEqual(words[0].source, "candidate")

    def test_extract_main_structure_basic(self):
        sentence = LongSentence("Students read complex books in the old library because they need reliable information.", 16, 2, 3)
        result = extract_main_structure(sentence, self.config)
        self.assertEqual(result.main_clause, "Students read complex books")
        self.assertEqual((result.paragraph_index, result.sentence_index), (2, 3))
        self.assertTrue(any("介词短语" in item for item in result.modifiers))
        self.assertTrue(any("状语从句" in item for item in result.modifiers))

    def test_extract_main_structure_failure_fallback(self):
        with patch("core.study.main_structure.pos_tagger", side_effect=RuntimeError("missing")):
            result = extract_main_structure(LongSentence("One two three four five six seven eight nine.", 9, 1, 1), self.config)
        self.assertEqual(result.main_clause, "One two three four five six seven eight...")
        self.assertEqual(result.modifiers, [])
        self.assertIn("人工判断", result.note)

    def test_extract_main_structure_preserves_negation(self):
        result = extract_main_structure(LongSentence("The plan was not approved.", 5, 1, 1), self.config)
        self.assertIn("not", result.main_clause)
        self.assertIn("approved", result.main_clause)

    def test_rank_paragraphs_skips_stage_directions(self):
        result = make_study_analysis()
        result.paragraph_summaries[2].word_count = 10
        ranked = rank_paragraphs(result, self.config)
        self.assertNotIn(3, [item.index for item in ranked])

    def test_rank_paragraphs_skips_short(self):
        ranked = rank_paragraphs(make_study_analysis(), StudyConfig(use_dictionary=False, min_paragraph_words=15))
        self.assertEqual([item.index for item in ranked], [1])

    def test_rank_paragraphs_keyword_weight_and_input_unchanged(self):
        result = make_study_analysis()
        result.paragraph_summaries[0].word_count = 15
        result.paragraph_summaries[1].word_count = 12
        before = copy.deepcopy(result)
        ranked = rank_paragraphs(result, self.config)
        self.assertEqual(ranked[0].index, 2)
        self.assertEqual(ranked[0].reason, "关键词密集")
        self.assertEqual(ranked[0].score, 18)
        self.assertEqual(result, before)

    def test_build_outline_empty(self):
        self.assertEqual(build_outline(AnalysisResult(), self.config).blocks, [])

    def test_build_outline_by_ratio(self):
        for size in (5, 6, 10, 21):
            result = AnalysisResult(paragraph_summaries=[ParagraphSummary(index, f"Paragraph {index}.", [], 10) for index in range(1, size + 1)])
            outline = build_outline(result, self.config)
            self.assertEqual(len(outline.blocks), 5)
            covered = [number for block in outline.blocks for number in range(block.paragraph_range[0], block.paragraph_range[1] + 1)]
            self.assertEqual(covered, list(range(1, size + 1)))
            self.assertEqual(sum(block.word_count for block in outline.blocks), size * 10)

    def test_build_outline_short_document_is_single_block(self):
        result = make_study_analysis()
        result.article_map = [SectionOverview("First", 2, [1], 10), SectionOverview("Second", 2, [2, 3], 10)]
        self.assertEqual(len(build_outline(result, self.config).blocks), 1)

    def test_build_outline_uses_headings(self):
        result = AnalysisResult(paragraph_summaries=[ParagraphSummary(i, str(i), [], 10) for i in range(1, 7)],
                                article_map=[SectionOverview("First", 2, [1, 2, 3], 30), SectionOverview("", 2, [4, 5, 6], 30)])
        outline = build_outline(result, self.config)
        self.assertEqual([block.title for block in outline.blocks], ["First", "第 2 部分"])
        self.assertEqual(outline.blocks[1].paragraph_range, (4, 6))

    def test_build_study_list_article_mode(self):
        result = make_study_analysis()
        before = copy.deepcopy(result)
        study = build_study_list(result, self.config)
        self.assertEqual(len(study.study_words), 3)
        self.assertEqual(len(study.sentence_breakdowns), 1)
        self.assertEqual(len(study.action_items), 6)
        self.assertEqual(result, before)
        study.stats.total_words = 0
        study.study_words[0].locations.append(99)
        self.assertEqual(result, before)

    def test_build_study_list_vocabulary_mode(self):
        study = build_study_list(make_study_analysis("vocabulary"), self.config)
        self.assertEqual(study.mode, "vocabulary")
        self.assertIn("one", [item.word for item in study.study_words])
        self.assertEqual(next(item for item in study.study_words if item.word == "one").collocations, ["one person"])

    def test_build_study_list_empty_document(self):
        study = build_study_list(AnalysisResult())
        self.assertEqual(study.study_words, [])
        self.assertEqual(study.action_items, [])
        self.assertEqual(study.overview, "")

    def test_builder_failure_does_not_abort_other_steps(self):
        with patch("core.study.builder.select_study_words", side_effect=RuntimeError("test failure")):
            study = build_study_list(make_study_analysis(), self.config)
        self.assertEqual(study.study_words, [])
        self.assertTrue(study.key_paragraphs)
        self.assertTrue(any("test failure" in warning for warning in study.warnings))

    def test_builder_progress_and_cancel(self):
        steps = []
        build_study_list(make_study_analysis(), self.config, progress_callback=lambda done, total, message: steps.append((done, total)))
        self.assertEqual(steps, [(i, 6) for i in range(7)])
        def cancel(done, total, message):
            if done == 1:
                raise StudyCancelled("cancel")
        with self.assertRaises(StudyCancelled):
            build_study_list(make_study_analysis(), self.config, progress_callback=cancel)

    def test_builder_threshold_and_limits(self):
        result = make_study_analysis()
        study = build_study_list(result, StudyConfig(use_dictionary=False, top_study_words=1, max_key_paragraphs=1, min_sentence_words=100))
        self.assertEqual(len(study.study_words), 1)
        self.assertEqual(len(study.key_paragraphs), 1)
        self.assertFalse(study.sentence_breakdowns)

    def test_study_list_to_markdown(self):
        text = study_list_to_markdown(build_study_list(make_study_analysis(), self.config))
        for heading in ("文章速览", "必学词", "长难句", "关键段", "文章结构", "行动清单"):
            self.assertIn("## " + heading, text)
        self.assertIn("- [ ]", text)

    def test_study_list_to_html(self):
        text = study_list_to_html(build_study_list(make_study_analysis(), self.config))
        self.assertIn('<meta charset="utf-8">', text)
        self.assertIn("<style>", text)
        self.assertNotIn("{{title}}", text)
        self.assertNotIn('<link ', text)
        self.assertNotIn('<script', text)

    def test_html_escapes_user_content_and_replaces_once(self):
        study = StudyList(title="<script>alert(1)</script>{{overview}}", overview="<b>text</b>")
        html = study_list_to_html(study)
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertIn("{{overview}}", html)
        self.assertIn("&lt;b&gt;text&lt;/b&gt;", html)

    def test_save_study_list_md(self):
        study = build_study_list(make_study_analysis(), self.config)
        path = save_study_list(study, self.folder / "nested" / "preview", "md")
        self.assertEqual(path.suffix, ".md")
        self.assertEqual(path.read_text(encoding="utf-8"), study_list_to_markdown(study))

    def test_save_study_list_html(self):
        path = save_study_list(StudyList(title="测试"), self.folder / "preview.md", "html")
        self.assertEqual(path.suffix, ".html")
        self.assertIn("测试", path.read_text(encoding="utf-8"))

    def test_atomic_save_failure_preserves_old_file(self):
        path = self.folder / "preview.md"
        path.write_text("old content", encoding="utf-8")
        with patch("core.study.render.os.replace", side_effect=OSError("test write failure")), self.assertRaises(OSError):
            save_study_list(StudyList(), path)
        self.assertEqual(path.read_text(), "old content")
        self.assertEqual(list(self.folder.glob(".study-*")), [])

    def test_save_rejects_invalid_format(self):
        with self.assertRaises(ValueError):
            save_study_list(StudyList(), self.folder / "preview", "pdf")

    def test_worker_reuses_cached_analysis(self):
        from ui.main_window import MainWindow
        from core.models import AnalysisConfig, Document
        window = object.__new__(MainWindow)
        window.events = queue.Queue()
        result = make_study_analysis()
        with patch("core.analyzer.analyze_document") as analyze:
            window._study_worker(Document(), result, AnalysisConfig(), self.config, threading.Event())
        analyze.assert_not_called()
        events = list(window.events.queue)
        self.assertEqual(events[-1][0], "study_done")
        self.assertIs(events[-1][1][0], result)

    def test_worker_cancels_before_analysis(self):
        from ui.main_window import MainWindow
        from core.models import AnalysisConfig, Document
        window = object.__new__(MainWindow)
        window.events = queue.Queue()
        cancelled = threading.Event()
        cancelled.set()
        with patch("core.analyzer.analyze_document") as analyze:
            window._study_worker(Document(), None, AnalysisConfig(), self.config, cancelled)
        analyze.assert_not_called()
        self.assertEqual(window.events.get_nowait()[0], "cancelled")

    def panel_without_display(self):
        from ui.study_panel import StudyPanel
        panel = object.__new__(StudyPanel)
        panel.study = None
        panel.preferences_path = None
        for name in ("top_words", "max_sentences", "max_paragraphs", "overview", "warnings",
                     "build_button", "copy_button", "md_button", "html_button", "words", "sentences",
                     "paragraphs", "outline", "actions", "detail", "canvas", "_on_status",
                     "phrases", "exam_combo", "exam_level", "max_phrases", "translation_enabled", "model_dir"):
            setattr(panel, name, MagicMock())
        panel.exam_level.get.return_value = "通用"
        panel.max_phrases.get.return_value = "12"
        panel.translation_enabled.get.return_value = False
        panel.model_dir.get.return_value = ""
        panel.top_words.get.return_value = "15"
        panel.max_sentences.get.return_value = "5"
        panel.max_paragraphs.get.return_value = "8"
        panel.option_widgets = [MagicMock(), MagicMock(), MagicMock()]
        panel.action_vars = []
        panel.actions.winfo_children.return_value = []
        panel.words.get_children.return_value = ()
        panel.sentences.get_children.return_value = ()
        panel.copy_button.instate.return_value = False
        panel.md_button.instate.return_value = False
        panel.winfo_toplevel = MagicMock()
        panel.clipboard_clear = MagicMock()
        panel.clipboard_append = MagicMock()
        return panel

    def test_panel_config_validation_without_display(self):
        panel = self.panel_without_display()
        self.assertEqual(panel.config().top_study_words, 15)
        panel.top_words.get.return_value = "bad"
        with self.assertRaises(ValueError):
            panel.config()

    def test_panel_buttons_follow_ready_and_busy(self):
        panel = self.panel_without_display()
        panel.study = StudyList()
        panel.set_state(True, True)
        panel.build_button.configure.assert_called_with(state="disabled")
        panel.md_button.configure.assert_called_with(state="disabled")
        panel.set_state(True, False)
        panel.build_button.configure.assert_called_with(state="normal")
        panel.html_button.configure.assert_called_with(state="normal")

    def test_panel_show_and_clear_without_display(self):
        panel = self.panel_without_display()
        study = build_study_list(make_study_analysis(), self.config)
        with patch("ui.study_panel.tk.BooleanVar"), patch("ui.study_panel.ttk.Checkbutton"):
            panel.show_study_list(study)
        self.assertIs(panel.study, study)
        self.assertEqual(panel.words.insert.call_count, len(study.study_words))
        self.assertEqual(panel.sentences.insert.call_count, len(study.sentence_breakdowns))
        self.assertEqual(len(panel.action_vars), 6)
        panel.clear()
        self.assertIsNone(panel.study)
        self.assertEqual(panel.action_vars, [])
        panel.copy_button.configure.assert_called_with(state="disabled")

    def test_panel_copy_complete_report_without_display(self):
        panel = self.panel_without_display()
        panel.study = build_study_list(make_study_analysis(), self.config)
        panel.copy()
        panel.clipboard_clear.assert_called_once()
        self.assertEqual(panel.clipboard_append.call_args.args[0], study_list_to_markdown(panel.study))

    def test_panel_save_cancel_does_not_write(self):
        panel = self.panel_without_display()
        panel.study = StudyList()
        with patch("ui.study_panel.filedialog.asksaveasfilename", return_value=""), patch("ui.study_panel.save_study_list") as save:
            panel.save()
        save.assert_not_called()

    def test_panel_saves_both_formats_without_display(self):
        panel = self.panel_without_display()
        panel.study = build_study_list(make_study_analysis(), self.config)
        for fmt in ("md", "html"):
            path = self.folder / ("panel." + fmt)
            with patch("ui.study_panel.filedialog.asksaveasfilename", return_value=str(path)):
                panel.save(fmt)
            self.assertTrue(path.is_file())

    def main_window_without_display(self):
        from ui.main_window import MainWindow
        from core.models import AnalysisConfig, Document
        window = object.__new__(MainWindow)
        window.busy = False
        window.result = SimpleNamespace(document=Document())
        window.analysis_result = make_study_analysis()
        window._analysis_config_at_result = AnalysisConfig()
        window.study_panel = MagicMock()
        window.study_panel.config.return_value = self.config
        window.analysis_panel = MagicMock()
        window.analysis_panel.config.return_value = AnalysisConfig()
        window.progress = MagicMock()
        window.status = MagicMock()
        window._set_busy = MagicMock()
        return window

    def test_build_study_reuses_unchanged_config(self):
        window = self.main_window_without_display()
        with patch("ui.main_window.threading.Thread") as thread:
            window.build_study()
        self.assertIs(thread.call_args.kwargs["args"][1], window.analysis_result)
        thread.return_value.start.assert_called_once()

    def test_build_study_invalidates_changed_targets(self):
        from core.models import AnalysisConfig
        window = self.main_window_without_display()
        window.analysis_panel.config.return_value = AnalysisConfig(target_words=["crucible"])
        with patch("ui.main_window.threading.Thread") as thread:
            window.build_study()
        self.assertIsNone(thread.call_args.kwargs["args"][1])

    def test_poll_discards_result_after_late_cancellation(self):
        window = self.main_window_without_display()
        window.closed = False
        window.events = queue.Queue()
        window.events.put(("study_done", None))
        window.cancel_event = threading.Event()
        window.cancel_event.set()
        window.root = MagicMock()
        window._poll()
        window.study_panel.show_study_list.assert_not_called()
        window._set_busy.assert_called_once_with(False)
        window.status.set.assert_called_with("已取消本次处理。")


if __name__ == "__main__":
    unittest.main()
