"""Metriche e report HTML per il comitato di ricerca azionaria.

Il modulo non dipende da Streamlit né dal modello linguistico: si può
provare da solo con `python report_html.py`, che crea `anteprima_esempio.html`
con dati di fantasia.
"""
from __future__ import annotations

import html
import json
import re
import time
import base64
import io

from contextvars import ContextVar
from datetime import date

# Import per il grafico statico e il PDF
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd

# ------------------------------------------------------------------ lingua
# La lingua corrente vive in una ContextVar: ogni sessione Streamlit gira nel
# suo thread, quindi due utenti con lingue diverse non si disturbano.
_LANG = ContextVar("lingua_report", default="it")

STR = {
    "it": {
        "nd": "N/D", "mld": "mld", "mln": "mln",
        "av_prezzo": "Prezzo non disponibile.",
        "av_fcf": "Free cash flow non disponibile: i rapporti che lo usano non sono calcolati.",
        "av_valuta": "Il prezzo è in {v} e il bilancio in {vb}: rendimento e multiplo sul free cash flow non sono calcolati.",
        "cassa_netta": "Cassa netta", "fcf_neg": "FCF non positivo", "anni_fcf": "anni di FCF",
        "margine_netto": "Margine netto", "margine_op": "Margine operativo", "roe": "ROE",
        "crescita": "Crescita ricavi (trimestre su anno)", "fcf": "Free cash flow", "cassa": "Cassa",
        "debito": "Debito totale", "debito_netto": "Debito netto", "dn_fcf": "Debito netto rispetto al FCF",
        "mcap": "Capitalizzazione", "ev": "Valore d'impresa (EV)", "pe_fwd": "P/E atteso (forward)",
        "pe_trail": "P/E storico (trailing)", "ev_ebitda": "EV / EBITDA", "p_fcf": "Prezzo / free cash flow",
        "fcf_yield": "Rendimento da free cash flow", "upside": "Potenziale rispetto al target medio",
        "prezzo": "Prezzo", "range52": "Minimo / massimo 52 settimane", "range_target": "Target minimo / medio / massimo",
        "ag_azienda": "Azienda", "ag_settore": "Settore", "ag_industria": "Industria", "ag_mcap": "Capitalizzazione",
        "ag_52": "Intervallo 52 settimane", "ag_target": "Target analisti (min / medio / max)",
        "ag_upside": "Potenziale sul target medio", "ag_pfcf": "Prezzo/FCF", "ag_yield": "Rendimento da FCF",
        "ag_crescita": "Crescita ricavi (trimestre su anno)", "ag_dnfcf": "Debito netto / FCF (anni)",
        "ag_avvisi": "Avvisi sui dati",
        "ag_nota": "I rapporti sono già calcolati dal sistema: non rifare i calcoli.",
        "dato_nd": "Dato non disponibile.", "intervalli_nd": "Intervalli di prezzo non disponibili.",
        "ultime52": "Ultime 52 settimane", "target_analisti": "Target degli analisti",
        "nota_valori": "Valori in {v}. La linea verticale è il prezzo attuale.",
        "nota_target": " Il segno scuro è il target medio ({t}{up}{n}).",
        "up_sul_prezzo": ", {x} sul prezzo", "n_analisti": ", {n} analisti",
        "tv_titolo": "Andamento del prezzo", "tv_nd": "Storico dei prezzi non disponibile.",
        "tv_offline": "Grafico non disponibile: serve una connessione internet.",
        "tv_prezzo": "Prezzo {x}", "tv_target": "Target medio {x}", "tv_tmin": "Target min {x}", "tv_tmax": "Target max {x}",
        "tv_1a": "1A", "tv_2a": "2A",
        "tv_f50": "Media 50 giorni", "tv_f200": "Media 200 giorni", "tv_fprezzo": "prezzo",
        "tv_fdist": "Distanza dal target medio", "tv_fmax": "Dal massimo 52 settimane", "tv_fmin": "Dal minimo 52 settimane",
        "tv_nota": ("Valori in {v}. Fascia azzurra: intervallo dei target degli analisti. "
                    "Linea blu continua: target medio. Linea nera punteggiata: prezzo attuale. "
                    "Linea arancione: media a 50 giorni. Linea viola: media a 200 giorni. "
                    "Prezzi da Yahoo Finance, fonte non ufficiale."),
        # --- RSI (settimanale) ---
        "rsi_titolo": "RSI settimanale (14) e divergenze",
        "rsi_nd": "Storico insufficiente per calcolare l'RSI settimanale.",
        "rsi_ipercomprato": "Ipercomprato (70)",
        "rsi_ipovenduto": "Ipovenduto (30)",
        "rsi_div_rialzista": "Divergenza rialzista",
        "rsi_div_ribassista": "Divergenza ribassista",
        "rsi_nessuna_div": "Nessuna divergenza rilevata negli ultimi 2 anni.",
        "rsi_nota": ("RSI a 14 periodi (metodo Wilder) calcolato sulle chiusure settimanali: "
                     "ogni punto è una settimana, l'ultima è quella in corso. Linee a 30 e 70. "
                     "La divergenza è segnalata quando prezzo e RSI si muovono in direzioni opposte "
                     "tra due pivot consecutivi."),
        "rsi_valore_attuale": "RSI settimanale attuale: {x}",
        # --- confronto con i concorrenti ---
        "conf_titolo": "Confronto con i concorrenti",
        "conf_nd": "Confronto con i concorrenti non disponibile: non sono stati trovati titoli comparabili.",
        "conf_col_metrica": "Indicatore", "conf_col_verdetto": "Rispetto ai concorrenti",
        "conf_fav": "Favorevole", "conf_con": "Sfavorevole", "conf_lin": "In linea",
        "conf_h_fav": "Punti a favore", "conf_h_con": "Punti a sfavore",
        "conf_nessuno": "Nessuno scostamento significativo rispetto ai concorrenti.",
        "conf_frase": "{lab}: {v} contro una media di {ref} dei concorrenti ({det}).",
        "conf_sintesi": "Su {n} indicatori confrontabili, {t} risulta favorevole in {f}, sfavorevole in {c} e in linea in {l}.",
        "conf_sel_auto": "Concorrenti scelti tra le maggiori società dell&rsquo;industria per capitalizzazione, secondo Yahoo Finance: {l}.",
        "conf_sel_man": "Concorrenti indicati dall&rsquo;utente: {l}.",
        "conf_metodo": ("Per multipli e leva un valore più basso è favorevole; per margini, ROE, crescita, rendimento da FCF "
                        "e potenziale sul target uno più alto. Lo scostamento è giudicato rispetto alla media dei concorrenti "
                        "ed è significativo oltre il 10% per i multipli, da 1 a 3 punti percentuali per gli altri indicatori "
                        "e mezzo anno di FCF per la leva. Confronto indicativo: valute e principi contabili possono differire "
                        "e un multiplo basso non implica che il titolo sia sottovalutato."),
        "html_lang": "it", "titolo_report": "Report del comitato", "data_fmt": "%d/%m/%Y",
        "report_del": "Report del {d}", "dati_alle": "Dati aggiornati alle {t}",
        "settore_nd": "Settore non disponibile",
        "h_prezzo_target": "Prezzo e target", "h_bull": "Tesi rialzista", "h_bear": "Tesi ribassista",
        "h_qualita": "Qualità e solidità", "h_valutazione": "Valutazione",
        "h_contabile": "Analisi contabile", "h_macro": "Contesto macro e di settore",
        "f_note": "Note sui dati", "f_fonti": "Fonti e metodo", "f_avvert": "Avvertenze",
        "f_fonti1": "Dati di mercato e di bilancio: Yahoo Finance tramite yfinance, fonte non ufficiale. Rapporti, medie mobili e distanze sono calcolati dal sistema.",
        "f_fonti2": "Le sezioni di analisi sono redatte da modelli linguistici che lavorano in modo indipendente e possono contenere errori.",
        "f_modello": " Modello linguistico utilizzato: {m}.",
        "f_avvert1": "Documento di analisi generale a solo scopo informativo. Non costituisce consulenza in materia di investimenti, raccomandazione personalizzata né sollecitazione all&rsquo;acquisto o alla vendita di strumenti finanziari.",
        "f_avvert2": "I risultati passati non sono indicativi di quelli futuri. Verificare le cifre sui documenti ufficiali della società prima di ogni decisione.",
    },
    "en": {
        "nd": "N/A", "mld": "bn", "mln": "mn",
        "av_prezzo": "Price not available.",
        "av_fcf": "Free cash flow not available: the ratios that use it are not calculated.",
        "av_valuta": "The price is in {v} and the financial statements in {vb}: free cash flow yield and multiple are not calculated.",
        "cassa_netta": "Net cash", "fcf_neg": "FCF not positive", "anni_fcf": "years of FCF",
        "margine_netto": "Net margin", "margine_op": "Operating margin", "roe": "ROE",
        "crescita": "Revenue growth (quarter on year)", "fcf": "Free cash flow", "cassa": "Cash",
        "debito": "Total debt", "debito_netto": "Net debt", "dn_fcf": "Net debt to FCF",
        "mcap": "Market cap", "ev": "Enterprise value (EV)", "pe_fwd": "Forward P/E",
        "pe_trail": "Trailing P/E", "ev_ebitda": "EV / EBITDA", "p_fcf": "Price / free cash flow",
        "fcf_yield": "Free cash flow yield", "upside": "Upside to mean target",
        "prezzo": "Price", "range52": "52-week low / high", "range_target": "Target low / mean / high",
        "ag_azienda": "Company", "ag_settore": "Sector", "ag_industria": "Industry", "ag_mcap": "Market cap",
        "ag_52": "52-week range", "ag_target": "Analyst targets (low / mean / high)",
        "ag_upside": "Upside to mean target", "ag_pfcf": "Price/FCF", "ag_yield": "FCF yield",
        "ag_crescita": "Revenue growth (quarter on year)", "ag_dnfcf": "Net debt / FCF (years)",
        "ag_avvisi": "Data notices",
        "ag_nota": "Ratios are already computed by the system: do not recalculate them.",
        "dato_nd": "Data not available.", "intervalli_nd": "Price ranges not available.",
        "ultime52": "Last 52 weeks", "target_analisti": "Analyst targets",
        "nota_valori": "Values in {v}. The vertical line is the current price.",
        "nota_target": " The dark mark is the mean target ({t}{up}{n}).",
        "up_sul_prezzo": ", {x} vs. price", "n_analisti": ", {n} analysts",
        "tv_titolo": "Price history", "tv_nd": "Price history not available.",
        "tv_offline": "Chart not available: an internet connection is required.",
        "tv_prezzo": "Price {x}", "tv_target": "Mean target {x}", "tv_tmin": "Target low {x}", "tv_tmax": "Target high {x}",
        "tv_1a": "1Y", "tv_2a": "2Y",
        "tv_f50": "50-day average", "tv_f200": "200-day average", "tv_fprezzo": "price",
        "tv_fdist": "Distance from mean target", "tv_fmax": "From 52-week high", "tv_fmin": "From 52-week low",
        "tv_nota": ("Values in {v}. Blue band: range of analyst targets. "
                    "Solid blue line: mean target. Dotted black line: current price. "
                    "Orange line: 50-day average. Purple line: 200-day average. "
                    "Prices from Yahoo Finance, unofficial source."),
        # --- RSI (weekly) ---
        "rsi_titolo": "Weekly RSI (14) and divergences",
        "rsi_nd": "Not enough history to compute the weekly RSI.",
        "rsi_ipercomprato": "Overbought (70)",
        "rsi_ipovenduto": "Oversold (30)",
        "rsi_div_rialzista": "Bullish divergence",
        "rsi_div_ribassista": "Bearish divergence",
        "rsi_nessuna_div": "No divergence detected over the last 2 years.",
        "rsi_nota": ("14-period RSI (Wilder method) computed on weekly closes: "
                     "each point is one week, the last being the current week. Lines at 30 and 70. "
                     "A divergence is flagged when price and RSI move in opposite directions "
                     "between two consecutive pivots."),
        "rsi_valore_attuale": "Current weekly RSI: {x}",
        # --- peer comparison ---
        "conf_titolo": "Peer comparison",
        "conf_nd": "Peer comparison not available: no comparable stocks were found.",
        "conf_col_metrica": "Indicator", "conf_col_verdetto": "Versus peers",
        "conf_fav": "Favourable", "conf_con": "Unfavourable", "conf_lin": "In line",
        "conf_h_fav": "Points in favour", "conf_h_con": "Points against",
        "conf_nessuno": "No significant gap versus peers.",
        "conf_frase": "{lab}: {v} versus a peer average of {ref} ({det}).",
        "conf_sintesi": "Across {n} comparable indicators, {t} is favourable on {f}, unfavourable on {c} and in line on {l}.",
        "conf_sel_auto": "Peers chosen among the largest companies in the industry by market cap, according to Yahoo Finance: {l}.",
        "conf_sel_man": "Peers chosen by the user: {l}.",
        "conf_metodo": ("For multiples and leverage a lower value is favourable; for margins, ROE, growth, FCF yield "
                        "and upside to target a higher one. The gap is judged against the peer average "
                        "and is significant beyond 10% for multiples, 1 to 3 percentage points for the other indicators "
                        "and half a year of FCF for leverage. Indicative comparison: currencies and accounting standards may differ "
                        "and a low multiple does not mean the stock is undervalued."),
        "html_lang": "en", "titolo_report": "Committee report", "data_fmt": "%d %b %Y",
        "report_del": "Report dated {d}", "dati_alle": "Data as of {t}",
        "settore_nd": "Sector not available",
        "h_prezzo_target": "Price and target", "h_bull": "Bull case", "h_bear": "Bear case",
        "h_qualita": "Quality and strength", "h_valutazione": "Valuation",
        "h_contabile": "Accounting analysis", "h_macro": "Macro and sector context",
        "f_note": "Data notes", "f_fonti": "Sources and method", "f_avvert": "Disclaimer",
        "f_fonti1": "Market and financial statement data: Yahoo Finance via yfinance, unofficial source. Ratios, moving averages and distances are calculated by the system.",
        "f_fonti2": "The analysis sections are written by independent language models and may contain errors.",
        "f_modello": " Language model used: {m}.",
        "f_avvert1": "General analysis document for information purposes only. It does not constitute investment advice, a personal recommendation or a solicitation to buy or sell financial instruments.",
        "f_avvert2": "Past results are not indicative of future results. Verify the figures against the company&rsquo;s official documents before making any decision.",
    },
}


