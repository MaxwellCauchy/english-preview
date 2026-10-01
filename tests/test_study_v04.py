"""v0.4 行为验证：等级匹配、变形短语、全文选句、译文状态与模型下载核验。"""
import copy
import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
from core.models import Document, Section, Paragraph, AnalysisConfig, WordFrequency
from core.analyzer import analyze_document
from core.analysis.frequency import prepare
from core.models import SentenceRecord
from core.study.models import StudyConfig, StudyList, SentenceBreakdown, StudyPhrase
from core.study.builder import build_study_list, StudyCancelled
from core.study.exams import load_exam_words
from core.study.study_words import select_study_words
from core.study.phrases import match_phrases, load_phrases, select_phrases
from core.study.translation import translate_study_sentences, TranslationTooLong, TranslationUnavailable, model_fingerprint
from core.study.render import study_list_to_markdown, study_list_to_html

class V04Tests(unittest.TestCase):
    def records(self, text):
        return prepare([SentenceRecord(text,1,1)],AnalysisConfig())

    def test_config_rejects_unknown_exam(self):
        with self.assertRaises(ValueError):StudyConfig(exam_level='tem8')
        with self.assertRaises(ValueError):StudyConfig(max_phrases=0)
        with self.assertRaises(ValueError):StudyConfig(translate_sentences='yes')

    def test_exam_source_and_definitions(self):
        for level in ['cet4','cet6']:
            entries=load_exam_words(level)
            self.assertGreater(len(entries),3000)
            self.assertIn('ECDICT',next(iter(entries.values()))['source'])
            self.assertTrue(any(row['meaning_cn'] for row in entries.values()))

    def test_exam_selection_differs_by_level(self):
        four=load_exam_words('cet4');six=load_exam_words('cet6')
        common=next(w for w in sorted(four.keys()-six.keys()) if len(w)>5)
        advanced=next(w for w in sorted(six.keys()-four.keys()) if len(w)>5)
        items=[WordFrequency(common,common,1),WordFrequency(advanced,advanced,1)]
        config=dict(top_study_words=1,use_wordlists=False)
        a=select_study_words(items,StudyConfig(exam_level='cet4',**config))
        b=select_study_words(items,StudyConfig(exam_level='cet6',**config))
        self.assertEqual(a[0].word,common)
        self.assertIn('四级',a[0].selection_reasons[0])
        self.assertEqual(b[0].word,advanced)
        self.assertIn('cet6',b[0].exam_levels)

    def test_exam_words_do_not_require_large_dictionary(self):
        word=next(w for w in load_exam_words('cet6') if len(w)>6)
        with patch('core.study.dictionary.load_ecdict',side_effect=AssertionError('must not load full CSV')):
            found=select_study_words([WordFrequency(word,word,1)],StudyConfig(exam_level='cet6',use_wordlists=False))
        self.assertTrue(found[0].meaning_cn)

    def test_phrase_verb_inflection_and_original_form(self):
        items=select_phrases(self.records('She carried out the research and gave up the job.'),StudyConfig(exam_level='cet4'))
        self.assertEqual({i.phrase for i in items},{'carry out','give up'})
        self.assertIn('carried out',next(i for i in items if i.phrase=='carry out').forms)

    def test_phrase_inserted_object(self):
        items=select_phrases(self.records('We took the unexpected cost into account.'),StudyConfig(exam_level='cet6'))
        self.assertIn('take into account',{i.phrase for i in items})
        self.assertEqual(items[0].forms,['took the unexpected cost into account'])

    def test_phrase_longest_overlap(self):
        matches=match_phrases(self.records('As a result of the rain, the game ended.')[0],load_phrases(),'cet4')
        self.assertEqual([m.phrase for m in matches],['as a result of'])

    def test_phrase_does_not_cross_punctuation(self):
        self.assertEqual(match_phrases(self.records('We take, into account.')[0],load_phrases(),'cet4'),[])

    def test_phrase_gap_bounded(self):
        matches=match_phrases(self.records('We take the large new and quite unexpected additional financial cost into account.')[0],load_phrases(),'cet4')
        self.assertNotIn('take into account',{m.phrase for m in matches})

    def test_phrase_sentence_pattern(self):
        items=select_phrases(self.records('It was so difficult that we stopped.'),StudyConfig(exam_level='cet4'))
        self.assertIn('so … that',{i.phrase for i in items})
        self.assertTrue(all(not i.exam_levels for i in items))

    def test_phrase_count_two_occurrences(self):
        items=select_phrases(self.records('We depend on you and depend on them.'),StudyConfig(exam_level='cet4'))
        item=next(i for i in items if i.phrase=='depend on')
        self.assertEqual(item.count,2)
        self.assertEqual(item.locations,[1])

    def test_phrase_stage_directions_excluded(self):
        items=select_phrases(self.records('(They give up.)'),StudyConfig(exam_level='cet4'))
        self.assertEqual(items,[])

    def test_missing_phrase_resource_explicit(self):
        with patch('core.study.phrases.PHRASE_PATH',Path('/missing/phrases.json')):
            with self.assertRaises(FileNotFoundError):load_phrases()

    def article(self):
        return Document(title='Research',sections=[Section(content=[
            Paragraph('We took the unexpected cost into account. However, the research contributed to better decisions.'),
            Paragraph('This result is important because it allows researchers to adapt to changes.'),
            Paragraph('The children played a simple game in the garden.')])])

    def test_full_document_selects_short_phrase_sentence(self):
        document=self.article();analysis=analyze_document(document,AnalysisConfig(max_words_per_sentence=25))
        before=copy.deepcopy(analysis)
        self.assertEqual(analysis.long_sentences,[])
        result=build_study_list(analysis,StudyConfig(exam_level='cet4'),document=document)
        self.assertTrue(result.study_phrases)
        self.assertTrue(result.sentence_breakdowns)
        self.assertTrue(any('took' in sentence.text for sentence in result.sentence_breakdowns))
        self.assertEqual(analysis,before)
        self.assertTrue(all(sentence.word_count<25 for sentence in result.sentence_breakdowns))

    def test_sentence_coverage_and_locations(self):
        document=self.article();analysis=analyze_document(document)
        result=build_study_list(analysis,StudyConfig(exam_level='cet6',max_long_sentences=2),document=document)
        self.assertEqual(len(result.sentence_breakdowns),2)
        self.assertTrue(any(sentence.matched_phrases for sentence in result.sentence_breakdowns))
        self.assertTrue(all(sentence.paragraph_index>0 and sentence.sentence_index>0 for sentence in result.sentence_breakdowns))
        self.assertEqual(len({s.text for s in result.sentence_breakdowns}),2)

    def test_missing_full_document_warns(self):
        result=build_study_list(analyze_document(self.article()),StudyConfig(exam_level='cet4'))
        self.assertTrue(any('未提供完整' in w for w in result.warnings))

    def test_missing_exam_resource_warns_without_false_grade(self):
        with patch('core.study.exams.RESOURCE_ROOT',Path('/missing')):
            result=build_study_list(analyze_document(self.article()),StudyConfig(exam_level='cet4'),document=self.article())
        self.assertEqual(result.study_words,[])
        self.assertTrue(any('素材库缺失' in w for w in result.warnings))

    def test_translation_missing_model_preserves_selection(self):
        result=build_study_list(analyze_document(self.article()),StudyConfig(exam_level='cet4',translate_sentences=True,
            translation_model_dir='/missing/model'),document=self.article())
        self.assertTrue(result.study_words or result.study_phrases)
        self.assertTrue(result.sentence_breakdowns)
        self.assertTrue(all(item.translation_status=='unavailable' and not item.translation for item in result.sentence_breakdowns))

    def test_translation_cache_status_and_export(self):
        study=StudyList(exam_level='cet4',sentence_breakdowns=[SentenceBreakdown(text='She carried out research.')])
        engine=MagicMock();engine.translate.return_value=('她开展了研究。','cached')
        translate_study_sentences(study,StudyConfig(),translator=engine)
        self.assertEqual(study.sentence_breakdowns[0].translation_status,'cached')
        self.assertIn('她开展了研究。',study_list_to_markdown(study))
        self.assertIn('她开展了研究。',study_list_to_html(study))

    def test_translation_failures_not_fabricated(self):
        study=StudyList(sentence_breakdowns=[SentenceBreakdown(text='A'),SentenceBreakdown(text='B')])
        engine=MagicMock();engine.translate.side_effect=[TranslationTooLong('too long'),ValueError('failed')]
        translate_study_sentences(study,StudyConfig(),translator=engine)
        self.assertEqual([i.translation_status for i in study.sentence_breakdowns],['too_long','failed'])
        self.assertTrue(all(not i.translation for i in study.sentence_breakdowns))
        self.assertTrue(study.warnings)

    def test_translation_cancellation_propagates(self):
        study=StudyList(sentence_breakdowns=[SentenceBreakdown(text='A')]);engine=MagicMock()
        def cancel(*args):raise StudyCancelled('stop')
        with self.assertRaises(StudyCancelled):translate_study_sentences(study,StudyConfig(),translator=engine,progress_callback=cancel)
        engine.translate.assert_not_called()

    def test_exports_escape_phrase_and_translation(self):
        study=StudyList(exam_level='cet6',study_phrases=[StudyPhrase(phrase='<script>',meaning_cn='<unsafe>')],
            sentence_breakdowns=[SentenceBreakdown(text='A',translation='<script>bad</script>',selection_reasons=['<tag>'])])
        h=study_list_to_html(study);m=study_list_to_markdown(study)
        self.assertNotIn('<script>',h);self.assertIn('&lt;script&gt;',h);self.assertIn('重点短语',m)

    def test_preferences_validate_and_round_trip(self):
        from ui.study_preferences import load_preferences, save_preferences
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'settings.json'
            self.assertEqual(load_preferences(path),{})
            save_preferences({'exam_level':'六级','model_dir':'C:/models','translate_sentences':False},path)
            self.assertEqual(load_preferences(path)['exam_level'],'六级')
            path.write_text('{"exam_level":"专八","translate_sentences":"yes","irrelevant":42}')
            self.assertEqual(load_preferences(path),{})
            path.write_text('broken')
            self.assertEqual(load_preferences(path),{})

    def test_generated_limit_rejected_even_with_forced_eos(self):
        import threading
        from types import SimpleNamespace
        from core.study.translation import OpusTranslator
        with tempfile.TemporaryDirectory() as folder:
            obj=object.__new__(OpusTranslator);obj.model_id='x';obj.cache_path=Path(folder)/'cache.db'
            obj._lock=threading.RLock();obj.limit=3;obj.tokenizer=MagicMock();obj.model=MagicMock();obj.torch=MagicMock()
            obj.tokenizer.supported_language_codes=[];obj.tokenizer.eos_token_id=2
            obj.tokenizer.return_value={'input_ids':SimpleNamespace(shape=(1,2))}
            predicted=MagicMock();predicted.tolist.return_value=[0,7,8,2]
            obj.model.generate.return_value=[predicted]
            with self.assertRaises(TranslationTooLong):obj.translate('English sentence.')
            obj.tokenizer.decode.assert_not_called()

    def test_model_fingerprint_requires_actual_weights(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(TranslationUnavailable):model_fingerprint(Path(folder))

    def test_panel_exam_and_translation_config(self):
        from tests.test_study import StudyTests
        panel=StudyTests().panel_without_display()
        panel.exam_level.get.return_value='六级'
        panel.translation_enabled.get.return_value=True
        panel.model_dir.get.return_value='C:/models/opus'
        config=panel.config()
        self.assertEqual(config.exam_level,'cet6')
        self.assertTrue(config.translate_sentences)
        self.assertEqual(config.translation_model_dir,'C:/models/opus')

    def test_panel_freezes_and_restores_readonly_exam(self):
        from tests.test_study import StudyTests
        panel=StudyTests().panel_without_display()
        panel.option_widgets.append(panel.exam_combo)
        panel.set_state(True,True)
        panel.exam_combo.configure.assert_called_with(state='disabled')
        panel.set_state(True,False)
        panel.exam_combo.configure.assert_called_with(state='readonly')

    def test_panel_phrase_and_translation_details(self):
        from tests.test_study import StudyTests
        panel=StudyTests().panel_without_display()
        panel.study=StudyList(study_phrases=[StudyPhrase(phrase='carry out',meaning_cn='开展',examples=['She carried out research.'])],
            sentence_breakdowns=[SentenceBreakdown(text='She carried out research.',translation='她开展了研究。',translation_status='translated')])
        panel._set_detail=MagicMock()
        panel.phrases.selection.return_value=('0',);panel.sentences.selection.return_value=('0',)
        panel._show_phrase();self.assertIn('开展',panel._set_detail.call_args.args[0])
        panel._show_sentence();self.assertIn('她开展了研究。',panel._set_detail.call_args.args[0])

    def test_worker_passes_full_document_to_study(self):
        import queue, threading
        from ui.main_window import MainWindow
        window=object.__new__(MainWindow);window.events=queue.Queue()
        document=self.article();analysis=analyze_document(document)
        config=StudyConfig(exam_level='cet4')
        with patch('core.study.builder.build_study_list',return_value=StudyList()) as build:
            window._study_worker(document,analysis,AnalysisConfig(),config,threading.Event())
        self.assertIs(build.call_args.kwargs['document'],document)

    def test_sqlite_cache_survives_new_engine_and_separates_models(self):
        import threading
        from types import SimpleNamespace
        from core.study.translation import OpusTranslator
        with tempfile.TemporaryDirectory() as folder:
            def engine(identity):
                obj=object.__new__(OpusTranslator);obj.model_id=identity;obj.cache_path=Path(folder)/'cache.db'
                obj._lock=threading.RLock();obj.limit=512;obj.torch=MagicMock();obj.model=MagicMock();obj.tokenizer=MagicMock()
                obj.tokenizer.supported_language_codes=[];obj.tokenizer.eos_token_id=2
                obj.tokenizer.return_value={'input_ids':SimpleNamespace(shape=(1,3))}
                predicted=MagicMock();predicted.tolist.return_value=[0,3,2];obj.model.generate.return_value=[predicted]
                obj.tokenizer.decode.return_value='中文译文'
                return obj
            first=engine('model-a');self.assertEqual(first.translate('English sentence.'),('中文译文','translated'))
            second=engine('model-a');second.model.generate.side_effect=AssertionError('must use cache')
            self.assertEqual(second.translate('English sentence.'),('中文译文','cached'))
            third=engine('model-b');self.assertEqual(third.translate('English sentence.')[1],'translated')
            third.model.generate.assert_called_once()

    def test_translation_never_silently_truncates(self):
        import threading
        from types import SimpleNamespace
        from core.study.translation import OpusTranslator
        with tempfile.TemporaryDirectory() as folder:
            obj=object.__new__(OpusTranslator);obj.model_id='x';obj.cache_path=Path(folder)/'cache.db'
            obj._lock=threading.RLock();obj.limit=512;obj.tokenizer=MagicMock();obj.model=MagicMock()
            obj.tokenizer.supported_language_codes=[]
            obj.tokenizer.return_value={'input_ids':SimpleNamespace(shape=(1,513))}
            with self.assertRaises(TranslationTooLong):obj.translate('Long sentence.')
            obj.model.generate.assert_not_called()
            self.assertIs(obj.tokenizer.call_args.kwargs['truncation'],False)

    def test_download_git_and_lfs_verification(self):
        file=Path(__file__).resolve().parents[1]/'tools/download_translation_model.py'
        spec=importlib.util.spec_from_file_location('download_model_test',file);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'data';p.write_bytes(b'abc')
            sha=hashlib.sha256(b'abc').hexdigest();blob=hashlib.sha1(b'blob 3\0abc').hexdigest()
            self.assertTrue(module.verify(p,{'size':3,'lfs':{'sha256':sha}}))
            self.assertTrue(module.verify(p,{'size':3,'blobId':blob}))
            self.assertFalse(module.verify(p,{'size':4,'lfs':{'sha256':sha}}))
            self.assertFalse(module.verify(p,{'size':3,'blobId':'wrong'}))

if __name__=='__main__':unittest.main()
