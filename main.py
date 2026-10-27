import html
import os
import re
import time

import requests
import yfinance as yf

# ------------------------------------------------------------------
# CONFIGURAZIONE API GEMINI (Google AI Studio, piano gratuito)
# La chiave NON sta nel codice: va impostata come GEMINI_API_KEY
# (in locale: .streamlit/secrets.toml oppure variabile d'ambiente;
# su Streamlit Cloud: nei Secrets, app.py la copia in os.environ).
# Il modello si può cambiare senza toccare il codice con GEMINI_MODEL.
# ------------------------------------------------------------------
MODELLO = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")
# Modello di riserva se il principale va in limite, sovraccarico o timeout.
# Vuoto = nessuna riserva.
MODELLO_RISERVA = os.environ.get("GEMINI_MODEL_RISERVA", "gemini-3.8-flash")

URL_API = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"


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

    tentativi = 5
    ultimo_errore = ""
    modello = MODELLO
    # Nei modelli Gemini 2.5 i token di ragionamento contano nel limite di
    # uscita: lasciamo più spazio di max_t, altrimenti la risposta resta vuota.
    max_uscita = max(max_t * 2, 1800)
    con_ragionamento = True

    for tentativo in range(tentativi):
        try:
            corpo = {
                "model": modello,
                "messages": [
                    {"role": "system", "content": sistema},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.6,
                "max_tokens": max_uscita,
            }
            if con_ragionamento:
                corpo["reasoning_effort"] = "low"

            r = requests.post(
                URL_API,
                headers={"Authorization": f"Bearer {_chiave()}", "Content-Type": "application/json"},
                json=corpo,
                timeout=60,
            )

            if r.status_code != 200:
                ultimo_errore = f"HTTP {r.status_code}: {r.text[:300]}"
                if r.status_code == 429:
                    attesa = _attesa_da_errore(r.text.lower(), tentativo)
                    print(f"[!] Limite raggiunto, attesa di {attesa:.0f} secondi... (tentativo {tentativo + 1}/{tentativi})")
                    print(f"    [dettaglio] {ultimo_errore}")
                    if "per day" in r.text.lower() or "perday" in r.text.lower():
                        print("[!] Limite GIORNALIERO raggiunto: inutile riprovare.")
                        break
                    if MODELLO_RISERVA and tentativo >= 1 and modello != MODELLO_RISERVA:
                        modello = MODELLO_RISERVA
                        print(f"[i] Passo al modello di riserva: {MODELLO_RISERVA}")
                    time.sleep(attesa)
                elif r.status_code in (500, 502, 503, 504):
                    # Sovraccarico temporaneo lato Google: attesa crescente e,
                    # se impostato, passaggio al modello di riserva.
                    attesa = min(8 * (tentativo + 1), 40)
                    print(f"[!] Servizio momentaneamente sovraccarico ({r.status_code}), attesa di {attesa} secondi... (tentativo {tentativo + 1}/{tentativi})")
                    if MODELLO_RISERVA and tentativo >= 1 and modello != MODELLO_RISERVA:
                        modello = MODELLO_RISERVA
                        print(f"[i] Passo al modello di riserva: {MODELLO_RISERVA}")
                    time.sleep(attesa)
                elif r.status_code == 400 and con_ragionamento and "reasoning" in r.text.lower():
                    con_ragionamento = False  # il modello non supporta reasoning_effort
                    print("[i] Modello senza reasoning_effort: riprovo senza.")
                else:
                    print(f"[!] Errore API: {ultimo_errore}")
                    if r.status_code in (401, 403):
                        break  # chiave non valida o non autorizzata: inutile riprovare
                    time.sleep(3)
                continue

            testo = (r.json()["choices"][0]["message"].get("content") or "").strip()
            if "</think>" in testo:
                testo = testo.split("</think>")[-1].strip()

            if testo:
                print(f"    [OK] Risposta completata ({len(testo)} caratteri)")
                return testo

            ultimo_errore = "risposta vuota (token esauriti dal ragionamento?)"
            print(f"[!] {ultimo_errore}; riprovo con più spazio (tentativo {tentativo + 1}/{tentativi})")
            max_uscita = int(max_uscita * 1.5)
            time.sleep(2)

        except Exception as e:
            ultimo_errore = str(e)
            print(f"[!] Errore: {e}")
            # Timeout o problemi di rete: dal secondo tentativo prova il modello di riserva.
            if MODELLO_RISERVA and tentativo >= 1 and modello != MODELLO_RISERVA:
                modello = MODELLO_RISERVA
                print(f"[i] Passo al modello di riserva: {MODELLO_RISERVA}")
            time.sleep(3)

    # Mostra anche l'errore vero, così non resta nascosto.
    return f"{errore_api} (dettaglio: {ultimo_errore[:200]})"


def genera_scheda_html(
    ticker: str, nome_az: str, dati: dict, sintesi: dict, file_html: str
):
    def format_val(val, suffix="", is_pct=False, is_curr=False):
        if val is None or val == "N/D":
            return "N/D"
        try:
            num = float(val)
            if is_pct:
                return f"{num * 100:.1f}%"
            if is_curr:
                if abs(num) >= 1e9:
                    return f"${num / 1e9:.2f} B"
                if abs(num) >= 1e6:
                    return f"${num / 1e6:.2f} M"
                return f"${num:,.2f}"
            return f"{num:.2f}{suffix}"
        except Exception:
            return str(val)

    def format_text(testo: str) -> str:
        if not testo:
            return "Dato non disponibile."
        testo_pulito = html.escape(str(testo))
        testo_pulito = re.sub(r"\*\*(.*?)\*\*", r"<strong>\1</strong>", testo_pulito)
        return testo_pulito.replace("\n", "<br>")

    html_content = f"""<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="UTF-8">
<title>Equity Research One-Pager - {ticker}</title>
<style>
    @page {{
        size: A4 portrait;
        margin: 10mm 12mm;
    }}
    * {{
        box-sizing: border-box;
        -webkit-print-color-adjust: exact !important;
        print-color-adjust: exact !important;
    }}
    body {{
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
        color: #1e293b;
        background-color: #ffffff;
        margin: 0;
        padding: 24px;
        font-size: 12px;
        line-height: 1.5;
    }}
    .header {{
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        border-bottom: 2px solid #0f172a;
        padding-bottom: 10px;
        margin-bottom: 14px;
    }}
    .title-area h1 {{
        margin: 0;
        font-size: 22px;
        font-weight: 800;
        color: #0f172a;
    }}
    .title-area .sub {{
        font-size: 11px;
        color: #64748b;
        margin-top: 2px;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }}

    .grid-kpi {{
        display: grid;
        grid-template-columns: repeat(6, 1fr);
        gap: 8px;
        margin-bottom: 14px;
    }}
    .kpi-card {{
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 4px;
        padding: 8px;
        text-align: center;
    }}
    .kpi-card .label {{
        font-size: 9.5px;
        color: #64748b;
        font-weight: 700;
        text-transform: uppercase;
    }}
    .kpi-card .val {{
        font-size: 13.5px;
        font-weight: 700;
        color: #0f172a;
        margin-top: 3px;
    }}

    .two-col {{
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 12px;
        margin-bottom: 12px;
    }}
    .box-thesis {{
        border: 1px solid #e2e8f0;
        border-radius: 6px;
        padding: 10px 12px;
        background: #ffffff;
        min-height: 110px;
    }}
    .box-thesis.bull {{
        border-top: 3px solid #16a34a;
    }}
    .box-thesis.bear {{
        border-top: 3px solid #dc2626;
    }}
    .box-thesis h3 {{
        margin: 0 0 8px 0;
        font-size: 11px;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }}
    .box-thesis.bull h3 {{ color: #16a34a; }}
    .box-thesis.bear h3 {{ color: #dc2626; }}

    .text-content {{
        font-size: 11.5px;
        color: #334155;
        line-height: 1.5;
    }}

    .footer {{
        border-top: 1px solid #e2e8f0;
        margin-top: 16px;
        padding-top: 8px;
        font-size: 9.5px;
        color: #94a3b8;
        display: flex;
        justify-content: space-between;
    }}
</style>
</head>
<body>

<div class="header">
    <div class="title-area">
        <h1>{nome_az} ({ticker})</h1>
        <div class="sub">Equity Research Committee Report &bull; Settore: {dati.get('sector', 'N/D')} &bull; Industria: {dati.get('industry', 'N/D')}</div>
    </div>
    <div class="meta-box" style="text-align: right;">
        <div style="font-size: 10px; color: #64748b;">Data: {time.strftime('%d/%m/%Y')}</div>
    </div>
</div>

<div class="grid-kpi">
    <div class="kpi-card">
        <div class="label">Prezzo Attuale</div>
        <div class="val">{format_val(dati.get('currentPrice'), suffix=' USD')}</div>
    </div>
    <div class="kpi-card">
        <div class="label">Target Mean</div>
        <div class="val">{format_val(dati.get('targetMeanPrice'), suffix=' USD')}</div>
    </div>
    <div class="kpi-card">
        <div class="label">P/E Forward</div>
        <div class="val">{format_val(dati.get('forwardPE'))}x</div>
    </div>
    <div class="kpi-card">
        <div class="label">Margine Netto</div>
        <div class="val">{format_val(dati.get('profitMargins'), is_pct=True)}</div>
    </div>
    <div class="kpi-card">
        <div class="label">Free Cash Flow</div>
        <div class="val">{format_val(dati.get('freeCashflow'), is_curr=True)}</div>
    </div>
    <div class="kpi-card">
        <div class="label">Cassa vs Debito</div>
        <div class="val">{format_val(dati.get('totalCash'), is_curr=True)} / {format_val(dati.get('totalDebt'), is_curr=True)}</div>
    </div>
</div>

<div class="two-col">
    <div class="box-thesis bull">
        <h3>&bull; Tesi Rialzista (Bull Catalysts)</h3>
        <div class="text-content">{format_text(sintesi.get('bull'))}</div>
    </div>
    <div class="box-thesis bear">
        <h3>&bull; Tesi Ribassista (Bear Risks)</h3>
        <div class="text-content">{format_text(sintesi.get('bear'))}</div>
    </div>
</div>

<div class="two-col">
    <div class="box-thesis" style="border-top: 3px solid #0284c7;">
        <h3 style="color: #0284c7;">&bull; Analisi Contabile & Bilancio</h3>
        <div class="text-content">{format_text(sintesi.get('contabile'))}</div>
    </div>
    <div class="box-thesis" style="border-top: 3px solid #64748b;">
        <h3 style="color: #475569;">&bull; Inquadramento Macro & Settoriale</h3>
        <div class="text-content">{format_text(sintesi.get('macro'))}</div>
    </div>
</div>

<div class="footer">
    <span>Documento ad uso informativo preparato da Institutional AI Investment Committee.</span>
    <span>Dati di mercato forniti da Yahoo Finance.</span>
</div>

</body>
</html>
"""
    with open(file_html, "w", encoding="utf-8") as f:
        f.write(html_content)


def analizza_azienda(ticker: str):
    print("\n" + "=" * 55)
    print(f" COMITATO DI INVESTIMENTO: ANALISI {ticker}")
    print("=" * 55)

    print(f"[>] Recupero dati finanziari per {ticker}...")
    stock = yf.Ticker(ticker)

    try:
        dati = stock.info
        if not dati or dati.get("longName") is None:
            print(f"[!] Errore: Ticker '{ticker}' non valido o non trovato.\n")
            return None
    except Exception as e:
        print(f"[!] Errore Yahoo Finance: {e}\n")
        return None

    nome_azienda = dati.get("longName", ticker)
    sintesi_dati = (
        f"Azienda: {nome_azienda} ({ticker})\n"
        f"Settore: {dati.get('sector', 'N/D')}\n"
        f"Prezzo: {dati.get('currentPrice', 'N/D')} USD\n"
        f"P/E Forward: {dati.get('forwardPE', 'N/D')} | PEG:"
        f" {dati.get('pegRatio', 'N/D')}\n"
        f"Margine Netto: {dati.get('profitMargins', 'N/D')} | ROE:"
        f" {dati.get('returnOnEquity', 'N/D')}\n"
        f"Free Cash Flow: {dati.get('freeCashflow', 'N/D')} USD\n"
        f"Debito: {dati.get('totalDebt', 'N/D')} USD | Cassa:"
        f" {dati.get('totalCash', 'N/D')} USD\n"
        f"Target Mean Analisti: {dati.get('targetMeanPrice', 'N/D')} USD\n"
    )

    # 1. Agente Contabile
    res_contabile = chiedi_agente(
        ruolo="Analista Contabile Forense",
        compito=(
            "Valuta in 2 punti concisi la solidita di cassa (FCF), debito e"
            " qualita margini."
        ),
        contesto=sintesi_dati,
        max_t=900,
        pausa=6,
    )

    # 2. Agente Bull
    res_bull = chiedi_agente(
        ruolo="Analista Bull",
        compito=(
            "Presenta in 2 punti concisi i fattori di crescita duraturi e il"
            " vantaggio competitivo."
        ),
        contesto=f"{sintesi_dati}\nContabile:\n{res_contabile}",
        max_t=900,
        pausa=6,
    )

    # 3. Agente Bear
    res_bear = chiedi_agente(
        ruolo="Analista Bear",
        compito=(
            "Esposti in 2 punti concisi i principali rischi di valutazione e"
            " concorrenza."
        ),
        contesto=f"{sintesi_dati}\nBull:\n{res_bull}",
        max_t=900,
        pausa=6,
    )

    # 4. Agente Macro
    res_macro = chiedi_agente(
        ruolo="Economista Macro",
        compito=(
            "Inquadra in 2 punti concisi l'impatto del ciclo tassi sul settore"
            f" {dati.get('sector')}."
        ),
        contesto=sintesi_dati,
        max_t=900,
        pausa=6,
    )

    dati_sintesi = {
        "contabile": res_contabile,
        "bull": res_bull,
        "bear": res_bear,
        "macro": res_macro,
    }

    file_md = f"scheda_{ticker}.md"
    with open(file_md, "w", encoding="utf-8") as f:
        f.write(f"# SCHEDA ESECUTIVA: {nome_azienda} ({ticker})\n\n")
        f.write(f"### Contabile\n{dati_sintesi['contabile']}\n\n")
        f.write(f"### Bull\n{dati_sintesi['bull']}\n\n")
        f.write(f"### Bear\n{dati_sintesi['bear']}\n\n")
        f.write(f"### Macro\n{dati_sintesi['macro']}\n")

    file_html = f"scheda_{ticker}.html"
    genera_scheda_html(ticker, nome_azienda, dati, dati_sintesi, file_html)

    print(f"\n[+] File Markdown salvato: {file_md}")
    print(f"[+] Scheda Grafica One-Pager salvata: {file_html}")

    return dati_sintesi


if __name__ == "__main__":
    print("=" * 60)
    print(" COMITATO DI INVESTIMENTO - REPORT GENERATOR ISTITUZIONALE")
    print("=" * 60)

    input_utente = input("\nInserisci un ticker (es. V oppure NVDA, AAPL): ")
    tickers = [t.strip().upper() for t in input_utente.split(",") if t.strip()]

    for idx, t in enumerate(tickers, start=1):
        analizza_azienda(t)
        if idx < len(tickers):
            print("\n[i] Attesa di sicurezza prima del prossimo ticker...")
            time.sleep(15)
