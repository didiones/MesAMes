"""Dashboard: cards com comparação, indicadores, alertas, baixa rápida e análises em abas."""
from datetime import date

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from core import db, ui
from core import indicadores as ind
from core.utils import (COR_PREVISTO, CORES_TIPO, MAPA_MESES_ABREV, add_months, formatar_moeda,
                        formatar_pct, mes_ano, primeiro_dia)


def render(ctx):
    periodo, aux = ctx["periodo"], ctx["aux"]
    cats = aux["categorias"]
    st.header("Visão geral")
    if periodo is None:
        st.info("Escolha os meses no filtro da barra lateral.")
        return
    st.caption(periodo.rotulo)

    hoje = date.today()
    ini = min(add_months(periodo.inicio, -12), date(periodo.ano_ref, 1, 1))
    fim = max(date(periodo.ano_ref + 1, 1, 1), add_months(primeiro_dia(hoje), 13), periodo.fim)
    df = db.carregar_transacoes(ini, fim)
    if df.empty:
        st.info("Nenhum lançamento ainda. Comece em **Lançamentos** ou traga seu extrato em **Importar extrato**.")
        return

    df_p = df[periodo.mascara(df["data"])]
    anterior = periodo.anterior()
    r, ra = ind.resumo(df_p), ind.resumo(df[anterior.mascara(df["data"])])
    ultimo = date(*periodo.meses[-1], 1)
    meses6 = [(d.year, d.month) for d in (add_months(ultimo, -i) for i in range(5, -1, -1))]
    cores = {row.nome: row.cor for row in cats.itertuples() if isinstance(row.cor, str) and row.cor}

    _cards(r, ra, df, df_p, meses6)
    _alertas(df, df_p, periodo, cats)
    _indicadores(df, df_p, periodo, r, hoje)
    _baixa_rapida(df_p)

    st.divider()
    abas = st.tabs(["Categorias", "Orçamentos", "Fixas e 50/30/20", "Mapa de gastos",
                    "Faturas", "Parcelas futuras", "Evolução"])
    with abas[0]:
        _por_categoria(df_p, cores)
    with abas[1]:
        _orcamentos(df_p, cats, periodo)
    with abas[2]:
        _fixas_503020(df_p, cats)
    with abas[3]:
        _mapa(df_p, cores)
    with abas[4]:
        _faturas(df, periodo)
    with abas[5]:
        _parcelas(df, r, hoje)
    with abas[6]:
        _evolucao(df, periodo, ultimo)


# ------------------------------------------------------------------ cards
def _cards(r, ra, df, df_p, meses6):
    c = st.columns(4)
    ui.card(c[0], "📥 Receitas", r["receita"], ui.texto_delta(ind.variacao(r["receita"], ra["receita"])),
            ajuda=f"Inclui receitas previstas. Já recebido: {formatar_moeda(r['receita_real'])}.",
            serie=ind.serie_mensal(df, meses6, "Receita"))
    ui.card(c[1], "📤 Despesas", r["despesa"], ui.texto_delta(ind.variacao(r["despesa"], ra["despesa"])),
            inverso=True, ajuda=f"Pagas: {formatar_moeda(r['despesa_paga'])} · a pagar: "
                                f"{formatar_moeda(r['despesa_aberta'])}.",
            serie=ind.serie_mensal(df, meses6, "Despesa"))
    abertas = df_p[(df_p["tipo"] == "Despesa") & ~df_p["pago"]]
    vencidas = abertas[abertas["data"] < pd.Timestamp(date.today())]
    ui.card(c[2], "🗓️ A pagar", r["despesa_aberta"],
            f"{len(vencidas)} vencida(s)" if len(vencidas) else None, neutro=True, descricao=None,
            ajuda="Despesas do período ainda não pagas.")
    ui.card(c[3], "📈 Investimentos", r["invest"], ui.texto_delta(ind.variacao(r["invest"], ra["invest"])),
            serie=ind.serie_mensal(df, meses6, "Investimento"))

    c = st.columns(3)
    ui.card(c[0], "💵 Saldo realizado", r["saldo_real"],
            ui.texto_delta(ind.variacao(r["saldo_real"], ra["saldo_real"])),
            ajuda="Recebido − despesas pagas − investimentos realizados. É o que de fato ficou no caixa.")
    ui.card(c[1], "🔮 Saldo projetado", r["saldo_proj"],
            ui.texto_delta(ind.variacao(r["saldo_proj"], ra["saldo_proj"])),
            ajuda="Considera também as receitas e despesas previstas até o fim do período.")
    tp, tpa = r["taxa_poupanca"], ra["taxa_poupanca"]
    ui.card(c[2], "🐷 Taxa de poupança", formatar_pct(tp), moeda=False,
            delta=ui.texto_delta(tp - tpa, pontos=True) if tp is not None and tpa is not None else None,
            ajuda="(Receitas − despesas) ÷ receitas. Acima de 20% é considerado saudável.")


