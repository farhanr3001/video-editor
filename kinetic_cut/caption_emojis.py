"""Conservative, sparse emoji emphasis shared by caption preview and export."""
import re
from collections import Counter
from .caption_words import timings

_GROUPS=[
    ('⚠️',6,'danger dangerous warning hazard'),('🚨',6,'emergency alarm siren'),
    ('☠️',6,'death dead deadly killed'),('🔥',5,'fire flames burning'),
    ('🌊',5,'water ocean sea river flood flooding drowning sinking'),('🚗',5,'car cars vehicle driving'),
    ('✈️',5,'airplane airport flight'),('🚀',6,'rocket spaceship'),('🏠',4,'home house'),
    ('🔒',4,'locked lock'),('🔓',4,'unlock unlocked'),('🔨',4,'hammer'),('🔧',4,'tool tools'),
    ('💥',6,'explosion exploded crash smashed shattered'),('🛡️',5,'survival survive safety'),
    ('☕',5,'coffee espresso latte cappuccino'),('☕',4,'cafe café'),('🎧',5,'headphones earbuds'),
    ('📱',5,'phone smartphone'),('💬',4,'message messages texting texted'),('📞',5,'call calls calling'),
    ('🍕',5,'pizza'),('🍔',5,'burger burgers'),('🍰',5,'cake birthday'),('🍎',5,'apple apples'),
    ('🍫',5,'chocolate'),('🍿',5,'popcorn'),('🐶',5,'dog dogs puppy'),('🐱',5,'cat cats kitten'),
    ('😂',6,'laugh laughing laughed laughter hilarious'),('😰',6,'panic panicked panicking'),
    ('🤯',6,'crazy insane unbelievable'),('😱',6,'shocked shocking terrified'),
    ('😵‍💫',6,'unhinged'),('😢',6,'cry crying cried tears'),('😡',6,'angry furious'),
    ('🤔',5,'curious confused'),('🤫',5,'secret secrets'),('❤️',5,'love heart'),
    ('💰',5,'money cash millionaire'),('💵',5,'dollar dollars'),('🏆',6,'win winner victory'),
    ('🏅',6,'medal medals'),('🏊',5,'swim swimming'),('🧗',5,'climbing'),
    ('💪',5,'strength strong workout'),('👶',5,'baby babies'),('🎮',5,'gaming gamer videogame'),
    ('🎵',5,'music song singing'),('🎤',5,'microphone karaoke'),('🎸',5,'guitar'),
    ('⚽',5,'soccer football'),('🏀',5,'basketball'),('❄️',5,'snow freezing'),
    ('🌧️',5,'rain raining'),('☀️',5,'sun sunshine'),('⏱️',4,'seconds minutes hours'),
]
KEYWORD_EMOJI_MAP={word:emoji for emoji,_,words in _GROUPS for word in words.split()}
_SCORES={word:score for _,score,words in _GROUPS for word in words.split()}
_NUMBERS=set('one two three four five six seven eight nine ten twenty thirty sixty few couple'.split())

def clean_token(word):
    return re.sub(r'[^\w]','',word).casefold()

def find_emoji_for_word(word):
    # No prefix or random fallback: filler/unknown words must stay plain.
    return KEYWORD_EMOJI_MAP.get(clean_token(word))

def _candidate(tokens,index):
    word=tokens[index]; before=tokens[max(0,index-3):index]; after=tokens[index+1:index+4]
    if word in ('call','calls','calling'):
        if after[:2]==['of','duty'] or after[:1] in (['out'],['it'],['him'],['her'],['them']):return None
        if after[:2]==['me','crazy']:return None
    if word in ('fire','burning') and (after[:1] in (['employee'],['employees'],['him'],['her'],['them'],['bridges']) or before[-1:] in (['hire'],['to'])):return None
    if word in ('seconds','minutes','hours') and not (before and (before[-1] in _NUMBERS or before[-1].isdigit())):return None
    if word in ('run','running') and not any(w in ('code','program','business','tests','test') for w in after) and any(w in ('home','away','marathon','race') for w in before+after):return ('🏃',5)
    if word=='silent' and ('phone' in before or after[:1]==['mode']):return ('🔇',6)
    if word=='believe' and before[-1:] in (['not'],['cant'],['cannot']):return ('🤯',6)
    if word=='duty' and before[-2:]==['call','of']:return ('🎮',6)
    emoji=KEYWORD_EMOJI_MAP.get(word)
    return (emoji,_SCORES[word]) if emoji else None

