"""Componentes visuais reutilizáveis."""
from __future__ import annotations

from datetime import date

import streamlit as st

from core.utils import MAPA_MESES_ABREV, add_months, formatar_moeda, periodo_de_meses, ultimos_meses

ATALHOS = ["Este mês", "Mês anterior", "3 meses", "Este ano", "Escolher"]

CSS = """
<style>
/* números tabulares: valores alinham melhor em cards e tabelas */
[data-testid="stMetricValue"], [data-testid="stDataFrame"] { font-variant-numeric: tabular-nums; }
section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] h3 { margin-bottom: 0; }
</style>
"""


def aplicar_estilo():
    st.markdown(CSS, unsafe_allow_html=True)


# ------------------------------------------------------------------ filtros
def filtro_periodo(key: str = "periodo"):
    """Atalhos de período + seleção livre de meses. Retorna Periodo ou None."""
    hoje = date.today()
    atalho = st.segmented_control("Período", ATALHOS, default="Este mês", required=True, key=f"{key}_atalho")
    if atalho == "Este mês":
        return ultimos_meses(1)
    if atalho == "Mês anterior":
        return ultimos_meses(1, add_months(hoje, -1))
    if atalho == "3 meses":
        return ultimos_meses(3)
    if atalho == "Este ano":
        return periodo_de_meses((hoje.year, m) for m in range(1, 13))
    ano = st.number_input("Ano", 2015, 2100, hoje.year, key=f"{key}_ano")
    meses = st.pills("Meses", list(range(1, 13)), selection_mode="multi",
                     default=[hoje.month] if ano == hoje.year else [1],
                     format_func=lambda m: MAPA_MESES_ABREV[m], key=f"{key}_meses_{ano}")
    if not meses:
        st.caption("Escolha pelo menos um mês.")
        return None
    return periodo_de_meses((ano, m) for m in meses)


# ------------------------------------------------------------------ gráficos
def estilizar(fig, eixo_moeda: str | None = "y", altura: int | None = None, legenda: bool = True):
    """Padrão brasileiro nos números (1.234,56), margens enxutas e legenda horizontal."""
    fig.update_layout(separators=",.", margin=dict(l=8, r=8, t=24, b=8), showlegend=legenda,
                      legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, title=None),
                      hoverlabel=dict(namelength=-1))
    if altura:
        fig.update_layout(height=altura)
    if eixo_moeda == "y":
        fig.update_yaxes(tickprefix="R$ ", tickformat=",.0f", title=None)
        fig.update_xaxes(title=None)
    elif eixo_moeda == "x":
        fig.update_xaxes(tickprefix="R$ ", tickformat=",.0f", title=None)
        fig.update_yaxes(title=None)
    return fig


def grafico(fig, **kw):
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False}, **kw)


# ------------------------------------------------------------------ cards
def texto_delta(frac, pontos=False):
    """Variação formatada: '+12%' ou, para taxas, '+1,5 p.p.'."""
    if frac is None:
        return None
    if pontos:
        return f"{frac * 100:+.1f} p.p.".replace(".", ",")
    return f"{frac * 100:+.0f}%"


def card(col, rotulo, valor, delta=None, inverso=False, ajuda=None, serie=None, moeda=True,
         descricao="vs período anterior", neutro=False):
    """Card de indicador. `neutro=True` mostra o delta como informação, sem seta nem cor."""
    col.metric(
        rotulo, formatar_moeda(valor) if moeda else valor,
        delta=delta, delta_description=descricao if delta else None,
        delta_color="off" if neutro else ("inverse" if inverso else "normal"),
        delta_arrow="off" if neutro else "auto",
        help=ajuda, border=True,
        chart_data=serie if serie and any(serie) else None, chart_type="bar",
    )


def pedir_exclusao(titulo: str, itens: list[str], tabela: str, edicoes: dict, exclusoes: list[int], msg: str):
    """Guarda a operação e abre o diálogo de confirmação no próximo ciclo (ver `dialogo_pendente`)."""
    st.session_state["_exclusao_pendente"] = {"titulo": titulo, "itens": itens, "tabela": tabela,
                                              "edicoes": edicoes, "exclusoes": exclusoes, "msg": msg}
    st.rerun()


def _cancelar_pendente():
    st.session_state.pop("_exclusao_pendente", None)


def dialogo_pendente():
    """Chamado em toda execução do app: mostra a confirmação se houver exclusão aguardando."""
    p = st.session_state.get("_exclusao_pendente")
    if not p:
        return

    @st.dialog(p["titulo"], on_dismiss=_cancelar_pendente)
    def _dialogo():
        itens = p["itens"]
        st.write("Estes itens serão excluídos definitivamente:" if len(itens) > 1
                 else "Este item será excluído definitivamente:")
        for i in itens[:15]:
            st.markdown(f"- {i}")
        if len(itens) > 15:
            st.caption(f"… e mais {len(itens) - 15}.")
        c1, c2 = st.columns(2)
        if c1.button("Excluir", type="primary", width="stretch"):
            from core import db
            db.atualizar(p["tabela"], p["edicoes"], p["exclusoes"])
            _cancelar_pendente()
            concluir(p["msg"])
        if c2.button("Cancelar", width="stretch"):
            _cancelar_pendente()
            st.rerun()

    _dialogo()


# ------------------------------------------------------------------ avisos que sobrevivem ao st.rerun()
def avisar(msg: str, icone: str = "✅"):
    st.session_state.setdefault("_avisos", []).append((msg, icone))


def mostrar_avisos():
    for msg, icone in st.session_state.pop("_avisos", []):
        st.toast(msg, icon=icone)


def concluir(msg: str, icone: str = "✅"):
    """Registra o aviso e recarrega a página (substitui o antigo toast + time.sleep + rerun)."""
    avisar(msg, icone)
    st.rerun()
