"""
Utilidades compartidas: fechas, formato de moneda, control de acceso simple,
y la lógica que convierte facturas + letras en "eventos de pago" para el
calendario y el presupuesto.
"""
import calendar as _cal
import io
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

    admin_pin = st.secrets.get("APP_PASSWORD")
    validator_pin = st.secrets.get("VALIDATOR_PASSWORD")

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


def compute_cash_balance(invoices, letras, expenses, incomes, saldo_inicial=0.0, saldo_inicial_fecha=None):
    """Saldo de caja real y cuánto queda libre para comprometer en un pedido
    nuevo, a partir de un saldo inicial que se configura una sola vez
    (Configuración → Saldo inicial de caja):

      saldo_actual = saldo_inicial + ingresos registrados DESPUÉS de esa
                     fecha - egresos ya PAGADOS después de esa fecha.
                     (la fecha del saldo inicial se excluye, asumiendo que
                     ese saldo ya refleja el cierre de ese día).
      comprometido = todo lo que sigue 'pendiente' — ya se debe, tarde o
                     temprano hay que pagarlo —, sin importar la fecha.
      disponible   = saldo_actual - comprometido: lo que de verdad sobra
                     sin tocar lo que ya está comprometido.
    """
    desde = saldo_inicial_fecha or "0001-01-01"

    ingresos = dsum(i["amount"] for i in incomes if i["date"] > desde)

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


def max_new_purchase(events, saldo_actual, venta_diaria, term_days, today=None):
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
        proyectado = dsum([saldo_actual, venta_diaria * dias, -comprometido])
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


def events_dataframe(events):
    if not events:
        return pd.DataFrame(columns=["date", "amount", "vendor", "branch", "invoice_number", "label", "overdue"])
    return pd.DataFrame(events)
