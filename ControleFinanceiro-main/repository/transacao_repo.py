import streamlit as st
import pandas as pd
from sqlalchemy import text
from datetime import date, datetime, timedelta
import calendar
from core.config import engine
import logging

logger = logging.getLogger(__name__)

# =========================================================
#  FUNÇÕES AUXILIARES DE DATAS
# =========================================================
def add_months(source_date: date, months: int) -> date:
    """Adiciona/subtrai meses de uma data mantendo o dia dentro do limite do mês de destino."""
    month = source_date.month - 1 + months
    year = source_date.year + month // 12
    month = month % 12 + 1
    return date(year, month, min(source_date.day, calendar.monthrange(year, month)[1]))

# =========================================================
#  FUNÇÕES DE LEITURA (CACHE)
# =========================================================
@st.cache_data(ttl=300)
def carregar_dados(user_id: int) -> pd.DataFrame:
    """Traz todo o histórico de transações do usuário do banco."""
    query = """
        SELECT t.id, t.data, t.descricao, t.valor, c.grupo, c.nome as categoria, c.icone, t.tipo, t.pago,
               fp.nome as metodo_pagamento, t.cartao, t.parcela_atual, t.parcela_total, t.categoria_id, t.forma_pagamento_id
        FROM transacoes t
        JOIN categorias c ON t.categoria_id = c.id
        LEFT JOIN formas_pagamento fp ON t.forma_pagamento_id = fp.id
        WHERE t.user_id = :uid
        ORDER BY t.data DESC, t.id DESC
    """
    try:
        with engine.connect() as conn: 
            return pd.read_sql(text(query), conn, params={"uid": user_id})
    except Exception as e:
        logger.error(f"Erro ao carregar dados do usuário {user_id}: {e}", exc_info=True)
        return pd.DataFrame()

@st.cache_data(ttl=300)
def carregar_dados_ano(user_id: int, ano: int) -> pd.DataFrame:
    """Traz dados de transações do usuário para um ano específico."""
    query = """
        SELECT t.data, t.valor, c.grupo, c.nome as categoria, t.tipo, t.pago, c.cor, c.icone
        FROM transacoes t
        JOIN categorias c ON t.categoria_id = c.id
        WHERE t.user_id = :uid AND EXTRACT(YEAR FROM t.data) = :ano 
        ORDER BY t.data
    """
    try:
        with engine.connect() as conn: 
            return pd.read_sql(text(query), conn, params={"uid": user_id, "ano": ano})
    except Exception as e:
        logger.error(f"Erro ao carregar dados do ano {ano} para {user_id}: {e}", exc_info=True)
        return pd.DataFrame()

@st.cache_data(ttl=60)
def carregar_ultimos_lancamentos(user_id: int) -> pd.DataFrame:
    """Traz as últimas 15 transações lançadas pelo usuário."""
    query = """
        SELECT t.data, t.descricao, t.valor, c.grupo, c.nome as categoria, c.icone, t.tipo, t.pago, fp.nome as metodo_pagamento
        FROM transacoes t
        JOIN categorias c ON t.categoria_id = c.id
        LEFT JOIN formas_pagamento fp ON t.forma_pagamento_id = fp.id
        WHERE t.user_id = :uid
        ORDER BY t.id DESC LIMIT 15
    """
    try:
        with engine.connect() as conn: 
            return pd.read_sql(text(query), conn, params={"uid": user_id})
    except Exception as e:
        logger.error(f"Erro ao carregar últimos lançamentos de {user_id}: {e}", exc_info=True)
        return pd.DataFrame()

def limpar_cache_dados():
    """Limpa o cache das transações."""
    carregar_dados.clear()
    carregar_dados_ano.clear()
    carregar_ultimos_lancamentos.clear()

# =========================================================
#  FUNÇÕES DE ESCRITA E ATUALIZAÇÃO
# =========================================================
def salvar_transacao(user_id: int, data: date, desc: str, val: float, cat_id: int, tipo: str, pago: bool, fp_id: int, cartao: str, pa: int = 1, pt: int = 1) -> bool:
    """Grava uma única transação no banco."""
    query = text("""
        INSERT INTO transacoes (user_id, data, descricao, valor, categoria_id, tipo, pago, forma_pagamento_id, cartao, parcela_atual, parcela_total) 
        VALUES (:uid, :d, :desc, :v, :c, :t, :p, :fp, :card, :pa, :pt)
    """)
    try:
        with engine.begin() as conn:
            conn.execute(query, {
                "uid": user_id, "d": data, "desc": desc.strip(), "v": val, "c": cat_id, 
                "t": tipo, "p": pago, "fp": fp_id, "card": cartao.strip() if cartao else None, "pa": pa, "pt": pt
            })
        limpar_cache_dados()
        return True
    except Exception as e:
        logger.error(f"Erro ao salvar transacao para {user_id}: {e}", exc_info=True)
        return False