def _imposta(lang):
    """Imposta la lingua corrente ('it' o 'en'); None lascia quella attuale."""
    if lang in STR:
        _LANG.set(lang)


def _t(chiave: str) -> str:
    return STR[_LANG.get()][chiave]


def _nd() -> str:
    return _t("nd")


# ------------------------------------------------------------------ numeri

def _num(v):
    """Float valido oppure None (gestisce None, 'N/D', NaN, infiniti, stringhe)."""
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    if x != x or x in (float("inf"), float("-inf")):
        return None
    return x


def _it(x, dec=2):
    """Formato numerico della lingua corrente: 1.234,56 (it) oppure 1,234.56 (en)."""
    s = f"{x:,.{dec}f}"
    if _LANG.get() == "it":
        return s.replace(",", "§").replace(".", ",").replace("§", ".")
    return s


def fmt_prezzo(v, valuta):
    x = _num(v)
    return _nd() if x is None else f"{_it(x)} {valuta}"


def fmt_pct(v, dec=1, segno=False):
    x = _num(v)
    if x is None:
        return _nd()
    s = _it(x * 100, dec)
    return ("+" + s if segno and x > 0 else s) + "%"


def fmt_x(v, dec=1):
    x = _num(v)
    return _nd() if x is None else f"{_it(x, dec)}x"


def fmt_grande(v, valuta):
    x = _num(v)
    if x is None:
        return _nd()
    if abs(x) >= 1e9:
        n, unita = x / 1e9, _t("mld")
    elif abs(x) >= 1e6:
        n, unita = x / 1e6, _t("mln")
    else:
        return f"{_it(x, 0)} {valuta}"
    return f"{_it(n, 1 if abs(n) < 100 else 0)} {unita} {valuta}"


# ---------------------------------------------------------------- metriche

def calcola_metriche(info: dict, lang: str = None) -> dict:
    """Ricava dai dati grezzi di Yahoo Finance i rapporti che NON devono
    essere calcolati dal modello linguistico."""
    _imposta(lang)
    g = lambda k: _num(info.get(k))  # noqa: E731

    valuta = info.get("currency") or "USD"
    valuta_bilancio = info.get("financialCurrency") or valuta
    stessa_valuta = valuta == valuta_bilancio

    prezzo = g("currentPrice") or g("regularMarketPrice")
    target = g("targetMeanPrice")
    mcap = g("marketCap")
    fcf = g("freeCashflow")
    cassa = g("totalCash")
    debito = g("totalDebt")
    minimo, massimo = g("fiftyTwoWeekLow"), g("fiftyTwoWeekHigh")

    debito_netto = debito - cassa if debito is not None and cassa is not None else None
    debito_netto_su_fcf = (
        debito_netto / fcf
        if debito_netto is not None and fcf is not None and fcf > 0
        else None
    )
    fcf_yield = fcf / mcap if stessa_valuta and fcf is not None and mcap else None
    p_fcf = mcap / fcf if stessa_valuta and fcf and fcf > 0 and mcap else None
    upside = target / prezzo - 1 if prezzo and target else None
    pos52 = (
        (prezzo - minimo) / (massimo - minimo)
        if prezzo is not None and minimo is not None and massimo is not None and massimo > minimo
        else None
    )

    avvisi = []
    if prezzo is None:
        avvisi.append(_t("av_prezzo"))
    if fcf is None:
        avvisi.append(_t("av_fcf"))
    if not stessa_valuta:
        avvisi.append(_t("av_valuta").format(v=valuta, vb=valuta_bilancio))

    return {
        "valuta": valuta,
        "valuta_bilancio": valuta_bilancio,
        "prezzo": prezzo,
        "target": target,
        "target_min": g("targetLowPrice"),
        "target_max": g("targetHighPrice"),
        "n_analisti": g("numberOfAnalystOpinions"),
        "upside": upside,
        "mcap": mcap,
        "ev": g("enterpriseValue"),
        "fcf": fcf,
        "cassa": cassa,
        "debito": debito,
        "debito_netto": debito_netto,
        "debito_netto_su_fcf": debito_netto_su_fcf,
        "fcf_yield": fcf_yield,
        "p_fcf": p_fcf,
        "pe_fwd": g("forwardPE"),
        "pe_trail": g("trailingPE"),
        "ev_ebitda": g("enterpriseToEbitda"),
        "margine_netto": g("profitMargins"),
        "margine_op": g("operatingMargins"),
        "roe": g("returnOnEquity"),
        "crescita_ricavi": g("revenueGrowth"),
        "min52": minimo,
        "max52": massimo,
        "pos52": pos52,
        "beta": g("beta"),
        "avvisi": avvisi,
    }


