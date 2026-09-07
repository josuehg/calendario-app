"""
Capa de acceso a datos — todas las consultas a Supabase viven aquí para que
las páginas de Streamlit no repitan lógica de base de datos.
"""
from datetime import date

import streamlit as st
from supabase import create_client, Client

DEFAULT_BRANCHES = [
    "Sucursal 1", "Sucursal 2", "Sucursal 3",
    "Sucursal 4", "Sucursal 5", "Sucursal 6",
]


@st.cache_resource
def get_client() -> Client:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_SERVICE_KEY"]
    return create_client(url, key)


# ---------- sucursales ----------

def get_branches():
    sb = get_client()
    res = sb.table("branches").select("name").order("id").execute()
    names = [r["name"] for r in res.data]
    return names if names else DEFAULT_BRANCHES


def get_branches_full():
    """Devuelve [{id, name, pin}, ...] para la página de Configuración."""
    sb = get_client()
    res = sb.table("branches").select("id, name, pin").order("id").execute()
    return res.data


def save_branches(rows):
    """Reemplaza la lista completa de sucursales, en orden.
    rows: lista de dicts {name, pin}. pin vacío se guarda como None."""
    sb = get_client()
    sb.table("branches").delete().neq("id", 0).execute()
    payload = [
        {"name": r["name"].strip(), "pin": (r.get("pin") or "").strip() or None}
        for r in rows if r["name"].strip()
    ]
    if payload:
        sb.table("branches").insert(payload).execute()


def find_branch_by_pin(pin):
    """Devuelve el nombre de la sucursal cuyo PIN coincide, o None."""
    pin = (pin or "").strip()
    if not pin:
        return None
    sb = get_client()
    res = sb.table("branches").select("name, pin").execute()
    for r in res.data:
        if r.get("pin") and r["pin"] == pin:
            return r["name"]
    return None


# ---------- proveedores ----------

def get_vendors():
    sb = get_client()
    res = sb.table("vendors").select("*").order("name").execute()
    return res.data


def get_vendor_by_name(name):
    sb = get_client()
    res = sb.table("vendors").select("*").eq("name", name).limit(1).execute()
    return res.data[0] if res.data else None


def get_vendor_by_ruc(ruc):
    ruc = (ruc or "").strip()
    if not ruc:
        return None
    sb = get_client()
    res = sb.table("vendors").select("*").eq("ruc", ruc).limit(1).execute()
    return res.data[0] if res.data else None


def create_vendor(data: dict):
    """Crea un proveedor nuevo. Lanza una excepción si el nombre o el RUC
    ya existen (restricción unique en la base de datos) — quien llama debe
    validar antes con get_vendors()/get_vendor_by_ruc() para dar un mensaje
    claro, y puede envolver esto en try/except como respaldo."""
    sb = get_client()
    return sb.table("vendors").insert(data).execute()


def update_vendor(vendor_id, data: dict):
    """Actualiza un proveedor existente por id (no por nombre, para que
    renombrarlo no cree una fila duplicada). Si cambia el nombre, arrastra
    el cambio a las facturas ya registradas (guardan el nombre como texto)."""
    sb = get_client()
    new_name = (data.get("name") or "").strip()
    prev = None
    if new_name:
        cur = sb.table("vendors").select("name").eq("id", vendor_id).limit(1).execute().data
        prev = cur[0]["name"] if cur else None
    res = sb.table("vendors").update(data).eq("id", vendor_id).execute()
    if prev and new_name and prev != new_name:
        sb.table("invoices").update({"vendor": new_name}).eq("vendor", prev).execute()
    return res


def delete_vendor(vendor_id):
    sb = get_client()
    return sb.table("vendors").delete().eq("id", vendor_id).execute()


# ---------- ajustes ----------

def get_settings():
    sb = get_client()
    res = sb.table("app_settings").select("*").eq("id", 1).limit(1).execute()
    return res.data[0] if res.data else {"track_contado": True}


def save_settings(data: dict):
    sb = get_client()
    return sb.table("app_settings").update(data).eq("id", 1).execute()


# ---------- facturas ----------

