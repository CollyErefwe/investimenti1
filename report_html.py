"""Metriche e report HTML per il comitato di ricerca azionaria.

Il modulo non dipende da Streamlit né dal modello linguistico: si può
provare da solo con `python report_html.py`, che crea `anteprima_esempio.html`
con dati di fantasia.
"""
from __future__ import annotations

import html
import re
import time

ND = "N/D"


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
    """Formato italiano: 1.234,56."""
    s = f"{x:,.{dec}f}"
    return s.replace(",", "§").replace(".", ",").replace("§", ".")


def fmt_prezzo(v, valuta):
    x = _num(v)
    return ND if x is None else f"{_it(x)} {valuta}"


def fmt_pct(v, dec=1, segno=False):
    x = _num(v)
    if x is None:
        return ND
    s = _it(x * 100, dec)
    return ("+" + s if segno and x > 0 else s) + "%"


def fmt_x(v, dec=1):
    x = _num(v)
    return ND if x is None else f"{_it(x, dec)}x"


def fmt_grande(v, valuta):
    x = _num(v)
    if x is None:
        return ND
    if abs(x) >= 1e9:
        n, unita = x / 1e9, "mld"
    elif abs(x) >= 1e6:
        n, unita = x / 1e6, "mln"
    else:
        return f"{_it(x, 0)} {valuta}"
    return f"{_it(n, 1 if abs(n) < 100 else 0)} {unita} {valuta}"


# ---------------------------------------------------------------- metriche

def calcola_metriche(info: dict) -> dict:
    """Ricava dai dati grezzi di Yahoo Finance i rapporti che NON devono
    essere calcolati dal modello linguistico."""
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
        avvisi.append("Prezzo non disponibile.")
    if fcf is None:
        avvisi.append("Free cash flow non disponibile: i rapporti che lo usano non sono calcolati.")
    if not stessa_valuta:
        avvisi.append(
            f"Il prezzo è in {valuta} e il bilancio in {valuta_bilancio}: "
            "rendimento e multiplo sul free cash flow non sono calcolati."
        )

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
        return ND
    if dn <= 0:
        return "Cassa netta"
    if m["fcf"] is not None and m["fcf"] <= 0:
        return "FCF non positivo"
    if m["debito_netto_su_fcf"] is None:
        return ND
    return f"{_it(m['debito_netto_su_fcf'], 1)} anni di FCF"


def righe_qualita(m):
    vb = m["valuta_bilancio"]
    return [
        ("Margine netto", fmt_pct(m["margine_netto"])),
        ("Margine operativo", fmt_pct(m["margine_op"])),
        ("ROE", fmt_pct(m["roe"])),
        ("Crescita ricavi (trimestre su anno)", fmt_pct(m["crescita_ricavi"], segno=True)),
        ("Free cash flow", fmt_grande(m["fcf"], vb)),
        ("Cassa", fmt_grande(m["cassa"], vb)),
        ("Debito totale", fmt_grande(m["debito"], vb)),
        ("Debito netto", fmt_grande(m["debito_netto"], vb)),
        ("Debito netto rispetto al FCF", _ratio_debito(m)),
    ]


def righe_valutazione(m):
    v = m["valuta"]
    return [
        ("Capitalizzazione", fmt_grande(m["mcap"], v)),
        ("Valore d'impresa (EV)", fmt_grande(m["ev"], v)),
        ("P/E atteso (forward)", fmt_x(m["pe_fwd"])),
        ("P/E storico (trailing)", fmt_x(m["pe_trail"])),
        ("EV / EBITDA", fmt_x(m["ev_ebitda"])),
        ("Prezzo / free cash flow", fmt_x(m["p_fcf"])),
        ("Rendimento da free cash flow", fmt_pct(m["fcf_yield"])),
        ("Potenziale rispetto al target medio", fmt_pct(m["upside"], segno=True)),
    ]