def get_caption_emojis(caption_text,max_emojis=2):
    """Standalone/template-card selection; empty is a valid, preferred result."""
    if max_emojis<=0:return []
    tokens=[clean_token(word) for word in caption_text.split()]; ranked=[]
    for index in range(len(tokens)):
        candidate=_candidate(tokens,index)
        if candidate:ranked.append((candidate[1],index,candidate[0]))
    result=[]; seen=set()
    for _,index,emoji in sorted(ranked,key=lambda c:(-c[0],c[1])):
        if emoji in seen:continue
        result.append((index,emoji)); seen.add(emoji)
        if len(result)>=max_emojis:break
    return sorted(result)

def _signature(project,caption):
    return (caption.text,caption.start,caption.end,tuple((w.get('text'),w.get('start'),w.get('end')) for w in caption.word_timings),
            tuple(caption.highlighted_words),project.caption_style(caption).animation)

def _plan(project):
    records=[]; group=0; previous_end=None; previous_text=''
    for caption in sorted(project.captions,key=lambda c:(c.start,c.end,c.id)):
        if previous_end is not None and (caption.start-previous_end>.8 or caption.start<previous_end-.05 or re.search(r'[.!?]$',previous_text)):group+=1
        last_word=''
        for index,(word,(start,end)) in enumerate(zip(caption.text.split(),timings(caption))):
            if re.search(r'[.!?]$',last_word):group+=1
            records.append((caption,index,clean_token(word),start,end,group))
            last_word=word
        previous_end=caption.end; previous_text=caption.text
    candidates=[]; frequency=Counter(record[2] for record in records)
    for index,(caption,word_index,_,start,end,group) in enumerate(records):
        if project.caption_style(caption).animation not in ('emoji pop','double emoji'):continue
        left=max(0,index-3); right=min(len(records),index+4)
        while left<index and records[left][5]!=group:left+=1
        while right>index+1 and records[right-1][5]!=group:right-=1
        candidate=_candidate([r[2] for r in records[left:right]],index-left)
        if candidate and end>start:
            emoji,score=candidate
            # Recurring concrete topics deserve emphasis over incidental nouns;
            # the small bonus never outranks a clearly salient emotion/danger.
            score+=min(.75,.15*(frequency[records[index][2]]-1))
            candidates.append((score+int(word_index in caption.highlighted_words),start,index,caption,word_index,emoji))
    chosen=[]; counts={}
    for _,start,index,caption,word_index,emoji in sorted(candidates,key=lambda c:(-c[0],c[1],c[2])):
        limit=2 if project.caption_style(caption).animation=='double emoji' else 1
        if counts.get(caption.id,0)>=limit:continue
        # Distinct concrete words can occur in the same sentence (headphones,
        # coffee). Keep repetition sparse without discarding the earlier object.
        if any(abs(start-other[0])<.8 or (emoji==other[3] and abs(start-other[0])<8) for other in chosen):continue
        chosen.append((start,caption.id,word_index,emoji)); counts[caption.id]=counts.get(caption.id,0)+1
    result={c.id:(_signature(project,c),[]) for c in project.captions}
    for _,caption_id,index,emoji in sorted(chosen):result[caption_id][1].append((index,emoji))
    return result

def emojis_for_caption(project,caption,max_emojis=1):
    """Cached sparse transcript plan; ephemeral state never enters project files."""
    stamp=(project.modified_at,id(project.captions),len(project.captions),project.subtitle_style.animation)
    cache=getattr(project,'_caption_emoji_plan',None); own=_signature(project,caption)
    if not cache or cache[0]!=stamp or (caption.id in cache[1] and cache[1][caption.id][0]!=own):
        cache=(stamp,_plan(project)); project._caption_emoji_plan=cache
    entry=cache[1].get(caption.id)
    return entry[1][:max(0,max_emojis)] if entry else get_caption_emojis(caption.text,max_emojis)
