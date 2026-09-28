"""Categorias e orçamentos: criação, edição completa por ID e exclusão com confirmação."""
import pandas as pd
import streamlit as st

from core import db, ui
from core.utils import LISTA_ICONES, NATUREZAS, TIPOS, formatar_moeda, rotulo_categoria


def _campos(prefixo, atual=None):
    """Campos do formulário; `atual` preenche para edição."""
    a = atual if atual is not None else {}
    c1, c2, c3 = st.columns([2, 2, 1.2])
    grupo = c1.text_input("Grupo", a.get("grupo", ""), placeholder="Ex.: Alimentação", key=f"{prefixo}_g")
    nome = c2.text_input("Nome", a.get("nome", ""), placeholder="Ex.: Mercado", key=f"{prefixo}_n")
    tipo = c3.selectbox("Tipo", TIPOS, index=TIPOS.index(a["tipo"]) if a.get("tipo") in TIPOS else 0,
                        key=f"{prefixo}_t")
    c4, c5, c6, c7, c8 = st.columns([1, 1, 1.6, 1.3, 1.2])
    cor = c4.color_picker("Cor", a.get("cor") if isinstance(a.get("cor"), str) else "#4A8FD4", key=f"{prefixo}_c")
    icone = c5.selectbox("Ícone", LISTA_ICONES,
                         index=LISTA_ICONES.index(a["icone"]) if a.get("icone") in LISTA_ICONES else 0,
                         key=f"{prefixo}_i")
    orc_atual = a.get("orcamento")
    orc = c6.number_input("Orçamento mensal (R$)", min_value=0.0, step=50.0, format="%.2f",
                          value=float(orc_atual) if orc_atual is not None and not pd.isna(orc_atual) else 0.0,
                          help="Só para despesas. Deixe 0 para não acompanhar.", key=f"{prefixo}_o")
    natureza = c7.selectbox("Natureza", NATUREZAS,
                            index=NATUREZAS.index(a["natureza"]) if a.get("natureza") in NATUREZAS else 0,
                            help="Usada na regra 50/30/20.", key=f"{prefixo}_nat")
    fixa = c8.checkbox("Despesa fixa", bool(a.get("fixa", False)), key=f"{prefixo}_f",
                       help="Valor previsível todo mês: aluguel, escola, plano de saúde…")
    return {"grupo": grupo.strip(), "nome": nome.strip(), "tipo": tipo, "cor": cor, "icone": icone,
            "orcamento": orc or None, "natureza": natureza, "fixa": fixa}


def render(ctx):
    cats = ctx["aux"]["categorias"]
    st.header("Categorias e orçamentos")

    with st.expander("➕ Nova categoria", expanded=cats.empty):
        with st.form("cat_nova", clear_on_submit=True):
            dados = _campos("nova")
            if st.form_submit_button("Criar categoria", type="primary"):
                if not dados["grupo"] or not dados["nome"]:
                    st.error("Informe grupo e nome.")
                else:
                    db.inserir("categorias", dados)
                    ui.concluir(f"Categoria {dados['nome']} criada.")

    if cats.empty:
        return

    st.subheader("Editar categoria")
    rotulos = {int(r.id): f"{rotulo_categoria(r.icone, r.grupo, r.nome)} ({r.tipo})" for r in cats.itertuples()}
    cid = st.selectbox("Categoria", list(rotulos), format_func=rotulos.get, key="cat_sel")
    atual = cats[cats["id"] == cid].iloc[0].to_dict()
    with st.form(f"cat_editar_{cid}"):
        dados = _campos(f"ed{cid}", atual)
        if st.form_submit_button("Salvar categoria", type="primary"):
            if not dados["grupo"] or not dados["nome"]:
                st.error("Grupo e nome não podem ficar vazios.")
            else:
                db.atualizar("categorias", {cid: dados})
                ui.concluir("Categoria atualizada.")

    st.divider()
    st.subheader("Todas as categorias")
    desp = cats[cats["tipo"] == "Despesa"]
    total_orc = pd.to_numeric(desp["orcamento"], errors="coerce").fillna(0).sum()
    if total_orc:
        st.caption(f"Orçamento mensal total das despesas: **{formatar_moeda(total_orc)}**")
    e = cats.copy()
    e.insert(0, "excluir", False)
    e = e[["excluir", "icone", "grupo", "nome", "tipo", "orcamento", "fixa", "natureza", "id"]]
    st.data_editor(e, hide_index=True, width="stretch", key="cat_editor", column_config={
        "id": None, "excluir": st.column_config.CheckboxColumn("🗑️", width="small"),
        "icone": st.column_config.TextColumn("", disabled=True, width="small"),
        "grupo": "Grupo", "nome": "Nome",
        "tipo": st.column_config.SelectboxColumn("Tipo", options=TIPOS),
        "orcamento": st.column_config.NumberColumn("Orçamento/mês", format="R$ %.2f", min_value=0.0),
        "fixa": st.column_config.CheckboxColumn("Fixa"),
        "natureza": st.column_config.SelectboxColumn("Natureza", options=NATUREZAS),
    })
    alt = st.session_state["cat_editor"]["edited_rows"]
    if st.button("💾 Salvar tabela", disabled=not alt):
        exc, upd, nomes = [], {}, []
        for i, v in alt.items():
            linha = e.iloc[int(i)]
            rid = int(linha["id"])
            if v.get("excluir"):
                exc.append(rid)
                nomes.append(rotulo_categoria(linha["icone"], linha["grupo"], linha["nome"]))
            else:
                campos = {k: val for k, val in v.items() if k != "excluir"}
                if campos:
                    upd[rid] = campos
        em_uso = db.ids_em_uso("categorias", exc)
        if em_uso:
            nomes_uso = ", ".join(cats.loc[cats["id"].isin(em_uso), "nome"])
            st.error(f"Não é possível excluir categorias com lançamentos ou recorrências: {nomes_uso}. "
                     "Mova esses lançamentos para outra categoria no Extrato antes.")
        else:
            if exc:
                ui.pedir_exclusao("Excluir categorias?", nomes, "categorias", upd, exc, "Categorias atualizadas.")
            else:
                db.atualizar("categorias", upd)
                ui.concluir("Categorias atualizadas.")
