"""Persisted, caption-relative word timing and editable sparse emphasis."""
import re,math

ANIMATIONS = ["none", "pop", "fade", "word reveal", "word highlight", "fade every word", "word highlight 2", "punch", "bounce", "karaoke", "emoji pop", "double emoji", "smart highlight"]
STOP_WORDS=set("a an the this that these those i you he she it we they my your his her our their is are was were be been being am to of in on at for from with as by and or but so if then than not do does did have has had can could will would should just very really oh uh um hey there here what how who when where why".split())

def timings(caption):
    words=caption.text.split(); stored=caption.word_timings
    try:
        if len(stored)==len(words) and all(str(t.get('text','')).casefold()==w.casefold() for t,w in zip(stored,words)):
            result=[(caption.start+float(t['start']),caption.start+float(t['end'])) for t in stored]
            if all(math.isfinite(a) and math.isfinite(b) and b>=a for a,b in result):return result
    except (KeyError,TypeError,ValueError,AttributeError):pass
    duration=max(.01,caption.end-caption.start)
    return [(caption.start+duration*i/max(1,len(words)),caption.start+duration*(i+1)/max(1,len(words))) for i in range(len(words))]

def active_word(caption,time):
    return next((i for i,(start,end) in enumerate(timings(caption)) if start<=time<end),None)

def remove_periods(text):
    # Preserve decimal points, URLs and internal abbreviation punctuation.
    return re.sub(r'(?<=\w)\.+(?=[\"\u201d\u2019\)\]]*(?:\s|$))','',text)

def prepare_generated(captions,style,strip_periods=False,censor=False):
    from .profanity import censor_text
    last_emphasis=-10.
    for caption in captions:
        if censor:caption.text=censor_text(caption.text)
        if strip_periods:caption.text=remove_periods(caption.text)
        for word,text in zip(caption.word_timings,caption.text.split()):word['text']=text
        if style.animation!='word highlight 2' or len(caption.text.split())<2:continue
        candidates=[]
        for index,word in enumerate(caption.text.split()):
            clean=re.sub(r'[^\w]','',word).casefold()
            if clean and clean not in STOP_WORDS and (len(clean)>=4 or any(c.isdigit() for c in clean)):
                score=min(len(clean),10)+(4 if any(c.isdigit() for c in clean) else 0)+(2 if '!' in word else 0)
                candidates.append((score,index))
        if candidates and caption.start-last_emphasis>=1.5:
            caption.highlighted_words=[max(candidates,key=lambda pair:(pair[0],-pair[1]))[1]]; last_emphasis=caption.start
    if style.animation=='smart highlight':
        from .caption_emphasis import mark_strong_words
        mark_strong_words(captions)

def retime(old_text,old_timings,new_text):
    """Word timings for edited text. Unchanged words keep their measured timing; new or replaced
    words are spread over the span the old words occupied (flagged estimated)."""
    import difflib
    old=old_text.split(); new=new_text.split()
    if not new or not old_timings or len(old_timings)!=len(old):return []
    norm=lambda w:re.sub(r'\W','',w).casefold()
    try:
        spans=[(float(t['start']),float(t['end'])) for t in old_timings]
    except (KeyError,TypeError,ValueError):return []
    result=[None]*len(new)
    for tag,i1,i2,j1,j2 in difflib.SequenceMatcher(a=[norm(w) for w in old],b=[norm(w) for w in new],autojunk=False).get_opcodes():
        if tag=='equal':
            for k in range(j2-j1):
                t=dict(old_timings[i1+k]);t['text']=new[j1+k];result[j1+k]=t
            continue
        if j1==j2:continue
        if i1==i2:lo=spans[i1-1][1] if i1>0 else spans[0][0];hi=spans[i1][0] if i1<len(spans) else spans[-1][1]
        else:lo,hi=spans[i1][0],spans[i2-1][1]
        hi=max(hi,lo+.06*(j2-j1)); weights=[max(1,len(norm(w))) for w in new[j1:j2]]; total=sum(weights); cursor=lo
        for k,weight in enumerate(weights):
            end=cursor+(hi-lo)*weight/total
            result[j1+k]=dict(text=new[j1+k],start=round(cursor,3),end=round(end,3),estimated=True); cursor=end
    return result

def set_text(caption,text):
    if text!=caption.text:
        timings_=retime(caption.text,caption.word_timings,text)
        if len(timings_)==len(text.split()) and timings_:caption.word_timings=timings_
        else:caption.word_timings=[]
        old_words,new_words=caption.text.split(),text.split(); clean=lambda w:re.sub(r'\W','',w).casefold()
        caption.highlighted_words=[i for i in caption.highlighted_words if i<len(old_words) and i<len(new_words) and clean(old_words[i])==clean(new_words[i])]
        caption.text=text

def shift_origin(caption,delta):
    for word in caption.word_timings:word['start']-=delta; word['end']-=delta
