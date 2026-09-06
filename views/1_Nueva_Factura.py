from datetime import date, timedelta

import streamlit as st
import db
import utils

st.title("🧾 Registro de documentos de compra")

auth_role = st.session_state.get("auth_role")
auth_branch = st.session_state.get("auth_branch")

DOCUMENT_TYPES = ["Factura", "Boleta", "Nota de compra", "Otro"]

# Para "limpiar" el formulario no se borran keys de widgets (poco fiable en el
# navegador): se cambia el sufijo `nonce` de TODAS las keys, así en el siguiente
# render los widgets son nuevos y arrancan vacíos. Método a prueba de balas.
nonce = st.session_state.get("nf_nonce", 0)


def K(name: str) -> str:
    return f"{name}__{nonce}"


def _clear_form():
    """Callback de 'Limpiar campos' / 'Registrar otro documento'."""
    st.session_state["nf_nonce"] = st.session_state.get("nf_nonce", 0) + 1
    st.session_state.pop("nf_pending", None)
    st.session_state.pop("nf_done", None)


def _recalc_due_date():
    """Vuelve a poner el vencimiento en emisión + plazo (callback: corre antes
    del rerun, antes de instanciar el widget)."""
    n = st.session_state.get("nf_nonce", 0)
    computed = st.session_state.get("_nf_computed_due")
    if computed:
        st.session_state[f"nf_due_date__{n}"] = computed


def _is_duplicate(vendor, inv_number):
    """Devuelve el documento existente con ese N° para ese proveedor (cualquier
    sucursal), o None."""
    v = (vendor or "").strip().lower()
    n = (inv_number or "").strip().lower()
    return next(
        (
            i for i in db.list_invoices()
            if (i.get("vendor") or "").strip().lower() == v
            and (i.get("invoice_number") or "").strip().lower() == n
        ),
        None,
    )


# Mensaje de éxito del último registro (se muestra tras el st.rerun).
done = st.session_state.pop("nf_done", None)
if done:
    st.success(done)
    st.button("➕ Registrar otro documento", type="primary", on_click=_clear_form)
    st.divider()

# ---------- sucursal ----------
if auth_role == "branch":
    st.text_input("Sucursal", value=auth_branch, disabled=True)
    branch = auth_branch
else:
    branch = st.selectbox("Sucursal", db.get_branches() + ["Oficina central"], key=K("nf_branch"))

# ---------- proveedor ----------
st.markdown("**Proveedor**")
query = st.text_input(
    "Buscar proveedor por RUC o nombre",
    key=K("nf_query"),
    placeholder="Ej: 20123456789 o 'Droguería Norte'",
)

matched_vendor = None
vendor_name = None
vendor_ruc = None
doc_type = None
term_days = None
is_new_vendor = False

q = query.strip()
if q:
    all_vendors = db.get_vendors()
    ql = q.lower()

    if q.isdigit():
        exact = next((v for v in all_vendors if (v.get("ruc") or "") == q), None)
        candidates = [exact] if exact else [v for v in all_vendors if ql in (v.get("ruc") or "").lower()]
    else:
        candidates = [v for v in all_vendors if ql in v["name"].lower() or ql in (v.get("ruc") or "").lower()]

    if len(candidates) == 1:
        matched_vendor = candidates[0]
    elif len(candidates) > 1:
        options = {f"{v['name']} · RUC {v.get('ruc') or 's/RUC'}": v for v in candidates}
        choice = st.selectbox(
            "Se encontraron varios proveedores, elige el correcto:",
            list(options.keys()),
            key=K(f"nf_vendor_choice_{q}"),
        )
        matched_vendor = options[choice]

    if matched_vendor:
        ruc_txt = f" · RUC {matched_vendor['ruc']}" if matched_vendor.get("ruc") else ""
        st.success(f"Proveedor: **{matched_vendor['name']}**{ruc_txt}")
        vendor_name = matched_vendor["name"]
        vendor_ruc = matched_vendor.get("ruc")
        doc_type = matched_vendor["doc_type"]
        term_days = matched_vendor["term_days"]
        if doc_type == "credito":
            st.info(f"Este proveedor trabaja a **crédito, {term_days} días**.")
        else:
            st.info("Este proveedor trabaja al **contado**.")
    else:
        st.warning("No se encontró ningún proveedor con esos datos. Regístralo como proveedor nuevo:")
        is_new_vendor = True
        colA, colB = st.columns(2)
        vendor_name = colA.text_input(
            "Nombre del proveedor nuevo",
            value=("" if q.isdigit() else query),
            key=K("nf_new_vendor_name"),
        )
        vendor_ruc = colB.text_input(
            "RUC (11 dígitos)",
            value=(q if q.isdigit() else ""),
            key=K("nf_new_vendor_ruc"),
            max_chars=11,
        )
        st.caption(
            "Se guarda al contado por defecto — el administrador puede reclasificarlo "
            "luego en Configuración si trabaja a crédito."
        )
        doc_type, term_days = "contado", None
