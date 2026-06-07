import streamlit as st
import pandas as pd
from sqlalchemy import text
from core.config import engine
import logging

logger = logging.getLogger(__name__)

@st.cache_data(ttl=3600)
def carregar_tabelas_auxiliares(user_id: int):
    """Carrega categorias e formas de pagamento do banco filtradas por user_id."""
    try:
        with engine.connect() as conn:
            c = pd.read_sql(
                text("SELECT id, grupo, nome, tipo, cor, icone FROM categorias WHERE user_id = :uid ORDER BY grupo, nome"), 
                conn, 
                params={"uid": user_id}
            )
            f = pd.read_sql(
                text("SELECT id, nome, e_cartao FROM formas_pagamento WHERE user_id = :uid ORDER BY nome"), 
                conn, 
                params={"uid": user_id}
            )
        return c, f
    except Exception as e:
        logger.error(f"Erro ao carregar tabelas auxiliares para usuário {user_id}: {e}", exc_info=True)
        return pd.DataFrame(), pd.DataFrame()

def limpar_cache_configs():
    """Limpa o cache das tabelas auxiliares."""
    carregar_tabelas_auxiliares.clear()

def criar_categoria(user_id: int, grupo: str, nome: str, tipo: str, cor: str, icone: str) -> bool:
    """Cria uma nova categoria para o usuário."""
    try:
        with engine.begin() as conn:
            conn.execute(
                text("INSERT INTO categorias (user_id, grupo, nome, tipo, cor, icone) VALUES (:uid, :g, :n, :t, :c, :i)"),
                {"uid": user_id, "g": grupo.strip(), "n": nome.strip(), "t": tipo.strip(), "c": cor.strip(), "i": icone.strip()}
            )
        limpar_cache_configs()
        return True
    except Exception as e:
        logger.error(f"Erro ao criar categoria para {user_id}: {e}", exc_info=True)
        return False

def criar_forma_pagamento(user_id: int, nome: str, e_cartao: bool) -> bool:
    """Cria um novo método de pagamento para o usuário."""
    try:
        with engine.begin() as conn:
            conn.execute(
                text("INSERT INTO formas_pagamento (user_id, nome, e_cartao) VALUES (:uid, :n, :c)"),
                {"uid": user_id, "n": nome.strip(), "c": e_cartao}
            )
        limpar_cache_configs()
        return True
    except Exception as e:
        logger.error(f"Erro ao criar forma pagamento para {user_id}: {e}", exc_info=True)
        return False

def inicializar_dados_padrao(user_id: int) -> bool:
    """Semeia categorias e formas de pagamento padrão para um novo usuário."""
    try:
        cats_padrao = [
            ("Habitação", "Aluguel", "Despesa", "#e74c3c", "🏠"),
            ("Alimentação", "Mercado", "Despesa", "#f39c12", "🛒"),
            ("Lazer", "Restaurante", "Despesa", "#1abc9c", "🍔"),
            ("Renda", "Salário", "Receita", "#2ecc71", "💰"),
            ("Transporte", "Combustível", "Despesa", "#9b59b6", "⛽"),
            ("Investimentos", "Ações", "Investimento", "#3498db", "📈")
        ]
        fps_padrao = [
            ("Dinheiro", False),
            ("Cartão de Crédito", True),
            ("Pix", False)
        ]
        
        with engine.begin() as conn:
            for g, n, t, c, i in cats_padrao:
                conn.execute(
                    text("INSERT INTO categorias (user_id, grupo, nome, tipo, cor, icone) VALUES (:uid, :g, :n, :t, :c, :i) ON CONFLICT DO NOTHING"),
                    {"uid": user_id, "g": g, "n": n, "t": t, "c": c, "i": i}
                )
            for n, c in fps_padrao:
                conn.execute(
                    text("INSERT INTO formas_pagamento (user_id, nome, e_cartao) VALUES (:uid, :n, :c) ON CONFLICT DO NOTHING"),
                    {"uid": user_id, "n": n, "c": c}
                )
        limpar_cache_configs()
        return True
    except Exception as e:
        logger.error(f"Erro ao inicializar dados padrão para {user_id}: {e}", exc_info=True)
        return False

def atualizar_categorias(user_id: int, edicoes: dict, exclusoes: list) -> bool:
    """Atualiza ou exclui categorias do usuário."""
    try:
        with engine.begin() as conn:
            if exclusoes:
                ids_clean = tuple(int(x) for x in exclusoes)
                # Verifica se está em uso em transações
                for i in ids_clean:
                    cnt = conn.execute(
                        text("SELECT COUNT(*) FROM transacoes WHERE user_id = :uid AND categoria_id = :id"), 
                        {"uid": user_id, "id": i}
                    ).scalar()
                    if cnt > 0:
                        st.error(f"A categoria ID {i} está em uso por transações e não pode ser excluída.")
                        return False
                
                conn.execute(
                    text("DELETE FROM categorias WHERE user_id = :uid AND id IN :ids"), 
                    {"uid": user_id, "ids": ids_clean}
                )
            if edicoes:
                for i, ch in edicoes.items():
                    clauses = []
                    params = {"uid": user_id, "id": int(i)}
                    for k, v in ch.items():
                        if k in {"cor", "icone", "grupo", "nome", "tipo"}:
                            clauses.append(f"{k} = :{k}")
                            params[k] = v
                    if clauses:
                        conn.execute(
                            text(f"UPDATE categorias SET {', '.join(clauses)} WHERE user_id = :uid AND id = :id"), 
                            params
                        )
        limpar_cache_configs()
        return True
    except Exception as e:
        logger.error(f"Erro ao atualizar categorias do {user_id}: {e}", exc_info=True)
        st.error(f"Erro ao atualizar categorias: {e}")
        return False

def atualizar_formas_pagamento(user_id: int, edicoes: dict, exclusoes: list) -> bool:
    """Atualiza ou exclui métodos de pagamento do usuário."""
    try:
        with engine.begin() as conn:
            if exclusoes:
                ids_clean = tuple(int(x) for x in exclusoes)
                # Verifica se está em uso em transações
                for i in ids_clean:
                    cnt = conn.execute(
                        text("SELECT COUNT(*) FROM transacoes WHERE user_id = :uid AND forma_pagamento_id = :id"), 
                        {"uid": user_id, "id": i}
                    ).scalar()
                    if cnt > 0:
                        st.error(f"A forma de pagamento ID {i} está em uso por transações e não pode ser excluída.")
                        return False
                
                conn.execute(
                    text("DELETE FROM formas_pagamento WHERE user_id = :uid AND id IN :ids"), 
                    {"uid": user_id, "ids": ids_clean}
                )
            if edicoes:
                for i, ch in edicoes.items():
                    clauses = []
                    params = {"uid": user_id, "id": int(i)}
                    for k, v in ch.items():
                        if k in {"nome", "e_cartao"}:
                            clauses.append(f"{k} = :{k}")
                            params[k] = v
                    if clauses:
                        conn.execute(
                            text(f"UPDATE formas_pagamento SET {', '.join(clauses)} WHERE user_id = :uid AND id = :id"), 
                            params
                        )
        limpar_cache_configs()
        return True
    except Exception as e:
        logger.error(f"Erro ao atualizar formas pagamento de {user_id}: {e}", exc_info=True)
        st.error(f"Erro ao atualizar formas de pagamento: {e}")
        return False
