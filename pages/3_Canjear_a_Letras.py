import uuid
import streamlit as st
import db
import utils

st.set_page_config(page_title="Canjear a Letras", page_icon="🔁", layout="wide")
utils.check_password()

st.title("🔁 Canjear facturas a letras")
st.caption("Selecciona una o varias facturas a crédito y agrúpalas en una o varias letras — no necesitan coincidir 1 a 1.")

invoices = db.list_invoices()
pendientes_credito = [i for i in invoices if i["status"] == "pendiente" and i["doc_type"] == "credito"]

if "canje_selected_ids" not in st.session_state:
    st.session_state["canje_selected_ids"] = st.session_state.pop("canje_preselect", [])
if "canje_letra_ids" not in st.session_state:
    st.session_state["canje_letra_ids"] = []

if not pendientes_credito:
    st.info("No hay facturas a crédito pendientes de canje.")
    st.stop()

options = {
    f"{r['vendor']} · Fact. {r['invoice_number']} · {r['branch']} · {utils.money(r['amount'])} · vence {utils.fmt_short(r['due_date'])}": r["id"]
    for r in pendientes_credito
}
id_to_label = {v: k for k, v in options.items()}
default_labels = [id_to_label[i] for i in st.session_state["canje_selected_ids"] if i in id_to_label]

selected_labels = st.multiselect("Facturas a incluir en este canje", list(options.keys()), default=default_labels)
selected_ids = [options[l] for l in selected_labels]
st.session_state["canje_selected_ids"] = selected_ids

selected_invoices = [i for i in pendientes_credito if i["id"] in selected_ids]
total_facturas = sum(float(i["amount"]) for i in selected_invoices)

if not selected_invoices:
    st.warning("Selecciona al menos una factura para continuar.")
    st.stop()

st.metric("Total de facturas seleccionadas", utils.money(total_facturas))

st.divider()
st.subheader("Letras a generar")

# inicializa con una letra por defecto si la lista está vacía
if not st.session_state["canje_letra_ids"]:
    new_id = str(uuid.uuid4())
    st.session_state["canje_letra_ids"] = [new_id]
    st.session_state[f"numero_{new_id}"] = ""
    st.session_state[f"monto_{new_id}"] = total_facturas
    earliest_due = min(i["due_date"] for i in selected_invoices)
    st.session_state[f"fecha_{new_id}"] = None

letras_data = []
for idx, lid in enumerate(st.session_state["canje_letra_ids"]):
    c1, c2, c3, c4 = st.columns([1.2, 1, 1, 0.5])
    numero = c1.text_input(f"N° letra {idx + 1}", key=f"numero_{lid}")
    monto = c2.number_input(f"Monto {idx + 1}", min_value=0.0, step=0.01, format="%.2f", key=f"monto_{lid}")
    fecha = c3.date_input(f"Vencimiento {idx + 1}", key=f"fecha_{lid}", value=None)
    if c4.button("✕", key=f"remove_{lid}", help="Quitar esta letra"):
        st.session_state["canje_letra_ids"].remove(lid)
        st.rerun()
    letras_data.append({"numero": numero, "monto": monto, "fecha_vencimiento": fecha})

if st.button("+ Agregar letra"):
    new_id = str(uuid.uuid4())
    st.session_state["canje_letra_ids"].append(new_id)
    st.session_state[f"numero_{new_id}"] = ""
    st.session_state[f"monto_{new_id}"] = 0.0
    st.rerun()

total_letras = sum(l["monto"] or 0 for l in letras_data)
mismatch = abs(total_letras - total_facturas) > 0.009
color = ":red" if mismatch else ":green"
st.markdown(f"Total asignado a letras: {color}[**{utils.money(total_letras)}**] de **{utils.money(total_facturas)}**"
            + (" — no coincide con el total de las facturas seleccionadas." if mismatch else ""))

st.divider()
if st.button("Confirmar canje", type="primary"):
    if any(not l["fecha_vencimiento"] or not l["monto"] or l["monto"] <= 0 for l in letras_data):
        st.error("Cada letra necesita un monto mayor a 0 y una fecha de vencimiento.")
    else:
        letras_payload = [
            {"numero": l["numero"], "monto": l["monto"], "fecha_vencimiento": l["fecha_vencimiento"].isoformat()}
            for l in letras_data
        ]
        db.create_canje(selected_ids, letras_payload)
        st.session_state["canje_selected_ids"] = []
        st.session_state["canje_letra_ids"] = []
        st.success(f"Canje registrado: {len(selected_ids)} factura(s) → {len(letras_payload)} letra(s).")
        st.balloons()
