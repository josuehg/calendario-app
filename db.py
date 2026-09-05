"""
Capa de acceso a datos — todas las consultas a Supabase viven aquí para que
las páginas de Streamlit no repitan lógica de base de datos.
"""
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


def save_vendor(data: dict):
    """Crea o actualiza un proveedor (upsert por nombre)."""
    sb = get_client()
    return sb.table("vendors").upsert(data, on_conflict="name").execute()


def delete_vendor(vendor_id):
    sb = get_client()
    return sb.table("vendors").delete().eq("id", vendor_id).execute()


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


def mark_invoice_paid(invoice_id: str, paid_at: str):
    return update_invoice(invoice_id, {"status": "pagada", "paid_at": paid_at})


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


def create_canje(invoice_ids: list, letras: list, notes: str = ""):
    """
    invoice_ids: lista de ids de facturas incluidas en el canje.
    letras: lista de dicts {numero, monto, fecha_vencimiento}.
    Marca las facturas incluidas como 'canjeada'.
    """
    sb = get_client()
    canje_res = sb.table("canjes").insert({"notes": notes}).execute()
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


def mark_letra_paid(letra_id: str, fecha_pago: str):
    sb = get_client()
    return sb.table("letras").update(
        {"estado": "pagada", "fecha_pago": fecha_pago}
    ).eq("id", letra_id).execute()
