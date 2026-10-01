"""离线预习层：消费 AnalysisResult，不修改读取或分析结果。"""

from .builder import StudyCancelled, build_study_list
from .models import StudyConfig, StudyList, StudyPhrase
from .phrases import select_phrases
from .translation import translate_study_sentences
from .render import save_study_list, study_list_to_html, study_list_to_markdown

__all__ = ["StudyCancelled", "StudyConfig", "StudyList", "build_study_list",
           "save_study_list", "study_list_to_html", "study_list_to_markdown",
           "StudyPhrase", "select_phrases", "translate_study_sentences"]
