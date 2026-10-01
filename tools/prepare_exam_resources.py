"""从本地 ECDICT 重建四六级标签词表。短语素材单独人工维护。"""
import argparse
import csv
import hashlib
import json
import re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SOURCE='ECDICT bc015ed2e24a7abef49fc6dbbb7fe32c1dadaf8b tag '

def prepare(dictionary: Path, destination: Path) -> dict:
    words={'cet4':{},'cet6':{}}
    with dictionary.open(encoding='utf-8-sig',newline='') as stream:
        reader=csv.DictReader(stream)
        if not {'word','tag','translation'}<=set(reader.fieldnames or []):raise ValueError('词典缺少 word、tag 或 translation 字段。')
        for row in reader:
            word=row['word'].strip().lower()
            if not re.fullmatch(r"[a-z](?:\.[a-z])+\.?|[a-z]+(?:['’-][a-z]+)*",word):continue
            for level in set(row.get('tag','').split()) & words.keys():
                words[level][word]=dict(word=word,meaning_cn=row.get('translation','').replace('\\n','\n'),
                    meaning_en=row.get('definition','').replace('\\n','\n'),pos=row.get('pos',''),
                    collins_star=row.get('collins','0'),oxford_flag=row.get('oxford','0'),source=SOURCE+level)
    if not all(words.values()):raise ValueError('输入词典没有完整四六级标签，未写入。')
    destination.mkdir(parents=True,exist_ok=True)
    info={}
    for level,entries in words.items():
        path=destination/f'{level}_words.csv'
        with path.open('w',encoding='utf-8',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=['word','meaning_cn','meaning_en','pos','collins_star','oxford_flag','source'],lineterminator='\n')
            writer.writeheader();writer.writerows(entries.values())
        info[level]={'records':len(entries),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'meaning':'词典历史考试标签，不是最新官方大纲，未使用或声称真题考频'}
    metadata_path=destination/'sources.json'
    metadata=json.loads(metadata_path.read_text()) if metadata_path.exists() else {}
    metadata.update(version='0.4',dictionary_source='https://github.com/skywind3000/ECDICT',
        commit='bc015ed2e24a7abef49fc6dbbb7fe32c1dadaf8b',
        license='MIT；保留 resources/dictionary/ECDICT_LICENSE.txt',wordlists=info)
    metadata_path.write_text(json.dumps(metadata,ensure_ascii=False,indent=2))
    return info

def main():
    parser=argparse.ArgumentParser(description='从已有 ECDICT 派生四六级素材')
    parser.add_argument('--dictionary',type=Path,default=ROOT/'resources/dictionary/ecdict.csv')
    parser.add_argument('--destination',type=Path,default=ROOT/'resources/exams')
    args=parser.parse_args();print(json.dumps(prepare(args.dictionary,args.destination),ensure_ascii=False,indent=2))
if __name__=='__main__':main()
