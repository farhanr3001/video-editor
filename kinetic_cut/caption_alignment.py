"""Bounded CTC forced alignment for English; never changes recognized text.

Uses the existing ONNX Runtime, not PyTorch. Whisper remains the recognizer.
Unsupported tokens retain their recognizer timing and low-confidence repairs
are exposed to caption review, rather than silently dropping words.
"""
import json
import re
from pathlib import Path

SAMPLE_RATE=16000


def ctc_spans(logits,tokens,blank,cancel_check=None):
    """Viterbi CTC alignment, including repeat-letter blank transitions."""
    import numpy as np
    from .captions import _check_cancel
    if not tokens:return []
    if len(tokens)>2048 or len(logits)>2500:return None
    scores=logits-logits.max(axis=1,keepdims=True)
    scores-=np.log(np.exp(scores).sum(axis=1,keepdims=True))
    labels=np.full(len(tokens)*2+1,blank,np.int64);labels[1::2]=tokens
    previous=np.full(len(labels),-np.inf,np.float32);previous[0]=0
    trace=np.zeros((len(scores),len(labels)),np.uint8)
    skip=np.zeros(len(labels),bool);skip[2:]=(labels[2:]!=blank)&(labels[2:]!=labels[:-2])
    columns=np.arange(len(labels))
    for frame,row in enumerate(scores):
        if frame%64==0:_check_cancel(cancel_check)
        choices=np.stack((previous,np.r_[-np.inf,previous[:-1]],np.r_[-np.inf,-np.inf,previous[:-2]]))
        choices[2,~skip]=-np.inf
        step=choices.argmax(axis=0);trace[frame]=step
        previous=choices[step,columns]+row[labels]
    state=len(labels)-1 if previous[-1]>previous[-2] else len(labels)-2
    if not np.isfinite(previous[state]):return None
    spans=[None]*len(tokens)
    for frame in range(len(scores)-1,-1,-1):
        if state%2:
            index=state//2
            if spans[index] is None:spans[index]=[frame,frame+1]
            else:spans[index][0]=frame
        state-=int(trace[frame,state])
    return spans


class WordAligner:
    def __init__(self,root=None):
        import onnxruntime as ort
        from .icons import resource_path
        root=Path(root) if root else resource_path('assets','caption-alignment')
        self.vocab=json.loads((root/'vocab.json').read_text(encoding='utf-8'))
        options=ort.SessionOptions();options.intra_op_num_threads=2;options.inter_op_num_threads=1
        self.session=ort.InferenceSession(str(root/'model.onnx'),sess_options=options,providers=['CPUExecutionProvider'])

    def align(self,audio,words,start,end,cancel_check=None):
        import numpy as np
        from .captions import _check_cancel
        _check_cancel(cancel_check)
        start=max(0.,start-.3);end=min(len(audio)/SAMPLE_RATE,end+.3)
        # Bounded windows keep memory/cancellation latency independent of VOD length.
        if end-start>32 or not words:return False
        clip=audio[round(start*SAMPLE_RATE):round(end*SAMPLE_RATE)]
        if len(clip)<400:return False
        if float(clip.var())<1e-10:return False
        clip=(clip-clip.mean())/np.sqrt(clip.var()+1e-7)
        logits=self.session.run(None,{'input_values':clip[None].astype(np.float32)})[0][0]
        _check_cancel(cancel_check)
        tokens=[];owners=[]
        for index,word in enumerate(words):
            # Numbers/currency have multiple spoken forms. Do not invent a
            # pronunciation; retain Whisper's real timestamp for those tokens.
            original=word['text'].strip()
            if any(c.isdigit() for c in original):continue
            text=re.sub("[^A-Z']",'',original.upper())
            if not text:continue
            if tokens:tokens.append(self.vocab['|']);owners.append(-1)
            tokens.extend(self.vocab[c] for c in text);owners.extend([index]*len(text))
        spans=ctc_spans(logits,tokens,self.vocab['<pad>'],cancel_check)
        if spans is None:return False
        step=len(clip)/SAMPLE_RATE/len(logits)
        bounds={};evidence={}
        probabilities=np.exp(logits-logits.max(axis=1,keepdims=True));probabilities/=probabilities.sum(axis=1,keepdims=True)
        for owner,span,token in zip(owners,spans,tokens):
            if owner<0 or span is None:continue
            a,b=span
            if owner not in bounds:bounds[owner]=[a,b]
            else:bounds[owner][1]=b
            evidence.setdefault(owner,[]).append(float(probabilities[a:b,token].max()))
        for index,(a,b) in bounds.items():
            # A forced path exists even for wrong text or silence. Reject weak
            # acoustic evidence instead of confidently moving it elsewhere.
            if np.mean(evidence[index])<.08:continue
            # CTC character emissions are narrow; retain a small phonetic tail.
            proposed=max(start,start+a*step-.02)
            if words[index]['end']>words[index]['start'] and abs(proposed-words[index]['start'])>.8:continue
            words[index]['start']=proposed
            words[index]['end']=min(end,start+b*step+.04)
        return bool(bounds)


