#!/usr/bin/env python3
"""Træk brugerbeskeder ud af HAL-samtaler til en testfil, der kan mærkes JA/NEJ.

Kør:  python3 hent_beskeder.py samtalemappe
      python3 hent_beskeder.py samtalemappe 60    (antal, standard 50)

Læser alle .json-filer i mappen og dens undermapper. Finder brugerbeskeder i formen
{"role": "user", "content": ...}, uanset hvor dybt de ligger i filen.
Ændrer ingenting. Skriver mine_beskeder.txt i den mappe, du står i.
Hver linje hedder "? | besked". Ret ? til JA eller NEJ, og slet linjer, du ikke vil have med.
"""
import json
import os
import random
import sys

MAX_CHARS = 400     # længere beskeder er typisk indsatte tekster, de springes over
CUT_MARKERS = ("--- WEB-INFORMATION ---", "[System:")


def text_of(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(p.get("text", "") for p in content
                         if isinstance(p, dict) and p.get("type") == "text")
    return ""


def user_messages(node):
    """Find alle {'role': 'user', 'content': ...} uanset hvordan filen er bygget op."""
    if isinstance(node, dict):
        if node.get("role") == "user" and "content" in node:
            yield text_of(node["content"])
        for value in node.values():
            yield from user_messages(value)
    elif isinstance(node, list):
        for item in node:
            yield from user_messages(item)


def clean(text):
    for marker in CUT_MARKERS:
        if marker in text:
            text = text.split(marker, 1)[0]
    return " ".join(text.replace("|", "/").split())


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    root = sys.argv[1]
    wanted = int(sys.argv[2]) if len(sys.argv) > 2 else 50

    files, broken, too_long = 0, 0, 0
    seen = set()
    messages = []
    for dirpath, _, names in os.walk(root):
        for name in sorted(names):
            if not name.endswith(".json"):
                continue
            files += 1
            try:
                with open(os.path.join(dirpath, name), encoding="utf-8") as f:
                    data = json.load(f)
            except (OSError, json.JSONDecodeError):
                broken += 1
                continue
            for raw in user_messages(data):
                text = clean(raw)
                if not text or text.lower() in seen:
                    continue
                if len(text) > MAX_CHARS:
                    too_long += 1
                    continue
                seen.add(text.lower())
                messages.append(text)

    random.seed(42)  # samme udtræk hver gang
    sample = random.sample(messages, min(wanted, len(messages)))

    with open("mine_beskeder.txt", "w", encoding="utf-8") as f:
        for text in sample:
            f.write(f"? | {text}\n")

    print(f"Filer læst: {files} (ulæselige: {broken})")
    print(f"Unikke beskeder: {len(messages)}  (sprunget over, for lange: {too_long})")
    print(f"Skrevet {len(sample)} til mine_beskeder.txt")


if __name__ == "__main__":
    main()
