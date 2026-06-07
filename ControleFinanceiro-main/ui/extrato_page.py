import streamlit as st
import pandas as pd
import time
from datetime import date

from repository.transacao_repo import carregar_dados, atualizar_transacoes, replicar_lancamento
from repository.categoria_repo import carregar_tabelas_auxiliares
from ui.utils import formatar_moeda, MAPA_MESES_INV

def render_extrato_page(user_id: int, ano_selecionado: int, meses_selecionados: list):
    """Renderiza a página de Extrato & Gestão de Lançamentos."""
    st.header("Extrato & Gestão")
    
    # Gerenciamento de edição de registro único (filtro)
    id_f = st.session_state.get('filtro_transacao_id')
    filtro_ativo = id_f is not None
    if filtro_ativo:
        st.info("🔍 Editando registro único.")
        if st.button("Voltar para visualização completa"):
            del st.session_state['filtro_transacao_id']
            st.rerun()

    df = carregar_dados(user_id)
    cats_df, fps_df = carregar_tabelas_auxiliares(user_id)

    if df.empty:
        st.info("Não há dados cadastrados para o período.")
        return

    df['data'] = pd.to_datetime(df['data'])
    
    if filtro_ativo:
        df = df[df['id'] == id_f]
    else:
        # Filtros temporais
        df = df[df['data'].dt.year == ano_selecionado]
        if meses_selecionados:
            df = df[df['data'].dt.month.isin([MAPA_MESES_INV[m] for m in meses_selecionados])]
        
        # Filtros de interface
        c1, c2 = st.columns(2)
        with c1:
            stt = st.radio("Status de Pagamento", ["Todos", "Pendentes", "Pagos"], horizontal=True)
        with c2:
            cts = st.multiselect("Filtrar por Categoria", sorted(df['categoria'].unique()))
            
        if stt == "Pendentes":
            df = df[~df['pago']]
        elif stt == "Pagos":
            df = df[df['pago']]
            
        if cts:
            df = df[df['categoria'].isin(cts)]
        
    if not df.empty:
        if not id_f:
            st.download_button(
                "📥 Exportar CSV", 
                df.to_csv(index=False).encode('utf-8'), 
                "extrato.csv", 
                "text/csv"
            )
            
        df_e = df.copy()
        df_e['data'] = df_e['data'].dt.date
        df_e.insert(0, "excluir", False)
        df_e['Status'] = df_e['pago'].apply(lambda x: "🟢" if x else "🟠")
        df_e['cat_full'] = df_e.apply(
            lambda x: f"{x['icone'] if x['icone'] else ''} {x['grupo']} - {x['categoria']}".strip(), 
            axis=1
        )
        
        cols_visual = [
            'excluir', 'Status', 'data', 'cat_full', 'descricao', 'valor', 'tipo', 
            'pago', 'metodo_pagamento', 'cartao', 'parcela_atual', 'parcela_total', 
            'id', 'grupo', 'categoria_id', 'forma_pagamento_id'
        ]
        df_e = df_e.reindex(columns=cols_visual)
        if df_e['Status'].isnull().any():
            df_e['Status'] = df_e['pago'].apply(lambda x: "🟢" if x else "🟠")

        # CRITICAL FIX: Resetar o index para garantir alinhamento absoluto de chaves do data_editor com iloc
        df_editor = df_e.reset_index(drop=True)

        ch = st.data_editor(
            df_editor, 
            hide_index=True, 
            use_container_width=True, 
            key="ed_full", 
            height=500,
            column_config={
                "id": None, "grupo": None, "categoria_id": None, "forma_pagamento_id": None,
                "excluir": st.column_config.CheckboxColumn("🗑️", width="small"),
                "pago": st.column_config.CheckboxColumn("Pago?", width="small"),
                "Status": st.column_config.Column("Status", width="small", disabled=True),
                "cat_full": st.column_config.SelectboxColumn(
                    "Categoria", 
                    options=sorted([f"{r.icone if r.icone else ''} {r.grupo} - {r.nome}".strip() for _, r in cats_df.iterrows()]), 
                    width="medium"
                ),
                "metodo_pagamento": st.column_config.SelectboxColumn(
                    "Método", 
                    options=sorted(fps_df['nome']) if not fps_df.empty else [], 
                    width="medium"
                ),
                "valor": st.column_config.NumberColumn("Valor", format="R$ %.2f", width="medium"),
                "data": st.column_config.DateColumn("Data", format="DD/MM/YYYY", width="medium"),
                "descricao": st.column_config.TextColumn("Descrição", width="large"),
                "tipo": st.column_config.SelectboxColumn("Tipo", options=["Receita", "Despesa", "Investimento"], width="small"),
                "cartao": st.column_config.TextColumn("Cartão"),
                "parcela_atual": st.column_config.NumberColumn("Parc. Atual"),
                "parcela_total": st.column_config.NumberColumn("Total Parc.")
            }
        )
        
        if st.button("💾 Salvar Alterações / Excluir Selecionados", type="primary"):
            exc = []
            upd = {}
            st_ch = st.session_state["ed_full"]
            
            # Mapeamento reverso para obter IDs das categorias e formas de pagamento
            mc = {f"{r.icone if r.icone else ''} {r.grupo} - {r.nome}".strip(): r.id for _, r in cats_df.iterrows()}
            mf = {r.nome: r.id for _, r in fps_df.iterrows()}
            
            for i, v in st_ch["edited_rows"].items():
                # Obtenção segura por posição no df_editor (graças ao reset_index)
                row_idx = int(i)
                rid = df_editor.iloc[row_idx]['id']
                
                if v.get("excluir") is True:
                    exc.append(rid)
                else:
                    d = {}
                    if "pago" in v: d["pago"] = v["pago"]
                    if "valor" in v: d["valor"] = v["valor"]
                    if "data" in v: d["data"] = v["data"]
                    if "descricao" in v: d["descricao"] = v["descricao"]
                    if "tipo" in v: d["tipo"] = v["tipo"]
                    if "cat_full" in v: d["categoria_id"] = mc.get(v["cat_full"])
                    if "metodo_pagamento" in v: d["forma_pagamento_id"] = mf.get(v["metodo_pagamento"])
                    if "cartao" in v: d["cartao"] = v["cartao"]
                    if "parcela_atual" in v: d["parcela_atual"] = int(v["parcela_atual"])
                    if "parcela_total" in v: d["parcela_total"] = int(v["parcela_total"])
                    if d: 
                        upd[rid] = d
                        
            # Captura de itens deletados da lista de deleções implícita do data_editor (se houver)
            for i in st_ch.get("deleted_rows", []):
                rid = df_editor.iloc[int(i)]['id']
                exc.append(rid)
                
            if atualizar_transacoes(user_id, upd, exc):
                st.toast("Alterações salvas com sucesso!", icon="✅")
                time.sleep(0.5)
                st.rerun()
    else:
        st.warning("Nenhum lançamento corresponde aos filtros aplicados.")
        
    # Painel de Duplicação/Replicação
    if not id_f and not df.empty:
        with st.expander("🔄 Duplicar Lançamento (Projeção Mensal)", expanded=False):
            mapa_opcoes = {
                row['id']: f"{row['data'].strftime('%d/%m/%Y')} | {row['categoria']} | {row['descricao']} | {formatar_moeda(row['valor'])}" 
                for _, row in df.iterrows()
            }
            if mapa_opcoes:
                dup_id = st.selectbox("Selecione o Lançamento de Origem:", options=list(mapa_opcoes.keys()), format_func=lambda x: mapa_opcoes.get(x))
                dup_qtd = st.number_input("Quantidade de Meses a Projetar:", 1, 36, 1)
                if st.button("Duplicar Lançamento"):
                    if replicar_lancamento(user_id, dup_id, dup_qtd):
                        st.toast("Lançamento duplicado com sucesso!", icon="✅")
                        time.sleep(0.5)
                        st.rerun()
            else:
                st.info("Sem dados disponíveis para duplicação.")
