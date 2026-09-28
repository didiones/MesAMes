"""Importação de extratos OFX/CSV com categorização automática e detecção de duplicados."""
from datetime import timedelta

import pandas as pd
import streamlit as st

from core import db, importador, ui
from core.utils import formatar_moeda, rotulo_categoria


def render(ctx):
    aux = ctx["aux"]
    cats, formas = aux["categorias"], aux["formas"]
    st.header("Importar extrato")
    st.caption("Envie o arquivo OFX ou CSV exportado do seu banco. As categorias são sugeridas a partir dos "
               "lançamentos que você já fez; revise antes de importar.")

    versao = st.session_state.setdefault("imp_versao", 0)
    arq = st.file_uploader("Arquivo do banco", type=["ofx", "csv", "txt"], key=f"imp_arquivo_{versao}")
    if not arq:
        return
    conteudo = arq.getvalue()

    if arq.name.lower().endswith(".ofx"):
        dados = importador.ler_ofx(conteudo)
    else:
        try:
            bruto = importador.ler_csv_bruto(conteudo)
        except Exception as e:
            st.error(f"Não foi possível ler o CSV: {e}")
            return
        st.dataframe(bruto.head(5), hide_index=True, width="stretch")
        cols = list(bruto.columns)
        adivinha = lambda termos, pad: next((c for c in cols if any(t in c.lower() for t in termos)), pad)  # noqa: E731
        c1, c2, c3 = st.columns(3)
        col_data = c1.selectbox("Coluna da data", cols, index=cols.index(adivinha(["data", "date"], cols[0])))
        col_desc = c2.selectbox("Coluna da descrição", cols,
                                index=cols.index(adivinha(["desc", "hist", "lan", "memo"], cols[min(1, len(cols) - 1)])))
        col_val = c3.selectbox("Coluna do valor", cols, index=cols.index(adivinha(["valor", "value", "amount"], cols[-1])))
        inverter = st.checkbox("No meu arquivo as despesas aparecem como valores positivos",
                               help="Comum em faturas de cartão.")
        dados = importador.montar_csv(bruto, col_data, col_desc, col_val, inverter)

    if dados.empty:
        st.error("Nenhum lançamento encontrado no arquivo.")
        return

    dados = dados[dados["valor"] != 0].copy()
    dados["tipo"] = dados["valor"].map(lambda v: "Despesa" if v < 0 else "Receita")
    categ = importador.Categorizador(db.historico_descricoes())
    rotulos = {int(r.id): rotulo_categoria(r.icone, r.grupo, r.nome) for r in cats.itertuples()}
    dados["categoria"] = [rotulos.get(categ.sugerir(d, t)) for d, t in zip(dados["descricao"], dados["tipo"])]

    existentes = db.carregar_transacoes(dados["data"].min().date() - timedelta(days=1),
                                        dados["data"].max().date() + timedelta(days=1))
    dados["duplicado"] = importador.marcar_duplicados(dados, existentes)
    dados["valor"] = dados["valor"].abs()
    dados["importar"] = ~dados["duplicado"]

    n_dup, n_sug = int(dados["duplicado"].sum()), int(dados["categoria"].notna().sum())
    st.success(f"{len(dados)} lançamento(s) lidos · {n_sug} com categoria sugerida · "
               f"{n_dup} provável(is) duplicado(s) desmarcado(s).")

    c1, c2 = st.columns(2)
    fp_nome = c1.selectbox("Forma de pagamento destes lançamentos", formas["nome"].tolist())
    pago = c2.checkbox("Marcar como pagos", True, help="Lançamentos de extrato normalmente já aconteceram.")

    ed = st.data_editor(
        dados[["importar", "data", "descricao", "valor", "tipo", "categoria", "duplicado"]].reset_index(drop=True),
        hide_index=True, width="stretch", height=480, key="imp_editor",
        column_config={
            "importar": st.column_config.CheckboxColumn("Importar", width="small"),
            "data": st.column_config.DateColumn("Data", format="DD/MM/YYYY"),
            "descricao": st.column_config.TextColumn("Descrição", width="large"),
            "valor": st.column_config.NumberColumn("Valor", format="R$ %.2f"),
            "tipo": st.column_config.SelectboxColumn("Tipo", options=["Despesa", "Receita", "Investimento"]),
            "categoria": st.column_config.SelectboxColumn("Categoria", options=sorted(rotulos.values()), width="medium"),
            "duplicado": st.column_config.CheckboxColumn("Já existe?", disabled=True),
        })

    sel = ed[ed["importar"]]
    sem_cat = int(sel["categoria"].isna().sum())
    if sem_cat:
        st.warning(f"{sem_cat} lançamento(s) marcados estão sem categoria. Escolha uma ou desmarque-os.")
    rotulo_para_id = {v: k for k, v in rotulos.items()}
    total = sel["valor"].sum()
    if st.button(f"📥 Importar {len(sel)} lançamento(s) · {formatar_moeda(total)}", type="primary",
                 disabled=sel.empty or sem_cat > 0):
        fp_id = int(formas.loc[formas["nome"] == fp_nome, "id"].iloc[0])
        linhas = [{"data": pd.Timestamp(r.data).date(), "descricao": r.descricao, "valor": float(r.valor),
                   "tipo": r.tipo, "categoria_id": rotulo_para_id[r.categoria], "pago": pago,
                   "forma_pagamento_id": fp_id} for r in sel.itertuples()]
        n = db.inserir_transacoes(linhas)
        st.session_state["imp_versao"] += 1  # limpa o upload
        ui.concluir(f"{n} lançamento(s) importado(s).", "📥")
