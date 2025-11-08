from flask import Flask, render_template_string
import yfinance as yf
import plotly.graph_objs as go
import pandas as pd
from datetime import datetime, timedelta
import numpy as np
import os

app = Flask(__name__)

def get_spx_data():
    try:
        # Fetch 31 days to calculate predictions for 30 days
        end_date = datetime.now()
        start_date = end_date - timedelta(days=40)
        
        # Download data
        spx_data = yf.download('^GSPC', start=start_date, end=end_date, progress=False)
        vix_data = yf.download('^VIX', start=start_date, end=end_date, progress=False)
        
        if spx_data.empty or vix_data.empty:
            raise ValueError("No data received")
        
        # Create DataFrame
        df = pd.DataFrame()
        df['Date'] = spx_data.index
        df['SPX'] = spx_data['Close'].values
        df['VIX'] = vix_data['Close'].reindex(spx_data.index, method='ffill').values
        
        # Calculate TODAY's predicted bands for TOMORROW
        df['Daily_Sigma'] = df['VIX'] / 15.87
        df['Predicted_1σ_Upper'] = df['SPX'] * (1 + df['Daily_Sigma']/100)
        df['Predicted_1σ_Lower'] = df['SPX'] * (1 - df['Daily_Sigma']/100)
        df['Predicted_2σ_Upper'] = df['SPX'] * (1 + 2*df['Daily_Sigma']/100)
        df['Predicted_2σ_Lower'] = df['SPX'] * (1 - 2*df['Daily_Sigma']/100)
        
        # Shift predictions forward by 1 day (today's prediction is for tomorrow)
        df['1σ_Upper'] = df['Predicted_1σ_Upper'].shift(1)
        df['1σ_Lower'] = df['Predicted_1σ_Lower'].shift(1)
        df['2σ_Upper'] = df['Predicted_2σ_Upper'].shift(1)
        df['2σ_Lower'] = df['Predicted_2σ_Lower'].shift(1)
        
        # Check if actual close was within predicted bands
        df['Within_1σ'] = (df['SPX'] >= df['1σ_Lower']) & (df['SPX'] <= df['1σ_Upper'])
        df['Within_2σ'] = (df['SPX'] >= df['2σ_Lower']) & (df['SPX'] <= df['2σ_Upper'])
        df['Outside_2σ'] = ~df['Within_2σ']
        
        # Remove first row (no prediction for it) and last few if incomplete
        df = df.iloc[1:-1].copy()
        
        return df
        
    except Exception as e:
        print(f"Error fetching data: {e}")
        return None