def list_invoices():
    sb = get_client()
    res = sb.table("invoices").select("*").order("issue_date", desc=True).execute()
    return res.data


def create_invoice(data: dict):
    sb = get_client()
    return sb.table("invoices").insert(data).execute()


def update_invoice(invoice_id: str, data: dict):
    sb = get_client()
    return sb.table("invoices").update(data).eq("id", invoice_id).execute()


def delete_invoice(invoice_id: str):
    sb = get_client()
    return sb.table("invoices").delete().eq("id", invoice_id).execute()


def mark_invoice_paid(invoice_id: str, paid_at: str, paid_by: str | None = None):
    return update_invoice(invoice_id, {"status": "pagada", "paid_at": paid_at, "paid_by": paid_by})


# ---------- canjes y letras ----------

def list_canjes():
    sb = get_client()
    return sb.table("canjes").select("*").execute().data


def list_canje_facturas():
    sb = get_client()
    return sb.table("canje_facturas").select("*").execute().data


def list_letras():
    sb = get_client()
    res = sb.table("letras").select("*").order("fecha_vencimiento").execute()
    return res.data


def create_canje(invoice_ids: list, letras: list, notes: str = "", created_by: str | None = None):
    """
    invoice_ids: lista de ids de facturas incluidas en el canje.
    letras: lista de dicts {numero, monto, fecha_vencimiento}.
    Marca las facturas incluidas como 'canjeada'.
    """
    sb = get_client()
    canje_res = sb.table("canjes").insert({"notes": notes, "created_by": created_by}).execute()
    canje_id = canje_res.data[0]["id"]

    sb.table("canje_facturas").insert(
        [{"canje_id": canje_id, "invoice_id": iid} for iid in invoice_ids]
    ).execute()

    sb.table("letras").insert(
        [
            {
                "canje_id": canje_id,
                "numero": l.get("numero", ""),
                "monto": l["monto"],
                "fecha_vencimiento": l["fecha_vencimiento"],
                "estado": "pendiente",
            }
            for l in letras
        ]
    ).execute()

    for iid in invoice_ids:
        sb.table("invoices").update({"status": "canjeada"}).eq("id", iid).execute()

    return canje_id


def mark_letra_paid(letra_id: str, fecha_pago: str, paid_by: str | None = None):
    sb = get_client()
    return sb.table("letras").update(
        {"estado": "pagada", "fecha_pago": fecha_pago, "paid_by": paid_by}
    ).eq("id", letra_id).execute()


def create_letra(data: dict):
    """Registra una letra ya programada, sin canje (canje_id queda null).
    data: {numero, monto, fecha_vencimiento, vendor, branch, notes}."""
    sb = get_client()
    return sb.table("letras").insert({**data, "estado": "pendiente"}).execute()


def update_letra(letra_id: str, data: dict):
    sb = get_client()
    return sb.table("letras").update(data).eq("id", letra_id).execute()


def delete_letra(letra_id: str):
    sb = get_client()
    return sb.table("letras").delete().eq("id", letra_id).execute()


# ---------- categorías de gasto ----------

def list_expense_categories():
    sb = get_client()
    res = sb.table("expense_categories").select("*").order("sort_order").order("name").execute()
    return res.data


def add_expense_category(name: str):
    sb = get_client()
    return sb.table("expense_categories").insert({"name": name.strip(), "sort_order": 50}).execute()


def rename_expense_category(cat_id: int, new_name: str):
    """Renombra la categoría y arrastra el cambio a los gastos ya guardados
    (category se guarda como texto en fixed_expenses y expenses)."""
    sb = get_client()
    old = sb.table("expense_categories").select("name").eq("id", cat_id).limit(1).execute().data
    new_name = new_name.strip()
    sb.table("expense_categories").update({"name": new_name}).eq("id", cat_id).execute()
    if old:
        prev = old[0]["name"]
        sb.table("fixed_expenses").update({"category": new_name}).eq("category", prev).execute()
        sb.table("expenses").update({"category": new_name}).eq("category", prev).execute()


def delete_expense_category(cat_id: int):
    sb = get_client()
    return sb.table("expense_categories").delete().eq("id", cat_id).execute()