def _ratio_debito(m):
    dn = m["debito_netto"]
    if dn is None:
        return _nd()
    if dn <= 0:
        return _t("cassa_netta")
    if m["fcf"] is not None and m["fcf"] <= 0:
        return _t("fcf_neg")
    if m["debito_netto_su_fcf"] is None:
        return _nd()
    return f"{_it(m['debito_netto_su_fcf'], 1)} {_t('anni_fcf')}"


def righe_qualita(m):
    vb = m["valuta_bilancio"]
    return [
        (_t("margine_netto"), fmt_pct(m["margine_netto"])),
        (_t("margine_op"), fmt_pct(m["margine_op"])),
        (_t("roe"), fmt_pct(m["roe"])),
        (_t("crescita"), fmt_pct(m["crescita_ricavi"], segno=True)),
        (_t("fcf"), fmt_grande(m["fcf"], vb)),
        (_t("cassa"), fmt_grande(m["cassa"], vb)),
        (_t("debito"), fmt_grande(m["debito"], vb)),
        (_t("debito_netto"), fmt_grande(m["debito_netto"], vb)),
        (_t("dn_fcf"), _ratio_debito(m)),
    ]


def righe_valutazione(m):
    v = m["valuta"]
    return [
        (_t("mcap"), fmt_grande(m["mcap"], v)),
        (_t("ev"), fmt_grande(m["ev"], v)),
        (_t("pe_fwd"), fmt_x(m["pe_fwd"])),
        (_t("pe_trail"), fmt_x(m["pe_trail"])),
        (_t("ev_ebitda"), fmt_x(m["ev_ebitda"])),
        (_t("p_fcf"), fmt_x(m["p_fcf"])),
        (_t("fcf_yield"), fmt_pct(m["fcf_yield"])),
        (_t("upside"), fmt_pct(m["upside"], segno=True)),
    ]


def tabella_metriche(m, lang: str = None):
    """Elenco (voce, valore) mostrato nella scheda 'Dati usati'."""
    _imposta(lang)
    righe = righe_valutazione(m) + righe_qualita(m)
    righe.append((_t("prezzo"), fmt_prezzo(m["prezzo"], m["valuta"])))
    righe.append((_t("range52"),
                  f"{fmt_prezzo(m['min52'], m['valuta'])} / {fmt_prezzo(m['max52'], m['valuta'])}"))
    righe.append((_t("range_target"),
                  " / ".join(fmt_prezzo(m[k], m["valuta"]) for k in ("target_min", "target", "target_max"))))
    return righe


# ------------------------------------------------------- testo per gli agenti

def _raw(x, dec=2, pct=False):
    if x is None:
        return _nd()
    return f"{x * 100:.{dec}f}%" if pct else f"{x:.{dec}f}"


def _mld(x):
    return _nd() if x is None else f"{x / 1e9:.2f} {_t('mld')}"


def dati_per_agenti(nome: str, ticker: str, info: dict, m: dict, lang: str = None) -> str:
    """Scheda dati consegnata a tutti gli analisti. I rapporti sono già
    calcolati: gli agenti non devono rifarli."""
    _imposta(lang)
    v, vb = m["valuta"], m["valuta_bilancio"]
    righe = [
        f"{_t('ag_azienda')}: {nome} ({ticker})",
        f"{_t('ag_settore')}: {info.get('sector') or _nd()} | {_t('ag_industria')}: {info.get('industry') or _nd()}",
        f"{_t('prezzo')}: {_raw(m['prezzo'])} {v} | {_t('ag_mcap')}: {_mld(m['mcap'])} {v}",
        f"{_t('ag_52')}: {_raw(m['min52'])} - {_raw(m['max52'])} {v}",
        f"{_t('ag_target')}: {_raw(m['target_min'])} / {_raw(m['target'])} / {_raw(m['target_max'])} {v}"
        f" | {_t('ag_upside')}: {_raw(m['upside'], 1, pct=True)}",
        f"P/E forward: {_raw(m['pe_fwd'], 1)} | P/E trailing: {_raw(m['pe_trail'], 1)} | EV/EBITDA: {_raw(m['ev_ebitda'], 1)}",
        f"{_t('ag_pfcf')}: {_raw(m['p_fcf'], 1)} | {_t('ag_yield')}: {_raw(m['fcf_yield'], 1, pct=True)}",
        f"{_t('margine_netto')}: {_raw(m['margine_netto'], 1, pct=True)} | {_t('margine_op')}: {_raw(m['margine_op'], 1, pct=True)}"
        f" | ROE: {_raw(m['roe'], 1, pct=True)}",
        f"{_t('ag_crescita')}: {_raw(m['crescita_ricavi'], 1, pct=True)}",
        f"{_t('fcf')}: {_mld(m['fcf'])} {vb} | {_t('cassa')}: {_mld(m['cassa'])} {vb} | {_t('debito')}: {_mld(m['debito'])} {vb}",
        f"{_t('debito_netto')}: {_mld(m['debito_netto'])} {vb} | {_t('ag_dnfcf')}: {_raw(m['debito_netto_su_fcf'], 2)}",
    ]
    if m["avvisi"]:
        righe.append(f"{_t('ag_avvisi')}: " + " ".join(m["avvisi"]))
    righe.append(_t("ag_nota"))
    return "\n".join(righe)


# ------------------------------------------- grafico TradingView (solo a schermo)

def _media_mobile(valori, n):
    """Media mobile semplice: None finché non ci sono n valori."""
    out = [None] * len(valori)
    if len(valori) < n:
        return out
    somma = sum(valori[:n])
    out[n - 1] = somma / n
    for i in range(n, len(valori)):
        somma += valori[i] - valori[i - n]
        out[i] = somma / n
    return out


_TV_CSS = """
<style>
.tv-barra{display:flex;gap:6px;margin:0 0 8px}
.tv-barra button{font:600 11px var(--sans);padding:3px 11px;border:1px solid var(--rule);background:#fff;color:var(--slate);cursor:pointer}
.tv-barra button.on{background:var(--accent);border-color:var(--accent);color:#fff}
.tv-box{position:relative;height:320px;border:1px solid var(--rule);overflow:hidden}
.tv-banda{position:absolute;left:0;display:none;pointer-events:none;z-index:3;
background:rgba(200, 200, 200, 0.1);border-top:1px solid rgba(200, 200, 200, 0.3);border-bottom:1px solid rgba(200, 200, 200, 0.3)}
.tv-fatti{display:flex;flex-wrap:wrap;gap:4px 22px;margin-top:6px;font-size:11.5px;color:var(--slate)}
.tv-fatti b{color:var(--ink);font-variant-numeric:tabular-nums}
@media print{.tv{display:none}}
</style>
"""

_TV_JS = """
<script src="https://unpkg.com/lightweight-charts@4.2.0/dist/lightweight-charts.standalone.production.js"></script>
<script>
(function(){
  var D = __DATI__;
  var box = document.getElementById('tv-chart');
  if (typeof LightweightCharts === 'undefined') {
    box.innerHTML = '<p class="nd" style="padding:12px"></p>'; box.firstChild.textContent = D.msg;
    return;
  }
  var chart = LightweightCharts.createChart(box, {
    width: box.clientWidth, height: 320,
    layout: {background: {type: 'solid', color: '#ffffff'}, textColor: '#566273', fontSize: 11,
             fontFamily: '"Segoe UI","Helvetica Neue",Arial,sans-serif'},
    grid: {vertLines: {color: '#f1f3f6'}, horzLines: {color: '#f1f3f6'}},
    rightPriceScale: {borderColor: '#e2e6ec', scaleMargins: {top: 0.08, bottom: 0.08}},
    timeScale: {borderColor: '#e2e6ec'},
    crosshair: {mode: 0,
      vertLine: {color: '#cbd5e1', labelBackgroundColor: '#64748b'},
      horzLine: {color: '#cbd5e1', labelBackgroundColor: '#64748b'}}
  });
  var L = D.livelli;
  var estremi = [L.tmin, L.tmax, L.target].filter(function(x){ return x !== null; });
  var cs = chart.addCandlestickSeries({
    upColor: '#2b7a57', downColor: '#a8412f', borderVisible: false,
    wickUpColor: '#2b7a57', wickDownColor: '#a8412f',
    lastValueVisible: false, priceLineVisible: false,
    autoscaleInfoProvider: function(orig) {
      var r = orig();
      if (r !== null && estremi.length) {
        r.priceRange.minValue = Math.min(r.priceRange.minValue, Math.min.apply(null, estremi));
        r.priceRange.maxValue = Math.max(r.priceRange.maxValue, Math.max.apply(null, estremi));
      }
      return r;
    }
  });
  cs.setData(D.candele);

  function media(dati, colore) {
    if (!dati.length) return;
    var s = chart.addLineSeries({color: colore, lineWidth: 1, lastValueVisible: false,
                                 priceLineVisible: false, crosshairMarkerVisible: false});
    s.setData(dati);
  }
  media(D.sma50, '#d9a94f');
  media(D.sma200, '#9482b8');

  function linea(prezzo, titolo, coloreLinea, coloreSfondo, coloreTesto, spessore) {
    if (prezzo === null) return;
    cs.createPriceLine({
      price: prezzo, 
      title: titolo, 
      color: coloreLinea, 
      lineWidth: spessore, 
      lineStyle: 0, // 0 = linea continua
      axisLabelVisible: true, 
      axisLabelColor: coloreSfondo, 
      axisLabelTextColor: coloreTesto
    });
  }
  
  // I target usano un grigio chiaro continuo. Il prezzo usa un nero.
  var STILE_ESTREMI = {linea: '#94a3b8', sfondo: '#e2e8f0', testo: '#475569'};
  var STILE_MEDIO   = {linea: '#94a3b8', sfondo: '#e2e8f0', testo: '#475569'};
  var STILE_PREZZO  = {linea: '#17202b', sfondo: '#17202b', testo: '#ffffff'};

  linea(L.tmax, D.et.tmax, STILE_ESTREMI.linea, STILE_ESTREMI.sfondo, STILE_ESTREMI.testo, 1);
  linea(L.tmin, D.et.tmin, STILE_ESTREMI.linea, STILE_ESTREMI.sfondo, STILE_ESTREMI.testo, 1);
  linea(L.target, D.et.target, STILE_MEDIO.linea, STILE_MEDIO.sfondo, STILE_MEDIO.testo, 2);
  linea(L.prezzo, D.et.prezzo, STILE_PREZZO.linea, STILE_PREZZO.sfondo, STILE_PREZZO.testo, 1);

  function intervallo(giorni) {
    var ts = chart.timeScale();
    if (!giorni) { ts.fitContent(); return; }
    var ult = D.candele[D.candele.length - 1].time;
    var d = new Date(ult + 'T00:00:00Z');
    d.setUTCDate(d.getUTCDate() - giorni);
    try { ts.setVisibleRange({from: d.toISOString().slice(0, 10), to: ult}); }
    catch (e) { ts.fitContent(); }
  }
  var bottoni = document.querySelectorAll('.tv-barra button');
  Array.prototype.forEach.call(bottoni, function(b) {
    b.addEventListener('click', function() {
      Array.prototype.forEach.call(bottoni, function(x){ x.classList.remove('on'); });
      b.classList.add('on');
      intervallo(parseInt(b.getAttribute('data-g'), 10));
    });
  });
  intervallo(365);

  function adatta() { chart.applyOptions({width: box.clientWidth}); }
  if (typeof ResizeObserver !== 'undefined') { new ResizeObserver(adatta).observe(box); }
  window.addEventListener('resize', adatta);
})();
</script>
"""


