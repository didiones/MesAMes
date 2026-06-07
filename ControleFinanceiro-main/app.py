import streamlit as st
import time
from datetime import datetime, timedelta

# Configuração de Página deve ser a PRIMEIRA instrução Streamlit
st.set_page_config(page_title="Finanças Pessoais", page_icon="💰", layout="wide")

# CSS Customizado (Aparência Premium)
st.markdown("""
    <style>
    div[data-testid="stMetric"] { display: none; } 
    .stDataFrame { border: 1px solid #333; border-radius: 5px; }
    div[data-testid="stSidebar"] .stCheckbox { margin-bottom: -15px !important; }
    .insight-box { background-color: #151515; border-left: 4px solid #3498db; padding: 15px; margin: 15px 0; border-radius: 4px; color: #eee; font-size: 1rem; }
    .insight-label { color: #3498db; font-weight: bold; margin-right: 8px; }
    </style>
    """, unsafe_allow_html=True)

# Imports locais
from core.security import verify_session_token, generate_session_token, get_cookie_manager, verify_password
from repository.usuario_repo import buscar_usuario, cadastrar_usuario
from repository.categoria_repo import inicializar_dados_padrao
from ui.utils import MAPA_MESES

# Inicializa Cookie Manager com segurança no estado da sessão
cookie_manager = get_cookie_manager()

def check_password() -> bool:
    """Verifica e gerencia o fluxo de autenticação (Login e Cadastro)."""
    # 1. Caso tenha clicado em Logout explicitamente
    if st.session_state.get('logout', False): 
        st.session_state['password_correct'] = False
        return False
        
    # 2. Caso já esteja autenticado na sessão ativa
    if st.session_state.get('password_correct', False): 
        return True
        
    # 3. Caso não esteja logado, tenta recuperar sessão salva via Cookie assinado
    token = cookie_manager.get(cookie="auth_token")
    if token:
        user_data = verify_session_token(token)
        if user_data:
            st.session_state['password_correct'] = True
            st.session_state['user'] = user_data['user']
            st.session_state['user_id'] = user_data['user_id']
            return True
            
    # --- INTERFACE DE LOGIN / CADASTRO ---
    st.markdown("<h2 style='text-align: center; margin-top: 50px;'>💰 Controle Financeiro Pessoal</h2>", unsafe_allow_html=True)
    
    c1, c2, c3 = st.columns([1, 1.5, 1])
    with c2:
        tab_login, tab_cadastro = st.tabs(["🔒 Entrar", "🆕 Cadastrar Conta"])
        
        # TAB 1: LOGIN DE USUÁRIO
        with tab_login:
            with st.form("login_form"):
                u = st.text_input("Usuário", placeholder="Nome de usuário")
                p = st.text_input("Senha", type="password", placeholder="Digite sua senha")
                
                if st.form_submit_button("Entrar no Painel", use_container_width=True):
                    if u and p:
                        db_user = buscar_usuario(u)
                        if db_user and verify_password(p, db_user['senha_hash']):
                            st.session_state['logout'] = False
                            st.session_state['password_correct'] = True
                            st.session_state['user'] = db_user['usuario']
                            st.session_state['user_id'] = db_user['id']
                            
                            # Gera Cookie seguro assinado por 20 minutos
                            token_val = generate_session_token(db_user['usuario'], db_user['id'])
                            expires = datetime.utcnow() + timedelta(minutes=20)
                            cookie_manager.set("auth_token", token_val, expires_at=expires)
                            
                            st.toast(f"Bem-vindo, {db_user['usuario']}!", icon="👋")
                            time.sleep(0.5)
                            st.rerun()
                        else:
                            st.error("Usuário ou senha incorretos.")
                    else:
                        st.error("Preencha todos os campos.")
                        
        # TAB 2: CADASTRO DE NOVO USUÁRIO
        with tab_cadastro:
            with st.form("register_form"):
                new_u = st.text_input("Nome de Usuário", placeholder="Ex: didio")
                new_p = st.text_input("Senha", type="password", placeholder="Mínimo 6 caracteres")
                confirm_p = st.text_input("Confirme a Senha", type="password")
                
                if st.form_submit_button("Criar Minha Conta", use_container_width=True):
                    if new_u and new_p and confirm_p:
                        if new_p != confirm_p:
                            st.error("As senhas não coincidem.")
                        elif len(new_p) < 6:
                            st.error("A senha deve conter ao menos 6 caracteres.")
                        else:
                            # Tenta cadastrar no banco
                            if cadastrar_usuario(new_u, new_p):
                                created_user = buscar_usuario(new_u)
                                if created_user:
                                    # Semeia automaticamente as categorias e métodos de pagamento iniciais do usuário
                                    inicializar_dados_padrao(created_user['id'])
                                st.success("Conta criada com sucesso! Faça login na aba ao lado.")
                            else:
                                st.error("Erro ao cadastrar. Este nome de usuário já está em uso.")
                    else:
                        st.error("Preencha todos os campos de cadastro.")
                        
    return False