def _alertas(df, df_p, periodo, cats):
    msgs = []
    orc = ind.orcamentos(df_p, cats, periodo.n_meses)
    if not orc.empty:
        for row in orc[orc["pct"] >= 0.9].itertuples():
            estado = "estourou" if row.pct > 1 else "está perto do limite de"
            msgs.append(f"**{row.nome}** {estado} o orçamento: {formatar_moeda(row.gasto)} de "
                        f"{formatar_moeda(row.limite)} ({formatar_pct(row.pct, 0)}).")
    anom = ind.alertas(df, periodo)
    for cat, row in anom.head(3).iterrows():
        msgs.append(f"**{cat}** está {formatar_pct(row.acima, 0)} acima da sua média mensal "
                    f"({formatar_moeda(row.atual)} contra {formatar_moeda(row.media)}).")
    if msgs:
        st.warning("\n".join(f"- {m}" for m in msgs), icon="⚠️")


def _indicadores(df, df_p, periodo, r, hoje):
    st.subheader("Indicadores")
    c = st.columns(4)
    if periodo.contem_hoje():
        p = ind.projecao_mes(df, hoje)
        ui.card(c[0], "🧭 Projeção de despesas do mês", p["projetado"],
                f"{formatar_moeda(p['variaveis_ate_hoje'] + p['fixas'])} até hoje", neutro=True, descricao=None,
                ajuda=f"Despesas fixas do mês ({formatar_moeda(p['fixas'])}) + variáveis no ritmo atual "
                      f"(dia {p['dia']} de {p['dias_mes']}).")
    else:
        media = ind.media_mensal(df, "Despesa", periodo.inicio)
        ui.card(c[0], "📊 Média mensal de despesas", media, "6 meses anteriores", neutro=True, descricao=None)

    media_desp = ind.media_mensal(df, "Despesa", hoje)
    acumulado = db.investimento_acumulado(hoje)
    meses_reserva = acumulado / media_desp if media_desp else None
    ui.card(c[1], "🛟 Reserva de emergência",
            f"{meses_reserva:.1f} meses".replace(".", ",") if meses_reserva is not None else "—", moeda=False,
            delta=formatar_moeda(acumulado) + " investidos", neutro=True, descricao=None,
            ajuda="Total investido ÷ despesa média dos últimos 6 meses. O recomendado é de 6 a 12 meses.")

    por_mes, _ = ind.parcelas_futuras(df, hoje)
    prox = float(por_mes.loc[por_mes["mes"] == pd.Timestamp(add_months(primeiro_dia(hoje), 1)), "valor"].sum()) \
        if not por_mes.empty else 0.0
    renda = ind.media_mensal(df, "Receita", hoje) or r["receita"]
    ui.card(c[2], "💳 Parcelas do próximo mês", prox,
            f"{formatar_pct(prox / renda, 0)} da renda média" if renda else None, neutro=True, descricao=None,
            ajuda="Soma das parcelas em aberto com vencimento no mês que vem.")

    fixas, variaveis = ind.fixas_variaveis(df_p)
    total = fixas + variaveis
    ui.card(c[3], "📌 Despesas fixas", formatar_pct(fixas / total, 0) if total else "—", moeda=False,
            delta=f"{formatar_moeda(fixas)} no período" if total else None, neutro=True, descricao=None,
            ajuda="Parte das despesas marcada como fixa nas categorias (aluguel, escola, assinaturas…).")