def grafico_tradingview(ticker: str, storico, m: dict, lang: str = None) -> str:
    """Sezione HTML con il grafico (Lightweight Charts di TradingView) per
    l'uso a schermo. `storico` è una lista di dict con time (AAAA-MM-GG),
    open, high, low, close. Sul grafico si sovrappongono i livelli del
    report: target medio, fascia min-max dei target e prezzo attuale. Medie
    mobili e distanze sono calcolate qui, non dai modelli linguistici."""
    _imposta(lang)
    if not storico or len(storico) < 20:
        return (
            f'<section class="tv"><h2>{_t("tv_titolo")}</h2>'
            f'<p class="nd">{_t("tv_nd")}</p></section>'
        )

    v = m["valuta"]
    chiusure = [r["close"] for r in storico]
    s50 = _media_mobile(chiusure, 50)
    s200 = _media_mobile(chiusure, 200)

    def serie(ms):
        return [{"time": r["time"], "value": round(x, 4)} for r, x in zip(storico, ms) if x is not None]

    prezzo = m["prezzo"] if m["prezzo"] is not None else chiusure[-1]
    et = {
        "prezzo": _t("tv_prezzo").format(x=_it(prezzo)),
        "target": _t("tv_target").format(x=_it(m["target"])) if m["target"] is not None else "",
        "tmin": _t("tv_tmin").format(x=_it(m["target_min"])) if m["target_min"] is not None else "",
        "tmax": _t("tv_tmax").format(x=_it(m["target_max"])) if m["target_max"] is not None else "",
    }
    dati = {
        "candele": [{k: r[k] for k in ("time", "open", "high", "low", "close")} for r in storico],
        "sma50": serie(s50),
        "sma200": serie(s200),
        "livelli": {
            "prezzo": prezzo,
            "target": m["target"],
            "tmin": m["target_min"],
            "tmax": m["target_max"],
        },
        "et": et,
        "msg": _t("tv_offline"),
    }
    dati_js = json.dumps(dati).replace("</", "<\\/")

    fatti = []
    if s50[-1]:
        fatti.append(f"{_t('tv_f50')} <b>{_it(s50[-1])}</b> ({_t('tv_fprezzo')} {fmt_pct(prezzo / s50[-1] - 1, segno=True)})")
    if s200[-1]:
        fatti.append(f"{_t('tv_f200')} <b>{_it(s200[-1])}</b> ({_t('tv_fprezzo')} {fmt_pct(prezzo / s200[-1] - 1, segno=True)})")
    if m["upside"] is not None:
        fatti.append(f"{_t('tv_fdist')} <b>{fmt_pct(m['upside'], segno=True)}</b>")
    if m["max52"]:
        fatti.append(f"{_t('tv_fmax')} <b>{fmt_pct(prezzo / m['max52'] - 1, segno=True)}</b>")
    if m["min52"]:
        fatti.append(f"{_t('tv_fmin')} <b>{fmt_pct(prezzo / m['min52'] - 1, segno=True)}</b>")
    righe_fatti = "".join(f"<span>{f}</span>" for f in fatti)

    nota = html.escape(_t("tv_nota").format(v=v))

    return (
        '<section class="tv">' + _TV_CSS
        + f"<h2>{_t('tv_titolo')}</h2>"
        + '<div class="tv-barra"><button data-g="90">3M</button><button data-g="180">6M</button>'
        f'<button data-g="365" class="on">{_t("tv_1a")}</button><button data-g="0">{_t("tv_2a")}</button></div>'
        + '<div class="tv-box" id="tv-chart"></div>'
        + f'<p class="nota">{nota}</p>'
        + (f'<div class="tv-fatti">{righe_fatti}</div>' if righe_fatti else "")
        + _TV_JS.replace("__DATI__", dati_js)
        + "</section>"
    )


# --------------------------------------------- RSI e divergenze

def _rsi(chiusure, periodo=14):
    """RSI (Relative Strength Index) con smoothing di Wilder.
    Restituisce una lista allineata a `chiusure` con None dove non calcolabile."""
    n = len(chiusure)
    out = [None] * n
    if n < periodo + 1:
        return out
    guadagni, perdite = [], []
    for i in range(1, n):
        delta = chiusure[i] - chiusure[i - 1]
        guadagni.append(max(delta, 0.0))
        perdite.append(max(-delta, 0.0))
    # media iniziale semplice sui primi `periodo` valori
    media_g = sum(guadagni[:periodo]) / periodo
    media_p = sum(perdite[:periodo]) / periodo

    def _valore(mg, mp):
        if mp == 0:
            return 100.0 if mg > 0 else 50.0
        rs = mg / mp
        return 100.0 - 100.0 / (1.0 + rs)

    out[periodo] = _valore(media_g, media_p)
    for i in range(periodo + 1, n):
        media_g = (media_g * (periodo - 1) + guadagni[i - 1]) / periodo
        media_p = (media_p * (periodo - 1) + perdite[i - 1]) / periodo
        out[i] = _valore(media_g, media_p)
    return out


def _chiusure_settimanali(storico):
    """Un punto per settimana ISO: l'ultima candela giornaliera disponibile.
    L'ultima settimana, se in corso, usa l'ultima chiusura finora."""
    sett = {}
    for r in storico:
        anno, settimana, _ = date.fromisoformat(r["time"]).isocalendar()
        sett[(anno, settimana)] = r
    return list(sett.values())


def _pivot_locali(serie, finestra=5):
    """Trova massimi e minimi locali in una serie (ignora i None).
    Restituisce due liste di indici: (massimi, minimi)."""
    massimi, minimi = [], []
    n = len(serie)
    for i in range(finestra, n - finestra):
        v = serie[i]
        if v is None:
            continue
        intorno = [serie[j] for j in range(i - finestra, i + finestra + 1)
                   if j != i and serie[j] is not None]
        if not intorno:
            continue
        if v >= max(intorno):
            massimi.append(i)
        elif v <= min(intorno):
            minimi.append(i)
    return massimi, minimi


def _trova_divergenze(prezzi, rsi, finestra=5, sguardo=25):
    """Cerca divergenze rialziste e ribassiste tra ultimi due pivot di prezzo.
    Restituisce lista di dict: {tipo, i1, i2} con gli indici degli estremi.
    - rialzista: prezzo fa minimi più bassi, RSI fa minimi più alti.
    - ribassista: prezzo fa massimi più alti, RSI fa massimi più bassi."""
    if not prezzi or len(prezzi) < finestra * 2 + 2:
        return []
    idx_massimi_p, idx_minimi_p = _pivot_locali(prezzi, finestra)
    divergenze = []

    # Divergenze rialziste sui minimi
    if len(idx_minimi_p) >= 2:
        ultimi = idx_minimi_p[-sguardo:] if len(idx_minimi_p) > sguardo else idx_minimi_p
        for k in range(len(ultimi) - 1):
            i1, i2 = ultimi[k], ultimi[k + 1]
            if prezzi[i2] < prezzi[i1] and rsi[i1] is not None and rsi[i2] is not None:
                if rsi[i2] > rsi[i1] + 1.5:  # tolleranza minima
                    divergenze.append({"tipo": "rialzista", "i1": i1, "i2": i2})

    # Divergenze ribassiste sui massimi
    if len(idx_massimi_p) >= 2:
        ultimi = idx_massimi_p[-sguardo:] if len(idx_massimi_p) > sguardo else idx_massimi_p
        for k in range(len(ultimi) - 1):
            i1, i2 = ultimi[k], ultimi[k + 1]
            if prezzi[i2] > prezzi[i1] and rsi[i1] is not None and rsi[i2] is not None:
                if rsi[i2] < rsi[i1] - 1.5:
                    divergenze.append({"tipo": "ribassista", "i1": i1, "i2": i2})

    # Teniamo solo le più recenti (max 2 per tipo)
    div_rialz = [d for d in divergenze if d["tipo"] == "rialzista"][-2:]
    div_ribass = [d for d in divergenze if d["tipo"] == "ribassista"][-2:]
    return div_rialz + div_ribass