@app.route('/')
def index():
    df = get_spx_data()
    
    if df is None or df.empty:
        return "<h1>Error loading data. Please try again.</h1>"
    
    # Create Plotly chart
    fig = go.Figure()
    
    # Add 2σ bands (background)
    # fig.add_trace(go.Scatter(
    #     x=df['Date'], y=df['2σ_Upper'],
    #     name='2σ Predicted',
    #     line=dict(color='red', dash='dot', width=1),
    #     showlegend=True
    # ))

    
    # fig.add_trace(go.Scatter(
    #     x=df['Date'], y=df['2σ_Lower'],
    #     name='2σ Lower (Predicted)',
    #     line=dict(color='red', dash='dot', width=1),
    #     fill='tonexty',
    #     fillcolor='rgba(255,0,0,0.05)',
    #     showlegend=True
    # ))
    
    
    fig.add_trace(go.Scatter(
        x=df['Date'], y=df['2σ_Upper'],
        line=dict(color='red', dash='dot', width=1),
        showlegend=False
    ))
    fig.add_trace(go.Scatter(
        x=df['Date'], y=df['2σ_Lower'],
        name='2σ Band',
        line=dict(color='red', dash='dot', width=1),
        fill='tonexty',
        fillcolor='rgba(255,0,0,0.05)',
        showlegend=True
    ))

    
    # Add 1σ bands
    # fig.add_trace(go.Scatter(
    #     x=df['Date'], y=df['1σ_Upper'],
    #     name='1σ Predicted',
    #     line=dict(color='orange', dash='dash', width=1.5),
    #     showlegend=True
    # ))
    # fig.add_trace(go.Scatter(
    #     x=df['Date'], y=df['1σ_Lower'],
    #     name='1σ Lower (Predicted)',
    #     line=dict(color='orange', dash='dash', width=1.5),
    #     fill='tonexty',
    #     fillcolor='rgba(255,165,0,0.1)',
    #     showlegend=True
    # ))
    

    fig.add_trace(go.Scatter(
        x=df['Date'], y=df['1σ_Upper'],
        line=dict(color='orange', dash='dash', width=1.5),
        showlegend=False
    ))
    fig.add_trace(go.Scatter(
        x=df['Date'], y=df['1σ_Lower'],
        name='1σ Band',
        line=dict(color='orange', dash='dash', width=1.5),
        fill='tonexty',
        fillcolor='rgba(255,165,0,0.1)',
        showlegend=True
    ))




    # Add SPX line
    fig.add_trace(go.Scatter(
        x=df['Date'], y=df['SPX'],
        name='SPX Actual Close',
        line=dict(color='blue', width=2),
        mode='lines'
    ))
    
    # Add markers for breaches
    df_outside_1σ = df[~df['Within_1σ'] & df['Within_2σ']]
    df_outside_2σ = df[df['Outside_2σ']]
    
    if not df_outside_1σ.empty:
        fig.add_trace(go.Scatter(
            x=df_outside_1σ['Date'], 
            y=df_outside_1σ['SPX'],
            mode='markers',
            name='Outside 1σ',
            marker=dict(color='orange', size=8, symbol='circle'),
            showlegend=True
        ))
    
    if not df_outside_2σ.empty:
        fig.add_trace(go.Scatter(
            x=df_outside_2σ['Date'], 
            y=df_outside_2σ['SPX'],
            mode='markers',
            name='Outside 2σ (Rare)',
            marker=dict(color='red', size=10, symbol='x'),
            showlegend=True
        ))
    
    # Update layout
    fig.update_layout(
        title=f'SPX Actual vs Predicted Bands (Updated: {datetime.now().strftime("%Y-%m-%d %H:%M")})',
        xaxis_title='Date',
        yaxis_title='Price',
        hovermode='x unified',
        template='plotly_white',
        height=600,
        legend=dict(
            yanchor="top",
            y=0.99,
            xanchor="left",
            x=0.01
        )
    )
    
    # Calculate statistics
    total_days = len(df)
    within_1σ_count = df['Within_1σ'].sum()
    within_2σ_count = df['Within_2σ'].sum()
    outside_2σ_count = df['Outside_2σ'].sum()
    
    within_1σ_pct = (within_1σ_count / total_days * 100) if total_days > 0 else 0
    within_2σ_pct = (within_2σ_count / total_days * 100) if total_days > 0 else 0
    outside_2σ_pct = (outside_2σ_count / total_days * 100) if total_days > 0 else 0
    
    # Get latest values
    latest = df.iloc[-1]
    tomorrow_prediction = df.iloc[-1]  # Today's data contains tomorrow's predictions
    
    html_template = '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>SPX Tracker</title>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }
            .container { max-width: 1400px; margin: 0 auto; }
            .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; margin-bottom: 20px; }
            .stats-box { background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
            .stat-row { display: flex; justify-content: space-between; margin: 10px 0; }
            .chart-container { background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
            h1 { color: #333; text-align: center; }
            h3 { color: #666; margin-top: 0; }
            .value { font-weight: bold; color: #2196F3; }
            .success { color: #4CAF50; }
            .warning { color: #FF9800; }
            .danger { color: #F44336; }
            .performance-box { background: #f0f7ff; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🎯 SPX Daily Range Tracker - Actual vs Predicted</h1>
            
            <div class="stats-grid">
                <div class="stats-box">
                    <h3>Today's Values</h3>
                    <div class="stat-row">
                        <span>SPX Close:</span>
                        <span class="value">{{ "%.2f"|format(latest_spx) }}</span>
                    </div>
                    <div class="stat-row">
                        <span>VIX:</span>
                        <span class="value">{{ "%.2f"|format(latest_vix) }}</span>
                    </div>
                    <div class="stat-row">
                        <span>Today's Close vs Yesterday's Prediction:</span>
                        <span class="{% if latest_within_1σ %}success{% elif latest_within_2σ %}warning{% else %}danger{% endif %}">
                            {% if latest_within_1σ %}✓ Within 1σ{% elif latest_within_2σ %}⚠ Outside 1σ{% else %}✗ Outside 2σ{% endif %}
                        </span>
                    </div>
                </div>
                
                <div class="stats-box">
                    <h3>Tomorrow's Predicted Ranges</h3>
                    <div class="stat-row">
                        <span>1σ Range (68.3% expected):</span>
                        <span class="value">{{ "%.2f"|format(tomorrow_1σ_lower) }} - {{ "%.2f"|format(tomorrow_1σ_upper) }}</span>
                    </div>
                    <div class="stat-row">
                        <span>2σ Range (95.5% expected):</span>
                        <span class="value">{{ "%.2f"|format(tomorrow_2σ_lower) }} - {{ "%.2f"|format(tomorrow_2σ_upper) }}</span>
                    </div>
                </div>
                
                <div class="stats-box performance-box">
                    <h3>Model Performance ({{ total_days }} days)</h3>
                    <div class="stat-row">
                        <span>Within 1σ:</span>
                        <span class="{% if within_1σ_pct > 60 %}success{% else %}warning{% endif %}">
                            {{ within_1σ_count }}/{{ total_days }} ({{ "%.1f"|format(within_1σ_pct) }}% vs 68.3% expected)
                        </span>
                    </div>
                    <div class="stat-row">
                        <span>Within 2σ:</span>
                        <span class="{% if within_2σ_pct > 90 %}success{% else %}warning{% endif %}">
                            {{ within_2σ_count }}/{{ total_days }} ({{ "%.1f"|format(within_2σ_pct) }}% vs 95.5% expected)
                        </span>
                    </div>
                    <div class="stat-row">
                        <span>Outside 2σ (tail events):</span>
                        <span class="{% if outside_2σ_pct < 10 %}success{% else %}danger{% endif %}">
                            {{ outside_2σ_count }} days ({{ "%.1f"|format(outside_2σ_pct) }}%)
                        </span>
                    </div>
                </div>
            </div>
            
            <div class="chart-container">
                {{ chart_html|safe }}
                <p style="margin-top: 20px; color: #666; font-size: 14px;">
                    <strong>How to read:</strong> The bands show yesterday's prediction for today's close. 
                    Blue line is actual SPX close. Orange dots = closed outside 1σ but within 2σ. 
                    Red X = closed outside 2σ (rare events).
                </p>
            </div>
        </div>
    </body>
    </html>
    '''
    
    return render_template_string(
        html_template,
        chart_html=fig.to_html(include_plotlyjs='cdn', div_id="chart"),
        latest_spx=latest['SPX'],
        latest_vix=latest['VIX'],
        latest_within_1σ=latest['Within_1σ'],
        latest_within_2σ=latest['Within_2σ'],
        tomorrow_1σ_upper=latest['Predicted_1σ_Upper'],
        tomorrow_1σ_lower=latest['Predicted_1σ_Lower'],
        tomorrow_2σ_upper=latest['Predicted_2σ_Upper'],
        tomorrow_2σ_lower=latest['Predicted_2σ_Lower'],
        total_days=total_days,
        within_1σ_count=within_1σ_count,
        within_2σ_count=within_2σ_count,
        outside_2σ_count=outside_2σ_count,
        within_1σ_pct=within_1σ_pct,
        within_2σ_pct=within_2σ_pct,
        outside_2σ_pct=outside_2σ_pct
    )

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=True)