@st.fragment
def _baixa_rapida(df_p):
    abertas = df_p[(df_p["tipo"] == "Despesa") & ~df_p["pago"]].sort_values("data")
    if abertas.empty:
        return
    st.divider()
    st.subheader("⚠️ Contas a pagar")
    hoje = pd.Timestamp(date.today())
    v = abertas[["id", "data", "descricao", "categoria", "valor"]].copy()
    v.insert(1, "Situação", np.select([v["data"] < hoje, v["data"] == hoje], ["🔴 Vencida", "🟡 Hoje"], "⚪ A vencer"))
    v["data"] = v["data"].dt.date
    v.insert(0, "Pagar", False)
    ed = st.data_editor(
        v, key="baixa_rapida", hide_index=True, width="stretch",
        column_config={"id": None, "Pagar": st.column_config.CheckboxColumn(width="small"),
                       "data": st.column_config.DateColumn("Vencimento", format="DD/MM/YYYY"),
                       "descricao": st.column_config.TextColumn("Descrição", width="large"),
                       "categoria": "Categoria",
                       "valor": st.column_config.NumberColumn("Valor", format="R$ %.2f")},
        disabled=["Situação", "data", "descricao", "categoria", "valor"])
    sel = ed[ed["Pagar"]]
    if st.button(f"✅ Marcar {len(sel)} como paga(s) · {formatar_moeda(sel['valor'].sum())}" if len(sel)
                 else "✅ Marcar como pagas", type="primary", disabled=sel.empty):
        n = db.marcar_pagas(sel["id"].tolist())
        ui.concluir(f"{n} conta(s) marcada(s) como paga(s).")


# ------------------------------------------------------------------ abas
def _barras_categoria(d, cores):
    g = d.groupby("categoria")["valor"].sum().sort_values().reset_index()
    g["pct"] = g["valor"] / g["valor"].sum()
    g["rotulo"] = g["valor"].map(formatar_moeda)
    fig = px.bar(g, x="valor", y="categoria", orientation="h", text="rotulo", color="categoria",
                 color_discrete_map=cores or None, custom_data=["rotulo", "pct"])
    fig.update_traces(textposition="outside", cliponaxis=False,
                      hovertemplate="<b>%{y}</b><br>%{customdata[0]}<br>%{customdata[1]:.1%} do total<extra></extra>")
    ui.estilizar(fig, "x", altura=max(260, 34 * len(g) + 60), legenda=False)
    fig.update_xaxes(visible=False)
    fig.update_layout(margin=dict(r=110))
    ui.grafico(fig)


def _por_categoria(df_p, cores):
    c1, c2 = st.columns(2)
    for col, tipo in ((c1, "Receita"), (c2, "Despesa")):
        with col:
            st.markdown(f"**{tipo}s**")
            d = df_p[df_p["tipo"] == tipo]
            if d.empty:
                st.caption(f"Sem {tipo.lower()}s no período.")
            else:
                _barras_categoria(d, cores)


def _orcamentos(df_p, cats, periodo):
    orc = ind.orcamentos(df_p, cats, periodo.n_meses)
    if orc.empty:
        st.info("Nenhum orçamento definido. Informe um limite mensal nas categorias de despesa em **Categorias**.")
        return
    tot_g, tot_l = orc["gasto"].sum(), orc["limite"].sum()
    st.metric("Total orçado no período", formatar_moeda(tot_l),
              delta=f"{formatar_moeda(tot_g)} gastos ({formatar_pct(tot_g / tot_l, 0)})",
              delta_color="inverse" if tot_g > tot_l else "off", delta_arrow="off")
    for row in orc.itertuples():
        marca = "🔴" if row.pct > 1 else ("🟡" if row.pct >= 0.9 else "🟢")
        falta = (f"faltam {formatar_moeda(row.restante)}" if row.restante >= 0
                 else f"passou {formatar_moeda(-row.restante)}")
        st.progress(min(float(row.pct), 1.0),
                    text=f"{marca} **{row.nome}** — {formatar_moeda(row.gasto)} de {formatar_moeda(row.limite)} "
                         f"({formatar_pct(row.pct, 0)}, {falta})")
    if periodo.n_meses > 1:
        st.caption(f"Limites multiplicados por {periodo.n_meses} meses do período.")