_RSI_CSS = """
<style>
.rsi-box{margin-top:14px;border:1px solid var(--rule);padding:10px 12px 6px;background:#fff}
.rsi-head{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:4px}
.rsi-head h3{font:700 12px/1.2 var(--sans);letter-spacing:.05em;text-transform:uppercase;
color:var(--ink);margin:0}
.rsi-head .cur{font-size:12px;color:var(--slate);font-variant-numeric:tabular-nums}
.rsi-head .cur b{color:var(--ink)}
.rsi-svg{display:block;width:100%;height:150px}
.rsi-legenda{display:flex;flex-wrap:wrap;gap:4px 18px;margin-top:4px;font-size:10.5px;color:var(--slate)}
.rsi-legenda .dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:5px;
vertical-align:middle}
.rsi-legenda .r{background:#a8412f}.rsi-legenda .v{background:#2b7a57}
</style>
"""


def grafico_rsi(storico, lang: str = None) -> str:
    """Grafico RSI settimanale a 14 periodi in SVG (funziona anche nel PDF),
    con evidenziazione delle divergenze rialziste/ribassiste rilevate.
    Lo storico giornaliero viene ridotto a una chiusura per settimana."""
    _imposta(lang)
    nd_html = (f'<section class="rsi"><h2>{_t("rsi_titolo")}</h2>'
               f'<p class="nd">{_t("rsi_nd")}</p></section>')

    if not storico or len(storico) < 30:
        return nd_html

    settimanale = _chiusure_settimanali(storico)
    if len(settimanale) < 30:
        return nd_html

    chiusure = [r["close"] for r in settimanale]
    rsi = _rsi(chiusure, 14)
    divergenze = _trova_divergenze(chiusure, rsi, finestra=3)

    W, H = 760, 150
    pad_l, pad_r, pad_t, pad_b = 35, 10, 8, 18
    plot_w = W - pad_l - pad_r
    plot_h = H - pad_t - pad_b
    n = len(rsi)
    validi = [(i, v) for i, v in enumerate(rsi) if v is not None]
    if not validi:
        return nd_html
    i_primo = validi[0][0]

    def x(i):
        return pad_l + (i - i_primo) / max(1, n - 1 - i_primo) * plot_w

    def y(v):
        return pad_t + (1 - v / 100.0) * plot_h

    # Polilinea RSI
    punti = " ".join(f"{x(i):.1f},{y(v):.1f}" for i, v in validi)

    # Linee di divergenza
    linee_div = []
    for d in divergenze:
        colore = "#2b7a57" if d["tipo"] == "rialzista" else "#a8412f"
        x1, y1 = x(d["i1"]), y(rsi[d["i1"]])
        x2, y2 = x(d["i2"]), y(rsi[d["i2"]])
        linee_div.append(
            f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
            f'stroke="{colore}" stroke-width="2" opacity="0.9"/>'
        )
        linee_div.append(
            f'<circle cx="{x1:.1f}" cy="{y1:.1f}" r="3" fill="{colore}"/>'
            f'<circle cx="{x2:.1f}" cy="{y2:.1f}" r="3" fill="{colore}"/>'
        )

    # Etichette asse Y e linee 30/50/70 (tutte continue)
    etichette = ""

    # Linea 50 (continua, grigio chiarissimo)
    etichette += (
        f'<line x1="{pad_l}" y1="{y(50):.1f}" x2="{W - pad_r}" y2="{y(50):.1f}" '
        f'stroke="#e2e8f0" stroke-width="1"/>'
        f'<text x="{pad_l - 6}" y="{y(50) + 4:.1f}" text-anchor="end" '
        f'font-size="10" font-weight="normal" fill="#94a3b8">50</text>'
    )

    # Linea 70 (continua, grigio chiaro)
    etichette += (
        f'<line x1="{pad_l}" y1="{y(70):.1f}" x2="{W - pad_r}" y2="{y(70):.1f}" '
        f'stroke="#cbd5e1" stroke-width="1"/>'
        f'<text x="{pad_l - 6}" y="{y(70) + 4:.1f}" text-anchor="end" '
        f'font-size="11" font-weight="normal" fill="#64748b">70</text>'
    )

    # Linea 30 (continua, grigio chiaro)
    etichette += (
        f'<line x1="{pad_l}" y1="{y(30):.1f}" x2="{W - pad_r}" y2="{y(30):.1f}" '
        f'stroke="#cbd5e1" stroke-width="1"/>'
        f'<text x="{pad_l - 6}" y="{y(30) + 4:.1f}" text-anchor="end" '
        f'font-size="11" font-weight="normal" fill="#64748b">30</text>'
    )

    valore_attuale = rsi[-1] if rsi[-1] is not None else None
    etichetta_attuale = (
        _t("rsi_valore_attuale").format(x=f"{valore_attuale:.1f}")
        if valore_attuale is not None else ""
    )

    # Legenda divergenze
    legenda = []
    ha_rialz = any(d["tipo"] == "rialzista" for d in divergenze)
    ha_ribass = any(d["tipo"] == "ribassista" for d in divergenze)
    if ha_rialz:
        legenda.append(f'<span><span class="dot v"></span>{_t("rsi_div_rialzista")}</span>')
    if ha_ribass:
        legenda.append(f'<span><span class="dot r"></span>{_t("rsi_div_ribassista")}</span>')
    if not legenda:
        legenda.append(f'<span>{_t("rsi_nessuna_div")}</span>')

    return (
        '<section class="rsi">' + _RSI_CSS
        + f"<h2>{_t('rsi_titolo')}</h2>"
        + '<div class="rsi-box">'
        + '<div class="rsi-head">'
        + f'<h3>{_t("rsi_ipercomprato")} / {_t("rsi_ipovenduto")}</h3>'
        + f'<div class="cur"><b>{etichetta_attuale}</b></div>'
        + '</div>'
        + f'<svg class="rsi-svg" viewBox="0 0 {W} {H}" preserveAspectRatio="none" '
          f'xmlns="http://www.w3.org/2000/svg">'
        + etichette
        + f'<polyline points="{punti}" fill="none" stroke="#1d4e6e" stroke-width="1.8"/>'
        + "".join(linee_div)
        + '</svg>'
        + f'<div class="rsi-legenda">{"".join(legenda)}</div>'
        + f'<p class="nota">{html.escape(_t("rsi_nota"))}</p>'
        + '</div>'
        + '</section>'
    )


# --------------------------------------------------------------------- HTML

def testo_html(testo) -> str:
    """Testo del modello -> HTML sicuro (escape, elenchi puntati, grassetto)."""
    if not testo:
        return f'<p class="nd">{_t("dato_nd")}</p>'
    pulito = re.sub(r"<think>.*?</think>", "", str(testo), flags=re.S).strip()
    blocchi, voci = [], []

    def chiudi_elenco():
        if voci:
            blocchi.append("<ul>" + "".join(f"<li>{x}</li>" for x in voci) + "</ul>")
            voci.clear()

    for riga in (r for r in pulito.splitlines() if r.strip()):
        punto = re.match(r"^\s*(?:[-•*–]|\d+[.)])\s+(.*)$", riga)
        corpo = html.escape(punto.group(1) if punto else riga.strip())
        corpo = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", corpo)
        if punto:
            voci.append(corpo)
        else:
            chiudi_elenco()
            blocchi.append(f"<p>{corpo}</p>")
    chiudi_elenco()
    return "".join(blocchi)


def _tabella(righe) -> str:
    celle = []
    for etichetta, valore in righe:
        classe = ' class="nd"' if valore == _nd() else ""
        celle.append(
            f"<tr><th>{html.escape(etichetta)}</th><td{classe}>{html.escape(valore)}</td></tr>"
        )
    return f'<table class="kv">{"".join(celle)}</table>'


def _scala(m):
    """Posizioni (0-100) dei valori sull'asse comune del grafico prezzo/target."""
    p = m["prezzo"]
    valori = [p]
    for k in ("min52", "max52", "target_min", "target_max", "target"):
        if m[k] is not None:
            valori.append(m[k])
    if p is None or len(valori) < 3:
        return None
    basso, alto = min(valori), max(valori)
    margine = ((alto - basso) or abs(p) or 1) * 0.04
    basso, alto = basso - margine, alto + margine
    return lambda x: max(0.0, min(100.0, (x - basso) / (alto - basso) * 100))


