"""Leitura de extratos bancários (OFX e CSV) e categorização automática pelo histórico."""
from __future__ import annotations

import io
import re
from collections import Counter

import pandas as pd

from core.utils import normalizar_texto


# ------------------------------------------------------------------ leitura
def _decodificar(conteudo: bytes) -> str:
    for enc in ("utf-8", "cp1252", "latin-1"):
        try:
            return conteudo.decode(enc)
        except UnicodeDecodeError:
            continue
    return conteudo.decode("latin-1", errors="ignore")


def _tag(bloco: str, nome: str) -> str | None:
    # OFX 1.x (SGML) nem sempre fecha as tags, por isso lê até o próximo '<'
    m = re.search(rf"<{nome}>\s*([^<\r\n]*)", bloco, re.IGNORECASE)
    return m.group(1).strip() if m else None


def ler_ofx(conteudo: bytes) -> pd.DataFrame:
    txt = _decodificar(conteudo)
    blocos = re.split(r"<STMTTRN>", txt, flags=re.IGNORECASE)[1:]
    linhas = []
    for b in blocos:
        b = re.split(r"</STMTTRN>", b, flags=re.IGNORECASE)[0]
        dt, valor = _tag(b, "DTPOSTED"), _tag(b, "TRNAMT")
        if not dt or not valor:
            continue
        desc = _tag(b, "MEMO") or _tag(b, "NAME") or ""
        linhas.append({"data": pd.to_datetime(dt[:8], format="%Y%m%d", errors="coerce"),
                       "descricao": desc, "valor": _numero(valor), "fitid": _tag(b, "FITID")})
    return pd.DataFrame(linhas).dropna(subset=["data", "valor"])


def _numero(v) -> float | None:
    """Converte '1.234,56', '-1234.56', 'R$ 12,00' etc. em float."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = re.sub(r"[^\d,.\-]", "", str(v))
    if not s:
        return None
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def ler_csv_bruto(conteudo: bytes) -> pd.DataFrame:
    txt = _decodificar(conteudo)
    return pd.read_csv(io.StringIO(txt), sep=None, engine="python", dtype=str)


def montar_csv(bruto: pd.DataFrame, col_data: str, col_desc: str, col_valor: str,
               inverter_sinal: bool = False) -> pd.DataFrame:
    df = pd.DataFrame({
        "data": pd.to_datetime(bruto[col_data], dayfirst=True, errors="coerce"),
        "descricao": bruto[col_desc].fillna("").astype(str).str.strip(),
        "valor": bruto[col_valor].map(_numero),
    }).dropna(subset=["data", "valor"])
    if inverter_sinal:
        df["valor"] = -df["valor"]
    df["fitid"] = None
    return df


# ------------------------------------------------------------------ categorização
class Categorizador:
    """Sugere a categoria pela descrição mais parecida já lançada no histórico."""

    def __init__(self, historico: pd.DataFrame):
        self.exato: dict[tuple, int] = {}
        self.tokens: list[tuple[set, int, str]] = []
        contagem: dict[tuple, Counter] = {}
        for desc, cat, tipo in historico[["descricao", "categoria_id", "tipo"]].itertuples(index=False):
            toks = normalizar_texto(desc)
            if not toks:
                continue
            chave = (tipo, " ".join(toks[:3]))
            contagem.setdefault(chave, Counter())[int(cat)] += 1
            self.tokens.append((set(toks), int(cat), tipo))
        self.exato = {k: c.most_common(1)[0][0] for k, c in contagem.items()}

    def sugerir(self, descricao: str, tipo: str) -> int | None:
        toks = normalizar_texto(descricao)
        if not toks:
            return None
        cat = self.exato.get((tipo, " ".join(toks[:3])))
        if cat is not None:
            return cat
        alvo, melhor, melhor_score = set(toks), None, 0.0
        for conj, cat_id, t in self.tokens:
            if t != tipo:
                continue
            score = len(alvo & conj) / len(alvo | conj)
            if score > melhor_score:
                melhor, melhor_score = cat_id, score
        return melhor if melhor_score >= 0.5 else None


def marcar_duplicados(novos: pd.DataFrame, existentes: pd.DataFrame) -> pd.Series:
    """Mesmo dia, mesmo valor e descrição parecida = provável lançamento já cadastrado."""
    if existentes.empty:
        return pd.Series(False, index=novos.index)
    idx: dict[tuple, list[set]] = {}
    for d, v, desc in existentes[["data", "valor", "descricao"]].itertuples(index=False):
        idx.setdefault((pd.Timestamp(d).date(), round(float(v), 2)), []).append(set(normalizar_texto(desc)))

    def dup(row):
        candidatos = idx.get((row["data"].date(), round(abs(row["valor"]), 2)), [])
        toks = set(normalizar_texto(row["descricao"]))
        return any(not toks or not c or len(toks & c) / len(toks | c) >= 0.3 for c in candidatos)

    return novos.apply(dup, axis=1)