def _fixas_503020(df_p, cats):
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Fixas × variáveis**")
        fixas, variaveis = ind.fixas_variaveis(df_p)
        if fixas + variaveis == 0:
            st.caption("Sem despesas no período.")
        else:
            fig = go.Figure(go.Pie(labels=["Fixas", "Variáveis"], values=[fixas, variaveis], hole=0.6,
                                   marker_colors=["#4A8FD4", "#E0A458"], sort=False,
                                   hovertemplate="%{label}: R$ %{value:,.2f} (%{percent})<extra></extra>"))
            ui.grafico(ui.estilizar(fig, None, altura=300))
            st.caption("Marque as categorias fixas em **Categorias** para refinar esse número.")
    with c2:
        st.markdown("**Regra 50/30/20**")
        regra = ind.regra_503020(df_p, cats)
        if not regra:
            st.caption("Precisa de receitas no período para calcular.")
        else:
            nomes = ["Necessidades", "Desejos", "Poupança"]
            fig = go.Figure([
                go.Bar(name="Você", x=nomes, y=[regra[n] for n in nomes], marker_color="#3FA37E",
                       text=[formatar_pct(regra[n], 0) for n in nomes], textposition="outside"),
                go.Bar(name="Referência", x=nomes, y=[0.5, 0.3, 0.2], marker_color="rgba(150,150,150,0.45)"),
            ])
            ui.estilizar(fig, None, altura=300)
            fig.update_yaxes(tickformat=".0%", title=None)
            fig.update_layout(barmode="group")
            ui.grafico(fig)
            st.caption("Necessidade ou desejo é definido em cada categoria de despesa.")


def _mapa(df_p, cores):
    d = df_p[df_p["tipo"] == "Despesa"]
    if d.empty:
        st.caption("Sem despesas no período.")
        return
    g = d.groupby(["grupo", "categoria"], as_index=False)["valor"].sum()
    fig = px.treemap(g, path=["grupo", "categoria"], values="valor", color="categoria",
                     color_discrete_map=cores or None)
    fig.update_traces(texttemplate="<b>%{label}</b><br>R$ %{value:,.2f}<br>%{percentRoot:.1%}",
                      hovertemplate="<b>%{label}</b><br>R$ %{value:,.2f}<br>%{percentRoot:.1%} do total<extra></extra>")
    ui.grafico(ui.estilizar(fig, None, altura=460))


@st.fragment
def _faturas(df, periodo):
    f = ind.faturas(df)
    if f.empty:
        st.info("Cadastre seus cartões em **Configurações** e escolha o cartão ao lançar uma compra "
                "para acompanhar as faturas aqui.")
        return
    lim_ini, lim_fim = pd.Timestamp(periodo.inicio), pd.Timestamp(add_months(periodo.fim, 2))
    f = f[(f["mes"] >= lim_ini) & (f["mes"] < lim_fim)]
    if f.empty:
        st.caption("Nenhuma fatura no período.")
        return
    v = f.assign(Mês=f["mes"].map(mes_ano), Vencimento=f["vencimento"].dt.date)
    st.dataframe(v[["cartao", "Mês", "Vencimento", "total", "itens", "status"]], hide_index=True, width="stretch",
                 column_config={"cartao": "Cartão", "total": st.column_config.NumberColumn("Total", format="R$ %.2f"),
                                "itens": "Lançamentos", "status": "Situação"})
    abertas = f[f["status"] == "Em aberto"].reset_index(drop=True)
    if not abertas.empty:
        c1, c2 = st.columns([3, 1], vertical_alignment="bottom")
        i = c1.selectbox("Fatura", abertas.index,
                         format_func=lambda i: f"{abertas.at[i, 'cartao']} · {mes_ano(abertas.at[i, 'mes'])} · "
                                               f"{formatar_moeda(abertas.at[i, 'total'])}")
        if c2.button("Pagar fatura", type="primary", width="stretch"):
            n = db.marcar_pagas(abertas.at[i, "ids"])
            ui.concluir(f"Fatura paga ({n} lançamentos).")