def _grafico_prezzo(m) -> str:
    pos = _scala(m)
    if pos is None:
        return f'<p class="nd">{_t("intervalli_nd")}</p>'
    v = m["valuta"]
    righe = []
    if m["min52"] is not None and m["max52"] is not None:
        a, b = pos(m["min52"]), pos(m["max52"])
        righe.append(
            f'<div class="lrow"><div class="ll"><span>{_t("ultime52")}</span>'
            f'<span class="num">{_it(m["min52"])} &ndash; {_it(m["max52"])}</span></div>'
            f'<div class="track"><div class="fill" style="left:{a:.1f}%;width:{b - a:.1f}%"></div></div></div>'
        )
    if m["target_min"] is not None and m["target_max"] is not None:
        a, b = pos(m["target_min"]), pos(m["target_max"])
        tick = f'<div class="tick" style="left:{pos(m["target"]):.1f}%"></div>' if m["target"] is not None else ""
        righe.append(
            f'<div class="lrow"><div class="ll"><span>{_t("target_analisti")}</span>'
            f'<span class="num">{_it(m["target_min"])} &ndash; {_it(m["target_max"])}</span></div>'
            f'<div class="track"><div class="fill t" style="left:{a:.1f}%;width:{b - a:.1f}%"></div>{tick}</div></div>'
        )
    linea = (
        f'<div class="priceline" style="left:{pos(m["prezzo"]):.1f}%"><span>{_it(m["prezzo"])}</span></div>'
    )
    n = m["n_analisti"]
    dettaglio_target = ""
    if m["target"] is not None:
        quanti = _t("n_analisti").format(n=int(n)) if n else ""
        sul_prezzo = _t("up_sul_prezzo").format(x=fmt_pct(m["upside"], segno=True)) if m["upside"] is not None else ""
        dettaglio_target = _t("nota_target").format(t=fmt_prezzo(m["target"], v), up=sul_prezzo, n=quanti)
    nota = f'<p class="nota">{html.escape(_t("nota_valori").format(v=v) + dettaglio_target)}</p>'
    return f'<div class="ladder"><div class="axis">{linea}{"".join(righe)}</div>{nota}</div>'


# ------------------------------------------- confronto con i concorrenti

def _pos(x):
    """Solo valori positivi (un multiplo negativo non è confrontabile)."""
    return x if x is not None and x > 0 else None


def _lev(m):
    """Debito netto / FCF in anni come numero confrontabile: 0 se cassa netta,
    None se non calcolabile."""
    dn = m["debito_netto"]
    if dn is None:
        return None
    if dn <= 0:
        return 0.0
    if m["fcf"] is None or m["fcf"] <= 0:
        return None
    return m["debito_netto_su_fcf"]


def _fmt_lev(x):
    return _t("cassa_netta") if x <= 0 else f"{_it(x, 1)} {_t('anni_fcf')}"


# (chiave testo, valore, formato, direzione, soglia, modo)
# direzione: +1 = più alto è meglio, -1 = più basso è meglio.
# modo "rel": soglia come scostamento relativo; "abs": scostamento assoluto.
_CONF = [
    ("pe_fwd", lambda m: _pos(m["pe_fwd"]), fmt_x, -1, 0.10, "rel"),
    ("ev_ebitda", lambda m: _pos(m["ev_ebitda"]), fmt_x, -1, 0.10, "rel"),
    ("fcf_yield", lambda m: m["fcf_yield"], fmt_pct, 1, 0.01, "abs"),
    ("margine_op", lambda m: m["margine_op"], fmt_pct, 1, 0.03, "abs"),
    ("margine_netto", lambda m: m["margine_netto"], fmt_pct, 1, 0.03, "abs"),
    ("roe", lambda m: m["roe"], fmt_pct, 1, 0.03, "abs"),
    ("crescita", lambda m: m["crescita_ricavi"], lambda x: fmt_pct(x, segno=True), 1, 0.02, "abs"),
    ("dn_fcf", _lev, _fmt_lev, -1, 0.5, "abs"),
    ("upside", lambda m: m["upside"], lambda x: fmt_pct(x, segno=True), 1, 0.03, "abs"),
]


def _cella_conf(chiave, fmt, valore, m_az):
    if chiave == "dn_fcf":
        return _ratio_debito(m_az)
    return _nd() if valore is None else fmt(valore)


def _analisi_confronto(m, concorrenti):
    """Confronta il titolo con la media dei concorrenti, indicatore per
    indicatore. Tutto è calcolato dal codice. Restituisce le righe della
    tabella, i principali punti a favore e contro e i conteggi."""
    tutti = [m] + [c["m"] for c in concorrenti]
    righe, fav, con = [], [], []
    conteggi = {"fav": 0, "con": 0, "lin": 0}
    for chiave, val, fmt, direz, soglia, modo in _CONF:
        valori = [val(x) for x in tutti]
        classi = [""] * len(tutti)

        # Miglior e peggior valore, evidenziati solo se la distanza è significativa.
        presenti = [(direz * x, i) for i, x in enumerate(valori) if x is not None]
        if len(presenti) >= 2:
            grezzi = [x for x in valori if x is not None]
            distanza = max(grezzi) - min(grezzi)
            if modo == "rel":
                media = sum(grezzi) / len(grezzi)
                distanza = distanza / abs(media) if media else 0.0
            migliore = max(p for p, _ in presenti)
            peggiore = min(p for p, _ in presenti)
            if distanza >= soglia and migliore != peggiore:
                for p, i in presenti:
                    if p == migliore:
                        classi[i] = "best"
                    elif p == peggiore:
                        classi[i] = "worst"

        testi = [_cella_conf(chiave, fmt, v, x) for v, x in zip(valori, tutti)]

        # Giudizio rispetto alla media dei concorrenti.
        esito = None
        altri = [x for x in valori[1:] if x is not None]
        if valori[0] is not None and altri:
            ref = sum(altri) / len(altri)
            scarto = valori[0] - ref
            if modo == "rel":
                scarto = scarto / abs(ref) if ref else 0.0
            punteggio = direz * scarto / soglia
            if punteggio >= 1:
                esito = "fav"
                fav.append((punteggio, chiave, testi, fmt(ref)))
            elif punteggio <= -1:
                esito = "con"
                con.append((-punteggio, chiave, testi, fmt(ref)))
            else:
                esito = "lin"
            conteggi[esito] += 1
        righe.append((_t(chiave), list(zip(testi, classi)), esito))

    fav.sort(key=lambda r: r[0], reverse=True)
    con.sort(key=lambda r: r[0], reverse=True)
    return righe, fav[:3], con[:3], conteggi


_VERDETTO = {
    "fav": ("v-fav", "&#9650;", "conf_fav"),
    "con": ("v-con", "&#9660;", "conf_con"),
    "lin": ("v-lin", "=", "conf_lin"),
}


def sezione_confronto(ticker: str, nome: str, m: dict, concorrenti: list,
                      lang: str = None, manuale: bool = False) -> str:
    """Sezione HTML di confronto con i concorrenti. `concorrenti` è una lista
    di dict {ticker, nome, m} dove m sono le metriche di calcola_metriche."""
    _imposta(lang)
    esc = html.escape
    titolo = f"<h2>{_t('conf_titolo')}</h2>"
    vuoto = f'<section class="conf">{titolo}<p class="nd">{_t("conf_nd")}</p></section>'
    if not concorrenti:
        return vuoto

    righe, fav, con, cnt = _analisi_confronto(m, concorrenti)
    totale = sum(cnt.values())
    if totale == 0:
        return vuoto

    intestazione = (
        f'<th>{esc(_t("conf_col_metrica"))}</th>'
        f'<th class="sel" title="{esc(nome, quote=True)}">{esc(ticker)}</th>'
        + "".join(f'<th title="{esc(c["nome"], quote=True)}">{esc(c["ticker"])}</th>' for c in concorrenti)
        + f'<th>{esc(_t("conf_col_verdetto"))}</th>'
    )

    celle_mcap = "".join(
        "<td{}>{}</td>".format(' class="sel"' if k == 0 else "", esc(fmt_grande(x["mcap"], x["valuta"])))
        for k, x in enumerate([m] + [c["m"] for c in concorrenti])
    )
    corpo = [f'<tr><td>{esc(_t("mcap"))}</td>{celle_mcap}<td class="v-lin"></td></tr>']
    for etichetta, celle, esito in righe:
        tds = ""
        for k, (testo, cl) in enumerate(celle):
            classi = " ".join(x for x in ("sel" if k == 0 else "", cl) if x)
            attr = f' class="{classi}"' if classi else ""
            tds += f"<td{attr}>{esc(testo)}</td>"
        if esito:
            cl, glifo, chiave = _VERDETTO[esito]
            verdetto = f'<td class="{cl}">{glifo} {esc(_t(chiave))}</td>'
        else:
            verdetto = f'<td class="v-lin">{esc(_nd())}</td>'
        corpo.append(f"<tr><td>{esc(etichetta)}</td>{tds}{verdetto}</tr>")

    def frasi(voci):
        if not voci:
            return f'<p class="nd">{_t("conf_nessuno")}</p>'
        out = []
        for _, chiave, testi, ref in voci:
            dettaglio = ", ".join(f"{c['ticker']} {t}" for c, t in zip(concorrenti, testi[1:]))
            out.append(_t("conf_frase").format(lab=_t(chiave), v=testi[0], ref=ref, det=dettaglio))
        return "<ul>" + "".join(f"<li>{esc(f)}</li>" for f in out) + "</ul>"

    sintesi = _t("conf_sintesi").format(n=totale, t=ticker, f=cnt["fav"], c=cnt["con"], l=cnt["lin"])
    elenco = ", ".join(f"{c['ticker']} ({c['nome']})" for c in concorrenti)
    selezione = _t("conf_sel_man" if manuale else "conf_sel_auto").format(l=esc(elenco))

    return (
        f'<section class="conf">{titolo}'
        f'<p class="conf-sint">{esc(sintesi)}</p>'
        f'<div class="cmp-wrap"><table class="cmp"><thead><tr>{intestazione}</tr></thead>'
        f'<tbody>{"".join(corpo)}</tbody></table></div>'
        '<div class="cols conf-cols">'
        f'<div class="tesi bull"><h2>{_t("conf_h_fav")}</h2><div class="testo">{frasi(fav)}</div></div>'
        f'<div class="tesi bear"><h2>{_t("conf_h_con")}</h2><div class="testo">{frasi(con)}</div></div>'
        "</div>"
        f'<p class="nota">{selezione} {_t("conf_metodo")}</p>'
        "</section>"
    )


