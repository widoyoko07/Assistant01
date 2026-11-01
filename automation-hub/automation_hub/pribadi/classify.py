"""K2a: tebak Subcategory dari deskripsi: riwayat Excel > kata kunci config > token riwayat > typo (fuzzy).
Ragu atau bertentangan = UNCATEGORIZED, bukan ditebak."""
import difflib
import json
import re
from collections import Counter, defaultdict

from ..common.money import UNCATEGORIZED, categorize

_AMOUNT = re.compile(r"(?<![\w.,])(?:rp\.?\s*)?\d[\d.,]*\s*(?:juta|jt|ribu|rb|k)?(?![a-z\d])", re.IGNORECASE)
MIN_PHRASE_SHARE = 0.8   # share suara terbanyak agar deskripsi persis dipercaya
MIN_TOKEN_COUNT = 3      # token harus muncul minimal sekian kali di riwayat
MIN_TOKEN_SHARE = 0.85
FUZZY_CUTOFF = 0.84
MIN_FUZZY_LEN = 4


def normalize(text):
    t = _AMOUNT.sub(" ", text.lower())
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9& ]+", " ", t)).strip()


def tokens(text):
    return [w for w in normalize(text).split() if len(w) >= 3 and not w.isdigit()]


def build_lexicon(records):
    """records: [{description, subcategory}] -> {'phrases': {frasa: {subcat: n}}, 'tokens': {...}}"""
    phrases, toks = defaultdict(Counter), defaultdict(Counter)
    for r in records:
        sub = r["subcategory"]
        n = normalize(r["description"])
        if n:
            phrases[n][sub] += 1
        for w in set(tokens(r["description"])):
            toks[w][sub] += 1
    return {"phrases": {k: dict(v) for k, v in phrases.items()}, "tokens": {k: dict(v) for k, v in toks.items()}}


def save_lexicon(lex, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(lex, ensure_ascii=False), encoding="utf-8")


def load_lexicon(path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def _winner(counts, min_share, min_count=1):
    total = sum(counts.values())
    sub, n = max(counts.items(), key=lambda kv: kv[1])
    return sub if total >= min_count and n / total >= min_share else None


def _trusted_tokens(lex):
    return {w: s for w in lex["tokens"] if (s := _winner(lex["tokens"][w], MIN_TOKEN_SHARE, MIN_TOKEN_COUNT))}


def classify(text, categories, lexicon=None):
    norm = normalize(text)
    if lexicon and norm in lexicon["phrases"]:
        sub = _winner(lexicon["phrases"][norm], MIN_PHRASE_SHARE)
        if sub:
            return sub
    cat = categorize(norm, categories)
    if cat != UNCATEGORIZED:
        return cat
    if not lexicon:
        return UNCATEGORIZED
    trusted = _trusted_tokens(lexicon)
    words = tokens(text)
    hits = {trusted[w] for w in words if w in trusted}
    if len(hits) == 1:
        return hits.pop()
    if hits:
        return UNCATEGORIZED  # token menunjuk subcategory berbeda: ambigu
    # typo: samakan dengan kosakata terpercaya + kata kunci config satu kata
    vocab = dict(trusted)
    for sub, words_ in categories.items():
        for kw in words_:
            if " " not in kw:
                vocab.setdefault(kw.lower(), sub)
    fuzzy = set()
    for w in words:
        if len(w) >= MIN_FUZZY_LEN:
            near = difflib.get_close_matches(w, vocab, n=1, cutoff=FUZZY_CUTOFF)
            if near:
                fuzzy.add(vocab[near[0]])
    return fuzzy.pop() if len(fuzzy) == 1 else UNCATEGORIZED
