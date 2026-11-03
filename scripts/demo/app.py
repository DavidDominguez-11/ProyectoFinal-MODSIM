"""Demo en vivo: incendio del Camp Fire + evacuación, organizado por concepto de la materia.

    .venv/Scripts/streamlit run scripts/demo/app.py

Enlaces directos: ?p=<sección 0-3>&sub=<subvista 0-3>
"""
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.demo import datos as D  # noqa: E402

st.set_page_config(page_title='Camp Fire: fuego y evacuación', page_icon='🔥', layout='wide')

from scripts.demo import c_agentes, c_des, c_grid, c_red  # noqa: E402
from scripts.demo.ui import static  # noqa: E402

NAV = ['🟩 1 · Grillas, autómatas y SIG', '🟦 2 · Redes: grafo vial dirigido',
       '🟧 3 · DES: entidades, recursos y colas', '🟪 4 · Agentes y corridas múltiples']
KEYS = ['grid', 'net', 'des', 'agent']

S = static()
runs = D.available_runs()

st.sidebar.title('🔥 Camp Fire\nFuego + evacuación')
st.sidebar.caption('Modelación y Simulación. Los parámetros de evacuación (alertas, capacidades, velocidades) '
                   'son **supuestos hipotéticos**, no datos históricos.')
qp = st.query_params
if 'nav' not in st.session_state and qp.get('p', '').isdigit() and int(qp['p']) < len(NAV):
    st.session_state['nav'] = NAV[int(qp['p'])]
    if qp.get('sub', '').isdigit():
        st.session_state['lz_' + KEYS[int(qp['p'])]] = '__sub__' + qp['sub']
page = st.sidebar.radio('Concepto', NAV, key='nav', label_visibility='collapsed')

if page == NAV[0]:
    c_grid.render(S)
elif page == NAV[1]:
    c_red.render(S)
elif page == NAV[2]:
    c_des.render(S, runs)
else:
    c_agentes.render(S, runs)