CSS = """
:root{--ink:#17202b;--slate:#566273;--rule:#d6dbe2;--wash:#eef0f3;--accent:#1d4e6e;
--pos:#2b7a57;--neg:#a8412f;
--serif:Georgia,"Times New Roman",serif;--sans:"Segoe UI","Helvetica Neue",Arial,sans-serif}
*{box-sizing:border-box;-webkit-print-color-adjust:exact;print-color-adjust:exact}
body{margin:0;padding:24px 12px;background:var(--wash);color:var(--ink);font:12.5px/1.55 var(--sans)}
.page{max-width:830px;margin:0 auto;background:#fff;padding:34px 40px 26px;border:1px solid var(--rule)}
header{display:flex;justify-content:space-between;align-items:flex-end;gap:24px;
border-bottom:2px solid var(--ink);padding-bottom:12px}
h1{font:700 28px/1.15 var(--serif);margin:0}
.brand{display:flex;align-items:center;gap:14px}
.logo{width:52px;height:52px;object-fit:contain;border:1px solid var(--rule);padding:5px;background:#fff;flex:none}
.mono{width:52px;height:52px;flex:none;display:flex;align-items:center;justify-content:center;background:var(--accent);color:#fff;font:700 19px var(--serif);letter-spacing:.02em}
.sotto{color:var(--slate);margin-top:4px}
.data{text-align:right;color:var(--slate);font-size:11.5px;white-space:nowrap}
h2{font:700 15px/1.3 var(--serif);margin:0 0 8px}
section{margin-top:22px}
.nd{color:var(--slate)}
.ladder{padding:24px 12px 0}
.axis{position:relative}
.lrow{margin-bottom:12px}
.ll{display:flex;justify-content:space-between;gap:8px;font-size:11px;color:var(--slate);margin-bottom:3px}
.num{font-variant-numeric:tabular-nums;color:var(--ink)}
.track{position:relative;height:10px;background:#f1f3f6}
.fill{position:absolute;top:0;bottom:0;background:#c6ced9}
.fill.t{background:#9dbfd6}
.tick{position:absolute;top:-3px;bottom:-3px;width:2px;margin-left:-1px;background:var(--accent)}
.priceline{position:absolute;top:-6px;bottom:0;width:0;border-left:1.5px solid var(--ink);z-index:2}
.priceline span{position:absolute;top:-18px;left:0;transform:translateX(-50%);font-size:11px;font-weight:600;
white-space:nowrap;font-variant-numeric:tabular-nums}
.nota{font-size:10.5px;color:var(--slate);margin:6px 0 0}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:34px}
.tesi{border-top:3px solid var(--rule);padding-top:8px}
.tesi.bull{border-top-color:var(--pos)}.tesi.bear{border-top-color:var(--neg)}
.testo p{margin:0 0 6px}
.testo ul{margin:0;padding-left:16px}
.testo li{margin-bottom:5px}
table.kv{width:100%;border-collapse:collapse}
.kv th,.kv td{padding:4px 0;border-bottom:1px solid var(--rule);font-weight:400;vertical-align:baseline}
.kv th{text-align:left;color:var(--slate);padding-right:12px}
.kv td{text-align:right;font-weight:600;font-variant-numeric:tabular-nums;white-space:nowrap}
.kv td.nd{font-weight:400}
.kv tr:last-child th,.kv tr:last-child td{border-bottom:0}
footer{margin-top:26px;border-top:2px solid var(--ink);padding-top:12px;color:var(--slate);font-size:10.5px;line-height:1.55}
.foot{display:grid;grid-template-columns:1fr 1fr;gap:34px}
footer h3{font:700 9.5px/1.3 var(--sans);letter-spacing:.09em;text-transform:uppercase;color:var(--ink);margin:0 0 5px}
footer p{margin:0 0 4px}
.foot-note{margin-bottom:12px;padding-bottom:10px;border-bottom:1px solid var(--rule)}
.conf-sint{margin:0 0 10px;color:var(--slate)}
.cmp-wrap{overflow-x:auto}
table.cmp{width:100%;border-collapse:collapse;font-size:11.5px}
.cmp th,.cmp td{padding:5px 8px;border-bottom:1px solid var(--rule);text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.cmp th:first-child,.cmp td:first-child{text-align:left;padding-left:0;color:var(--slate);font-weight:400;white-space:normal}
.cmp thead th{font:700 10px/1.3 var(--sans);letter-spacing:.07em;text-transform:uppercase;color:var(--ink);border-bottom:2px solid var(--ink)}
.cmp td.sel,.cmp th.sel{background:#f1f5f9;font-weight:700;color:var(--ink)}
.cmp td.best{color:var(--pos);font-weight:700}
.cmp td.worst{color:var(--neg);font-weight:700}
.cmp td.v-fav{color:var(--pos);font-weight:600}
.cmp td.v-con{color:var(--neg);font-weight:600}
.cmp td.v-lin{color:var(--slate)}
.cmp tr:last-child td{border-bottom:0}
.conf-cols{margin-top:16px}
@page{size:A4;margin:11mm}
@media print{body{background:#fff;padding:0}.page{border:0;max-width:none;padding:0}section,footer{break-inside:avoid}}
@media (max-width:640px){.cols,.foot{grid-template-columns:1fr}header{flex-direction:column;align-items:flex-start}.data{text-align:left}}
"""


# --- FUNZIONI PER IL GRAFICO STATICO E IL PDF ---

def genera_grafico_statico_png(storico: list, m: dict) -> str:
    """Genera un grafico a candele statico in base64 per il PDF."""
    if not storico or len(storico) < 20:
        return ""

    df = pd.DataFrame(storico)
    df['time'] = pd.to_datetime(df['time'])

    fig, ax = plt.subplots(figsize=(8, 3.2))  # Formato perfetto per A4

    up = df[df.close >= df.open]
    down = df[df.close < df.open]

    # Candele verdi
    col1 = '#2b7a57'
    ax.vlines(up.time, up.low, up.high, color=col1, linewidth=1)
    ax.bar(up.time, up.close - up.open, bottom=up.open, color=col1, width=1.0, align='center')

    # Candele rosse
    col2 = '#a8412f'
    ax.vlines(down.time, down.low, down.high, color=col2, linewidth=1)
    ax.bar(down.time, down.close - down.open, bottom=down.open, color=col2, width=1.0, align='center')

    # Linee target e prezzo
    if m.get('target'):
        ax.axhline(m['target'], color='#94a3b8', linestyle='-', linewidth=1.5, label='Target Medio')
    if m.get('prezzo'):
        ax.axhline(m['prezzo'], color='#17202b', linestyle='-', linewidth=1, label='Prezzo Attuale')

    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['left'].set_color('#d6dbe2')
    ax.spines['bottom'].set_color('#d6dbe2')
    ax.tick_params(colors='#566273', labelsize=8)
    ax.grid(True, linestyle='--', alpha=0.3)
    ax.set_facecolor('#ffffff')
    fig.patch.set_facecolor('#ffffff')
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %y'))

    buf = io.BytesIO()
    plt.tight_layout()
    plt.savefig(buf, format='png', dpi=150)
    plt.close(fig)

    buf.seek(0)
    img_b64 = base64.b64encode(buf.read()).decode('utf-8')
    return f"data:image/png;base64,{img_b64}"


