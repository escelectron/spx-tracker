from flask import Flask, render_template_string
import yfinance as yf
import plotly.graph_objs as go
import plotly.io as pio
import pandas as pd
from datetime import datetime, timedelta
import numpy as np
import os

app = Flask(__name__)

def get_spx_data():
    # Fetch 30 days of historical data
    end_date = datetime.now()
    start_date = end_date - timedelta(days=30)
    
    spx = yf.Ticker('^GSPC')
    vix = yf.Ticker('^VIX')
    
    spx_data = spx.history(start=start_date, end=end_date)
    vix_data = vix.history(start=start_date, end=end_date)
    
    # Calculate daily 1σ and 2σ bands
    df = pd.DataFrame()
    df['Date'] = spx_data.index
    df['SPX'] = spx_data['Close'].values
    df['VIX'] = vix_data['Close'].reindex(spx_data.index, method='ffill').values
    
    # Calculate sigma bands
    df['Daily_Sigma'] = df['VIX'] / 15.87
    df['1σ_Upper'] = df['SPX'] * (1 + df['Daily_Sigma']/100)
    df['1σ_Lower'] = df['SPX'] * (1 - df['Daily_Sigma']/100)
    df['2σ_Upper'] = df['SPX'] * (1 + 2*df['Daily_Sigma']/100)
    df['2σ_Lower'] = df['SPX'] * (1 - 2*df['Daily_Sigma']/100)
    
    return df

@app.route('/')
def index():
    df = get_spx_data()
    
    # Create Plotly chart
    fig = go.Figure()
    
    # Add SPX line
    fig.add_trace(go.Scatter(
        x=df['Date'], y=df['SPX'],
        name='SPX Close',
        line=dict(color='blue', width=2)
    ))
    
    # Add 1σ bands
    fig.add_trace(go.Scatter(
        x=df['Date'], y=df['1σ_Upper'],
        name='1σ Upper',
        line=dict(color='orange', dash='dash')
    ))
    fig.add_trace(go.Scatter(
        x=df['Date'], y=df['1σ_Lower'],
        name='1σ Lower',
        line=dict(color='orange', dash='dash'),
        fill='tonexty',
        fillcolor='rgba(255,165,0,0.1)'
    ))
    
    # Add 2σ bands
    fig.add_trace(go.Scatter(
        x=df['Date'], y=df['2σ_Upper'],
        name='2σ Upper',
        line=dict(color='red', dash='dot')
    ))
    fig.add_trace(go.Scatter(
        x=df['Date'], y=df['2σ_Lower'],
        name='2σ Lower',
        line=dict(color='red', dash='dot'),
        fill='tonexty',
        fillcolor='rgba(255,0,0,0.05)'
    ))
    
    # Update layout
    fig.update_layout(
        title=f'SPX with 1σ and 2σ Bands (Updated: {datetime.now().strftime("%Y-%m-%d %H:%M")})',
        xaxis_title='Date',
        yaxis_title='Price',
        hovermode='x unified',
        template='plotly_white',
        height=600
    )
    
    # Get current values for display
    latest = df.iloc[-1]
    
    html_template = '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>SPX Tracker</title>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }
            .stats { background: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; }
            .stat-row { display: flex; justify-content: space-between; margin: 10px 0; }
            .chart-container { background: white; padding: 20px; border-radius: 8px; }
            h1 { color: #333; }
            .value { font-weight: bold; color: #2196F3; }
        </style>
    </head>
    <body>
        <h1>🎯 SPX Daily Range Tracker</h1>
        <div class="stats">
            <h3>Current Values</h3>
            <div class="stat-row">
                <span>SPX Close:</span>
                <span class="value">{{ "%.2f"|format(latest_spx) }}</span>
            </div>
            <div class="stat-row">
                <span>VIX:</span>
                <span class="value">{{ "%.2f"|format(latest_vix) }}</span>
            </div>
            <div class="stat-row">
                <span>Tomorrow's 1σ Range (68.3%):</span>
                <span class="value">{{ "%.2f"|format(latest_1σ_lower) }} - {{ "%.2f"|format(latest_1σ_upper) }}</span>
            </div>
            <div class="stat-row">
                <span>Tomorrow's 2σ Range (95.5%):</span>
                <span class="value">{{ "%.2f"|format(latest_2σ_lower) }} - {{ "%.2f"|format(latest_2σ_upper) }}</span>
            </div>
        </div>
        <div class="chart-container">
            {{ chart_html|safe }}
        </div>
    </body>
    </html>
    '''
    
    return render_template_string(
        html_template,
        chart_html=fig.to_html(include_plotlyjs='cdn', div_id="chart"),
        latest_spx=latest['SPX'],
        latest_vix=latest['VIX'],
        latest_1σ_upper=latest['1σ_Upper'],
        latest_1σ_lower=latest['1σ_Lower'],
        latest_2σ_upper=latest['2σ_Upper'],
        latest_2σ_lower=latest['2σ_Lower']
    )

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)