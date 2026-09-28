"""Acesso ao banco (Supabase/PostgreSQL): conexão, migrações, leitura e escrita."""
from __future__ import annotations

import io
import logging
from datetime import date

import pandas as pd
import streamlit as st
from sqlalchemy import bindparam, create_engine, text
from sqlalchemy.engine import make_url

from core.utils import add_months, descricao_base, dia_seguro, primeiro_dia

log = logging.getLogger("financas.db")

TABELAS_BACKUP = ["cartoes", "formas_pagamento", "categorias", "recorrencias", "transacoes"]  # ordem de inserção
COLUNAS_EDITAVEIS = {
    "transacoes": {"data", "descricao", "valor", "categoria_id", "tipo", "pago", "forma_pagamento_id",
                   "cartao", "cartao_id", "parcela_atual", "parcela_total"},
    "categorias": {"grupo", "nome", "tipo", "cor", "icone", "orcamento", "fixa", "natureza"},
    "formas_pagamento": {"nome", "e_cartao"},
    "cartoes": {"nome", "dia_fechamento", "dia_vencimento", "limite"},
    "recorrencias": {"descricao", "valor", "categoria_id", "tipo", "forma_pagamento_id", "cartao_id",
                     "dia", "inicio", "fim", "ativo", "gerar_pago"},
}
# tabela -> coluna de transacoes que a referencia (bloqueia exclusão de itens em uso)
REFERENCIAS = {"categorias": "categoria_id", "formas_pagamento": "forma_pagamento_id", "cartoes": "cartao_id"}


# =========================================================== conexão
def _detectar_driver() -> str:
    try:
        import psycopg  # noqa: F401
        return "psycopg"
    except ImportError:
        pass
    try:
        import psycopg2  # noqa: F401
        return "psycopg2"
    except ImportError:
        raise RuntimeError("Nenhum driver PostgreSQL instalado. Adicione 'psycopg[binary]' ao requirements.txt.")


def _montar_url(url_bruta: str, driver: str):
    url = make_url(url_bruta.strip()).set(drivername=f"postgresql+{driver}")
    if "sslmode" not in url.query and url.host not in ("localhost", "127.0.0.1"):
        url = url.update_query_dict({"sslmode": "require"})
    return url


@st.cache_resource
def get_engine():
    driver = _detectar_driver()
    connect_args = {"connect_timeout": 10}
    if driver == "psycopg":
        connect_args["prepare_threshold"] = None  # pooler do Supabase (porta 6543)
    eng = create_engine(_montar_url(st.secrets["DB_URL"], driver), pool_pre_ping=True,
                        pool_recycle=300, connect_args=connect_args)
    with eng.connect() as conn:
        conn.execute(text("SELECT 1"))
    return eng


def engine():
    return get_engine()


# =========================================================== migrações versionadas
MIGRACOES = [
    (1, "Colunas de parcelamento, cor e ícone", [
        "ALTER TABLE transacoes ADD COLUMN IF NOT EXISTS parcela_atual INTEGER",
        "ALTER TABLE transacoes ADD COLUMN IF NOT EXISTS parcela_total INTEGER",
        "ALTER TABLE categorias ADD COLUMN IF NOT EXISTS cor VARCHAR",
        "ALTER TABLE categorias ADD COLUMN IF NOT EXISTS icone VARCHAR",
    ]),
    (2, "Orçamento, fixa/variável e natureza nas categorias", [
        "ALTER TABLE categorias ADD COLUMN IF NOT EXISTS orcamento NUMERIC(12,2)",
        "ALTER TABLE categorias ADD COLUMN IF NOT EXISTS fixa BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE categorias ADD COLUMN IF NOT EXISTS natureza VARCHAR NOT NULL DEFAULT 'Necessidade'",
    ]),
    (3, "Cadastro de cartões", [
        """CREATE TABLE IF NOT EXISTS cartoes (
            id SERIAL PRIMARY KEY,
            nome VARCHAR NOT NULL,
            dia_fechamento INTEGER NOT NULL CHECK (dia_fechamento BETWEEN 1 AND 31),
            dia_vencimento INTEGER NOT NULL CHECK (dia_vencimento BETWEEN 1 AND 31),
            limite NUMERIC(12,2)
        )""",
        "ALTER TABLE transacoes ADD COLUMN IF NOT EXISTS cartao_id INTEGER",
    ]),
    (4, "Lançamentos recorrentes", [
        """CREATE TABLE IF NOT EXISTS recorrencias (
            id SERIAL PRIMARY KEY,
            descricao VARCHAR NOT NULL,
            valor NUMERIC(12,2) NOT NULL,
            categoria_id INTEGER NOT NULL,
            tipo VARCHAR NOT NULL,
            forma_pagamento_id INTEGER,
            cartao_id INTEGER,
            dia INTEGER NOT NULL CHECK (dia BETWEEN 1 AND 31),
            inicio DATE NOT NULL,
            fim DATE,
            ativo BOOLEAN NOT NULL DEFAULT TRUE,
            gerar_pago BOOLEAN NOT NULL DEFAULT FALSE,
            ultima_geracao DATE
        )""",
        "ALTER TABLE transacoes ADD COLUMN IF NOT EXISTS recorrencia_id INTEGER",
    ]),
    (5, "Índices de desempenho", [
        "CREATE INDEX IF NOT EXISTS idx_transacoes_data ON transacoes (data)",
        "CREATE INDEX IF NOT EXISTS idx_transacoes_categoria ON transacoes (categoria_id)",
        "CREATE INDEX IF NOT EXISTS idx_transacoes_cartao_data ON transacoes (cartao_id, data)",
    ]),
]


