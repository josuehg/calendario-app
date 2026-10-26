"""
Reporte diario de pagos por Telegram, pensado para correr una vez al día
(vía GitHub Actions, ver .github/workflows/telegram_daily_report.yml).

Reusa exactamente la misma lógica que Calendario/Resumen (db.py + utils.py)
para que el reporte nunca se desalinee con lo que se ve en la app: una letra
"vive" en vencimiento + plazo típico de pago, no en su vencimiento contractual.

Requiere, como variables de entorno:
  TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
y, para que db.py pueda hablar con Supabase fuera de `streamlit run`,
un .streamlit/secrets.toml con SUPABASE_URL / SUPABASE_SERVICE_KEY
(el workflow lo genera a partir de GitHub Secrets antes de ejecutar esto).
"""
import os
import pathlib
import sys
import urllib.request
import urllib.parse

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import db
import utils


def build_message(today):
    settings = db.get_settings()
    invoices = db.list_invoices()
    letras = db.list_letras()
    canje_facturas = db.list_canje_facturas()
    expenses = db.list_expenses()
    events = utils.get_payment_events(
        invoices, letras, canje_facturas,
        settings.get("track_contado", True), expenses,
        letra_dias_pago_tipico=settings.get("letra_dias_pago_tipico", 8),
        letra_dias_gracia_max=settings.get("letra_dias_gracia_max", 10),
    )
    hoy = sorted(
        (e for e in events if e["date"] == today),
        key=lambda e: -e["amount"],
    )

    lines = [f"📅 Pagos de hoy, {utils.fmt_long(today)}", ""]
    if not hoy:
        lines.append("No hay pagos programados para hoy. 🎉")
        return "\n".join(lines)

    for e in hoy:
        ref = f" · Fact. {e['invoice_number']}" if e.get("invoice_number") and e["kind"] != "expense" else ""
        lines.append(f"• {e['vendor']}{ref} · {e['label']} · {e['branch']} · {utils.money(e['amount'])}")

    total = utils.dsum(e["amount"] for e in hoy)
    lines.append("")
    lines.append(f"Total del día: {utils.money(total)}")
    return "\n".join(lines)


def send_telegram(text, token, chat_id):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    with urllib.request.urlopen(req, timeout=15) as resp:
        if resp.status != 200:
            raise RuntimeError(f"Telegram respondió {resp.status}: {resp.read()!r}")


def main():
    today = utils.today_lima().isoformat()
    text = build_message(today)
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    send_telegram(text, token, chat_id)
    print(f"Reporte enviado para {today}.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR enviando reporte de Telegram: {exc}", file=sys.stderr)
        sys.exit(1)
