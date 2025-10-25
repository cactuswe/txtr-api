from __future__ import annotations
from typing import List, Dict
from .utils import first_sentences, normalize_text
from langdetect import detect, LangDetectException
import nltk

def extract_keywords(text: str, top_k: int = 12) -> list[str]:
    """
    RAKE (rake-nltk) + rensning → 1–5-grams som inte är skräp.
    Kräver nltk stopwords (nltk==3.9.1 finns installerat).
    """
    if not text or len(text) < 200:
        return []

    import re
    from rake_nltk import Rake
    import nltk

    try:
        nltk.data.find('corpora/stopwords')
    except LookupError:
        nltk.download('stopwords', quiet=True)

    r = Rake()
    sample = text if len(text) < 20000 else text[:20000]
    r.extract_keywords_from_text(sample)
    scored = r.get_ranked_phrases_with_scores()

    phrases: list[str] = []
    for score, phrase in scored:
        phrase = re.sub(r"\s+", " ", phrase.strip().lower())
        if not phrase or len(phrase) < 4:
            continue
        if phrase.isdigit() or re.fullmatch(r"\d{4}", phrase):
            continue
        if phrase in {"retrieved", "archived", "original", "references", "other", "using"}:
            continue
        tokens = phrase.split()
        if len(tokens) > 5:
            phrase = " ".join(tokens[:5])
        phrases.append(phrase)

    seen, out = set(), []
    for p in phrases:
        if p not in seen:
            seen.add(p)
            out.append(p)
        if len(out) >= top_k:
            break

    if not out:
        words = re.findall(r"\b[a-z]{4,}\b", sample.lower())
        freq: dict[str, int] = {}
        for w in words:
            freq[w] = freq.get(w, 0) + 1
        out = [w for w, _ in sorted(freq.items(), key=lambda x: x[1], reverse=True)[:top_k]]

    return out

# Initialize NLTK resources on demand
def _ensure_nltk_resources() -> None:
    """Ensure required NLTK resources are available."""
    try:
        nltk.data.find('tokenizers/punkt')
        nltk.data.find('sentiment/vader_lexicon.zip')
    except LookupError:
        nltk.download('punkt')
        nltk.download('stopwords')
        nltk.download('vader_lexicon')


def detect_language(text: str) -> str:
    try:
        return detect(text)
    except (LangDetectException, Exception):
        return "und"

def summarize_text(text: str, target_sentences: int = 2) -> str:
    txt = normalize_text(text or "")
    if not txt:
        return ""
    # Language → tokenizer
    try:
        lang = detect_language(txt)
    except Exception:
        lang = "en"
    lang_map = {
        "en": "english", "sv": "swedish", "no": "norwegian", 
        "da": "danish", "de": "german", "fr": "french",
        "es": "spanish", "it": "italian", "pt": "portuguese", 
        "nl": "dutch"
    }
    tok = lang_map.get(lang, "english")

    try:
        from sumy.parsers.plaintext import PlaintextParser
        from sumy.nlp.tokenizers import Tokenizer
        from sumy.summarizers.text_rank import TextRankSummarizer

        # Use detected language's tokenizer
        parser = PlaintextParser.from_string(txt, Tokenizer(tok))
        summarizer = TextRankSummarizer()
        sentences = [str(s) for s in summarizer(parser.document, target_sentences)]
        if sentences:
            # Ensure reasonable length summary
            summary = " ".join(sentences)
            if len(summary) > 1000:
                return first_sentences(summary, target_sentences)
            return summary
    except Exception:
        pass
    return first_sentences(txt, target_sentences)

