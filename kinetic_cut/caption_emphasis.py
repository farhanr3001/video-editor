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