@st.cache_resource
def aplicar_migracoes() -> list[str]:
    """Aplica, em ordem, as migrações ainda não registradas em schema_migrations."""
    aplicadas = []
    with engine().begin() as conn:
        conn.execute(text("""CREATE TABLE IF NOT EXISTS schema_migrations (
            versao INTEGER PRIMARY KEY, descricao VARCHAR, aplicada_em TIMESTAMPTZ DEFAULT now())"""))
        feitas = {r[0] for r in conn.execute(text("SELECT versao FROM schema_migrations"))}
    for versao, desc, comandos in MIGRACOES:
        if versao in feitas:
            continue
        with engine().begin() as conn:  # cada versão é atômica
            for cmd in comandos:
                conn.execute(text(cmd))
            conn.execute(text("INSERT INTO schema_migrations (versao, descricao) VALUES (:v, :d)"),
                         {"v": versao, "d": desc})
        log.info("Migração %s aplicada: %s", versao, desc)
        aplicadas.append(f"{versao}: {desc}")
    _seed()
    limpar_cache()
    return aplicadas


def _seed():
    with engine().begin() as conn:
        if conn.execute(text("SELECT COUNT(*) FROM categorias")).scalar() == 0:
            padroes = [("Habitação", "Aluguel", "Despesa", True), ("Alimentação", "Mercado", "Despesa", False),
                       ("Renda", "Salário", "Receita", False)]
            conn.execute(text("INSERT INTO categorias (grupo, nome, tipo, fixa) VALUES (:g, :n, :t, :f)"),
                         [{"g": g, "n": n, "t": t, "f": f} for g, n, t, f in padroes])
        if conn.execute(text("SELECT COUNT(*) FROM formas_pagamento")).scalar() == 0:
            conn.execute(text("INSERT INTO formas_pagamento (nome, e_cartao) VALUES (:n, :c)"),
                         [{"n": "Pix", "c": False}, {"n": "Débito", "c": False}, {"n": "Cartão de crédito", "c": True}])


# =========================================================== leitura
def limpar_cache():
    carregar_transacoes.clear()
    carregar_ultimos.clear()
    carregar_auxiliares.clear()
    investimento_acumulado.clear()