def preserve_fillers(words,speech):
    """Sustained vowels in um/uh can be almost entirely CTC blank emissions."""
    for index,word in enumerate(words):
        if not re.fullmatch(r'[uU]+[mhMH]+[.!?,…]*|[eE]+[rmRM]+[.!?,…]*',word['text'].strip()):continue
        original=word.get('_recognizer_start',word['start'])
        candidates=[(a,b) for a,b in speech if a<=word['end'] and b>=original]
        if not candidates:continue
        a,b=min(candidates,key=lambda span:abs(span[0]-original))
        left=words[index-1]['end'] if index else a
        right=words[index+1]['start'] if index+1<len(words) else b
        word['start']=max(a,left,min(original,word['start']))
        word['end']=max(word['end'],min(b,right))


def refine_speech_edges(audio,words,speech):
    """Repair silent leads/clipped tails only at isolated acoustic boundaries.

    CTC can be all blank on a short word. VAD alone is too late for initial
    fricatives, so use energy around its boundary when quiet context confirms
    the onset/tail. Never stretch across another recognized word or a pause.
    This is caption presentation recovery, not exact audio-edit evidence.
    """
    import numpy as np
    if not words:return
    for a,b in speech:
        candidates=[(i,w) for i,w in enumerate(words) if w['start']<b and w['end']>a]
        if not candidates:continue
        left=max(0,round((a-.2)*SAMPLE_RATE));right=min(len(audio),round((b+.12)*SAMPLE_RATE))
        clip=audio[left:right];step=160
        if len(clip)<step:continue
        levels=np.sqrt(np.mean(clip[:len(clip)//step*step].reshape(-1,step)**2,axis=1))
        peak=float(levels.max());floor=float(np.quantile(levels,.1))
        if peak<1e-5 or floor>peak*.08:continue  # Background sound obscures the boundary.
        active=np.flatnonzero(levels>max(1e-5,peak*.02,floor*3))
        if not len(active):continue
        first,last=candidates[0],candidates[-1]
        onset=(left+int(active[0])*step)/SAMPLE_RATE
        tail=(left+(int(active[-1])+1)*step)/SAMPLE_RATE
        i,w=first
        if active[0]>0 and onset-.35<=w['start']<onset-.02 and w['end']>onset:
            w['start']=max(words[i-1]['end'] if i else 0,onset-.01)
        i,w=last
        next_start=words[i+1]['start'] if i+1<len(words) else float('inf')
        if active[-1]<len(levels)-1 and 0<tail-w['end']<=.45 and next_start>=tail:
            w['end']=tail


def usable_words(words,start,end,require_exact=False):
    """Preserve collapsed recognized tokens, but never call interpolation exact."""
    from .captions import CaptionBackendError
    # Resolve only boundary overlaps. Never delete a token because DTW collapsed it.
    for index,word in enumerate(words):
        if word['end']<=word['start']:
            if require_exact:raise CaptionBackendError('A recognized word has no reliable timing. Audio was not changed.')
            left=words[index-1]['end'] if index else start
            right=next((w['start'] for w in words[index+1:] if w['start']>left),end)
            if right<=left:
                if index and words[index-1]['start']<end-.02:
                    left=max(words[index-1]['start']+.01,end-.04)
                    words[index-1]['end']=left;right=end;word['start']=left
                else:raise CaptionBackendError('The recognizer returned no usable span for a recognized word.')
            word['start']=max(left,min(word['start'],right-.01));word['end']=min(right,word['start']+.06)
            word['confidence']=0.
        if index and word['start']<words[index-1]['end']:
            previous=words[index-1]
            boundary=(previous['end']+word['start'])/2
            if previous['start']<boundary<word['end']:
                previous['end']=boundary;word['start']=boundary
            elif require_exact:raise CaptionBackendError('Conflicting word timestamps. Audio was not changed.')
            else:
                if previous['end']>=end:
                    raise CaptionBackendError('The recognizer returned conflicting timestamps beyond the audio range.')
                word['start']=previous['end'];word['end']=min(end,max(word['end'],word['start']+.02));word['confidence']=0.
    return words
