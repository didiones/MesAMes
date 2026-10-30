"""Gera o hash bcrypt da senha do app. Uso: python gerar_hash.py

A senha é digitada sem aparecer na tela e não fica salva em lugar nenhum.
Copie a linha exibida para os secrets do Streamlit.
"""
from getpass import getpass

import bcrypt

senha = getpass("Nova senha do app: ")
if senha != getpass("Repita a senha: "):
    raise SystemExit("As senhas não conferem.")
if len(senha) < 10:
    raise SystemExit("Use pelo menos 10 caracteres.")
print("\nCole esta linha nos secrets do Streamlit:\n")
print(f'admin_password_hash = "{bcrypt.hashpw(senha.encode(), bcrypt.gensalt(rounds=12)).decode()}"')
