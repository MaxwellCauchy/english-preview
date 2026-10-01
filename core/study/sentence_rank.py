"""重点句排序：词语覆盖、句法线索、逻辑作用；标签均为规则候选。"""
import re
from ..analysis.frequency import PreparedSentence
from ..models import LongSentence
from .models import StudyConfig, StudyWord, StudyPhrase, SentenceBreakdown
from .main_structure import extract_main_structure
from .phrases import match_phrases, load_phrases

def select_sentences(prepared: list[PreparedSentence], words: list[StudyWord], phrases: list[StudyPhrase],
                     config: StudyConfig, keywords: set[str] | None = None) -> list[SentenceBreakdown]:
    wordset = {word.word.lower() for word in words if word.count > 0}
    phraseset = {phrase.phrase for phrase in phrases}
    try: entries = load_phrases()
    except (OSError, ValueError): entries=()
    candidates=[]; seen=set(); previous={}
    keywords=keywords or set()
    for sentence in prepared:
        record=sentence.record; text=record.text.strip(); count=len(sentence.tokens)
        before=previous.get(record.paragraph_index,"")
        previous[record.paragraph_index]=text
        if count < 3 or (config.exclude_stage_directions and re.fullmatch(r"\(.*\)",text,re.S)): continue
        norm=" ".join(text.lower().split())
        if norm in seen: continue
        seen.add(norm)
        terms=set(sentence.lemmas) | {t.lower() for t in sentence.tokens}
        hits=sorted(terms & wordset)
        phits=sorted({match.phrase for match in match_phrases(sentence,entries,config.exam_level)} & phraseset)
        reasons=[]; structure=[]
        if hits: reasons.append("覆盖重点词："+"、".join(hits))
        if phits: reasons.append("覆盖重点短语："+"、".join(phits))
        lower=text.lower()
        if re.search(r"\b(which|who|whose|although|because|unless|whether|whereas)\b",lower): structure.append("从句连接线索")
        finite=sum(tag in ('VBD','VBP','VBZ','MD') for tag in sentence.tags)
        if finite>=2: structure.append("多个谓语线索")
        if any(tag in ('VBG','VBN') for tag in sentence.tags): structure.append("分词线索，需核对是否为非谓语")
        if re.search(r"\b(not only|only then|never before|had .* not)\b",lower): structure.append("强调／倒装线索")
        if structure: reasons.extend(structure)
        logic=bool(re.search(r"\b(however|therefore|consequently|nevertheless|in conclusion|as a result|in contrast)\b",lower))
        if logic: reasons.append("转折／因果／总结连接线索")
        topic=bool(terms & keywords)
        if topic: reasons.append("覆盖文章关键词")
        long=count>=config.min_sentence_words
        if long: reasons.append("句长辅助指标")
        if not (hits or phits or structure or logic or topic or long): continue
        score=4*len(hits)+6*len(phits)+min(4,len(structure)*1.5)+logic*3+topic*2+min(count,40)/20
        # 不让极长的列举句单靠长度占优。
        if count>70: score-=3
        candidates.append((sentence,hits,phits,reasons,score,before))
    result=[];covered_words=set();covered_phrases=set();paragraphs=set()
    while candidates and len(result)<config.max_long_sentences:
        def priority(item):
            sentence,hits,phits,_,score,_=item
            return (score+3*len(set(hits)-covered_words)+4*len(set(phits)-covered_phrases)
                    +(2 if sentence.record.paragraph_index not in paragraphs else 0),
                    -sentence.record.paragraph_index,-sentence.record.sentence_index)
        item=max(candidates,key=priority);candidates.remove(item)
        sentence,hits,phits,reasons,score,before=item;record=sentence.record
        output=extract_main_structure(LongSentence(record.text,len(sentence.tokens),record.paragraph_index,
            record.sentence_index,record.page_number),config)
        output.matched_words=hits;output.matched_phrases=phits;output.selection_reasons=reasons
        output.score=round(score,3);output.page_number=record.page_number
        if re.match(r"^(this|that|these|those|it|they|such)\b",record.text,re.I): output.context_before=before
        result.append(output);covered_words.update(hits);covered_phrases.update(phits);paragraphs.add(record.paragraph_index)
    return result
