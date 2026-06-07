import streamlit as st
import pandas as pd
import time

from repository.categoria_repo import carregar_tabelas_auxiliares, criar_categoria, atualizar_categorias
from ui.utils import LISTA_ICONES

def render_categorias_page(user_id: int):
    """Renderiza a página de gestão de Categorias com suporte a multiusuário."""
    st.header("Categorias")
    
    # Cadastro de Nova Categoria
    st.subheader("🆕 Nova Categoria")
    with st.form("nc"):
        c1, c2, c3, c4, c5 = st.columns([2, 2, 1, 1, 1])
        g = c1.text_input("Grupo (Ex: Alimentação, Habitação)")
        n = c2.text_input("Nome da Categoria (Ex: Supermercado, Aluguel)")
        t = c3.selectbox("Tipo", ["Despesa", "Receita", "Investimento"])
        cor = c4.color_picker("Cor", "#3498db")
        icone = c5.selectbox("Ícone", LISTA_ICONES)
        
        if st.form_submit_button("Criar Categoria"): 
            if g and n:
                if criar_categoria(user_id, g, n, t, cor, icone): 
                    st.toast("Categoria criada com sucesso!", icon="✅")
                    time.sleep(0.5)
                    st.rerun()
                else:
                    st.error("Erro ao criar categoria. Talvez o nome já exista.")
            else:
                st.error("Preencha Grupo e Nome.")
    
    st.divider()
    
    # Leitura dos dados mais recentes
    cats_df, _ = carregar_tabelas_auxiliares(user_id)
    
    if cats_df.empty:
        st.info("Nenhuma categoria cadastrada ainda.")
        return

    # Edição de Categoria Existente (Apenas cor e ícone para não quebrar dados antigos)
    st.subheader("✏️ Editar Categoria Existente")
    cat_to_edit = st.selectbox("Selecione a Categoria para alterar visualmente", cats_df['nome'].unique())
    
    if cat_to_edit:
        row = cats_df[cats_df['nome'] == cat_to_edit].iloc[0]
        with st.form("edit_cat"):
            ce1, ce2, ce3 = st.columns(3)
            new_cor = ce1.color_picker("Nova Cor", row['cor'] if pd.notna(row['cor']) else "#3498db")
            new_icon = ce2.selectbox(
                "Novo Ícone", 
                LISTA_ICONES, 
                index=LISTA_ICONES.index(row['icone']) if row['icone'] in LISTA_ICONES else 0
            )
            
            if st.form_submit_button("Atualizar Aparência"):
                if atualizar_categorias(user_id, {row['id']: {"cor": new_cor, "icone": new_icon}}, []):
                    st.toast("Aparência atualizada!", icon="✅")
                    time.sleep(0.5)
                    st.rerun()

    st.divider()
    
    # Gestão/Exclusão de Categorias
    st.subheader("📋 Gestão e Exclusão de Categorias")
    
    # Reseta os índices para alinhar 1:1 com as alterações do st.data_editor
    de = cats_df.copy().reset_index(drop=True)
    de.insert(0, "excluir", False)
    
    ed = st.data_editor(
        de, 
        hide_index=True, 
        key="ed_cat", 
        column_config={
            "id": None, 
            "excluir": st.column_config.CheckboxColumn("🗑️ Excluir?", width="small"),
            "grupo": "Grupo", 
            "nome": "Nome", 
            "tipo": "Tipo",
            "cor": st.column_config.TextColumn("Cor (Hex)", disabled=True),
            "icone": st.column_config.TextColumn("Ícone", disabled=True)
        }
    )
    
    if st.button("Salvar Exclusões", type="secondary"):
        exc = []
        stc = st.session_state["ed_cat"]
        
        for i, v in stc["edited_rows"].items():
            row_idx = int(i)
            # Acesso posicional seguro do df index-resetado
            rid = de.iloc[row_idx]['id']
            if v.get("excluir"): 
                exc.append(rid)
                
        if exc:
            if atualizar_categorias(user_id, {}, exc): 
                st.toast("Exclusões salvas com sucesso!", icon="✅")
                time.sleep(0.5)
                st.rerun()
        else:
            st.info("Nenhuma categoria selecionada para exclusão.")
