import streamlit as st
import pandas as pd
import io
import time
from datetime import date

from repository.categoria_repo import carregar_tabelas_auxiliares, criar_forma_pagamento, atualizar_formas_pagamento
from repository.transacao_repo import limpar_cache_dados
from core.config import engine
from sqlalchemy import text
import logging

logger = logging.getLogger(__name__)

def render_configuracoes_page(user_id: int):
    """Renderiza a página de Configurações, Formas de Pagamento e Backup Seguro."""
    st.header("Configurações")
    
    # --- GESTÃO DE FORMAS DE PAGAMENTO ---
    st.subheader("💳 Formas de Pagamento")
    with st.form("nfp"):
        c1, c2 = st.columns([3, 1])
        n = c1.text_input("Nome do Método (Ex: Itaú Débito, Nu Crédito)")
        c = c2.checkbox("É cartão de crédito?")
        
        if st.form_submit_button("Adicionar Método"):
            if n:
                if criar_forma_pagamento(user_id, n, c):
                    st.toast("Método de pagamento adicionado!", icon="✅")
                    time.sleep(0.5)
                    st.rerun()
                else:
                    st.error("Erro ao adicionar método. Talvez o nome já exista.")
            else:
                st.error("Por favor, digite o nome do método.")
                
    st.divider()
    
    # Carrega dados atualizados do banco
    _, fps_df = carregar_tabelas_auxiliares(user_id)
    
    if not fps_df.empty:
        # Reseta os índices para alinhar 1:1 com as alterações do st.data_editor
        de = fps_df.copy().reset_index(drop=True)
        de.insert(0, "excluir", False)
        
        ed = st.data_editor(
            de, 
            hide_index=True, 
            key="ed_fp", 
            column_config={
                "id": None, 
                "excluir": st.column_config.CheckboxColumn("🗑️ Excluir?", width="small"),
                "nome": "Nome", 
                "e_cartao": "Crédito?"
            }
        )
        
        if st.button("Salvar Modificações / Exclusões", type="secondary"):
            exc = []
            upd = {}
            stc = st.session_state["ed_fp"]
            
            for i, v in stc["edited_rows"].items():
                row_idx = int(i)
                # Acesso posicional seguro do df index-resetado
                rid = de.iloc[row_idx]['id']
                if v.get("excluir"): 
                    exc.append(rid)
                else: 
                    d = {k: v for k, v in v.items() if k != 'excluir'}
                    if d: 
                        upd[rid] = d
                        
            if exc or upd:
                if atualizar_formas_pagamento(user_id, upd, exc):
                    st.toast("Alterações salvas!", icon="✅")
                    time.sleep(0.5)
                    st.rerun()
            else:
                st.info("Nenhuma alteração foi realizada.")
    else:
        st.info("Nenhum método de pagamento cadastrado.")

    # --- SEÇÃO DE BACKUP E SEGURANÇA ISOLADA ---
    st.markdown("---")
    st.subheader("📦 Backup e Restauração de Dados")
    st.caption("Faça o download do seu histórico financeiro ou restaure-o a partir de uma planilha Excel (.xlsx).")
    
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("##### 📥 Exportar Backup")
        if st.button("Preparar Download do Backup", use_container_width=True):
            try:
                # Realiza queries com isolamento de usuário
                with engine.connect() as conn:
                    transacoes_df = pd.read_sql(
                        text("SELECT data, descricao, valor, tipo, pago, cartao, parcela_atual, parcela_total, categoria_id, forma_pagamento_id FROM transacoes WHERE user_id = :uid"), 
                        conn, 
                        params={"uid": user_id}
                    )
                    categorias_df = pd.read_sql(
                        text("SELECT id, grupo, nome, tipo, cor, icone FROM categorias WHERE user_id = :uid"), 
                        conn, 
                        params={"uid": user_id}
                    )
                    fps_df_exp = pd.read_sql(
                        text("SELECT id, nome, e_cartao FROM formas_pagamento WHERE user_id = :uid"), 
                        conn, 
                        params={"uid": user_id}
                    )
                
                b = io.BytesIO()
                with pd.ExcelWriter(b, engine='xlsxwriter') as w: 
                    transacoes_df.to_excel(w, sheet_name='transacoes', index=False)
                    categorias_df.to_excel(w, sheet_name='categorias', index=False)
                    fps_df_exp.to_excel(w, sheet_name='formas_pagamento', index=False)
                    
                st.download_button(
                    "💾 Baixar Arquivo .xlsx", 
                    b.getvalue(), 
                    f"backup_financeiro_{date.today()}.xlsx",
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )
            except Exception as e:
                logger.error(f"Erro ao gerar backup para {user_id}: {e}", exc_info=True)
                st.error("Erro interno ao gerar o arquivo de backup.")

    with c2:
        st.markdown("##### ⚠️ Restaurar Backup")
        up = st.file_uploader("Selecione a planilha do backup (.xlsx)", type=["xlsx"])
        if up:
            if st.button("Confirmar Restauração", type="primary", use_container_width=True):
                # RESTAURAÇÃO SEGURA: Mapeamento de chaves estrangeiras dinâmicas e isolamento por user_id
                try:
                    xls = pd.ExcelFile(up)
                    up_trans = pd.read_excel(xls, 'transacoes')
                    up_cats = pd.read_excel(xls, 'categorias')
                    up_fps = pd.read_excel(xls, 'formas_pagamento')
                    
                    with engine.begin() as conn:
                        # 1. Limpa dados antigos apenas do usuário ativo
                        conn.execute(text("DELETE FROM transacoes WHERE user_id = :uid"), {"uid": user_id})
                        conn.execute(text("DELETE FROM categorias WHERE user_id = :uid"), {"uid": user_id})
                        conn.execute(text("DELETE FROM formas_pagamento WHERE user_id = :uid"), {"uid": user_id})
                        
                        # 2. Insere métodos de pagamento e mapeia IDs para evitar conflitos de banco multiusuário
                        map_fp = {}
                        for _, row in up_fps.iterrows():
                            old_id = int(row['id'])
                            res = conn.execute(
                                text("INSERT INTO formas_pagamento (user_id, nome, e_cartao) VALUES (:uid, :n, :c) RETURNING id"),
                                {"uid": user_id, "n": str(row['nome']).strip(), "c": bool(row['e_cartao'])}
                            ).fetchone()
                            map_fp[old_id] = res[0]
                            
                        # 3. Insere categorias e mapeia IDs
                        map_cat = {}
                        for _, row in up_cats.iterrows():
                            old_id = int(row['id'])
                            res = conn.execute(
                                text("INSERT INTO categorias (user_id, grupo, nome, tipo, cor, icone) VALUES (:uid, :g, :n, :t, :c, :i) RETURNING id"),
                                {
                                    "uid": user_id, 
                                    "g": str(row['grupo']).strip(), 
                                    "n": str(row['nome']).strip(), 
                                    "t": str(row['tipo']).strip(), 
                                    "c": str(row.get('cor', '#3498db')).strip(), 
                                    "i": str(row.get('icone', '💰')).strip()
                                }
                            ).fetchone()
                            map_cat[old_id] = res[0]
                            
                        # 4. Insere transações vinculando os novos IDs correspondentes
                        for _, row in up_trans.iterrows():
                            old_cat = int(row['categoria_id'])
                            old_fp = int(row['forma_pagamento_id'])
                            
                            new_cat = map_cat.get(old_cat)
                            new_fp = map_fp.get(old_fp)
                            
                            # Apenas insere se as chaves estrangeiras mapearam com sucesso
                            if new_cat and new_fp:
                                conn.execute(
                                    text("""
                                        INSERT INTO transacoes (user_id, data, descricao, valor, categoria_id, tipo, pago, forma_pagamento_id, cartao, parcela_atual, parcela_total)
                                        VALUES (:uid, :data, :desc, :val, :cat, :tipo, :pago, :fp, :cartao, :pa, :pt)
                                    """),
                                    {
                                        "uid": user_id,
                                        "data": row['data'],
                                        "desc": str(row['descricao']).strip(),
                                        "val": float(row['valor']),
                                        "cat": new_cat,
                                        "tipo": str(row['tipo']).strip(),
                                        "pago": bool(row['pago']),
                                        "fp": new_fp,
                                        "cartao": str(row['cartao']).strip() if pd.notna(row['cartao']) else None,
                                        "pa": int(row['parcela_atual']) if pd.notna(row['parcela_atual']) else 1,
                                        "pt": int(row['parcela_total']) if pd.notna(row['parcela_total']) else 1
                                    }
                                )
                                
                    st.toast("Dados restaurados com sucesso!", icon="✅")
                    limpar_cache_dados()
                    # Reseta caches de configuração
                    from repository.categoria_repo import limpar_cache_configs
                    limpar_cache_configs()
                    time.sleep(0.5)
                    st.rerun()
                except Exception as e:
                    logger.error(f"Erro ao restaurar backup para {user_id}: {e}", exc_info=True)
                    st.error(f"Formato do arquivo inválido ou erro no processamento: {e}")
