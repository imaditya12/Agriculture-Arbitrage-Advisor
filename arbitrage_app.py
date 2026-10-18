"""
ARBITRAGE WEB APP - Built with Streamlit
"""

import streamlit as st
import pandas as pd
import mysql.connector
import plotly.express as px
from datetime import datetime

# ============================================================
# Database Configuration
# ============================================================
DB_CONFIG = {
    "host": "mysql-1de05a75-aditya12-30d7.c.aivencloud.com",
    "port": 21089,
    "user": "avnadmin",
    "password": st.secrets["DB_PASSWORD"],  # Safely pulls from Streamlit Secrets
    "database": "defaultdb"
}

def get_connection():
    return mysql.connector.connect(**DB_CONFIG, ssl_disabled=False)

# ============================================================
# Helper Functions
# ============================================================
def get_latest_date(commodity=None):
    conn = get_connection()
    cursor = conn.cursor()
    if commodity:
        cursor.execute("SELECT MAX(date) FROM commodity_prices WHERE commodity = %s AND modal_price > 0", (commodity,))
    else:
        cursor.execute("SELECT MAX(date) FROM commodity_prices WHERE modal_price > 0")
    latest = cursor.fetchone()[0]
    conn.close()
    return latest

@st.cache_data(ttl=3600)
def get_all_commodities():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT commodity FROM commodity_prices WHERE modal_price > 0 ORDER BY commodity")
    commodities = [row[0] for row in cursor.fetchall()]
    conn.close()
    return commodities

@st.cache_data(ttl=3600)
def get_recommendation(commodity):
    latest_date = get_latest_date(commodity)
    conn = get_connection()

    query = """
    SELECT state,
           SUM(modal_price * arrival_quantity) / SUM(arrival_quantity) as weighted_price,
           SUM(arrival_quantity) as total_arrival
    FROM commodity_prices
    WHERE commodity = %s AND date = %s AND modal_price > 0 AND arrival_quantity > 0
    GROUP BY state
    HAVING total_arrival > 0
    ORDER BY weighted_price
    """

    df = pd.read_sql(query, conn, params=[commodity, latest_date])
    conn.close()

    if df.empty or len(df) < 2:
        return None

    cheapest = df.iloc[0]
    most_expensive = df.iloc[-1]

    gross_profit = most_expensive['weighted_price'] - cheapest['weighted_price']

    return {
        'commodity': commodity,
        'date': latest_date,
        'buy_state': cheapest['state'],
        'buy_price': round(cheapest['weighted_price'], 2),
        'sell_state': most_expensive['state'],
        'sell_price': round(most_expensive['weighted_price'], 2),
        'gross_profit': round(gross_profit, 2),
        'states_covered': len(df)
    }

@st.cache_data(ttl=3600)
def get_top_commodities_and_insights():
    """
    MASSIVE OPTIMIZATION: Instead of looping 416 times in Python, 
    this runs ONE query in MySQL to calculate everything.
    """
    conn = get_connection()
    
    # This complex query calculates the weighted average for EVERY state and EVERY commodity 
    # on the latest date, then ranks them to find the buy/sell states, and sorts by profit.
    query = """
    WITH LatestDate AS (
        SELECT MAX(date) as max_date FROM commodity_prices WHERE modal_price > 0
    ),
    StatePrices AS (
        SELECT commodity, state, 
               SUM(modal_price * arrival_quantity) / SUM(arrival_quantity) as weighted_price
        FROM commodity_prices
        WHERE date = (SELECT max_date FROM LatestDate) AND modal_price > 0 AND arrival_quantity > 0
        GROUP BY commodity, state
        HAVING SUM(arrival_quantity) > 10
    ),
    MinMax AS (
        SELECT commodity, 
               MIN(weighted_price) as min_price, 
               MAX(weighted_price) as max_price
        FROM StatePrices
        GROUP BY commodity
        HAVING COUNT(state) > 1
    )
    SELECT sp_buy.commodity, 
           sp_buy.state as buy_state, sp_buy.weighted_price as buy_price,
           sp_sell.state as sell_state, sp_sell.weighted_price as sell_price,
           (sp_sell.weighted_price - sp_buy.weighted_price) as gross_profit,
           ((sp_sell.weighted_price - sp_buy.weighted_price) / sp_buy.weighted_price * 100) as margin_pct
    FROM MinMax mm
    JOIN StatePrices sp_buy ON mm.commodity = sp_buy.commodity AND mm.min_price = sp_buy.weighted_price
    JOIN StatePrices sp_sell ON mm.commodity = sp_sell.commodity AND mm.max_price = sp_sell.weighted_price
    ORDER BY gross_profit DESC
    """
    
    df = pd.read_sql(query, conn)
    conn.close()
    
    if df.empty:
        return [], {}
        
    # Process into format for Top 5
    top5 = df.head(5).to_dict('records')
    
    # Process into format for Insights
    buy_counts = df['buy_state'].value_counts().to_dict()
    sell_counts = df['sell_state'].value_counts().to_dict()
    avg_margin = round(df['margin_pct'].mean(), 1)
    top_margin = df.nlargest(5, 'margin_pct').to_dict('records')
    
    insights = {
        'all_recs': df.to_dict('records'),
        'buy_counts': buy_counts,
        'sell_counts': sell_counts,
        'avg_margin': avg_margin,
        'top_margin': top_margin
    }
    
    return top5, insights

