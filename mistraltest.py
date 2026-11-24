#!/usr/bin/env python3
"""Samme test som soegetest.py, men med en Mistral-model via API'et.

Prompten er en kopi af den, HAL's søgeagent bruger i produktion, så sammenligningen er fair.
Hver besked sendes ALENE, uden samtalehistorik, ligesom i den lokale test.
Kræver kun Pythons standardbibliotek.

Kør:  python3 mistraltest.py eksempel_testfil.txt
      python3 mistraltest.py mine_beskeder.txt mistral-medium-latest
      python3 mistraltest.py mine_beskeder.txt mistral-large-latest 2000   (tokenbudget)

Nøglen læses fra miljøet eller fra .env i samme mappe (første variabel med MISTRAL og KEY
i navnet). Den udskrives aldrig.
"""
import datetime
import json
import os
import sys
import time
import urllib.error
import urllib.request
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
URL = "https://api.mistral.ai/v1/chat/completions"

CLASSIFIER_MODEL = "mistral-small-2603"
CLASSIFIER_MAX_TOKENS = 300

# Kopi af HAL's klassificeringsprompt (search_agent.py, november 2026), som HAL bygger den,
# når brugerens by ikke er kendt. Det var sådan, testen blev kørt.
def build_prompt(user_timezone="Europe/Copenhagen"):
    today = datetime.datetime.now(ZoneInfo(user_timezone)).date()
    dato_str = today.strftime("%d. %B %Y")
    by_linje = "Brugerens by er ikke kendt fra IP."
    by_regel = (
        "- Hvis spørgsmålet refererer til 'her', 'min by' eller lignende "
        "og byen ikke fremgår af samtalehistorikken, returnér search=false "
        "med reasoning='lokation ukendt' – så spørger HAL brugeren."
    )
    return f"""Du er en klassificerings-agent for en dansk chatapplikation.
Din eneste opgave er at afgøre, om et spørgsmål kræver aktuel web-information,
og i så fald returnere de bedste søgetermer.

I dag er {dato_str}. {by_linje}
Brug relative tidstermer som "i dag", "denne uge" når spørgsmålet
er tidsaktuelt – ikke specifikke dato-numre.

Svar ALTID med ren JSON i dette format – ingen forklaring, ingen markdown:
{{
  "search": true,
  "queries": ["...", "..."],
  "reasoning": "kort begrundelse på dansk",
  "user_timezone": "Europe/Copenhagen"
}}

Regler:
- search=true for nyheder, aktuelle priser, vejr, begivenheder efter din
  træningscutoff, specifikke facts du ikke er sikker på.
- search=false for generel viden, kode, matematik, oversættelse, kreativt.
- queries: 1-3 korte søgetermer. ALTID udfyldt – også når search=false.
  Ved search=false er queries dine bedste gæt på hvad man VILLE
  søge på hvis brugeren insisterer. Aldrig hele sætninger, aldrig
  brugerens spørgsmål ordret.
- Brug IKKE dato-numre i selve queries (fx "vejrudsigt Nakskov 22. september
  2026"). DDG matcher dårligt på datoer. Brug brede termer: "vejrudsigt
  Nakskov", "Nakskov vejr DMI", "Netto Nakskov åbningstider".

Sprogvalg for queries – vigtigt:
- Vælg sproget der giver bedst hit for emnet, ikke automatisk brugerens sprog.
- Engelsk: produkter (Adobe, GitLab, Anthropic), software, teknisk
  dokumentation, internationale nyheder, APIs, konferencer, videnskab.
- Dansk: danske forhold (vejr i dansk by, danske myndigheder, dansk sport,
  danske virksomheder, dansk lovgivning).
- Ved blandede emner: lav ÉN dansk OG ÉN engelsk query hvis det
  giver bredere dækning.
- Eksempler:
    "Hvordan opsætter jeg Rust på Ubuntu?" → ['Rust install Ubuntu', 'rustup install Linux']
    "Hvad siger dansk lov om GDPR?" → ['GDPR dansk lov', 'databeskyttelsesforordningen dansk']
    "Nyheder om Anthropic?" → ['Anthropic news 2026', 'Anthropic Claude announcement']
- user_timezone: IANA-navn (fx Europe/Copenhagen, America/New_York) hvis
  byen kendes fra spørgsmålet eller historikken. Ellers tom streng "".
{by_regel}
- Ved tvivl: search=false. Hellere ét svar for lidt end støj.
"""


