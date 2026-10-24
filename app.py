import base64
import json
import random
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
import streamlit as st

# ============================ SETTINGS (edit these) ============================
APP_NAME = "Pragna Mitra"
TAGLINE = "Your friend in learning"
LEARNER = "Narayana"
LANGUAGE = "Telugu"
STYLE_NOTE = "Everyday spoken Telugu, the way people talk in Hyderabad"
TIMEZONE = "Australia/Brisbane"
DAILY_GOAL = 20            # practice answers per day for a ✅ day
QUIZ_LENGTH = 10

st.set_page_config(page_title=APP_NAME, page_icon="🪔", layout="centered")

# ------------------------------------------------------------------------------
# HOW TELUGU IS WRITTEN IN THIS FILE (for whoever adds words later)
#   aa ee oo = long vowels  ·  E / O = long e / long o (ఏ / ఓ)
#   T D N L  = the "tongue-curled" sounds (ట డ ణ ళ)  ·  t d n l = soft sounds (త ద న ల)
#   ch = చ  · sh = శ  · S = ష  ·  _word = an English word said as English (e.g. _bus)
# The app shows everything in simple English letters, and uses this spelling to pronounce it correctly.
# ------------------------------------------------------------------------------


def show(roman: str) -> str:
    """Learner-friendly spelling: tinTunnaanu -> tintunnaanu."""
    s = roman.replace("_", "")
    s = s.replace("S", "sh")
    for a, b in (("T", "t"), ("D", "d"), ("N", "n"), ("L", "l"), ("E", "e"), ("O", "o"), ("M", "m")):
        s = s.replace(a, b)
    return s


def show_cap(roman: str) -> str:
    s = show(roman)
    return s[:1].upper() + s[1:] if s else s


# ---------------------- English letters -> Telugu script (for the voice) ----------------------
_V = [("aa", "ఆ", "ా"), ("ai", "ఐ", "ై"), ("au", "ఔ", "ౌ"), ("ee", "ఈ", "ీ"), ("ii", "ఈ", "ీ"),
      ("oo", "ఊ", "ూ"), ("uu", "ఊ", "ూ"), ("E", "ఏ", "ే"), ("O", "ఓ", "ో"), ("a", "అ", ""), ("i", "ఇ", "ి"),
      ("u", "ఉ", "ు"), ("e", "ఎ", "ె"), ("o", "ఒ", "ొ")]
_C = [("ksh", "క్ష"), ("chh", "ఛ"), ("ch", "చ"), ("kh", "ఖ"), ("gh", "ఘ"), ("jh", "ఝ"), ("Th", "ఠ"), ("Dh", "ఢ"),
      ("th", "థ"), ("dh", "ధ"), ("ph", "ఫ"), ("bh", "భ"), ("sh", "శ"), ("k", "క"), ("g", "గ"), ("j", "జ"),
      ("T", "ట"), ("D", "డ"), ("N", "ణ"), ("t", "త"), ("d", "ద"), ("n", "న"), ("p", "ప"), ("b", "బ"), ("m", "మ"),
      ("y", "య"), ("r", "ర"), ("l", "ల"), ("L", "ళ"), ("v", "వ"), ("w", "వ"), ("s", "స"), ("S", "ష"), ("h", "హ"),
      ("f", "ఫ"), ("z", "జ"), ("x", "క్స"), ("c", "క"), ("q", "క")]
_STOPS = ("k", "g", "ch", "j", "T", "D", "t", "d", "p", "b")
_VIRAMA, _ANUSVARA = "్", "ం"


def _te_word(w: str) -> str:
    out, pending, i = "", None, 0
    while i < len(w):
        if w[i] == "M":
            if pending:
                out += pending + _VIRAMA
                pending = None
            out += _ANUSVARA
            i += 1
            continue
        for v, ind, sign in _V:
            if w.startswith(v, i):
                if pending:
                    out += pending + sign
                    pending = None
                else:
                    out += ind
                i += len(v)
                break
        else:
            hit = next(((c, s) for c, s in _C if w.startswith(c, i)), None)
            if hit is None:
                i += 1
                continue
            c, s = hit
            nxt = w[i + len(c):]
            if c in ("n", "N", "m") and pending is None and out and (
                    any(nxt.startswith(x) for x in _STOPS) or (c == "m" and nxt == "")):
                out += _ANUSVARA           # e.g. tinTunnaanu -> తింటున్నాను, annam -> అన్నం
                i += len(c)
                continue
            if pending:
                out += pending + _VIRAMA
            pending = s
            i += len(c)
    if pending:
        out += pending + _VIRAMA
    return out


def te_script(roman: str) -> str:
    parts = re.split(r"([\s,.!?;:()/\-]+)", roman)
    res = []
    for p in parts:
        if not p or re.match(r"[\s,.!?;:()/\-]+$", p):
            res.append(p)
        elif p.startswith("_"):
            res.append(p[1:])               # English word: let the voice say it as English
        else:
            res.append(_te_word(p))
    return "".join(res)


# ---------------------- Telugu script -> English letters (for online look-ups) ----------------------
_TV = {"అ": "a", "ఆ": "aa", "ఇ": "i", "ఈ": "ee", "ఉ": "u", "ఊ": "oo", "ఋ": "ru", "ఎ": "e", "ఏ": "E", "ఐ": "ai",
       "ఒ": "o", "ఓ": "O", "ఔ": "au"}
_TS = {"ా": "aa", "ి": "i", "ీ": "ee", "ు": "u", "ూ": "oo", "ృ": "ru", "ె": "e", "ే": "E", "ై": "ai", "ొ": "o",
       "ో": "O", "ౌ": "au"}
_TC = {"క": "k", "ఖ": "kh", "గ": "g", "ఘ": "gh", "ఙ": "n", "చ": "ch", "ఛ": "chh", "జ": "j", "ఝ": "jh", "ఞ": "n",
       "ట": "T", "ఠ": "Th", "డ": "D", "ఢ": "Dh", "ణ": "N", "త": "t", "థ": "th", "ద": "d", "ధ": "dh", "న": "n",
       "ప": "p", "ఫ": "ph", "బ": "b", "భ": "bh", "మ": "m", "య": "y", "ర": "r", "ఱ": "r", "ల": "l", "ళ": "L",
       "వ": "v", "శ": "sh", "ష": "S", "స": "s", "హ": "h"}
TELUGU_RE = re.compile("[ఀ-౿]")


def roman_from_telugu(text: str) -> str:
    out, i = "", 0
    while i < len(text):
        ch = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else ""
        if ch in _TC:
            if nxt == "్":
                out += _TC[ch]; i += 2
            elif nxt in _TS:
                out += _TC[ch] + _TS[nxt]; i += 2
            else:
                out += _TC[ch] + "a"; i += 1
        elif ch in _TV:
            out += _TV[ch]; i += 1
        elif ch == "ం":
            out += "m" if (nxt in ("ప", "బ", "భ", "మ") or not nxt or not TELUGU_RE.match(nxt)) else "n"; i += 1
        elif ch == "ః":
            out += "h"; i += 1
        else:
            out += ch; i += 1
    return out


# ------------------------------------ voice ------------------------------------
@st.cache_data(show_spinner=False, max_entries=4000)
def _gtts_b64(script: str, slow: bool):
    from io import BytesIO
    from gtts import gTTS
    buf = BytesIO()
    gTTS(text=script, lang="te", slow=slow, timeout=6).write_to_fp(buf)
    return base64.b64encode(buf.getvalue()).decode()


AUDIO_ENGINE = r"""
(function(){
  if (window.__pmSay) return;
  var ctx = null;
  function ensure(){ if(!ctx){ try{ ctx = new (window.AudioContext||window.webkitAudioContext)(); }catch(e){ return null; } }
    if (ctx.state === 'suspended') ctx.resume(); return ctx; }
  function unlock(){ var c = ensure(); if(!c) return; try{ var b=c.createBuffer(1,1,22050), s=c.createBufferSource();
    s.buffer=b; s.connect(c.destination); s.start(0);}catch(e){} }
  ['pointerdown','touchend','click','keydown'].forEach(function(ev){ document.addEventListener(ev, unlock, {capture:true, passive:true}); });
  var current = null;
  function speak(text, rate){
    try { speechSynthesis.cancel(); var u = new SpeechSynthesisUtterance(text);
      var v = speechSynthesis.getVoices().find(function(x){ return x.lang && x.lang.toLowerCase().indexOf('te') === 0; });
      if (v) { u.voice = v; u.lang = v.lang; } else { u.lang = 'te-IN'; }
      u.rate = rate < 1 ? 0.6 : 0.9; speechSynthesis.speak(u); } catch(e) {}
  }
  window.__pmSay = function(b64, text, rate){
    var c = ensure();
    if (!b64 || !c) { speak(text, rate); return; }
    try {
      var bin = atob(b64), buf = new Uint8Array(bin.length);
      for (var i = 0; i < bin.length; i++) buf[i] = bin.charCodeAt(i);
      c.decodeAudioData(buf.buffer, function(audio){
        try { if (current) current.stop(); } catch(e) {}
        var s = c.createBufferSource(); s.buffer = audio; s.connect(c.destination); s.start(0); current = s;
      }, function(){ speak(text, rate); });
    } catch(e) { speak(text, rate); }
  };
  if (window.speechSynthesis) speechSynthesis.getVoices();
})();
"""


def _embed(html_doc, height):
    if hasattr(st, "iframe"):
        st.iframe(html_doc, height=height)
    else:
        import streamlit.components.v1 as components
        components.html(html_doc, height=height)


def install_audio_engine():
    _embed("<script>try{var P=window.parent;if(!P.__pmSay){var s=P.document.createElement('script');"
           f"s.textContent={json.dumps(AUDIO_ENGINE)};P.document.head.appendChild(s);}}}}catch(e){{}}</script>", 1)


def queue_say(roman: str, slow=False):
    """Button callback: remember what to say; it is played at the top of the next run."""
    st.session_state.say_req = (roman, slow, random.random())


def play_queued(holder):
    req = st.session_state.pop("say_req", None)
    if not req:
        return
    roman, slow, nonce = req
    script = te_script(roman)
    b64 = None
    if not st.session_state.get("tts_off"):
        try:
            b64 = _gtts_b64(script, slow)
        except Exception:
            st.session_state.tts_off = True     # no internet voice: use the device's own voice from now on
    with holder:
        _embed(f"<script>/*{nonce}*/try{{window.parent.__pmSay({json.dumps(b64)},{json.dumps(script)},"
               f"{0.7 if slow else 1})}}catch(e){{}}</script>", 1)


def say_btns(roman: str, key: str, slow=True):
    """Two small buttons: 🔊 say it, 🐢 slowly."""
    if slow:
        c1, c2 = st.columns(2)
        c1.button("🔊", key=f"s_{key}", on_click=queue_say, args=(roman,), help="Say it", use_container_width=True)
        c2.button("🐢", key=f"w_{key}", on_click=queue_say, args=(roman, True), help="Slowly", use_container_width=True)
    else:
        st.button("🔊", key=f"s_{key}", on_click=queue_say, args=(roman,), help="Say it")


# ------------------------------------ dates ------------------------------------
def today_local() -> date:
    return datetime.now(ZoneInfo(TIMEZONE)).date()


# ----------------------------------- storage -----------------------------------
LOCAL_FILE = Path("pragna_progress_local.json")


def default_data():
    return {"days": {}, "known": [], "practise": [], "quizzes": [], "verb_ok": 0, "verb_tries": 0,
            "online_words": {}, "notes": ""}


def secret(name, default=None):
    try:
        return st.secrets.get(name, default)
    except Exception:
        return default


def storage_cfg():
    s = secret("storage")
    if s and s.get("github_token") and s.get("repo"):
        return {"token": s["github_token"], "repo": s["repo"], "path": s.get("path", "pragna_progress.json")}
    return None


def _gh(cfg):
    url = f"https://api.github.com/repos/{cfg['repo']}/contents/{cfg['path']}"
    return url, {"Authorization": f"Bearer {cfg['token']}", "Accept": "application/vnd.github+json",
                 "Cache-Control": "no-cache"}


def load_data():
    cfg = storage_cfg()
    if cfg:
        url, headers = _gh(cfg)
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code == 404:
            return default_data(), None
        r.raise_for_status()
        body = r.json()
        return {**default_data(), **json.loads(base64.b64decode(body["content"]).decode())}, body["sha"]
    if LOCAL_FILE.exists():
        return {**default_data(), **json.loads(LOCAL_FILE.read_text())}, None
    return default_data(), None


def save_data(data, sha):
    text = json.dumps(data, indent=1, sort_keys=True, ensure_ascii=False)
    cfg = storage_cfg()
    if cfg:
        url, headers = _gh(cfg)
        payload = {"message": f"Pragna progress {today_local()}", "content": base64.b64encode(text.encode()).decode()}
        if sha:
            payload["sha"] = sha
        r = requests.put(url, headers=headers, json=payload, timeout=15)
        r.raise_for_status()
        return r.json()["content"]["sha"]
    LOCAL_FILE.write_text(text)
    return None


def update(change) -> bool:
    for attempt in range(2):
        try:
            data, sha = load_data()
            if change(data) is False:
                st.session_state.data, st.session_state.sha = data, sha
                return False
            sha = save_data(data, sha)
            st.session_state.data, st.session_state.sha = data, sha
            return True
        except requests.HTTPError as e:
            code = e.response.status_code if e.response is not None else None
            if attempt == 0 and code in (409, 422):
                continue
            st.session_state.save_error = f"GitHub said {code} — the token may have expired."
            return False
        except Exception as e:
            st.session_state.save_error = str(e)
            return False
    return False


def log_practice(right: int, total: int = 1):
    t = today_local().isoformat()

    def change(d):
        day = d.setdefault("days", {}).setdefault(t, {"answers": 0, "right": 0})
        day["answers"] += total
        day["right"] += right
    update(change)


def streak(data, today: date) -> int:
    days = data.get("days", {})
    d = today if days.get(today.isoformat(), {}).get("answers", 0) else today - timedelta(days=1)
    n = 0
    while days.get(d.isoformat(), {}).get("answers", 0):
        n += 1
        d -= timedelta(days=1)
    return n


# ------------------------------- verb tables -------------------------------
# Each person: (key, Telugu pronoun, English, person group)
PERSONS = [
    ("nEnu", "nEnu", "I", "1st person"),
    ("mEmu", "mEmu / manam", "We", "1st person"),
    ("nuvvu", "nuvvu", "You (casual)", "2nd person"),
    ("meeru", "meeru", "You (respectful / all of you)", "2nd person"),
    ("vaaDu", "vaaDu", "He (casual)", "3rd person"),
    ("aame", "aame / adi", "She / It", "3rd person"),
    ("aayana", "aayana / aavida", "He / She (respectful)", "3rd person"),
    ("vaaLLu", "vaaLLu", "They", "3rd person"),
]
_END = {"nEnu": "aanu", "mEmu": "aamu", "nuvvu": "aavu", "meeru": "aaru", "vaaDu": "aaDu", "aayana": "aaru",
        "vaaLLu": "aaru"}
