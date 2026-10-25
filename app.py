"""Interfaccia Streamlit del comitato di ricerca azionaria.

Avvio:  streamlit run app.py
Richiede nella stessa cartella main.py (MODELLO, chiedi_agente)
e report_html.py.
"""
import re
import time

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
import yfinance as yf

from main import MODELLO, chiedi_agente
from report_html import (
    calcola_metriche,
    dati_per_agenti,
    genera_report,
    tabella_metriche,
)

st.set_page_config(page_title="Analisi investimento azionario", page_icon="📈", layout="wide")

# Aspetto della pagina: stessi colori e carattere del report.
st.markdown(
    """
<style>
.block-container{padding-top:2.2rem;max-width:1100px}
[data-testid="stToolbar"],[data-testid="stDecoration"],footer{display:none}
header[data-testid="stHeader"]{background:transparent}
.testata{border-bottom:2px solid #17202b;padding-bottom:.9rem;margin-bottom:1.5rem}
.titolo{font-family:Georgia,"Times New Roman",serif;font-size:2rem;font-weight:700;line-height:1.15;color:#17202b}
.sottotitolo{color:#566273;margin-top:.35rem}
.sez{font-family:Georgia,"Times New Roman",serif;font-size:1.1rem;font-weight:700;color:#17202b;margin:2.2rem 0 .8rem}
.elenco{max-width:46rem}
.voce{border-left:3px solid #1d4e6e;padding-left:.9rem;margin-bottom:1.1rem}
.vt{font-family:Georgia,"Times New Roman",serif;font-size:1rem;font-weight:700;color:#17202b;margin-bottom:.3rem}
.vp{color:#566273;font-size:.9rem;line-height:1.5}
[data-testid="InputInstructions"]{display:none}
div[data-baseweb="input"]:focus-within,div[data-baseweb="base-input"]:focus-within{border-color:#1d4e6e !important;box-shadow:none !important}
[data-testid="stForm"]{border:0;padding:0}
button[kind^="primary"],button[data-testid^="stBaseButton-primary"]{background:#1d4e6e;border-color:#1d4e6e;color:#fff}
button[kind^="primary"]:hover,button[data-testid^="stBaseButton-primary"]:hover{background:#163d57;border-color:#163d57;color:#fff}
</style>
""",
    unsafe_allow_html=True,
)

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


@st.cache_data(ttl=900, show_spinner=False)
def scarica_info(ticker: str) -> dict:
    return yf.Ticker(ticker).info or {}


def esegui_comitato(ticker: str, nome: str, info: dict, m: dict, log) -> dict:
    """Quattro analisti lavorano in modo indipendente sulla stessa scheda dati
    (nessuno legge le risposte degli altri)."""
    dati = dati_per_agenti(nome, ticker, info, m)

    log("Analista contabile")
    contabile = chiedi_agente("Analista Contabile Forense", ISTRUZIONI["contabile"] + REGOLE, dati, max_t=450, pausa=2)

    log("Analista rialzista")
    bull = chiedi_agente("Analista Bull", ISTRUZIONI["bull"] + REGOLE, dati, max_t=450, pausa=4)

    log("Analista ribassista")
    bear = chiedi_agente("Analista Bear", ISTRUZIONI["bear"] + REGOLE, dati, max_t=450, pausa=4)

    log("Economista macro e di settore")
    macro = chiedi_agente("Economista Macro", ISTRUZIONI["macro"] + REGOLE, dati, max_t=400, pausa=4)

    return {
        "bull": bull,
        "bear": bear,
        "contabile": contabile,
        "macro": macro,
    }


# ------------------------------------------------------------------ pagina

st.markdown(
    '<div class="testata"><div class="titolo">Analisi investimento azionario</div>'
    '<div class="sottotitolo">Un report di una pagina su un titolo, preparato da quattro analisti AI '
    "indipendenti.</div></div>",
    unsafe_allow_html=True,
)

with st.form("ricerca"):  # con il form, Invio nel campo avvia l'analisi
    colonna_ticker, colonna_pulsante, _ = st.columns([2, 1.3, 5])
    ticker_input = (
        colonna_ticker.text_input(
            "Ticker", placeholder="Ticker, per esempio V o ENI.MI", label_visibility="collapsed"
        )
        .upper()
        .strip()
    )
    avvia = colonna_pulsante.form_submit_button("Genera report", type="primary", use_container_width=True)

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
        ):
            with st.expander(titolo):
                st.markdown(esito.get(chiave) or "Nessuna risposta.")
else:
    voci = (
        ("Analisi contabile", "Free cash flow, debito, margini e ROE: quanto sono solidi i numeri."),
        ("Tesi rialzista", "Le ragioni più solide per cui l'azienda può crescere o rivalutarsi."),
        ("Tesi ribassista", "I rischi più seri e i segnali che li confermerebbero."),
        ("Macro e settore", "Come tassi, ciclo e regolamentazione incidono su questo settore."),
    )
    riquadri = "".join(
        f'<div class="voce"><div class="vt">{titolo}</div><div class="vp">{testo}</div></div>'
        for titolo, testo in voci
    )
    st.markdown(
        '<div class="sez">Quattro analisti, ciascuno per conto suo</div>'
        f'<div class="elenco">{riquadri}</div>',
        unsafe_allow_html=True,
    )

st.write("")
st.caption(
    "Strumento di analisi automatica.  \n"
    "Non è consulenza in materia di investimenti.  \n"
    "I dati vengono da Yahoo Finance e le analisi da modelli linguistici: verifica le cifre."
)
