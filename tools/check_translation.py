"""实际本地翻译自测，禁止网络连接，检查缓存命中。"""
import argparse
import json
import socket
import sys
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from core.study.translation import OpusTranslator, DEFAULT_MODEL_DIR

def main():
    parser=argparse.ArgumentParser(description='本地 OPUS-MT 离线与缓存验证')
    parser.add_argument('--model-dir',type=Path,default=DEFAULT_MODEL_DIR)
    parser.add_argument('--output',type=Path,default=ROOT/'output/translation_check.json')
    args=parser.parse_args()
    texts=['We took the unexpected cost into account.',
           'Although the experiment failed, the researchers did not abandon their plan.']
    records=[]
    with patch.object(socket.socket,'connect',side_effect=AssertionError('测试禁止联网')):
        engine=OpusTranslator(args.model_dir)
        for text in texts:
            translated,status=engine.translate(text)
            with patch.object(engine.model,'generate',side_effect=AssertionError('缓存不应重新推理')):
                cached,cached_status=engine.translate(text)
            if not translated or cached!=translated or cached_status!='cached':raise ValueError('缓存验证失败。')
            records.append({'text':text,'translation':translated,'first_status':status,'repeat_status':cached_status})
    data={'model_fingerprint':engine.model_id,'offline_network_guard':'passed','cache':'passed','results':records}
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(data,ensure_ascii=False,indent=2))
    print(json.dumps(data,ensure_ascii=False,indent=2))
if __name__=='__main__':
    try:main()
    except Exception as exc:
        print('自测未通过：'+str(exc));raise SystemExit(1)