def tabella_metriche(m):
    """Elenco (voce, valore) mostrato nella scheda 'Dati usati'."""
    righe = righe_valutazione(m) + righe_qualita(m)
    righe.append(("Prezzo", fmt_prezzo(m["prezzo"], m["valuta"])))
    righe.append(("Minimo / massimo 52 settimane",
                  f"{fmt_prezzo(m['min52'], m['valuta'])} / {fmt_prezzo(m['max52'], m['valuta'])}"))
    righe.append(("Target minimo / medio / massimo",
                  " / ".join(fmt_prezzo(m[k], m["valuta"]) for k in ("target_min", "target", "target_max"))))
    return righe


# ------------------------------------------------------- testo per gli agenti

def _raw(x, dec=2, pct=False):
    if x is None:
        return ND
    return f"{x * 100:.{dec}f}%" if pct else f"{x:.{dec}f}"


def _mld(x):
    return ND if x is None else f"{x / 1e9:.2f} mld"


def dati_per_agenti(nome: str, ticker: str, info: dict, m: dict) -> str:
    """Scheda dati consegnata a tutti gli analisti. I rapporti sono già
    calcolati: gli agenti non devono rifarli."""
    v, vb = m["valuta"], m["valuta_bilancio"]
    righe = [
        f"Azienda: {nome} ({ticker})",
        f"Settore: {info.get('sector') or ND} | Industria: {info.get('industry') or ND}",
        f"Prezzo: {_raw(m['prezzo'])} {v} | Capitalizzazione: {_mld(m['mcap'])} {v}",
        f"Intervallo 52 settimane: {_raw(m['min52'])} - {_raw(m['max52'])} {v}",
        f"Target analisti (min / medio / max): {_raw(m['target_min'])} / {_raw(m['target'])} / {_raw(m['target_max'])} {v}"
        f" | Potenziale sul target medio: {_raw(m['upside'], 1, pct=True)}",
        f"P/E forward: {_raw(m['pe_fwd'], 1)} | P/E trailing: {_raw(m['pe_trail'], 1)} | EV/EBITDA: {_raw(m['ev_ebitda'], 1)}",
        f"Prezzo/FCF: {_raw(m['p_fcf'], 1)} | Rendimento da FCF: {_raw(m['fcf_yield'], 1, pct=True)}",
        f"Margine netto: {_raw(m['margine_netto'], 1, pct=True)} | Margine operativo: {_raw(m['margine_op'], 1, pct=True)}"
        f" | ROE: {_raw(m['roe'], 1, pct=True)}",
        f"Crescita ricavi (trimestre su anno): {_raw(m['crescita_ricavi'], 1, pct=True)}",
        f"Free cash flow: {_mld(m['fcf'])} {vb} | Cassa: {_mld(m['cassa'])} {vb} | Debito totale: {_mld(m['debito'])} {vb}",
        f"Debito netto: {_mld(m['debito_netto'])} {vb} | Debito netto / FCF (anni): {_raw(m['debito_netto_su_fcf'], 2)}",
    ]
    if m["avvisi"]:
        righe.append("Avvisi sui dati: " + " ".join(m["avvisi"]))
    righe.append("I rapporti sono già calcolati dal sistema: non rifare i calcoli.")
    return "\n".join(righe)


# --------------------------------------------------------------------- HTML

