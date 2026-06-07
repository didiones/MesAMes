from core.config import engine
from core.security import hash_password
from sqlalchemy import text
import logging

logger = logging.getLogger(__name__)

def cadastrar_usuario(username: str, password_raw: str) -> bool:
    """Insere um novo usuário com senha hash no banco de dados."""
    try:
        senha_hash = hash_password(password_raw)
        with engine.begin() as conn:
            conn.execute(
                text("INSERT INTO usuarios (usuario, senha_hash) VALUES (:u, :s)"),
                {"u": username.strip(), "s": senha_hash}
            )
        return True
    except Exception as e:
        logger.error(f"Erro ao cadastrar usuário {username}: {e}", exc_info=True)
        return False

def buscar_usuario(username: str) -> dict:
    """Busca dados de um usuário pelo nome."""
    try:
        with engine.connect() as conn:
            res = conn.execute(
                text("SELECT id, usuario, senha_hash FROM usuarios WHERE usuario = :u"),
                {"u": username.strip()}
            ).fetchone()
            if res:
                return {"id": res[0], "usuario": res[1], "senha_hash": res[2]}
        return None
    except Exception as e:
        logger.error(f"Erro ao buscar usuário {username}: {e}", exc_info=True)
        return None
