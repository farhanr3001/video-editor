"""Conservative spoken-money formatting and transparent timing review."""
import copy
import math
import re

ONES=dict(zip('zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen'.split(),range(20)))
TENS=dict(zip('twenty thirty forty fifty sixty seventy eighty ninety'.split(),range(20,100,10)))


def number(tokens):
    if not tokens:return None
    if tokens.count('point')==1:
        index=tokens.index('point'); left=number(tokens[:index]); right=tokens[index+1:]
        if left is not None and right and all(t in ONES and ONES[t]<10 for t in right):
            return float(f"{int(left)}."+''.join(str(ONES[t]) for t in right))
        return None
    text=' '.join(tokens).replace(',','')
    if re.fullmatch(r'\d+(?:\.\d+)?',text):return float(text)
    value=0; group=0; last=''
    for token in tokens:
        if token in ONES:
            if last in ONES:return None
            group+=ONES[token]
        elif token in TENS:
            if last in ONES or last in TENS:return None
            group+=TENS[token]
        elif token=='hundred' and 0<group<10:group*=100
        elif token=='and' and group>=100:pass
        else:return None
        last=token
    return float(value+group)


def normalize_words(words):
    """Merge money tokens before caption chunking, retaining their full speech span.

    Only explicit dollars/bucks or K/thousand/million markers qualify; ordinary
    numbers, years, IDs, dates and version strings remain untouched.
    """
    result=[]; index=0
    while index<len(words):
        best=None
        for end in range(index,min(len(words),index+10)):
            raw=[str(w['text']) for w in words[index:end+1]]
            phrase=' '.join(raw).lower().strip(); trailing=''
            if phrase and phrase[-1] in ',.!?':trailing=phrase[-1]; phrase=phrase[:-1]
            phrase=phrase.replace('-',' ')
            currency=phrase.startswith('$')
            if currency:phrase=phrase[1:]
            tokens=phrase.split()
            if tokens and tokens[-1] in ('dollar','dollars','buck','bucks'):
                currency=True; tokens.pop()
            suffix=''
            if tokens and tokens[-1] in ('k','thousand','million','m','billion','b'):
                suffix={'k':'K','thousand':'K','million':'M','m':'M','billion':'B','b':'B'}[tokens.pop()]
            elif tokens:
                compact=re.fullmatch(r'(\d+(?:\.\d+)?)([kmb])',tokens[-1])
                if compact:tokens[-1]=compact[1]; suffix=compact[2].upper()
            if not currency and not suffix:continue
            value=number(tokens)
            if value is None:continue
            # Never combine words separated by a real pause or reversed timing.
            window=words[index:end+1]
            if any(b['start']-a['end']>.65 or b['start']<a['start'] for a,b in zip(window,window[1:])):continue
            if suffix and value>=1000:continue
            text=('$' if currency else '')+f'{value:g}'+suffix+trailing
            merged=copy.deepcopy(window[0]); merged.update(text=text,end=window[-1]['end'])
            if any('confidence' in w for w in window):merged['confidence']=min(w.get('confidence',1) for w in window)
            best=(end,merged)
        if best:index=best[0]+1; result.append(best[1])
        else:result.append(copy.deepcopy(words[index])); index+=1
    return result


def review(project):
    issues=[]
    ordered=sorted(project.captions,key=lambda c:(c.start,c.end))
    for index,caption in enumerate(ordered):
        flags=[]; words=caption.text.split(); timed=caption.word_timings
        if not timed:flags.append('estimated_word_timing')
        elif len(timed)!=len(words):flags.append('word_count_mismatch')
        else:
            previous=-math.inf
            for text,word in zip(words,timed):
                try:
                    a,b=float(word['start']),float(word['end'])
                    if not math.isfinite(a+b) or a<0 or b<=a or b>caption.end-caption.start+.05:flags.append('invalid_word_bounds')
                    if a<previous-.02:flags.append('overlapping_word_timing')
                    if b-a>1.5:flags.append('long_word_alignment')
                    if float(word.get('confidence',1))<.5:flags.append('low_recognition_confidence')
                    if re.sub(r'\W','',text).casefold()!=re.sub(r'\W','',str(word['text'])).casefold():flags.append('word_text_mismatch')
                    previous=b
                except (ValueError,KeyError,TypeError):flags.append('invalid_word_timing')
        if index and caption.start<ordered[index-1].end-.01:flags.append('overlapping_caption')
        if len(words)/max(.01,caption.end-caption.start)>8:flags.append('very_short_reading_time')
        if flags:issues.append(dict(caption_id=caption.id,start=caption.start,end=caption.end,text=caption.text,flags=sorted(set(flags))))
    return dict(captions=len(ordered),issues=issues,
                guidance='Heuristic review, not forced alignment. Replay flagged audio before correcting. Long held words can be intentional.')
