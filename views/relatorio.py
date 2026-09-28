"""Relatório anual: tabelas mês a mês por categoria, resumo, taxa de poupança e exportação Excel."""
import io
from datetime import date

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import db, ui
from core import indicadores as ind
from core.utils import MAPA_MESES, MAPA_MESES_ABREV, formatar_moeda, formatar_pct

COLS_MESES = [MAPA_MESES[i] for i in range(1, 13)]


def _pivot(df, tipo):
    d = df[df["tipo"] == tipo]
    if d.empty:
        return None, None
    tab = d.pivot_table(index="categoria", columns="mes", values="valor", aggfunc="sum", fill_value=0)
    tab = tab.reindex(columns=range(1, 13), fill_value=0)
    tab.columns = COLS_MESES
    pagos = d[d["pago"]].pivot_table(index="categoria", columns="mes", values="valor", aggfunc="sum", fill_value=0)
    pagos = pagos.reindex(index=tab.index, columns=range(1, 13), fill_value=0)
    pagos.columns = COLS_MESES
    tab["TOTAL"] = tab.sum(axis=1)
    total = pd.DataFrame(tab.sum(axis=0)).T
    total.index = ["TOTAL"]
    return pd.concat([tab, total]), pagos


def _estilo(tab, pagos):
    def cor(row):
        out = []
        for c in row.index:
            if c == "TOTAL" or row.name == "TOTAL":
                out.append("font-weight: 600")
                continue
            v, p = row[c], pagos.at[row.name, c] if row.name in pagos.index else 0.0
            out.append("opacity: 0.45" if v == 0 else ("color: #3FA37E" if p >= v - 0.01 else "color: #E0A458"))
        return out
    return tab.style.apply(cor, axis=1).format(formatar_moeda)


@st.cache_data(show_spinner=False)
def _excel(tabelas: dict) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf) as w:
        for nome, t in tabelas.items():
            if t is not None:
                t.to_excel(w, sheet_name=nome)
    return buf.getvalue()


def render(ctx):
    ano = ctx["ano"]
    st.header(f"Relatório {ano}")
    df = db.carregar_transacoes(date(ano, 1, 1), date(ano + 1, 1, 1))
    if df.empty:
        st.info(f"Sem lançamentos em {ano}.")
        return
    df["mes"] = df["data"].dt.month
    r = ind.resumo(df)

    c = st.columns(5)
    ui.card(c[0], "Receitas", r["receita"], descricao=None)
    ui.card(c[1], "Despesas", r["despesa"], descricao=None)
    ui.card(c[2], "Investimentos", r["invest"], descricao=None)
    ui.card(c[3], "Saldo", r["saldo_proj"], descricao=None)
    ui.card(c[4], "Taxa de poupança", formatar_pct(r["taxa_poupanca"]), moeda=False, descricao=None)

    desp = df[df["tipo"] == "Despesa"]
    if not desp.empty:
        top = desp.groupby("categoria")["valor"].sum().sort_values(ascending=False)
        st.info(f"Sua maior despesa do ano foi **{top.index[0]}**: {formatar_moeda(top.iloc[0])} "
                f"({formatar_pct(top.iloc[0] / top.sum())} de todas as despesas).", icon="💡")

    rec, p_rec = _pivot(df, "Receita")
    des, p_des = _pivot(df, "Despesa")
    inv, p_inv = _pivot(df, "Investimento")
    zero = pd.Series(0.0, index=COLS_MESES + ["TOTAL"])
    s_r, s_d, s_i = [(t.loc["TOTAL"] if t is not None else zero) for t in (rec, des, inv)]
    caixa = pd.DataFrame([s_r, s_d, s_i, s_r - s_d - s_i], index=["Receitas", "Despesas", "Investimentos", "Saldo"])

    st.download_button("📥 Baixar relatório (Excel)",
                       _excel({"Receitas": rec, "Despesas": des, "Investimentos": inv, "Resumo": caixa}),
                       f"relatorio_{ano}.xlsx",
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    st.subheader("Resumo")
    st.dataframe(caixa.style.format(formatar_moeda).apply(
        lambda s: ["color: #D9534F; font-weight:600" if v < 0 else "color: #3FA37E; font-weight:600" for v in s]
        if s.name == "Saldo" else [""] * len(s), axis=1), width="stretch")

    taxa = ((s_r - s_d) / s_r.where(s_r > 0))[COLS_MESES]
    fig = go.Figure(go.Scatter(x=[MAPA_MESES_ABREV[i] for i in range(1, 13)], y=taxa.values, mode="lines+markers",
                               line=dict(color="#3FA37E", width=2.5), name="Taxa de poupança",
                               hovertemplate="%{x}: %{y:.1%}<extra></extra>"))
    fig.add_hline(y=0.2, line_dash="dot", line_color="gray", annotation_text="meta 20%")
    ui.estilizar(fig, None, altura=260, legenda=False)
    fig.update_yaxes(tickformat=".0%")
    st.markdown("**Taxa de poupança por mês**")
    ui.grafico(fig)

    st.caption("🟢 pago/recebido · 🟠 ainda previsto")
    for titulo, tab, pagos in (("Receitas", rec, p_rec), ("Despesas", des, p_des), ("Investimentos", inv, p_inv)):
        st.subheader(titulo)
        if tab is None:
            st.caption(f"Sem {titulo.lower()} em {ano}.")
        else:
            st.dataframe(_estilo(tab, pagos), width="stretch", height=(len(tab) + 1) * 35 + 3)
