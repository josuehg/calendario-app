import streamlit as st
import db
import utils

st.set_page_config(page_title="Configuración", page_icon="⚙️", layout="wide")
utils.check_password()

st.title("⚙️ Configuración de sucursales")
st.caption("Ponle el nombre real a cada una de tus 6 sucursales. Se usará en el formulario y en el consolidado.")

branches = db.get_branches()
while len(branches) < 6:
    branches.append(f"Sucursal {len(branches) + 1}")

with st.form("branches_form"):
    names = []
    cols = st.columns(2)
    for i, b in enumerate(branches):
        with cols[i % 2]:
            names.append(st.text_input(f"Sucursal {i + 1}", value=b))
    submitted = st.form_submit_button("Guardar nombres", type="primary")
    if submitted:
        db.save_branches([n.strip() for n in names if n.strip()])
        st.success("Nombres guardados.")
