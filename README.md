# Finanças Pessoais

## Rodar localmente
1. `pip install -r requirements.txt`
2. Copie `.streamlit/secrets.toml.example` para `.streamlit/secrets.toml` e preencha.
3. `streamlit run app.py`

Na primeira execução, as migrações ajustam o banco automaticamente (sem apagar dados).

## Estrutura
- `app.py`: conexão, login e menu
- `core/db.py`: conexão, migrações versionadas, leitura e escrita
- `core/indicadores.py`: cálculos dos indicadores
- `core/importador.py`: leitura de OFX/CSV e categorização automática
- `core/ui.py`: filtros, cards, gráficos e confirmações
- `core/auth.py`: login
- `core/utils.py`: formatação, datas e período
- `views/`: uma tela por arquivo

## Primeiros passos no app
- **Configurações → Cartões de crédito**: cadastre dia de fechamento e vencimento.
- **Categorias**: marque despesas fixas, natureza (necessidade/desejo) e orçamento mensal.
- **Recorrências**: cadastre contas mensais (aluguel, assinaturas, salário).