_SPOKEN = {"aanu": "a", "aamu": "am", "aavu": "av", "aaru": "aaru", "aaDu": "aaDu"}
_NEG_END = {"nEnu": "nu", "mEmu": "mu", "nuvvu": "vu", "meeru": "ru", "vaaDu": "Du", "aame": "du", "aayana": "ru",
            "vaaLLu": "ru"}


def _ends_vowel(s):
    return s[-1:] in "aeiouEO"


def conj(v, tense, person):
    """Returns (full textbook-style form, everyday spoken form)."""
    pre = v.get("pre", "")
    F, P = v["F"], v["P"]
    PC = v.get("PC", F + "u")
    if tense == "present":
        if person == "aame":
            full = PC + "nnadi"
            spoken = (PC[:-1] + "ondi") if PC.endswith("u") else full
        else:
            e = _END[person]
            full = PC + "nn" + e
            spoken = PC + "nn" + _SPOKEN[e]
    elif tense == "past":
        if person == "aame":
            if v.get("SP"):
                full = v["SP"]
            elif P.endswith("unn"):
                full = P[:-1] + "di"
            elif P.endswith("nn"):
                full = P + "adi"
            else:
                full = P + "indi"
            spoken = full
        else:
            e = _END[person]
            full, spoken = P + e, P + _SPOKEN[e]
    elif tense == "future":
        if person == "aame":
            full = spoken = F + "undi"
        else:
            e = _END[person]
            full, spoken = F + e, F + _SPOKEN[e]
    elif tense == "negative":      # won't / don't
        NG = v["NG"]
        e = _NEG_END[person]
        full = spoken = NG + (e if _ends_vowel(NG) else "a" + e)
    elif tense == "didnt":
        NG = v["NG"]
        full = spoken = NG + ("lEdu" if _ends_vowel(NG) else "alEdu")
    else:
        raise ValueError(tense)
    return pre + full, pre + spoken


def extra_forms(v):
    NG = v["NG"]
    vow = _ends_vowel(NG)
    pre = v.get("pre", "")
    return [
        ("Polite request (please …)", pre + v.get("POL", NG + ("nDi" if vow else "anDi"))),
        ("Casual command (to a friend)", pre + v.get("CMD", NG if vow else NG + "u")),
        ("Please don't …", pre + v.get("NPOL", NG + ("kanDi" if vow else "akanDi"))),
        ("Don't … (casual)", pre + v.get("NCMD", NG + ("ku" if vow else "aku"))),
        ("I must …", "nEnu " + pre + v.get("MUST", NG + ("vaali" if vow else "aali"))),
        ("I can …", "nEnu " + pre + v.get("CAN", NG + ("galanu" if vow else "agalanu"))),
        ("I can't …", "nEnu " + pre + v.get("CANT", NG + ("lEnu" if vow else "alEnu"))),
    ] + ([("Let's …", pre + v["LET"])] if v.get("LET") else [])

# ================================== VERBS ==================================
# id: English meaning · F = future stem (also habitual) · P = past stem · NG = root used for negatives/commands
# Optional: PC (present stem), SP (she/it past), CMD/POL (commands), LET ("let's …"), pre (word before the verb)
# ex = example sentences (Telugu, English)
VERBS = [
    {"en": "eat", "F": "tinT", "P": "tinn", "NG": "tin", "LET": "tindaam",
     "ex": [("nEnu _tiffin tinnaanu", "I ate breakfast."), ("meeru annam tinnaaraa?", "Have you eaten? (a common greeting)")]},
    {"en": "drink", "F": "taagut", "P": "taag", "NG": "taag", "LET": "taagudaam",
     "ex": [("nEnu chai taagutunnaanu", "I'm drinking tea."), ("konchem neeLLu taaganDi", "Please drink some water.")]},
    {"en": "go", "F": "veLt", "P": "veLL", "NG": "veLL", "LET": "veLdaam",
     "ex": [("nEnu _office ki veLtunnaanu", "I'm going to the office."), ("rEpu _market ki veLdaam", "Let's go to the market tomorrow.")]},
    {"en": "go (Hyderabad everyday word)", "F": "pOt", "P": "pOy", "NG": "pO", "CMD": "pO", "POL": "pOnDi", "LET": "pOdaam",
     "ex": [("nEnu intiki pOtunnaa", "I'm going home."), ("ekkaDiki pOtunnaav?", "Where are you going?")]},
    {"en": "come", "F": "vast", "P": "vachch", "NG": "raa", "CMD": "raa", "POL": "ranDi",
     "ex": [("nEnu rEpu vastaanu", "I'll come tomorrow."), ("lOpaliki ranDi", "Please come in.")]},
    {"en": "do", "F": "chEst", "P": "chEs", "NG": "chEy", "CMD": "cheyyi", "POL": "chEyanDi", "LET": "chEddaam",
     "ex": [("Em chEstunnaavu?", "What are you doing?"), ("nEnu _homework chEsaanu", "I did my homework.")]},
    {"en": "give", "F": "ist", "P": "ichch", "NG": "ivv",
     "ex": [("konchem neeLLu ivvanDi", "Please give me some water."), ("nEnu neeku rEpu istaanu", "I'll give it to you tomorrow.")]},
    {"en": "take", "F": "teesukunT", "P": "teesukunn", "NG": "teesukO", "CMD": "teesukO",
     "ex": [("inkonchem teesukOnDi", "Please take a bit more."), ("nEnu _auto teesukunnaanu", "I took an auto.")]},
    {"en": "see / watch", "F": "chuust", "P": "chuus", "NG": "chuuD", "LET": "chuuddaam",
     "ex": [("nEnu _movie chuusaanu", "I watched a movie."), ("idi chuuDanDi", "Please look at this.")]},
    {"en": "speak / talk", "F": "maaTlaaDut", "P": "maaTlaaD", "NG": "maaTlaaD", "LET": "maaTlaaDudaam",
     "ex": [("nEnu konchem _Telugu maaTlaaDagalanu", "I can speak a little Telugu."), ("nemmadigaa maaTlaaDanDi", "Please speak slowly.")]},
    {"en": "say / tell", "F": "chept", "P": "chepp", "NG": "chepp",
     "ex": [("mallee cheppanDi", "Please say it again."), ("nEnu vaaDiki cheppaanu", "I told him.")]},
    {"en": "ask", "F": "aDugut", "P": "aDig", "NG": "aDag", "CMD": "aDugu",
     "ex": [("nEnu daari aDigaanu", "I asked for directions."), ("_teacher ni aDugu", "Ask the teacher.")]},
    {"en": "listen / hear", "F": "vinT", "P": "vinn", "NG": "vin",
     "ex": [("nEnu paaTalu vinTaanu", "I listen to songs."), ("naa maaTa vinu", "Listen to me.")]},
    {"en": "read / study", "F": "chaduvut", "P": "chadiv", "NG": "chadav", "CMD": "chaduvu",
     "ex": [("nEnu _Telugu chaduvutunnaanu", "I'm studying Telugu."), ("ee pustakam chadivaavaa?", "Did you read this book?")]},
    {"en": "write", "F": "raast", "P": "raas", "NG": "raay", "CMD": "raayi",
     "ex": [("nEnu _letter raastunnaanu", "I'm writing a letter."), ("mee pEru ikkaDa raayanDi", "Please write your name here.")]},
    {"en": "learn", "F": "nErchukunT", "P": "nErchukunn", "NG": "nErchukO", "CMD": "nErchukO",
     "ex": [("nEnu _Telugu nErchukunTunnaanu", "I'm learning Telugu."), ("nEnu chaala nErchukunnaanu", "I learned a lot.")]},
    {"en": "teach", "F": "nErput", "P": "nErp", "NG": "nErp",
     "ex": [("maa amma naaku vanTa nErpindi", "My mum taught me cooking."), ("naaku _Telugu nErputaaraa?", "Will you teach me Telugu?")]},
    {"en": "know / find out", "F": "telusukunT", "P": "telusukunn", "NG": "telusukO", "CMD": "telusukO",
     "ex": [("nEnu daari telusukunnaanu", "I found out the way."), ("_time telusukOnDi", "Please find out the time.")]},
    {"en": "understand", "pre": "artham ", "F": "chEsukunT", "P": "chEsukunn", "NG": "chEsukO", "CMD": "chEsukO",
     "ex": [("nEnu artham chEsukunnaanu", "I understood (it)."), ("naaku artham kaalEdu", "I didn't understand. (a very useful phrase)")]},
    {"en": "think", "F": "aalOchist", "P": "aalOchinch", "NG": "aalOchinch", "CMD": "aalOchinchu",
     "ex": [("nEnu daani gurinchi aalOchistunnaanu", "I'm thinking about it."), ("baagaa aalOchinchanDi", "Think about it carefully.")]},
    {"en": "think / feel / suppose", "F": "anukunT", "P": "anukunn", "NG": "anukO", "CMD": "anukO",
     "ex": [("vaaDu vastaaDani anukunTunnaanu", "I think he'll come."), ("nEnu alaa anukOlEdu", "I didn't think so.")]},
    {"en": "remember", "F": "gurtupeTTukunT", "P": "gurtupeTTukunn", "NG": "gurtupeTTukO", "CMD": "gurtupeTTukO",
     "ex": [("ee maaTa gurtupeTTukO", "Remember this word."), ("nEnu mee pEru gurtupeTTukunnaanu", "I remembered your name.")]},
    {"en": "forget", "F": "marchipOt", "P": "marchipOy", "NG": "marchipO", "CMD": "marchipO",
     "ex": [("nEnu _phone marchipOyaanu", "I forgot my phone."), ("marchipOkanDi", "Please don't forget.")]},
    {"en": "sit", "F": "kuurchunT", "P": "kuurchunn", "NG": "kuurchO", "CMD": "kuurcho",
     "ex": [("kuurchOnDi", "Please sit down."), ("nEnu ikkaDa kuurchunTaanu", "I'll sit here.")]},
    {"en": "stand", "F": "nilabaDut", "P": "nilabaDD", "NG": "nilabaD", "SP": "nilabaDindi", "CMD": "nilabaDu",
     "ex": [("ikkaDa nilabaDanDi", "Please stand here."), ("nEnu _queue lO nilabaDDaanu", "I stood in the queue.")]},
    {"en": "walk", "F": "naDust", "P": "naDich", "NG": "naDav", "CMD": "naDu",
     "ex": [("nEnu prati rOju naDustaanu", "I walk every day."), ("nemmadigaa naDavanDi", "Please walk slowly.")]},
    {"en": "run", "F": "parigettut", "P": "parigett", "NG": "parigett",
     "ex": [("vaaDu vEgamgaa parigettaaDu", "He ran fast."), ("parigettaku", "Don't run.")]},
    {"en": "sleep (go to bed)", "F": "paDukunT", "P": "paDukunn", "NG": "paDukO", "CMD": "paDuko",
     "ex": [("nEnu padi gaNTalaki paDukunTaanu", "I go to bed at 10 o'clock."), ("tvaragaa paDukO", "Go to bed early.")]},
    {"en": "fall asleep", "F": "nidrapOt", "P": "nidrapOy", "NG": "nidrapO", "CMD": "nidrapO",
     "ex": [("pillalu nidrapOyaaru", "The children fell asleep."), ("naaku nidra vastOndi", "I'm feeling sleepy.")]},
    {"en": "get up / wake up", "F": "lEst", "P": "lEch", "NG": "lEv", "CMD": "lE", "POL": "lEnDi",
     "ex": [("nEnu aaru gaNTalaki lEstaanu", "I get up at 6 o'clock."), ("tvaragaa lE!", "Get up quickly!")]},
    {"en": "play", "F": "aaDut", "P": "aaD", "NG": "aaD", "LET": "aaDudaam",
     "ex": [("mEmu _cricket aaDutaamu", "We play cricket."), ("_cricket aaDudaamaa?", "Shall we play cricket?")]},
    {"en": "sing", "F": "paaDut", "P": "paaD", "NG": "paaD",
     "ex": [("aame baagaa paaDutundi", "She sings well."), ("oka paaTa paaDanDi", "Please sing a song.")]},
    {"en": "laugh", "F": "navvut", "P": "navv", "NG": "navv",
     "ex": [("andaruu navvaaru", "Everyone laughed."), ("navvakanDi!", "Please don't laugh!")]},
    {"en": "cry", "F": "EDust", "P": "EDch", "NG": "EDav", "CMD": "EDu",
     "ex": [("baabu EDustunnaaDu", "The baby boy is crying."), ("EDavaku", "Don't cry.")]},
    {"en": "buy", "F": "konT", "P": "konn", "NG": "kon",
     "ex": [("nEnu kotta _phone konnaanu", "I bought a new phone."), ("_market lO kooragaayalu konTaanu", "I'll buy vegetables at the market.")]},
    {"en": "sell", "F": "ammut", "P": "amm", "NG": "amm",
     "ex": [("vaaDu panDlu ammutaaDu", "He sells fruit."), ("nEnu naa _bike ammaanu", "I sold my bike.")]},
    {"en": "pay (a bill) / tie / build", "F": "kaDat", "P": "kaTT", "NG": "kaTT", "PC": "kaDutu",
     "ex": [("nEnu _bill kaDataanu", "I'll pay the bill."), ("vaaLLu kotta illu kaTTaaru", "They built a new house.")]},
    {"en": "put / keep", "F": "peDat", "P": "peTT", "NG": "peTT", "PC": "peDutu",
     "ex": [("_bag ikkaDa peTTanDi", "Please put the bag here."), ("_message peTTu", "Send a message. (Hyderabad way of saying it)")]},
    {"en": "send", "F": "pamput", "P": "pamp", "NG": "pamp",
     "ex": [("nEnu _photo pampaanu", "I sent the photo."), ("_location pampanDi", "Please send the location.")]},
    {"en": "bring", "F": "test", "P": "tecch", "NG": "tE", "CMD": "tE", "POL": "tEnDi",
     "ex": [("konchem neeLLu tEnDi", "Please bring some water."), ("nEnu _sweets tecchaanu", "I brought sweets.")]},
    {"en": "call (someone)", "F": "pilust", "P": "pilich", "NG": "pilav", "CMD": "piluvu",
     "ex": [("amma ninnu pilustOndi", "Mum is calling you."), ("_doctor ni pilavanDi", "Please call the doctor.")]},
    {"en": "phone / ring someone", "pre": "_phone ", "F": "chEst", "P": "chEs", "NG": "chEy", "CMD": "cheyyi",
     "POL": "chEyanDi", "ex": [("tarvaata _phone chEstaanu", "I'll call later."), ("naaku _phone chEyanDi", "Please call me.")]},
    {"en": "meet", "F": "kalust", "P": "kalis", "NG": "kalav", "CMD": "kalavu", "LET": "kaluddaam",
     "ex": [("rEpu kaluddaam", "Let's meet tomorrow."), ("nEnu ninna mee anna ni kalisaanu", "I met your brother yesterday.")]},
    {"en": "show", "F": "chuupist", "P": "chuupinch", "NG": "chuupinch", "CMD": "chuupinchu",
     "ex": [("daari chuupinchanDi", "Please show me the way."), ("nEnu naa illu chuupistaanu", "I'll show you my house.")]},
    {"en": "help", "pre": "sahaayam ", "F": "chEst", "P": "chEs", "NG": "chEy", "CMD": "cheyyi", "POL": "chEyanDi",
     "ex": [("konchem sahaayam chEstaaraa?", "Could you help me a little?"), ("nEnu meeku sahaayam chEstaanu", "I'll help you.")]},
    {"en": "work", "pre": "pani ", "F": "chEst", "P": "chEs", "NG": "chEy", "CMD": "cheyyi", "POL": "chEyanDi",
     "ex": [("nEnu _office lO pani chEstaanu", "I work in an office."), ("eeroju chaala pani chEsaanu", "I did a lot of work today.")]},
    {"en": "cook", "pre": "vanTa ", "F": "chEst", "P": "chEs", "NG": "chEy", "CMD": "cheyyi", "POL": "chEyanDi",
     "ex": [("amma vanTa chEstOndi", "Mum is cooking."), ("nEnu _biryani vanTa chEsaanu", "I cooked biryani.")]},
    {"en": "bathe / shower", "pre": "snaanam ", "F": "chEst", "P": "chEs", "NG": "chEy", "CMD": "cheyyi", "POL": "chEyanDi",
     "ex": [("nEnu snaanam chEstunnaanu", "I'm having a shower."), ("tvaragaa snaanam cheyyi", "Have your bath quickly.")]},
    {"en": "wash", "F": "kaDugut", "P": "kaDig", "NG": "kaDag", "CMD": "kaDugu",
     "ex": [("bhOjanam mundu chEtulu kaDagaali", "You must wash your hands before eating."), ("nEnu baTTalu kaDigaanu", "I washed the clothes.")]},
    {"en": "open", "F": "terust", "P": "terich", "NG": "terav", "CMD": "teruvu",
     "ex": [("talupu teravanDi", "Please open the door."), ("_shop padi gaNTalaki terustaaru", "The shop opens at 10.")]},
    {"en": "close / shut", "F": "moost", "P": "moos", "NG": "mooy", "CMD": "mooyi",
     "ex": [("kiTikii mooyanDi", "Please close the window."), ("kaLLu moosukO", "Close your eyes.")]},
    {"en": "wait / stop", "F": "aagut", "P": "aag", "NG": "aag",
     "ex": [("oka nimisham aaganDi", "Please wait a minute."), ("_bus ikkaDa aagutundaa?", "Does the bus stop here?")]},
    {"en": "get on / climb", "F": "ekkut", "P": "ekk", "NG": "ekk",
     "ex": [("nEnu _bus ekkaanu", "I got on the bus."), ("_auto ekkanDi", "Please get into the auto.")]},
    {"en": "get off / get down", "F": "digut", "P": "dig", "NG": "dig",
     "ex": [("nEnu _metro _station daggara digutaanu", "I'll get off near the metro station."), ("ikkaDa diganDi", "Please get off here.")]},
    {"en": "search / look for", "F": "vetukut", "P": "vetik", "NG": "vetak", "CMD": "vetuku",
     "ex": [("nEnu naa _keys vetukutunnaanu", "I'm looking for my keys."), ("nEnu illu vetikaanu", "I searched (for) a house.")]},
    {"en": "drive / ride", "F": "naDuput", "P": "naDip", "NG": "naDap", "CMD": "naDupu",
     "ex": [("nEnu _car naDupagalanu", "I can drive a car."), ("nemmadigaa naDapanDi", "Please drive slowly.")]},
    {"en": "use", "F": "vaaDut", "P": "vaaD", "NG": "vaaD",
     "ex": [("nEnu _UPI vaaDutaanu", "I use UPI."), ("idi vaaDakanDi", "Please don't use this.")]},
    {"en": "try", "F": "prayatnist", "P": "prayatninch", "NG": "prayatninch", "CMD": "prayatninchu",
     "ex": [("nEnu prayatnistaanu", "I'll try."), ("mallee prayatninchu", "Try again.")]},
]

