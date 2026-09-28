"""Lançamentos recorrentes: contas que se repetem todo mês e são criadas automaticamente."""
from datetime import date

import streamlit as st

from core import db, ui
from core.utils import formatar_moeda, primeiro_dia, rotulo_categoria


def render(ctx):
    aux = ctx["aux"]
    cats, formas, cartoes, recs = aux["categorias"], aux["formas"], aux["cartoes"], aux["recorrencias"]
    st.header("Recorrências")
    st.caption("Aluguel, salário, assinaturas… Cadastre uma vez e o lançamento de cada mês é criado "
               "automaticamente ao abrir o app, como pendente (ou pago, se preferir).")

    rot_cat = {int(r.id): rotulo_categoria(r.icone, r.grupo, r.nome) for r in cats.itertuples()}
    with st.form("nova_recorrencia", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        desc = c1.text_input("Descrição", placeholder="Ex.: Aluguel")
        cat_id = c1.selectbox("Categoria", list(rot_cat), format_func=rot_cat.get, index=None,
                              placeholder="Escolha")
        valor = c2.number_input("Valor mensal (R$)", min_value=0.0, step=10.0, format="%.2f")
        dia = c2.number_input("Dia do mês", 1, 31, 5, help="Em meses mais curtos, usa o último dia.")
        fp_id = c3.selectbox("Forma de pagamento", formas["id"].tolist(), index=None, placeholder="Opcional",
                             format_func=lambda i: formas.loc[formas["id"] == i, "nome"].iloc[0])
        cartao_id = c3.selectbox("Cartão", cartoes["id"].tolist(), index=None, placeholder="Opcional",
                                 format_func=lambda i: cartoes.loc[cartoes["id"] == i, "nome"].iloc[0])
        c4, c5, c6 = st.columns(3)
        inicio = c4.date_input("A partir de", primeiro_dia(date.today()), format="DD/MM/YYYY")
        fim = c5.date_input("Até (opcional)", None, format="DD/MM/YYYY")
        gerar_pago = c6.checkbox("Criar já como pago", help="Útil para débito automático.")
        if st.form_submit_button("Criar recorrência", type="primary"):
            if not desc.strip() or cat_id is None or valor <= 0:
                st.error("Preencha descrição, categoria e valor.")
            else:
                tipo = cats.loc[cats["id"] == cat_id, "tipo"].iloc[0]
                db.inserir("recorrencias", {"descricao": desc.strip(), "valor": valor, "categoria_id": cat_id,
                                            "tipo": tipo, "forma_pagamento_id": fp_id, "cartao_id": cartao_id,
                                            "dia": dia, "inicio": inicio, "fim": fim, "gerar_pago": gerar_pago})
                n = db.gerar_recorrencias()
                ui.concluir(f"Recorrência criada · {n} lançamento(s) gerado(s).", "🔁")

    if recs.empty:
        return
    st.divider()
    ativas = recs[recs["ativo"]]
    st.subheader("Suas recorrências")
    st.caption(f"{len(ativas)} ativa(s) · compromisso mensal de "
               f"{formatar_moeda(ativas.loc[ativas['tipo'] == 'Despesa', 'valor'].astype(float).sum())} em despesas")

    e = recs.copy()
    e["categoria"] = e["categoria_id"].map(rot_cat)
    e["valor"] = e["valor"].astype(float)
    e.insert(0, "excluir", False)
    e = e[["excluir", "ativo", "descricao", "categoria", "valor", "dia", "inicio", "fim", "gerar_pago",
           "ultima_geracao", "id"]].reset_index(drop=True)
    st.data_editor(e, hide_index=True, width="stretch", key="rec_editor", column_config={
        "id": None, "excluir": st.column_config.CheckboxColumn("🗑️", width="small"),
        "ativo": st.column_config.CheckboxColumn("Ativa", width="small"),
        "descricao": "Descrição", "categoria": st.column_config.TextColumn("Categoria", disabled=True),
        "valor": st.column_config.NumberColumn("Valor", format="R$ %.2f", min_value=0.0),
        "dia": st.column_config.NumberColumn("Dia", min_value=1, max_value=31, step=1),
        "inicio": st.column_config.DateColumn("Início", format="DD/MM/YYYY"),
        "fim": st.column_config.DateColumn("Fim", format="DD/MM/YYYY"),
        "gerar_pago": st.column_config.CheckboxColumn("Já pago"),
        "ultima_geracao": st.column_config.DateColumn("Gerada até", format="MM/YYYY", disabled=True),
    })
    alt = st.session_state["rec_editor"]["edited_rows"]
    if st.button("💾 Salvar alterações", disabled=not alt):
        exc, upd, nomes = [], {}, []
        for i, v in alt.items():
            linha = e.iloc[int(i)]
            if v.get("excluir"):
                exc.append(int(linha["id"]))
                nomes.append(f"{linha['descricao']} · {formatar_moeda(linha['valor'])}")
            else:
                campos = {k: val for k, val in v.items() if k != "excluir"}
                if campos:
                    upd[int(linha["id"])] = campos

        msg = "Recorrências atualizadas. Lançamentos já criados não são alterados."
        if exc:
            ui.pedir_exclusao("Excluir recorrências?", nomes, "recorrencias", upd, exc, msg)
        else:
            db.atualizar("recorrencias", upd)
            ui.concluir(msg)
