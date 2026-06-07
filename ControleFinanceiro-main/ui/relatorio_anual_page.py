import streamlit as st
import pandas as pd
import io

from repository.transacao_repo import carregar_dados_ano
from ui.utils import formatar_moeda, MAPA_MESES

def render_relatorio_anual_page(user_id: int, ano_selecionado: int):
    """Renderiza a página de Relatório Anual com tabelas pivô e exportação."""
    st.header(f"Relatório {ano_selecionado}")
    
    df = carregar_dados_ano(user_id, ano_selecionado)
    
    if df.empty:
        st.warning("Sem dados cadastrados para o ano selecionado.")
        return
        
    total_desp_ano = df[df['tipo'] == 'Despesa']['valor'].sum()
    if total_desp_ano > 0:
        top_cat = df[df['tipo'] == 'Despesa'].groupby('categoria')['valor'].sum().sort_values(ascending=False)
        if not top_cat.empty:
            cat_n = top_cat.index[0]
            cat_v = top_cat.iloc[0]
            pct = (cat_v / total_desp_ano) * 100
            st.markdown(
                f"""
                <div class="insight-box">
                    <span class="insight-label">💡 Destaque do Ano:</span>
                    Sua maior despesa foi <b>{cat_n}</b> com {formatar_moeda(cat_v)} 
                    (representando <b>{pct:.1f}%</b> de todas as suas despesas no ano).
                </div>
                """, 
                unsafe_allow_html=True
            )

    df['mes'] = pd.to_datetime(df['data']).dt.month
    df['pago'] = df['pago'].fillna(False).astype(bool)

    def make_pivot(tf):
        d = df[df['tipo'] == tf]
        if d.empty: 
            return None, None
        # Pivota por categoria e mês
        p = d.pivot_table(index='categoria', columns='mes', values='valor', aggfunc='sum', fill_value=0)
        p = p.reindex(columns=range(1, 13), fill_value=0)
        p.columns = [MAPA_MESES[i] for i in range(1, 13)]
        
        # Cria matriz auxiliar de controle de pagamentos (para colorir)
        d_pago = d[d['pago'] == True]
        if not d_pago.empty:
            p_paid = d_pago.pivot_table(index='categoria', columns='mes', values='valor', aggfunc='sum', fill_value=0)
            p_paid = p_paid.reindex(index=p.index, columns=range(1, 13), fill_value=0)
            p_paid.columns = p.columns
        else:
            p_paid = pd.DataFrame(0.0, index=p.index, columns=p.columns)
            
        p['TOTAL'] = p.sum(axis=1)
        row = pd.DataFrame(p.sum(axis=0)).T
        row.index = ['TOTAL']
        return pd.concat([p, row]), p_paid

    r_rec, p_rec = make_pivot('Receita')
    r_desp, p_desp = make_pivot('Despesa')
    r_inv, p_inv = make_pivot('Investimento')
    
    # Planilha de Resumo Anual Caixa
    def gt(d): 
        return d.loc['TOTAL'] if d is not None else pd.Series(0.0, index=[MAPA_MESES[i] for i in range(1, 13)] + ['TOTAL'])
        
    s_r = gt(r_rec)
    s_d = gt(r_desp)
    s_i = gt(r_inv)
    s_s = s_r - s_d - s_i
    df_caixa = pd.DataFrame([s_r, s_d, s_i, s_s], index=['Receitas', 'Despesas', 'Investimentos', 'SALDO'])

    # Geração do Excel de forma cacheada para economizar CPU
    @st.cache_data
    def gerar_excel(r_r, r_d, r_i, s_cx):
        out = io.BytesIO()
        with pd.ExcelWriter(out, engine='xlsxwriter') as writer:
            if r_r is not None: r_r.to_excel(writer, sheet_name='Receitas')
            if r_d is not None: r_d.to_excel(writer, sheet_name='Despesas')
            if r_i is not None: r_i.to_excel(writer, sheet_name='Investimentos')
            if s_cx is not None: s_cx.to_excel(writer, sheet_name='Resumo')
        return out.getvalue()
        
    excel_bytes = gerar_excel(
        r_rec.to_json() if r_rec is not None else None, 
        r_desp.to_json() if r_desp is not None else None, 
        r_inv.to_json() if r_inv is not None else None, 
        df_caixa.to_json()
    )
    
    # Nota: st.cache_data requer parâmetros serializáveis ou hashables simples. 
    # Por isso, passamos strings JSON para indexação do cache e depois processamos dentro da exportação.
    @st.cache_data
    def gerar_excel_final(ano: int, user_id_val: int) -> bytes:
        # Recarrega diretamente dentro da função cacheada por tipo simples
        df_int = carregar_dados_ano(user_id_val, ano)
        df_int['mes'] = pd.to_datetime(df_int['data']).dt.month
        
        def make_pivot_cache(tf):
            d = df_int[df_int['tipo'] == tf]
            if d.empty: return None
            p = d.pivot_table(index='categoria', columns='mes', values='valor', aggfunc='sum', fill_value=0)
            p = p.reindex(columns=range(1, 13), fill_value=0)
            p.columns = [MAPA_MESES[i] for i in range(1, 13)]
            p['TOTAL'] = p.sum(axis=1)
            row = pd.DataFrame(p.sum(axis=0)).T
            row.index = ['TOTAL']
            return pd.concat([p, row])
            
        r_rec_c = make_pivot_cache('Receita')
        r_desp_c = make_pivot_cache('Despesa')
        r_inv_c = make_pivot_cache('Investimento')
        
        s_r_c = r_rec_c.loc['TOTAL'] if r_rec_c is not None else pd.Series(0.0, index=[MAPA_MESES[i] for i in range(1, 13)] + ['TOTAL'])
        s_d_c = r_desp_c.loc['TOTAL'] if r_desp_c is not None else pd.Series(0.0, index=[MAPA_MESES[i] for i in range(1, 13)] + ['TOTAL'])
        s_i_c = r_inv_c.loc['TOTAL'] if r_inv_c is not None else pd.Series(0.0, index=[MAPA_MESES[i] for i in range(1, 13)] + ['TOTAL'])
        s_s_c = s_r_c - s_d_c - s_i_c
        df_caixa_c = pd.DataFrame([s_r_c, s_d_c, s_i_c, s_s_c], index=['Receitas', 'Despesas', 'Investimentos', 'SALDO'])
        
        out = io.BytesIO()
        with pd.ExcelWriter(out, engine='xlsxwriter') as writer:
            if r_rec_c is not None: r_rec_c.to_excel(writer, sheet_name='Receitas')
            if r_desp_c is not None: r_desp_c.to_excel(writer, sheet_name='Despesas')
            if r_inv_c is not None: r_inv_c.to_excel(writer, sheet_name='Investimentos')
            df_caixa_c.to_excel(writer, sheet_name='Resumo')
        return out.getvalue()

    excel_bytes = gerar_excel_final(ano_selecionado, user_id)
    
    st.download_button(
        "📥 Baixar Relatório (Excel)", 
        excel_bytes, 
        f"relatorio_anual_{ano_selecionado}.xlsx", 
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    # Estilização visual condicional para colorir células baseadas no status de pago
    def style(v, p):
        if v is None: 
            return None
        def hl(row):
            s = []
            for c in row.index:
                if c == 'TOTAL': 
                    s.append('font-weight: bold; color: white')
                    continue
                try:
                    val = row[c]
                    paid = p.loc[row.name, c] if (p is not None and row.name in p.index and c in p.columns) else 0.0
                    if val == 0: 
                        s.append("color: #bbbbbb") 
                    elif paid >= val - 0.01: 
                        s.append("color: #2ecc71; font-weight: bold") 
                    else: 
                        s.append("color: #f39c12; font-weight: bold") 
                except: 
                    s.append("")
            return s
        return v.style.apply(hl, axis=1).format(formatar_moeda)

    def show(t, s, r):
        st.subheader(t)
        if s is not None: 
            st.dataframe(s, use_container_width=True, height=(len(r)+1)*35+3)
        else: 
            st.info(f"Sem {t} cadastradas no ano.")

    show("Receitas", style(r_rec, p_rec), r_rec)
    show("Despesas", style(r_desp, p_desp), r_desp)
    show("Investimentos", style(r_inv, p_inv), r_inv)
    
    st.markdown("---")
    st.subheader("Resumo de Fluxo de Caixa")
    def st_c(s): 
        return ['color: #e74c3c; font-weight: bold' if (v < 0 and s.name == 'SALDO') else ('color: #2ecc71; font-weight: bold' if (v >= 0 and s.name == 'SALDO') else '') for v in s]
    st.dataframe(df_caixa.style.apply(st_c, axis=1).format(formatar_moeda), use_container_width=True)
