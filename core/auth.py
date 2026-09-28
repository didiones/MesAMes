"""Login com cookie assinado (mesma lógica da versão anterior, apenas isolada em módulo)."""
import hashlib
import hmac
import time
from datetime import datetime, timedelta

import extra_streamlit_components as stx
import streamlit as st

SESSAO_MINUTOS = 20


def cookie_manager():
    return stx.CookieManager(key="auth_manager_financas")


def _chave() -> bytes:
    return str(st.secrets.get("cookie_secret", st.secrets["admin_password"])).encode()


def _assinar(expira_ts: int) -> str:
    msg = f"{st.secrets['admin_user']}|{expira_ts}".encode()
    return hmac.new(_chave(), msg, hashlib.sha256).hexdigest()


def gerar_token() -> str:
    exp = int(time.time()) + SESSAO_MINUTOS * 60
    return f"{exp}.{_assinar(exp)}"


def token_valido(token) -> bool:
    try:
        exp_str, assinatura = str(token).split(".", 1)
        exp = int(exp_str)
    except (ValueError, AttributeError):
        return False
    return exp > time.time() and hmac.compare_digest(assinatura, _assinar(exp))


def check_password(cm) -> bool:
    if st.session_state.get("logout", False):
        st.session_state["password_correct"] = False
    elif st.session_state.get("password_correct", False):
        return True
    else:
        token = cm.get(cookie="auth_token")
        if token and token_valido(token):
            st.session_state["password_correct"] = True
            return True

    _, meio, _ = st.columns([1, 1.2, 1])
    with meio:
        st.markdown("### 💰 Finanças Pessoais")
        with st.form("login"):
            u = st.text_input("Usuário")
            p = st.text_input("Senha", type="password")
            if st.form_submit_button("Entrar", type="primary", width="stretch"):
                ok_u = hmac.compare_digest(u.encode(), str(st.secrets["admin_user"]).encode())
                ok_p = hmac.compare_digest(p.encode(), str(st.secrets["admin_password"]).encode())
                if ok_u and ok_p:
                    st.session_state["logout"] = False
                    st.session_state["password_correct"] = True
                    cm.set("auth_token", gerar_token(),
                           expires_at=datetime.now() + timedelta(minutes=SESSAO_MINUTOS))
                    time.sleep(0.3)  # dá tempo do componente gravar o cookie antes do rerun
                    st.rerun()
                else:
                    st.error("Usuário ou senha incorretos.")
    return False


def logout(cm):
    cm.delete("auth_token")
    st.session_state["logout"] = True
    st.session_state["password_correct"] = False