else:
    st.caption("Escribe el RUC o el nombre del proveedor para buscarlo. Si no existe, podrás crearlo aquí mismo.")

# ---------- datos del documento ----------
col1, col2 = st.columns(2)
with col1:
    document_type = st.selectbox("Tipo de documento", DOCUMENT_TYPES, key=K("nf_doc_type_sel"))
    invoice_number = st.text_input("N° de documento", placeholder="F001-00123", key=K("nf_invoice_number"))
    amount = st.number_input("Monto (S/)", min_value=0.0, step=0.01, format="%.2f", key=K("nf_amount"))
with col2:
    issue_date = st.date_input("Fecha de emisión", value=None, key=K("nf_issue_date"))
    notes = st.text_area("Notas (opcional)", height=68, key=K("nf_notes"))

# ---------- vencimiento: solo si el proveedor es a crédito ----------
due_date = None
if doc_type == "credito":
    computed_due = issue_date + timedelta(days=term_days) if (issue_date and term_days) else None
    st.session_state["_nf_computed_due"] = computed_due
    if K("nf_due_date") not in st.session_state:
        st.session_state[K("nf_due_date")] = computed_due or issue_date or date.today()
    dc1, dc2 = st.columns([3, 1])
    due_date = dc1.date_input("Fecha de vencimiento", key=K("nf_due_date"))
    if computed_due:
        dc2.button(
            "↻ Recalcular", use_container_width=True, on_click=_recalc_due_date,
            help=f"Usar emisión + {term_days} días",
        )
    if term_days:
        dc1.caption(f"Sugerida: emisión + {term_days} días. Ajústala si se pactó otra.")

# ---------- registrar / limpiar ----------
if done:
    st.caption("Documento guardado. Pulsa **➕ Registrar otro documento** arriba para cargar el siguiente.")
    st.stop()

rc1, rc2 = st.columns(2)
trigger_register = rc1.button("Registrar documento", type="primary", use_container_width=True)
rc2.button("🧹 Limpiar campos", use_container_width=True, on_click=_clear_form)

if trigger_register:
    faltan = []
    vn = (vendor_name or "").strip()
    ruc_clean = (vendor_ruc or "").strip()
    if not vn:
        faltan.append("nombre del proveedor")
    if not invoice_number.strip():
        faltan.append("N° de documento")
    if amount <= 0:
        faltan.append("monto")
    if not issue_date:
        faltan.append("fecha de emisión")
    if doc_type == "credito" and not due_date:
        faltan.append("fecha de vencimiento")

    if faltan:
        st.error("Completa: " + ", ".join(faltan) + ".")
    elif is_new_vendor and not (ruc_clean.isdigit() and len(ruc_clean) == 11):
        st.error("El RUC debe tener exactamente 11 dígitos.")
    elif doc_type == "credito" and due_date and issue_date and due_date < issue_date:
        st.error("La fecha de vencimiento no puede ser anterior a la de emisión.")
    else:
        proceed = True
        resolved_name, resolved_doc_type, resolved_term = vn, doc_type, term_days
        vendor_is_new = is_new_vendor

        if is_new_vendor:
            existing = db.get_vendors()
            name_match = next((v for v in existing if v["name"].strip().lower() == vn.lower()), None)
            ruc_match = next((v for v in existing if (v.get("ruc") or "") == ruc_clean), None)
            if name_match:
                resolved_name = name_match["name"]
                resolved_doc_type = name_match["doc_type"]
                resolved_term = name_match["term_days"]
                vendor_is_new = False
            elif ruc_match:
                st.error(f"El RUC {ruc_clean} ya pertenece a **{ruc_match['name']}**. Búscalo por ese nombre o RUC arriba.")
                proceed = False

        if proceed:
            dup = _is_duplicate(resolved_name, invoice_number)
            if dup:
                st.error(
                    f"Ya está registrado el documento N° **{dup['invoice_number']}** de "
                    f"**{resolved_name}** (sucursal {dup['branch']}, emitido "
                    f"{utils.fmt_short(dup['issue_date'])}). No se registró de nuevo."
                )
                proceed = False

        if proceed:
            final_due = (
                due_date.isoformat()
                if resolved_doc_type == "credito" and due_date
                else issue_date.isoformat()
            )
            st.session_state["nf_pending"] = {
                "branch": branch,
                "vendor": resolved_name,
                "ruc": ruc_clean or None,
                "is_new_vendor": vendor_is_new,
                "invoice_number": invoice_number.strip(),
                "document_type": document_type,
                "doc_type": resolved_doc_type,
                "term_days": resolved_term,
                "amount": float(amount),
                "issue_date": issue_date.isoformat(),
                "due_date": final_due,
                "notes": notes.strip(),
            }
            st.rerun()

