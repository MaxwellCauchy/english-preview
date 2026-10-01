"""显式联网下载固定版本 OPUS-MT；日常应用不调用本工具。仅用标准库。"""
import argparse
import hashlib
import json
import os
import tempfile
import urllib.request
from pathlib import Path

MODEL_ID='Helsinki-NLP/opus-mt-en-zh'
REVISION='408d9bc410a388e1d9aef112a2daba955b945255'
ROOT=Path(__file__).resolve().parents[1]
FILES=('config.json','generation_config.json','tokenizer_config.json','source.spm','target.spm','vocab.json','pytorch_model.bin','README.md')

def fetch(url):
    return urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'EnglishPreview/0.4'}),timeout=60)

def verify(path, item):
    if not path.is_file():return False
    if item.get('size') is not None and path.stat().st_size!=item['size']:return False
    lfs=item.get('lfs')
    value=hashlib.sha256() if lfs else hashlib.sha1()
    if not lfs:value.update(f'blob {path.stat().st_size}\0'.encode())
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):value.update(chunk)
    expected=lfs['sha256'] if lfs else item.get('blobId')
    if not expected:raise ValueError('官方元数据没有文件校验值，停止下载。')
    return value.hexdigest()==expected

def download(destination):
    destination=Path(destination).resolve()
    print('正在获取固定版本的模型文件信息……',flush=True)
    with fetch(f'https://huggingface.co/api/models/{MODEL_ID}/revision/{REVISION}?blobs=true') as response:metadata=json.load(response)
    if metadata.get('sha')!=REVISION:raise ValueError('模型版本核验失败。')
    source={item['rfilename']:item for item in metadata['siblings']}
    if any(name not in source for name in FILES):raise ValueError('模型文件清单不完整。')
    destination.mkdir(parents=True,exist_ok=True)
    records=[]
    for name in FILES:
        item=source[name];target=destination/name
        if verify(target,item):print('已核验，跳过：'+name,flush=True)
        else:
            fd, temporary=tempfile.mkstemp(prefix='.download-',dir=destination);temporary=Path(temporary)
            try:
                print('正在下载：'+name,flush=True)
                with os.fdopen(fd,'wb') as output, fetch(f'https://huggingface.co/{MODEL_ID}/resolve/{REVISION}/{name}') as response:
                    done=0;next_report=25*1024*1024
                    while chunk:=response.read(1024*1024):
                        output.write(chunk);done+=len(chunk)
                        if done>=next_report:
                            print(f'{name}：{done//(1024*1024)} MiB',flush=True);next_report+=25*1024*1024
                if not verify(temporary,item):raise ValueError('下载内容校验失败：'+name)
                os.replace(temporary,target)
            finally:temporary.unlink(missing_ok=True)
        records.append({'name':name,'size':target.stat().st_size,'lfs_sha256':(item.get('lfs') or {}).get('sha256'),'git_blob':item.get('blobId')})
    (destination/'download_manifest.json').write_text(json.dumps({'model':MODEL_ID,'revision':REVISION,'license':'Apache-2.0，详见随下载的官方 README.md','files':records},ensure_ascii=False,indent=2))
    print('模型下载并校验完成：'+str(destination),flush=True)

def main():
    parser=argparse.ArgumentParser(description='首次联网准备 OPUS-MT；之后可离线运行')
    parser.add_argument('--destination',type=Path,default=ROOT/'resources/models/opus-mt-en-zh')
    args=parser.parse_args();download(args.destination)

if __name__=='__main__':
    try:main()
    except (OSError,ValueError,KeyError) as exc:
        print('下载未完成：'+str(exc)+'\n检查网络后可重新运行；已校验的文件会跳过。')
        raise SystemExit(1)
