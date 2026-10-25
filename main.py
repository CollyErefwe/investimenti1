import html
import re
import time
import yfinance as yf
from groq import APIStatusError, Groq

# ------------------------------------------------------------------
# CONFIGURAZIONE API GROQ
# ------------------------------------------------------------------
CHIAVE_GROQ = "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"

client = Groq(api_key=CHIAVE_GROQ)
MODELLO = "openai/gpt-oss-120b"

def chiedi_agente(
    ruolo: str,
    compito: str,
    contesto: str,
    max_t: int = 800,
    pausa: int = 6,
) -> str:
  print(f"[>] Al lavoro: {ruolo}...")
  time.sleep(pausa)

  prompt = (
      f"Ruolo: {ruolo}\n"
      f"Obiettivo: {compito}\n\n"
      f"DATI:\n{contesto}\n\n"
      "VINCOLI TASSATIVI:\n"
      "- Rispondi ESCLUSIVAMENTE in lingua italiana.\n"
      "- Scrivi solo 2 punti elenco preceduti da trattino '- '.\n"
      "- Ogni punto deve essere una singola frase di massimo 18 parole.\n"
      "- Termina OBBLIGATORIAMENTE ogni riga con il punto fermo '.' prima di"
      " fermarti.\n"
      "- Nessun preambolo, nessun commento in inglese."
  )

  tentativi = 3
  for tentativo in range(tentativi):
        try:
            risposta = client.chat.completions.create(
                model=MODELLO,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Sei un equity analyst istituzionale. Rispondi "
                            "esclusivamente in lingua italiana con 2 punti elenco chiari, completi e sintetici."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=1,
                max_completion_tokens=2048,
            )

            testo = risposta.choices[0].message.content
            if testo and testo.strip():
                testo_pulito = testo.strip()

                if "</think>" in testo_pulito:
                    testo_pulito = testo_pulito.split("</think>")[-1].strip()

                print(f"    [OK] Risposta completata ({len(testo_pulito)} caratteri)")
                return testo_pulito

            time.sleep(3)

        except Exception as e:
            err_msg = str(e).lower()
            if "rate_limit" in err_msg or "429" in err_msg:
                print(f"[!] Limite Groq raggiunto, attesa di 15 secondi... (tentativo {tentativo + 1}/{tentativi})")
                time.sleep(15)
            else:
                print(f"[!] Errore API: {e}")
                time.sleep(3)

  return "- Dati al momento non disponibili per sovraccarico API."


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

  verdetto_raw = sintesi.get("verdetto", "BUY").upper()
  badge_class = "badge-hold"
  if "BUY" in verdetto_raw:
    badge_class = "badge-buy"
  elif "SELL" in verdetto_raw:
    badge_class = "badge-sell"

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
    .badge {{
        display: inline-block;
        font-size: 13px;
        font-weight: 800;
        padding: 6px 14px;
        border-radius: 4px;
        text-transform: uppercase;
    }}
    .badge-buy {{
        background-color: #dcfce7;
        color: #166534;
        border: 1px solid #86efac;
    }}
    .badge-hold {{
        background-color: #fef3c7;
        color: #92400e;
        border: 1px solid #fde047;
    }}
    .badge-sell {{
        background-color: #fee2e2;
        color: #991b1b;
        border: 1px solid #fca5a5;
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

    .verdict-box {{
        background: linear-gradient(135deg, #0f172a, #1e293b);
        color: #f8fafc;
        padding: 12px 16px;
        border-radius: 6px;
        margin-bottom: 14px;
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 16px;
    }}
    .verdict-left {{
        flex: 1;
    }}
    .verdict-left .label-v {{
        font-size: 10px;
        color: #94a3b8;
        text-transform: uppercase;
        font-weight: 700;
        letter-spacing: 0.5px;
    }}
    .verdict-left .desc-v {{
        font-size: 12px;
        margin-top: 5px;
        color: #f1f5f9;
        line-height: 1.45;
    }}
    .score-circle {{
        text-align: center;
        background: rgba(255, 255, 255, 0.1);
        border: 1px solid rgba(255, 255, 255, 0.2);
        padding: 8px 16px;
        border-radius: 6px;
        min-width: 90px;
    }}
    .score-circle .score-num {{
        font-size: 24px;
        font-weight: 800;
        color: #38bdf8;
    }}
    .score-circle .score-label {{
        font-size: 9px;
        color: #94a3b8;
        text-transform: uppercase;
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
        <div class="badge {badge_class}">{verdetto_raw}</div>
        <div style="font-size: 10px; color: #64748b; margin-top: 4px;">Data: {time.strftime('%d/%m/%Y')}</div>
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

<div class="verdict-box">
    <div class="verdict-left">
        <div class="label-v">Verdetto Esecutivo del Portfolio Manager</div>
        <div class="desc-v">{format_text(sintesi.get('verdetto_dettaglio'))}</div>
    </div>
    <div class="score-circle">
        <div class="score-num">{sintesi.get('score', '75')}</div>
        <div class="score-label">Score / 100</div>
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

 # 5. Lead Portfolio Manager
  quadro_pm = (
      f"TITOLO: {ticker}\n"
      f"PREZZO: {dati.get('currentPrice')} USD | TARGET:"
      f" {dati.get('targetMeanPrice')} USD\n"
      f"P/E FWD: {dati.get('forwardPE')}\n"
      f"PUNTI CHIAVE:\n"
      f"Bull: {res_bull}\n"
      f"Bear: {res_bear}\n"
  )

  prompt_pm = """
Emetti il verdetto per il cliente. Rispondi con queste 3 righe esatte:
VERDETTO: [STRONG BUY / BUY / HOLD / SELL]
SCORE: [Numero da 1 a 100]
SINTESI: [Spiegazione pratica per il cliente in 2 frasi complete]
"""

  print("\n[i] Sincronizzazione comitato prima del verdetto finale...")
  time.sleep(12)
  prompt_pm_completo = f"DATI:\n{quadro_pm}\n\n{prompt_pm}"
    
  try:
        risp = client.chat.completions.create(
            model=MODELLO,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Sei il Portfolio Manager istituzionale. Rispondi SOLO con questo formato esatto:\n"
                        "VERDETTO: [BUY / STRONG BUY / HOLD / SELL]\n"
                        "SCORE: [un numero intero da 1 a 100]\n"
                        "SINTESI: [2 frasi complete che riassumono il giudizio sul titolo]"
                    ),
                },
                {"role": "user", "content": prompt_pm_completo},
            ],
            temperature=1,
            max_completion_tokens=2048,
        )

        report_pm = risp.choices[0].message.content or ""
        if "</think>" in report_pm:
            report_pm = report_pm.split("</think>")[-1].strip()

        print(f"\n[DEBUG RISPOSTA PM]:\n{report_pm}\n" + "-" * 30)

        # Valori predefiniti di sicurezza
        verdetto_val = "HOLD"
        score_val = "50"
        sintesi_pm = ""

        for line in report_pm.splitlines():
            # Rimuove eventuali asterischi markdown o spazi extra
            line_clean = line.replace("*", "").strip()
            line_upper = line_clean.upper()

            if line_upper.startswith("VERDETTO:"):
                verdetto_val = line_clean.split(":", 1)[1].strip()
            elif line_upper.startswith("SCORE:"):
                score_raw = line_clean.split(":", 1)[1].strip()
                numeri = "".join(c for c in score_raw if c.isdigit())
                score_val = numeri if numeri else "50"
            elif line_upper.startswith("SINTESI:"):
                sintesi_pm = line_clean.split(":", 1)[1].strip()

        # Se la sintesi non è su una riga singola con etichetta, usa l'intero testo restituito
        if not sintesi_pm and len(report_pm) > 10:
            sintesi_pm = report_pm

  except Exception as e:
        print(f"[!] Errore Portfolio Manager: {e}")
        verdetto_val = "Non determinato"
        score_val = "N/D"
        sintesi_pm = "Sintesi non disponibili."
  
  report_pm = risp.choices[0].message.content or ""
  if "</think>" in report_pm:
        report_pm = report_pm.split("</think>")[-1].strip()

  verdetto_val = "BUY"
  score_val = "75"
  sintesi_pm = report_pm

  for line in report_pm.splitlines():
    if "VERDETTO:" in line:
      verdetto_val = line.replace("VERDETTO:", "").strip()
    elif "SCORE:" in line:
      score_val = line.replace("SCORE:", "").strip().replace("/100", "")
    elif "SINTESI:" in line:
      sintesi_pm = line.replace("SINTESI:", "").strip()

  dati_sintesi = {
      "verdetto": verdetto_val,
      "score": score_val,
      "verdetto_dettaglio": sintesi_pm,
      "contabile": res_contabile,
      "bull": res_bull,
      "bear": res_bear,
      "macro": res_macro,
  }

  file_md = f"scheda_{ticker}.md"
  with open(file_md, "w", encoding="utf-8") as f:
    f.write(f"# SCHEDA ESECUTIVA: {nome_azienda} ({ticker})\n\n")
    f.write(f"**Verdetto:** {verdetto_val} | **Score:** {score_val}/100\n\n")
    f.write(f"{sintesi_pm}\n\n---\n")
    f.write(f"### Contabile\n{res_contabile}\n\n")
    f.write(f"### Bull\n{res_bull}\n\n")
    f.write(f"### Bear\n{res_bear}\n\n")
    f.write(f"### Macro\n{res_macro}\n") 

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
