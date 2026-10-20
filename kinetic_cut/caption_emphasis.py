"""Static, sparse emphasis for one-word cards, independent of speech hold padding."""
from .caption_emojis import clean_token,find_emoji_for_word,emojis_for_caption
from .caption_words import STOP_WORDS

_PLAIN=STOP_WORDS|set('okay ok wait happened happens happen got get going went said say says thing things something anything everything actually literally always never next another because about right like'.split())

def single_word_emphasized(project,caption):
    if caption.highlighted_words:return 0 in caption.highlighted_words
    if emojis_for_caption(project,caption):return True
    word=clean_token(caption.text)
    if word in _PLAIN or not (find_emoji_for_word(word) or len(word)>=7 or word.isdigit()):return False
    singles=[c for c in sorted(project.captions,key=lambda c:(c.start,c.end,c.id)) if len(c.text.split())==1]
    chosen=[]
    for c in singles:
        token=clean_token(c.text)
        important=token not in _PLAIN and (find_emoji_for_word(token) or len(token)>=7 or token.isdigit())
        if important and (not chosen or c.start-chosen[-1].start>=.8):chosen.append(c)
    return any(c.id==caption.id for c in chosen) if singles else True


def measure_emphasis(captions,audio,offset=0.,sample_rate=16000,cancel_check=None):
    """Presentation metadata only: relative vocal energy, never word-clock edits.

    A local reference makes a quiet microphone and a loud microphone comparable.
    Short 20ms windows avoid rewarding a long word merely for lasting longer.
    This runs in the owned transcription process, not the GUI or painter.
    """
    import numpy as np
    from .caption_words import timings
    from .captions import _check_cancel
    hop=max(1,round(sample_rate*.02)); samples=np.asarray(audio,dtype=np.float32)
    frames=len(samples)//hop
    if not frames:return
    energy=10*np.log10(np.maximum(np.mean(samples[:frames*hop].reshape(-1,hop)**2,axis=1),1e-10))
    for caption in captions:
        _check_cancel(cancel_check)
        for word,(start,end) in zip(caption.word_timings,timings(caption)):
            a=max(0,int((start-offset)*sample_rate/hop));b=min(frames,int((end-offset)*sample_rate/hop)+1)
            if b<=a:continue
            local=energy[max(0,a-150):min(frames,b+150)]
            voiced=local[local>max(-65.,float(np.max(local))-25.)]
            if not len(voiced):continue
            delta=float(np.percentile(energy[a:b],75)-np.median(voiced))
            word['emphasis_db']=round(max(-20.,min(20.,delta)),3)


def mark_strong_words(captions):
    """A sparse transcript plan, independent of how words are split into cards.

    Relative vocal accents, meaningful intensifiers and phrase endings contribute;
    function words and routine connective speech remain plain. Existing metadata
    is persisted with captions and never recomputed in the rendering hot path.
    Applying the style to older captions uses the conservative text fallback.
    """
    import math,re
    from .caption_words import timings
    strong=set('amazing incredible unbelievable insane crazy brilliant terrible horrible perfect worst best greatest impossible absolutely definitely never always love hate furious disaster victory winner genius ridiculous powerful beautiful awesome hilarious most least top bottom million billion'.split())
    plain=_PLAIN|set('chat man guys gonna wanna thats its im ive dont didnt cant hes shes wouldve couldve'.split())
    modifiers=set('most least best worst very absolutely completely truly incredibly'.split())
    records=[]
    for c in sorted(captions,key=lambda c:(c.start,c.end,c.id)):
        c.highlighted_words=[]
        for index,(raw,(a,b)) in enumerate(zip(c.text.split(),timings(c))):
            clean=clean_token(raw)
            metadata=c.word_timings[index] if index<len(c.word_timings) else {}
            try:db=float(metadata.get('emphasis_db',0.))
            except (TypeError,ValueError):db=0.
            if not math.isfinite(db):db=0.
            records.append(dict(c=c,index=index,raw=raw,word=clean,start=a,end=b,db=db))
    candidates=[]
    for n,r in enumerate(records):
        word=r['word']; raw=r['raw']
        # Tier/grade letters after "a" are meaningful even in one-word cards.
        grade=word in {'s','a','b','c','d','f'} and n>0 and records[n-1]['word'] in {'a','say','tier','rank','grade'}
        if not word or (word in STOP_WORDS and word not in strong and not grade):continue
        if word in plain and word not in strong and not grade and r['db']<5.:continue
        numeric=any(char.isdigit() for char in word)
        if len(word)<3 and not numeric and not grade:continue
        boundary=n==len(records)-1 or bool(re.search(r'[.!?][\"\u201d\u2019]*$',raw)) or records[n+1]['start']-r['end']>.4
        score=(2.6 if word in strong else .25)+(2.3 if numeric or grade else 0.)
        score+=min(3.,max(0.,r['db']-1.5)*.55)
        if boundary:score+=.65
        if '!' in raw:score+=.7
        if score<2.25:continue
        members=[n]
        if n+1<len(records) and word in modifiers:
            following=records[n+1]
            if following['word'] not in plain and following['start']-r['end']<.25 and not re.search(r'[.!?]$',raw):members.append(n+1)
        elif n and records[n-1]['word'] in modifiers and r['start']-records[n-1]['end']<.25:
            members.insert(0,n-1)
        candidates.append((score,n,members))
    chosen=[];budget=max(2,math.ceil(len(records)*.24));used=0
    for score,n,members in sorted(candidates,key=lambda v:(-v[0],v[1])):
        start=records[members[0]]['start'];end=records[members[-1]]['end']
        if used+len(members)>budget:continue
        if any(start<other_end+1.25 and end>other_start-1.25 for other_start,other_end in chosen):continue
        for index in members:
            r=records[index];r['c'].highlighted_words.append(r['index'])
        chosen.append((start,end));used+=len(members)
