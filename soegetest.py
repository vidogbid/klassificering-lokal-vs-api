#!/usr/bin/env python3
"""Kan en lille lokal model afgøre, om en besked kræver websøgning?

Kør:  python3 soegetest.py [model] [prompt] [testfil]
      python3 soegetest.py qwen2.5:3b en mine_beskeder.txt   (dine egne, mærkede beskeder)
      python3 soegetest.py                       (qwen2.5:1.5b, prompt "en")
      python3 soegetest.py qwen2.5:1.5b da       (dansk prompt med eksempler)
      python3 soegetest.py qwen2.5:1.5b kort     (den første, korte prompt)
      python3 soegetest.py gemma3:1b en          (anden model, hent den først med ollama pull)

Eksemplerne i promptene er bevidst ANDRE beskeder end testbeskederne,
ellers måler testen bare, om modellen kan skrive af.
"""
import json
import sys
import time
import urllib.request

MODEL = sys.argv[1] if len(sys.argv) > 1 else "qwen2.5:1.5b"
VARIANT = sys.argv[2] if len(sys.argv) > 2 else "en"
URL = "http://127.0.0.1:11434/api/generate"

# Beskeden står til sidst, så Ollama kan genbruge den faste del af prompten.
PROMPTS = {
    "kort": ("Afgør om beskeden kræver en websøgning for at kunne besvares. "
             "Svar kun JA eller NEJ.\n\nBesked: {}"),

    "en": ("You decide whether a chat message needs a web search.\n"
           "Answer YES only if a good answer depends on current or changing information: "
           "news, prices, weather, opening hours, timetables, results, who holds a position now, "
           "latest versions, or recent events.\n"
           "Answer NO for everything else: writing, rewriting, proofreading, translation, code, "
           "math, lists, ideas, advice, and explanations of general knowledge, history or terms.\n"
           "If in doubt, answer NO.\n\n"
           "Message: Hvad er renten på et boliglån i dag?\nAnswer: YES\n\n"
           "Message: Hvem er borgmester i Lolland Kommune nu?\nAnswer: YES\n\n"
           "Message: Hvornår kører næste tog til Odense?\nAnswer: YES\n\n"
           "Message: Skriv en hilsen til min mors fødselsdag.\nAnswer: NO\n\n"
           "Message: Hvad er fotosyntese?\nAnswer: NO\n\n"
           "Message: Oversæt 'god morgen' til fransk.\nAnswer: NO\n\n"
           "Message: Hvem opfandt telefonen?\nAnswer: NO\n\n"
           "Message: {}\nAnswer:"),

    "da": ("Du afgør, om en besked i en chat kræver en websøgning.\n"
           "Svar JA kun hvis et godt svar afhænger af aktuel eller skiftende information: "
           "nyheder, priser, vejr, åbningstider, køreplaner, resultater, hvem der har en post nu, "
           "seneste versioner eller nylige begivenheder.\n"
           "Svar NEJ til alt andet: skrive, omskrive, rette, oversætte, kode, regne, lister, ideer, "
           "råd og forklaringer af almen viden, historie eller begreber.\n"
           "Ved tvivl: svar NEJ.\n\n"
           "Besked: Hvad er renten på et boliglån i dag?\nSvar: JA\n\n"
           "Besked: Hvem er borgmester i Lolland Kommune nu?\nSvar: JA\n\n"
           "Besked: Hvornår kører næste tog til Odense?\nSvar: JA\n\n"
           "Besked: Skriv en hilsen til min mors fødselsdag.\nSvar: NEJ\n\n"
           "Besked: Hvad er fotosyntese?\nSvar: NEJ\n\n"
           "Besked: Oversæt 'god morgen' til fransk.\nSvar: NEJ\n\n"
           "Besked: Hvem opfandt telefonen?\nSvar: NEJ\n\n"
           "Besked: {}\nSvar:"),
}
PROMPT = PROMPTS[VARIANT]

