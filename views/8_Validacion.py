import streamlit as st
import db
import utils

st.title("✅ Validación de facturas")
st.caption(
    "Confirma que cada documento que te mandan los proveedores (o que ves en Odoo) "
    "ya esté registrado aquí. Esta app no se conecta con Odoo — es un cruce manual: "
    "revisa allá y marca 'Validado' aquí cuando confirmes que coincide."
)

invoices = db.list_invoices()

f1, f2, f3, f4, f5 = st.columns([1.2, 1.4, 1.2, 1, 1])
branches = ["Todas"] + db.get_branches() + ["Oficina central"]
f_branch = f1.selectbox("Sucursal", branches, key="val_f_branch")
f_vendor = f2.text_input("Buscar proveedor", key="val_f_vendor")
f_validado = f3.selectbox("Validado", ["Todos", "Pendientes de validar", "Ya validados"], key="val_f_validado")
f_from = f4.date_input("Emitidas desde", value=None, key="val_f_from")
f_to = f5.date_input("Emitidas hasta", value=None, key="val_f_to")

rows = invoices
if f_branch != "Todas":
    rows = [r for r in rows if r["branch"] == f_branch]
if f_vendor:
    rows = [r for r in rows if f_vendor.lower() in r["vendor"].lower()]
if f_validado == "Pendientes de validar":
    rows = [r for r in rows if not r.get("validated")]
elif f_validado == "Ya validados":
    rows = [r for r in rows if r.get("validated")]
if f_from:
    rows = [r for r in rows if r["issue_date"] >= f_from.isoformat()]
if f_to:
    rows = [r for r in rows if r["issue_date"] <= f_to.isoformat()]

rows = sorted(rows, key=lambda r: r["issue_date"], reverse=True)

pend_total = len([i for i in invoices if not i.get("validated")])
c1, c2 = st.columns(2)
c1.metric("Pendientes de validar (todas las sucursales)", pend_total)
c2.metric("Mostrando con estos filtros", len(rows))

st.divider()

if not rows:
    st.info("No hay documentos con estos filtros.")
else:
    for r in rows:
        with st.container(border=True):
            c1, c2, c3 = st.columns([3, 1.6, 1.2])
            with c1:
                st.markdown(f"**{r['vendor']}** · Fact. {r['invoice_number']} · {r['branch']}")
                st.caption(f"Emisión {utils.fmt_short(r['issue_date'])} · {utils.money(r['amount'])} · {r['doc_type']}")
                if r.get("validated"):
                    st.caption(f"✅ Validado por {r.get('validated_by') or '—'} el {utils.fmt_short(r.get('validated_at'))}")
            with c2:
                st.markdown("✅ Validado" if r.get("validated") else "⏳ Pendiente")
            with c3:
                if r.get("validated"):
                    if st.button("Desmarcar", key=f"val_undo_{r['id']}", width="stretch"):
                        db.unmark_invoice_validated(r["id"])
                        st.rerun()
                else:
                    if st.button("Marcar validado", key=f"val_mark_{r['id']}", width="stretch", type="primary"):
                        db.mark_invoice_validated(r["id"], utils.current_actor(), utils.today_lima().isoformat())
                        st.rerun()
