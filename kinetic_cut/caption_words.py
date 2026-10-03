"""Persisted, caption-relative word timing and editable sparse emphasis."""
import re,math

ANIMATIONS = ["none", "pop", "fade", "word reveal", "word highlight", "fade every word", "word highlight 2", "punch", "bounce", "karaoke", "emoji pop", "double emoji"]
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

def set_text(caption,text):
    if text!=caption.text:
        # Preserve timings for case/punctuation-only edits; don't attach old
        # speech onsets to an unrelated replacement sentence.
        old=caption.text.split(); new=text.split()
        if len(old)==len(new) and all(re.sub(r'\W','',a).casefold()==re.sub(r'\W','',b).casefold() for a,b in zip(old,new)):
            for timing,word in zip(caption.word_timings,new):timing['text']=word
        else:caption.word_timings=[]; caption.highlighted_words=[]
        caption.text=text

def shift_origin(caption,delta):
    for word in caption.word_timings:word['start']-=delta; word['end']-=delta
