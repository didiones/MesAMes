import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date, datetime
import time

from repository.transacao_repo import carregar_dados, baixar_contas_rapido
from repository.categoria_repo import carregar_tabelas_auxiliares
from ui.utils import formatar_moeda, render_card_html, MAPA_MESES_INV, MAPA_MESES_ABREV

def render_dashboard_page(user_id: int, ano_selecionado: int, meses_selecionados: list):
    """Renderiza a página do Dashboard com gráficos e KPIs."""
    df = carregar_dados(user_id)
    cats_df, fps_df = carregar_tabelas_auxiliares(user_id)

    if df.empty:
        st.warning("Banco de dados vazio. Comece cadastrando transações e categorias.")
        return

    # Preparação dos dados
    df['data'] = pd.to_datetime(df['data'])
    df['tipo'] = df['tipo'].astype(str).str.strip() 
    df['pago'] = df['pago'].fillna(False).astype(bool)

    # Filtragem temporal em memória (eficiente para escopo individual)
    df_ano = df[df['data'].dt.year == ano_selecionado].copy()
    meses_idx = [MAPA_MESES_INV[m] for m in meses_selecionados]
    df_mes = df_ano[df_ano['data'].dt.month.isin(meses_idx)].copy()
    
    mapa_cores = {}
    if not cats_df.empty and 'cor' in cats_df.columns:
        mapa_cores = {row['nome']: row['cor'] for _, row in cats_df.iterrows() if pd.notna(row['cor'])}

    # --- LÓGICA DE KPI AJUSTADA (RECEITA PREVISTA) ---
    res_mes = df_mes.groupby(['tipo', 'pago'])['valor'].sum()
    
    # Receita total (Paga + Pendente) para visão projetada
    rec_mes = res_mes.get(('Receita', True), 0) + res_mes.get(('Receita', False), 0)
    # Despesa no KPI principal: apenas realizado (o que saiu de caixa)
    desp_mes = res_mes.get(('Despesa', True), 0)
    # Investimento (Total)
    inv_mes = res_mes.get(('Investimento', True), 0) + res_mes.get(('Investimento', False), 0)
    # A Pagar (Despesas abertas)
    prev_mes = res_mes.get(('Despesa', False), 0)
    
    res_ano = df_ano.groupby(['tipo', 'pago'])['valor'].sum()
    rec_ano = res_ano.get(('Receita', True), 0) + res_ano.get(('Receita', False), 0)
    desp_ano = res_ano.get(('Despesa', True), 0)
    inv_ano = res_ano.get(('Investimento', True), 0) + res_ano.get(('Investimento', False), 0)
    
    # Saldo Projetado (Receita total - Despesa total - Investimento total)
    saldo_mes = rec_mes - (desp_mes + prev_mes) - inv_mes
    saldo_ano = rec_ano - (desp_ano + res_ano.get(('Despesa', False), 0)) - inv_ano
    
    st.header(f"Visão Geral - {ano_selecionado}")
    c1, c2, c3, c4, c5 = st.columns(5)
    
    c1.markdown(render_card_html("📥 Receitas (Previsto)", formatar_moeda(rec_mes), f"Ano: {formatar_moeda(rec_ano)}", cor_footer="#2ecc71", seta="▲"), unsafe_allow_html=True)
    c2.markdown(render_card_html("📤 Despesas (Pagas)", formatar_moeda(desp_mes), f"- Ano: {formatar_moeda(desp_ano)}", cor_footer="#ff4b4b", seta="▼"), unsafe_allow_html=True)
    c3.markdown(render_card_html("🗓️ A Pagar (Previsto)", formatar_moeda(prev_mes), "Falta sair do caixa", cor_footer="#aaaaaa", seta="-"), unsafe_allow_html=True)
    
    seta_inv = "-" if inv_ano == 0 else "▲"
    col_inv = "#ffffff" if inv_ano == 0 else "#2ecc71"
    c4.markdown(render_card_html("📈 Investimentos", formatar_moeda(inv_mes), f"Ano: {formatar_moeda(inv_ano)}", cor_footer=col_inv, seta=seta_inv), unsafe_allow_html=True)
    
    cor_saldo = "#2ecc71" if saldo_mes >= 0 else "#ff4b4b"
    if saldo_ano > 0:
        ss, cs = "▲", "#2ecc71"
    elif saldo_ano < 0:
        ss, cs = "▼", "#ff4b4b"
    else:
        ss, cs = "-", "#ffffff"
    c5.markdown(render_card_html("💵 Saldo (Projetado)", formatar_moeda(saldo_mes), f"Ano: {formatar_moeda(saldo_ano)}", cor_valor=cor_saldo, cor_footer=cs, seta=ss), unsafe_allow_html=True)

    # --- INSIGHTS INTELIGENTES ---
    if rec_mes > 0 and not df_mes[df_mes['tipo'] == 'Despesa'].empty:
        df_d = df_mes[df_mes['tipo'] == 'Despesa']
        top = df_d.groupby('categoria')['valor'].sum().sort_values(ascending=False)
        if not top.empty:
            cat_top = top.index[0]
            val_top = top.iloc[0]
            perc = (val_top / rec_mes) * 100
            st.markdown(
                f'<div class="insight-box"><span class="insight-label">💡 Smart Insight (Mês):</span>'
                f'Maior gasto: <b>{cat_top}</b> ({formatar_moeda(val_top)} - {perc:.1f}% da receita projetada).</div>', 
                unsafe_allow_html=True
            )

    # Barra cumulativa de pagamentos (Pago vs Aberto)
    tot_comprometido = desp_mes + prev_mes
    if tot_comprometido > 0:
        pp = (desp_mes / tot_comprometido) * 100
        pa = (prev_mes / tot_comprometido) * 100
        df_bar = pd.DataFrame({
            'V': [desp_mes, prev_mes], 
            'S': ['Pago', 'Aberto'], 
            'C': ['#2ecc71', '#f39c12'], 
            'T': [f"{formatar_moeda(desp_mes)} ({pp:.0f}%)", f"{formatar_moeda(prev_mes)} ({pa:.0f}%)"]
        })
        fig = px.bar(df_bar, x='V', y=[1, 1], color='S', orientation='h', text='T', color_discrete_sequence=df_bar['C'])
        fig.update_layout(
            xaxis_visible=False, yaxis_visible=False, barmode='stack', height=40, 
            margin=dict(l=0, r=0, t=0, b=0), showlegend=False, 
            paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)'
        )
        fig.update_traces(textposition='inside', textfont=dict(color='white', size=14))
        _, c_mid, _ = st.columns([1, 10, 1]) 
        with c_mid: 
            st.plotly_chart(fig, use_container_width=True, config={'staticPlot': True})

    # --- BAIXA RÁPIDA DE CONTAS ---
    df_open = df_mes[(df_mes['pago'] == False) & (df_mes['tipo'] == 'Despesa')].sort_values('data')
    if not df_open.empty:
        st.markdown("---")
        st.subheader("⚠️ Baixa Rápida de Contas")
        st.caption("Selecione e confirme o pagamento de despesas abertas no período filtrado.")
        
        df_open['Situação'] = df_open['data'].apply(
            lambda x: "🔴 Vencido" if x.date() < date.today() else ("🟡 Hoje" if x.date() == date.today() else "⚪ A Vencer")
        )
        # Reseta os índices para garantir que o st.data_editor funcione de forma estável
        df_view = df_open[['id', 'Situação', 'data', 'descricao', 'categoria', 'valor']].copy().reset_index(drop=True)
        df_view['data'] = df_view['data'].dt.date
        df_view.insert(0, "Pagar?", False)
        
        edited = st.data_editor(
            df_view, 
            key="qp_fix_final", 
            hide_index=True, 
            use_container_width=True, 
            column_config={
                "id": None, 
                "Pagar?": st.column_config.CheckboxColumn(width="small"), 
                "Situação": st.column_config.TextColumn(width="small"), 
                "data": st.column_config.DateColumn("Vencimento", format="DD/MM/YYYY", width="small"), 
                "descricao": st.column_config.TextColumn("Descrição", width="large"), 
                "categoria": st.column_config.TextColumn("Categoria", width="medium"), 
                "valor": st.column_config.NumberColumn("Valor", format="R$ %.2f", width="small")
            }, 
            disabled=["Situação", "data", "descricao", "categoria", "valor"]
        )
        
        if st.button("✅ Confirmar Pagamentos", type="primary"):
            ids = edited[edited['Pagar?']]['id'].tolist()
            if ids and baixar_contas_rapido(user_id, ids):
                st.toast(f"{len(ids)} conta(s) baixada(s)!", icon='✅')
                time.sleep(0.5)
                st.rerun()

    # --- GRÁFICOS ---
    st.markdown("---")
    tab_v, tab_m = st.tabs(["📊 Visão por Categoria", "🌳 Mapa de Gastos"])
    with tab_v:
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("Receitas")
            df_rec = df_mes[df_mes['tipo'] == 'Receita']
            if not df_rec.empty:
                df_g = df_rec.groupby('categoria')['valor'].sum().reset_index().sort_values('valor')
                df_g['fmt_val'] = df_g['valor'].apply(formatar_moeda)
                total_r = df_g['valor'].sum()
                df_g['perc'] = (df_g['valor'] / total_r).apply(lambda x: f"{x:.1%}")
                fig = px.bar(
                    df_g, x='valor', y='categoria', orientation='h', text='fmt_val', 
                    color='categoria', color_discrete_map=mapa_cores if mapa_cores else None, 
                    custom_data=['fmt_val', 'perc']
                )
                fig.update_layout(yaxis_title=None, xaxis_title=None, showlegend=False, xaxis_visible=False, margin=dict(r=130))
                fig.update_traces(
                    textposition='outside', textfont=dict(size=14, color='white', family="Arial Black"), 
                    cliponaxis=False, hovertemplate='<b>%{y}</b><br>Valor: %{customdata[0]}<br>Repres.: %{customdata[1]}<extra></extra>'
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("Sem receitas no período.")
        with c2:
            st.subheader("Despesas")
            df_desp = df_mes[df_mes['tipo'] == 'Despesa']
            if not df_desp.empty:
                df_g = df_desp.groupby('categoria')['valor'].sum().reset_index().sort_values('valor')
                df_g['fmt_val'] = df_g['valor'].apply(formatar_moeda)
                total_d = df_g['valor'].sum()
                df_g['perc'] = (df_g['valor'] / total_d).apply(lambda x: f"{x:.1%}")
                fig = px.bar(
                    df_g, x='valor', y='categoria', orientation='h', text='fmt_val', 
                    color='categoria', color_discrete_map=mapa_cores if mapa_cores else None, 
                    custom_data=['fmt_val', 'perc']
                )
                fig.update_layout(yaxis_title=None, xaxis_title=None, showlegend=False, xaxis_visible=False, margin=dict(r=130))
                fig.update_traces(
                    textposition='outside', textfont=dict(size=14, color='white', family="Arial Black"), 
                    cliponaxis=False, hovertemplate='<b>%{y}</b><br>Valor: %{customdata[0]}<br>Repres.: %{customdata[1]}<extra></extra>'
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("Sem despesas no período.")
    
    with tab_m:
        st.subheader("Mapa de Despesas (Treemap)")
        df_tree = df_mes[df_mes['tipo'] == 'Despesa'].copy()
        if not df_tree.empty:
            df_tree['fmt_val'] = df_tree['valor'].apply(formatar_moeda)
            fig = px.treemap(
                df_tree, path=['grupo', 'categoria'], values='valor', 
                color='categoria', color_discrete_map=mapa_cores if mapa_cores else None, 
                custom_data=['fmt_val']
            )
            fig.update_traces(
                textinfo="label+value+percent entry", 
                texttemplate='<b>%{label}</b><br>%{customdata[0]}', 
                textfont=dict(size=18, family="Arial Black"), 
                hovertemplate='<b>%{label}</b><br>Valor: %{customdata[0]}<br>%{percentRoot:.1%} do Total<extra></extra>'
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Sem dados de despesas para o mapa.")
            
    st.markdown("---")
    c_evo1, c_evo2 = st.columns(2)
    with c_evo1:
        st.subheader("Evolução Mensal (Período Selecionado)")
        if not df_mes.empty:
            # Agrupamento mensal correto pelo Pandas
            df_evolucao = df_mes.groupby([pd.Grouper(key='data', freq='ME'), 'tipo'])['valor'].sum().reset_index()
            df_evolucao['mes_str'] = df_evolucao['data'].apply(lambda d: MAPA_MESES_ABREV.get(d.month, str(d.month)))
            df_evolucao = df_evolucao.sort_values('data')
            fig_evo = px.line(
                df_evolucao, x='mes_str', y='valor', color='tipo', markers=True, 
                color_discrete_map={'Receita': '#2ecc71', 'Despesa': '#e74c3c', 'Investimento': '#3498db'}
            )
            fig_evo.update_layout(xaxis_title=None, yaxis_title="R$")
            st.plotly_chart(fig_evo, use_container_width=True)
        else:
            st.info("Sem dados de evolução nos meses selecionados.")

    with c_evo2:
        st.subheader("Fluxo de Caixa Anual (Projetado vs Realizado)")
        if not df_ano.empty:
            df_cx = df_ano.copy()
            df_cx['mes_num'] = df_cx['data'].dt.month
            df_cx['status_legenda'] = df_cx.apply(lambda r: f"{r['tipo']} - {'Realizado' if r['pago'] else 'Previsto'}", axis=1)
            df_line_cx = df_cx.groupby(['mes_num', 'status_legenda'])['valor'].sum().reset_index().sort_values('mes_num')
            df_line_cx = df_line_cx[df_line_cx['status_legenda'].str.contains('Receita|Despesa')]
            df_line_cx['mes_nome'] = df_line_cx['mes_num'].apply(lambda m: MAPA_MESES_ABREV.get(m, str(m)))
            
            cores_mapa = {
                'Receita - Realizado': '#27ae60', 'Receita - Previsto': '#82e0aa', 
                'Despesa - Realizado': '#c0392b', 'Despesa - Previsto': '#f1948a'
            }
            fig_cx = px.line(df_line_cx, x='mes_nome', y='valor', color='status_legenda', markers=True, color_discrete_map=cores_mapa)
            fig_cx.update_layout(xaxis_title=None, yaxis_title="R$", legend_title=None)
            st.plotly_chart(fig_cx, use_container_width=True)
        else:
            st.info("Sem dados anuais para gerar o fluxo de caixa.")