def _parcelas(df, r, hoje):
    por_mes, lista = ind.parcelas_futuras(df, hoje)
    if por_mes.empty:
        st.info("Nenhuma parcela em aberto. 🎉")
        return
    renda = ind.media_mensal(df, "Receita", hoje) or r["receita"]
    por_mes["Mês"] = por_mes["mes"].map(mes_ano)
    por_mes["pct"] = por_mes["valor"] / renda if renda else 0
    fig = px.bar(por_mes, x="Mês", y="valor", custom_data=["pct"], color_discrete_sequence=["#E0A458"])
    fig.update_traces(hovertemplate="%{x}: R$ %{y:,.2f}<br>%{customdata[0]:.0%} da renda média<extra></extra>")
    ui.grafico(ui.estilizar(fig, "y", altura=300, legenda=False))
    st.caption(f"Total ainda a pagar em parcelas: **{formatar_moeda(lista['total_restante'].sum())}**.")
    lista = lista.assign(termina=lista["termina"].map(mes_ano))
    st.dataframe(lista, hide_index=True, width="stretch", column_config={
        "compra": "Compra", "cartao": "Cartão", "parcela_total": "Parcelas",
        "valor_parcela": st.column_config.NumberColumn("Parcela", format="R$ %.2f"),
        "restantes": "Faltam", "total_restante": st.column_config.NumberColumn("Restante", format="R$ %.2f"),
        "termina": "Última em"})


def _evolucao(df, periodo, ultimo):
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Últimos 12 meses**")
        ini = pd.Timestamp(add_months(ultimo, -11))
        d = df[(df["data"] >= ini) & (df["data"] < pd.Timestamp(add_months(ultimo, 1)))]
        if d.empty:
            st.caption("Sem dados.")
        else:
            g = d.groupby([d["data"].dt.to_period("M").dt.to_timestamp(), "tipo"])["valor"].sum().unstack(fill_value=0)
            fig = go.Figure()
            for tipo in ["Receita", "Despesa", "Investimento"]:
                if tipo in g:
                    fig.add_scatter(x=g.index, y=g[tipo], name=tipo, mode="lines+markers",
                                    line=dict(color=CORES_TIPO[tipo], width=2.5))
            saldo = g.get("Receita", 0) - g.get("Despesa", 0) - g.get("Investimento", 0)
            fig.add_bar(x=g.index, y=saldo, name="Saldo", marker_color="rgba(150,150,150,0.35)")
            fig.update_xaxes(tickformat="%b/%y")
            ui.grafico(ui.estilizar(fig, "y", altura=340))
    with c2:
        ano = periodo.ano_ref
        st.markdown(f"**Fluxo de caixa {ano}: realizado × previsto**")
        d = df[df["data"].dt.year == ano]
        d = d[d["tipo"].isin(["Receita", "Despesa"])]
        if d.empty:
            st.caption("Sem dados.")
        else:
            g = d.groupby([d["data"].dt.month, "tipo", "pago"])["valor"].sum().reset_index()
            fig = go.Figure()
            meses = [MAPA_MESES_ABREV[m] for m in range(1, 13)]
            for tipo in ["Receita", "Despesa"]:
                serie = {p: g[(g["tipo"] == tipo) & (g["pago"] == p)].set_index("data")["valor"]
                         .reindex(range(1, 13), fill_value=0).values for p in (True, False)}
                # realizado embaixo e previsto empilhado em cima, lado a lado por tipo
                fig.add_bar(x=meses, y=serie[True], name=f"{tipo} realizada", offsetgroup=tipo,
                            marker_color=CORES_TIPO[tipo])
                fig.add_bar(x=meses, y=serie[False], base=serie[True], name=f"{tipo} prevista",
                            offsetgroup=tipo, marker_color=COR_PREVISTO[tipo])
            fig.update_layout(barmode="group")
            ui.grafico(ui.estilizar(fig, "y", altura=340))
