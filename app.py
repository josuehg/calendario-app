import streamlit as st
import utils

st.set_page_config(page_title="Calendario Maestro de Pagos", page_icon="🗓️", layout="wide")

auth = utils.authenticate()

if auth["role"] == "branch":
    # La sucursal solo registra facturas: una sola página y sin menú lateral,
    # así no ve los nombres de las demás secciones.
    pages = [
        st.Page("pages/1_Nueva_Factura.py", title="Registrar factura", icon="🧾", default=True),
    ]
    nav = st.navigation(pages, position="hidden")
else:
    st.sidebar.success("Acceso de administrador")
    pages = [
        st.Page("pages/0_Resumen.py", title="Resumen", icon="🗓️", default=True),
        st.Page("pages/1_Nueva_Factura.py", title="Nueva Factura", icon="🧾"),
        st.Page("pages/2_Consolidado.py", title="Consolidado", icon="📋"),
        st.Page("pages/3_Canjear_a_Letras.py", title="Canjear a Letras", icon="🔁"),
        st.Page("pages/4_Calendario.py", title="Calendario", icon="📅"),
        st.Page("pages/5_Presupuesto.py", title="Presupuesto", icon="📊"),
        st.Page("pages/6_Configuracion.py", title="Configuración", icon="⚙️"),
    ]
    nav = st.navigation(pages)

nav.run()
