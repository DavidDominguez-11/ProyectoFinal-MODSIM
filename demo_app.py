"""Presentación guiada del modelo Camp Fire. Solo lee artefactos locales."""

from pathlib import Path

import streamlit as st

from demo_concepts import agents_page, des_page, grid_page, network_page
from demo_data import load_bundle
from demo_process import load_process


ROOT = Path(__file__).resolve().parent
INPUTS = (
    "data/procesado/grilla_fuego.npz",
    "data/procesado/red_vial.json",
    "salidas/fuego/llegada_replicas.npz",
    "salidas/fuego/contrato.json",
    "config/escenarios_evacuacion.json",
    "config/dominio.json",
    "salidas/evacuacion_final/summary.json",
    "salidas/evacuacion_final/replicas.csv",
    "salidas/demo_proceso.json",
)
PAGES = (
    "1 · Territorio y fuego",
    "2 · Red y rutas",
    "3 · Eventos y colas",
    "4 · Grupos y resultados",
)


def input_signature() -> tuple:
    """Invalidar la lectura verificada si cambia un archivo local."""
    signature = []
    for name in INPUTS:
        path = ROOT / name
        if path.is_file():
            info = path.stat()
            signature.append((info.st_mtime_ns, info.st_size))
        else:
            signature.append(None)
    return tuple(signature)


@st.cache_resource(show_spinner=False)
def verified_data(signature: tuple):
    bundle = load_bundle(ROOT)
    return bundle, load_process(ROOT, bundle)


st.set_page_config(page_title="Camp Fire · presentación MODSIM", page_icon="🔥", layout="wide")
try:
    bundle, process = verified_data(input_signature())
except (ValueError, KeyError, OSError, TypeError) as error:
    st.error(f"No se pueden mostrar artefactos incompatibles: {error}")
    st.stop()

st.sidebar.title("Camp Fire · MODSIM")
page = st.sidebar.radio("Recorrido de la presentación", PAGES)
st.sidebar.caption("Modelo hipotético · 06:25–14:25 · 8 nov 2018")
with st.sidebar.expander("Procedencia y límites"):
    st.write("Fuego y resultados finales: archivos del proyecto. Las rutas detalladas "
             "proceden de una réplica ilustrativa nueva con 36 grupos trazados. Su red vial "
             "regenerada difiere en SHA-256 de la usada en las 120 corridas finales.")
    st.write("Población residencial estimada; alertas, salidas, capacidades y velocidades "
             "de evacuación son supuestos. Exposición potencial no significa lesiones.")
    st.caption("El visor no ejecuta simulaciones al navegar. El reloj parte de la primera "
               "llamada registrada, no de una ignición física comprobada.")

if page == PAGES[0]:
    grid_page(bundle, process)
elif page == PAGES[1]:
    network_page(bundle, process)
elif page == PAGES[2]:
    des_page(bundle, process)
else:
    agents_page(bundle, process)
