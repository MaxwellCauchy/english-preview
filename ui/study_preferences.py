"""只保存用户选择，不保存文章正文；无效或缺失配置使用默认值。"""
import json
import os
import tempfile
from pathlib import Path
DEFAULT_PATH=Path(__file__).resolve().parents[1]/'output/study_preferences.json'

def load_preferences(path: Path = DEFAULT_PATH) -> dict:
    try:
        value=json.loads(Path(path).read_text(encoding='utf-8'))
        if not isinstance(value,dict):return {}
        return {key:val for key,val in value.items() if
            (key=='exam_level' and val in ('四级','六级')) or
            (key=='model_dir' and isinstance(val,str)) or
            (key=='translate_sentences' and type(val) is bool)}
    except (OSError,ValueError):return {}

def save_preferences(value: dict, path: Path = DEFAULT_PATH) -> None:
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    fd,temporary=tempfile.mkstemp(prefix='.preferences-',dir=path.parent);temporary=Path(temporary)
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as stream:
            json.dump(value,stream,ensure_ascii=False,indent=2)
            stream.flush();os.fsync(stream.fileno())
        os.replace(temporary,path)
    finally:temporary.unlink(missing_ok=True)
