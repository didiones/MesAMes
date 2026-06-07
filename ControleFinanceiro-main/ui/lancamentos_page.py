import streamlit as st
import pandas as pd
from datetime import datetime, date
import time

from repository.transacao_repo import salvar_transacao, salvar_parcelamento, carregar_ultimos_lancamentos
from repository.categoria_repo import carregar_tabelas_auxiliares
from ui.utils import formatar_moeda

def render_lancamentos_page(user_id: int):
    """Renderiza o formulário de cadastro de Lançamentos e o histórico recente."""
    st.header("Novo Lançamento")
    
    cats_df, fps_df = carregar_tabelas_auxiliares(user_id)
    
    if cats_df.empty:
        st.warning("Cadastre categorias antes de realizar lançamentos.")
        return
    if fps_df.empty:
        st.warning("Cadastre formas de pagamento nas Configurações antes de realizar lançamentos.")
        return

    if 'nk' not in st.session_state:
        st.session_state.nk = str(datetime.now())
        
    with st.container(border=True):
        c1, c2, c3 = st.columns(3)
        with c1:
            tp = st.selectbox("Tipo de Lançamento", ["Despesa", "Receita", "Investimento"], key="n_t")
            
            # Filtra categorias pelo tipo selecionado (case insensitive)
            cats_df['tipo'] = cats_df['tipo'].astype(str).str.strip()
            cv = cats_df[cats_df['tipo'].str.lower() == tp.lower()]
            
            opts = sorted([f"{r.icone if r.icone else ''} {r.grupo} - {r.nome}".strip() for _, r in cv.iterrows()])
            ct_s = st.selectbox("Categoria", opts) if not cv.empty else None
            
            # Obtém ID da categoria selecionada
            ct_id = None
            if ct_s:
                for _, r in cv.iterrows():
                    if f"{r.icone if r.icone else ''} {r.grupo} - {r.nome}".strip() == ct_s:
                        ct_id = r.id
                        break
            
            dsc = st.text_input("Descrição (Ex: Compras da semana)", key="n_d")
            
        with c2:
            vl = st.number_input("Valor (R$)", min_value=0.01, format="%.2f", key="n_v")
            dt = st.date_input("Data da Transação", datetime.today(), key="n_dt")
            pg = st.checkbox("Pago?", True, key="n_p")
            
        with c3:
            fp_n = st.selectbox("Método de Pagamento", fps_df['nome'])
            
            fp_id = None
            card = False
            if fp_n:
                fp_r = fps_df[fps_df['nome'] == fp_n].iloc[0]
                fp_id = int(fp_r['id'])
                card = bool(fp_r['e_cartao'])
                
                cn = None
                pa = 1
                pt = 1
                ret = False
                
                if card:
                    cn = st.text_input("Nome/Bandeira do Cartão (Opcional)", key="n_c")
                    c3a, c3b = st.columns(2)
                    pa = c3a.number_input("Parcela Inicial", 1, 60, 1)
                    pt = c3b.number_input("Total de Parcelas", 1, 60, 1)
                    if pa > 1:
                        ret = st.checkbox("Gerar parcelas anteriores como Pagas (Retroativo)?", True)
                    pg = False  # Cartão de crédito inicia como despesa aberta (não paga)

        st.markdown("---")
        if st.button("💾 Salvar Lançamento", type="primary"):
            if ct_id and vl > 0 and fp_id:
                ok = False
                if card and pt > 1:
                    ok = salvar_parcelamento(user_id, dt, dsc, vl, int(ct_id), tp, int(fp_id), cn, pa, pt, ret, pg)
                else:
                    ok = salvar_transacao(user_id, dt, dsc, vl, int(ct_id), tp, pg, int(fp_id), cn)
                    
                if ok:
                    st.toast("Lançamento salvo com sucesso!", icon="🚀")
                    time.sleep(0.5)
                    st.rerun()
                else:
                    st.error("Erro interno ao gravar lançamento no banco de dados.")
            else:
                st.error("Por favor, preencha todos os campos obrigatórios.")
                
    st.divider()
    st.subheader("📋 Histórico Recente (Últimos 15 lançamentos)")
    df_ult = carregar_ultimos_lancamentos(user_id)
    
    if not df_ult.empty:
        df_ult['data'] = pd.to_datetime(df_ult['data']).dt.date
        
        def highlight_status(row):
            return [f'color: {"#2ecc71" if row["Pago?"] else "#f39c12"}; font-weight: bold' for _ in row]
            
        df_view = df_ult.rename(columns={
            'data': 'Data', 'descricao': 'Descrição', 'valor': 'Valor', 
            'grupo': 'Grupo', 'categoria': 'Categoria', 'tipo': 'Tipo', 
            'pago': 'Pago?', 'metodo_pagamento': 'Método',
            'icone': ' '
        })
        cols_hist = ['Data', 'Descrição', 'Valor', 'Grupo', ' ', 'Categoria', 'Tipo', 'Pago?', 'Método']
        df_view = df_view[cols_hist]
        
        st.dataframe(
            df_view.style.apply(highlight_status, axis=1).format({'Valor': formatar_moeda}), 
            hide_index=True, 
            use_container_width=True
        )
    else:
        st.info("Nenhum lançamento recente encontrado.")