# ---------- diálogo: resumen para confirmar ----------
if st.session_state.get("nf_pending"):
    p = st.session_state["nf_pending"]

    @st.dialog("Confirmar registro")
    def _confirm_dialog():
        tipo_txt = "Contado" if p["doc_type"] == "contado" else f"Crédito · {p['term_days']} días"
        filas = [
            ("Sucursal", p["branch"]),
            ("Proveedor", p["vendor"] + ("  · 🆕 nuevo" if p["is_new_vendor"] else "")),
            ("RUC", p["ruc"] or "—"),
            ("Tipo de documento", p["document_type"]),
            ("N° de documento", p["invoice_number"]),
            ("Monto", utils.money(p["amount"])),
            ("Emisión", utils.fmt_short(p["issue_date"])),
            ("Condición", tipo_txt),
            ("Vencimiento", utils.fmt_short(p["due_date"])),
        ]
        if p["notes"]:
            filas.append(("Notas", p["notes"]))
        st.table({"Campo": [f[0] for f in filas], "Valor": [f[1] for f in filas]})

        b1, b2 = st.columns(2)
        if b1.button("Confirmar y guardar", type="primary", use_container_width=True):
            dup = _is_duplicate(p["vendor"], p["invoice_number"])
            if dup:
                st.error(
                    f"Mientras confirmabas, ya se registró el documento N° "
                    f"**{dup['invoice_number']}** de **{p['vendor']}**. No se guardó otra vez."
                )
                st.session_state["nf_pending"] = None
                return
            if p["is_new_vendor"]:
                try:
                    db.create_vendor(
                        {"name": p["vendor"], "ruc": p["ruc"], "doc_type": "contado", "term_days": None}
                    )
                except Exception:
                    st.error("No se pudo registrar el proveedor: el nombre o el RUC ya está en uso.")
                    return
            db.create_invoice({
                "branch": p["branch"],
                "vendor": p["vendor"],
                "invoice_number": p["invoice_number"],
                "document_type": p["document_type"],
                "doc_type": p["doc_type"],
                "amount": p["amount"],
                "issue_date": p["issue_date"],
                "term_days": p["term_days"],
                "due_date": p["due_date"],
                "status": "pendiente",
                "notes": p["notes"],
                "registered_by": utils.current_actor(),
            })
            tipo_msg = "contado" if p["doc_type"] == "contado" else f"crédito a {p['term_days']} días"
            st.session_state["nf_done"] = (
                f"Registrado: {p['document_type']} N° {p['invoice_number']} de {p['vendor']} "
                f"({tipo_msg}). Vence el {utils.fmt_short(p['due_date'])}."
            )
            # Los campos quedan a la vista para repasar; se vacían al pulsar
            # "➕ Registrar otro documento" (que sube el nonce).
            st.session_state["nf_pending"] = None
            st.rerun()
        if b2.button("Volver a editar", use_container_width=True):
            st.session_state["nf_pending"] = None
            st.rerun()

    _confirm_dialog()
