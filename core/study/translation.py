"""OPUS-MT 本地翻译。运行时只读本地模型，SQLite 缓存按模型及输入隔离。"""
import hashlib
import json
import os
import sqlite3
import threading
from pathlib import Path
from typing import Callable
from .models import StudyConfig, StudyList

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODEL_DIR = PROJECT_ROOT / "resources" / "models" / "opus-mt-en-zh"
DEFAULT_CACHE = PROJECT_ROOT / "output" / "translation_cache.sqlite3"
_LOCK = threading.RLock()
_ENGINES = {}

class TranslationUnavailable(Exception):
    """资源或依赖未准备好；不阻塞其他预习内容。"""

class TranslationTooLong(Exception):
    """原句超过模型长度，不静默截断。"""

def model_fingerprint(folder: Path) -> str:
    folder = Path(folder).resolve()
    files = [folder/name for name in ('config.json','source.spm','target.spm','vocab.json')]
    weights = folder/'model.safetensors'
    if not weights.is_file(): weights=folder/'pytorch_model.bin'
    files.append(weights)
    if any(not p.is_file() for p in files):
        raise TranslationUnavailable("OPUS-MT 模型尚未安装完整。请先运行 tools/download_translation_model.py。")
    identity=hashlib.sha256()
    for p in files:
        identity.update(p.name.encode())
        with p.open('rb') as stream:
            for chunk in iter(lambda:stream.read(1024*1024),b''): identity.update(chunk)
    return identity.hexdigest()

class OpusTranslator:
    def __init__(self, model_dir: Path = DEFAULT_MODEL_DIR, cache_path: Path = DEFAULT_CACHE):
        self.model_dir=Path(model_dir).expanduser().resolve()
        self.cache_path=Path(cache_path)
        self.model_id=model_fingerprint(self.model_dir)
        try:
            import torch
            from transformers import MarianMTModel, MarianTokenizer
        except ImportError as exc:
            raise TranslationUnavailable("未安装翻译依赖，请运行 py -m pip install -r requirements-translation.txt。") from exc
        torch.set_num_threads(max(1, min(4, os.cpu_count() or 1)))
        self.torch=torch
        # 不使用 pipeline、远程仓库 ID 或自定义模型代码。
        self.tokenizer=MarianTokenizer.from_pretrained(str(self.model_dir),local_files_only=True)
        self.model=MarianMTModel.from_pretrained(str(self.model_dir),local_files_only=True)
        self.model.to('cpu');self.model.eval()
        self.limit=int(self.model.config.max_position_embeddings)
        self._lock=threading.RLock()

    def _key(self, text: str) -> str:
        return hashlib.sha256((self.model_id+'\0cmn_Hans\0beam4\0'+text).encode()).hexdigest()

    def translate(self, text: str) -> tuple[str, str]:
        if not text.strip(): raise ValueError("待译句子为空。")
        key=self._key(text)
        self.cache_path.parent.mkdir(parents=True,exist_ok=True)
        with self._lock:
            with sqlite3.connect(self.cache_path,timeout=10) as db:
                db.execute('CREATE TABLE IF NOT EXISTS translations (key TEXT PRIMARY KEY, translation TEXT NOT NULL)')
                row=db.execute('SELECT translation FROM translations WHERE key=?',(key,)).fetchone()
                if row:return row[0],'cached'
            token='>>cmn_Hans<<'
            source=(token+' '+text) if token in (getattr(self.tokenizer,'supported_language_codes',None) or []) else text
            encoded=self.tokenizer(source,return_tensors='pt',truncation=False)
            if encoded['input_ids'].shape[-1]>self.limit:
                raise TranslationTooLong(f"原句超过模型 {self.limit} token 上限，未截断；请人工拆句后翻译。")
            with self.torch.inference_mode():
                predicted=self.model.generate(**encoded,num_beams=4,max_new_tokens=self.limit,early_stopping=True)
            ids=predicted[0].tolist()
            if len(ids) >= self.limit + 1 or ids[-1] != self.tokenizer.eos_token_id:
                raise TranslationTooLong("译文达到生成上限，未保存不完整译文。")
            translation=self.tokenizer.decode(ids,skip_special_tokens=True).strip()
            if not translation:raise ValueError("模型返回空译文。")
            with sqlite3.connect(self.cache_path,timeout=10) as db:
                db.execute('INSERT OR REPLACE INTO translations VALUES (?,?)',(key,translation))
            return translation,'translated'

def get_translator(model_dir: Path) -> OpusTranslator:
    folder=Path(model_dir).resolve()
    # 资源被替换时重建；模型指纹由构造器核验，避免错误复用译文。
    stamp=tuple((p.name,p.stat().st_size,p.stat().st_mtime_ns) for p in sorted(folder.iterdir()) if p.is_file()) if folder.is_dir() else ()
    with _LOCK:
        key=(str(folder),stamp)
        if key not in _ENGINES:
            engine=OpusTranslator(folder)
            _ENGINES.clear();_ENGINES[key]=engine
        return _ENGINES[key]

def translate_study_sentences(study: StudyList, config: StudyConfig, *,
        progress_callback: Callable[[int,int,str],None] | None = None, translator=None) -> None:
    """只翻译选中的完整原句，不伪造译文；回调异常传播以保留取消。"""
    items=study.sentence_breakdowns
    if not items:return
    callback=progress_callback or (lambda done,total,message:None)
    callback(0,len(items),'正在准备离线翻译')
    try:
        engine=translator or get_translator(Path(config.translation_model_dir) if config.translation_model_dir else DEFAULT_MODEL_DIR)
    except Exception as exc:
        message=f"离线翻译不可用：{exc}"
        study.warnings.append(message)
        for item in items:item.translation='';item.translation_status='unavailable';item.translation_note=message
        return
    for index,item in enumerate(items,1):
        callback(index-1,len(items),'正在翻译重点句')
        item.translation = ''
        try:
            item.translation,item.translation_status=engine.translate(item.text)
            item.translation_note='OPUS-MT 参考译文；逐句翻译，前文仅供阅读核对，未参与模型输入。'
        except TranslationTooLong as exc:
            item.translation_status='too_long';item.translation_note=str(exc)
        except Exception as exc:
            item.translation_status='failed';item.translation_note=f'翻译失败：{exc}'
        callback(index,len(items),'重点句翻译完成')
    failed=sum(item.translation_status not in ('translated','cached') for item in items)
    if failed:study.warnings.append(f'{failed} 个重点句未取得完整译文，请查看各句状态；可以重新生成重试。')