# ================================== WORDS ==================================
# Each topic: list of (English, Telugu, note)
WORDS = {
    "👪 Family": [
        ("mother", "amma", ""), ("father", "naanna", "also 'nanna'"), ("elder brother", "anna", "also used for any older man — 'anna' is how you call a stranger politely in Hyderabad"),
        ("younger brother", "tammuDu", ""), ("elder sister", "akka", "also used to politely call an older woman"),
        ("younger sister", "chelli", ""), ("grandmother (mum's mother)", "ammamma", ""), ("grandmother (dad's mother)", "naanamma", ""),
        ("grandfather", "taatayya", "also 'taata'"), ("uncle (dad's younger brother)", "baabaai", ""),
        ("uncle (dad's elder brother)", "peddanaanna", ""), ("uncle (mum's brother)", "maamayya", "also 'maama'"),
        ("aunt (mum's younger sister)", "pinni", ""), ("aunt (mum's elder sister)", "peddamma", ""),
        ("aunt (dad's sister)", "atta", "also means mother-in-law"), ("husband", "bharta", "in speech people often say 'aayana' (he)"),
        ("wife", "bhaarya", "in speech people often say 'aavida' (she)"), ("son", "koDuku", ""), ("daughter", "kooturu", ""),
        ("children", "pillalu", ""), ("baby", "paapa", "baby girl · 'baabu' = baby boy"), ("family", "kuTumbam", ""),
        ("relatives", "bandhuvulu", ""), ("friend", "snEhituDu", "in Hyderabad most people just say '_friend'"),
        ("brother-in-law", "baava", "sister's husband or a male cousin"), ("sister-in-law", "vadina", "elder brother's wife"),
        ("grandson", "manavaDu", ""), ("granddaughter", "manavaraalu", ""),
    ],
    "🙋 People & pronouns": [
        ("I", "nEnu", ""), ("we (not including you)", "mEmu", ""), ("we (including you)", "manam", "'manam veLdaam' = let's (all of us) go"),
        ("you (casual: friends, younger people)", "nuvvu", ""), ("you (respectful / more than one)", "meeru", "use with elders and people you don't know"),
        ("he (casual)", "vaaDu", "friends, younger people"), ("he (respectful)", "aayana", "elders, people you respect"),
        ("she", "aame", ""), ("she (respectful)", "aavida", ""), ("it / that", "adi", ""), ("this", "idi", ""),
        ("they", "vaaLLu", "polite and casual"), ("these people", "veeLLu", ""), ("my", "naa", ""), ("our", "maa", "'maa illu' = our house"),
        ("your (casual)", "nee", ""), ("your (respectful)", "mee", ""), ("his", "vaaDi", "respectful: 'aayana'"), ("her", "aame", ""),
        ("their", "vaaLLa", ""), ("to me / I have", "naaku", "'naaku telusu' = I know"), ("to you", "neeku / meeku", ""),
        ("me (object)", "nannu", ""), ("you (object)", "ninnu / mimmalni", ""), ("everyone", "andaruu", ""), ("someone", "evarO", ""),
        ("nobody", "evaruu lEru", ""), ("man", "magavaaDu", "in speech: 'aayana' / '_man'"), ("woman", "aaDadi", "'aaDavaaLLu' = women"),
        ("boy", "abbaayi", ""), ("girl", "ammaayi", ""), ("person / people", "manishi / manushulu", ""),
    ],
    "❓ Question words": [
        ("what?", "Enti? / Emi?", "'Enti' is the everyday form"), ("who?", "evaru?", ""), ("where?", "ekkaDa?", ""),
        ("where to?", "ekkaDiki?", ""), ("from where?", "ekkaDi nunchi?", ""), ("when?", "eppuDu?", ""), ("why?", "enduku?", ""),
        ("how?", "elaa?", ""), ("how much?", "enta?", "'idi enta?' = how much is this?"), ("how many?", "enni?", ""),
        ("which?", "Edi?", ""), ("whose?", "evaridi?", ""), ("what happened?", "Emaindi?", ""), ("what kind?", "elaanTi?", ""),
        ("is it? / really?", "-aa?", "add '-aa' to the end to make a question: 'vastaaraa?' = will you come?"),
    ],
    "🍛 Food & drink": [
        ("rice (cooked) / food", "annam", ""), ("rice (uncooked)", "biyyam", ""), ("dal / lentils", "pappu", ""),
        ("curry", "koora", ""), ("vegetables", "kooragaayalu", ""), ("rasam (tangy soup)", "chaaru", ""), ("curd / yoghurt", "perugu", ""),
        ("milk", "paalu", ""), ("water", "neeLLu", ""), ("tea", "chai", "Hyderabad loves Irani chai!"), ("coffee", "kaafi", ""),
        ("salt", "uppu", ""), ("chilli / spicy", "kaaram", "'kaaram takkuva' = less spicy"), ("sugar", "chakkera", ""),
        ("oil", "noone", ""), ("ghee", "neyyi", ""), ("egg", "guDDu", ""), ("chicken", "kODi maamsam", "most people just say '_chicken'"),
        ("fish", "chEpa", ""), ("meat (mutton)", "maamsam", "most people say '_mutton'"), ("bread / roti", "roTTe", "also '_chapati'"),
        ("fruit", "panDu / panDlu", "one / many"), ("banana", "araTi panDu", ""), ("mango", "maamiDi panDu", ""),
        ("onion", "uLLipaaya", "Hyderabad also says 'ulligaDDa'"), ("tomato", "TamaaTaa", ""), ("potato", "aalugaDDa", "Hyderabad word"),
        ("brinjal / eggplant", "vankaaya", ""), ("okra", "benDakaaya", ""), ("green chilli", "pachchi mirapakaaya", ""),
        ("ginger", "allam", ""), ("garlic", "vellulli", ""), ("coriander", "kottimeera", ""), ("lemon", "nimmakaaya", ""),
        ("breakfast", "_tiffin", "everyone in Hyderabad says '_tiffin'"), ("meal / lunch / dinner", "bhOjanam", "also 'bhOjanam chEsaaraa?' = have you eaten?"),
        ("snack", "chirutinDi", ""), ("sweet (dessert)", "_sweet / miThaayi", ""), ("hungry (hunger)", "aakali", "'naaku aakali vEstOndi' = I'm hungry"),
        ("thirst", "daaham", "'naaku daaham vEstOndi' = I'm thirsty"), ("tasty", "ruchigaa", "'chaala ruchigaa undi' = it's very tasty"),
    ],
    "🏠 Home": [
        ("house / home", "illu", "'intiki' = to home · 'intlO' = at home"), ("room", "gadi", ""), ("kitchen", "vanTagadi", ""),
        ("door", "talupu", ""), ("window", "kiTikii", ""), ("bed", "mancham", ""), ("chair", "kurchii", ""), ("table", "_table", ""),
        ("fan", "_fan", ""), ("light", "_light", "'_light vEyi' = switch on the light"), ("key", "taaLam chevi", ""), ("lock", "taaLam", ""),
        ("clock / watch", "gaDiyaaram", "most say '_watch'"), ("mirror", "addam", ""), ("plate", "_plate / palleM", ""),
        ("glass (to drink)", "_glass", ""), ("bag", "sanchi", "'_bag' also"), ("clothes", "baTTalu", ""), ("slippers / sandals", "cheppulu", ""),
        ("soap", "sabbu", ""), ("towel", "_towel", ""), ("roof / terrace", "_terrace / meeda", ""), ("rent", "addhe", "'illu addhe' = house rent"),
    ],
    "🧍 Body & health": [
        ("head", "tala", ""), ("hair", "juTTu", ""), ("face", "mukham", ""), ("eye / eyes", "kannu / kaLLu", ""), ("ear", "chevi", ""),
        ("nose", "mukku", ""), ("mouth", "nOru", ""), ("teeth", "pallu", ""), ("neck", "meDa", ""), ("hand / hands", "chEyi / chEtulu", ""),
        ("finger", "vElu", ""), ("leg / foot", "kaalu", ""), ("stomach", "kaDupu", ""), ("back", "veepu", ""), ("heart", "gunDe", ""),
        ("body", "ollu", "'ollu baagOlEdu' = I'm not well"), ("pain", "noppi", "'tala noppi' = headache"), ("fever", "jvaram", ""),
        ("cold (illness)", "jalubu", ""), ("cough", "dagguu", ""), ("medicine", "mandu", "'mandulu' = medicines"),
        ("doctor", "_doctor", ""), ("hospital", "aaspatri", "most say '_hospital'"),
    ],
    "📍 Places & travel": [
        ("town / village / home town", "ooru", "'mee ooru Edi?' = where is your home town?"), ("city", "nagaram", ""), ("road / street", "rODDu", ""),
        ("way / route", "daari", "'daari cheppanDi' = please tell me the way"), ("shop", "koTTu", "most say '_shop'"), ("market", "_market / santa", ""),
        ("temple", "guDi", ""), ("school", "baDi", "most say '_school'"), ("bus", "_bus", ""), ("train", "railu", ""), ("car", "_car", ""),
        ("bike / vehicle", "banDi", "Hyderabad word for any vehicle, especially a bike"), ("auto rickshaw", "_auto", ""),
        ("plane", "vimaanam", "most say '_flight'"), ("left", "eDama", "most say '_left'"), ("right", "kuDi", "most say '_right'"),
        ("straight", "tinnagaa", "most say '_straight'"), ("near", "daggara", ""), ("far", "dooram", ""), ("here", "ikkaDa", ""),
        ("there", "akkaDa", ""), ("inside", "lOpala", ""), ("outside", "bayaTa", ""), ("upstairs / up", "paina", ""),
        ("downstairs / down", "kinda", ""), ("map / address", "_address", ""), ("ticket", "_ticket", ""),
    ],
    "⏰ Time & days": [
        ("today", "ivvaala / eeroju", "'ivvaala' is the Hyderabad everyday word"), ("tomorrow", "rEpu", ""), ("yesterday", "ninna", ""),
        ("day after tomorrow", "ellundi", ""), ("day before yesterday", "monna", ""), ("now", "ippuDu", ""), ("later", "tarvaata", ""),
        ("before / earlier", "mundu", ""), ("then (at that time)", "appuDu", ""), ("always", "eppuDuu", ""), ("sometimes", "appuDappuDu", ""),
        ("early morning", "poddunna", "Hyderabad word"), ("morning", "udayam", ""), ("afternoon", "madhyaahnam", ""),
        ("evening", "saayantram", ""), ("night", "raatri", ""), ("day", "rOju", ""), ("week", "vaaram", ""), ("month", "nela", ""),
        ("year", "samvatsaram", "for age people say 'ELLu' = years"), ("hour / o'clock", "ganTa", "'renDu ganTalaki' = at 2 o'clock"),
        ("minute", "nimisham", ""), ("Sunday", "aadivaaram", ""), ("Monday", "sOmavaaram", ""), ("Tuesday", "mangaLavaaram", ""),
        ("Wednesday", "budhavaaram", ""), ("Thursday", "guruvaaram", ""), ("Friday", "shukravaaram", ""), ("Saturday", "shanivaaram", ""),
        ("late", "aalasyam", "most say '_late' — '_late ayyindi' = it got late"), ("quickly / early", "tvaragaa", ""),
    ],
    "🎨 Colours & describing words": [
        ("colour", "rangu", ""), ("red", "erupu", ""), ("yellow", "pasupu", ""), ("green", "aakupachcha", ""), ("blue", "neelam", ""),
        ("black", "nalupu", ""), ("white", "telupu", ""), ("pink", "gulaabi", ""), ("big", "pedda", ""), ("small", "chinna", ""),
        ("good", "manchi", ""), ("bad", "cheDDa", ""), ("new", "kotta", ""), ("old (thing)", "paata", ""), ("hot", "vEDi", ""),
        ("cold", "challani", "'challagaa undi' = it's cold"), ("sweet", "tiyyani", ""), ("beautiful", "andamaina", "'chaala andamgaa undi' = it's very beautiful"),
        ("more / too much", "ekkuva", ""), ("less / too little", "takkuva", ""), ("easy", "sulabham", "most say '_easy'"),
        ("difficult", "kashTam", ""), ("slowly", "nemmadigaa", ""), ("clean", "shubhramgaa", ""), ("dirty", "muriki", ""),
        ("heavy", "baruvu", ""), ("tall / long", "poDugu", ""), ("short", "poTTi", ""), ("very / a lot", "chaala", ""),
        ("a little", "konchem", ""), ("nice / fine", "baagundi", "'baagundi' = it's nice/good"),
    ],
    "😊 Feelings": [
        ("happy / happiness", "santOsham", "'naaku santOshamgaa undi' = I'm happy"), ("sad / sadness", "baadha", "'baadhagaa undi' = I feel sad"),
        ("angry / anger", "kOpam", "'naaku kOpam vachchindi' = I got angry"), ("fear / scared", "bhayam", "'naaku bhayamgaa undi' = I'm scared"),
        ("surprise", "aashcharyam", ""), ("love", "prEma", ""), ("like (it's dear to me)", "ishTam", "'naaku _biryani ishTam' = I like biryani"),
        ("tired", "alasipOyaanu", "= I'm tired"), ("sleepy (sleep)", "nidra", "'naaku nidra vastOndi' = I'm sleepy"),
        ("bored", "_bore", "'naaku _bore koDutOndi' = I'm bored"), ("worry / tension", "_tension", "very Hyderabad: '_tension paDaku' = don't worry"),
        ("shy", "siggu", ""), ("proud", "garvam", ""),
    ],
    "🐾 Animals & nature": [
        ("dog", "kukka", ""), ("cat", "pilli", ""), ("cow", "aavu", ""), ("buffalo", "barre", ""), ("goat", "mEka", ""), ("hen", "kODi", ""),
        ("bird", "pakshi", ""), ("crow", "kaaki", ""), ("parrot", "chilaka", ""), ("monkey", "kOti", ""), ("elephant", "Enugu", ""),
        ("snake", "paamu", ""), ("horse", "gurram", ""), ("lion", "simham", ""), ("tiger", "puli", ""), ("mosquito", "dOma", ""),
        ("tree", "cheTTu", ""), ("flower", "puvvu", ""), ("leaf", "aaku", ""), ("sun / sunshine", "enDa", "'enDa ekkuvagaa undi' = it's very sunny/hot"),
        ("rain", "vaana", "'vaana paDutOndi' = it's raining"), ("wind", "gaali", ""), ("sky", "aakaasham", ""), ("moon", "chandamaama", ""),
        ("star", "chukka", ""), ("river", "nadi", ""), ("sea", "samudram", ""), ("lake", "cheruvu", "Hyderabad has many 'cheruvulu'"),
        ("hill", "konDa", ""), ("weather (cold)", "chali", "'chaligaa undi' = it's cold"),
    ],
    "💼 Work, study & money": [
        ("work / job", "pani", "'pani undi' = I have work"), ("job", "uddyOgam", "most say '_job'"), ("office", "_office", ""),
        ("salary", "jeetam", "most say '_salary'"), ("money", "Dabbulu / paisalu", "'paisalu' is very common in Hyderabad"),
        ("rupees", "rupaayalu", ""), ("change (coins)", "chillara", "'chillara lEdu' = I have no change"), ("price", "dhara", "most say '_rate'"),
        ("expensive / too much", "ekkuva", ""), ("cheap", "takkuva", ""), ("book", "pustakam", ""), ("pen", "_pen", ""),
        ("exam", "pariiksha", "most say '_exam'"), ("lesson", "paaTham", ""), ("word", "maaTa", ""), ("language", "bhaasha", ""),
        ("name", "pEru", ""), ("age", "vayasu", ""), ("leave / holiday", "selavu", "most say '_leave'"), ("festival", "panDaga", ""),
    ],
    "✅ Small useful words": [
        ("yes", "avunu", "also 'haa'"), ("no (it's not)", "kaadu", ""), ("no (there isn't / didn't)", "lEdu", ""),
        ("don't want / no thanks", "vaddu", ""), ("okay", "sarE", "also 'sarle' (casual) or '_ok'"), ("please", "dayachEsi", "in speech, saying '-anDi' at the end is the 'please'"),
        ("thank you", "dhanyavaadaalu", "in everyday Hyderabad speech: '_thanks'"), ("sorry", "kshaminchanDi", "in everyday speech: '_sorry'"),
        ("again", "mallee", ""), ("also / too", "kooDaa", ""), ("only", "maatramE", ""), ("still / more", "inkaa", ""), ("all", "anni", ""),
        ("every", "prati", "'prati rOju' = every day"), ("but", "kaani", ""), ("or", "lEdaa", "'_tea lEdaa _coffee?' = tea or coffee?"),
        ("and", "mariyu", "formal · in speech people say 'inka' or just list the words"), ("because", "endukanTE", ""), ("if", "-tE", "'vastE' = if (you) come"),
        ("maybe", "bahushaa", ""), ("really? / is it true?", "nijamaa?", ""), ("of course", "tappakunDaa", ""), ("enough", "chaalu", ""),
        ("wow / great", "bhale", ""), ("awesome!", "kEka!", "Telugu slang"), ("oh no!", "ayyO!", ""),
    ],
}