def testo_html(testo) -> str:
    """Testo del modello -> HTML sicuro (escape, elenchi puntati, grassetto)."""
    if not testo:
        return '<p class="nd">Dato non disponibile.</p>'
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
        classe = ' class="nd"' if valore == ND else ""
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
        return '<p class="nd">Intervalli di prezzo non disponibili.</p>'
    v = m["valuta"]
    righe = []
    if m["min52"] is not None and m["max52"] is not None:
        a, b = pos(m["min52"]), pos(m["max52"])
        righe.append(
            '<div class="lrow"><div class="ll"><span>Ultime 52 settimane</span>'
            f'<span class="num">{_it(m["min52"])} &ndash; {_it(m["max52"])}</span></div>'
            f'<div class="track"><div class="fill" style="left:{a:.1f}%;width:{b - a:.1f}%"></div></div></div>'
        )
    if m["target_min"] is not None and m["target_max"] is not None:
        a, b = pos(m["target_min"]), pos(m["target_max"])
        tick = f'<div class="tick" style="left:{pos(m["target"]):.1f}%"></div>' if m["target"] is not None else ""
        righe.append(
            '<div class="lrow"><div class="ll"><span>Target degli analisti</span>'
            f'<span class="num">{_it(m["target_min"])} &ndash; {_it(m["target_max"])}</span></div>'
            f'<div class="track"><div class="fill t" style="left:{a:.1f}%;width:{b - a:.1f}%"></div>{tick}</div></div>'
        )
    linea = (
        f'<div class="priceline" style="left:{pos(m["prezzo"]):.1f}%"><span>{_it(m["prezzo"])}</span></div>'
    )
    n = m["n_analisti"]
    dettaglio_target = ""
    if m["target"] is not None:
        quanti = f", {int(n)} analisti" if n else ""
        dettaglio_target = (
            f" Il segno scuro è il target medio ({fmt_prezzo(m['target'], v)}"
            f"{', ' + fmt_pct(m['upside'], segno=True) + ' sul prezzo' if m['upside'] is not None else ''}{quanti})."
        )
    nota = f'<p class="nota">Valori in {html.escape(v)}. La linea verticale è il prezzo attuale.{html.escape(dettaglio_target)}</p>'
    return f'<div class="ladder"><div class="axis">{linea}{"".join(righe)}</div>{nota}</div>'


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
footer{margin-top:22px;border-top:1px solid var(--rule);padding-top:10px;color:var(--slate);font-size:10.5px;line-height:1.5}
footer p{margin:0 0 4px}
@page{size:A4;margin:11mm}
@media print{body{background:#fff;padding:0}.page{border:0;max-width:none;padding:0}section{break-inside:avoid}}
@media (max-width:640px){.cols{grid-template-columns:1fr}header{flex-direction:column;align-items:flex-start}.data{text-align:left}}
"""


def genera_report(ticker: str, nome: str, info: dict, m: dict, s: dict, modello: str = "") -> str:
    """Report di una pagina (A4). `s` contiene bull, bear, contabile, macro."""
    esc = html.escape

    borsa = info.get("fullExchangeName") or info.get("exchange") or ""
    sigla = f"{borsa}: {ticker}" if borsa else ticker
    settore = ", ".join(x for x in (info.get("sector"), info.get("industry")) if x) or "Settore non disponibile"

    avvisi = "".join(f"<p>{esc(a)}</p>" for a in m["avvisi"])
    modello_txt = f" Modello linguistico: {esc(modello)}." if modello else ""

    return f"""<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(nome)} ({esc(ticker)}) - Report del comitato</title>
<style>{CSS}</style>
</head>
<body>
<div class="page">
<header>
  <div>
    <h1>{esc(nome)}</h1>
    <div class="sotto">{esc(sigla)}. {esc(settore)}.</div>
  </div>
  <div class="data">Report del {time.strftime('%d/%m/%Y')}<br>Dati aggiornati alle {time.strftime('%H:%M')}</div>
</header>

<section>
  <h2>Prezzo e target</h2>
  {_grafico_prezzo(m)}
</section>

<section class="cols">
  <div class="tesi bull"><h2>Tesi rialzista</h2><div class="testo">{testo_html(s.get('bull'))}</div></div>
  <div class="tesi bear"><h2>Tesi ribassista</h2><div class="testo">{testo_html(s.get('bear'))}</div></div>
</section>

<section class="cols">
  <div><h2>Qualità e solidità</h2>{_tabella(righe_qualita(m))}</div>
  <div><h2>Valutazione</h2>{_tabella(righe_valutazione(m))}</div>
</section>

<section class="cols">
  <div><h2>Analisi contabile</h2><div class="testo">{testo_html(s.get('contabile'))}</div></div>
  <div><h2>Contesto macro e di settore</h2><div class="testo">{testo_html(s.get('macro'))}</div></div>
</section>

<footer>
  {avvisi}
  <p>Dati di mercato e di bilancio da Yahoo Finance tramite yfinance, fonte non ufficiale. Le sezioni di analisi sono scritte da modelli linguistici che lavorano in modo indipendente e possono contenere errori.{modello_txt}</p>
  <p>Documento di analisi generale. Non è consulenza in materia di investimenti né una raccomandazione personalizzata. Verifica le cifre sui documenti ufficiali della società prima di decidere.</p>
</footer>
</div>
</body>
</html>
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
