"""Interfaccia Streamlit del comitato di ricerca azionaria.

Avvio:  streamlit run app.py
Richiede nella stessa cartella main.py (MODELLO, chiedi_agente)
e report_html.py.
"""
import base64
import re
import time
import urllib.request
from urllib.parse import urlparse

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
import yfinance as yf

from main import MODELLO, chiedi_agente
from report_html import (
    calcola_metriche,
    dati_per_agenti,
    genera_report,
    genera_frammento_report,
    grafico_tradingview,
    tabella_metriche,
    genera_grafico_statico_png,
    genera_pdf_da_html,
)

st.set_page_config(page_title="Analisi azionaria · Equity analysis", page_icon="📈", layout="wide")

# Logo aziendale (facoltativo). Lasciato vuoto non si chiama nessun servizio
# esterno e nel report compare un monogramma con le iniziali dell'azienda.
# Per attivarlo indica un indirizzo con {domain}, per esempio:
#   LOGO_URL = "https://servizio-loghi.example/{domain}"
LOGO_URL = ""

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
[data-testid="stRadio"] > div{justify-content:flex-end}
button[kind^="primary"],button[data-testid^="stBaseButton-primary"]{background:#1d4e6e;border-color:#1d4e6e;color:#fff}
button[kind^="primary"]:hover,button[data-testid^="stBaseButton-primary"]:hover{background:#163d57;border-color:#163d57;color:#fff}
</style>
""",
    unsafe_allow_html=True,
)

# ------------------------------------------------------------------ testi

UI = {
    "it": {
        "titolo": "Analisi investimento azionario",
        "sottotitolo": "Un report di una pagina su un titolo, preparato da quattro analisti AI indipendenti.",
        "cerca_ph": "Nome o ticker, per esempio Apple, Ferrari, V o ENI.MI",
        "cerca_aiuto": "Scrivi il nome o il ticker e premi Invio: i titoli trovati compaiono nel menu accanto.",
        "scegli_ph": "Scegli il titolo dai suggerimenti",
        "nessun_risultato": "Nessun titolo trovato per «{q}».",
        "genera": "Genera report",
        "errore_ticker": "Scegli un titolo dai suggerimenti oppure inserisci un ticker valido, per esempio V, AAPL o ENI.MI.",
        "in_corso": "Analisi di {t} in corso",
        "recupero": "Recupero dei dati da Yahoo Finance",
        "nessun_dato": "Nessun dato trovato per il ticker {t}.",
        "pronto": "Report pronto",
        "interrotta": "Analisi interrotta",
        "log": {"contabile": "Analista contabile", "bull": "Analista rialzista",
                "bear": "Analista ribassista", "macro": "Economista macro e di settore"},
        "ruoli": {"contabile": "Analista Contabile Forense", "bull": "Analista Bull",
                  "bear": "Analista Bear", "macro": "Economista Macro"},
        "tabs": ["Report", "Dati usati", "Risposte degli analisti"],
        "scarica_html": "Scarica Report (HTML)",
        "scarica_pdf": "Scarica Report (PDF)",
        "cap_pdf": "Il PDF è ottimizzato per la stampa in formato A4 e include il grafico a candele statico.",
        "cap_dati": "Tutti i rapporti sono calcolati dal codice, non dai modelli. Qui puoi controllarli.",
        "col_dati": ["Voce", "Valore"],
        "analisti": [("Analisi contabile", "contabile"), ("Tesi rialzista", "bull"),
                     ("Tesi ribassista", "bear"), ("Macro e settore", "macro")],
        "nessuna_risposta": "Nessuna risposta.",
        "lingua_diversa": "Questo report è stato generato in {vecchia}. Premi «Genera report» per ottenerlo in {nuova}.",
        "nomi_lingua": {"it": "italiano", "en": "inglese"},
        "intro": "Quattro analisti, ciascuno per conto suo",
        "voci": (
            ("Analisi contabile", "Free cash flow, debito, margini e ROE: quanto sono solidi i numeri."),
            ("Tesi rialzista", "Le ragioni più solide per cui l'azienda può crescere o rivalutarsi."),
            ("Tesi ribassista", "I rischi più seri e i segnali che li confermerebbero."),
            ("Macro e settore", "Come tassi, ciclo e regolamentazione incidono su questo settore."),
        ),
        "footer": ("Strumento di analisi automatica.  \n"
                   "Non è consulenza in materia di investimenti.  \n"
                   "I dati vengono da Yahoo Finance e le analisi da modelli linguistici: verifica le cifre."),
        "regole": (
            " Usa SOLO i dati forniti e non inventare cifre: se un dato manca scrivi N/D. "
            "I rapporti (debito netto/FCF, rendimento da FCF, potenziale sul target) sono già calcolati: citali, non rifarli. "
            "Rispondi con un elenco puntato di massimo 3 punti, una o due frasi ciascuno, e cita almeno un numero per punto. "
            "Non usare formule come 'compra' o 'vendi'."
        ),
        "istruzioni": {
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
        },
    },
    "en": {
        "titolo": "Equity investment analysis",
        "sottotitolo": "A one-page report on a stock, prepared by four independent AI analysts.",
        "cerca_ph": "Name or ticker, for example Apple, Ferrari, V or ENI.MI",
        "cerca_aiuto": "Type the name or ticker and press Enter: matching stocks appear in the menu next to it.",
        "scegli_ph": "Pick the stock from the suggestions",
        "nessun_risultato": "No stock found for \"{q}\".",
        "genera": "Generate report",
        "errore_ticker": "Pick a stock from the suggestions or enter a valid ticker, for example V, AAPL or ENI.MI.",
        "in_corso": "Analyzing {t}",
        "recupero": "Fetching data from Yahoo Finance",
        "nessun_dato": "No data found for ticker {t}.",
        "pronto": "Report ready",
        "interrotta": "Analysis interrupted",
        "log": {"contabile": "Accounting analyst", "bull": "Bull analyst",
                "bear": "Bear analyst", "macro": "Macro and sector economist"},
        "ruoli": {"contabile": "Forensic Accounting Analyst", "bull": "Bull Analyst",
                  "bear": "Bear Analyst", "macro": "Macro Economist"},
        "tabs": ["Report", "Data used", "Analyst responses"],
        "scarica_html": "Download Report (HTML)",
        "scarica_pdf": "Download Report (PDF)",
        "cap_pdf": "The PDF is optimized for A4 printing and includes the static candlestick chart.",
        "cap_dati": "All ratios are calculated by the code, not by the models. You can check them here.",
        "col_dati": ["Item", "Value"],
        "analisti": [("Accounting analysis", "contabile"), ("Bull case", "bull"),
                     ("Bear case", "bear"), ("Macro and sector", "macro")],
        "nessuna_risposta": "No response.",
        "lingua_diversa": "This report was generated in {vecchia}. Press \"Generate report\" to get it in {nuova}.",
        "nomi_lingua": {"it": "Italian", "en": "English"},
        "intro": "Four analysts, each on their own",
        "voci": (
            ("Accounting analysis", "Free cash flow, debt, margins and ROE: how solid are the numbers."),
            ("Bull case", "The strongest reasons the company can grow or be re-rated."),
            ("Bear case", "The most serious risks and the signals that would confirm them."),
            ("Macro and sector", "How rates, the cycle and regulation affect this sector."),
        ),
        "footer": ("Automated analysis tool.  \n"
                   "This is not investment advice.  \n"
                   "Data comes from Yahoo Finance and the analyses from language models: verify the figures."),
        "regole": (
            " Use ONLY the data provided and do not invent figures: if a figure is missing, write N/A. "
            "The ratios (net debt/FCF, FCF yield, upside to target) are already calculated: quote them, do not recalculate them. "
            "Reply with a bulleted list of at most 3 points, one or two sentences each, and cite at least one number per point. "
            "Do not use phrases such as 'buy' or 'sell'."
        ),
        "istruzioni": {
            "contabile": (
                "Assess earnings quality and financial strength: free cash flow, net debt relative to FCF, "
                "margins and ROE. Flag any figures that look anomalous or inconsistent with each other."
            ),
            "bull": (
                "Present the two strongest reasons the company can grow or be re-rated "
                "(competitive advantage, growth). For each, say what would disprove it."
            ),
            "bear": (
                "Present the two most serious risks (valuation relative to growth and quality, competition, "
                "regulation, the cycle). For each, say which signal would confirm it."
            ),
            "macro": (
                "Explain how rates, the economic cycle, regulation and competition affect this industry. "
                "Reason about the company's actual business model: do not attribute mechanisms to it that do not apply."
            ),
        },
    },
}

TICKER_VALIDO = r"[A-Z0-9.\-=^]{1,15}"


# ------------------------------------------------------------------ dati

@st.cache_data(ttl=900, show_spinner=False)
def scarica_info(ticker: str) -> dict:
    return yf.Ticker(ticker).info or {}


@st.cache_data(ttl=3600, show_spinner=False)
def cerca_titoli(testo: str):
    """Suggerimenti (ticker, nome, borsa) dalla ricerca di Yahoo Finance
    integrata in yfinance. Se la ricerca non è disponibile restituisce una
    lista vuota e l'app accetta comunque un ticker scritto a mano."""
    testo = testo.strip()
    if len(testo) < 2:
        return []
    try:
        quotes = yf.Search(testo, max_results=8, news_count=0).quotes
    except Exception:
        return []
    risultati = []
    for q in quotes:
        if q.get("quoteType") != "EQUITY" or not q.get("symbol"):
            continue
        risultati.append(
            {
                "symbol": q["symbol"],
                "nome": q.get("longname") or q.get("shortname") or q["symbol"],
                "borsa": q.get("exchDisp") or q.get("exchange") or "",
            }
        )
    return risultati


@st.cache_data(ttl=86400, show_spinner=False)
def scarica_logo(sito: str) -> str:
    """Logo come data-URI (così resta nel file scaricato), oppure '' se
    LOGO_URL non è impostato o il download non riesce."""
    if not LOGO_URL or not sito:
        return ""
    dominio = urlparse(sito if "//" in sito else "//" + sito).netloc.lower().removeprefix("www.")
    if not dominio:
        return ""
    try:
        richiesta = urllib.request.Request(LOGO_URL.format(domain=dominio), headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(richiesta, timeout=6) as r:
            tipo = r.headers.get_content_type()
            corpo = r.read(300_000)
        if not tipo.startswith("image/"):
            return ""
        return f"data:{tipo};base64,{base64.b64encode(corpo).decode()}"
    except Exception:
        return ""


@st.cache_data(ttl=900, show_spinner=False)
def scarica_storico(ticker: str):
    """Candele giornaliere degli ultimi due anni per il grafico.

    Prezzi non corretti per i dividendi (auto_adjust=False), così i livelli
    sono confrontabili con il prezzo attuale e con i target degli analisti.
    Se il download fallisce restituisce None: il report si genera lo stesso.
    """
    try:
        df = yf.Ticker(ticker).history(period="2y", interval="1d", auto_adjust=False)
    except Exception:
        return None
    if df is None or df.empty:
        return None
    df = df.dropna(subset=["Open", "High", "Low", "Close"])
    return [
        {
            "time": idx.strftime("%Y-%m-%d"),
            "open": round(float(r["Open"]), 4),
            "high": round(float(r["High"]), 4),
            "low": round(float(r["Low"]), 4),
            "close": round(float(r["Close"]), 4),
        }
        for idx, r in df.iterrows()
    ]


def esegui_comitato(ticker: str, nome: str, info: dict, m: dict, log, lang: str) -> dict:
    """Quattro analisti lavorano in modo indipendente sulla stessa scheda dati
    (nessuno legge le risposte degli altri)."""
    T = UI[lang]
    dati = dati_per_agenti(nome, ticker, info, m, lang)
    regole = T["regole"]
    istr = T["istruzioni"]

    log(T["log"]["contabile"])
    contabile = chiedi_agente(T["ruoli"]["contabile"], istr["contabile"] + regole, dati, max_t=450, pausa=2, lingua=lang)

    log(T["log"]["bull"])
    bull = chiedi_agente(T["ruoli"]["bull"], istr["bull"] + regole, dati, max_t=450, pausa=4, lingua=lang)

    log(T["log"]["bear"])
    bear = chiedi_agente(T["ruoli"]["bear"], istr["bear"] + regole, dati, max_t=450, pausa=4, lingua=lang)

    log(T["log"]["macro"])
    macro = chiedi_agente(T["ruoli"]["macro"], istr["macro"] + regole, dati, max_t=400, pausa=4, lingua=lang)

    return {
        "bull": bull,
        "bear": bear,
        "contabile": contabile,
        "macro": macro,
    }


# ------------------------------------------------------------------ pagina

# Selettore lingua in alto a destra.
_, colonna_lingua = st.columns([9, 1.6])
scelta_lingua = colonna_lingua.radio(
    "Lingua / Language", ["IT", "EN"], horizontal=True, key="lingua_sel", label_visibility="collapsed"
)
lang = "it" if scelta_lingua == "IT" else "en"
T = UI[lang]

st.markdown(
    f'<div class="testata"><div class="titolo">{T["titolo"]}</div>'
    f'<div class="sottotitolo">{T["sottotitolo"]}</div></div>',
    unsafe_allow_html=True,
)

# Ricerca: scrivi nome o ticker e premi Invio, poi scegli dal menu.
colonna_testo, colonna_menu, colonna_pulsante = st.columns([3, 4, 1.6])
testo_ricerca = colonna_testo.text_input(
    "Ricerca", placeholder=T["cerca_ph"], help=T["cerca_aiuto"], key="ricerca", label_visibility="collapsed"
).strip()
opzioni = cerca_titoli(testo_ricerca) if testo_ricerca else []
atteso = testo_ricerca.upper()
indice_iniziale = next((i for i, o in enumerate(opzioni) if o["symbol"] == atteso), None)
scelta = colonna_menu.selectbox(
    "Titolo",
    range(len(opzioni)),
    index=indice_iniziale,
    format_func=lambda i: f"{opzioni[i]['symbol']} · {opzioni[i]['nome']}"
    + (f" ({opzioni[i]['borsa']})" if opzioni[i]["borsa"] else ""),
    placeholder=T["scegli_ph"],
    disabled=not opzioni,
    label_visibility="collapsed",
)
avvia = colonna_pulsante.button(T["genera"], type="primary", use_container_width=True)
if testo_ricerca and not opzioni and not re.fullmatch(TICKER_VALIDO, atteso):
    st.caption(T["nessun_risultato"].format(q=testo_ricerca))

if avvia:
    ticker_input = None
    if opzioni and scelta is not None:
        ticker_input = opzioni[scelta]["symbol"]
    elif not opzioni and re.fullmatch(TICKER_VALIDO, atteso):
        ticker_input = atteso  # ricerca non disponibile: vale il ticker scritto a mano

    if not ticker_input:
        st.error(T["errore_ticker"])
    else:
        with st.status(T["in_corso"].format(t=ticker_input), expanded=True) as status:
            try:
                st.write(T["recupero"])
                info = scarica_info(ticker_input)
                nome = info.get("longName") or info.get("shortName")
                if not nome:
                    raise ValueError(T["nessun_dato"].format(t=ticker_input))

                m = calcola_metriche(info, lang)
                storico = scarica_storico(ticker_input)
                logo = scarica_logo(info.get("website") or "")
                esito = esegui_comitato(ticker_input, nome, info, m, st.write, lang)

                # 1. Genera l'immagine del grafico per il PDF
                immagine_grafico = genera_grafico_statico_png(storico, m)

                # 2. Genera l'HTML completo per il DOWNLOAD (con grafico statico)
                html_report = genera_report(
                    ticker_input, nome, info, m, esito, MODELLO, 
                    grafico_statico=immagine_grafico, 
                    lang=lang, 
                    logo=logo
                )

                # 3. Genera il PDF partendo dall'HTML completo
                try:
                    pdf_bytes = genera_pdf_da_html(html_report)
                except Exception as e_pdf:
                    st.warning(f"Impossibile generare il PDF: {e_pdf}")
                    pdf_bytes = None

                # 4. Genera il frammento HTML per la VISUALIZZAZIONE A SCHERMO (con grafico interattivo)
                html_schermo = genera_frammento_report(
                    ticker_input, nome, info, m, esito, MODELLO,
                    grafico=grafico_tradingview(ticker_input, storico, m, lang),
                    lang=lang,
                    logo=logo,
                )

                st.session_state["risultato"] = {
                    "ticker": ticker_input,
                    "lang": lang,
                    "html": html_report,
                    "html_schermo": html_schermo,
                    "pdf": pdf_bytes,
                    "metriche": tabella_metriche(m, lang),
                    "avvisi": m["avvisi"],
                    "esito": esito,
                }
                status.update(label=T["pronto"], state="complete", expanded=False)
            except Exception as errore:  # mostrato all'utente, non nascosto
                status.update(label=T["interrotta"], state="error")
                st.error(f"{errore}")

# Il risultato resta in session_state: premere "Scarica" non lo fa sparire.
risultato = st.session_state.get("risultato")
if risultato:
    if risultato.get("lang", "it") != lang:
        st.info(
            T["lingua_diversa"].format(
                vecchia=T["nomi_lingua"][risultato.get("lang", "it")], nuova=T["nomi_lingua"][lang]
            )
        )
    scheda_report, scheda_dati, scheda_analisti = st.tabs(T["tabs"])

    with scheda_report:
        components.html(risultato.get("html_schermo", risultato["html"]), height=1500, scrolling=True)
        st.write("") 
        
        col_dl_pdf, col_dl_html = st.columns(2)
        
        with col_dl_pdf:
            if risultato.get("pdf"):
                st.download_button(
                    label="📄 " + T["scarica_pdf"],
                    data=risultato["pdf"],
                    file_name=f"EquityResearch_{risultato['ticker']}_{time.strftime('%Y%m%d')}.pdf",
                    mime="application/pdf",
                    type="primary",
                    use_container_width=True
                )
            else:
                st.button("PDF non disponibile", disabled=True, use_container_width=True)
                
        with col_dl_html:
            st.download_button(
                label="🌐 " + T["scarica_html"],
                data=risultato["html"],
                file_name=f"EquityResearch_{risultato['ticker']}_{time.strftime('%Y%m%d')}.html",
                mime="text/html",
                use_container_width=True
            )
            
        st.caption(T["cap_pdf"])

    with scheda_dati:
        st.caption(T["cap_dati"])
        for avviso in risultato["avvisi"]:
            st.warning(avviso)
        st.dataframe(
            pd.DataFrame(risultato["metriche"], columns=T["col_dati"]),
            hide_index=True,
            use_container_width=True,
        )

    with scheda_analisti:
        esito = risultato["esito"]
        for titolo, chiave in T["analisti"]:
            with st.expander(titolo):
                st.markdown(esito.get(chiave) or T["nessuna_risposta"])
else:
    riquadri = "".join(
        f'<div class="voce"><div class="vt">{titolo}</div><div class="vp">{testo}</div></div>'
        for titolo, testo in T["voci"]
    )
    st.markdown(
        f'<div class="sez">{T["intro"]}</div><div class="elenco">{riquadri}</div>',
        unsafe_allow_html=True,
    )

st.write("")
st.caption(T["footer"])
