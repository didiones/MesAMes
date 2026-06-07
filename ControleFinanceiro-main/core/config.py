import streamlit as st
from sqlalchemy import create_engine
import logging

# Configuração de logs padrão
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ControleFinanceiro")

@st.cache_resource
def get_engine():
    """Inicializa o pool de conexões com o banco de dados via SQLAlchemy."""
    try:
        db_url = st.secrets["DB_URL"]
        return create_engine(
            db_url,
            pool_pre_ping=True,
            pool_size=10,
            max_overflow=20,
            pool_recycle=1800
        )
    except KeyError:
        logger.critical("A variável de ambiente/secret 'DB_URL' não foi encontrada.")
        st.error("Erro de Configuração: DB_URL não encontrada.")
        st.stop()
    except Exception as e:
        logger.critical(f"Falha ao criar o engine de banco de dados: {e}", exc_info=True)
        st.error("Erro crítico ao conectar ao banco de dados.")
        st.stop()

engine = get_engine()
