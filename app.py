import streamlit as st
import utils

st.set_page_config(page_title="Calendario Maestro de Pagos", page_icon="🗓️", layout="wide")

# Las secciones viven en views/ (no en pages/) a propósito: si la carpeta se
# llama "pages", Streamlit arma solo un menú lateral con TODAS y lo muestra
# incluso en la pantalla de login. Con views/ el único menú es el de abajo,
# que se construye después de autenticar y según el rol.
auth = utils.authenticate()

if auth["role"] == "branch":
    # La sucursal solo registra documentos de compra: una sola página y sin
    # menú lateral, así no ve los nombres de las demás secciones.
    pages = [
        st.Page("views/1_Nueva_Factura.py", title="Registrar documento", icon="🧾", default=True),
    ]
    nav = st.navigation(pages, position="hidden")
else:
    st.sidebar.success("Acceso de administrador")
    pages = [
        st.Page("views/0_Resumen.py", title="Resumen", icon="🗓️", default=True),
        st.Page("views/1_Nueva_Factura.py", title="Registrar documento", icon="🧾"),
        st.Page("views/2_Consolidado.py", title="Consolidado", icon="📋"),
        st.Page("views/3_Canjear_a_Letras.py", title="Canjear a Letras", icon="🔁"),
        st.Page("views/4_Calendario.py", title="Calendario", icon="📅"),
        st.Page("views/5_Presupuesto.py", title="Presupuesto", icon="📊"),
        st.Page("views/7_Gastos.py", title="Gastos", icon="💸"),
        st.Page("views/6_Configuracion.py", title="Configuración", icon="⚙️"),
    ]
    nav = st.navigation(pages)

nav.run()