def genera_pdf_da_html(html_content: str) -> bytes:
    """Converte l'HTML in PDF usando Playwright (Chromium invisibile)."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()

        # Carica il codice HTML
        page.set_content(html_content, wait_until="networkidle")

        # Aspetta un attimo per sicurezza (es. per le immagini base64)
        time.sleep(0.5)

        # Genera il PDF (formato A4)
        pdf_bytes = page.pdf(
            format="A4",
            print_background=True,  # Importante: stampa i colori di sfondo!
            margin={"top": "10mm", "bottom": "10mm", "left": "10mm", "right": "10mm"}
        )
        browser.close()
        return pdf_bytes

# -------------------------------------------------------

def genera_report(ticker: str, nome: str, info: dict, m: dict, s: dict, modello: str = "",
                  grafico: str = "", grafico_statico: str = "", adatta_iframe: bool = False,
                  lang: str = None, logo: str = "", confronto: str = "") -> str:
    """Report di una pagina (A4). `s` contiene bull, bear, contabile, macro.
    `grafico` è HTML facoltativo inserito sotto 'Prezzo e target' (solo schermo).
    `grafico_statico` è un'immagine base64 per il PDF.
    `logo` è un URL o data-URI facoltativo; se manca compare un monogramma."""
    _imposta(lang)
    esc = html.escape

    borsa = info.get("fullExchangeName") or info.get("exchange") or ""
    sigla = f"{borsa}: {ticker}" if borsa else ticker
    settore = ", ".join(x for x in (info.get("sector"), info.get("industry")) if x) or _t("settore_nd")

    note_dati = (
        f'<div class="foot-note"><h3>{_t("f_note")}</h3>'
        + "".join(f"<p>{esc(a)}</p>" for a in m["avvisi"])
        + "</div>"
        if m["avvisi"]
        else ""
    )
    modello_txt = _t("f_modello").format(m=esc(modello)) if modello else ""
    iniziali = "".join(w[0] for w in re.findall(r"[A-Za-z0-9]+", nome)[:2]).upper() or ticker[:2]
    marchio = (
        f'<img class="logo" src="{esc(logo, quote=True)}" alt="">' if logo
        else f'<div class="mono">{esc(iniziali)}</div>'
    )

    # Usa il grafico statico se presente (per il PDF), altrimenti quello interattivo.
    # Il grafico RSI settimanale (SVG) viene sempre mostrato sotto.
    blocco_grafico = (
        f'<img src="{grafico_statico}" style="width:100%; height:auto; border:1px solid var(--rule); border-radius:4px; margin-top:10px;" alt="Grafico">'
        + grafico
        if grafico_statico else grafico
    )

    # Solo per la vista a schermo: la finestra si adatta all'altezza del report.
    script_altezza = (
        "<script>(function(){function a(){try{var f=window.frameElement;"
        "if(f){f.style.height=document.body.offsetHeight+'px';}}catch(e){}}"
        "window.addEventListener('load',a);"
        "if(typeof ResizeObserver!=='undefined'){new ResizeObserver(a).observe(document.body);}a();})();</script>"
        if adatta_iframe
        else ""
    )

    return f"""<!DOCTYPE html>
<html lang="{_t('html_lang')}">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(nome)} ({esc(ticker)}) - {_t('titolo_report')}</title>
<style>{CSS}</style>
</head>
<body>
<div class="page">
<header>
  <div class="brand">
    {marchio}
    <div>
      <h1>{esc(nome)}</h1>
      <div class="sotto">{esc(sigla)}. {esc(settore)}.</div>
    </div>
  </div>
  <div class="data">{_t('report_del').format(d=time.strftime(_t('data_fmt')))}<br>{_t('dati_alle').format(t=time.strftime('%H:%M'))}</div>
</header>

<section>
  <h2>{_t('h_prezzo_target')}</h2>
  {_grafico_prezzo(m)}
</section>

{blocco_grafico}

<section class="cols">
  <div class="tesi bull"><h2>{_t('h_bull')}</h2><div class="testo">{testo_html(s.get('bull'))}</div></div>
  <div class="tesi bear"><h2>{_t('h_bear')}</h2><div class="testo">{testo_html(s.get('bear'))}</div></div>
</section>

<section class="cols">
  <div><h2>{_t('h_qualita')}</h2>{_tabella(righe_qualita(m))}</div>
  <div><h2>{_t('h_valutazione')}</h2>{_tabella(righe_valutazione(m))}</div>
</section>

{confronto}

<section class="cols">
  <div><h2>{_t('h_contabile')}</h2><div class="testo">{testo_html(s.get('contabile'))}</div></div>
  <div><h2>{_t('h_macro')}</h2><div class="testo">{testo_html(s.get('macro'))}</div></div>
</section>

<footer>
  {note_dati}
  <div class="foot">
    <div>
      <h3>{_t('f_fonti')}</h3>
      <p>{_t('f_fonti1')}</p>
      <p>{_t('f_fonti2')}{modello_txt}</p>
    </div>
    <div>
      <h3>{_t('f_avvert')}</h3>
      <p>{_t('f_avvert1')}</p>
      <p>{_t('f_avvert2')}</p>
    </div>
  </div>
</footer>
</div>
{script_altezza}
</body>
</html>
"""


def genera_frammento_report(ticker: str, nome: str, info: dict, m: dict, s: dict, modello: str = "", grafico: str = "", lang: str = None, logo: str = "", confronto: str = "") -> str:
    """Genera solo il frammento HTML del report (senza <html>, <head>, <body>)
    per essere visualizzato in un iframe di Streamlit."""
    _imposta(lang)
    esc = html.escape

    borsa = info.get("fullExchangeName") or info.get("exchange") or ""
    sigla = f"{borsa}: {ticker}" if borsa else ticker
    settore = ", ".join(x for x in (info.get("sector"), info.get("industry")) if x) or _t("settore_nd")

    note_dati = (
        f'<div class="foot-note"><h3>{_t("f_note")}</h3>'
        + "".join(f"<p>{esc(a)}</p>" for a in m["avvisi"])
        + "</div>"
        if m["avvisi"]
        else ""
    )
    modello_txt = _t("f_modello").format(m=esc(modello)) if modello else ""
    iniziali = "".join(w[0] for w in re.findall(r"[A-Za-z0-9]+", nome)[:2]).upper() or ticker[:2]
    marchio = (
        f'<img class="logo" src="{esc(logo, quote=True)}" alt="">' if logo
        else f'<div class="mono">{esc(iniziali)}</div>'
    )

    # Il CSS è incluso nel frammento per non dipendere da quello di Streamlit
    return f"""
<style>{CSS}</style>
<div class="page">
<header>
  <div class="brand">
    {marchio}
    <div>
      <h1>{esc(nome)}</h1>
      <div class="sotto">{esc(sigla)}. {esc(settore)}.</div>
    </div>
  </div>
  <div class="data">{_t('report_del').format(d=time.strftime(_t('data_fmt')))}<br>{_t('dati_alle').format(t=time.strftime('%H:%M'))}</div>
</header>

<section>
  <h2>{_t('h_prezzo_target')}</h2>
  {_grafico_prezzo(m)}
</section>

{grafico}

<section class="cols">
  <div class="tesi bull"><h2>{_t('h_bull')}</h2><div class="testo">{testo_html(s.get('bull'))}</div></div>
  <div class="tesi bear"><h2>{_t('h_bear')}</h2><div class="testo">{testo_html(s.get('bear'))}</div></div>
</section>

<section class="cols">
  <div><h2>{_t('h_qualita')}</h2>{_tabella(righe_qualita(m))}</div>
  <div><h2>{_t('h_valutazione')}</h2>{_tabella(righe_valutazione(m))}</div>
</section>

{confronto}

<section class="cols">
  <div><h2>{_t('h_contabile')}</h2><div class="testo">{testo_html(s.get('contabile'))}</div></div>
  <div><h2>{_t('h_macro')}</h2><div class="testo">{testo_html(s.get('macro'))}</div></div>
</section>

<footer>
  {note_dati}
  <div class="foot">
    <div>
      <h3>{_t('f_fonti')}</h3>
      <p>{_t('f_fonti1')}</p>
      <p>{_t('f_fonti2')}{modello_txt}</p>
    </div>
    <div>
      <h3>{_t('f_avvert')}</h3>
      <p>{_t('f_avvert1')}</p>
      <p>{_t('f_avvert2')}</p>
    </div>
  </div>
</footer>
</div>
"""


if __name__ == "__main__":
    # Anteprima del layout con dati di fantasia (azienda inventata).
    info = {
        "sector": "Financial Services", "industry": "Credit Services",
        "fullExchangeName": "NYSE", "currency": "USD", "financialCurrency": "USD",
    }
    dati = {
        "currentPrice": 240.0, "targetMeanPrice": 262.0, "targetLowPrice": 205.0, "targetHighPrice": 300.0,
        "numberOfAnalystOpinions": 34, "marketCap": 480e9, "enterpriseValue": 487e9,
        "freeCashflow": 14.2e9, "totalCash": 11.3e9, "totalDebt": 20.1e9,
        "forwardPE": 26.4, "trailingPE": 29.8, "enterpriseToEbitda": 21.5,
        "profitMargins": 0.47, "operatingMargins": 0.66, "returnOnEquity": 0.55, "revenueGrowth": 0.09,
        "fiftyTwoWeekLow": 198.0, "fiftyTwoWeekHigh": 251.0, "beta": 0.95,
    }
    info.update(dati)
    m = calcola_metriche(info)
    sintesi = {
        "bull": "- **Crescita dei volumi**: i ricavi crescono del 9% su base annua con margine operativo del 66%.\n"
                "- **Posizione di mercato**: la rete esistente rende costoso per i concorrenti entrare nel settore.",
        "bear": "- **Valutazione**: P/E atteso di 26,4x e rendimento da FCF di circa 3%, poco spazio per delusioni.\n"
                "- **Regolamentazione**: limiti alle commissioni possono comprimere i margini.",
        "contabile": "- Il free cash flow di 14,2 mld copre il debito netto in meno di un anno.\n"
                     "- Margine netto del 47% e ROE del 55%: redditività elevata e coerente tra le voci.",
        "macro": "- Il modello vive di volumi di pagamento: consumi e commercio internazionale contano più dei tassi.\n"
                 "- Le norme sulle commissioni e i sistemi di pagamento alternativi sono il fattore di settore più rilevante.",
    }
    with open("anteprima_esempio.html", "w", encoding="utf-8") as f:
        f.write(genera_report("EXMP", "Azienda Esempio Inc.", info, m, sintesi, "modello-di-esempio"))
    print("Creato anteprima_esempio.html")
