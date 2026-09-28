"""Novo lançamento: cartão com fatura, prévia de parcelamento e formulário que limpa após salvar."""
from datetime import date

import streamlit as st

from core import db, ui
from core.utils import TIPOS, add_months, formatar_moeda, mes_ano, rotulo_categoria, vencimento_fatura


def _valores_parcelas(valor: float, total: int, modo_total: bool) -> list[float]:
    """Valor de cada parcela; no modo 'total', a última absorve a diferença de centavos."""
    if not modo_total:
        return [round(valor, 2)] * total
    base = round(valor / total, 2)
    return [base] * (total - 1) + [round(valor - base * (total - 1), 2)]


def render(ctx):
    aux = ctx["aux"]
    cats, formas, cartoes = aux["categorias"], aux["formas"], aux["cartoes"]
    st.header("Novo lançamento")
    v = st.session_state.setdefault("form_versao", 0)  # trocar a versão recria os campos vazios
    k = lambda nome: f"lc_{nome}_{v}"  # noqa: E731

    with st.container(border=True):
        c1, c2, c3 = st.columns(3)
        with c1:
            tipo = st.segmented_control("Tipo", TIPOS, default="Despesa", required=True, key=k("tipo"))
            cv = cats[cats["tipo"].str.lower() == tipo.lower()]
            opcoes = {rotulo_categoria(r.icone, r.grupo, r.nome): int(r.id) for r in cv.itertuples()}
            cat_rot = st.selectbox("Categoria", sorted(opcoes), key=k("cat"), index=None,
                                   placeholder="Escolha a categoria") if opcoes else None
            if not opcoes:
                st.warning(f"Crie uma categoria de {tipo.lower()} em **Categorias**.")
            desc = st.text_input("Descrição", key=k("desc"))
        with c2:
            data = st.date_input("Data", date.today(), format="DD/MM/YYYY", key=k("data"))
            fp_nome = st.selectbox("Forma de pagamento", formas["nome"].tolist(), key=k("fp")) \
                if not formas.empty else None
            if formas.empty:
                st.warning("Cadastre formas de pagamento em **Configurações**.")
            fp = formas[formas["nome"] == fp_nome].iloc[0] if fp_nome else None
            e_cartao = bool(fp is not None and fp["e_cartao"])
            pago = st.checkbox("Já está pago", value=not e_cartao, key=k("pago"), disabled=e_cartao,
                               help="Compras no cartão ficam em aberto até você pagar a fatura." if e_cartao else None)
            if e_cartao:
                pago = False
        with c3:
            cartao, parcelas, parcela_ini, retro, modo_total = None, 1, 1, False, False
            if e_cartao:
                if cartoes.empty:
                    st.info("Cadastre seus cartões em **Configurações** para lançar na fatura certa.")
                else:
                    nome = st.selectbox("Cartão", cartoes["nome"].tolist(), key=k("cartao"))
                    cartao = cartoes[cartoes["nome"] == nome].iloc[0]
                a, b = st.columns(2)
                parcelas = a.number_input("Parcelas", 1, 60, 1, key=k("parc"))
                parcela_ini = b.number_input("Começa na", 1, int(parcelas), 1, key=k("pini"),
                                             help="Use para compras antigas já em andamento.")
                if parcela_ini > 1:
                    retro = st.checkbox("Lançar também as parcelas anteriores (como pagas)", True, key=k("retro"))
            if parcelas > 1:
                modo_total = st.radio("O valor informado é", ["da parcela", "total da compra"], horizontal=True,
                                      key=k("modo")) == "total da compra"
            valor = st.number_input("Valor (R$)", min_value=0.0, step=10.0, format="%.2f", key=k("valor"))

        # ---- prévia
        primeira = data
        if cartao is not None:
            primeira = vencimento_fatura(data, int(cartao["dia_fechamento"]), int(cartao["dia_vencimento"]))
        valores = _valores_parcelas(valor, int(parcelas), modo_total) if valor > 0 else []
        if valores and parcelas > 1:
            ultima = add_months(primeira, int(parcelas) - int(parcela_ini))
            st.info(f"**{parcelas}x de {formatar_moeda(valores[0])}** (total {formatar_moeda(sum(valores))}) · "
                    f"parcela {parcela_ini} vence em {primeira:%d/%m/%Y}, última em {mes_ano(ultima)}.", icon="🧮")
        elif valores and cartao is not None:
            st.info(f"Entra na fatura do **{cartao['nome']}** que vence em **{primeira:%d/%m/%Y}**.", icon="💳")

        if st.button("💾 Salvar lançamento", type="primary"):
            faltando = [n for n, ok in (("categoria", cat_rot), ("descrição", desc.strip()), ("valor", valor > 0),
                                        ("forma de pagamento", fp is not None)) if not ok]
            if faltando:
                st.error("Preencha: " + ", ".join(faltando) + ".")
            else:
                base = {"descricao": desc.strip(), "categoria_id": opcoes[cat_rot], "tipo": tipo,
                        "forma_pagamento_id": int(fp["id"]),
                        "cartao_id": int(cartao["id"]) if cartao is not None else None,
                        "cartao": cartao["nome"] if cartao is not None else None}
                linhas = []
                if parcelas > 1:
                    inicio = 1 if retro else int(parcela_ini)
                    for p in range(inicio, int(parcelas) + 1):
                        linhas.append({**base, "data": add_months(primeira, p - int(parcela_ini)),
                                       "descricao": f"{base['descricao']} ({p}/{parcelas})",
                                       "valor": valores[p - 1], "pago": p < parcela_ini,
                                       "parcela_atual": p, "parcela_total": int(parcelas)})
                else:
                    linhas.append({**base, "data": primeira, "valor": valores[0], "pago": pago})
                n = db.inserir_transacoes(linhas)
                st.session_state["form_versao"] += 1
                ui.concluir(f"{n} lançamento(s) salvo(s).", "🚀")

    st.divider()
    st.subheader("Últimos lançamentos")
    ult = db.carregar_ultimos()
    if ult.empty:
        st.caption("Nada lançado ainda.")
        return
    ult = ult.assign(data=ult["data"].dt.date, categoria=[f"{i or ''} {c}".strip() for i, c in
                                                             zip(ult["icone"], ult["categoria"])])
    st.dataframe(ult[["data", "descricao", "valor", "categoria", "tipo", "pago", "metodo_pagamento", "cartao"]],
                 hide_index=True, width="stretch", column_config={
                     "data": st.column_config.DateColumn("Data", format="DD/MM/YYYY"),
                     "descricao": "Descrição", "valor": st.column_config.NumberColumn("Valor", format="R$ %.2f"),
                     "categoria": "Categoria", "tipo": "Tipo", "pago": "Pago", "metodo_pagamento": "Método",
                     "cartao": "Cartão"})
