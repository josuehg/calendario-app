"""
Utilidades compartidas: fechas, formato de moneda, control de acceso simple,
y la lógica que convierte facturas + letras en "eventos de pago" para el
calendario y el presupuesto.
"""
import calendar as _cal
import io
import os
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal

_PERU_TZ = timezone(timedelta(hours=-5))  # Perú: UTC-5 fijo, sin horario de verano

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

def secret(name, default=None):
    """Lee un secreto de .streamlit/secrets.toml (Streamlit Cloud) o, si no
    está ahí, de una variable de entorno (Railway)."""
    try:
        if name in st.secrets:
            return st.secrets[name]
    except Exception:
        pass  # sin secrets.toml: st.secrets lanza en vez de devolver vacío
    return os.environ.get(name, default)


def authenticate():
    """
    Pide un PIN de acceso y detiene la app hasta que sea válido.
    - Si coincide con el PIN de administrador (APP_PASSWORD en secrets): acceso total.
    - Si coincide con el PIN de validación (VALIDATOR_PASSWORD en secrets): acceso
      de solo lectura a la pantalla de Validación (uno solo para todas las sucursales).
    - Si coincide con el PIN de alguna sucursal (tabla branches): acceso limitado
      a esa sucursal, ya identificada — no hace falta elegirla en un menú.
    Devuelve {"role": "admin" | "validador" | "branch", "branch": str | None}.
    """
    if st.session_state.get("auth_role"):
        return {"role": st.session_state["auth_role"], "branch": st.session_state.get("auth_branch")}

    admin_pin = secret("APP_PASSWORD")
    validator_pin = secret("VALIDATOR_PASSWORD")

    st.title("🗓️ Control Compras")
    st.caption("Ingresa tu PIN de acceso.")
    with st.form("login_form"):
        pin = st.text_input("PIN", type="password")
        submitted = st.form_submit_button("Entrar", type="primary")

    if submitted:
        if admin_pin and pin == admin_pin:
            st.session_state["auth_role"] = "admin"
            st.session_state["auth_branch"] = None
            st.rerun()
        if validator_pin and pin == validator_pin:
            st.session_state["auth_role"] = "validador"
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
    el nombre de la sucursal, 'Validador' o 'Administrador'."""
    role = st.session_state.get("auth_role")
    if role == "branch":
        return st.session_state.get("auth_branch") or "Sucursal"
    if role == "validador":
        return "Validador"
    return "Administrador"


# ---------- fechas y moneda ----------

def today_str():
    return date.today().isoformat()


def add_days(date_str, n):
    d = date.fromisoformat(date_str)
    return (d + timedelta(days=n)).isoformat()


def days_late(reference_date, today):
    """Días de atraso respecto a una fecha ya vencida; 0 si aún no pasó."""
    return max((date.fromisoformat(today) - date.fromisoformat(reference_date)).days, 0)


def fmt_atraso(days):
    return f"{days} día{'s' if days != 1 else ''} de atraso"


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


def df_to_xlsx_bytes(df, sheet_name="Hoja1"):
    """Serializa un DataFrame a bytes de un .xlsx, para botones de descarga."""
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name)
    return buf.getvalue()


def dict_list_to_xlsx_bytes(sheets: dict):
    """sheets: {nombre_hoja: lista_de_dicts}. Cada entrada se vuelve una
    pestaña de un mismo .xlsx — para un backup completo en un solo archivo."""
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        for name, rows in sheets.items():
            df = pd.DataFrame(rows) if rows else pd.DataFrame()
            df.to_excel(writer, index=False, sheet_name=name[:31])
    return buf.getvalue()


def fmt_time(ts):
    """'HH:MM' en hora de Perú de un timestamp ISO. Supabase guarda en UTC;
    si el valor viene sin zona horaria se asume UTC."""
    if not ts:
        return "—"
    try:
        dt = datetime.fromisoformat(ts)
    except (ValueError, TypeError):
        return "—"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(_PERU_TZ).strftime("%H:%M")


def today_lima():
    """La fecha de 'hoy' en hora de Perú, sin importar en qué zona horaria
    corra el servidor (Streamlit Cloud corre en UTC). Úsala en vez de
    date.today() para cualquier '¿esto fue hoy?' pensado para el usuario
    — si no, el corte de 'hoy' cae a medianoche UTC (7pm en Perú), no a
    medianoche real."""
    return datetime.now(timezone.utc).astimezone(_PERU_TZ).date()


def to_lima_date_str(ts):
    """La fecha 'YYYY-MM-DD' en hora de Perú de un timestamp ISO (si viene
    sin zona horaria, como puede pasar, se asume UTC — igual que fmt_time)."""
    if not ts:
        return ""
    try:
        dt = datetime.fromisoformat(ts)
    except (ValueError, TypeError):
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(_PERU_TZ).date().isoformat()


# ---------- eventos de pago (calendario / presupuesto) ----------

def get_payment_events(
    invoices, letras, canje_facturas, track_contado=True, expenses=None,
    letra_dias_pago_tipico=8, letra_dias_gracia_max=10,
):
    """
    Devuelve una lista de eventos de pago futuros/pendientes:
    - una factura 'pendiente' (no canjeada) aporta un evento en su due_date.
    - cada letra 'pendiente' de un canje aporta un evento, no en su
      fecha_vencimiento contractual sino en vencimiento + letra_dias_pago_tipico
      (el plazo real con el que normalmente se paga, no exacto en vcto),
      representando a TODAS las facturas agrupadas en ese canje. Se considera
      vencida solo pasado vencimiento + letra_dias_gracia_max (el máximo real
      que da el proveedor), no el día siguiente al vencimiento contractual.
    - si se pasa 'expenses', cada gasto 'pendiente' aporta un evento en su
      due_date (los 'pagado' y 'omitido' no).
    Las facturas 'pagada' o 'canjeada' no generan evento por sí mismas.
    Si track_contado es False, las facturas al contado se excluyen (siguen
    registradas y visibles en Facturas, solo no aparecen en estas vistas).
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
                "dias_atraso": days_late(inv["due_date"], today),
                "kind": "invoice",
                "doc_type": inv["doc_type"],
                "ref_id": inv["id"],
            })

    for l in letras:
        if l["estado"] != "pendiente":
            continue
        grouped = canje_invoices.get(l.get("canje_id"), [])
        if grouped:
            vendors = ", ".join(sorted(set(i["vendor"] for i in grouped))) or "—"
            branches = ", ".join(sorted(set(i["branch"] for i in grouped))) or "—"
            facturas = ", ".join(i["invoice_number"] for i in grouped) or "—"
            label = f"Letra {l.get('numero') or '—'} ({len(grouped)} factura(s))"
        else:
            # letra suelta ya programada: usa sus propios datos
            vendors = l.get("vendor") or "—"
            branches = l.get("branch") or "—"
            facturas = "—"
            label = f"Letra {l.get('numero') or '—'} (programada)"
        fecha_esperada = add_days(l["fecha_vencimiento"], letra_dias_pago_tipico)
        fecha_limite = add_days(l["fecha_vencimiento"], letra_dias_gracia_max)
        events.append({
            "date": fecha_esperada,
            "vencimiento_real": l["fecha_vencimiento"],
            "amount": float(l["monto"]),
            "vendor": vendors,
            "branch": branches,
            "invoice_number": facturas,
            "label": label,
            "overdue": fecha_limite < today,
            # Se marca vencida recién pasado el plazo máximo, pero el atraso
            # que se muestra cuenta desde el vencimiento real.
            "dias_atraso": days_late(l["fecha_vencimiento"], today),
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
            "dias_atraso": days_late(x["due_date"], today),
            "kind": "expense",
            "expense_kind": x["kind"],
            "category": x["category"],
            "fixed_expense_id": x.get("fixed_expense_id"),
            "ref_id": x["id"],
        })

    events.sort(key=lambda e: e["date"])
    return events


