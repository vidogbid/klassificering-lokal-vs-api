# Jeg ville flytte et klassificeringskald fra cloud-API til selvhostet lille model på VPS. Testen fandt i stedet en fejl i produktionsmiljøet.

## 1. Problemet

Søgeagenten sender hver besked til et cloud-API (Mistral) for at afgøre, om der skal søges. Kan en lokal model gøre det, så data bliver på serveren af hensyn til privatliv, kontrol og GDPR?

## 2. Opsætning

Hetzner CX22, 2 vCPU, 8 GB, ingen GPU. Ollama som systemd-tjeneste med et loft over hukommelsen (MemoryMax) på 3,5 GB.

## 3. Første test (syntetisk)

30 selvskrevne beskeder med facit (`eksempel_testfil.txt`).

- Qwen 2.5 1.5B: 16/30. Svarede JA til alt, reelt ubrugelig.
- Qwen 2.5 3B: 26/30.
- Mistral Small: 29/30 på de samme beskeder (med søgeagentens egen prompt, ikke den samme prompt som Qwen).

Læring: små modeller skal have kriterier og eksempler.

## 4. Rigtige data

50 af mine egne beskeder. Qwen 2.5 3B: 36/50. 8 af 16 JA fanget, 2,6 sekunder i gennemsnit og 7,3 sekunder for den langsomste.

Af de 50 beskeder er de 34 NEJ. En model, der konsekvent svarer NEJ, får altså 34/50. Fejlene sad i opfølgende beskeder som "Hvad er det?", som ikke kan afgøres uden resten af samtalen. Testen var for pæn.

## 5. Sammenligning med det, der allerede var i produktion

I produktion kørte Mistral Large 4. Med 300 tokens fik den 0/50. Med 2.000 tokens fik den 16/24 (Small 17/24 på de samme beskeder), men brugte 28 sekunder i gennemsnit og fik timeout over 60 sekunder ved besked nr. 24.

Til sammenligning:

- Mistral Small: 39/50, 8 af 16 JA, 1,1 sekunder.
- Mistral Medium: 39/50, 7 af 16 JA, 0,9 sekunder.

## 6. Fundet i produktion: 24 % fejl

På 30 dage var der 152 klassificeringer og 36 fejl.

- 21 skyldtes, at Large 4 brugte budgettet på at tænke (`finish=length`).
- 15 skyldtes, at modellen ikke svarede med JSON, men fortsatte samtalen.

Ved en fejl blev der ikke søgt, uanset om der var brug for det. Det skete for næsten hver fjerde besked.

## 7. Rettelse og beslutning

Mistral Small 2603, i drift i produktion siden 23. november 2026. Fast navn i stedet for "latest", da jeg ikke vil risikere, at modellen skifter under mig. Small er valgt, fordi den ikke tænker.

Lokal model fravalgt: 2,6 sekunder i gennemsnit og op til 7,3 mod 1,1 for Small, og den rammer ikke bedre (se punkt 4 og 8).

## 8. Begrænsninger

50 beskeder, mærket af én person (mig), ingen samtalehistorik i testen. Grundlinjen er 34/50 (se punkt 4). Forskelle på 1-3 beskeder er støj.

## 9. Næste skridt

Tool calling i stedet for separat klassificering. Under arbejde, ikke færdigt.

## 10. Sådan kører du det

- Kun Pythons standardbibliotek er nødvendigt.
- Ollama skal være installeret for at køre `soegetest.py`.
- Hent modellen: `ollama pull qwen2.5:3b`
- Mistral-nøglen skal ligge i `MISTRAL_API_KEY` eller i en `.env`-fil.
- `eksempel_testfil.txt` ligger i repoet, men mine egne beskeder gør ikke. `hent_beskeder.py` viser, hvordan man laver sin egen testfil.

```
python3 soegetest.py qwen2.5:3b en eksempel_testfil.txt
python3 mistraltest.py eksempel_testfil.txt
```

## Licens

MIT