def salvar_parcelamento(user_id: int, dt_ini: date, desc_base: str, val: float, cat_id: int, tipo: str, fp_id: int, cartao: str, p_ini: int, p_tot: int, retro: bool, pg_prim: bool) -> bool:
    """Gera parcelas futuras e retroativas no banco de dados."""
    query = text("""
        INSERT INTO transacoes (user_id, data, descricao, valor, categoria_id, tipo, pago, forma_pagamento_id, cartao, parcela_atual, parcela_total) 
        VALUES (:uid, :d, :desc, :v, :c, :t, :p, :fp, :card, :pa, :pt)
    """)
    try:
        with engine.begin() as conn:
            # Geração das parcelas retroativas como pagas
            if p_ini > 1 and retro:
                for i in range(1, p_ini):
                    conn.execute(query, {
                        "uid": user_id, "d": add_months(dt_ini, -(p_ini-i)), "desc": f"{desc_base} ({i}/{p_tot})", 
                        "v": val, "c": cat_id, "t": tipo, "p": True, "fp": fp_id, "card": cartao, "pa": i, "pt": p_tot
                    })
            # Geração das parcelas atuais e futuras
            for i in range((p_tot - p_ini) + 1):
                pago = True if (i == 0 and pg_prim) else False
                conn.execute(query, {
                    "uid": user_id, "d": add_months(dt_ini, i), "desc": f"{desc_base} ({p_ini+i}/{p_tot})", 
                    "v": val, "c": cat_id, "t": tipo, "p": pago, "fp": fp_id, "card": cartao, "pa": p_ini+i, "pt": p_tot
                })
        limpar_cache_dados()
        return True
    except Exception as e:
        logger.error(f"Erro ao salvar parcelas para {user_id}: {e}", exc_info=True)
        return False

def baixar_contas_rapido(user_id: int, ids: list) -> bool:
    """Atualiza o status de pagamento de várias transações pendentes do usuário para Pago."""
    if not ids:
        return True
    try:
        ids_clean = tuple(int(x) for x in ids)
        with engine.begin() as conn: 
            conn.execute(
                text("UPDATE transacoes SET pago = TRUE WHERE user_id = :uid AND id IN :ids"), 
                {"uid": user_id, "ids": ids_clean}
            )
        limpar_cache_dados()
        return True
    except Exception as e:
        logger.error(f"Erro ao baixar contas rápidas para {user_id}: {e}", exc_info=True)
        return False

def atualizar_transacoes(user_id: int, edicoes: dict, exclusoes: list) -> bool:
    """Atualiza e/ou remove transações com isolamento de usuário."""
    try:
        with engine.begin() as conn:
            if exclusoes:
                ids_clean = tuple(int(x) for x in exclusoes)
                conn.execute(
                    text("DELETE FROM transacoes WHERE user_id = :uid AND id IN :ids"), 
                    {"uid": user_id, "ids": ids_clean}
                )
            if edicoes:
                for i, ch in edicoes.items():
                    clauses = []
                    params = {"uid": user_id, "id": int(i)}
                    for k, v in ch.items():
                        if k in {"pago", "valor", "data", "descricao", "tipo", "categoria_id", "forma_pagamento_id", "cartao", "parcela_atual", "parcela_total"}:
                            clauses.append(f"{k} = :{k}")
                            params[k] = v
                    if clauses:
                        conn.execute(
                            text(f"UPDATE transacoes SET {', '.join(clauses)} WHERE user_id = :uid AND id = :id"), 
                            params
                        )
        limpar_cache_dados()
        return True
    except Exception as e:
        logger.error(f"Erro ao atualizar transações do usuário {user_id}: {e}", exc_info=True)
        st.error(f"Erro ao salvar alterações das transações: {e}")
        return False

def replicar_lancamento(user_id: int, id_origem: int, num_repeticoes: int) -> bool:
    """Duplica uma transação existente projetando-a para meses futuros."""
    try:
        with engine.begin() as conn:
            res = conn.execute(
                text("SELECT * FROM transacoes WHERE user_id = :uid AND id = :id"), 
                {"uid": user_id, "id": id_origem}
            ).fetchone()
            if not res: 
                return False
            
            # Mapeamento do Row retornado (garantindo compatibilidade com SQLAlchemy 1.4/2.0)
            # Row expõe valores como tupla indexada
            # Campos: id, user_id, data, descricao, valor, categoria_id, tipo, pago, forma_pagamento_id, cartao, parcela_atual, parcela_total
            orig_data = res[2] if isinstance(res[2], date) else datetime.strptime(res[2], "%Y-%m-%d").date()
            base_desc = res[3].split('(')[0].strip()
            
            insert_q = text("""
                INSERT INTO transacoes (user_id, data, descricao, valor, categoria_id, tipo, pago, forma_pagamento_id, cartao) 
                VALUES (:uid, :data, :desc, :val, :cat, :tipo, :pago, :fid, :cartao)
            """)
            
            for i in range(1, num_repeticoes + 1):
                conn.execute(insert_q, {
                    "uid": user_id,
                    "data": add_months(orig_data, i), 
                    "desc": base_desc, 
                    "val": res[4], # valor
                    "cat": res[5], # categoria_id
                    "tipo": res[6], # tipo
                    "pago": False,
                    "fid": res[8], # forma_pagamento_id
                    "cartao": res[9] # cartao
                })
        limpar_cache_dados()
        return True
    except Exception as e:
        logger.error(f"Erro ao replicar lançamento {id_origem} para {user_id}: {e}", exc_info=True)
        st.error(f"Erro ao replicar: {e}")
        return False