# ================================ NUMBERS ================================
_UNITS = {1: "okaTi", 2: "renDu", 3: "mooDu", 4: "naalugu", 5: "aidu", 6: "aaru", 7: "EDu", 8: "enimidi", 9: "tommidi"}
_TEENS = {10: "padi", 11: "padakonDu", 12: "panneNDu", 13: "padamooDu", 14: "padnaalugu", 15: "padihEnu", 16: "padahaaru",
          17: "padihEDu", 18: "paddenimidi", 19: "pantommidi"}
_TENS = {20: "iravai", 30: "muppai", 40: "nalabhai", 50: "yaabhai", 60: "aravai", 70: "Debbai", 80: "enabhai", 90: "tombhai"}


def number_te(n: int) -> str:
    if n < 10:
        return _UNITS[n]
    if n < 20:
        return _TEENS[n]
    if n < 100:
        t, u = (n // 10) * 10, n % 10
        return _TENS[t] + (" " + _UNITS[u] if u else "")
    if n == 100:
        return "vanda"
    raise ValueError(n)


BIG_NUMBERS = [(100, "vanda", ""), (200, "renDu vandalu", ""), (300, "mooDu vandalu", ""), (500, "aidu vandalu", ""),
               (1000, "veyyi", ""), (2000, "renDu vElu", ""), (5000, "aidu vElu", ""), (10000, "padi vElu", ""),
               (100000, "laksha", "1 lakh = 100,000"), (10000000, "kOTi", "1 crore = 10 million"),
               (250, "renDu vandala yaabhai", "250"), (1500, "veyyi aidu vandalu", "1,500")]
MONEY_EXAMPLES = [("aidu vandala rupaayalu", "500 rupees"), ("vanda rupaayalu", "100 rupees"),
                  ("idi enta? — yaabhai rupaayalu", "How much is this? — 50 rupees"),
                  ("renDu kilOlu ivvanDi", "Please give me 2 kilos"), ("mooDu chai ivvanDi", "Three teas, please")]
COUNT_PEOPLE = [("okkaru", "one person"), ("iddaru", "two people"), ("mugguru", "three people"), ("naluguru", "four people"),
                ("aiduguru", "five people")]

# ============================ PREPOSITIONS ============================
# In Telugu these little words go AFTER the word (amma tO = with mum). (English, Telugu, example Telugu, example English)
PREPOSITIONS = [
    ("in / at (inside)", "lO", "amma vanTagadi lO undi", "Mum is in the kitchen."),
    ("to / for (a person)", "ki / ku", "nEnu _office ki veLtunnaanu", "I'm going to the office."),
    ("with", "tO", "nEnu _friends tO vachchaanu", "I came with friends."),
    ("from / since", "nunchi", "nEnu _Australia nunchi vachchaanu", "I came from Australia."),
    ("for (the sake of)", "kOsam", "idi nee kOsam", "This is for you."),
    ("about", "gurinchi", "nEnu _Hyderabad gurinchi chaduvutunnaanu", "I'm reading about Hyderabad."),
    ("on / on top of", "meeda", "pustakam _table meeda undi", "The book is on the table."),
    ("above / over / up", "paina", "_fan paina undi", "The fan is up above."),
    ("under / below / down", "kinda", "pilli mancham kinda undi", "The cat is under the bed."),
    ("near / at (someone's place)", "daggara", "nEnu _bus _stop daggara unnaanu", "I'm near the bus stop."),
    ("next to / beside", "pakkana", "naa pakkana kuurchO", "Sit next to me."),
    ("in front of / before", "mundu", "illu mundu _car undi", "There's a car in front of the house."),
    ("behind", "venaka", "illu venaka _park undi", "There's a park behind the house."),
    ("after", "tarvaata", "_class tarvaata kaluddaam", "Let's meet after class."),
    ("before (time)", "mundu", "bhOjanam mundu chEtulu kaDukkOvaali", "You must wash your hands before eating."),
    ("between / among / in the middle", "madhyalO", "iddari madhyalO kuurchO", "Sit between the two of them."),
    ("around", "chuTTuu", "illu chuTTuu cheTlu unnaayi", "There are trees around the house."),
    ("opposite / facing", "edurugaa", "_bank edurugaa _ATM undi", "There's an ATM opposite the bank."),
    ("outside", "bayaTa", "pillalu bayaTa aaDukunTunnaaru", "The children are playing outside."),
    ("inside", "lOpala", "lOpala kuurchOnDi", "Please sit inside."),
    ("into (going inside)", "lOpaliki", "lOpaliki ranDi", "Please come in."),
    ("up to / until / till", "varaku", "saayantram varaku _office lO unTaanu", "I'll be in the office until evening."),
    ("towards", "vaipu", "_station vaipu veLLanDi", "Go towards the station."),
    ("through", "gunDaa", "_park gunDaa veLLanDi", "Go through the park."),
    ("across / on the other side", "avatala", "rODDu avatala _shop undi", "The shop is across the road."),
    ("like / as", "laagaa", "vaaDu _hero laagaa unnaaDu", "He looks like a hero."),
    ("than", "kanTE", "idi daani kanTE pedda", "This is bigger than that."),
    ("per / each", "ki", "kilO ki vanda rupaayalu", "100 rupees per kilo."),
    ("without", "lEkunDaa", "chakkera lEkunDaa _tea ivvanDi", "Tea without sugar, please."),
    ("instead of", "baduluga", "_tea baduluga _coffee ivvanDi", "Coffee instead of tea, please."),
    ("because of", "valla", "vaana valla _late ayyindi", "It got late because of the rain."),
    ("except", "tappa", "aadivaaram tappa prati rOju _office", "Office every day except Sunday."),
    ("during / at the time of", "samayamlO", "vaana samayamlO bayaTiki veLLaku", "Don't go out during the rain."),
    ("according to", "prakaaram", "_plan prakaaram chEddaam", "Let's do it according to the plan."),
    ("on behalf of", "taraphuna", "naa taraphuna _thanks cheppu", "Say thanks on my behalf."),
    ("even if / in spite of", "-inaa", "vaana vachchinaa nEnu vastaanu", "Even if it rains, I'll come."),
    ("far from", "ki dooramgaa", "maa illu _office ki dooramgaa undi", "Our house is far from the office."),
    ("close to", "ki daggaragaa", "maa illu _station ki daggaragaa undi", "Our house is close to the station."),
    ("of ('s)", "-di / yokka", "idi _Narayana di", "This is Narayana's. ('yokka' is formal, rarely spoken)"),
]
POINTING_WORDS = [("this (thing)", "idi"), ("that (thing)", "adi"), ("these", "ivi"), ("those", "avi"),
                  ("this … (before a noun)", "ee"), ("that … (before a noun)", "aa"), ("here", "ikkaDa"), ("there", "akkaDa")]

# ================================ PHRASES ================================
# Everyday Hyderabad Telugu. (English, Telugu, tip)
PHRASES = {
    "👋 Hello & goodbye": [
        ("Hello (respectful)", "namaskaaram", "say it with folded hands to elders"),
        ("How are you? (respectful)", "elaa unnaaru?", ""),
        ("How are you? (to a friend)", "elaa unnaavu?", "in speech: 'ela unnav?'"),
        ("I'm fine. And you?", "baagunnaanu. meeru?", "casual: 'baagunna, nuvvu?'"),
        ("What's up? / What's new?", "Em sangati?", "very Hyderabad"),
        ("What are you doing?", "Em chEstunnaavu?", "friends use this as 'hi!' — 'em chestunnav?'"),
        ("Is everything OK?", "anta _ok naa?", ""),
        ("Have you eaten?", "bhOjanam chEsaaraa?", "a common, caring way to greet someone"),
        ("Long time no see!", "chaala rOjulayyindi!", ""),
        ("Nice to meet you", "mimmalni kalavaDam santOshamgaa undi", ""),
        ("Good morning", "_good _morning", "people in Hyderabad just say it in English"),
        ("See you tomorrow", "rEpu kaluddaam", ""),
        ("Let's meet again", "mallee kaluddaam", ""),
        ("Bye — I'll go and come back", "veLLostaanu", "the polite Telugu goodbye"),
        ("Bye! (casual)", "vastaa / Ostaa", "'Ostaa' is the Hyderabad way — literally 'I'll come'"),
        ("Take care", "jaagrattagaa unDanDi", "casual: 'jaagratta'"),
        ("Thank you", "_thanks", "formal: 'dhanyavaadaalu'"),
        ("You're welcome / no problem", "paravaaledu", ""),
        ("Sorry", "_sorry", "formal: 'kshaminchanDi'"),
    ],
    "🙋 About me": [
        ("My name is Narayana", "naa pEru _Narayana", ""),
        ("What's your name? (respectful)", "mee pEru Enti?", ""),
        ("What's your name? (to a friend)", "nee pEru Enti?", ""),
        ("I'm 20 years old", "naaku iravai ELLu", "literally 'to me 20 years'"),
        ("I came from Australia", "nEnu _Australia nunchi vachchaanu", "Hyderabad: 'vachchina'"),
        ("I live in Brisbane", "nEnu _Brisbane lO unTaanu", ""),
        ("I'm a student", "nEnu _student ni", ""),
        ("I work", "nEnu _job chEstunnaanu", ""),
        ("I'm learning Telugu", "nEnu _Telugu nErchukunTunnaanu", ""),
        ("I know a little Telugu", "naaku _Telugu konchem vachchu", "'vachchu' = I know how to (a skill)"),
        ("I'm new to Hyderabad", "nEnu _Hyderabad ki kotta", ""),
        ("Where do you live?", "meeru ekkaDa unTaaru?", ""),
        ("What do you do (for work)?", "meeru Em chEstaaru?", ""),
        ("Where is your home town?", "mee ooru Edi?", ""),
        ("I like Hyderabad a lot", "naaku _Hyderabad chaala ishTam", ""),
        ("How many people in your family?", "mee intlO enta mandi unnaaru?", ""),
        ("There are four of us at home", "maa intlO naluguru unnaamu", ""),
    ],
    "🗣️ When you don't understand": [
        ("I didn't understand", "naaku artham kaalEdu", "the most useful sentence for a learner!"),
        ("I understood", "naaku artham ayyindi", ""),
        ("Please say it again", "mallee cheppanDi", ""),
        ("Please speak slowly", "konchem nemmadigaa maaTlaaDanDi", ""),
        ("What does that mean?", "daaniki artham Enti?", ""),
        ("How do you say ___ in Telugu?", "_Telugu lO ___ ni Emantaaru?", ""),
        ("Do you speak English?", "meeru _English maaTlaaDataaraa?", ""),
        ("I don't know", "naaku teliyadu", ""),
        ("I know", "naaku telusu", ""),
        ("Can you help me?", "konchem _help chEstaaraa?", ""),
        ("One minute, please", "oka nimisham", ""),
        ("Is that right?", "adi _correct aa?", ""),
    ],
    "🍛 Food & eating out": [
        ("I'm hungry", "naaku aakali vEstOndi", ""),
        ("I'm thirsty", "naaku daaham vEstOndi", ""),
        ("Let's eat biryani", "_biryani tindaam", ""),
        ("Shall we have tea?", "_chai taagudaamaa?", ""),
        ("I want ___", "naaku ___ kaavaali", ""),
        ("I don't want ___", "naaku ___ vaddu", ""),
        ("Some water, please", "konchem neeLLu ivvanDi", ""),
        ("Less spicy, please", "kaaram takkuva peTTanDi", ""),
        ("It's very tasty", "chaala ruchigaa undi", ""),
        ("It's too spicy!", "kaaram ekkuvagaa undi!", ""),
        ("I'm full", "kaDupu ninDindi", ""),
        ("One more tea", "inkO _chai", ""),
        ("The bill, please", "_bill ivvanDi", ""),
        ("I'm vegetarian", "nEnu _vegetarian ni", ""),
        ("Have a little more (to a guest)", "inkonchem teesukOnDi", ""),
    ],
    "🛒 Shopping & money": [
        ("How much is this?", "idi enta?", ""),
        ("That's too expensive", "chaala ekkuva", ""),
        ("Please reduce it a little", "konchem taggiMchanDi", ""),
        ("What's the last price?", "_last _price enta?", "every Hyderabad shopper asks this!"),
        ("Do you have another colour?", "vEre rangu undaa?", ""),
        ("Bigger size / smaller size", "pedda _size / chinna _size", ""),
        ("I'll pay by UPI", "_UPI chEstaanu", "or '_PhonePe chEstaa'"),
        ("I don't have change", "naa daggara chillara lEdu", ""),
        ("Give me a bag, please", "oka sanchi ivvanDi", ""),
        ("I'll take this", "idi teesukunTaanu", ""),
        ("Just looking", "_just chuustunnaanu", ""),
    ],
    "🛺 Auto, cab & directions": [
        ("Will you come to ___? (to an auto driver)", "___ ki vastaaraa?", ""),
        ("Will you go by the meter?", "_meter vEstaaraa?", ""),
        ("How much will it be?", "enta avutundi?", ""),
        ("Stop here, please", "ikkaDa aapanDi", ""),
        ("Turn left / turn right", "_left teesukOnDi / _right teesukOnDi", ""),
        ("Go straight", "_straight veLLanDi", ""),
        ("Where is ___?", "___ ekkaDa undi?", ""),
        ("How far is it from here?", "ikkaDi nunchi enta dooram?", ""),
        ("Is there a ___ nearby?", "daggaralO ___ undaa?", ""),
        ("How do I get to the metro station?", "_metro _station ki elaa veLLaali?", ""),
        ("I'm lost", "nEnu daari tappipOyaanu", ""),
        ("There's a lot of traffic", "_traffic chaala undi", ""),
        ("Please go slowly", "nemmadigaa veLLanDi", ""),
    ],
    "🤝 Friends & going out": [
        ("Are you free?", "nuvvu _free gaa unnaavaa?", ""),
        ("I'm busy", "nEnu _busy gaa unnaanu", ""),
        ("What shall we do?", "Em chEddaam?", ""),
        ("Shall we go out?", "bayaTiki pOdaamaa?", ""),
        ("Let's go to a movie", "_movie ki pOdaam", ""),
        ("Come quickly!", "tvaragaa raa!", ""),
        ("I'm on my way", "_on _the _way lO unnaanu", "Hyderabad mixes English like this all the time"),
        ("Wait for me", "naa kOsam aagu", ""),
        ("I'll call you later", "tarvaata _call chEstaanu", ""),
        ("Send me a message", "naaku _message peTTu", ""),
        ("Don't worry!", "_tension paDaku!", "very common in Hyderabad"),
        ("Awesome!", "kEka!", ""),
        ("Really?", "nijamaa?", ""),
        ("What happened?", "Emaindi?", ""),
        ("Nothing (it's nothing)", "Em lEdu", ""),
        ("Bro, where to? (to a friend)", "anna, ekkaDiki?", "'anna' = elder brother; used for any guy older than you"),
    ],
    "🏠 At home & visiting": [
        ("Please come in", "lOpaliki ranDi", ""),
        ("Please sit down", "kuurchOnDi", ""),
        ("What will you drink? Tea or coffee?", "Em taagutaaru? _tea lEdaa _coffee?", ""),
        ("Your house is very nice", "mee illu chaala baagundi", ""),
        ("Please come again", "mallee ranDi", ""),
        ("I'm going home", "nEnu intiki pOtunnaanu", ""),
        ("Where's the bathroom?", "_bathroom ekkaDa undi?", ""),
        ("Switch on the fan", "_fan vEyi", ""),
        ("Switch off the light", "_light aapEyi", ""),
        ("I'm going to sleep", "nEnu paDukunTunnaanu", ""),
    ],
    "🏥 Health & help": [
        ("I'm not feeling well", "naaku ollu baagOlEdu", ""),
        ("I have a headache", "naaku tala noppigaa undi", ""),
        ("I have a fever", "naaku jvaram vachchindi", ""),
        ("My stomach hurts", "naaku kaDupu noppigaa undi", ""),
        ("I need a doctor", "naaku _doctor kaavaali", ""),
        ("Where is the hospital?", "_hospital ekkaDa undi?", ""),
        ("Help!", "kaapaaDanDi!", ""),
        ("Please call the police", "_police ni pilavanDi", ""),
    ],
    "😊 Feelings": [
        ("I'm happy", "naaku santOshamgaa undi", ""),
        ("I'm tired", "nEnu alasipOyaanu", ""),
        ("I'm sleepy", "naaku nidra vastOndi", ""),
        ("I'm bored", "naaku _bore koDutOndi", ""),
        ("I'm scared", "naaku bhayamgaa undi", ""),
        ("I got angry", "naaku kOpam vachchindi", ""),
        ("I feel sad", "naaku baadhagaa undi", ""),
        ("I like it a lot", "naaku chaala ishTam", ""),
        ("I don't like it", "naaku ishTam lEdu", ""),
    ],
    "⏰ Time & plans": [
        ("What's the time?", "_time enta ayyindi?", ""),
        ("It's two o'clock", "renDu ganTalu ayyindi", ""),
        ("What are you doing today?", "ivvaala Em chEstunnaavu?", ""),
        ("I'll come tomorrow", "nEnu rEpu vastaanu", ""),
        ("I'm late", "naaku _late ayyindi", ""),
        ("I have no time", "naaku _time lEdu", ""),
        ("Today I have work", "ivvaala naaku pani undi", ""),
        ("It's finished / done", "ayipOyindi", ""),
        ("Not yet", "inkaa lEdu", ""),
    ],
}

# Short real-life conversations (speaker, Telugu, English)
CONVERSATIONS = {
    "☕ Meeting a new friend": [
        ("Friend", "namaskaaram! mee pEru Enti?", "Hello! What's your name?"),
        ("Narayana", "naa pEru _Narayana. mee pEru?", "My name is Narayana. Yours?"),
        ("Friend", "naa pEru _Ravi. meeru ekkaDi nunchi vachchaaru?", "My name is Ravi. Where are you from?"),
        ("Narayana", "nEnu _Australia nunchi vachchaanu. _Telugu nErchukunTunnaanu.", "I came from Australia. I'm learning Telugu."),
        ("Friend", "bhale! mee _Telugu baagundi.", "Great! Your Telugu is good."),
        ("Narayana", "_thanks! konchem nemmadigaa maaTlaaDanDi.", "Thanks! Please speak a little slowly."),
        ("Friend", "sarE. _chai taagudaamaa?", "Okay. Shall we have tea?"),
        ("Narayana", "tappakunDaa! pOdaam.", "Of course! Let's go."),
    ],
    "🛺 Taking an auto": [
        ("Narayana", "anna, _Charminar ki vastaaraa?", "Anna, will you come to Charminar?"),
        ("Driver", "vastaanu. renDu vandalu.", "I'll come. Two hundred."),
        ("Narayana", "chaala ekkuva. _meter vEstaaraa?", "That's too much. Will you go by the meter?"),
        ("Driver", "_meter lEdu. vanda yaabhai ivvanDi.", "No meter. Give one-fifty."),
        ("Narayana", "sarE, ekkanDi… ikkaDa aapanDi.", "Okay… (later) Stop here, please."),
        ("Driver", "_UPI aa, _cash aa?", "UPI or cash?"),
        ("Narayana", "_UPI chEstaanu. _thanks anna!", "I'll pay by UPI. Thanks, anna!"),
    ],
    "🍛 At a restaurant": [
        ("Waiter", "Em kaavaali _sir?", "What would you like, sir?"),
        ("Narayana", "oka _chicken _biryani, kaaram takkuva.", "One chicken biryani, less spicy."),
        ("Waiter", "taagaDaaniki Emainaa?", "Anything to drink?"),
        ("Narayana", "oka _Irani _chai. konchem neeLLu kooDaa ivvanDi.", "One Irani chai. Some water too, please."),
        ("Waiter", "sarE _sir.", "Okay, sir."),
        ("Narayana", "chaala ruchigaa undi! _bill ivvanDi.", "It's very tasty! The bill, please."),
    ],
    "🛒 Shopping": [
        ("Narayana", "anna, ee _shirt enta?", "Anna, how much is this shirt?"),
        ("Shopkeeper", "EDu vandalu.", "Seven hundred."),
        ("Narayana", "chaala ekkuva. _last _price enta?", "Too much. What's the last price?"),
        ("Shopkeeper", "aaru vandalu ivvanDi.", "Give six hundred."),
        ("Narayana", "aidu vandalu ayitE teesukunTaanu.", "I'll take it for five hundred."),
        ("Shopkeeper", "sarE, teesukOnDi.", "Okay, take it."),
    ],
    "📞 A phone call": [
        ("Narayana", "_hello, _Ravi naa?", "Hello, is this Ravi?"),
        ("Ravi", "haa, cheppu _Narayana. Em sangati?", "Yes, tell me Narayana. What's up?"),
        ("Narayana", "ivvaala saayantram _free gaa unnaavaa?", "Are you free this evening?"),
        ("Ravi", "_free ee. Em chEddaam?", "Yes, I'm free. What shall we do?"),
        ("Narayana", "_movie ki pOdaam. aaru ganTalaki kaluddaam.", "Let's go to a movie. Let's meet at 6."),
        ("Ravi", "sarE! _location peTTu.", "Okay! Send the location."),
    ],
}

# ================================ GRAMMAR BASICS ================================
GRAMMAR = [
    ("1 · Word order: the verb goes LAST",
     "English says *I ate rice*. Telugu says *I rice ate*.",
     [("nEnu annam tinnaanu", "I ate rice (I · rice · ate)"), ("vaaDu _office ki veLtunnaaDu", "He is going to the office (he · office-to · going)")]),
    ("2 · Questions: just add '-aa'",
     "Turn any sentence into a yes/no question by adding **-aa** to the end.",
     [("meeru vastaaru", "You will come."), ("meeru vastaaraa?", "Will you come?"), ("idi baagundaa?", "Is this good?")]),
    ("3 · 'Is / am / are' — often no word at all!",
     "For *who/what something is*, Telugu simply puts two words together. For *where someone is* or *how someone is*, use **unnaanu / unnaavu / unnaaDu / undi / unnaaru**.",
     [("naa pEru _Narayana", "My name (is) Narayana."), ("idi naa illu", "This (is) my house."),
      ("nEnu intlO unnaanu", "I am at home."), ("aame baagundi", "She is well."), ("meeru ekkaDa unnaaru?", "Where are you?")]),
    ("4 · 'Not': kaadu, lEdu and vaddu",
     "**kaadu** = it is not (that thing) · **lEdu** = there isn't / didn't / don't have · **vaddu** = I don't want / don't.",
     [("idi naa _bag kaadu", "This is not my bag."), ("naa daggara Dabbulu lEvu", "I don't have money."),
      ("nEnu tinalEdu", "I didn't eat."), ("naaku _sugar vaddu", "I don't want sugar.")]),
    ("5 · I have / I want / I like / I know — start with 'naaku' (to me)",
     "Telugu says *to me there is*, *to me it's needed*, and so on.",
     [("naaku oka _car undi", "I have a car."), ("naaku neeLLu kaavaali", "I want water."), ("naaku _biryani ishTam", "I like biryani."),
      ("naaku _Telugu vachchu", "I know (how to speak) Telugu."), ("naaku telusu", "I know (that fact)."), ("naaku teliyadu", "I don't know.")]),
    ("6 · Respect: nuvvu or meeru?",
     "Use **meeru** (and verbs ending in **-aaru**) with elders, strangers and anyone you respect. Use **nuvvu** with close friends and younger people. Add **-anDi** to make a request polite, and **gaaru** after a name for respect (*Ravi gaaru*).",
     [("nuvvu raa", "You come. (to a friend)"), ("meeru ranDi", "Please come. (respectful)"), ("aayana vachchaaru", "He has come. (respectful)"),
      ("vaaDu vachchaaDu", "He has come. (casual)")]),
    ("7 · Must · can · can't",
     "Add **-aali** for *must*, **-galanu** for *can*, **-lEnu** for *can't* (see each verb's table for the exact form).",
     [("nEnu veLLaali", "I must go."), ("nEnu _Telugu maaTlaaDagalanu", "I can speak Telugu."), ("nEnu raalEnu", "I can't come.")]),
    ("8 · The little endings (like English prepositions)",
     "They stick to the END of the word: **-lO** in · **-ki/-ku** to · **-tO** with · **nunchi** from · **kOsam** for · **-ni** (the person/thing you act on).",
     [("_office lO", "in the office"), ("intiki", "to home"), ("amma tO", "with mum"), ("_Delhi nunchi", "from Delhi"), ("amma ni pilu", "call mum")]),
    ("9 · The Hyderabad trick: English word + chEyyi",
     "In Hyderabad, people take an English verb and add **chEyyi** (do). Use the 'do' table for every tense!",
     [("nEnu _call chEstaanu", "I'll call."), ("_book chEsaanu", "I booked (it)."), ("_start chEddaam", "Let's start."),
      ("_try cheyyi", "Try it.")]),
    ("10 · Everyday short forms",
     "In speech the endings get shorter: **tinnaanu → tinna** (I ate), **vastaanu → vasta** (I'll come), **chEstunnaavu → chEstunnav** (you're doing). The verb tables show both.",
     [("nEnu vasta", "I'll come. (spoken)"), ("Em chEstunnav?", "What are you doing? (spoken)")]),
]

# A few Hyderabad specials for the Home page
HYD_TIPS = [
    "In Hyderabad people mix in lots of English: '_office ki veLtunnaa', '_bill ivvanDi', '_tension paDaku'. That's normal!",
    "Call any older man 'anna' and any older woman 'akka' — it's friendly and polite.",
    "'Ostaa' (I'll come) is how Hyderabadis say bye. The full form is 'vastaanu'.",
    "Add '-anDi' to a request to make it polite: 'ivvu' (give) → 'ivvanDi' (please give).",
    "'ivvaala' is the Hyderabad word for today (textbook: 'eeroju').",
    "'banDi' means any vehicle — usually a bike. 'banDi meeda vachchaanu' = I came by bike.",
    "When you don't understand, say: 'naaku artham kaalEdu, mallee cheppanDi'.",
    "'Em sangati?' = what's up? A perfect casual greeting.",
]

# ================================ ONLINE DICTIONARY ================================
def _translate_google(q: str):
    from deep_translator import GoogleTranslator
    return GoogleTranslator(source="en", target="te").translate(q)


def _translate_mymemory(q: str):
    r = requests.get("https://api.mymemory.translated.net/get", params={"q": q, "langpair": "en|te"}, timeout=6)
    r.raise_for_status()
    return r.json()["responseData"]["translatedText"]


@st.cache_data(show_spinner=False, max_entries=5000, ttl=60 * 60 * 24 * 7)
def _online_cached(q: str):
    import concurrent.futures as cf
    answered = False
    for fn in (_translate_google, _translate_mymemory):
        try:
            with cf.ThreadPoolExecutor(max_workers=1) as ex:
                te = ex.submit(fn, q).result(timeout=7)
            answered = True
            if te and TELUGU_RE.search(te):
                return te.strip()
        except Exception:
            continue
    if answered:
        return None
    raise ConnectionError("online dictionary not reachable")


def online_telugu(q: str):
    import time
    if time.time() < st.session_state.get("online_pause_until", 0):
        return None
    try:
        return _online_cached(q.strip().lower())
    except ConnectionError:
        st.session_state.online_pause_until = time.time() + 30
        return None
    except Exception:
        return None


# ===================================== STYLE =====================================
CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Poppins:wght@500;600;700&family=Inter:wght@400;500;600&display=swap');
:root { --ink:#23255e; --gold:#e9a21a; --teal:#0f7f81; --cream:#fbf6ec; --muted:#6c6a80; --line:#ece3cf; }
.stApp { background: radial-gradient(circle at 0% 0%, #fff4d8 0, transparent 35%),
  radial-gradient(circle at 100% 10%, #e6f3f2 0, transparent 35%), var(--cream); }
html, body, p, li, label, input, textarea, .stMarkdown, [data-baseweb="tab"] p { font-family: 'Inter', system-ui, sans-serif; }
h1, h2, h3 { font-family: 'Poppins', system-ui, sans-serif !important; color: var(--ink) !important; }
.block-container { max-width: 900px; padding-top: 1.6rem; }
.hero { border-radius: 24px; padding: 20px 22px; color: #fff; margin-bottom: 10px;
  background: linear-gradient(135deg, #23255e 0%, #343884 60%, #0f7f81 130%); box-shadow: 0 10px 30px rgba(35,37,94,.25); }
.hero .brand { font-family: Poppins, sans-serif; font-size: 2rem; font-weight: 700; line-height: 1.1; }
.hero .brand span { color: #ffd27a; }
.hero .tag { opacity: .85; font-size: .98rem; margin-top: 2px; }
.hero .hi { margin-top: 12px; font-size: 1.15rem; font-weight: 600; }
.pill { display: inline-block; margin: 8px 6px 0 0; padding: 4px 12px; border-radius: 999px; font-size: .88rem;
  background: rgba(255,255,255,.14); border: 1px solid rgba(255,255,255,.25); }
.card { background: #fff; border: 1px solid var(--line); border-radius: 16px; padding: 12px 16px; margin: 4px 0;
  box-shadow: 0 2px 8px rgba(35,37,94,.04); }
.en { color: var(--muted); font-size: .9rem; }
.te { color: var(--ink); font-size: 1.28rem; font-weight: 700; font-family: Poppins, sans-serif; line-height: 1.3; }
.note { color: #8a6a1a; font-size: .86rem; margin-top: 2px; }
.big { font-size: 2rem; }
.feature { background: #fff; border-left: 5px solid var(--gold); border-radius: 14px; padding: 12px 16px; margin: 6px 0; }
.feature .lbl { font-size: .8rem; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--teal); }
.tip { background: #eef7f6; border-radius: 12px; padding: 10px 14px; color: #0b5556; margin: 6px 0; }
.scroll { overflow-x: auto; -webkit-overflow-scrolling: touch; }
table.vt { border-collapse: separate; border-spacing: 0; width: 100%; min-width: 760px; background: #fff;
  border: 1px solid var(--line); border-radius: 14px; overflow: hidden; font-size: .92rem; }
table.vt th, table.vt td { padding: 8px 8px; text-align: center; border-bottom: 1px solid #f3ecdc; border-right: 1px solid #f3ecdc; }
table.vt th { background: #f7f2e6; color: var(--ink); font-weight: 600; }
table.vt th.grp { background: var(--ink); color: #fff; }
table.vt th.grp.g2 { background: #3a3f96; } table.vt th.grp.g3 { background: var(--teal); }
table.vt td.tense { font-weight: 700; color: var(--ink); background: #fffaf0; text-align: left; white-space: nowrap; }
table.vt td b { color: var(--ink); font-size: 1rem; }
table.vt td small { display: block; color: #9a97ab; font-size: .76rem; margin-top: 2px; }
.speaker { font-weight: 700; color: var(--teal); }
.numgrid { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 6px; }
.numgrid div { background: #fff; border: 1px solid var(--line); border-radius: 10px; padding: 6px 10px; font-size: .92rem; }
.numgrid b { color: var(--teal); margin-right: 6px; }
.q { font-family: Poppins, sans-serif; font-size: 1.5rem; color: var(--ink); font-weight: 600; margin: 4px 0 8px; }
div[data-testid="stButton"] button { border-radius: 12px; }
@media (max-width: 640px) {
  [data-testid="stHorizontalBlock"] { flex-wrap: nowrap !important; gap: .4rem !important; }
  [data-testid="stHorizontalBlock"] > [data-testid="stColumn"], [data-testid="stHorizontalBlock"] > [data-testid="column"] {
    min-width: 0 !important; }
  .te { font-size: 1.12rem; }
  .card { padding: 10px 12px; }
  div[data-testid="stButton"] button { padding: .3rem .4rem; min-height: 2.2rem; }
}
</style>
"""


# ====================================== DATA ======================================
if "data" not in st.session_state:
    try:
        st.session_state.data, st.session_state.sha = load_data()
    except Exception as e:
        st.session_state.data, st.session_state.sha = default_data(), None
        st.session_state.save_error = f"Couldn't load saved progress ({e})."
data = st.session_state.data
today = today_local()
TODAY_KEY = today.isoformat()

st.markdown(CSS, unsafe_allow_html=True)
install_audio_engine()

VERB_BY_EN = {v["en"]: v for v in VERBS}


def dict_form(v):
    """How a verb is listed: casual command form, e.g. tinu, cheyyi, raa."""
    NG = v["NG"]
    return v.get("pre", "") + v.get("CMD", NG if _ends_vowel(NG) else NG + "u")


def all_entries():
    """Everything searchable: (kind, English, Telugu, note)."""
    out = []
    for cat, items in WORDS.items():
        out += [("word", e, t, n or cat) for e, t, n in items]
    for cat, items in PHRASES.items():
        out += [("phrase", e, t, n or cat) for e, t, n in items]
    for v in VERBS:
        out.append(("verb", "to " + v["en"], dict_form(v), "verb — open 🔁 Verb tables for every tense"))
    for p in PREPOSITIONS:
        out.append(("little word", p[0], p[1], f"e.g. {show(p[2])} = {p[3]}"))
    for n in range(1, 101):
        out.append(("number", str(n), number_te(n), ""))
    for en, te in data.get("online_words", {}).items():
        out.append(("online", en, te, "🌐 looked up online"))
    return out


ENTRIES = all_entries()


def entry(en, te, note, key, slow=True):
    c1, c2 = st.columns([5, 2])
    c1.markdown(f'<div class="card"><div class="en">{htmlesc(en)}</div><div class="te">{htmlesc(show_cap(te))}</div>'
                + (f'<div class="note">💡 {htmlesc(show(note))}</div>' if note else "") + '</div>', unsafe_allow_html=True)
    with c2:
        st.write("")
        say_btns(te, key, slow)


def htmlesc(s):
    import html
    return html.escape(str(s)).replace("$", "&#36;")


def mdsafe(s):
    return str(s).replace("$", "\\$")


# ======================================= HERO =======================================
known = len(data.get("known", []))
answers_today = data.get("days", {}).get(TODAY_KEY, {}).get("answers", 0)
st.markdown(
    f'<div class="hero"><div class="brand">🪔 Pragna <span>Mitra</span></div><div class="tag">{TAGLINE} · '
    f'{STYLE_NOTE}</div><div class="hi">Namaskaaram, {htmlesc(LEARNER)}! 🙏</div>'
    f'<span class="pill">🔥 {streak(data, today)}-day streak</span>'
    f'<span class="pill">🎯 Today: {answers_today}/{DAILY_GOAL} practice answers</span>'
    f'<span class="pill">✅ {known} words &amp; phrases known</span></div>', unsafe_allow_html=True)
audio_holder = st.container()
play_queued(audio_holder)
if err := st.session_state.pop("save_error", None):
    st.warning(f"Progress couldn't be saved: {err}")

(tab_home, tab_phr, tab_verbs, tab_allv, tab_prep, tab_dict, tab_num, tab_gram, tab_prac, tab_prog) = st.tabs(
    ["🏠 Today", "💬 Phrases", "🔁 Verb tables", "📋 All verbs", "📍 Little words", "📖 Dictionary", "🔢 Numbers",
     "🧠 Grammar", "🎯 Practice", "📈 Progress"])


# ======================================= TODAY =======================================
with tab_home:
    rng = random.Random(today.toordinal())
    all_phr = [p for items in PHRASES.values() for p in items]
    all_wrd = [w for items in WORDS.values() for w in items]
    p_en, p_te, p_note = rng.choice(all_phr)
    w_en, w_te, w_note = rng.choice(all_wrd)
    v = rng.choice(VERBS)
    st.markdown('<div class="feature"><div class="lbl">💬 Phrase of the day</div></div>', unsafe_allow_html=True)
    entry(p_en, p_te, p_note, "home_p")
    st.markdown('<div class="feature"><div class="lbl">📖 Word of the day</div></div>', unsafe_allow_html=True)
    entry(w_en, w_te, w_note, "home_w")
    st.markdown(f'<div class="feature"><div class="lbl">🔁 Verb of the day · to {htmlesc(v["en"])} '
                f'({htmlesc(show(dict_form(v)))})</div></div>', unsafe_allow_html=True)
    for tn, tl in (("present", "I am …ing"), ("past", "I …ed"), ("future", "I will …")):
        full, spoken = conj(v, tn, "nEnu")
        entry(f"{tl} ({tn})", "nEnu " + spoken, f"full form: nEnu {full}", f"home_v_{tn}", slow=False)
    st.markdown(f'<div class="tip">🏙️ <b>Hyderabad tip:</b> {htmlesc(show(rng.choice(HYD_TIPS)))}</div>',
                unsafe_allow_html=True)
    with st.expander("🧭 How to use Pragna Mitra"):
        st.markdown(
            "1. **💬 Phrases** — start here. Learn whole sentences for real situations (auto, shop, friends, food).\n"
            "2. **🔁 Verb tables** — every verb in **Present · Past · Future** for **I, we, you, he, she, they** — "
            "casual and respectful. Tap 🔊 to hear a whole row.\n"
            "3. **📍 Little words** — Telugu's 'prepositions' (with, from, in, near…) with examples.\n"
            "4. **📖 Dictionary** — search any word; if it isn't built in, look it up online and save it.\n"
            "5. **🎯 Practice** — flashcards, quizzes and verb challenges. Aim for "
            f"**{DAILY_GOAL} answers a day** to keep your streak.\n\n"
            "🔊 = say it · 🐢 = say it slowly. Say every phrase out loud 3 times — speaking is how you learn!")


# ====================================== PHRASES ======================================
with tab_phr:
    st.markdown("### 💬 Everyday phrases")
    mode = st.radio("Show", ["Phrases by situation", "Real conversations"], horizontal=True, label_visibility="collapsed")
    if mode == "Phrases by situation":
        cat = st.selectbox("Situation", list(PHRASES), key="phr_cat")
        for i, (en, te, note) in enumerate(PHRASES[cat]):
            entry(en, te, note, f"phr_{cat}_{i}")
    else:
        conv = st.selectbox("Conversation", list(CONVERSATIONS), key="conv_pick")
        lines = CONVERSATIONS[conv]
        st.button("▶️ Play the whole conversation", on_click=queue_say,
                  args=(" . ".join(t for _, t, _ in lines),), key="conv_all")
        for i, (who, te, en) in enumerate(lines):
            c1, c2 = st.columns([5, 2])
            c1.markdown(f'<div class="card"><span class="speaker">{htmlesc(who)}:</span> '
                        f'<span class="te" style="font-size:1.12rem">{htmlesc(show_cap(te))}</span>'
                        f'<div class="en">{htmlesc(en)}</div></div>', unsafe_allow_html=True)
            with c2:
                st.write("")
                say_btns(te, f"conv_{conv}_{i}")
        st.caption("Practise: play a line, pause, and say the next line yourself before you hear it. 🎭")


# ==================================== VERB TABLES ====================================
def verb_table_html(v, tenses, show_full=True):
    groups = [("1st person", 2, "g1"), ("2nd person", 2, "g2"), ("3rd person", 4, "g3")]
    head1 = '<tr><th rowspan="2"></th>' + "".join(f'<th class="grp {c}" colspan="{n}">{g}</th>' for g, n, c in groups) + "</tr>"
    head2 = "<tr>" + "".join(f"<th>{htmlesc(show(p[1]))}<br><small style='font-weight:400;color:#7a7890'>{htmlesc(p[2])}</small></th>"
                             for p in PERSONS) + "</tr>"
    rows = ""
    for tkey, tlabel in tenses:
        cells = ""
        for p in PERSONS:
            full, spoken = conj(v, tkey, p[0])
            sub = f"<small>{htmlesc(show(full))}</small>" if show_full and full != spoken else ""
            cells += f"<td><b>{htmlesc(show(spoken))}</b>{sub}</td>"
        rows += f'<tr><td class="tense">{tlabel}</td>{cells}</tr>'
    return f'<div class="scroll"><table class="vt">{head1}{head2}{rows}</table></div>'


MAIN_TENSES = [("present", "Present<br><small>is …ing</small>"), ("past", "Past<br><small>…ed</small>"),
               ("future", "Future<br><small>will … / usually …</small>")]
NEG_TENSES = [("negative", "Won't / don't<br><small>(future & habit)</small>"), ("didnt", "Didn't<br><small>(same for all)</small>")]

with tab_verbs:
    st.markdown("### 🔁 Verb tables")
    st.caption("Bold = how people actually say it in Hyderabad · small grey = the full (textbook) form. "
               "Respectful 'aayana / aavida' and 'meeru' use the same endings as 'they'.")
    names = sorted(VERB_BY_EN, key=lambda x: x.lower())
    pick = st.selectbox("Choose a verb (type to search)", names, key="verb_pick",
                        format_func=lambda x: f"to {x}  —  {show(dict_form(VERB_BY_EN[x]))}")
    v = VERB_BY_EN[pick]
    show_full = st.toggle("Show the full textbook forms too", value=True, key="vt_full")
    st.markdown(f'<div class="feature"><div class="lbl">to {htmlesc(v["en"])}</div>'
                f'<div class="te big">{htmlesc(show(dict_form(v)))}</div></div>', unsafe_allow_html=True)
    st.markdown(verb_table_html(v, MAIN_TENSES, show_full), unsafe_allow_html=True)
    rc = st.columns(3)
    for col, (tkey, tname) in zip(rc, (("present", "Present"), ("past", "Past"), ("future", "Future"))):
        row = " , ".join(f"{p[1].split(' / ')[0]} {conj(v, tkey, p[0])[1]}" for p in PERSONS)
        col.button(f"🔊 {tname} row", key=f"vrow_{tkey}", on_click=queue_say, args=(row, True), use_container_width=True)
    st.caption("Each 🔊 row button says the whole row slowly: 'nenu …, memu …, nuvvu …' — repeat after it!")

    with st.expander("➖ Negatives: won't · didn't"):
        st.markdown(verb_table_html(v, NEG_TENSES, False), unsafe_allow_html=True)
        nb = st.columns(2)
        nb[0].button("🔊 Won't row", key="vrow_neg", on_click=queue_say, use_container_width=True,
                     args=(" , ".join(f"{p[1].split(' / ')[0]} {conj(v, 'negative', p[0])[0]}" for p in PERSONS), True))
        nb[1].button("🔊 Didn't (nEnu)", key="vrow_didnt", on_click=queue_say, use_container_width=True,
                     args=("nEnu " + conj(v, "didnt", "nEnu")[0], True))
    with st.expander("✨ Requests, must, can and more", expanded=True):
        for i, (lbl, form) in enumerate(extra_forms(v)):
            entry(lbl, form, "", f"vx_{pick}_{i}", slow=False)
    st.markdown("#### 🗨️ Examples")
    for i, (te, en) in enumerate(v["ex"]):
        entry(en, te, "", f"vex_{pick}_{i}")

    with st.expander(f"📋 All {len(VERBS)} verbs at a glance (for 'I')"):
        rows = "".join(
            f"<tr><td class='tense'>to {htmlesc(x['en'])}</td><td><b>{htmlesc(show(dict_form(x)))}</b></td>"
            + "".join(f"<td>{htmlesc(show(conj(x, t, 'nEnu')[1]))}</td>" for t in ("present", "past", "future"))
            + f"<td>{htmlesc(show(conj(x, 'negative', 'nEnu')[0]))}</td></tr>" for x in sorted(VERBS, key=lambda y: y["en"]))
        st.markdown('<div class="scroll"><table class="vt" style="min-width:640px"><tr><th>English</th><th>Verb</th>'
                    '<th>I am …ing</th><th>I …ed</th><th>I will …</th><th>I won\'t …</th></tr>'
                    f'{rows}</table></div>', unsafe_allow_html=True)
    st.markdown('<div class="tip">🏙️ Any English verb works too: add <b>chEyyi</b> (do) — '
                '“<b>call chestaanu</b>” (I\'ll call), “<b>book chesaanu</b>” (I booked). '
                'Use the <b>do</b> table for every tense.</div>', unsafe_allow_html=True)


# ================================== ALL VERBS (one big table) ==================================
ALLV_CSS = """<style>
@import url('https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@500;600;700&display=swap');
.allv-wrap { container-type: inline-size; width: 100%; }
table.avt { width: 100%; table-layout: fixed; border-collapse: separate; border-spacing: 0; background: #fff;
  border-radius: 14px; overflow: hidden; box-shadow: 0 4px 14px rgba(30,30,80,.07);
  font-family: 'Barlow Condensed', 'Avenir Next Condensed', 'Roboto Condensed', 'Arial Narrow', 'DejaVu Sans Condensed', sans-serif;
  font-stretch: condensed; }
table.avt col.c-verb { width: 10%; } table.avt col.c-tense { width: 4.6%; } table.avt col.c-p { width: 10.675%; }
table.avt th, table.avt td { padding: 4px 2px; text-align: center; vertical-align: middle; line-height: 1.12;
  border-bottom: 1px solid #f1ead9; border-right: 1px solid #f1ead9; overflow-wrap: anywhere; word-break: normal;
  font-size: clamp(8px, 1.5cqw, 14px); letter-spacing: -.01em; }
table.avt thead th { position: sticky; top: 0; z-index: 2; }
table.avt th.grp { color: #fff; font-weight: 700; font-size: clamp(9px, 1.7cqw, 15px); padding: 5px 2px; }
table.avt th.g1 { background: #23245e; } table.avt th.g2 { background: #3a3f96; } table.avt th.g3 { background: #0f7f7a; }
table.avt th.pp { background: #f7f2e6; color: #23245e; font-weight: 700; }
table.avt th.pp span { display: block; font-weight: 500; color: #7a7890; font-size: .82em; }
table.avt td.vb { text-align: left; padding-left: 5px; background: #fffaf0; font-weight: 700; color: #23245e;
  border-right: 2px solid #e8dcc0; }
table.avt td.vb span { display: block; font-weight: 500; color: #8a6d2f; font-size: .9em; margin-top: 2px; }
table.avt td.tn { font-weight: 700; color: #6b6890; background: #fbf8f1; font-size: clamp(8px, 1.45cqw, 13px); }
table.avt td.f { font-weight: 600; color: #1d1d3f; padding: 4px 1px; }
table.avt td.f .w { white-space: nowrap; }
table.avt td.f.s1 { font-size: clamp(7px, 1.32cqw, 13px); letter-spacing: -.015em; }
table.avt td.f.s2 { font-size: clamp(7px, 1.07cqw, 12px); letter-spacing: -.02em; }
table.avt td.f.s3 { font-size: clamp(6.5px, .98cqw, 11px); letter-spacing: -.025em; }
table.avt td.f.s4 { font-size: clamp(6.5px, .86cqw, 10px); letter-spacing: -.03em; }
@container (max-width: 560px) { table.avt td.f .w { white-space: normal; overflow-wrap: anywhere; } }
table.avt td.f small { display: block; color: #a29fb3; font-weight: 500; font-size: .82em; margin-top: 1px; }
table.avt tr.alt td.f { background: #fbfbff; }
table.avt tr.first td { border-top: 2px solid #e8dcc0; }
table.avt td.f.p1 { box-shadow: inset 3px 0 0 #23245e14; } table.avt td.f.p2 { box-shadow: inset 3px 0 0 #3a3f9614; }
.allv-legend { color: #6b6890; font-size: .9rem; margin: 2px 0 8px; }
</style>"""


def all_verbs_html(verbs, show_full):
    groups = [("1st person", 2, "g1"), ("2nd person", 2, "g2"), ("3rd person", 4, "g3")]
    cols = '<colgroup><col class="c-verb"><col class="c-tense">' + '<col class="c-p">' * len(PERSONS) + "</colgroup>"
    head = ('<thead><tr><th class="pp" rowspan="2">Verb</th><th class="pp" rowspan="2">Tense</th>'
            + "".join(f'<th class="grp {c}" colspan="{n}">{g}</th>' for g, n, c in groups) + "</tr><tr>"
            + "".join(f'<th class="pp">{htmlesc(show(p[1]))}<span>{htmlesc(p[2].replace(" (respectful / all of you)", " (resp.)").replace(" (respectful)", " (resp.)"))}</span></th>'
                      for p in PERSONS) + "</tr></thead>")
    body = []
    for vi, v in enumerate(verbs):
        alt = " alt" if vi % 2 else ""
        for ti, (tkey, tshort) in enumerate((("present", "Pres."), ("past", "Past"), ("future", "Fut."))):
            cells = ""
            for pi, p in enumerate(PERSONS):
                full, spoken = conj(v, tkey, p[0])
                sub = f"<small>{htmlesc(show(full))}</small>" if show_full and full != spoken else ""
                grp = "p1" if pi < 2 else ("p2" if pi < 4 else "p3")
                words = show(spoken).split()
                n = max(len(x) + 0.7 * sum(x.count(c) for c in "mw") for x in words)   # m and w are wide letters
                size = "" if n <= 10 else ("s1" if n <= 13 else ("s2" if n <= 16 else ("s3" if n <= 18 else "s4")))
                txt = " ".join(f'<span class="w">{htmlesc(x)}</span>' for x in words)
                cells += f'<td class="f {grp} {size}">{txt}{sub}</td>'
            verb_cell = (f'<td class="vb" rowspan="3">to {htmlesc(v["en"])}<span>{htmlesc(show(dict_form(v)))}</span></td>'
                         if ti == 0 else "")
            body.append(f'<tr class="{"first" if ti == 0 else ""}{alt}">{verb_cell}<td class="tn">{tshort}</td>{cells}</tr>')
    return f'<div class="allv-wrap"><table class="avt">{cols}{head}<tbody>{"".join(body)}</tbody></table></div>'


with tab_allv:
    st.markdown(f"### 📋 All {len(VERBS)} verbs — full tables")
    st.markdown('<div class="allv-legend">Present · Past · Future for every person — no need to pick a verb. '
                'Bold = everyday Hyderabad Telugu. Use <b>🔁 Verb tables</b> to hear a verb and see its examples.</div>',
                unsafe_allow_html=True)
    av_all = sorted(VERBS, key=lambda x: x["en"].lower())
    av_picks = st.multiselect(
        "✅ Choose up to 10 verbs to see together (leave empty to see all)", [x["en"] for x in av_all],
        key="allv_pick", max_selections=10, placeholder="Type to find a verb, e.g. eat, come, go…",
        format_func=lambda e: f"to {e}  —  {show(dict_form(VERB_BY_EN[e]))}")
    fc1, fc2, fc3 = st.columns([3, 2, 1.3], vertical_alignment="bottom")
    av_q = fc1.text_input("🔎 Or filter the full list", key="allv_q", placeholder="e.g. eat, come, tinu…",
                          disabled=bool(av_picks)).strip().lower()
    av_full = fc2.toggle("Show textbook forms too", value=False, key="allv_full")
    if av_picks:
        fc3.button("✖ Clear", key="allv_clear", use_container_width=True,
                   on_click=lambda: st.session_state.update(allv_pick=[]))
        av_list = [VERB_BY_EN[e] for e in av_picks]
        note = f"Showing your {len(av_list)} chosen verb{'s' if len(av_list) > 1 else ''} (in the order you picked them)"
    else:
        av_list = av_all
        if av_q:
            av_list = [x for x in av_list if av_q in x["en"].lower() or av_q in show(dict_form(x)).lower()]
        note = f"Showing {len(av_list)} of {len(VERBS)} verbs · A–Z by English"
    if not av_list:
        st.info("No verb matches that search.")
    else:
        st.caption(note)
        st.markdown(ALLV_CSS + all_verbs_html(av_list, av_full), unsafe_allow_html=True)


# ==================================== LITTLE WORDS ====================================
with tab_prep:
    st.markdown("### 📍 Little words (prepositions)")
    st.markdown('<div class="tip">In Telugu these go <b>after</b> the word, often joined to it: '
                '<b>amma tO</b> = with mum · <b>office lO</b> = in the office · <b>Hyderabad nunchi</b> = from Hyderabad.</div>',
                unsafe_allow_html=True)
    q = st.text_input("🔎 Filter", key="prep_q", placeholder="e.g. with, near, from").strip().lower()
    for i, (en, te, ex_te, ex_en) in enumerate(PREPOSITIONS):
        if q and q not in en.lower() and q not in show(te):
            continue
        c1, c2 = st.columns([5, 2])
        c1.markdown(f'<div class="card"><div class="en">{htmlesc(en)}</div><div class="te">{htmlesc(show(te))}</div>'
                    f'<div style="margin-top:4px">🗨️ <b>{htmlesc(show_cap(ex_te))}</b><div class="en">{htmlesc(ex_en)}</div></div></div>',
                    unsafe_allow_html=True)
        with c2:
            st.write("")
            say_btns(ex_te, f"prep_{i}")
    st.markdown("#### 👉 Pointing words")
    for i, (en, te) in enumerate(POINTING_WORDS):
        entry(en, te, "", f"point_{i}", slow=False)


# ===================================== DICTIONARY =====================================
def save_online(en, roman):
    def change(d):
        d.setdefault("online_words", {})[en] = roman
    if update(change):
        st.session_state.dict_msg = f"⭐ Saved “{en}” to your dictionary."


with tab_dict:
    st.markdown("### 📖 Dictionary")
    q = st.text_input("Search in English or Telugu (English letters)", key="dict_q",
                      placeholder="e.g. water, tomorrow, how much, neeLLu").strip()
    if msg := st.session_state.pop("dict_msg", None):
        st.success(msg)
    if q:
        ql = q.lower()
        hits = [e for e in ENTRIES if ql in e[1].lower() or ql in show(e[2]).lower()]
        hits.sort(key=lambda e: (e[1].lower() != ql, not e[1].lower().startswith(ql), len(e[1])))
        st.caption(f"{len(hits)} match{'es' if len(hits) != 1 else ''}")
        for i, (kind, en, te, note) in enumerate(hits[:25]):
            entry(f"{en}  ·  {kind}", te, note, f"dict_{i}_{en}")
        exact = any(e[1].lower() == ql for e in hits)
        if not exact and re.search(r"[a-zA-Z]", q):
            st.markdown("---")
            with st.spinner("Looking it up online…"):
                te_script_txt = online_telugu(q)
            if te_script_txt:
                roman = roman_from_telugu(te_script_txt)
                st.markdown(f'<div class="feature"><div class="lbl">🌐 Online dictionary</div>'
                            f'<div class="en">{htmlesc(q)}</div><div class="te">{htmlesc(show_cap(roman))}</div>'
                            '<div class="note">💡 Online dictionaries give the written (formal) word — '
                            'in Hyderabad people may say it differently or use the English word.</div></div>',
                            unsafe_allow_html=True)
                c1, c2 = st.columns([2, 3])
                with c1:
                    say_btns(roman, "dict_online")
                c2.button("⭐ Save to my dictionary", on_click=save_online, args=(q.lower(), roman), key="dict_save")
            else:
                st.caption("🌐 The online dictionary didn't answer just now — try again in a moment.")
    else:
        topics = list(WORDS) + (["🌐 Looked up online"] if data.get("online_words") else [])
        topic = st.selectbox("Or browse a topic", topics, key="dict_topic")
        items = ([(en, te, "") for en, te in data.get("online_words", {}).items()] if topic.startswith("🌐")
                 else WORDS[topic])
        for i, (en, te, note) in enumerate(items):
            entry(en, te, note, f"topic_{topic}_{i}")
    st.caption(f"Built in: {sum(len(x) for x in WORDS.values())} words · {sum(len(x) for x in PHRASES.values())} phrases · "
               f"{len(VERBS)} verbs with full tables · numbers 1–100 · plus the online dictionary.")


# ====================================== NUMBERS ======================================
with tab_num:
    st.markdown("### 🔢 Numbers")
    n = st.number_input("Pick a number (1–100)", min_value=1, max_value=100, value=21, step=1, key="num_pick")
    entry(str(n), number_te(int(n)), "", "num_one")
    st.markdown('<div class="numgrid">' + "".join(f"<div><b>{k}</b>{htmlesc(show(number_te(k)))}</div>" for k in range(1, 101))
                + "</div>", unsafe_allow_html=True)
    nb = st.columns(3)
    nb[0].button("🔊 1 to 10", key="n110", on_click=queue_say, args=(" , ".join(number_te(k) for k in range(1, 11)), True),
                 use_container_width=True)
    nb[1].button("🔊 11 to 20", key="n1120", on_click=queue_say, args=(" , ".join(number_te(k) for k in range(11, 21)), True),
                 use_container_width=True)
    nb[2].button("🔊 Tens: 10 to 100", key="ntens", on_click=queue_say,
                 args=(" , ".join(number_te(k) for k in range(10, 101, 10)), True), use_container_width=True)
    st.markdown('<div class="tip">💡 21–99: say the ten, then the unit — 45 = <b>nalabhai aidu</b>. '
                '15 is <b>padihEnu</b> (some say padahaidu).</div>', unsafe_allow_html=True)
    st.markdown("#### 💯 Big numbers")
    for i, (num, te, note) in enumerate(BIG_NUMBERS):
        entry(f"{num:,}", te, note, f"big_{i}", slow=False)
    st.markdown("#### 💰 Money & shopping")
    for i, (te, en) in enumerate(MONEY_EXAMPLES):
        entry(en, te, "", f"money_{i}", slow=False)
    st.markdown("#### 👥 Counting people")
    for i, (te, en) in enumerate(COUNT_PEOPLE):
        entry(en, te, "", f"ppl_{i}", slow=False)
    st.markdown("#### 🕐 Telling the time")
    for i, (te, en) in enumerate([("okaTi ganTa", "1 o'clock"), ("renDu ganTalu", "2 o'clock"), ("aidunnara", "5:30 (five and a half)"),
                                  ("padi ganTalaki", "at 10 o'clock"), ("_time enta ayyindi?", "What's the time?")]):
        entry(en, te, "", f"time_{i}", slow=False)


# ====================================== GRAMMAR ======================================
with tab_gram:
    st.markdown("### 🧠 Grammar basics")
    st.caption("Ten short ideas that unlock everyday Telugu. Tap 🔊 and repeat every example.")
    for gi, (title, expl, exs) in enumerate(GRAMMAR):
        with st.expander(title, expanded=gi == 0):
            st.markdown(mdsafe(show(expl)))
            for i, (te, en) in enumerate(exs):
                entry(en, te, "", f"gram_{gi}_{i}", slow=False)


# ===================================== PRACTICE =====================================
def norm(s):
    s = show(s).lower()
    for a, b in (("ee", "i"), ("oo", "u"), ("th", "t"), ("dh", "d"), ("w", "v")):
        s = s.replace(a, b)
    s = re.sub(r"[^a-z]", "", s)
    return re.sub(r"(.)\1+", r"\1", s)


def pool(source):
    if source == "Words":
        return [(e, t) for items in WORDS.values() for e, t, _ in items]
    if source == "Phrases":
        return [(e, t) for items in PHRASES.values() for e, t, _ in items]
    return [("to " + v["en"], dict_form(v)) for v in VERBS]


def mark(en, te, knew):
    def change(d):
        k, p = d.setdefault("known", []), d.setdefault("practise", [])
        if knew:
            if en not in k:
                k.append(en)
            if en in p:
                p.remove(en)
        else:
            if en not in p:
                p.append(en)
        day = d.setdefault("days", {}).setdefault(TODAY_KEY, {"answers": 0, "right": 0})
        day["answers"] += 1
        day["right"] += 1 if knew else 0
    update(change)
    st.session_state.fc_card = None
    st.session_state.fc_show = False


def new_quiz(source):
    items = pool(source)
    qs = []
    for en, te in random.sample(items, min(QUIZ_LENGTH, len(items))):
        wrong = random.sample([x for x in items if x[1] != te], 3)
        opts = [te] + [w[1] for w in wrong]
        random.shuffle(opts)
        qs.append({"en": en, "te": te, "opts": opts})
    st.session_state.quiz = {"qs": qs, "i": 0, "score": 0, "source": source, "last": None}


def answer_quiz(choice):
    qz = st.session_state.quiz
    q = qz["qs"][qz["i"]]
    right = choice == q["te"]
    qz["score"] += right
    qz["last"] = (right, q["en"], q["te"])
    qz["i"] += 1
    log_practice(int(right))
    if qz["i"] >= len(qz["qs"]):
        score, total, src = qz["score"], len(qz["qs"]), qz["source"]

        def change(d):
            d.setdefault("quizzes", []).append({"date": TODAY_KEY, "score": score, "total": total, "source": src})
        update(change)
    queue_say(q["te"])


def new_challenge():
    v = random.choice(VERBS)
    p = random.choice(PERSONS)
    t = random.choice(["present", "past", "future"])
    st.session_state.vc = {"en": v["en"], "p": p, "t": t, "result": None}
    st.session_state.vc_answer = ""


def check_challenge():
    vc = st.session_state.vc
    v = VERB_BY_EN[vc["en"]]
    full, spoken = conj(v, vc["t"], vc["p"][0])
    given = norm(st.session_state.get("vc_answer", ""))
    pron = norm(vc["p"][1].split(" / ")[0])
    ok = given in (norm(full), norm(spoken)) or (given.startswith(pron) and given[len(pron):] in (norm(full), norm(spoken)))
    vc["result"] = (ok, spoken, full)

    def change(d):
        d["verb_tries"] = d.get("verb_tries", 0) + 1
        d["verb_ok"] = d.get("verb_ok", 0) + (1 if ok else 0)
        day = d.setdefault("days", {}).setdefault(TODAY_KEY, {"answers": 0, "right": 0})
        day["answers"] += 1
        day["right"] += 1 if ok else 0
    update(change)
    queue_say(vc["p"][1].split(" / ")[0] + " " + spoken)


with tab_prac:
    st.markdown("### 🎯 Practice")
    pm = st.radio("Mode", ["🃏 Flashcards", "✅ Quiz", "🔁 Verb challenge", "🎙️ Speak & compare"], horizontal=True,
                  label_visibility="collapsed", key="prac_mode")
    if pm == "🃏 Flashcards":
        src = st.radio("Cards from", ["Phrases", "Words", "Verbs", "My 'practise again' list"], horizontal=True, key="fc_src")
        items = pool(src) if not src.startswith("My") else [
            (e[1], e[2]) for e in ENTRIES if e[1] in data.get("practise", [])]
        if not items:
            st.info("Nothing here yet — cards you mark 🔁 will appear in this list.")
        else:
            if not st.session_state.get("fc_card") or st.session_state.get("fc_src_last") != src:
                st.session_state.fc_card = random.choice(items)
                st.session_state.fc_show = False
                st.session_state.fc_src_last = src
            en, te = st.session_state.fc_card
            st.markdown(f'<div class="card" style="text-align:center;padding:26px"><div class="en">How do you say…</div>'
                        f'<div class="q">{htmlesc(en)}</div>'
                        + (f'<div class="te big">{htmlesc(show_cap(te))}</div>' if st.session_state.get("fc_show") else
                           '<div class="en">Say it out loud first, then tap “Show”.</div>') + '</div>', unsafe_allow_html=True)
            if not st.session_state.get("fc_show"):
                def _reveal(t=te):
                    st.session_state.fc_show = True
                    queue_say(t)
                st.button("👀 Show answer", on_click=_reveal, type="primary", use_container_width=True)
            else:
                say_btns(te, "fc")
                b1, b2 = st.columns(2)
                b1.button("✅ I knew it", on_click=mark, args=(en, te, True), use_container_width=True, type="primary")
                b2.button("🔁 Practise again", on_click=mark, args=(en, te, False), use_container_width=True)
    elif pm == "✅ Quiz":
        src = st.radio("Quiz on", ["Phrases", "Words", "Verbs"], horizontal=True, key="qz_src")
        qz = st.session_state.get("quiz")
        if not qz or qz["source"] != src:
            st.button(f"▶️ Start a {QUIZ_LENGTH}-question quiz", on_click=new_quiz, args=(src,), type="primary")
        else:
            if qz.get("last"):
                ok, en, te = qz["last"]
                (st.success if ok else st.error)(("✅ Correct! " if ok else "❌ Not quite. ") + f"{en} = **{mdsafe(show(te))}**")
            if qz["i"] < len(qz["qs"]):
                q = qz["qs"][qz["i"]]
                st.markdown(f'<div class="en">Question {qz["i"] + 1} of {len(qz["qs"])} · score {qz["score"]}</div>'
                            f'<div class="q">{htmlesc(q["en"])}</div>', unsafe_allow_html=True)
                for j, o in enumerate(q["opts"]):
                    st.button(show_cap(o), key=f"qz_{qz['i']}_{j}", on_click=answer_quiz, args=(o,), use_container_width=True)
            else:
                st.markdown(f'<div class="card" style="text-align:center"><div class="q">🎉 {qz["score"]} / {len(qz["qs"])}</div>'
                            f'<div class="en">{"Brilliant!" if qz["score"] >= 8 else "Good work — try again to beat it!"}</div></div>',
                            unsafe_allow_html=True)
                st.button("🔄 New quiz", on_click=new_quiz, args=(src,), type="primary")
    elif pm == "🔁 Verb challenge":
        if not st.session_state.get("vc"):
            new_challenge()
        vc = st.session_state.vc
        tl = {"present": "Present (is …ing)", "past": "Past (…ed)", "future": "Future (will …)"}[vc["t"]]
        st.markdown(f'<div class="card" style="text-align:center;padding:20px"><div class="en">Say and type the Telugu for</div>'
                    f'<div class="q">to {htmlesc(vc["en"])}</div><div>👤 <b>{htmlesc(show(vc["p"][1]))}</b> '
                    f'({htmlesc(vc["p"][2])}) · ⏱️ <b>{tl}</b></div></div>', unsafe_allow_html=True)
        with st.form("vc_form", border=False):
            st.text_input("Your answer (English letters)", key="vc_answer", placeholder="e.g. tintunnaanu")
            st.form_submit_button("Check ✔️", on_click=check_challenge)
        if vc.get("result"):
            ok, spoken, full = vc["result"]
            (st.success if ok else st.error)(("✅ Correct! " if ok else "❌ The answer is ") +
                                             f"**{mdsafe(show(spoken))}**" + (f" (full: {mdsafe(show(full))})" if full != spoken else ""))
            st.button("➡️ Next verb", on_click=new_challenge, type="primary")
        st.caption("Spelling is forgiving: 'tintunna', 'tintunnaanu' and 'thintunnanu' all count. Both the everyday "
                   "and full forms are accepted.")
    else:
        all_p = [p for items in PHRASES.values() for p in items]
        if "sp_i" not in st.session_state:
            st.session_state.sp_i = random.randrange(len(all_p))
        en, te, note = all_p[st.session_state.sp_i % len(all_p)]
        entry(en, te, note, "speak")
        if hasattr(st, "audio_input"):
            st.audio_input("🎙️ Record yourself, then play it back and compare", key=f"rec_{st.session_state.sp_i}")
        def _next_sp():
            st.session_state.sp_i = random.randrange(len(all_p))
            log_practice(1)
        st.button("➡️ Next phrase", on_click=_next_sp)
        st.caption("Listen 🔊 → record → compare. Recordings stay on this screen only; they aren't saved.")


# ===================================== PROGRESS =====================================
def save_notes():
    txt = st.session_state.get("notes_in", "")

    def change(d):
        d["notes"] = txt
    if update(change):
        st.session_state.prog_msg = "💾 Notes saved."


def reset_all():
    if st.session_state.get("reset_ok") != "RESET":
        st.session_state.prog_msg = "Type RESET in the box first."
        return
    if update(lambda d: d.clear() or d.update(default_data())):
        st.session_state.prog_msg = "Progress reset."
        st.session_state.reset_ok = ""


with tab_prog:
    st.markdown("### 📈 My progress")
    days = data.get("days", {})
    total = sum(x.get("answers", 0) for x in days.values())
    right = sum(x.get("right", 0) for x in days.values())
    m = st.columns(4)
    m[0].metric("🔥 Streak", f"{streak(data, today)} days")
    m[1].metric("📝 Answers", total)
    m[2].metric("🎯 Accuracy", f"{int(100 * right / total)}%" if total else "–")
    m[3].metric("✅ Known", len(data.get("known", [])))
    last14 = [today - timedelta(days=i) for i in range(13, -1, -1)]
    st.markdown("**Last 14 days** (practice answers)")
    st.bar_chart({"answers": [days.get(d.isoformat(), {}).get("answers", 0) for d in last14]}, height=180)
    st.caption(f"A ✅ day = {DAILY_GOAL}+ answers. Verb challenge: {data.get('verb_ok', 0)} right out of "
               f"{data.get('verb_tries', 0)}.")
    if data.get("quizzes"):
        st.markdown("**Recent quizzes**")
        for qz in reversed(data["quizzes"][-8:]):
            st.markdown(f"- {qz['date']} · {qz['source']}: **{qz['score']}/{qz['total']}**")
    prac = data.get("practise", [])
    if prac:
        st.markdown(f"**🔁 Practise again ({len(prac)})**")
        lookup = {e[1]: e[2] for e in ENTRIES}
        for i, en in enumerate(prac[:30]):
            if en in lookup:
                entry(en, lookup[en], "", f"prog_p_{i}", slow=False)
    st.markdown("**📝 My notes** (new words from friends, things to ask)")
    if "notes_in" not in st.session_state:
        st.session_state.notes_in = data.get("notes", "")
    st.text_area("Notes", key="notes_in", height=120, label_visibility="collapsed")
    st.button("💾 Save notes", on_click=save_notes)
    if msg := st.session_state.pop("prog_msg", None):
        st.info(msg)
    st.caption("☁️ Progress is saved online." if storage_cfg() else
               "💾 Progress is saved on this app's server only — set up the private 'pragna-mitra-data' storage to keep it safe.")
    with st.expander("⚠️ Reset all progress"):
        st.text_input("Type RESET to confirm", key="reset_ok")
        st.button("Reset everything", on_click=reset_all)