def _tratar(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    df["data"] = pd.to_datetime(df["data"])
    df["valor"] = pd.to_numeric(df["valor"], errors="coerce").fillna(0.0).astype(float)
    df["tipo"] = df["tipo"].astype(str).str.strip()
    df["pago"] = df["pago"].fillna(False).astype(bool)
    if "fixa" in df:
        df["fixa"] = df["fixa"].fillna(False).astype(bool)
    return df


SQL_TRANSACOES = """
    SELECT t.id, t.data, t.descricao, t.valor, t.tipo, t.pago,
           t.categoria_id, t.forma_pagamento_id, t.cartao_id, t.recorrencia_id,
           t.parcela_atual, t.parcela_total,
           c.grupo, c.nome AS categoria, c.icone, c.cor, c.fixa, c.natureza,
           fp.nome AS metodo_pagamento,
           COALESCE(k.nome, t.cartao) AS cartao
    FROM transacoes t
    JOIN categorias c ON t.categoria_id = c.id
    LEFT JOIN formas_pagamento fp ON t.forma_pagamento_id = fp.id
    LEFT JOIN cartoes k ON t.cartao_id = k.id
"""


@st.cache_data(ttl=300, show_spinner=False)
def carregar_transacoes(inicio: date, fim: date) -> pd.DataFrame:
    """Transações com data em [inicio, fim) — o filtro roda no banco e usa o índice de data."""
    q = text(SQL_TRANSACOES + " WHERE t.data >= :ini AND t.data < :fim ORDER BY t.data DESC, t.id DESC")
    with engine().connect() as conn:
        return _tratar(pd.read_sql(q, conn, params={"ini": inicio, "fim": fim}))


@st.cache_data(ttl=60, show_spinner=False)
def carregar_ultimos(n: int = 15) -> pd.DataFrame:
    q = text(SQL_TRANSACOES + " ORDER BY t.id DESC LIMIT :n")
    with engine().connect() as conn:
        return _tratar(pd.read_sql(q, conn, params={"n": n}))


@st.cache_data(ttl=3600, show_spinner=False)
def carregar_auxiliares() -> dict[str, pd.DataFrame]:
    with engine().connect() as conn:
        dados = {
            "categorias": pd.read_sql(text("SELECT * FROM categorias ORDER BY grupo, nome"), conn),
            "formas": pd.read_sql(text("SELECT * FROM formas_pagamento ORDER BY nome"), conn),
            "cartoes": pd.read_sql(text("SELECT * FROM cartoes ORDER BY nome"), conn),
            "recorrencias": pd.read_sql(text("SELECT * FROM recorrencias ORDER BY ativo DESC, descricao"), conn),
        }
    cats = dados["categorias"]
    cats["tipo"] = cats["tipo"].astype(str).str.strip()
    cats["fixa"] = cats["fixa"].fillna(False).astype(bool)
    cats["natureza"] = cats["natureza"].fillna("Necessidade")
    cats["orcamento"] = pd.to_numeric(cats["orcamento"], errors="coerce")
    dados["formas"]["e_cartao"] = dados["formas"]["e_cartao"].fillna(False).astype(bool)
    return dados


@st.cache_data(ttl=300, show_spinner=False)
def investimento_acumulado(ate: date) -> float:
    q = text("SELECT COALESCE(SUM(valor), 0) FROM transacoes WHERE tipo = 'Investimento' AND pago AND data <= :ate")
    with engine().connect() as conn:
        return float(conn.execute(q, {"ate": ate}).scalar() or 0)


def historico_descricoes(meses: int = 18) -> pd.DataFrame:
    q = text("""SELECT t.descricao, t.categoria_id, t.tipo, t.data FROM transacoes t
                WHERE t.data >= :ini ORDER BY t.data DESC""")
    with engine().connect() as conn:
        return pd.read_sql(q, conn, params={"ini": add_months(date.today(), -meses)})


# =========================================================== escrita
def _nativo(v):
    """Converte numpy/pandas (int64, bool_, Timestamp) para tipos aceitos pelo driver."""
    if isinstance(v, pd.Timestamp):
        return v.date()
    if v is not None and not isinstance(v, (str, bytes)) and pd.isna(v):
        return None
    return v.item() if hasattr(v, "item") else v


SQL_INSERT_TRANSACAO = text("""
    INSERT INTO transacoes (data, descricao, valor, categoria_id, tipo, pago, forma_pagamento_id,
                            cartao, cartao_id, parcela_atual, parcela_total, recorrencia_id)
    VALUES (:data, :descricao, :valor, :categoria_id, :tipo, :pago, :forma_pagamento_id,
            :cartao, :cartao_id, :parcela_atual, :parcela_total, :recorrencia_id)
""")
_PADRAO_TRANSACAO = {"cartao": None, "cartao_id": None, "parcela_atual": 1, "parcela_total": 1,
                     "recorrencia_id": None, "forma_pagamento_id": None, "pago": False}


def inserir_transacoes(linhas: list[dict]) -> int:
    """Insere várias transações numa única ida ao banco (executemany)."""
    if not linhas:
        return 0
    params = [{k: _nativo(v) for k, v in {**_PADRAO_TRANSACAO, **l}.items()} for l in linhas]
    with engine().begin() as conn:
        conn.execute(SQL_INSERT_TRANSACAO, params)
    limpar_cache()
    return len(params)


def inserir(tabela: str, dados: dict) -> None:
    cols = [c for c in dados if c in COLUNAS_EDITAVEIS[tabela]]
    q = text(f"INSERT INTO {tabela} ({', '.join(cols)}) VALUES ({', '.join(':' + c for c in cols)})")
    with engine().begin() as conn:
        conn.execute(q, {c: _nativo(dados[c]) for c in cols})
    limpar_cache()


def ids_em_uso(tabela: str, ids: list[int]) -> list[int]:
    col = REFERENCIAS.get(tabela)
    if not col or not ids:
        return []
    q = text(f"SELECT DISTINCT {col} FROM transacoes WHERE {col} IN :ids").bindparams(
        bindparam("ids", expanding=True))
    with engine().connect() as conn:
        em_uso = {r[0] for r in conn.execute(q, {"ids": [int(i) for i in ids]})}
        if tabela == "categorias":
            q2 = text("SELECT DISTINCT categoria_id FROM recorrencias WHERE categoria_id IN :ids").bindparams(
                bindparam("ids", expanding=True))
            em_uso |= {r[0] for r in conn.execute(q2, {"ids": [int(i) for i in ids]})}
    return sorted(em_uso)


def atualizar(tabela: str, edicoes: dict[int, dict], exclusoes: list[int] | None = None) -> None:
    """Aplica edições {id: {coluna: valor}} e exclusões numa única transação."""
    permitidas = COLUNAS_EDITAVEIS[tabela]
    with engine().begin() as conn:
        if exclusoes:
            q = text(f"DELETE FROM {tabela} WHERE id IN :ids").bindparams(bindparam("ids", expanding=True))
            conn.execute(q, {"ids": [int(x) for x in exclusoes]})
        for rid, campos in (edicoes or {}).items():
            campos = {k: _nativo(v) for k, v in campos.items() if k in permitidas}
            if not campos:
                continue
            sets = ", ".join(f"{k} = :{k}" for k in campos)
            conn.execute(text(f"UPDATE {tabela} SET {sets} WHERE id = :id"), {"id": int(rid), **campos})
    limpar_cache()


def marcar_pagas(ids: list[int]) -> int:
    if not ids:
        return 0
    q = text("UPDATE transacoes SET pago = TRUE WHERE id IN :ids").bindparams(bindparam("ids", expanding=True))
    with engine().begin() as conn:
        n = conn.execute(q, {"ids": [int(x) for x in ids]}).rowcount
    limpar_cache()
    return n


def replicar_lancamento(id_origem: int, repeticoes: int) -> int:
    with engine().connect() as conn:
        r = conn.execute(text("SELECT * FROM transacoes WHERE id = :id"), {"id": int(id_origem)}).mappings().first()
    if not r:
        return 0
    base = descricao_base(r["descricao"])
    linhas = [{"data": add_months(r["data"], i), "descricao": base, "valor": r["valor"],
               "categoria_id": r["categoria_id"], "tipo": r["tipo"], "pago": False,
               "forma_pagamento_id": r["forma_pagamento_id"], "cartao": r["cartao"],
               "cartao_id": r.get("cartao_id")} for i in range(1, int(repeticoes) + 1)]
    return inserir_transacoes(linhas)


# =========================================================== recorrências
def gerar_recorrencias(ate: date | None = None) -> int:
    """Cria os lançamentos das recorrências ativas até o mês de `ate` (padrão: mês atual)."""
    limite = primeiro_dia(ate or date.today())
    with engine().connect() as conn:
        recs = conn.execute(text("SELECT * FROM recorrencias WHERE ativo")).mappings().all()
    linhas, atualizacoes = [], {}
    for r in recs:
        mes = primeiro_dia(r["inicio"]) if r["ultima_geracao"] is None else add_months(r["ultima_geracao"], 1)
        ultimo = None
        while mes <= limite and (r["fim"] is None or mes <= primeiro_dia(r["fim"])):
            linhas.append({"data": dia_seguro(mes.year, mes.month, r["dia"]), "descricao": r["descricao"],
                           "valor": r["valor"], "categoria_id": r["categoria_id"], "tipo": r["tipo"],
                           "pago": bool(r["gerar_pago"]), "forma_pagamento_id": r["forma_pagamento_id"],
                           "cartao_id": r["cartao_id"], "recorrencia_id": r["id"]})
            ultimo = mes
            mes = add_months(mes, 1)
        if ultimo:
            atualizacoes[r["id"]] = ultimo
    if not linhas:
        return 0
    params = [{k: _nativo(v) for k, v in {**_PADRAO_TRANSACAO, **l}.items()} for l in linhas]
    with engine().begin() as conn:  # lançamentos e marcação de geração ficam na mesma transação
        conn.execute(SQL_INSERT_TRANSACAO, params)
        conn.execute(text("UPDATE recorrencias SET ultima_geracao = :m WHERE id = :id"),
                     [{"id": k, "m": v} for k, v in atualizacoes.items()])
    limpar_cache()
    return len(params)


# =========================================================== backup
def exportar_backup() -> bytes:
    buf = io.BytesIO()
    with engine().connect() as conn, pd.ExcelWriter(buf) as w:
        for t in TABELAS_BACKUP:
            pd.read_sql(text(f"SELECT * FROM {t} ORDER BY id"), conn).to_excel(w, sheet_name=t, index=False)
    return buf.getvalue()


def restaurar_backup(arquivo) -> None:
    xls = pd.ExcelFile(arquivo)
    with engine().begin() as conn:
        for t in reversed(TABELAS_BACKUP):
            conn.execute(text(f"DELETE FROM {t}"))
        for t in TABELAS_BACKUP:
            if t in xls.sheet_names:  # backups antigos não têm cartoes/recorrencias
                pd.read_excel(xls, t).to_sql(t, conn, if_exists="append", index=False)
            conn.execute(text(
                f"SELECT setval(pg_get_serial_sequence('{t}', 'id'), COALESCE((SELECT MAX(id) FROM {t}), 0) + 1, false)"))
    limpar_cache()