# ---------- gastos fijos (plantillas recurrentes) ----------

def list_fixed_expenses(active_only: bool = False):
    sb = get_client()
    q = sb.table("fixed_expenses").select("*").order("name")
    if active_only:
        q = q.eq("active", True)
    return q.execute().data


def create_fixed_expense(data: dict):
    sb = get_client()
    return sb.table("fixed_expenses").insert(data).execute()


def update_fixed_expense(fx_id: int, data: dict):
    """Actualiza la plantilla y **sincroniza las cuotas futuras que aún están
    pendientes**: nombre, categoría, sucursal, monto y la fecha (si cambió el
    día de pago). Las cuotas ya pagadas u omitidas, y los meses pasados, no se
    tocan. Si la plantilla queda inactiva o fuera del rango de fin, sus cuotas
    futuras pendientes se eliminan."""
    import utils
    from datetime import date

    sb = get_client()
    res = sb.table("fixed_expenses").update(data).eq("id", fx_id).execute()

    fx = sb.table("fixed_expenses").select("*").eq("id", fx_id).limit(1).execute().data
    fx = fx[0] if fx else None
    pend = sb.table("expenses").select("*").eq("fixed_expense_id", fx_id).eq("status", "pendiente").execute().data
    if not fx or not pend:
        return res

    this_month = date.today().replace(day=1)
    end = date.fromisoformat(fx["end_month"]).replace(day=1) if fx.get("end_month") else None

    for e in pend:
        period = e.get("period") or ""
        try:
            y, mo = int(period[:4]), int(period[5:7])
        except (ValueError, IndexError):
            continue
        first = date(y, mo, 1)
        if first < this_month:
            continue  # cuota vencida sin pagar: se ajusta a mano
        if not fx["active"] or (end and first > end):
            sb.table("expenses").delete().eq("id", e["id"]).execute()
            continue
        day = utils.due_day_for_month(y, mo, fx["pay_day"])
        sb.table("expenses").update({
            "name": fx["name"],
            "category": fx["category"],
            "branch": fx.get("branch"),
            "amount": fx["amount"],
            "due_date": date(y, mo, day).isoformat(),
        }).eq("id", e["id"]).execute()
    return res


def delete_fixed_expense(fx_id: int):
    """Borra la plantilla. Las instancias ya generadas quedan (con
    fixed_expense_id en null por el ON DELETE SET NULL)."""
    sb = get_client()
    return sb.table("fixed_expenses").delete().eq("id", fx_id).execute()


# ---------- gastos concretos ----------

def list_expenses():
    sb = get_client()
    res = sb.table("expenses").select("*").order("due_date").execute()
    return res.data


def create_expense(data: dict):
    sb = get_client()
    return sb.table("expenses").insert(data).execute()


def update_expense(expense_id: str, data: dict):
    sb = get_client()
    return sb.table("expenses").update(data).eq("id", expense_id).execute()


def delete_expense(expense_id: str):
    sb = get_client()
    return sb.table("expenses").delete().eq("id", expense_id).execute()


def set_expense_status(expense_id: str, status: str, paid_at: str | None = None, paid_by: str | None = None):
    return update_expense(expense_id, {"status": status, "paid_at": paid_at, "paid_by": paid_by})


def ensure_expense_instances(months_ahead: int = 3):
    """Genera las filas de 'expenses' que faltan para cada gasto fijo activo,
    desde el mes actual hasta months_ahead meses adelante. Idempotente: solo
    inserta lo que no existe (además del índice único como red de seguridad).
    Se llama al abrir Gastos, Calendario y Presupuesto — no hay cron.
    La lógica pura vive en utils.fixed_expense_rows_to_create (testeable)."""
    import utils  # local: evita el import circular utils <-> db

    fixed = list_fixed_expenses(active_only=True)
    if not fixed:
        return
    rows = utils.fixed_expense_rows_to_create(fixed, list_expenses(), date.today(), months_ahead)
    if rows:
        try:
            get_client().table("expenses").insert(rows).execute()
        except Exception:
            # carrera con otra sesión: el índice único ya cubrió el hueco
            pass
