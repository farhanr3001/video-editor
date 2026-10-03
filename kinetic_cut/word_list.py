"""Embedded offline dictionary for inline word autocomplete."""
from __future__ import annotations
import re
from typing import Optional

# High-frequency words prioritized for intuitive phone-keyboard-style auto-completion
COMMON_WORDS: list[str] = [
    # Top conversational & action words
    "guessing", "guess", "guests", "guest", "people", "something", "video", "videos",
    "stream", "streamer", "streaming", "streams", "channel", "content", "clipping",
    "caption", "captions", "subtitle", "subtitles", "awesome", "amazing", "brother",
    "friend", "friends", "talking", "looking", "working", "playing", "thinking",
    "feeling", "getting", "making", "coming", "welcome", "subscribe", "reaction",
    "because", "without", "question", "questions", "really", "another", "youtube",
    "together", "everything", "everyone", "someone", "somebody", "anybody", "anything",
    "probably", "actually", "remember", "different", "understand", "important",
    "already", "always", "nothing", "around", "before", "behind", "between",
    "during", "through", "toward", "against", "almost", "little", "should",
    "would", "could", "number", "system", "moment", "second", "minute", "action",
    "history", "change", "simple", "single", "future", "camera", "picture",
    "morning", "evening", "tonight", "tomorrow", "yesterday", "tonight",
    "watching", "waiting", "walking", "running", "listening", "learning",
    "starting", "stopping", "leaving", "keeping", "holding", "bringing",
    "happening", "beginning", "following", "breaking", "building", "creating",
    "helping", "leading", "living", "meaning", "moving", "offering", "paying",
    "providing", "putting", "reading", "saying", "seeing", "sending", "showing",
    "speaking", "standing", "telling", "winning", "writing", "about", "above",
    "across", "after", "again", "ahead", "allow", "alone", "along", "already",
    "although", "always", "among", "animal", "another", "answer", "anyone",
    "appear", "apply", "approach", "area", "argue", "around", "arrive",
    "article", "attack", "attempt", "attend", "author", "available", "avoid",
    "beautiful", "become", "begin", "behavior", "behind", "believe", "benefit",
    "better", "between", "beyond", "billion", "black", "blood", "board",
    "bottom", "break", "brief", "bring", "brother", "budget", "build",
    "building", "business", "camera", "campaign", "cancer", "candidate", "capital",
    "career", "carry", "catch", "cause", "center", "central", "century", "certain",
    "certainly", "chair", "challenge", "chance", "change", "character", "charge",
    "check", "child", "choice", "choose", "church", "citizen", "claim", "class",
    "clear", "clearly", "close", "coach", "color", "commercial", "common",
    "community", "company", "compare", "computer", "concern", "condition", "conference",
    "congress", "consider", "consumer", "contain", "continue", "control", "cost",
    "country", "couple", "course", "court", "cover", "create", "crime", "cultural",
    "culture", "current", "customer", "daughter", "death", "debate", "decade",
    "decide", "decision", "defense", "degree", "democrat", "democratic", "describe",
    "design", "despite", "detail", "determine", "develop", "development", "device",
    "differ", "difference", "different", "difficult", "direction", "director", "discover",
    "discuss", "discussion", "disease", "doctor", "dollar", "drawing", "dream",
    "drive", "early", "economic", "economy", "education", "effect", "effort",
    "eight", "either", "election", "employee", "energy", "enjoy", "enough",
    "enter", "entire", "environment", "environmental", "especially", "establish", "evening",
    "event", "every", "everybody", "everyone", "everything", "evidence", "exactly",
    "example", "executive", "exist", "expect", "experience", "expert", "explain",
    "factor", "family", "famous", "father", "federal", "feeling", "field",
    "fight", "figure", "final", "finally", "financial", "finger", "finish",
    "fire", "firm", "first", "floor", "focus", "follow", "foreign", "forget",
    "former", "forward", "friend", "front", "future", "garden", "general",
    "generation", "glass", "government", "great", "green", "ground", "group",
    "growth", "guess", "happen", "happy", "health", "heart", "heavy",
    "history", "hospital", "hotel", "house", "human", "hundred", "husband",
    "identify", "image", "imagine", "impact", "important", "improve", "include",
    "including", "increase", "indeed", "indicate", "individual", "industry", "information",
    "inside", "instead", "institution", "interest", "interesting", "international", "interview",
    "investment", "involve", "issue", "kitchen", "knowledge", "language", "large",
    "leader", "leadership", "learn", "least", "leave", "legal", "letter",
    "level", "light", "likely", "listen", "little", "local", "location",
    "machine", "magazine", "maintain", "major", "majority", "manage", "management",
    "manager", "market", "marriage", "material", "matter", "maybe", "measure",
    "media", "medical", "meeting", "member", "memory", "mention", "message",
    "method", "middle", "might", "military", "million", "minute", "mission",
    "model", "modern", "moment", "money", "month", "morning", "mother",
    "mouth", "movement", "movie", "music", "myself", "nation", "national",
    "natural", "nature", "nearly", "necessary", "network", "never", "newspaper",
    "night", "normal", "notice", "number", "occur", "office", "officer",
    "official", "operation", "opportunity", "option", "order", "organization", "others",
    "outside", "owner", "painting", "paper", "parent", "participant", "particular",
    "particularly", "partner", "party", "patient", "pattern", "peace", "people",
    "perform", "performance", "perhaps", "period", "person", "personal", "phone",
    "physical", "picture", "piece", "place", "player", "point", "police",
    "policy", "political", "politics", "popular", "population", "position", "positive",
    "possible", "power", "practice", "prepare", "present", "president", "pressure",
    "pretty", "prevent", "price", "private", "probably", "problem", "process",
    "produce", "product", "production", "professional", "professor", "program", "project",
    "property", "protect", "prove", "provide", "public", "purpose", "quality",
    "question", "quickly", "quite", "radio", "raise", "range", "rather",
    "reach", "ready", "reality", "realize", "really", "reason", "receive",
    "recent", "recently", "recognize", "record", "reduce", "reflect", "region",
    "relate", "relationship", "religious", "remain", "remember", "remove", "report",
    "represent", "republican", "require", "research", "resource", "respond", "response",
    "responsibility", "result", "return", "reveal", "right", "scene", "school",
    "science", "scientist", "score", "season", "second", "section", "security",
    "senior", "sense", "series", "serious", "serve", "service", "several",
    "shake", "share", "shoot", "short", "should", "shoulder", "similar",
    "simple", "simply", "since", "single", "sister", "situation", "skill",
    "small", "smile", "social", "society", "soldier", "somebody", "someone",
    "something", "sometimes", "sound", "source", "south", "southern", "space",
    "speak", "special", "specific", "speech", "spend", "sport", "spring",
    "staff", "stage", "stand", "standard", "start", "state", "statement",
    "station", "stock", "story", "strategy", "street", "strong", "structure",
    "student", "study", "stuff", "style", "subject", "success", "successful",
    "suddenly", "suffer", "suggest", "summer", "support", "surface", "system",
    "table", "teach", "teacher", "technology", "television", "thank", "their",
    "theory", "there", "these", "thing", "think", "third", "those",
    "though", "thought", "thousand", "threat", "through", "throughout", "today",
    "together", "tonight", "total", "tough", "toward", "trade", "traditional",
    "training", "travel", "treat", "treatment", "trial", "trouble", "truth",
    "under", "understand", "unit", "until", "value", "various", "victim",
    "video", "violence", "visit", "voice", "waiting", "watch", "water",
    "weapon", "weight", "welcome", "whatever", "whether", "which", "while",
    "white", "whole", "whose", "window", "within", "without", "woman",
    "wonder", "worker", "world", "worry", "would", "writer", "wrong"
]

# De-duplicate while strictly preserving priority order
_SEEN = set()
UNIQUE_WORDS: list[str] = []
for _w in COMMON_WORDS:
    _lw = _w.lower()
    if _lw not in _SEEN:
        _SEEN.add(_lw)
        UNIQUE_WORDS.append(_lw)


def get_completion(prefix: str, extra_words: Optional[list[str]] = None) -> str:
    """Return the completion suffix for a word prefix, matching casing."""
    if len(prefix) < 2:
        return ""
    p_low = prefix.lower()
    
    # Check extra context words (e.g. from active project/captions) first
    if extra_words:
        for w in extra_words:
            wl = w.lower()
            if wl.startswith(p_low) and len(wl) > len(p_low):
                suffix = wl[len(p_low):]
                return suffix.upper() if prefix.isupper() else suffix
                
    # Search common word pool
    for w in UNIQUE_WORDS:
        if w.startswith(p_low) and len(w) > len(p_low):
            suffix = w[len(p_low):]
            return suffix.upper() if prefix.isupper() else suffix
            
    return ""
