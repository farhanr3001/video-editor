"""Whole-word English profanity matching; deliberately no substring matching."""
import re

# Explicit forms avoid false positives such as 'class', 'Scunthorpe' or 'assess'.
WORDS=set("fuck fucks fucked fucking fucker fuckers motherfucker motherfuckers motherfucking shit shits shitty shitting bullshit horseshit bitch bitches bitching bastard bastards asshole assholes arsehole arseholes dick dicks dickhead dickheads cock cocks cocksucker cocksuckers cunt cunts piss pissed pissing twat twats wanker wankers goddamn goddammit".split())
TOKEN=re.compile(r"\b[^\W\d_]+(?:['’][^\W\d_]+)?\b",re.UNICODE)


def is_curse(word):
    return word.lower().replace("’","'").removesuffix("'s") in WORDS


def contains_curse(text):
    return any(is_curse(match.group()) for match in TOKEN.finditer(text))


def censor_text(text):
    def mask(match):
        word=match.group()
        if not is_curse(word):return word
        visible=2 if word.lower().startswith(("sh","bi","pi")) else 1
        return word[:visible]+"*"*(len(word)-visible)
    return TOKEN.sub(mask,text)
