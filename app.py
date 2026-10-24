"""Interfaccia Streamlit del comitato di ricerca azionaria.

Avvio:  streamlit run app.py
Richiede nella stessa cartella main.py (MODELLO, chiedi_agente, client)
e report_html.py.
"""
import re
import time

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
import yfinance as yf

from main import MODELLO, chiedi_agente, client
from report_html import (
    calcola_metriche,
    dati_per_agenti,
    estrai_campi,
    genera_report,
    tabella_metriche,
)

st.set_page_config(page_title="Comitato di ricerca azionaria", page_icon="📈", layout="wide")

# Pause tra le chiamate, per restare nei limiti di richieste del piano Groq.
PAUSA_PRE_RESPONSABILE = 10

REGOLE = (
    " Usa SOLO i dati forniti e non inventare cifre: se un dato manca scrivi N/D. "
    "I rapporti (debito netto/FCF, rendimento da FCF, potenziale sul target) sono già calcolati: citali, non rifarli. "
    "Rispondi con un elenco puntato di massimo 3 punti, una o due frasi ciascuno, e cita almeno un numero per punto. "
    "Non usare formule come 'compra' o 'vendi'."
)

ISTRUZIONI = {
    "contabile": (
        "Valuta la qualità degli utili e la solidità finanziaria: free cash flow, debito netto rispetto al FCF, "
        "margini e ROE. Segnala dati che sembrano anomali o incoerenti tra loro."
    ),
    "bull": (
        "Presenta le due ragioni più solide per cui l'azienda può crescere o essere rivalutata "
        "(vantaggio competitivo, crescita). Per ciascuna indica cosa la smentirebbe."
    ),
    "bear": (
        "Presenta i due rischi più seri (valutazione rispetto a crescita e qualità, concorrenza, "
        "regolamentazione, ciclo). Per ciascuno indica quale segnale lo confermerebbe."
    ),
    "macro": (
        "Spiega come tassi, ciclo economico, regolamentazione e concorrenza incidono su questa industria. "
        "Ragiona sul modello di business reale dell'azienda: non attribuirle meccanismi che non le appartengono."
    ),
}

REGOLA_PUNTEGGIO = (
    "Il punteggio misura insieme la qualità del business e la convenienza del prezzo attuale: "
    "80-100 business eccellente a un prezzo ragionevole; 60-79 buon business con prezzo pieno o qualche dubbio; "
    "40-59 equilibrio tra pregi e difetti; sotto 40 rischi o prezzo che prevalgono."
)


@st.cache_data(ttl=900, show_spinner=False)
def scarica_info(ticker: str) -> dict:
    return yf.Ticker(ticker).info or {}