def get_paid_events(invoices, letras, expenses=None):
    """Eventos ya pagados, con la fecha real en que se pagaron (no la de
    vencimiento). Para historial — p. ej. el toggle 'Mostrar pagados' de
    Calendario o el comando /pagados del bot — nunca para calcular totales
    pendientes. Trae los mismos campos 'kind'/'doc_type'/'expense_kind'/
    'category' que get_payment_events para poder reusar los mismos filtros."""
    events = []

    for inv in invoices:
        if inv["status"] != "pagada" or not inv.get("paid_at"):
            continue
        events.append({
            "date": inv["paid_at"],
            "amount": float(inv["amount"]),
            "vendor": inv["vendor"],
            "branch": inv["branch"],
            "invoice_number": inv["invoice_number"],
            "label": "Contado" if inv["doc_type"] == "contado" else "Factura a crédito",
            "kind": "invoice",
            "doc_type": inv["doc_type"],
            "paid_by": inv.get("paid_by"),
            "ref_id": inv["id"],
        })

    for l in letras:
        if l["estado"] != "pagada" or not l.get("fecha_pago"):
            continue
        events.append({
            "date": l["fecha_pago"],
            "amount": float(l["monto"]),
            "vendor": l.get("vendor") or "—",
            "branch": l.get("branch") or "—",
            "invoice_number": "—",
            "label": f"Letra {l.get('numero') or '—'}",
            "kind": "letra",
            "paid_by": l.get("paid_by"),
            "ref_id": l["id"],
        })

    for x in (expenses or []):
        if x.get("status") != "pagado" or not x.get("paid_at"):
            continue
        events.append({
            "date": x["paid_at"],
            "amount": float(x["amount"]),
            "vendor": x["name"],
            "branch": x.get("branch") or "General",
            "invoice_number": "",
            "label": f"Gasto {x['kind']} · {x['category']}",
            "kind": "expense",
            "expense_kind": x["kind"],
            "category": x["category"],
            "paid_by": x.get("paid_by"),
            "ref_id": x["id"],
        })

    events.sort(key=lambda e: e["date"])
    return events


def find_suspicious_due_dates(invoices, vendors):
    """Facturas 'pendiente' a crédito cuyo vencimiento no coincide con
    emisión + plazo configurado del proveedor (posible error de digitación
    al registrar o editar). No es un error garantizado — un proveedor puede
    pactar un plazo distinto al habitual para un documento puntual — pero
    vale la pena revisarlas."""
    terms = {v["name"]: v.get("term_days") for v in vendors if v.get("doc_type") == "credito"}
    out = []
    for inv in invoices:
        if inv.get("status") != "pendiente" or inv.get("doc_type") != "credito":
            continue
        term = terms.get(inv.get("vendor"))
        if not term or not inv.get("issue_date") or not inv.get("due_date"):
            continue
        expected = (date.fromisoformat(inv["issue_date"]) + timedelta(days=term)).isoformat()
        if inv["due_date"] != expected:
            out.append({**inv, "expected_due_date": expected, "vendor_term_days": term})
    return out


# ---------- generación de gastos fijos recurrentes ----------

def due_day_for_month(year, month, pay_day):
    """El día de pago, recortado al último día del mes (pay_day 31 en febrero
    -> 28 o 29)."""
    return min(int(pay_day), _cal.monthrange(year, month)[1])