# Executa fluxo de Login. Se não autenticado, para a execução do app.
if not check_password(): 
    st.stop()

# --- RECUPERAÇÃO DAS INFORMAÇÕES DE SESSÃO ---
user_active = st.session_state['user']
user_id_active = st.session_state['user_id']

# --- SIDEBAR E FILTROS ---
with st.sidebar:
    st.markdown(f"<h3>👤 {user_active}</h3>", unsafe_allow_html=True)
    st.caption("Painel Financeiro Multiusuário")
    
    # Navegação entre Páginas
    menu = st.radio(
        "Menu do Sistema", 
        ["Dashboard", "Relatório Anual", "Extrato & Gestão", "Lançamentos", "Categorias", "Configurações"], 
        key="nav_menu"
    )
    st.markdown("---")
    
    # Exibição de filtros apenas para páginas de relatórios/gráficos
    ano_selecionado = datetime.today().year
    meses_selecionados = []
    
    if menu in ["Dashboard", "Extrato & Gestão", "Relatório Anual"]:
        st.header("Filtros do Painel")
        hoje = datetime.today()
        ano_selecionado = st.number_input("Ano de Referência", 2020, 2030, hoje.year)
        
        if menu != "Relatório Anual":
            st.subheader("Meses")
            with st.container():
                for i in range(1, 13):
                    nome_mes = MAPA_MESES[i]
                    # Seleciona o mês atual por padrão
                    padrao = True if i == hoje.month else False
                    if st.checkbox(nome_mes, value=padrao, key=f"chk_{i}"): 
                        meses_selecionados.append(nome_mes)
            if not meses_selecionados: 
                st.error("Selecione pelo menos um mês.")
                st.stop()

    # Botão de Logout
    if st.button("🚪 Sair do Sistema", use_container_width=True):
        cookie_manager.delete("auth_token")
        st.session_state['logout'] = True
        st.session_state['password_correct'] = False
        st.session_state['user'] = None
        st.session_state['user_id'] = None
        st.rerun()

# --- ROTEAMENTO E RENDERIZAÇÃO DAS PÁGINAS ---
if menu == "Dashboard":
    from ui.dashboard_page import render_dashboard_page
    render_dashboard_page(user_id_active, ano_selecionado, meses_selecionados)

elif menu == "Relatório Anual":
    from ui.relatorio_anual_page import render_relatorio_anual_page
    render_relatorio_anual_page(user_id_active, ano_selecionado)

elif menu == "Extrato & Gestão":
    from ui.extrato_page import render_extrato_page
    render_extrato_page(user_id_active, ano_selecionado, meses_selecionados)

elif menu == "Lançamentos":
    from ui.lancamentos_page import render_lancamentos_page
    render_lancamentos_page(user_id_active)

elif menu == "Categorias":
    from ui.categorias_page import render_categorias_page
    render_categorias_page(user_id_active)

elif menu == "Configurações":
    from ui.configuracoes_page import render_configuracoes_page
    render_configuracoes_page(user_id_active)