def esegui_comitato(ticker: str, nome: str, info: dict, m: dict, log) -> dict:
    """Quattro analisti lavorano in modo indipendente sulla stessa scheda dati
    (nessuno legge le risposte degli altri); poi il responsabile le confronta."""
    dati = dati_per_agenti(nome, ticker, info, m)

    log("Analista contabile")
    contabile = chiedi_agente("Analista Contabile Forense", ISTRUZIONI["contabile"] + REGOLE, dati, max_t=450, pausa=2)

    log("Analista rialzista")
    bull = chiedi_agente("Analista Bull", ISTRUZIONI["bull"] + REGOLE, dati, max_t=450, pausa=4)

    log("Analista ribassista")
    bear = chiedi_agente("Analista Bear", ISTRUZIONI["bear"] + REGOLE, dati, max_t=450, pausa=4)

    log("Economista macro e di settore")
    macro = chiedi_agente("Economista Macro", ISTRUZIONI["macro"] + REGOLE, dati, max_t=400, pausa=4)

    log("Responsabile del comitato: confronto delle analisi")
    time.sleep(PAUSA_PRE_RESPONSABILE)
    prompt = (
        f"DATI:\n{dati}\n\n"
        f"ANALISI CONTABILE:\n{contabile}\n\n"
        f"TESI RIALZISTA:\n{bull}\n\n"
        f"TESI RIBASSISTA:\n{bear}\n\n"
        f"MACRO E SETTORE:\n{macro}\n\n"
        "COMPITO: confronta le analisi e controlla che siano coerenti con i dati numerici; "
        "se una affermazione contraddice i dati, segnalalo nella sintesi. "
        f"{REGOLA_PUNTEGGIO}\n"
        "Rispondi con queste righe, senza altro testo:\n"
        "GIUDIZIO: [MOLTO FAVOREVOLE, FAVOREVOLE, NEUTRALE, SFAVOREVOLE]\n"
        "SCORE: [numero intero da 1 a 100]\n"
        "SINTESI: [2 o 3 frasi: perché questo giudizio, tenendo conto del prezzo]\n"
        "CAMBIA_IDEA: [1 o 2 frasi: quali fatti o quale prezzo cambierebbero il giudizio]"
    )
    risposta = client.chat.completions.create(
        model=MODELLO,
        messages=[
            {
                "role": "system",
                "content": (
                    "Sei il responsabile di un comitato di ricerca azionaria. Sintetizzi il lavoro di quattro "
                    "analisti indipendenti usando solo i dati e le analisi forniti. Non dai istruzioni operative "
                    "personalizzate e non usi formule come 'acquista' o 'vendi'."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
        max_tokens=450,
        extra_body={"reasoning_format": "hidden"},
    )
    testo = risposta.choices[0].message.content or ""
    if "</think>" in testo:
        testo = testo.split("</think>")[-1].strip()

    campi = estrai_campi(testo)
    trovato = re.search(r"\d+", campi.get("SCORE", ""))
    score = min(100, max(1, int(trovato.group()))) if trovato else None  # se manca resta N/D, nessun valore inventato

    return {
        "giudizio": campi.get("GIUDIZIO"),
        "score": score,
        "sintesi": campi.get("SINTESI") or (testo if not campi else None),
        "cambia_idea": campi.get("CAMBIA_IDEA"),
        "bull": bull,
        "bear": bear,
        "contabile": contabile,
        "macro": macro,
        "_grezzo": testo,
    }


# ------------------------------------------------------------------ pagina

st.title("Comitato di ricerca azionaria")
st.caption("Un report di una pagina su un titolo, preparato da quattro analisti AI indipendenti e riassunto da un responsabile.")

with st.sidebar:
    st.subheader("Titolo da analizzare")
    ticker_input = st.text_input("Ticker", value="V", help="Esempi: V, AAPL, ENI.MI").upper().strip()
    avvia = st.button("Genera report", type="primary", use_container_width=True)
    st.caption(
        "Strumento di analisi automatica. Non è consulenza in materia di investimenti. "
        "I dati vengono da Yahoo Finance e le analisi da modelli linguistici: verifica le cifre."
    )

if avvia:
    if not re.fullmatch(r"[A-Z0-9.\-=^]{1,15}", ticker_input):
        st.error("Ticker non valido. Inserisci per esempio V, AAPL o ENI.MI.")
    else:
        with st.status(f"Analisi di {ticker_input} in corso", expanded=True) as status:
            try:
                st.write("Recupero dei dati da Yahoo Finance")
                info = scarica_info(ticker_input)
                nome = info.get("longName") or info.get("shortName")
                if not nome:
                    raise ValueError(f"Nessun dato trovato per il ticker {ticker_input}.")

                m = calcola_metriche(info)
                esito = esegui_comitato(ticker_input, nome, info, m, st.write)
                html_report = genera_report(ticker_input, nome, info, m, esito, MODELLO)

                st.session_state["risultato"] = {
                    "ticker": ticker_input,
                    "html": html_report,
                    "metriche": tabella_metriche(m),
                    "avvisi": m["avvisi"],
                    "esito": esito,
                }
                status.update(label="Report pronto", state="complete", expanded=False)
            except Exception as errore:  # mostrato all'utente, non nascosto
                status.update(label="Analisi interrotta", state="error")
                st.error(f"{errore}")

# Il risultato resta in session_state: premere "Scarica" non lo fa sparire.
risultato = st.session_state.get("risultato")
if risultato:
    scheda_report, scheda_dati, scheda_analisti = st.tabs(["Report", "Dati usati", "Risposte degli analisti"])

    with scheda_report:
        components.html(risultato["html"], height=1250, scrolling=True)
        st.download_button(
            "Scarica il report (HTML)",
            data=risultato["html"],
            file_name=f"Report_{risultato['ticker']}_{time.strftime('%Y%m%d')}.html",
            mime="text/html",
        )
        st.caption("Per ottenere un PDF apri il file scaricato nel browser e scegli Stampa, formato A4.")

    with scheda_dati:
        st.caption("Tutti i rapporti sono calcolati dal codice, non dai modelli. Qui puoi controllarli.")
        for avviso in risultato["avvisi"]:
            st.warning(avviso)
        st.dataframe(
            pd.DataFrame(risultato["metriche"], columns=["Voce", "Valore"]),
            hide_index=True,
            use_container_width=True,
        )

    with scheda_analisti:
        esito = risultato["esito"]
        for titolo, chiave in (
            ("Analisi contabile", "contabile"),
            ("Tesi rialzista", "bull"),
            ("Tesi ribassista", "bear"),
            ("Macro e settore", "macro"),
            ("Risposta completa del responsabile", "_grezzo"),
        ):
            with st.expander(titolo):
                st.markdown(esito.get(chiave) or "Nessuna risposta.")
else:
    st.info("Inserisci un ticker nella barra laterale e premi Genera report.")