def find_key():
    for name, value in os.environ.items():
        if "MISTRAL" in name.upper() and "KEY" in name.upper() and value:
            return value
    env_file = os.path.join(HERE, ".env")
    if os.path.exists(env_file):
        with open(env_file, encoding="utf-8") as f:
            for line in f:
                name, sep, value = line.strip().partition("=")
                name = name.replace("export ", "").strip()
                if sep and "MISTRAL" in name.upper() and "KEY" in name.upper():
                    return value.strip().strip('"').strip("'")
    sys.exit("Fandt ingen Mistral-nøgle i miljøet eller i .env.")


def load_tests(path):
    tests = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            label, sep, message = line.partition("|")
            label = label.strip().upper()
            if sep and label in ("JA", "NEJ") and message.strip():
                tests.append((message.strip(), label == "JA"))
    if not tests:
        sys.exit(f"Ingen mærkede linjer i {path}")
    return tests


def classify(key, model, system, message, max_tokens):
    body = json.dumps({
        "model": model,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": message}],
        "temperature": 0,
        "top_p": 1,  # Mistral Large kræver det ved temperature 0
        "max_tokens": max_tokens,
    }).encode()
    req = urllib.request.Request(URL, data=body, headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {key}",
    })
    for attempt in range(3):
        start = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.load(resp)
            break
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 2:
                time.sleep(3)
                continue
            detail = e.read().decode(errors="replace")[:300]
            sys.exit(f"Mistral svarede {e.code}: {detail}")
    secs = time.perf_counter() - start
    raw = data["choices"][0]["message"]["content"]
    if isinstance(raw, list):  # tænkende modeller (Large 4) svarer i bidder: tanker + tekst
        raw = "".join(p.get("text", "") for p in raw if isinstance(p, dict) and p.get("type") == "text")
    s, e = raw.find("{"), raw.rfind("}")
    try:
        verdict = json.loads(raw[s:e + 1])
    except (ValueError, json.JSONDecodeError):
        return None, [], secs
    return bool(verdict.get("search")), verdict.get("queries") or [], secs


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    tests = load_tests(sys.argv[1])
    model = sys.argv[2] if len(sys.argv) > 2 else CLASSIFIER_MODEL
    # valgfrit tokenbudget, fx 2000 til tænkende modeller
    max_tokens = int(sys.argv[3]) if len(sys.argv) > 3 else CLASSIFIER_MAX_TOKENS
    key = find_key()
    system = build_prompt()

    print(f"Model: {model}   (HAL's prompt, ingen historik)   Beskeder: {len(tests)}")
    hits, unclear, times, errors = 0, 0, [], []
    for message, expected in tests:
        got, queries, secs = classify(key, model, system, message, max_tokens)
        times.append(secs)
        short = message if len(message) <= 90 else message[:87] + "..."
        if got is None:
            unclear += 1
            errors.append(f"  UKLART: {short}")
            print(f"??    {secs:4.1f}s       {short}")
            continue
        ok = got == expected
        hits += ok
        if not ok:
            errors.append(f"  {'falsk JA ' if got else 'falsk NEJ'}: {short}")
        tag = "JA " if got else "NEJ"
        extra = f"   -> {queries}" if got and queries else ""
        print(f"{'OK  ' if ok else 'FEJL'}  {secs:4.1f}s  {tag}  {short}{extra}")
        time.sleep(0.3)

    n = len(tests)
    print(f"\nRigtige: {hits}/{n}   Uklare svar: {unclear}")
    print(f"Tid: gennemsnit {sum(times) / n:.1f}s, langsomste {max(times):.1f}s")
    if errors:
        print("Fejl:\n" + "\n".join(errors))


if __name__ == "__main__":
    main()
