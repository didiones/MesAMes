"""Cálculo dos indicadores financeiros (funções puras sobre DataFrames de transações)."""
from __future__ import annotations

import calendar
from datetime import date

import numpy as np
import pandas as pd

from core.utils import Periodo, add_months, descricao_base, primeiro_dia


def _soma(df, tipo, pago=None) -> float:
    m = df["tipo"] == tipo
    if pago is not None:
        m &= df["pago"] == pago
    return float(df.loc[m, "valor"].sum())


def resumo(df: pd.DataFrame) -> dict:
    """Totais do período. 'Projetado' considera tudo; 'realizado' só o que foi pago/recebido."""
    if df.empty:
        z = dict.fromkeys(["receita", "receita_real", "despesa", "despesa_paga", "despesa_aberta",
                           "invest", "invest_real", "saldo_real", "saldo_proj"], 0.0)
        z["taxa_poupanca"] = None
        return z
    r = {
        "receita": _soma(df, "Receita"),
        "receita_real": _soma(df, "Receita", True),
        "despesa": _soma(df, "Despesa"),
        "despesa_paga": _soma(df, "Despesa", True),
        "despesa_aberta": _soma(df, "Despesa", False),
        "invest": _soma(df, "Investimento"),
        "invest_real": _soma(df, "Investimento", True),
    }
    r["saldo_real"] = r["receita_real"] - r["despesa_paga"] - r["invest_real"]
    r["saldo_proj"] = r["receita"] - r["despesa"] - r["invest"]
    # Poupança = o que sobra da receita depois das despesas (inclui o que foi investido)
    r["taxa_poupanca"] = (r["receita"] - r["despesa"]) / r["receita"] if r["receita"] > 0 else None
    return r


def variacao(atual: float, anterior: float):
    if not anterior:
        return None
    return (atual - anterior) / abs(anterior)


def serie_mensal(df: pd.DataFrame, meses, tipo: str) -> list[float]:
    """Total por mês (na ordem de `meses`) — usado nos mini-gráficos dos cards."""
    d = df[df["tipo"] == tipo]
    chave = d["data"].dt.year * 100 + d["data"].dt.month
    tot = d.groupby(chave)["valor"].sum()
    return [float(tot.get(a * 100 + m, 0.0)) for a, m in meses]


def media_mensal(df: pd.DataFrame, tipo: str, antes_de: date, n: int = 6) -> float:
    """Média mensal dos `n` meses completos antes de `antes_de` (ignora meses sem lançamentos)."""
    ini = add_months(primeiro_dia(antes_de), -n)
    d = df[(df["data"] >= pd.Timestamp(ini)) & (df["data"] < pd.Timestamp(primeiro_dia(antes_de)))]
    if d.empty:
        return 0.0
    meses_com_dados = (d["data"].dt.year * 100 + d["data"].dt.month).nunique()
    return float(d.loc[d["tipo"] == tipo, "valor"].sum()) / max(meses_com_dados, 1)


def orcamentos(df_p: pd.DataFrame, cats: pd.DataFrame, n_meses: int) -> pd.DataFrame:
    """Gasto × orçamento por categoria de despesa com orçamento definido."""
    c = cats[(cats["tipo"] == "Despesa") & (cats["orcamento"].fillna(0) > 0)].copy()
    if c.empty:
        return pd.DataFrame()
    gasto = df_p[df_p["tipo"] == "Despesa"].groupby("categoria_id")["valor"].sum()
    c["gasto"] = c["id"].map(gasto).fillna(0.0)
    c["limite"] = c["orcamento"].astype(float) * n_meses
    c["pct"] = c["gasto"] / c["limite"]
    c["restante"] = c["limite"] - c["gasto"]
    return c.sort_values("pct", ascending=False)


def fixas_variaveis(df_p: pd.DataFrame) -> tuple[float, float]:
    d = df_p[df_p["tipo"] == "Despesa"]
    fixas = float(d.loc[d["fixa"], "valor"].sum())
    return fixas, float(d["valor"].sum()) - fixas


def projecao_mes(df: pd.DataFrame, hoje: date | None = None) -> dict | None:
    """Estimativa de despesa do mês atual: fixas integrais + ritmo diário das variáveis."""
    hoje = hoje or date.today()
    ini, fim = pd.Timestamp(primeiro_dia(hoje)), pd.Timestamp(add_months(primeiro_dia(hoje), 1))
    d = df[(df["tipo"] == "Despesa") & (df["data"] >= ini) & (df["data"] < fim)]
    dias_mes = calendar.monthrange(hoje.year, hoje.month)[1]
    fixas = float(d.loc[d["fixa"], "valor"].sum())
    var_ate_hoje = float(d.loc[~d["fixa"] & (d["data"] <= pd.Timestamp(hoje)), "valor"].sum())
    projetado = fixas + var_ate_hoje / hoje.day * dias_mes
    return {"projetado": projetado, "fixas": fixas, "variaveis_ate_hoje": var_ate_hoje,
            "dia": hoje.day, "dias_mes": dias_mes}