# ============================================================
# Streamlit App Config
# ============================================================
st.set_page_config(page_title="Arbitrage Advisor", page_icon="🌾", layout="wide")

def metric_card(label, value, sub=None, color="kpi-blue"):
    sub_html = f'<div class="kpi-label" style="margin-top:4px;">{sub}</div>' if sub else ""
    st.markdown(f"""
    <div class="kpi-card {color}">
        <div class="kpi-label">{label}</div>
        <div class="kpi-value">{value}</div>
        {sub_html}
    </div>
    """, unsafe_allow_html=True)

st.markdown("""
<style>
    header[data-testid="stHeader"] { background: transparent; height: 0; min-height: 0; }
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    .block-container { padding-top: 1rem; padding-bottom: 2rem; }
    .main-header {
        background: linear-gradient(120deg, #062E2B 0%, #04635A 55%, #00A896 100%);
        padding: 26px 32px; border-radius: 14px; margin: 0 0 22px 0;
        border: 1px solid rgba(0,168,150,0.35); box-shadow: 0 0 24px rgba(0,168,150,0.15);
        text-align: center;
    }
    .main-header h1 { margin: 0; font-size: 2.7rem; color: #FFFFFF !important; display: flex; align-items: center; justify-content: center; gap: 12px; }
    .main-header p { margin: 8px 0 0 0; opacity: 0.85; font-size: 1.05rem; color: #CFEFEA !important; text-align: center; }
    [data-testid="stMetric"] { background-color: #16191C; border: 1px solid rgba(255,255,255,0.08); border-left: 3px solid #3A4046; border-radius: 10px; padding: 14px 16px; }
    [data-testid="stMetricLabel"] p { color: #9AA5AB !important; }
    [data-testid="stMetricValue"] { color: #F2F5F4 !important; }
    [data-testid="stMetricDelta"] { color: #9AA5AB !important; }
    .kpi-card { background-color: #16191C; border: 1px solid rgba(255,255,255,0.08); border-radius: 10px; padding: 14px 16px; height: 100%; }
    .kpi-card .kpi-label { font-size: 0.82rem; color: #9AA5AB; margin-bottom: 4px; }
    .kpi-card .kpi-value { font-size: 1.7rem; font-weight: 700; color: #F2F5F4; }
    .kpi-blue   { border-left: 3px solid #38BDF8; }
    .kpi-amber  { border-left: 3px solid #FBBF24; }
    .kpi-purple { border-left: 3px solid #A78BFA; }
    .kpi-teal   { border-left: 3px solid #2DD4BF; }
    .kpi-green  { border-left: 3px solid #34D399; }
    .kpi-red    { border-left: 3px solid #F87171; }
    .kpi-brown  { border-left: 3px solid #B45309; }
    div[data-testid="stVerticalBlockBorderWrapper"] { background-color: #14171A; border: 1px solid rgba(255,255,255,0.08) !important; border-radius: 12px; }
    .rank-card { background: #191D20; border: 1px solid rgba(255,255,255,0.08); border-left: 3px solid #00A896; border-radius: 8px; padding: 12px 16px; margin-bottom: 10px; }
    .rank-card .title { font-weight: 600; font-size: 1.02rem; margin-bottom: 4px; color: #F2F5F4 !important; }
    .rank-card .route { font-size: 0.9rem; color: #A7B0B4 !important; }
    .rank-card .profit { font-weight: 700; color: #FBBF24 !important; margin-top: 4px; }
    .buy-tag { color: #34D399 !important; font-weight: 600; }
    .sell-tag { color: #F87171 !important; font-weight: 600; }
    button[kind="primary"] { background-color: #00A896 !important; border-color: #00A896 !important; color: #FFFFFF !important; }
    button[kind="primary"]:hover { background-color: #028090 !important; border-color: #028090 !important; }
    button[data-baseweb="tab"][aria-selected="true"] { color: #2DD4BF !important; }
    div[data-baseweb="tab-highlight"] { background-color: #2DD4BF !important; }
    footer.app-footer { text-align: center; color: #6B7A78 !important; font-size: 0.82rem; padding: 18px 0 4px 0; }
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="main-header">
    <h1>🚀 Agricultural Arbitrage Advisor</h1>
    <p>Real-time cross-state commodity price arbitrage signals, powered by AGMARKNET data</p>
</div>
""", unsafe_allow_html=True)

