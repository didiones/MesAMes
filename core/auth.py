"""Login: senha verificada por hash bcrypt, bloqueio após tentativas erradas e cookie assinado."""
import hashlib
import hmac
import logging
import threading
import time
from datetime import datetime, timedelta

import bcrypt
import extra_streamlit_components as stx
import streamlit as st

log = logging.getLogger("financas.auth")

SESSAO_MINUTOS = 20
MAX_TENTATIVAS = 5          # erros seguidos antes de bloquear
JANELA_SEGUNDOS = 15 * 60   # erros mais antigos que isso são esquecidos
BLOQUEIO_SEGUNDOS = 5 * 60  # duração do bloqueio (dobra a cada novo bloqueio, até 1 hora)


def cookie_manager():
    return stx.CookieManager(key="auth_manager_financas")


# ------------------------------------------------------------------ senha
def gerar_hash(senha: str) -> str:
    return bcrypt.hashpw(senha.encode(), bcrypt.gensalt(rounds=12)).decode()


def _senha_confere(senha: str) -> bool:
    """Prefere `admin_password_hash`; aceita `admin_password` em texto só como transição."""
    hash_salvo = st.secrets.get("admin_password_hash")
    if hash_salvo:
        try:
            return bcrypt.checkpw(senha.encode(), str(hash_salvo).encode())
        except ValueError:
            log.error("admin_password_hash inválido nos secrets")
            return False
    texto = st.secrets.get("admin_password")
    return bool(texto) and hmac.compare_digest(senha.encode(), str(texto).encode())


def usando_senha_em_texto() -> bool:
    return not st.secrets.get("admin_password_hash") and bool(st.secrets.get("admin_password"))


# ------------------------------------------------------------------ bloqueio (compartilhado entre sessões)
@st.cache_resource
def _registro_tentativas():
    """Fica no servidor: abrir outra aba ou limpar cookies não zera o contador."""
    return {"falhas": [], "bloqueado_ate": 0.0, "bloqueios": 0, "lock": threading.Lock()}


def segundos_bloqueado() -> int:
    r = _registro_tentativas()
    return max(0, int(r["bloqueado_ate"] - time.time()))


def _registrar_falha():
    r = _registro_tentativas()
    agora = time.time()
    with r["lock"]:
        r["falhas"] = [t for t in r["falhas"] if agora - t < JANELA_SEGUNDOS] + [agora]
        if len(r["falhas"]) >= MAX_TENTATIVAS:
            duracao = min(BLOQUEIO_SEGUNDOS * (2 ** r["bloqueios"]), 3600)
            r["bloqueado_ate"] = agora + duracao
            r["bloqueios"] += 1
            r["falhas"] = []
            log.warning("Login bloqueado por %s s após %s tentativas erradas", duracao, MAX_TENTATIVAS)


def _registrar_sucesso():
    r = _registro_tentativas()
    with r["lock"]:
        r["falhas"], r["bloqueios"] = [], 0


def tentativas_restantes() -> int:
    r = _registro_tentativas()
    agora = time.time()
    return MAX_TENTATIVAS - len([t for t in r["falhas"] if agora - t < JANELA_SEGUNDOS])


# ------------------------------------------------------------------ cookie de sessão
def _chave() -> bytes:
    segredo = (st.secrets.get("cookie_secret") or st.secrets.get("admin_password_hash")
               or st.secrets.get("admin_password"))
    return str(segredo).encode()


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


# ------------------------------------------------------------------ tela de login
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
        espera = segundos_bloqueado()
        if espera:
            st.error(f"Muitas tentativas erradas. Tente de novo em {espera // 60 + 1} minuto(s).")
        with st.form("login"):
            u = st.text_input("Usuário")
            p = st.text_input("Senha", type="password")
            entrar = st.form_submit_button("Entrar", type="primary", width="stretch", disabled=bool(espera))
        if entrar and not segundos_bloqueado():
            ok_u = hmac.compare_digest(u.encode(), str(st.secrets["admin_user"]).encode())
            ok_p = _senha_confere(p)  # sempre calcula o hash, mesmo com usuário errado
            if ok_u and ok_p:
                _registrar_sucesso()
                st.session_state["logout"] = False
                st.session_state["password_correct"] = True
                cm.set("auth_token", gerar_token(), expires_at=datetime.now() + timedelta(minutes=SESSAO_MINUTOS))
                time.sleep(0.3)  # dá tempo do componente gravar o cookie antes do rerun
                st.rerun()
            else:
                _registrar_falha()
                if segundos_bloqueado():
                    st.rerun()
                restantes = tentativas_restantes()
                st.error("Usuário ou senha incorretos."
                         + (f" Restam {restantes} tentativa(s) antes do bloqueio." if restantes <= 3 else ""))
    return False


def logout(cm):
    cm.delete("auth_token")
    st.session_state["logout"] = True
    st.session_state["password_correct"] = False