def occurrences_per_month(fixed_expense):
    """Cuántas veces al mes se paga: 2 si es quincenal (con su segundo día
    configurado), 1 si es mensual. Para sumar el compromiso mensual real."""
    if fixed_expense.get("frequency") == "quincenal" and fixed_expense.get("pay_day_2"):
        return 2
    return 1


def fixed_expense_rows_to_create(active_fixed, existing_expenses, today, months_ahead=6):
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
            pay_days = [f["pay_day"]]
            if f.get("frequency") == "quincenal" and f.get("pay_day_2"):
                pay_days.append(f["pay_day_2"])
            for idx, pd in enumerate(pay_days, start=1):
                # Mensual: period "YYYY-MM" (igual que siempre). Quincenal:
                # "YYYY-MM-Q1"/"YYYY-MM-Q2" para que las dos cuotas del mismo
                # mes no choquen contra el índice único (fixed_expense_id, period).
                period = f"{y:04d}-{mo:02d}" if len(pay_days) == 1 else f"{y:04d}-{mo:02d}-Q{idx}"
                if (f["id"], period) in existing:
                    continue
                day = due_day_for_month(y, mo, pd)
                rows.append({
                    "kind": "fijo",
                    "fixed_expense_id": f["id"],
                    "period": period,
                    "name": f["name"],
                    "category": f["category"],
                    "subcategory": f.get("subcategory"),
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


def weekly_balance(invoices, letras, expenses, weeks_back=8, letra_dias_pago_tipico=8):
    """Balance semanal histórico: para cada semana (de la primera deuda
    registrada hasta la semana actual) cuánto se debía (por vencimiento),
    cuánto se pagó de verdad (por fecha de pago) y el saldo pendiente
    acumulado (deuda acumulada - pagado acumulado) a esa altura. Devuelve
    solo las últimas `weeks_back` semanas, pero el acumulado se calcula
    desde el principio para que el saldo sea correcto.

    Las letras no se ubican en su vencimiento contractual sino en
    vencimiento + letra_dias_pago_tipico (el plazo real con el que se suele
    pagar), para que "Debido" refleje cuándo de verdad sale la plata."""
    debido = []
    pagado = []

    for inv in invoices:
        if inv.get("doc_type") != "credito":
            continue
        if inv.get("status") == "canjeada":
            # Su deuda ya no es "la factura": se transfirió a la(s) letra(s)
            # del canje, que la suman por su cuenta más abajo. Contar ambas
            # duplicaría el mismo compromiso (factura + letra resultante).
            continue
        debido.append((inv["due_date"], float(inv["amount"])))
        if inv.get("status") == "pagada" and inv.get("paid_at"):
            pagado.append((inv["paid_at"], float(inv["amount"])))

    for l in letras:
        debido.append((add_days(l["fecha_vencimiento"], letra_dias_pago_tipico), float(l["monto"])))
        if l.get("estado") == "pagada" and l.get("fecha_pago"):
            pagado.append((l["fecha_pago"], float(l["monto"])))

    for x in (expenses or []):
        debido.append((x["due_date"], float(x["amount"])))
        if x.get("status") == "pagado" and x.get("paid_at"):
            pagado.append((x["paid_at"], float(x["amount"])))

    if not debido and not pagado:
        return []

    today = today_str()
    primera = min([d for d, _ in debido] + [d for d, _ in pagado])
    ws = start_of_week(min(primera, today))
    ultima_semana = start_of_week(today)

    debido_por_semana = {}
    for d, amt in debido:
        wk = start_of_week(d)
        debido_por_semana[wk] = debido_por_semana.get(wk, 0.0) + amt
    pagado_por_semana = {}
    for d, amt in pagado:
        wk = start_of_week(d)
        pagado_por_semana[wk] = pagado_por_semana.get(wk, 0.0) + amt

    buckets = []
    acum_debido = 0.0
    acum_pagado = 0.0
    while ws <= ultima_semana:
        d = debido_por_semana.get(ws, 0.0)
        p = pagado_por_semana.get(ws, 0.0)
        acum_debido += d
        acum_pagado += p
        buckets.append({
            "start": ws, "end": add_days(ws, 6),
            "debido": round2(d), "pagado": round2(p),
            "saldo": round2(acum_debido - acum_pagado),
        })
        ws = add_days(ws, 7)

    return buckets[-weeks_back:]


def expense_statement(invoices, letras, expenses, period_start, period_end, letra_dias_pago_tipico=8):
    """Egresos del periodo [period_start, period_end] (inclusive), por
    vencimiento/emisión — se hayan pagado o no todavía, igual criterio que
    'Debido' en weekly_balance. Pensado como un estado de resultados de
    egresos: compras a proveedores (un solo total) + gastos operativos por
    categoría.

    Igual que weekly_balance, una factura 'canjeada' no se cuenta por su
    cuenta: su deuda ya está representada por la letra resultante (sumarlas
    las dos duplicaría el mismo compromiso). Los gastos 'omitido' tampoco
    cuentan — nunca llegaron a incurrirse."""
    compras_amounts = []
    for inv in invoices:
        if inv.get("status") == "canjeada":
            continue
        fecha = inv["due_date"] if inv.get("doc_type") == "credito" else (inv.get("issue_date") or inv["due_date"])
        if fecha and period_start <= fecha <= period_end:
            compras_amounts.append(float(inv["amount"]))
    for l in letras:
        fecha = add_days(l["fecha_vencimiento"], letra_dias_pago_tipico)
        if period_start <= fecha <= period_end:
            compras_amounts.append(float(l["monto"]))
    compras_proveedores = dsum(compras_amounts)

    por_categoria = {}
    for x in expenses:
        if x.get("status") == "omitido":
            continue
        fecha = x["due_date"]
        if period_start <= fecha <= period_end:
            por_categoria.setdefault(x["category"], []).append(float(x["amount"]))
    gastos_por_categoria = {cat: dsum(vals) for cat, vals in por_categoria.items()}
    total_gastos_operativos = dsum(gastos_por_categoria.values())

    return {
        "compras_proveedores": compras_proveedores,
        "gastos_por_categoria": gastos_por_categoria,
        "total_gastos_operativos": total_gastos_operativos,
        "total_egresos": dsum([compras_proveedores, total_gastos_operativos]),
    }


def compute_cash_balance(invoices, letras, expenses, incomes, saldo_inicial=0.0, saldo_inicial_fecha=None,
                         fixed_receipts=None):
    """Saldo de caja real y cuánto queda libre para comprometer en un pedido
    nuevo, a partir de un saldo inicial que se configura una sola vez
    (Configuración → Saldo inicial de caja):

      saldo_actual = saldo_inicial + ingresos registrados DESPUÉS de esa
                     fecha (ventas y lo recibido de ingresos fijos, como
                     las comisiones BCP) - egresos ya PAGADOS después de
                     esa fecha.
                     (la fecha del saldo inicial se excluye, asumiendo que
                     ese saldo ya refleja el cierre de ese día).
      comprometido = todo lo que sigue 'pendiente' — ya se debe, tarde o
                     temprano hay que pagarlo —, sin importar la fecha.
      disponible   = saldo_actual - comprometido: lo que de verdad sobra
                     sin tocar lo que ya está comprometido.
    """
    desde = saldo_inicial_fecha or "0001-01-01"

    ingresos = dsum(
        [i["amount"] for i in incomes if i["date"] > desde]
        + [r["amount"] for r in (fixed_receipts or []) if r["date"] > desde]
    )

    pagado_facturas = dsum(
        i["amount"] for i in invoices
        if i["status"] == "pagada" and i.get("paid_at") and i["paid_at"] > desde
    )
    pagado_letras = dsum(
        l["monto"] for l in letras
        if l["estado"] == "pagada" and l.get("fecha_pago") and l["fecha_pago"] > desde
    )
    pagado_gastos = dsum(
        x["amount"] for x in (expenses or [])
        if x.get("status") == "pagado" and x.get("paid_at") and x["paid_at"] > desde
    )
    egresos_pagados = dsum([pagado_facturas, pagado_letras, pagado_gastos])

    saldo_actual = dsum([round2(saldo_inicial), ingresos, -egresos_pagados])

    comprometido_facturas = dsum(i["amount"] for i in invoices if i["status"] == "pendiente")
    comprometido_letras = dsum(l["monto"] for l in letras if l["estado"] == "pendiente")
    comprometido_gastos = dsum(x["amount"] for x in (expenses or []) if x.get("status") == "pendiente")
    comprometido = dsum([comprometido_facturas, comprometido_letras, comprometido_gastos])

    return {
        "saldo_actual": saldo_actual,
        "comprometido": comprometido,
        "disponible": dsum([saldo_actual, -comprometido]),
    }


def average_daily_income(incomes, days_back=30, today=None):
    """Promedio diario de ingresos registrados en los últimos `days_back`
    días (incluye hoy). 0 si no hay nada registrado en ese rango."""
    today = today or today_str()
    desde = add_days(today, -(days_back - 1))
    total = dsum(i["amount"] for i in incomes if desde <= i["date"] <= today)
    return round2(total / days_back) if days_back else 0.0


def purchase_limit(incomes, fixed_expenses, days_back=30, today=None):
    """Cuánto se puede comprometer en compras NUEVAS a proveedores (fuera de
    los gastos fijos operativos ya comprometidos: alquiler, planilla,
    servicios, etc.), según el promedio de ventas reciente:

      venta_promedio    = promedio diario de `incomes` en los últimos
                           `days_back` días, llevado a semana/mes.
      gastos_fijos       = suma de fixed_expenses activos, cada uno ya
                           multiplicado por cuántas veces se paga al mes
                           (occurrences_per_month) — el compromiso mensual
                           real, no el monto por cuota.
      límite de compra  = venta_promedio - gastos_fijos, por semana y por
                           mes. No incluye facturas/letras a proveedores:
                           ESO es justamente lo que este límite acota.
    """
    venta_diaria = average_daily_income(incomes, days_back, today)
    venta_semanal = round2(venta_diaria * 7)
    venta_mensual = round2(venta_diaria * 30)

    gastos_fijos_mensuales = dsum(
        float(f["amount"]) * occurrences_per_month(f)
        for f in fixed_expenses if f.get("active", True)
    )
    gastos_fijos_semanales = round2(gastos_fijos_mensuales * 7 / 30)

    return {
        "venta_diaria": venta_diaria,
        "venta_semanal": venta_semanal,
        "venta_mensual": venta_mensual,
        "gastos_fijos_semanales": gastos_fijos_semanales,
        "gastos_fijos_mensuales": round2(gastos_fijos_mensuales),
        "limite_semanal": dsum([venta_semanal, -gastos_fijos_semanales]),
        "limite_mensual": dsum([venta_mensual, -gastos_fijos_mensuales]),
    }


def max_new_purchase(events, saldo_actual, venta_diaria, term_days, today=None, ingresos_esperados=None):
    """Cuánto se puede comprometer HOY con un proveedor a `term_days` de
    plazo, revisando semana por semana desde hoy hasta esa fecha (no solo el
    día exacto del vencimiento) — si algo grande cae unos días antes, esa
    semana es tu verdadero cuello de botella, no el día final (que puede
    verse bien solo porque ya se acumuló más venta para entonces). A
    diferencia de 'disponible para comprometer' (mira TODO lo pendiente sin
    importar fecha) y de 'límite de compra' (no distingue plazos), esto
    responde la pregunta real: "si compro con este proveedor, con SU plazo,
    ¿tendré con qué pagarle en el camino hasta que venza?"

      fecha_vence           = hoy + term_days.
      Para cada semana entre hoy y fecha_vence: saldo_actual + (venta_diaria
      * días transcurridos hasta el fin de esa semana) - todo lo YA
      pendiente que vence en o antes de esa semana.
      ingresos_esperados    = ingresos fijos aún no recibidos (comisiones
                              BCP...): suman desde la semana en que se
                              esperan, no como venta diaria. Los que ya
                              debieron llegar y no llegaron no se cuentan.
      semana_mas_ajustada   = la de menor saldo proyectado de ese camino.
      máximo seguro         = ese saldo, nunca negativo (si ya proyecta rojo
                              en algún punto, el máximo es 0 — no "menos
                              cero").
    """
    today = today or today_str()
    fecha_vence = add_days(today, term_days)

    semanas = []
    ws = start_of_week(today)
    while ws <= fecha_vence:
        fin_semana = min(add_days(ws, 6), fecha_vence)
        dias = (date.fromisoformat(fin_semana) - date.fromisoformat(today)).days
        comprometido = dsum(e["amount"] for e in events if e["date"] <= fin_semana)
        esperado = dsum(i["amount"] for i in (ingresos_esperados or []) if today <= i["date"] <= fin_semana)
        proyectado = dsum([saldo_actual, venta_diaria * dias, esperado, -comprometido])
        semanas.append({"fin_semana": fin_semana, "comprometido": comprometido, "proyectado": proyectado})
        ws = add_days(ws, 7)

    peor = min(semanas, key=lambda s: s["proyectado"])

    return {
        "fecha_vence": fecha_vence,
        "semana_mas_ajustada": peor["fin_semana"],
        "comprometido_antes": peor["comprometido"],
        "proyectado": peor["proyectado"],
        "maximo": max(0.0, peor["proyectado"]),
    }


# ---------- ingresos fijos mensuales (comisiones BCP, etc.) ----------

def _sumar_meses(periodo, n):
    y, m = int(periodo[:4]), int(periodo[5:7])
    total = y * 12 + (m - 1) + n
    return f"{total // 12:04d}-{total % 12 + 1:02d}"


def fixed_income_expected(fixed_incomes, receipts, today=None, months_ahead=6):
    """Ingresos fijos que todavía no se confirmaron como recibidos, mes por
    mes desde el primer mes de cada plantilla activa hasta `months_ahead`
    meses adelante. Cada uno se ubica en el ÚLTIMO día de su ventana (day_to)
    para planificar caja sin contar con plata antes de tiempo; `date_from` es
    el primer día en que suele llegar. `atrasado`: ya pasó el último día y
    no se confirmó."""
    today = today or today_str()
    recibidos = {(r.get("fixed_income_id"), r["period"]) for r in receipts}
    hasta = _sumar_meses(today[:7], months_ahead)
    out = []
    for f in fixed_incomes:
        if not f.get("active", True):
            continue
        periodo = f["start_month"]
        while periodo <= hasta:
            if (f["id"], periodo) not in recibidos:
                y, m = int(periodo[:4]), int(periodo[5:7])
                fecha = f"{periodo}-{due_day_for_month(y, m, f['day_to']):02d}"
                out.append({
                    "fixed_income_id": f["id"],
                    "name": f["name"],
                    "period": periodo,
                    "date": fecha,
                    "date_from": f"{periodo}-{due_day_for_month(y, m, f['day_from']):02d}",
                    "amount": round2(f["amount"]),
                    "atrasado": fecha < today,
                })
            periodo = _sumar_meses(periodo, 1)
    return sorted(out, key=lambda e: (e["date"], e["name"]))


def month_expected_inflows(incomes, ingresos_esperados, month_prefix, today=None, days_back=30):
    """Plata que todavía puede ENTRAR en el mes `month_prefix` ('YYYY-MM'),
    para compararla con lo que falta pagar ese mes:

      promedio_diario = venta total de los locales en los últimos
                        `days_back` días, dividida solo entre los días que
                        tienen registro (un día sin registrar no es un día
                        sin venta, así que no baja el promedio).
      dias_restantes  = días del mes desde hoy que aún no tienen ventas
                        registradas (hoy cuenta si todavía no se registró).
      venta_esperada  = promedio_diario * dias_restantes.
      fijos_por_llegar= ingresos fijos esperados de ese mes con fecha desde
                        hoy (los que ya debieron llegar y no llegaron no se
                        cuentan, igual que en el simulador de Presupuesto).
    Un mes ya pasado da 0: ahí ya no entra nada nuevo."""
    today = today or today_str()
    desde = add_days(today, -days_back)
    recientes = [i for i in incomes if desde <= i["date"] <= today]
    dias_con_registro = {i["date"] for i in recientes}
    promedio = round2(dsum(i["amount"] for i in recientes) / len(dias_con_registro)) if dias_con_registro else 0.0

    y, m = int(month_prefix[:4]), int(month_prefix[5:7])
    registrados = {i["date"] for i in incomes if i["date"].startswith(month_prefix)}
    dias_restantes = sum(
        1 for d in range(1, _cal.monthrange(y, m)[1] + 1)
        if (ds := f"{month_prefix}-{d:02d}") >= today and ds not in registrados
    )
    venta_esperada = round2(promedio * dias_restantes)
    fijos = dsum(
        i["amount"] for i in ingresos_esperados
        if i["date"].startswith(month_prefix) and i["date"] >= today
    )
    return {
        "promedio_diario": promedio,
        "dias_restantes": dias_restantes,
        "venta_esperada": venta_esperada,
        "fijos_por_llegar": fijos,
        "total": dsum([venta_esperada, fijos]),
    }


# ---------- simulador: usar un crédito para cancelar deudas ----------

def current_month_daily_sales(incomes, today=None, min_dias=7, days_back=30):
    """Venta promedio por día del mes en curso (total / días con registro).
    A principio de mes, con menos de `min_dias` días registrados, el promedio
    sería poco confiable: usa los últimos `days_back` días. Devuelve
    (promedio, n° de días usados, 'mes' o 'ultimos')."""
    today = today or today_str()
    del_mes = [i for i in incomes if i["date"][:7] == today[:7] and i["date"] <= today]
    dias = {i["date"] for i in del_mes}
    if len(dias) >= min_dias:
        return round2(dsum(i["amount"] for i in del_mes) / len(dias)), len(dias), "mes"
    desde = add_days(today, -days_back)
    recientes = [i for i in incomes if desde <= i["date"] <= today]
    dias = {i["date"] for i in recientes}
    prom = round2(dsum(i["amount"] for i in recientes) / len(dias)) if dias else 0.0
    return prom, len(dias), "ultimos"


def average_monthly_purchases(invoices, today=None, months=3):
    """Compras promedio por mes (facturas por fecha de emisión) en los últimos
    `months` meses completos, sin contar el mes en curso."""
    today = today or today_str()
    hasta = today[:7]
    desde = _sumar_meses(hasta, -months)
    # Los meses antes de empezar a registrar facturas no cuentan: sin esto, un
    # mes vacío (antes de usar la app) bajaba el promedio un tercio.
    emitidas = [(i.get("issue_date") or "")[:7] for i in invoices if i.get("issue_date")]
    primero = min((m for m in emitidas if m), default=hasta)
    desde = max(desde, primero)
    n = 0
    m = desde
    while m < hasta:
        n += 1
        m = _sumar_meses(m, 1)
    total = dsum(i["amount"] for i in invoices if desde <= (i.get("issue_date") or "")[:7] < hasta)
    return round2(total / n) if n else 0.0


def simulator_debts(debts, fixed_expenses):
    """Deudas que el simulador ofrece cancelar: las informales activas con
    saldo. Su cuota mensual se toma del gasto fijo vinculado (que es lo que
    de verdad se paga) o, si no está vinculada, de la ficha de la deuda."""
    fx = {f["id"]: f for f in fixed_expenses}
    out = []
    for d in debts:
        if d.get("debt_type") != "informal" or not d.get("active", True) or float(d.get("balance") or 0) <= 0:
            continue
        vinculado = fx.get(d.get("fixed_expense_id"))
        cuota = float(vinculado["amount"]) if vinculado else float(d.get("monthly_payment") or 0)
        out.append({
            "id": d["id"],
            "nombre": vinculado["name"] if vinculado else d["creditor"],
            "saldo": round2(d["balance"]),
            "cuota": round2(cuota),
            "fixed_expense_id": d.get("fixed_expense_id"),
        })
    return sorted(out, key=lambda x: (-x["saldo"], x["nombre"]))


def simulation_base(events, incomes, ingresos_esperados, deudas, venta_dia, compras_mes,
                    today=None, n_meses=7, compras_nuevas=None):
    """Lo que entra y sale cada mes desde el mes en curso, SIN las cuotas de
    las deudas del simulador (esas dependen de cuánto se cancele):

      ventas      = venta_dia * días (mes en curso: solo los que faltan y
                    aún no tienen ventas registradas).
      fijos       = ingresos fijos esperados de ese mes (desde hoy).
      proveedores = facturas y letras pendientes que vencen ese mes; desde el
                    tercer mes, al menos `compras_mes` (lo que se compre de
                    ahora en adelante vence recién ahí, a 60-90 días).
      otros       = el resto de lo pendiente (gastos fijos, bancos...).
    Con `compras_nuevas` ({mes: monto}) los proveedores de cada mes son lo ya
    registrado (fijo) + lo nuevo que se planea comprar y que vence ese mes, en
    vez de completar hasta `compras_mes`.
    El mes en curso incluye lo atrasado y deja las cuotas de esas deudas tal
    como están registradas (el crédito todavía no llegó)."""
    today = today or today_str()
    mes0 = today[:7]
    meses = [_sumar_meses(mes0, k) for k in range(n_meses)]
    ids_deudas = {d["fixed_expense_id"] for d in deudas if d.get("fixed_expense_id")}
    filas = []
    for k, mes in enumerate(meses):
        if k == 0:
            del_mes = [e for e in events if e["date"][:7] <= mes]
            dias = month_expected_inflows(incomes, [], mes, today)["dias_restantes"]
        else:
            del_mes = [
                e for e in events
                if e["date"][:7] == mes and not (e["kind"] == "expense" and e.get("fixed_expense_id") in ids_deudas)
            ]
            y, m = int(mes[:4]), int(mes[5:7])
            dias = _cal.monthrange(y, m)[1]
        registrado = dsum(e["amount"] for e in del_mes if e["kind"] in ("invoice", "letra"))
        if compras_nuevas is not None:
            nuevas = round2(compras_nuevas.get(mes, 0.0) or 0.0)
        else:
            nuevas = max(0.0, dsum([round2(compras_mes), -registrado])) if k >= 2 else 0.0
        prov = dsum([registrado, nuevas])
        filas.append({
            "mes": mes,
            "ventas": round2(venta_dia * dias),
            "fijos": dsum(i["amount"] for i in ingresos_esperados if i["date"][:7] == mes and i["date"] >= today),
            "proveedores": prov,
            "prov_registrado": registrado,
            "prov_nuevas": nuevas,
            "otros": dsum(e["amount"] for e in del_mes if e["kind"] not in ("invoice", "letra")),
        })
    return filas


def default_new_purchases(base, compras_mes, today=None, plazo_minimo=60):
    """Compras nuevas por mes que propone el simulador: lo que falta para
    llegar a `compras_mes` sobre lo ya registrado, solo en los meses donde
    todavía puede vencer algo que se pida hoy (desde hoy + plazo_minimo)."""
    today = today or today_str()
    primero = add_days(today, plazo_minimo)[:7]
    return {
        f["mes"]: max(0.0, dsum([round2(compras_mes), -f["prov_registrado"]]))
        for f in base if f["mes"] >= primero
    }


def simulate_credit(base, deudas, pagos, caja_inicial, credito, inversiones=None):
    """Caja a fin de cada mes si del `credito` se usan `pagos` ({id: monto})
    para cancelar capital de `deudas`. Cada deuda cobra su cuota sobre lo
    que queda: cancelar la mitad baja la cuota a la mitad (préstamos que se
    pagan solo con interés). El mes 0 no cambia (ver simulation_base).

    `inversiones`: [{monto, mes, recupera, mes_recupera}] — salen de la caja
    en `mes` y, si se espera recuperar algo (p. ej. mercadería de temporada
    que se vende), eso vuelve en `mes_recupera`."""
    inversiones = inversiones or []

    def _inv_del_mes(mes):
        sale = dsum(float(i.get("monto") or 0) for i in inversiones if i.get("mes") == mes)
        vuelve = dsum(float(i.get("recupera") or 0) for i in inversiones if i.get("mes_recupera") == mes)
        return dsum([vuelve, -sale])

    usado = dsum(pagos.get(d["id"], 0) for d in deudas)
    cuota_antes = dsum(d["cuota"] for d in deudas)
    cuota_despues = dsum(
        d["cuota"] * (d["saldo"] - min(pagos.get(d["id"], 0), d["saldo"])) / d["saldo"] for d in deudas
    )
    deuda_restante = dsum(d["saldo"] - min(pagos.get(d["id"], 0), d["saldo"]) for d in deudas)
    caja = dsum([caja_inicial, credito, -usado])
    serie = []
    for k, f in enumerate(base):
        cuotas = 0.0 if k == 0 else cuota_despues
        inv = _inv_del_mes(f["mes"])
        caja = dsum([caja, f["ventas"], f["fijos"], -f["proveedores"], -f["otros"], -cuotas, inv])
        serie.append({**f, "cuotas_deudas": round2(cuotas), "inversiones": inv, "caja_fin": caja})
    minimo = min(serie, key=lambda s: s["caja_fin"]) if serie else None
    rojo = next((s["mes"] for s in serie if s["caja_fin"] < 0), None)
    # Cuánto cambia la caja en un mes "normal" (sin el mes en curso, que
    # arrastra lo atrasado): negativo = la caja baja eso cada mes.
    # Las inversiones son puntuales: no cuentan para la tendencia de la caja.
    netos = [dsum([b["caja_fin"], -a["caja_fin"], -b["inversiones"]]) for a, b in zip(serie, serie[1:])]
    return {
        "caja_arranque": dsum([caja_inicial, credito, -usado]),
        "total_inversiones": dsum(float(i.get("monto") or 0) for i in inversiones),
        "total_recupera": dsum(float(i.get("recupera") or 0) for i in inversiones),
        "cambio_mensual_promedio": round2(sum(netos) / len(netos)) if netos else 0.0,
        "usado": usado,
        "sobra_credito": dsum([credito, -usado]),
        "cuota_antes": cuota_antes,
        "cuota_despues": round2(cuota_despues),
        "ahorro_mensual": dsum([cuota_antes, -round2(cuota_despues)]),
        "deuda_restante": deuda_restante,
        "serie": serie,
        "caja_minima": minimo["caja_fin"] if minimo else caja,
        "mes_minimo": minimo["mes"] if minimo else None,
        "mes_rojo": rojo,
    }


def purchase_windows(events, invoices, serie, meta_mensual, today=None, plazos=(60, 75, 90), plan=None):
    """Ventanas de compra de HOY: si coloco un pedido a cada plazo, en qué
    mes vence y cuánto espacio queda ese mes según la meta de compras.

      ya_por_pagar = facturas y letras pendientes que ya vencen ese mes.
      espacio      = meta_mensual - ya_por_pagar (nunca negativo).
      estado       = 'lleno' sin espacio; 'caja' si hay espacio pero en el
                     escenario la caja queda en rojo desde ese mes; si no, 'ok'.
      dias_1_10    = vence entre el 1 y el 10, cuando se juntan planilla,
                     alquileres y bancos.
    También devuelve cuánto queda de la meta para colocar en el mes en curso
    (meta - facturas ya emitidas este mes)."""
    today = today or today_str()
    filas = []
    for plazo in plazos:
        vence = add_days(today, plazo)
        mes = vence[:7]
        ya = dsum(e["amount"] for e in events if e["kind"] in ("invoice", "letra") and e["date"][:7] == mes)
        # Con un plan de compras nuevas por mes, el espacio es lo planeado para
        # ese mes; si no, lo que falta para llegar a la meta.
        espacio = max(0.0, plan[mes]) if plan is not None and mes in plan else max(0.0, dsum([meta_mensual, -ya]))
        desde_mes = [s["caja_fin"] for s in serie if s["mes"] >= mes]
        caja_rojo = bool(desde_mes) and min(desde_mes) < 0
        filas.append({
            "plazo": plazo,
            "vence": vence,
            "mes": mes,
            "ya_por_pagar": ya,
            "espacio": round2(espacio),
            "dias_1_10": int(vence[8:10]) <= 10,
            "estado": "lleno" if espacio <= 0 else ("caja" if caja_rojo else "ok"),
        })
    comprado_mes = dsum(i["amount"] for i in invoices if (i.get("issue_date") or "")[:7] == today[:7])
    return {
        "filas": filas,
        "comprado_este_mes": comprado_mes,
        "queda_este_mes": max(0.0, dsum([meta_mensual, -comprado_mes])),
    }


def adjustment_to_stay_positive(serie):
    """Cuánto habría que ajustar cada mes para que la caja (`serie` de
    simulate_credit) nunca quede en rojo:

      compras_mes  = comprar eso menos cada mes. Se nota recién desde el
                     tercer mes (lo que compras hoy vence en 60-90 días).
      venta_mes    = vender eso más cada mes (entra al toque, desde el mes
                     siguiente); venta_dia = lo mismo por día (/30).
      extra_inicio = plata que haría falta conseguir YA (más crédito, cobrar
                     antes, postergar un pago) porque los primeros meses
                     quedan en rojo antes de que bajar compras llegue a
                     tiempo. Con eso cubierto se calcula lo demás.
    Todo 0 si la caja no entra en rojo."""
    cajas = [s["caja_fin"] for s in serie]
    if not cajas or min(cajas) >= 0:
        return {"compras_mes": 0.0, "venta_mes": 0.0, "venta_dia": 0.0, "extra_inicio": 0.0, "extra_inicio_ventas": 0.0}
    extra = max(0.0, -min(cajas[:2]))
    compras = max([0.0] + [-(c + extra) / (k - 1) for k, c in enumerate(cajas) if k >= 2])
    extra_v = max(0.0, -cajas[0])
    venta = max([0.0] + [-(c + extra_v) / k for k, c in enumerate(cajas) if k >= 1])
    return {
        "compras_mes": round2(compras),
        "venta_mes": round2(venta),
        "venta_dia": round2(venta / 30),
        "extra_inicio": round2(extra),
        "extra_inicio_ventas": round2(extra_v),
    }


def events_dataframe(events):
    if not events:
        return pd.DataFrame(columns=["date", "amount", "vendor", "branch", "invoice_number", "label", "overdue"])
    return pd.DataFrame(events)


# ---------- indicadores de ingresos ----------

def income_period(name, today):
    """(desde, hasta) en ISO para los periodos de la página Ingresos."""
    if name == "Últimos 7 días":
        return (today - timedelta(days=6)).isoformat(), today.isoformat()
    if name == "Últimos 30 días":
        return (today - timedelta(days=29)).isoformat(), today.isoformat()
    if name == "Mes pasado":
        fin = today.replace(day=1) - timedelta(days=1)
        return fin.replace(day=1).isoformat(), fin.isoformat()
    return today.replace(day=1).isoformat(), today.isoformat()  # Este mes


def income_indicators(incomes, branches, start, end):
    """Indicadores de venta entre start y end (ISO, inclusive): total, promedio
    por día, mejor día y, por sucursal, total, promedio por día abierto (un 0
    es local cerrado y no baja el promedio), participación, días sin registrar
    y variación contra el periodo anterior del mismo largo."""
    d0, d1 = date.fromisoformat(start), date.fromisoformat(end)
    largo = (d1 - d0).days + 1
    prev_start = (d0 - timedelta(days=largo)).isoformat()
    prev_end = (d0 - timedelta(days=1)).isoformat()

    actuales = [r for r in incomes if start <= r["date"] <= end]
    previos = [r for r in incomes if prev_start <= r["date"] <= prev_end]
    total = dsum(r["amount"] for r in actuales)
    total_prev = dsum(r["amount"] for r in previos)

    por_dia = {}
    for r in actuales:
        por_dia[r["date"]] = por_dia.get(r["date"], 0) + float(r["amount"])
    mejor_dia = max(por_dia.items(), key=lambda kv: kv[1]) if por_dia else None

    def _variacion(actual, anterior):
        return round((actual - anterior) / anterior * 100, 1) if anterior else None

    filas = []
    for b in branches:
        mias = [r for r in actuales if r["branch"] == b]
        abiertos = [r for r in mias if float(r["amount"]) > 0]
        total_b = dsum(r["amount"] for r in mias)
        dias_registrados = {r["date"] for r in mias}
        mejor = max(abiertos, key=lambda r: float(r["amount"])) if abiertos else None
        filas.append({
            "branch": b,
            "total": total_b,
            "promedio": round2(total_b / len(abiertos)) if abiertos else 0.0,
            "participacion": round(total_b / total * 100, 1) if total else 0.0,
            "dias_abiertos": len(abiertos),
            "dias_cerrados": len(mias) - len(abiertos),
            "dias_sin_registrar": largo - len(dias_registrados),
            "mejor_dia": (mejor["date"], float(mejor["amount"])) if mejor else None,
            "variacion": _variacion(total_b, dsum(r["amount"] for r in previos if r["branch"] == b)),
        })
    filas.sort(key=lambda f: -f["total"])

    return {
        "total": total,
        "dias_con_registro": len(por_dia),
        "promedio_diario": round2(total / len(por_dia)) if por_dia else 0.0,
        "mejor_dia": mejor_dia,
        "total_anterior": total_prev,
        "variacion": _variacion(total, total_prev),
        "por_sucursal": filas,
    }
