"""Configurações: formas de pagamento, cartões de crédito e backup."""
from datetime import date

import streamlit as st

from core import db, ui


def _tabela_editavel(tabela, df, colunas, config, chave, rotulo_item):
    """Editor com exclusão confirmada e bloqueio de itens em uso."""
    e = df.copy()
    e.insert(0, "excluir", False)
    e = e[["excluir", *colunas, "id"]].reset_index(drop=True)
    st.data_editor(e, hide_index=True, width="stretch", key=chave,
                   column_config={"id": None, "excluir": st.column_config.CheckboxColumn("🗑️", width="small"), **config})
    alt = st.session_state[chave]["edited_rows"]
    if st.button("💾 Salvar", key=f"{chave}_salvar", disabled=not alt):
        exc, upd, nomes = [], {}, []
        for i, v in alt.items():
            linha = e.iloc[int(i)]
            if v.get("excluir"):
                exc.append(int(linha["id"]))
                nomes.append(rotulo_item(linha))
            else:
                campos = {k: val for k, val in v.items() if k != "excluir"}
                if campos:
                    upd[int(linha["id"])] = campos
        em_uso = db.ids_em_uso(tabela, exc)
        if em_uso:
            st.error("Itens com lançamentos vinculados não podem ser excluídos: "
                     + ", ".join(df.loc[df["id"].isin(em_uso), "nome"]) + ".")
            return

        if exc:
            ui.pedir_exclusao("Confirmar exclusão", nomes, tabela, upd, exc, "Alterações salvas.")
        else:
            db.atualizar(tabela, upd)
            ui.concluir("Alterações salvas.")


def render(ctx):
    aux = ctx["aux"]
    st.header("Configurações")
    aba_fp, aba_cartao, aba_bkp = st.tabs(["Formas de pagamento", "Cartões de crédito", "Backup"])

    with aba_fp:
        with st.form("fp_nova", clear_on_submit=True):
            c1, c2, c3 = st.columns([3, 1, 1], vertical_alignment="bottom")
            nome = c1.text_input("Nome", placeholder="Ex.: Pix")
            credito = c2.checkbox("É cartão de crédito")
            if c3.form_submit_button("Adicionar", width="stretch"):
                if nome.strip():
                    db.inserir("formas_pagamento", {"nome": nome.strip(), "e_cartao": credito})
                    ui.concluir(f"{nome.strip()} adicionada.")
                else:
                    st.error("Informe o nome.")
        if not aux["formas"].empty:
            _tabela_editavel("formas_pagamento", aux["formas"], ["nome", "e_cartao"],
                             {"nome": "Nome", "e_cartao": st.column_config.CheckboxColumn("Crédito")},
                             "fp_editor", lambda l: l["nome"])

    with aba_cartao:
        st.caption("Com o dia de fechamento e de vencimento, as compras entram automaticamente na fatura certa.")
        with st.form("cartao_novo", clear_on_submit=True):
            c1, c2, c3, c4 = st.columns([2.5, 1, 1, 1.4])
            nome = c1.text_input("Nome do cartão", placeholder="Ex.: Nubank")
            fech = c2.number_input("Fecha dia", 1, 31, 1)
            venc = c3.number_input("Vence dia", 1, 31, 10)
            limite = c4.number_input("Limite (R$)", min_value=0.0, step=500.0, format="%.2f")
            if st.form_submit_button("Adicionar cartão", type="primary"):
                if nome.strip():
                    db.inserir("cartoes", {"nome": nome.strip(), "dia_fechamento": fech, "dia_vencimento": venc,
                                           "limite": limite or None})
                    ui.concluir(f"Cartão {nome.strip()} adicionado.", "💳")
                else:
                    st.error("Informe o nome do cartão.")
        if not aux["cartoes"].empty:
            cart = aux["cartoes"].assign(limite=aux["cartoes"]["limite"].astype(float))
            _tabela_editavel("cartoes", cart, ["nome", "dia_fechamento", "dia_vencimento", "limite"], {
                "nome": "Cartão",
                "dia_fechamento": st.column_config.NumberColumn("Fecha dia", min_value=1, max_value=31, step=1),
                "dia_vencimento": st.column_config.NumberColumn("Vence dia", min_value=1, max_value=31, step=1),
                "limite": st.column_config.NumberColumn("Limite", format="R$ %.2f", min_value=0.0),
            }, "cartao_editor", lambda l: l["nome"])
            st.caption("Mudar os dias não altera compras já lançadas.")

    with aba_bkp:
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Exportar**")
            st.caption("Todas as tabelas em um arquivo Excel.")
            if st.button("Gerar backup"):
                st.session_state["bkp_bytes"] = db.exportar_backup()
            if "bkp_bytes" in st.session_state:
                st.download_button("⬇️ Baixar .xlsx", st.session_state["bkp_bytes"], f"backup_{date.today()}.xlsx",
                                   type="primary")
        with c2:
            st.markdown("**Restaurar**")
            st.caption("Substitui todos os dados atuais pelos do arquivo.")
            up = st.file_uploader("Arquivo de backup", type=["xlsx"], label_visibility="collapsed")
            if up and st.button("⚠️ Restaurar dados"):
                try:
                    db.restaurar_backup(up)
                    ui.concluir("Dados restaurados.")
                except Exception as e:
                    st.error(f"Não foi possível restaurar: {e}")
