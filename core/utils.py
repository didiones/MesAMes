"""Constantes, formatação e utilidades de datas/períodos."""
from __future__ import annotations

import calendar
import re
import unicodedata
from dataclasses import dataclass
from datetime import date

import pandas as pd

MAPA_MESES = {1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril", 5: "Maio", 6: "Junho",
              7: "Julho", 8: "Agosto", 9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro"}
MAPA_MESES_ABREV = {1: "Jan", 2: "Fev", 3: "Mar", 4: "Abr", 5: "Mai", 6: "Jun",
                    7: "Jul", 8: "Ago", 9: "Set", 10: "Out", 11: "Nov", 12: "Dez"}
TIPOS = ["Despesa", "Receita", "Investimento"]
NATUREZAS = ["Necessidade", "Desejo"]
LISTA_ICONES = ["💳", "🏠", "🛒", "🍔", "🚗", "💊", "🎓", "✈️", "🎮", "💡", "🏦", "💰", "🛠️", "👗", "🎁",
                "🐶", "📱", "💻", "🚌", "⛽", "🏥", "🏋️", "🍷", "👶", "🧾", "💇", "💪"]

CORES_TIPO = {"Receita": "#3FA37E", "Despesa": "#D9534F", "Investimento": "#4A8FD4"}
COR_PREVISTO = {"Receita": "#9BD3BC", "Despesa": "#EBA3A1", "Investimento": "#A9C8EA"}


# ---------------------------------------------------------------- formatação
def formatar_moeda(valor) -> str:
    if valor is None or pd.isna(valor):
        valor = 0
    txt = f"{abs(float(valor)):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"-R$ {txt}" if float(valor) < 0 else f"R$ {txt}"


def formatar_pct(valor, casas=1) -> str:
    if valor is None or pd.isna(valor):
        return "—"
    return f"{valor * 100:.{casas}f}%".replace(".", ",")


def mes_ano(dt) -> str:
    if dt is None or pd.isna(dt):
        return ""
    dt = pd.Timestamp(dt)
    return f"{MAPA_MESES_ABREV[dt.month]}/{str(dt.year)[2:]}"


def rotulo_categoria(icone, grupo, nome) -> str:
    icone = icone if isinstance(icone, str) and icone else ""
    return f"{icone} {grupo} - {nome}".strip()


# ---------------------------------------------------------------- datas
def add_months(d: date, months: int) -> date:
    m = d.month - 1 + months
    y = d.year + m // 12
    m = m % 12 + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def primeiro_dia(d: date) -> date:
    return date(d.year, d.month, 1)


def dia_seguro(ano: int, mes: int, dia: int) -> date:
    return date(ano, mes, min(int(dia), calendar.monthrange(ano, mes)[1]))


def vencimento_fatura(data_compra: date, dia_fechamento: int, dia_vencimento: int) -> date:
    """Data de vencimento da fatura em que uma compra no cartão vai cair.

    Compras feitas a partir do dia de fechamento entram na fatura seguinte.
    Se o vencimento é antes (ou no) dia de fechamento, ele cai no mês seguinte ao fechamento.
    """
    mes_fech = primeiro_dia(data_compra)
    if data_compra.day >= dia_fechamento:
        mes_fech = add_months(mes_fech, 1)
    mes_venc = mes_fech if dia_vencimento > dia_fechamento else add_months(mes_fech, 1)
    return dia_seguro(mes_venc.year, mes_venc.month, dia_vencimento)


# ---------------------------------------------------------------- período
@dataclass(frozen=True)
class Periodo:
    """Conjunto de meses (ano, mês) selecionados no filtro."""
    meses: tuple  # tupla ordenada de (ano, mes)
    rotulo: str

    @property
    def inicio(self) -> date:
        a, m = self.meses[0]
        return date(a, m, 1)

    @property
    def fim(self) -> date:
        """Primeiro dia após o último mês (limite exclusivo)."""
        a, m = self.meses[-1]
        return add_months(date(a, m, 1), 1)

    @property
    def n_meses(self) -> int:
        return len(self.meses)

    @property
    def ano_ref(self) -> int:
        return self.meses[-1][0]

    @property
    def chaves(self) -> set:
        return {a * 100 + m for a, m in self.meses}

    def contem_hoje(self) -> bool:
        h = date.today()
        return (h.year, h.month) in self.meses

    def anterior(self) -> "Periodo":
        """Bloco de mesmo tamanho imediatamente antes do início."""
        meses = tuple(
            (d.year, d.month)
            for d in (add_months(self.inicio, -i) for i in range(self.n_meses, 0, -1))
        )
        return Periodo(meses, "período anterior")

    def mascara(self, serie_datas: pd.Series) -> pd.Series:
        chave = serie_datas.dt.year * 100 + serie_datas.dt.month
        return chave.isin(self.chaves)


def periodo_de_meses(pares) -> Periodo:
    pares = tuple(sorted(set(pares)))
    if len(pares) == 1:
        a, m = pares[0]
        rot = f"{MAPA_MESES[m]} de {a}"
    else:
        (a1, m1), (a2, m2) = pares[0], pares[-1]
        rot = f"{MAPA_MESES_ABREV[m1]}/{a1} a {MAPA_MESES_ABREV[m2]}/{a2} ({len(pares)} meses)"
    return Periodo(pares, rot)


def ultimos_meses(n: int, ate: date | None = None) -> Periodo:
    ate = primeiro_dia(ate or date.today())
    return periodo_de_meses((d.year, d.month) for d in (add_months(ate, -i) for i in range(n)))


# ---------------------------------------------------------------- texto
_STOP = {"compra", "pix", "pag", "pagto", "pagamento", "debito", "credito", "cartao", "transf",
         "transferencia", "enviado", "enviada", "recebido", "recebida", "ted", "doc", "boleto",
         "de", "da", "do", "em", "no", "na", "para", "com", "elo", "visa", "master", "mastercard"}


def normalizar_texto(txt: str) -> list[str]:
    """Tokens relevantes de uma descrição, sem acentos, números e palavras genéricas."""
    if not isinstance(txt, str):
        return []
    txt = unicodedata.normalize("NFKD", txt).encode("ascii", "ignore").decode().lower()
    txt = re.sub(r"\(\d+/\d+\)", " ", txt)
    txt = re.sub(r"[^a-z ]", " ", txt)
    return [t for t in txt.split() if len(t) > 2 and t not in _STOP]


def descricao_base(desc: str) -> str:
    """Remove o sufixo de parcela, ex.: 'Notebook (3/10)' -> 'Notebook'."""
    return re.sub(r"\s*\(\d+/\d+\)\s*$", "", str(desc or "")).strip()