# ============================================================
# Load base data
# ============================================================
commodities = get_all_commodities()
overall_latest_date = get_latest_date()

with st.spinner("Calculating top opportunities..."):
    top5, insights = get_top_commodities_and_insights()

# ============================================================
# KPI Strip
# ============================================================
k1, k2, k3, k4 = st.columns(4)
with k1:
    st.markdown(f"""
    <div class="kpi-card kpi-blue">
        <div class="kpi-label">📦 Commodities Tracked</div>
        <div class="kpi-value">{len(commodities)}</div>
    </div>
    """, unsafe_allow_html=True)
with k2:
    st.markdown(f"""
    <div class="kpi-card kpi-amber">
        <div class="kpi-label">💰 Best Opportunity Today</div>
        <div class="kpi-value">₹{top5[0]['gross_profit']:.0f}</div>
    </div>
    """ if top5 else """
    <div class="kpi-card kpi-amber">
        <div class="kpi-label">💰 Best Opportunity Today</div>
        <div class="kpi-value">—</div>
    </div>
    """, unsafe_allow_html=True)
with k3:
    st.markdown(f"""
    <div class="kpi-card kpi-purple">
        <div class="kpi-label">🏅 Top Commodity</div>
        <div class="kpi-value">{top5[0]['commodity'] if top5 else '—'}</div>
    </div>
    """, unsafe_allow_html=True)
with k4:
    st.markdown(f"""
    <div class="kpi-card kpi-teal">
        <div class="kpi-label">📅 Data Freshness</div>
        <div class="kpi-value">{overall_latest_date if overall_latest_date else '—'}</div>
    </div>
    """, unsafe_allow_html=True)

st.write("")

# ============================================================
# Sidebar
# ============================================================
with st.sidebar:
    st.header("📊 About This App")
    st.markdown(f"""
    This app analyzes agricultural commodity prices across Indian states
    and identifies the best arbitrage opportunities.

    **Data Source:** AGMARKNET

    **Last Updated:** {overall_latest_date}

    **What is shown:**
    - Volume-weighted average price (price × quantity, summed and divided by total quantity)
    - Calculate your net profit by entering your costs
    """)

# ============================================================
# Tabs
# ============================================================
tab1, tab2 = st.tabs(["🔍 Find Opportunity", "📈 Market Insights"])

