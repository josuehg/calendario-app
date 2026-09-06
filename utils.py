"""
Utilidades compartidas: fechas, formato de moneda, control de acceso simple,
y la lógica que convierte facturas + letras en "eventos de pago" para el
calendario y el presupuesto.
"""
import calendar as _cal
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

import pandas as pd
import streamlit as st
import db

TERM_OPTIONS = [30, 45, 60, 75, 90]
WEEKS_AHEAD = 13
MONTHS_ES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
    "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]


# ---------- acceso ----------

def authenticate():
    """
    Pide un PIN de acceso y detiene la app hasta que sea válido.
    - Si coincide con el PIN de administrador (APP_PASSWORD en secrets): acceso total.
    - Si coincide con el PIN de alguna sucursal (tabla branches): acceso limitado
      a esa sucursal, ya identificada — no hace falta elegirla en un menú.
    Devuelve {"role": "admin" | "branch", "branch": str | None}.
    """
    if st.session_state.get("auth_role"):
        return {"role": st.session_state["auth_role"], "branch": st.session_state.get("auth_branch")}

    admin_pin = st.secrets.get("APP_PASSWORD")

    st.title("🗓️ Calendario Maestro de Pagos")
    st.caption("Ingresa tu PIN de acceso.")
    with st.form("login_form"):
        pin = st.text_input("PIN", type="password")
        submitted = st.form_submit_button("Entrar", type="primary")

    if submitted:
        if admin_pin and pin == admin_pin:
            st.session_state["auth_role"] = "admin"
            st.session_state["auth_branch"] = None
            st.rerun()
        branch = db.find_branch_by_pin(pin)
        if branch:
            st.session_state["auth_role"] = "branch"
            st.session_state["auth_branch"] = branch
            st.rerun()
        st.error("PIN incorrecto.")
    st.stop()


def current_actor():
    """Quién está usando la app ahora, para los campos de auditoría:
    el nombre de la sucursal, o 'Administrador'."""
    if st.session_state.get("auth_role") == "branch":
        return st.session_state.get("auth_branch") or "Sucursal"
    return "Administrador"


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


def round2(n):
    """Redondea a 2 decimales con half-up (como contabilidad), evitando la
    deriva binaria de float. Devuelve float para que el resto del código y la
    serialización a JSON/Supabase no cambien."""
    return float(Decimal(str(n or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def dsum(values):
    """Suma montos en Decimal y devuelve un float ya redondeado a 2 decimales.
    Úsalo para totales que se comparan o se muestran."""
    total = sum((Decimal(str(v or 0)) for v in values), Decimal("0"))
    return float(total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def money(n):
    return "S/ " + f"{round2(n):,.2f}"


# ---------- eventos de pago (calendario / presupuesto) ----------

def get_payment_events(invoices, letras, canje_facturas, track_contado=True, expenses=None):
    """
    Devuelve una lista de eventos de pago futuros/pendientes:
    - una factura 'pendiente' (no canjeada) aporta un evento en su due_date.
    - cada letra 'pendiente' de un canje aporta un evento en su fecha_vencimiento,
      representando a TODAS las facturas agrupadas en ese canje.
    - si se pasa 'expenses', cada gasto 'pendiente' aporta un evento en su
      due_date (los 'pagado' y 'omitido' no).
    Las facturas 'pagada' o 'canjeada' no generan evento por sí mismas.
    Si track_contado es False, las facturas al contado se excluyen (siguen
    registradas y visibles en Consolidado, solo no aparecen en estas vistas).
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
        if not track_contado and inv["doc_type"] == "contado":
            continue
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

    for x in (expenses or []):
        if x.get("status") != "pendiente":
            continue
        events.append({
            "date": x["due_date"],
            "amount": float(x["amount"]),
            "vendor": x["name"],
            "branch": x.get("branch") or "General",
            "invoice_number": "",
            "label": f"Gasto {x['kind']} · {x['category']}",
            "overdue": x["due_date"] < today,
            "kind": "expense",
            "ref_id": x["id"],
        })

    events.sort(key=lambda e: e["date"])
    return events


# ---------- generación de gastos fijos recurrentes ----------

def due_day_for_month(year, month, pay_day):
    """El día de pago, recortado al último día del mes (pay_day 31 en febrero
    -> 28 o 29)."""
    return min(int(pay_day), _cal.monthrange(year, month)[1])


def fixed_expense_rows_to_create(active_fixed, existing_expenses, today, months_ahead=3):
    """Filas de 'expenses' que faltan para cada gasto fijo activo, desde el mes
    de 'today' hasta months_ahead meses adelante. Pura (sin BD) para poder
    testearla; db.ensure_expense_instances la usa y luego inserta."""
    existing = {
        (e["fixed_expense_id"], e["period"])
        for e in existing_expenses
        if e.get("fixed_expense_id")
    }
    rows = []
    for f in active_fixed:
        start = date.fromisoformat(f["start_month"]).replace(day=1) if f.get("start_month") else None
        end = date.fromisoformat(f["end_month"]).replace(day=1) if f.get("end_month") else None
        for k in range(months_ahead + 1):
            y = today.year + (today.month - 1 + k) // 12
            mo = (today.month - 1 + k) % 12 + 1
            first = date(y, mo, 1)
            if start and first < start:
                continue
            if end and first > end:
                continue
            period = f"{y:04d}-{mo:02d}"
            if (f["id"], period) in existing:
                continue
            day = due_day_for_month(y, mo, f["pay_day"])
            rows.append({
                "kind": "fijo",
                "fixed_expense_id": f["id"],
                "period": period,
                "name": f["name"],
                "category": f["category"],
                "branch": f.get("branch"),
                "amount": f["amount"],
                "due_date": date(y, mo, day).isoformat(),
                "status": "pendiente",
                "registered_by": "Gasto fijo (automático)",
                "notes": f.get("notes"),
            })
    return rows


def compute_stats(events):
    today = today_str()
    week_end = add_days(today, 6)
    return {
        "total_pendiente": dsum(e["amount"] for e in events),
        "hoy": dsum(e["amount"] for e in events if e["date"] == today),
        "esta_semana": dsum(e["amount"] for e in events if today <= e["date"] <= week_end),
        "vencido": dsum(e["amount"] for e in events if e["date"] < today),
    }


def weekly_buckets(events, weeks_ahead=WEEKS_AHEAD):
    today = today_str()
    ws0 = start_of_week(today)
    buckets = []
    for i in range(weeks_ahead):
        ws = add_days(ws0, i * 7)
        we = add_days(ws, 6)
        buckets.append({"start": ws, "end": we, "amount": 0.0, "count": 0, "_items": []})
    for e in events:
        for b in buckets:
            if b["start"] <= e["date"] <= b["end"]:
                b["_items"].append(e["amount"])
                b["count"] += 1
                break
    for b in buckets:
        b["amount"] = dsum(b.pop("_items"))
    return buckets


def events_dataframe(events):
    if not events:
        return pd.DataFrame(columns=["date", "amount", "vendor", "branch", "invoice_number", "label", "overdue"])
    return pd.DataFrame(events)
