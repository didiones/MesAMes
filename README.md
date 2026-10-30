# Finanças Pessoais

## Rodar localmente
1. `pip install -r requirements.txt`
2. Copie `.streamlit/secrets.toml.example` para `.streamlit/secrets.toml` e preencha.
3. `streamlit run app.py`

Na primeira execução, as migrações criam ou ajustam as tabelas automaticamente, sem apagar dados.
Funciona tanto com um banco vazio (ex.: Neon novo) quanto com o banco antigo do Supabase.

## Senha do app
A senha não fica salva em texto. Gere o hash com `pip install bcrypt` e depois `python gerar_hash.py`,
e cole a linha `admin_password_hash = "..."` nos secrets. Após 5 tentativas erradas, o login fica
bloqueado por 5 minutos (o tempo dobra a cada novo bloqueio, até 1 hora).

## Backup e restauração
Em Configurações → Backup. Antes de restaurar, o app confere abas e colunas do arquivo, mostra o que
será importado, pede confirmação e guarda uma cópia dos dados atuais para download.

## Estrutura
- `app.py`: conexão, login e menu
- `core/db.py`: conexão, migrações versionadas, leitura e escrita
- `core/indicadores.py`: cálculos dos indicadores
- `core/importador.py`: leitura de OFX/CSV e categorização automática
- `core/ui.py`: filtros, cards, gráficos e confirmações
- `core/auth.py`: login
- `core/utils.py`: formatação, datas e período
- `gerar_hash.py`: gera o hash da senha do app
- `views/`: uma tela por arquivo

## Primeiros passos no app
- **Configurações → Cartões de crédito**: cadastre dia de fechamento e vencimento.
- **Categorias**: marque despesas fixas, natureza (necessidade/desejo) e orçamento mensal.
- **Recorrências**: cadastre contas mensais (aluguel, assinaturas, salário).
