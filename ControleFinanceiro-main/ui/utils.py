import pandas as pd
from datetime import date

MAPA_MESES = {
    1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril", 
    5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto", 
    9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro"
}

MAPA_MESES_INV = {v: k for k, v in MAPA_MESES.items()}

MAPA_MESES_ABREV = {
    1: "Jan", 2: "Fev", 3: "Mar", 4: "Abr", 5: "Mai", 6: "Jun", 
    7: "Jul", 8: "Ago", 9: "Set", 10: "Out", 11: "Nov", 12: "Dez"
}

LISTA_ICONES = [
    "💳", "🏠", "🛒", "🍔", "🚗", "💊", "🎓", "✈️", "🎮", "💡", "🏦", 
    "💰", "🛠️", "👗", "🎁", "🐶", "📱", "💻", "🚌", "⛽", "🏥", "🏋️", 
    "🍷", "👶", "🧾", "💇", "💪"
]

def formatar_moeda(valor: float) -> str:
    """Formata valor float no padrão R$ 1.234,56."""
    if pd.isna(valor) or valor == 0:
        return "R$ 0,00"
    return f"R$ {float(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def formatar_mes_ano(dt) -> str:
    """Gera string do tipo Jan/26 a partir de datas."""
    if pd.isna(dt):
        return ""
    if isinstance(dt, str):
        dt = pd.to_datetime(dt)
    return f"{MAPA_MESES_ABREV.get(dt.month, '')}/{str(dt.year)[2:]}"

def render_card_html(label: str, valor_principal: str, texto_footer: str, cor_valor: str = "#ffffff", cor_footer: str = "#ffffff", seta: str = "") -> str:
    """Retorna código HTML para exibição de KPIs customizados."""
    return f"""
    <div style="background-color: #000000; border: 1px solid #ffffff; padding: 15px; border-radius: 10px; height: 100%;">
        <p style="color: #aaaaaa; font-weight: bold; font-size: 14px; margin-bottom: 5px;">{label}</p>
        <div style="font-size: 2rem; color: {cor_valor}; font-weight: 500; line-height: 1.2;">{valor_principal}</div>
        <div style="font-size: 0.9rem; color: {cor_footer}; font-weight: bold; margin-top: 15px;">{seta} {texto_footer}</div>
    </div>
    """