# ------------------------------------------------------------
# TAB 1: Find Opportunity
# ------------------------------------------------------------
with tab1:
    col1, col2 = st.columns([2, 1])

    with col1:
        with st.container(border=True):
            st.subheader("🔍 Find Arbitrage Opportunities")
            selected_commodity = st.selectbox(
                "Select a Commodity", commodities, index=0 if commodities else None
            )

            get_rec_clicked = st.button("Get Recommendation", type="primary")

            if get_rec_clicked and selected_commodity:
                with st.spinner("Analyzing data..."):
                    rec = get_recommendation(selected_commodity)

                if rec:
                    st.session_state["rec"] = rec
                else:
                    st.session_state["rec"] = None
                    st.error("No arbitrage opportunity found for this commodity.")

            rec = st.session_state.get("rec")

            if rec and rec['commodity'] == selected_commodity:
                st.success("✅ Arbitrage Opportunity Found!")

                col_a, col_b, col_c = st.columns(3)
                with col_a:
                    metric_card(f"🟢 BUY in {rec['buy_state']}", f"₹{rec['buy_price']:.2f}", color="kpi-green")
                with col_b:
                    metric_card(f"🔴 SELL in {rec['sell_state']}", f"₹{rec['sell_price']:.2f}", color="kpi-red")
                with col_c:
                    metric_card("💰 Gross Profit", f"₹{rec['gross_profit']:.2f}", "Per Quintal", color="kpi-green")

                st.caption(f"📅 Based on data from: {rec['date']}  |  Weighted avg. across {rec['states_covered']} state(s)")

                # Net Profit Calculator
                st.markdown("---")
                st.subheader("💡 Calculate Your Net Profit")

                col_cost1, col_cost2 = st.columns(2)
                with col_cost1:
                    transport_cost = st.number_input(
                        "🚚 Transport Cost (per quintal)",
                        min_value=0, max_value=10000, value=150, step=10,
                        key="transport_cost"
                    )
                with col_cost2:
                    handling_cost = st.number_input(
                        "📦 Handling/Other Costs (per quintal)",
                        min_value=0, max_value=5000, value=50, step=10,
                        key="handling_cost"
                    )

                total_cost = transport_cost + handling_cost
                net_profit = rec['gross_profit'] - total_cost

                col_result1, col_result2, col_result3 = st.columns(3)
                with col_result1:
                    metric_card("💰 Gross Profit", f"₹{rec['gross_profit']:.2f}", "Per Quintal", color="kpi-green")
                with col_result2:
                    metric_card("📦 Total Costs", f"₹{total_cost:.2f}", f"₹{transport_cost} + ₹{handling_cost}", color="kpi-brown")
                with col_result3:
                    if net_profit > 0:
                        metric_card("✅ Net Profit", f"₹{net_profit:.2f}", "Per Quintal", color="kpi-green")
                    else:
                        metric_card("❌ Net Profit", f"₹{net_profit:.2f}", "Not Profitable", color="kpi-red")

                if net_profit > 0:
                    st.success(f"✅ You can make ₹{net_profit:.2f} per quintal after costs by buying from {rec['buy_state']} and selling in {rec['sell_state']}.")
                else:
                    st.warning("⚠️ After deducting costs, this trade is not profitable. Try reducing costs or finding a better route.")
            elif not commodities:
                st.info("No commodity data available yet.")
            else:
                st.info("Select a commodity and click **Get Recommendation** to see results.")

    with col2:
        with st.container(border=True):
            st.subheader("🏆 Top 5 Commodities")
            if top5:
                for i, item in enumerate(top5, 1):
                    st.markdown(f"""
                    <div class="rank-card">
                        <div class="title">#{i} {item['commodity']}</div>
                        <div class="route">
                            <span class="buy-tag">↓ {item['buy_state']} ₹{item['buy_price']:.0f}</span>
                            &nbsp;→&nbsp;
                            <span class="sell-tag">↑ {item['sell_state']} ₹{item['sell_price']:.0f}</span>
                        </div>
                        <div class="profit">💰 ₹{item['gross_profit']:.0f} gross/quintal</div>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.write("No opportunities found today")

    rec = st.session_state.get("rec")
    if rec and rec['commodity'] == selected_commodity:
        st.markdown("---")
        with st.container(border=True):
            st.subheader("📊 Price Comparison Across States")

            conn = get_connection()
            chart_query = """
            SELECT state,
                   SUM(modal_price * arrival_quantity) / SUM(arrival_quantity) as max_price
            FROM commodity_prices
            WHERE commodity = %s AND date = %s AND modal_price > 0 AND arrival_quantity > 0
            GROUP BY state
            HAVING SUM(arrival_quantity) > 0
            ORDER BY max_price
            """
            chart_df = pd.read_sql(chart_query, conn, params=[selected_commodity, rec['date']])
            conn.close()

            if not chart_df.empty:
                n = len(chart_df)
                colors = []
                for i in range(n):
                    if i == 0: colors.append('#1B8A5A')
                    elif i == n - 1: colors.append('#B00020')
                    else: colors.append('#4682B4')

                fig = px.bar(
                    chart_df, x='state', y='max_price',
                    text=chart_df['max_price'].apply(lambda v: f"₹{v:.0f}"),
                    title=f"{selected_commodity} Prices by State",
                    template='plotly_dark'
                )
                fig.update_traces(marker_color=colors, textposition='outside', textfont_color='#F2F5F4')
                fig.update_layout(
                    plot_bgcolor='#101B1A', paper_bgcolor='#101B1A',
                    font=dict(color='#F2F5F4'), title_font=dict(color='#F2F5F4', size=16),
                    xaxis_title="State", yaxis_title="Weighted Avg. Price (₹/Quintal)",
                    xaxis_tickangle=-45, showlegend=False, height=420,
                    margin=dict(t=50, b=10, l=10, r=10)
                )
                fig.update_xaxes(color='#F2F5F4', tickfont=dict(color='#F2F5F4'), title_font=dict(color='#F2F5F4'), linecolor='rgba(255,255,255,0.2)', gridcolor='rgba(255,255,255,0.08)')
                fig.update_yaxes(color='#F2F5F4', tickfont=dict(color='#F2F5F4'), title_font=dict(color='#F2F5F4'), linecolor='rgba(255,255,255,0.2)', gridcolor='rgba(255,255,255,0.08)')
                st.plotly_chart(fig, use_container_width=True, theme=None)
                st.caption("🟢 Green = Buy (Cheapest)  |  🔴 Red = Sell (Most Expensive)  |  Volume-weighted average, same date as recommendation")

# ------------------------------------------------------------
# TAB 2: Market Insights
# ------------------------------------------------------------
with tab2:
    all_recs = insights['all_recs']
    buy_counts = insights['buy_counts']
    sell_counts = insights['sell_counts']

    if not all_recs:
        st.info("No arbitrage data available yet.")
    else:
        top_buy_state = max(buy_counts, key=buy_counts.get)
        top_sell_state = max(sell_counts, key=sell_counts.get)

        i1, i2, i3, i4 = st.columns(4)
        i1.metric("📊 Profitable Routes", len(all_recs))
        i2.metric("📈 Avg Profit Margin", f"{insights['avg_margin']}%")
        i3.metric("🟢 Cheapest Most Often", top_buy_state, f"{buy_counts[top_buy_state]} commodities")
        i4.metric("🔴 Priciest Most Often", top_sell_state, f"{sell_counts[top_sell_state]} commodities")

        st.markdown("---")

        col_left, col_right = st.columns(2)

        with col_left:
            with st.container(border=True):
                st.subheader("💹 Best Return by % Margin")
                st.caption("Ranked by profit as a % of buy price — not the same list as raw ₹ profit")
                margin_df = pd.DataFrame(insights['top_margin']).sort_values('margin_pct')
                fig3 = px.bar(margin_df, x='margin_pct', y='commodity', orientation='h', text=margin_df['margin_pct'].apply(lambda v: f"{v:.1f}%"), template='plotly_dark')
                fig3.update_traces(marker_color='#7B2CBF', textposition='outside', textfont_color='#F2F5F4')
                fig3.update_layout(plot_bgcolor='#101B1A', paper_bgcolor='#101B1A', font=dict(color='#F2F5F4'), xaxis_title="Profit Margin (%)", yaxis_title="", height=360, margin=dict(t=20, b=10, l=10, r=10))
                fig3.update_xaxes(color='#F2F5F4', tickfont=dict(color='#F2F5F4'), title_font=dict(color='#F2F5F4'), linecolor='rgba(255,255,255,0.2)', gridcolor='rgba(255,255,255,0.08)')
                fig3.update_yaxes(color='#F2F5F4', tickfont=dict(color='#F2F5F4'), title_font=dict(color='#F2F5F4'), linecolor='rgba(255,255,255,0.2)', gridcolor='rgba(255,255,255,0.08)')
                st.plotly_chart(fig3, use_container_width=True, theme=None)

        with col_right:
            with st.container(border=True):
                st.subheader("🟢 Best Sourcing States")
                st.caption("How many commodities each state offers at the lowest price")
                buy_df = pd.DataFrame(sorted(buy_counts.items(), key=lambda x: x[1]), columns=['state', 'count'])
                fig4 = px.bar(buy_df, x='count', y='state', orientation='h', text='count', template='plotly_dark')
                fig4.update_traces(marker_color='#1B8A5A', textposition='outside', textfont_color='#F2F5F4')
                fig4.update_layout(plot_bgcolor='#101B1A', paper_bgcolor='#101B1A', font=dict(color='#F2F5F4'), xaxis_title="Commodities Cheapest Here", yaxis_title="", height=360, margin=dict(t=20, b=10, l=10, r=10))
                fig4.update_xaxes(color='#F2F5F4', tickfont=dict(color='#F2F5F4'), title_font=dict(color='#F2F5F4'), linecolor='rgba(255,255,255,0.2)', gridcolor='rgba(255,255,255,0.08)')
                fig4.update_yaxes(color='#F2F5F4', tickfont=dict(color='#F2F5F4'), title_font=dict(color='#F2F5F4'), linecolor='rgba(255,255,255,0.2)', gridcolor='rgba(255,255,255,0.08)')
                st.plotly_chart(fig4, use_container_width=True, theme=None)

        with st.container(border=True):
            st.subheader("🎯 Price Spread Across All Commodities")
            st.caption("Each point is one commodity — further above the diagonal means a bigger arbitrage gap. Bubble size = gross profit.")
            scatter_df = pd.DataFrame(all_recs)
            fig5 = px.scatter(scatter_df, x='buy_price', y='sell_price', size='gross_profit', color='margin_pct', hover_name='commodity', hover_data={'buy_state': True, 'sell_state': True, 'buy_price': ':.0f', 'sell_price': ':.0f', 'margin_pct': ':.1f'}, color_continuous_scale='Teal', template='plotly_dark')
            max_val = max(scatter_df['sell_price'].max(), scatter_df['buy_price'].max()) * 1.05
            fig5.add_shape(type='line', x0=0, y0=0, x1=max_val, y1=max_val, line=dict(color='#CCCCCC', dash='dash'))
            fig5.update_layout(plot_bgcolor='#101B1A', paper_bgcolor='#101B1A', font=dict(color='#F2F5F4'), xaxis_title="Cheapest State Price (₹/Quintal)", yaxis_title="Priciest State Price (₹/Quintal)", height=460, margin=dict(t=20, b=10, l=10, r=10), coloraxis_colorbar=dict(title="Margin %", tickfont=dict(color='#F2F5F4'), title_font=dict(color='#F2F5F4')))
            fig5.update_xaxes(color='#F2F5F4', tickfont=dict(color='#F2F5F4'), title_font=dict(color='#F2F5F4'), linecolor='rgba(255,255,255,0.2)', gridcolor='rgba(255,255,255,0.08)')
            fig5.update_yaxes(color='#F2F5F4', tickfont=dict(color='#F2F5F4'), title_font=dict(color='#F2F5F4'), linecolor='rgba(255,255,255,0.2)', gridcolor='rgba(255,255,255,0.08)')
            st.plotly_chart(fig5, use_container_width=True, theme=None)

# ============================================================
# Footer
# ============================================================
st.markdown(f"""
<footer class="app-footer">
    Data updated: {overall_latest_date} &nbsp;|&nbsp; Built with Streamlit 🌾
</footer>
""", unsafe_allow_html=True)
