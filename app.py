"""Finanças Pessoais — ponto de entrada. Rode com: streamlit run app.py"""
import logging
from datetime import date

import streamlit as st

st.set_page_config(page_title="Finanças Pessoais", page_icon="💰", layout="wide")

from core import auth, db, ui  # noqa: E402
from views import (categorias, configuracoes, dashboard, extrato, importar, lancamentos,  # noqa: E402
                   recorrencias, relatorio)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("financas")

# página -> (função, filtro exibido na barra lateral)
PAGINAS = {
    "📊 Dashboard": (dashboard.render, "periodo"),
    "📅 Relatório anual": (relatorio.render, "ano"),
    "📋 Extrato & Gestão": (extrato.render, "periodo"),
    "➕ Lançamentos": (lancamentos.render, None),
    "📥 Importar extrato": (importar.render, None),
    "🔁 Recorrências": (recorrencias.render, None),
    "🏷️ Categorias": (categorias.render, None),
    "⚙️ Configurações": (configuracoes.render, None),
}

ui.aplicar_estilo()

try:
    db.get_engine()
    db.aplicar_migracoes()
except Exception as e:
    log.exception("Falha ao iniciar o banco")
    st.error(f"Falha na conexão com o banco: {e}")
    st.stop()

cm = auth.cookie_manager()
if not auth.check_password(cm):
    st.stop()

ui.mostrar_avisos()

if not st.session_state.get("recorrencias_verificadas"):
    try:
        n = db.gerar_recorrencias()
        if n:
            st.toast(f"{n} lançamento(s) recorrente(s) criado(s) para este mês.", icon="🔁")
    except Exception:
        log.exception("Falha ao gerar recorrências")
    st.session_state["recorrencias_verificadas"] = True

if "page_request" in st.session_state:
    st.session_state["nav_menu"] = st.session_state.pop("page_request")

ctx = {"periodo": None, "ano": date.today().year}
with st.sidebar:
    st.markdown("### 💰 Finanças")
    st.caption(f"👤 {st.secrets['admin_user']}")
    menu = st.radio("Menu", list(PAGINAS), key="nav_menu", label_visibility="collapsed")
    filtro = PAGINAS[menu][1]
    if filtro == "periodo":
        st.divider()
        ctx["periodo"] = ui.filtro_periodo()
    elif filtro == "ano":
        st.divider()
        ctx["ano"] = st.number_input("Ano", 2015, 2100, date.today().year, key="filtro_ano")
    st.divider()
    if st.button("Sair", width="stretch"):
        auth.logout(cm)
        st.rerun()

ctx["aux"] = db.carregar_auxiliares()
ui.dialogo_pendente()

try:
    PAGINAS[menu][0](ctx)
except Exception as e:
    log.exception("Erro na página %s", menu)
    st.error(f"Algo deu errado nesta página: {e}")
