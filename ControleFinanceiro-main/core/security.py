import hashlib
import secrets
import base64
import hmac
import json
from datetime import datetime, timedelta
import streamlit as st
import extra_streamlit_components as stx

def hash_password(password: str) -> str:
    """Gera um hash PBKDF2-SHA256 seguro com salt aleatório."""
    salt = secrets.token_bytes(16)
    # 100.000 iterações são padrão para PBKDF2
    key = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
    salt_b64 = base64.b64encode(salt).decode('utf-8')
    key_b64 = base64.b64encode(key).decode('utf-8')
    return f"pbkdf2_sha256$100000${salt_b64}${key_b64}"

def verify_password(password: str, hashed: str) -> bool:
    """Verifica se a senha corresponde ao hash gerado."""
    try:
        parts = hashed.split('$')
        if len(parts) != 4 or parts[0] != 'pbkdf2_sha256':
            return False
        iterations = int(parts[1])
        salt = base64.b64decode(parts[2].encode('utf-8'))
        original_key = base64.b64decode(parts[3].encode('utf-8'))
        
        new_key = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, iterations)
        return secrets.compare_digest(original_key, new_key)
    except Exception:
        return False

def generate_session_token(username: str, user_id: int) -> str:
    """Gera um token de sessão criptograficamente assinado com expiração de 20 minutos."""
    # Utiliza chave secreta das secrets ou uma fallback segura
    secret_key = st.secrets.get("SECRET_KEY", "default_secret_key_controle_financeiro_321").encode('utf-8')
    expires = (datetime.utcnow() + timedelta(minutes=20)).isoformat()
    
    payload = json.dumps({"user": username, "user_id": user_id, "expires": expires}).encode('utf-8')
    signature = hmac.new(secret_key, payload, hashlib.sha256).digest()
    
    token_bytes = base64.b64encode(payload + b"." + signature)
    return token_bytes.decode('utf-8')

def verify_session_token(token: str) -> dict:
    """Valida o token e retorna o payload contendo o usuário e id caso válido."""
    if not token:
        return None
    try:
        secret_key = st.secrets.get("SECRET_KEY", "default_secret_key_controle_financeiro_321").encode('utf-8')
        token_bytes = base64.b64decode(token.encode('utf-8'))
        payload, signature = token_bytes.rsplit(b".", 1)
        
        # Verifica a assinatura HMAC
        expected_sig = hmac.new(secret_key, payload, hashlib.sha256).digest()
        if not hmac.compare_digest(signature, expected_sig):
            return None
            
        # Verifica a expiração
        data = json.loads(payload.decode('utf-8'))
        expiration = datetime.fromisoformat(data["expires"])
        if datetime.utcnow() > expiration:
            return None
            
        return data
    except Exception:
        return None

def get_cookie_manager():
    """Retorna uma instância persistente do CookieManager no session state."""
    if "cookie_manager" not in st.session_state:
        st.session_state.cookie_manager = stx.CookieManager(key="auth_manager_final_v15_receita_prevista")
    return st.session_state.cookie_manager
