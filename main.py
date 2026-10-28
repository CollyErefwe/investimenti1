"""Chiamate al modello linguistico (Gemini via endpoint compatibile OpenAI).

La chiave NON sta nel codice: va impostata come GEMINI_API_KEY
(in locale: .streamlit/secrets.toml oppure variabile d'ambiente;
su Streamlit Cloud: nei Secrets, app.py la copia in os.environ).
Il modello si può cambiare senza toccare il codice con GEMINI_MODEL
(e la riserva con GEMINI_MODEL_RISERVA; vuoto = nessuna riserva).
"""
import os
import re
import time

import requests

MODELLO = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")
MODELLO_RISERVA = os.environ.get("GEMINI_MODEL_RISERVA", "gemini-3.8-flash")

URL_API = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"

# Parole molto frequenti, usate per un controllo grossolano della lingua.
_PAROLE_IT = {"il", "lo", "la", "di", "del", "della", "che", "con", "per", "una", "un", "sono", "nel", "dei", "delle", "e", "è"}
_PAROLE_EN = {"the", "and", "of", "is", "with", "for", "that", "are", "to", "in", "its", "this", "by", "on"}


def _chiave() -> str:
    chiave = os.environ.get("GEMINI_API_KEY")
    if not chiave:
        raise RuntimeError("GEMINI_API_KEY non impostata (variabile d'ambiente o Secrets di Streamlit).")
    return chiave


def _attesa_da_errore(messaggio: str, tentativo: int) -> float:
    """Secondi da aspettare dopo un errore di limite: usa il tempo indicato
    dall'API ('retry in 12.3s' / 'retryDelay: 12s') oppure un'attesa crescente."""
    m = re.search(r"retry(?:delay)?\D{0,12}([\d.]+)\s*s", messaggio)
    if m:
        return min(float(m.group(1)) + 1, 45)
    return min(5 * (tentativo + 1), 30)


# ------------------------------------------------------------ validazione

def _estrai_punti(testo: str, quanti: int = 2) -> list:
    """Punti elenco della risposta (ignora preamboli e righe non elencate)."""
    punti = []
    for riga in testo.splitlines():
        m = re.match(r"^\s*(?:[-•*–]|\d+[.)])\s+(.*\S)\s*$", riga)
        if m:
            punti.append(m.group(1).strip())
    return punti[:quanti]


def _completo(punto: str) -> bool:
    """Una frase che non finisce con punteggiatura è quasi sempre troncata."""
    return punto.rstrip("*_\"'» )").endswith((".", "!", "?"))


def _lingua_ok(testo: str, lingua: str) -> bool:
    parole = re.findall(r"[a-zàèéìòù]+", testo.lower())
    it = sum(1 for p in parole if p in _PAROLE_IT)
    en = sum(1 for p in parole if p in _PAROLE_EN)
    if lingua == "en":
        return not (it >= 3 and it > en)
    return not (en >= 3 and en > it)


def _formatta(punti: list) -> str:
    out = []
    for p in punti:
        p = p.strip()
        if not _completo(p):
            p += "."
        out.append(f"- {p}")
    return "\n".join(out)


# ------------------------------------------------------------------ agente