# (besked, kræver søgning?)
TESTS = [
    ("Hvad koster en færgebillet fra Rødby til Puttgarden i dag?", True),
    ("Hvordan bliver vejret i Nakskov i morgen?", True),
    ("Hvem vandt Superligakampen i går?", True),
    ("Hvad er status på Femern-tunnelen lige nu?", True),
    ("Hvornår har Netto i Nakskov åbent på søndag?", True),
    ("Hvad er den seneste version af Python?", True),
    ("Hvem er formand for HK Hovedstaden?", True),
    ("Hvad skete der på Folkemødet i år?", True),
    ("Er der problemer med S-togene i dag?", True),
    ("Hvad koster Mistral Small pr. million tokens i deres API?", True),
    ("Hvilke film går i biografen i Nakskov denne uge?", True),
    ("Hvad er kursen på euro lige nu?", True),
    ("Find anmeldelser af den nye Volvo EX30.", True),
    ("Hvad har regeringen meldt ud om AI i folkeskolen?", True),
    ("Hvad er status på NIS2-loven i Danmark?", True),
    ("Skriv et kort digt om en kat.", False),
    ("Oversæt 'Bill of Lading' til tysk.", False),
    ("Ret kommaerne i denne sætning: Når skibet kommer skal vi være klar.", False),
    ("Forklar forskellen på TCP og UDP.", False),
    ("Forklar kort, hvad GDPR går ud på.", False),
    ("Skriv en Python-funktion, der vender en streng om.", False),
    ("Hvad er 17 procent af 2.340?", False),
    ("Giv mig fem ideer til en overskrift om havnesikkerhed.", False),
    ("Hvorfor er himlen blå?", False),
    ("Gør teksten kortere: Vi skal på nuværende tidspunkt gøre opmærksom på, at mødet er rykket.", False),
    ("Hvem var Thomas Kingo?", False),
    ("Hvad betyder en Himalaya-klausul i et konnossement?", False),
    ("Lav en indkøbsliste til lasagne for fire.", False),
    ("Hvad er forskellen på 'både og' og 'enten eller'?", False),
    ("Hjælp mig med en sms til min chef om, at jeg er syg i dag.", False),
]


TESTFILE = sys.argv[3] if len(sys.argv) > 3 else None
if TESTFILE:
    # Linjer som "JA | besked" eller "NEJ | besked". Linjer med ? eller uden | springes over.
    TESTS = []
    with open(TESTFILE, encoding="utf-8") as f:
        for line in f:
            label, sep, message = line.partition("|")
            label = label.strip().upper()
            if sep and label in ("JA", "NEJ") and message.strip():
                TESTS.append((message.strip(), label == "JA"))
    if not TESTS:
        sys.exit(f"Ingen mærkede linjer (JA | ... eller NEJ | ...) i {TESTFILE}")


def ask(message):
    body = json.dumps({
        "model": MODEL,
        "prompt": PROMPT.format(message),
        "stream": False,
        "keep_alive": "10m",
        "options": {"num_predict": 5, "temperature": 0},
    }).encode()
    req = urllib.request.Request(URL, data=body, headers={"Content-Type": "application/json"})
    start = time.perf_counter()
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.load(resp)
    return data["response"].strip().upper(), time.perf_counter() - start


def main():
    print(f"Model: {MODEL}   Prompt: {VARIANT}\nIndlæser modellen ...")
    ask("Hej")  # opvarmning, tælles ikke med

    hits, unclear, times, errors = 0, 0, [], []
    for message, expected in TESTS:
        answer, secs = ask(message)
        times.append(secs)
        for label in ("ANSWER:", "SVAR:"):  # små modeller gentager tit etiketten
            if answer.startswith(label):
                answer = answer[len(label):].strip()
        if answer.startswith(("JA", "YES")):
            got = True
        elif answer.startswith(("NEJ", "NO")):
            got = False
        else:
            unclear += 1
            errors.append(f"  UKLART ({answer!r}): {message}")
            print(f"??    {secs:4.1f}s  {answer:<4} {message}")
            continue
        ok = got == expected
        hits += ok
        if not ok:
            errors.append(f"  {'falsk JA ' if got else 'falsk NEJ'}: {message}")
        print(f"{'OK  ' if ok else 'FEJL'}  {secs:4.1f}s  {answer:<4} {message}")

    n = len(TESTS)
    print(f"\nRigtige: {hits}/{n}   Uklare svar: {unclear}")
    print(f"Tid: gennemsnit {sum(times) / n:.1f}s, langsomste {max(times):.1f}s")
    if errors:
        print("Fejl:\n" + "\n".join(errors))


if __name__ == "__main__":
    main()