def regra_503020(df_p: pd.DataFrame, cats: pd.DataFrame) -> dict | None:
    receita = _soma(df_p, "Receita")
    if receita <= 0:
        return None
    d = df_p[df_p["tipo"] == "Despesa"]
    nec = float(d.loc[d["natureza"].fillna("Necessidade") == "Necessidade", "valor"].sum())
    des = float(d["valor"].sum()) - nec
    return {"receita": receita,
            "Necessidades": nec / receita,
            "Desejos": des / receita,
            "Poupança": max(receita - nec - des, 0) / receita}


def alertas(df: pd.DataFrame, periodo: Periodo, base_meses: int = 6, fator: float = 1.5,
            minimo: float = 50.0) -> pd.DataFrame:
    """Categorias cujo gasto médio mensal no período superou `fator`× a média histórica."""
    d = df[df["tipo"] == "Despesa"]
    atual = d[periodo.mascara(d["data"])].groupby("categoria")["valor"].sum() / periodo.n_meses
    ini_base = pd.Timestamp(add_months(periodo.inicio, -base_meses))
    hist = d[(d["data"] >= ini_base) & (d["data"] < pd.Timestamp(periodo.inicio))]
    if hist.empty or atual.empty:
        return pd.DataFrame()
    meses_hist = (hist["data"].dt.year * 100 + hist["data"].dt.month).nunique()
    base = hist.groupby("categoria")["valor"].sum() / max(meses_hist, 1)
    # só compara categorias com histórico de pelo menos 2 meses (evita alertas com base em 1 lançamento)
    meses_por_cat = hist.groupby("categoria")["data"].apply(lambda s: (s.dt.year * 100 + s.dt.month).nunique())
    base = base[meses_por_cat >= 2]
    comp = pd.DataFrame({"atual": atual, "media": base}).dropna()
    comp = comp[(comp["atual"] > comp["media"] * fator) & (comp["atual"] - comp["media"] >= minimo)]
    comp["acima"] = comp["atual"] / comp["media"] - 1
    return comp.sort_values("acima", ascending=False)


def parcelas_futuras(df: pd.DataFrame, hoje: date | None = None, meses: int = 12):
    """Parcelas em aberto a partir do mês atual: total por mês e lista de parcelamentos."""
    hoje = hoje or date.today()
    ini = pd.Timestamp(primeiro_dia(hoje))
    d = df[(df["parcela_total"].fillna(1) > 1) & (~df["pago"]) & (df["data"] >= ini)
           & (df["tipo"] == "Despesa")].copy()
    if d.empty:
        return pd.DataFrame(), pd.DataFrame()
    d["mes"] = d["data"].dt.to_period("M").dt.to_timestamp()
    horizonte = [pd.Timestamp(add_months(ini.date(), i)) for i in range(meses)]
    por_mes = d.groupby("mes")["valor"].sum().reindex(horizonte, fill_value=0.0).reset_index()
    por_mes.columns = ["mes", "valor"]
    d["compra"] = d["descricao"].map(descricao_base)
    lista = (d.groupby(["compra", "cartao", "parcela_total"], dropna=False)
             .agg(valor_parcela=("valor", "mean"), restantes=("valor", "size"),
                  total_restante=("valor", "sum"), termina=("data", "max"))
             .reset_index().sort_values("termina"))
    return por_mes, lista


def faturas(df: pd.DataFrame) -> pd.DataFrame:
    """Faturas por cartão e mês de vencimento (lançamentos com cartão cadastrado)."""
    d = df[df["cartao_id"].notna() & (df["tipo"] == "Despesa")].copy()
    if d.empty:
        return pd.DataFrame()
    d["mes"] = d["data"].dt.to_period("M").dt.to_timestamp()
    f = (d.groupby(["cartao_id", "cartao", "mes"])
         .agg(total=("valor", "sum"), aberto=("pago", lambda s: int((~s).sum())), itens=("valor", "size"),
              vencimento=("data", "max"), ids=("id", list))
         .reset_index().sort_values(["mes", "cartao"]))
    f["status"] = np.where(f["aberto"] == 0, "Paga", "Em aberto")
    return f