def chiedi_agente(
    ruolo: str,
    compito: str,
    contesto: str,
    max_t: int = 800,
    pausa: int = 6,
    lingua: str = "it",
) -> str:
    print(f"[>] Al lavoro: {ruolo}...")
    time.sleep(pausa)

    if lingua == "en":
        prompt = (
            f"Role: {ruolo}\n"
            f"Objective: {compito}\n\n"
            f"DATA:\n{contesto}\n\n"
            "MANDATORY CONSTRAINTS:\n"
            "- Reply EXCLUSIVELY in English.\n"
            "- Write exactly 2 bullet points preceded by a dash '- '.\n"
            "- Each point must be a single sentence of at most 25 words.\n"
            "- You MUST end every line with a full stop '.' before stopping.\n"
            "- No preamble, no comments in any other language."
        )
        sistema = (
            "You are an institutional equity analyst. Reply "
            "exclusively in English with 2 clear, complete and concise bullet points."
        )
        errore_api = "- Data currently unavailable due to API overload."
    else:
        prompt = (
            f"Ruolo: {ruolo}\n"
            f"Obiettivo: {compito}\n\n"
            f"DATI:\n{contesto}\n\n"
            "VINCOLI TASSATIVI:\n"
            "- Rispondi ESCLUSIVAMENTE in lingua italiana.\n"
            "- Scrivi esattamente 2 punti elenco preceduti da trattino '- '.\n"
            "- Ogni punto deve essere una singola frase di massimo 25 parole.\n"
            "- Termina OBBLIGATORIAMENTE ogni riga con il punto fermo '.' prima di"
            " fermarti.\n"
            "- Nessun preambolo, nessun commento in inglese."
        )
        sistema = (
            "Sei un equity analyst istituzionale. Rispondi "
            "esclusivamente in lingua italiana con 2 punti elenco chiari, completi e sintetici."
        )
        errore_api = "- Dati al momento non disponibili per sovraccarico API."

    # La chiave mancante è un errore di configurazione: inutile riprovare.
    try:
        chiave = _chiave()
    except RuntimeError as e:
        print(f"[!] {e}")
        return f"{errore_api} (dettaglio: {e})"

    tentativi = 5
    ultimo_errore = ""
    modello = MODELLO
    # Nei modelli Gemini i token di ragionamento contano nel limite di uscita:
    # si lascia il doppio di max_t, altrimenti la risposta resta vuota o tagliata.
    max_uscita = max_t * 2
    con_ragionamento = True
    candidato = None  # miglior risposta utilizzabile, se nessuna è perfetta

    def passa_a_riserva() -> bool:
        nonlocal modello
        if MODELLO_RISERVA and modello != MODELLO_RISERVA:
            modello = MODELLO_RISERVA
            print(f"[i] Passo al modello di riserva: {MODELLO_RISERVA}")
            return True
        return False

    for tentativo in range(tentativi):
        try:
            corpo = {
                "model": modello,
                "messages": [
                    {"role": "system", "content": sistema},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.4,
                "max_tokens": max_uscita,
            }
            if con_ragionamento:
                corpo["reasoning_effort"] = "low"

            r = requests.post(
                URL_API,
                headers={"Authorization": f"Bearer {chiave}", "Content-Type": "application/json"},
                json=corpo,
                timeout=60,
            )

            if r.status_code != 200:
                ultimo_errore = f"HTTP {r.status_code}: {r.text[:300]}"
                testo_err = r.text.lower()
                if r.status_code == 429:
                    if "per day" in testo_err or "perday" in testo_err:
                        # Il limite giornaliero riguarda il modello: la riserva ha quote proprie.
                        print("[!] Limite GIORNALIERO raggiunto.")
                        if passa_a_riserva():
                            continue
                        break
                    attesa = _attesa_da_errore(testo_err, tentativo)
                    print(f"[!] Limite raggiunto, attesa di {attesa:.0f} secondi... (tentativo {tentativo + 1}/{tentativi})")
                    print(f"    [dettaglio] {ultimo_errore}")
                    if tentativo >= 1:
                        passa_a_riserva()
                    time.sleep(attesa)
                elif r.status_code in (500, 502, 503, 504):
                    attesa = min(8 * (tentativo + 1), 40)
                    print(f"[!] Servizio sovraccarico ({r.status_code}), attesa di {attesa} secondi... (tentativo {tentativo + 1}/{tentativi})")
                    if tentativo >= 1:
                        passa_a_riserva()
                    time.sleep(attesa)
                elif r.status_code == 400 and con_ragionamento and "reasoning" in testo_err:
                    con_ragionamento = False  # il modello non supporta reasoning_effort
                    print("[i] Modello senza reasoning_effort: riprovo senza.")
                elif r.status_code == 404:
                    # Nome del modello inesistente: prova la riserva, altrimenti basta.
                    print(f"[!] Modello '{modello}' non trovato: {ultimo_errore}")
                    if passa_a_riserva():
                        continue
                    break
                else:
                    print(f"[!] Errore API: {ultimo_errore}")
                    if r.status_code in (401, 403):
                        break  # chiave non valida o non autorizzata: inutile riprovare
                    time.sleep(3)
                continue

            scelta = r.json()["choices"][0]
            testo = (scelta["message"].get("content") or "").strip()
            if "</think>" in testo:
                testo = testo.split("</think>")[-1].strip()
            troncata = scelta.get("finish_reason") == "length"

            if not testo:
                ultimo_errore = "risposta vuota (token esauriti dal ragionamento?)"
                print(f"[!] {ultimo_errore}; riprovo con più spazio (tentativo {tentativo + 1}/{tentativi})")
                max_uscita = int(max_uscita * 1.5)
                time.sleep(2)
                continue

            punti = _estrai_punti(testo)
            valida = (
                len(punti) == 2
                and all(_completo(p) for p in punti)
                and not troncata
                and _lingua_ok(testo, lingua)
            )
            if valida:
                print(f"    [OK] Risposta completata ({len(testo)} caratteri)")
                return _formatta(punti)

            # Risposta imperfetta: la si tiene come ripiego e si riprova.
            if punti and _lingua_ok(testo, lingua):
                candidato = punti
            ultimo_errore = (
                "risposta troncata" if troncata
                else f"formato non valido ({len(punti)} punti)" if len(punti) != 2
                else "frase incompleta o lingua errata"
            )
            print(f"[!] {ultimo_errore}; riprovo (tentativo {tentativo + 1}/{tentativi})")
            if troncata:
                max_uscita = int(max_uscita * 1.5)
            time.sleep(2)

        except Exception as e:
            ultimo_errore = str(e)
            print(f"[!] Errore: {e}")
            # Timeout o problemi di rete: dal secondo tentativo prova la riserva.
            if tentativo >= 1:
                passa_a_riserva()
            time.sleep(3)

    if candidato:
        print("[i] Nessuna risposta perfetta: uso la migliore disponibile.")
        return _formatta(candidato)

    # Il dettaglio resta nella scheda "Risposte degli analisti"; app.py lo toglie dal report.
    return f"{errore_api} (dettaglio: {ultimo_errore[:200]})"