def extract_keywords(text: str, top_k: int = 10) -> list[str]:
    txt = normalize_text(text or "")
    if not txt:
        return []
    import re
    from collections import Counter

    # Language
    try:
        from langdetect import detect
        lang = detect(txt)
    except Exception:
        lang = "en"

    # Candidates with YAKE (1-3 grams)
    candidates: list[str] = []
    try:
        import yake  # type: ignore
        lan = lang if lang in {"en","sv","de","fr","es","it","pt","nl"} else "en"
        scored = []
        for n in (1, 2, 3):
            ke = yake.KeywordExtractor(lan=lan, n=n, top=top_k*5, dedupLim=0.9)
            scored.extend(ke.extract_keywords(txt))
        # lower score is better in YAKE
        scored.sort(key=lambda x: x[1])
        candidates = [w for w, _ in scored]
    except Exception:
        # RAKE fallback
        try:
            from rake_nltk import Rake
            try:
                _ = nltk.corpus.stopwords.words("english")
            except LookupError:
                nltk.download("stopwords")
            rake = Rake()
            rake.extract_keywords_from_text(txt)
            candidates = [p.strip() for p in rake.get_ranked_phrases()]
        except Exception:
            # Basic word frequency fallback
            candidates = re.findall(r"\b\w+\b", txt.lower())

    # Normalization/filtering
    stoplike = {
        "retrieved","archived","original","from","references","other","used","that","with","into","about",
        "their","been","such","also","most","some","many","which","these","those","often","typically"
    }
    norm: list[str] = []
    for c in candidates:
        c = re.sub(r"\s+", " ", c.lower()).strip()
        if not c: continue
        # drop years/numbers and very short
        if re.fullmatch(r"\d{4}", c) or c.isdigit(): continue
        if len(c) < 4: continue
        # drop "stoplike" pure words
        if c in stoplike: continue
        # drop phrases consisting only of stoplike words
        tokens = c.split()
        if all(t in stoplike or len(t) < 4 for t in tokens):
            continue
        norm.append(c)

    if not norm:
        words = re.findall(r"\b[a-z]{4,}\b", txt.lower())
        common = [w for w, _ in Counter(words).most_common(top_k)]
        return common

    # Dedup on stem (so we don't get "learning" + "deep learning" twice)
    try:
        import nltk
        from nltk.stem.snowball import SnowballStemmer
        stemmer = SnowballStemmer("english")
        def sig(phrase: str) -> str:
            toks = phrase.split()
            return " ".join(stemmer.stem(t) for t in toks)
        seen = set()
        unique: list[str] = []
        for c in norm:
            s = sig(c)
            if s in seen: 
                continue
            seen.add(s)
            unique.append(c)
            if len(unique) == top_k:
                break
        return unique
    except Exception:
        # simple uniquification if nltk is missing
        seen, unique = set(), []
        for c in norm:
            if c not in seen:
                seen.add(c)
                unique.append(c)
            if len(unique) == top_k:
                break
        return unique

def analyze_sentiment(text: str, source_url: str | None = None) -> Dict[str, float | str]:
    import nltk
    from math import fsum

    sample = (text or "").strip()
    if not sample:
        return {"label": "neutral", "score": 0.0}

    try:
        from nltk.sentiment import SentimentIntensityAnalyzer
        try:
            nltk.data.find("sentiment/vader_lexicon.zip")
        except LookupError:
            nltk.download("vader_lexicon")
        sia = SentimentIntensityAnalyzer()

        import re
        sentences = [s.strip() for s in re.split(r"(?<=[\.!\?])\s+", sample[:4000]) if s.strip()]
        if sentences:
            scores = [float(sia.polarity_scores(s)["compound"]) for s in sentences]
            comp = fsum(scores) / len(scores)
        else:
            comp = float(sia.polarity_scores(sample[:4000])["compound"])

        # Dämpa sentiment för uppslagsverk och neutrala källor
        NEUTRAL_DOMAINS = [
            "wikipedia.org",
            "wikidata.org",
            "britannica.com",
            "baike.baidu.com",
            "encyclopedia.com",
            "investopedia.com",
            "dictionary.com",
            "collinsdictionary.com",
            "thefreedictionary.com",
            "wordreference.com",
        ]

        if source_url and any(domain in source_url for domain in NEUTRAL_DOMAINS):
            comp = max(min(comp, 0.04), -0.04)
        else:
            comp = max(min(comp, 0.6), -0.6)

        # strikt gräns
        if comp > 0.05:
            label = "positive"
        elif comp < -0.05:
            label = "negative"
        else:
            label = "neutral"
        return {"label": label, "score": round(comp, 4)}
    except Exception:
        return {"label": "neutral", "score": 0.0}