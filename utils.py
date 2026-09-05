"""
Utilidades compartidas: fechas, formato de moneda, control de acceso simple,
y la lógica que convierte facturas + letras en "eventos de pago" para el
calendario y el presupuesto.
"""
from datetime import date, timedelta
import pandas as pd
import streamlit as st

TERM_OPTIONS = [30, 45, 60, 75, 90]
WEEKS_AHEAD = 13
MONTHS_ES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
    "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]


# ---------- acceso ----------

def check_password():
    """Muestra un campo de clave y detiene la app hasta que sea correcta.
    Protege el enlace público de la app con una sola clave compartida."""
    if st.session_state.get("_authed"):
        return True

    configured = st.secrets.get("APP_PASSWORD")
    if not configured:
        return True  # si no se configuró clave, no se bloquea (útil en desarrollo)

    st.title("🗓️ Calendario Maestro de Pagos")
    pwd = st.text_input("Clave de acceso", type="password")
    if pwd:
        if pwd == configured:
            st.session_state["_authed"] = True
            st.rerun()
        else:
            st.error("Clave incorrecta.")
    st.stop()


# ---------- fechas y moneda ----------

def today_str():
    return date.today().isoformat()


def add_days(date_str, n):
    d = date.fromisoformat(date_str)
    return (d + timedelta(days=n)).isoformat()


def fmt_short(date_str):
    if not date_str:
        return "—"
    d = date.fromisoformat(date_str)
    return d.strftime("%d/%m/%y")


def fmt_long(date_str):
    d = date.fromisoformat(date_str)
    return f"{d.day} de {MONTHS_ES[d.month - 1]} {d.year}"


def start_of_week(date_str):
    d = date.fromisoformat(date_str)
    return (d - timedelta(days=d.weekday())).isoformat()


def money(n):
    n = float(n or 0)
    return "S/ " + f"{n:,.2f}"


# ---------- eventos de pago (calendario / presupuesto) ----------

def get_payment_events(invoices, letras, canje_facturas):
    """
    Devuelve una lista de eventos de pago futuros/pendientes:
    - una factura 'pendiente' (no canjeada) aporta un evento en su due_date.
    - cada letra 'pendiente' de un canje aporta un evento en su fecha_vencimiento,
      representando a TODAS las facturas agrupadas en ese canje.
    Las facturas 'pagada' o 'canjeada' no generan evento por sí mismas.
    """
    today = today_str()
    inv_by_id = {i["id"]: i for i in invoices}

    # canje_id -> lista de facturas (vendor/invoice_number/branch) agrupadas
    canje_invoices = {}
    for cf in canje_facturas:
        inv = inv_by_id.get(cf["invoice_id"])
        if inv:
            canje_invoices.setdefault(cf["canje_id"], []).append(inv)

    events = []

    for inv in invoices:
        if inv["status"] == "pendiente":
            events.append({
                "date": inv["due_date"],
                "amount": float(inv["amount"]),
                "vendor": inv["vendor"],
                "branch": inv["branch"],
                "invoice_number": inv["invoice_number"],
                "label": "Contado" if inv["doc_type"] == "contado" else "Factura a crédito",
                "overdue": inv["due_date"] < today,
                "kind": "invoice",
                "ref_id": inv["id"],
            })

    for l in letras:
        if l["estado"] != "pendiente":
            continue
        grouped = canje_invoices.get(l["canje_id"], [])
        vendors = ", ".join(sorted(set(i["vendor"] for i in grouped))) or "—"
        branches = ", ".join(sorted(set(i["branch"] for i in grouped))) or "—"
        facturas = ", ".join(i["invoice_number"] for i in grouped) or "—"
        events.append({
            "date": l["fecha_vencimiento"],
            "amount": float(l["monto"]),
            "vendor": vendors,
            "branch": branches,
            "invoice_number": facturas,
            "label": f"Letra {l.get('numero') or '—'} ({len(grouped)} factura(s))",
            "overdue": l["fecha_vencimiento"] < today,
            "kind": "letra",
            "ref_id": l["id"],
        })

    events.sort(key=lambda e: e["date"])
    return events


def compute_stats(events):
    today = today_str()
    week_end = add_days(today, 6)
    stats = {"total_pendiente": 0.0, "hoy": 0.0, "esta_semana": 0.0, "vencido": 0.0}
    for e in events:
        stats["total_pendiente"] += e["amount"]
        if e["date"] == today:
            stats["hoy"] += e["amount"]
        if today <= e["date"] <= week_end:
            stats["esta_semana"] += e["amount"]
        if e["date"] < today:
            stats["vencido"] += e["amount"]
    return stats


def weekly_buckets(events, weeks_ahead=WEEKS_AHEAD):
    today = today_str()
    ws0 = start_of_week(today)
    buckets = []
    for i in range(weeks_ahead):
        ws = add_days(ws0, i * 7)
        we = add_days(ws, 6)
        buckets.append({"start": ws, "end": we, "amount": 0.0, "count": 0})
    for e in events:
        for b in buckets:
            if b["start"] <= e["date"] <= b["end"]:
                b["amount"] += e["amount"]
                b["count"] += 1
                break
    return buckets


def events_dataframe(events):
    if not events:
        return pd.DataFrame(columns=["date", "amount", "vendor", "branch", "invoice_number", "label", "overdue"])
    return pd.DataFrame(events)
