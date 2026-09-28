"""Extrato & Gestão: busca, filtros, edição em lote, exclusão com confirmação e duplicação."""
import streamlit as st

from core import db, ui
from core.utils import TIPOS, formatar_moeda, rotulo_categoria


def render(ctx):
    periodo, aux = ctx["periodo"], ctx["aux"]
    st.header("Extrato & Gestão")
    if periodo is None:
        st.info("Escolha os meses no filtro da barra lateral.")
        return
    st.caption(periodo.rotulo)
    df = db.carregar_transacoes(periodo.inicio, periodo.fim)
    df = df[periodo.mascara(df["data"])] if not df.empty else df
    if df.empty:
        st.info("Nenhum lançamento no período. Adicione em **Lançamentos** ou **Importar extrato**.")
        return
    _tabela(df, aux)
    _duplicar(df)


@st.fragment
def _tabela(df, aux):
    cats, formas = aux["categorias"], aux["formas"]
    c1, c2, c3 = st.columns([2, 1.3, 2])
    busca = c1.text_input("Buscar", placeholder="Descrição, ex.: mercado", key="ext_busca")
    status = c2.segmented_control("Situação", ["Todos", "Pendentes", "Pagos"], default="Todos",
                                  required=True, key="ext_status")
    filtro_cat = c3.multiselect("Categorias", sorted(df["categoria"].unique()), key="ext_cats")

    if busca:
        df = df[df["descricao"].fillna("").str.contains(busca, case=False, regex=False)]
    if status == "Pendentes":
        df = df[~df["pago"]]
    elif status == "Pagos":
        df = df[df["pago"]]
    if filtro_cat:
        df = df[df["categoria"].isin(filtro_cat)]
    if df.empty:
        st.caption("Nenhum lançamento com esses filtros.")
        return

    rec, desp = df.loc[df["tipo"] == "Receita", "valor"].sum(), df.loc[df["tipo"] == "Despesa", "valor"].sum()
    st.caption(f"{len(df)} lançamento(s) · receitas {formatar_moeda(rec)} · despesas {formatar_moeda(desp)}")

    e = df.copy()
    e["data"] = e["data"].dt.date
    e["categoria_rotulo"] = [rotulo_categoria(i, g, n) for i, g, n in zip(e["icone"], e["grupo"], e["categoria"])]
    e.insert(0, "excluir", False)
    e = e[["excluir", "pago", "data", "categoria_rotulo", "descricao", "valor", "tipo", "metodo_pagamento",
           "cartao", "parcela_atual", "parcela_total", "id"]].reset_index(drop=True)

    mapa_cat = {rotulo_categoria(r.icone, r.grupo, r.nome): int(r.id) for r in cats.itertuples()}
    mapa_fp = {r.nome: int(r.id) for r in formas.itertuples()}

    st.data_editor(e, hide_index=True, width="stretch", height=560, key="ext_editor", column_config={
        "id": None,
        "excluir": st.column_config.CheckboxColumn("🗑️", width="small", help="Marque para excluir"),
        "pago": st.column_config.CheckboxColumn("Pago", width="small"),
        "data": st.column_config.DateColumn("Data", format="DD/MM/YYYY"),
        "categoria_rotulo": st.column_config.SelectboxColumn("Categoria", options=sorted(mapa_cat), width="medium"),
        "descricao": st.column_config.TextColumn("Descrição", width="large"),
        "valor": st.column_config.NumberColumn("Valor", format="R$ %.2f", min_value=0.0),
        "tipo": st.column_config.SelectboxColumn("Tipo", options=TIPOS, width="small"),
        "metodo_pagamento": st.column_config.SelectboxColumn("Método", options=sorted(mapa_fp)),
        "cartao": st.column_config.TextColumn("Cartão", disabled=True),
        "parcela_atual": st.column_config.NumberColumn("Parc.", min_value=1, step=1, width="small"),
        "parcela_total": st.column_config.NumberColumn("de", min_value=1, step=1, width="small"),
    })

    alteracoes = st.session_state["ext_editor"]["edited_rows"]
    n_exc = sum(1 for v in alteracoes.values() if v.get("excluir"))
    rotulo = "💾 Salvar alterações" + (f" e excluir {n_exc}" if n_exc else "")
    if st.button(rotulo, type="primary", disabled=not alteracoes):
        exc, upd, nomes = [], {}, []
        for i, v in alteracoes.items():
            linha = e.iloc[int(i)]
            rid = int(linha["id"])
            if v.get("excluir"):
                exc.append(rid)
                nomes.append(f"{linha['data']:%d/%m/%Y} · {linha['descricao']} · {formatar_moeda(linha['valor'])}")
                continue
            campos = {k: v[k] for k in ("pago", "valor", "data", "descricao", "tipo", "parcela_atual",
                                         "parcela_total") if k in v}
            if "categoria_rotulo" in v:
                campos["categoria_id"] = mapa_cat.get(v["categoria_rotulo"])
            if "metodo_pagamento" in v:
                campos["forma_pagamento_id"] = mapa_fp.get(v["metodo_pagamento"])
            if campos:
                upd[rid] = campos

        msg = f"{len(upd)} alterado(s), {len(exc)} excluído(s)."
        if exc:
            ui.pedir_exclusao("Excluir lançamentos?", nomes, "transacoes", upd, exc, msg)
        else:
            db.atualizar("transacoes", upd)
            ui.concluir(msg)


def _duplicar(df):
    with st.expander("🔄 Repetir um lançamento nos próximos meses"):
        opcoes = {int(r.id): f"{r.data:%d/%m/%Y} · {r.categoria} · {r.descricao} · {formatar_moeda(r.valor)}"
                  for r in df.itertuples()}
        c1, c2, c3 = st.columns([4, 1, 1], vertical_alignment="bottom")
        escolhido = c1.selectbox("Lançamento", list(opcoes), format_func=opcoes.get)
        qtd = c2.number_input("Meses", 1, 36, 1)
        if c3.button("Repetir", width="stretch"):
            n = db.replicar_lancamento(escolhido, qtd)
            ui.concluir(f"{n} lançamento(s) criado(s).")
        st.caption("Para contas que se repetem sempre, use **Recorrências**: elas são criadas automaticamente.")
