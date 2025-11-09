from flask import Flask, render_template_string, request
import yfinance as yf
import plotly.graph_objs as go
import pandas as pd
from datetime import datetime, timedelta
import os

app = Flask(__name__)

def get_spx_data(days_to_fetch):
    """
    Fetches and processes SPX and VIX data for the specified number of calendar days.
    """
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days_to_fetch)

    try:
        spx_data = yf.download('^GSPC', start=start_date, end=end_date, progress=False)
        vix_data = yf.download('^VIX', start=start_date, end=end_date, progress=False)
        
        if spx_data.empty or vix_data.empty:
            print("Error: No data fetched from yfinance. Check ticker symbols or date range.")
            return None
    except Exception as e:
        print(f"Error downloading data from yfinance: {e}")
        return None

    df = pd.DataFrame()
    df['Date'] = spx_data.index
    df['SPX'] = spx_data['Close'].values
    df['VIX'] = vix_data['Close'].reindex(spx_data.index, method='ffill').values

    # Compute predicted bands
    df['Daily_Sigma'] = df['VIX'] / 15.87
    df['Predicted_1σ_Upper'] = df['SPX'] * (1 + df['Daily_Sigma'] / 100)
    df['Predicted_1σ_Lower'] = df['SPX'] * (1 - df['Daily_Sigma'] / 100)
    df['Predicted_2σ_Upper'] = df['SPX'] * (1 + 2 * df['Daily_Sigma'] / 100)
    df['Predicted_2σ_Lower'] = df['SPX'] * (1 - 2 * df['Daily_Sigma'] / 100)

    # Shift for visualization: yesterday's prediction applies to today
    df['1σ_Upper'] = df['Predicted_1σ_Upper'].shift(1)
    df['1σ_Lower'] = df['Predicted_1σ_Lower'].shift(1)
    df['2σ_Upper'] = df['Predicted_2σ_Upper'].shift(1)
    df['2σ_Lower'] = df['Predicted_2σ_Lower'].shift(1)

    # Compare today's actual SPX to YESTERDAY'S predicted (shifted) bands
    df['Within_1σ'] = (df['SPX'] >= df['1σ_Lower']) & (df['SPX'] <= df['1σ_Upper'])
    df['Within_2σ'] = (df['SPX'] >= df['2σ_Lower']) & (df['SPX'] <= df['2σ_Upper'])
    df['Outside_1σ'] = ~df['Within_1σ'] & df['Within_2σ']
    df['Outside_2σ'] = ~df['Within_2σ']

    return df.copy()


@app.route('/')
def index():
    # === 1. Get and validate 'days' input ===
    try:
        # Get 'days' from URL query parameter, default to 40
        days_to_display = int(request.args.get('days', 40))
    except ValueError:
        days_to_display = 40
    
    # Enforce reasonable limits
    if days_to_display < 10: days_to_display = 10
    if days_to_display > 500: days_to_display = 500

    # Fetch extra calendar days to ensure we have enough trading days
    calendar_days_to_fetch = int(days_to_display * 1.7 + 5) 
    
    # === 2. Fetch and clean data ===
    df_full = get_spx_data(calendar_days_to_fetch)

    # === 3. Handle data-fetching errors ===
    if df_full is None:
        return """
        <body style="font-family: Arial, sans-serif; padding: 20px;">
        <h1>Error fetching data from Yahoo Finance.</h1>
        <p>This can happen if Yahoo's service is temporarily down or if there's a network issue.</p>
        <p>Please <a href="/">try again</a> in a few moments.</p>
        </body>
        """

    # Remove first row (which has NaN from .shift())
    df_clean = df_full.iloc[1:].copy()

    if df_clean.empty or len(df_clean) < 2:
        return f"""
        <body style="font-family: Arial, sans-serif; padding: 20px;">
        <h1>Error: Not enough data retrieved to display.</h1>
        <p>Tried to fetch {calendar_days_to_fetch} calendar days but it resulted in less than 2 rows of processable data.</p>
        <p>Please <a href="/">try again</a> later or try a larger number of days.</p>
        </body>
        """

    # Get the final dataframe for charting (last N days)
    df = df_clean.tail(days_to_display).copy()
    
    # Ensure we still have enough data after tailing
    if df.empty or len(df) < 2:
         return "<h1>Error: Not enough processed data to display after filtering.</h1>"

    # === 4. Get stats from the *clean* dataframe (before tail) ===
    # 'today' is the last row of *all* clean data
    today_stats = df_clean.iloc[-1]
    yesterday_stats = df_clean.iloc[-2]
            
    # === 5. Build Chart (uses `df`) ===
    fig = go.Figure()

    # Add one-day-ahead prediction (for next trading day)
    tomorrow_date = pd.Timestamp(df['Date'].iloc[-1]) + pd.Timedelta(days=1)
    df_tomorrow = pd.DataFrame({
        'Date': [tomorrow_date],
        'SPX': [pd.NA],
        '1σ_Lower': [today_stats['Predicted_1σ_Lower']], # Use 'today_stats' for tomorrow's prediction
        '1σ_Upper': [today_stats['Predicted_1σ_Upper']],
        '2σ_Lower': [today_stats['Predicted_2σ_Lower']],
        '2σ_Upper': [today_stats['Predicted_2σ_Upper']],
    })
    df_all = pd.concat([df, df_tomorrow], ignore_index=True)

    # === Bands (draw first so they stay below markers) ===
    # 2σ band
    fig.add_trace(go.Scatter(
        x=df_all['Date'], y=df_all['2σ_Upper'],
        name='2σ Upper',
        line=dict(color='red', dash='dot', width=1),
        showlegend=False,
        hovertemplate='2σ Upper: %{y:.2f}<extra></extra>'
    ))
    fig.add_trace(go.Scatter(
        x=df_all['Date'], y=df_all['2σ_Lower'],
        name='2σ Band',
        line=dict(color='red', dash='dot', width=1),
        fill='tonexty',
        fillcolor='rgba(255,0,0,0.05)',
        showlegend=False, # Hide from legend
        hovertemplate='2σ Lower: %{y:.2f}<extra></extra>'
    ))

    # 1σ band
    fig.add_trace(go.Scatter(
        x=df_all['Date'], y=df_all['1σ_Upper'],
        name='1σ Upper',
        line=dict(color='orange', dash='dash', width=1.5),
        showlegend=False,
        hovertemplate='1σ Upper: %{y:.2f}<extra></extra>'
    ))
    fig.add_trace(go.Scatter(
        x=df_all['Date'], y=df_all['1σ_Lower'],
        name='1σ Band',
        line=dict(color='orange', dash='dash', width=1.5),
        fill='tonexty',
        fillcolor='rgba(255,165,0,0.1)',
        showlegend=False, # Hide from legend
        hovertemplate='1σ Lower: %{y:.2f}<extra></extra>'
    ))

    # === SPX Actual Close ===
    fig.add_trace(go.Scatter(
        x=df['Date'], y=df['SPX'],
        name='SPX Actual Close',
        mode='lines+markers',
        line=dict(color='blue', width=2),
        marker=dict(size=5, color='blue'),
        hovertemplate='SPX Close: %{y:.2f}<extra></extra>'
    ))

    # === Markers for outliers (draw AFTER SPX so they stay visible) ===
    df_outside_1σ = df[df['Outside_1σ']]
    if not df_outside_1σ.empty:
        fig.add_trace(go.Scatter(
            x=df_outside_1σ['Date'],
            y=df_outside_1σ['SPX'],
            mode='markers',
            name='Outside 1σ',
            marker=dict(color='red', size=11, symbol='x', line=dict(width=2, color='red')),
            hovertemplate='Outside 1σ: %{y:.2f}<extra></extra>',
            showlegend=False # Hide from legend
        ))

    df_outside_2σ = df[df['Outside_2σ']]
    if not df_outside_2σ.empty:
        fig.add_trace(go.Scatter(
            x=df_outside_2σ['Date'],
            y=df_outside_2σ['SPX'],
            mode='markers',
            name='Outside 2σ (Rare)',
            marker=dict(color='black', size=12, symbol='x', line=dict(width=2.5, color='black')),
            hovertemplate='Outside 2σ: %{y:.2f}<extra></extra>',
            showlegend=False # Hide from legend
        ))

    # === Tomorrow’s predicted range shading ===
    fig.add_shape(
        type="rect",
        x0=df['Date'].iloc[-1],
        x1=tomorrow_date,
        y0=df.iloc[-1]['2σ_Lower'], # Use last row of *charted* data
        y1=df.iloc[-1]['2σ_Upper'], # Use last row of *charted* data
        fillcolor="rgba(150,150,150,0.08)",
        line=dict(color="gray", width=1, dash="dot"),
        layer="below"
    )
    fig.add_annotation(
        x=tomorrow_date,
        y=df.iloc[-1]['2σ_Upper'],
        text="Tomorrow Prediction (Range Only)",
        showarrow=False, xanchor="right", yanchor="bottom",
        font=dict(size=12, color="gray")
    )

    # === 6. Update layout (Remove default legend) ===
    fig.update_layout(
        title=f"SPX Actual vs Predicted σ Bands (Updated: {datetime.now().strftime('%Y-%m-%d %H:%M')})",
        xaxis_title='Date',
        yaxis_title='Price',
        hovermode='x unified',
        template='plotly_white',
        height=600,
        showlegend=False # <-- THIS HIDES THE DUPLICATE LEGEND
    )

    # === 7. Calculate Stats ===
    
    # Today's actual ranges (based on yesterday's prediction)
    # Use df.iloc[-1] because it's the "today" row *for the chart*
    today_chart = df.iloc[-1]
    today_1s_range = today_chart['1σ_Upper'] - today_chart['1σ_Lower']
    today_2s_range = today_chart['2σ_Upper'] - today_chart['2σ_Lower']
    
    # Tomorrow's predicted ranges (based on today's closing data)
    # Use 'today_stats' which is the absolute latest data we have
    tomorrow_1s_range = today_stats['Predicted_1σ_Upper'] - today_stats['Predicted_1σ_Lower']
    tomorrow_2s_range = today_stats['Predicted_2σ_Upper'] - today_stats['Predicted_2σ_Lower']

    # Model performance stats (based on the `df` being charted)
    total_days = len(df)
    within_1σ = df['Within_1σ'].sum()
    outside_1σ = df['Outside_1σ'].sum()
    outside_2σ = df['Outside_2σ'].sum()

    # === 8. HTML Template ===
    html = '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>SPX Tracker</title>
        <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }
            .container { max-width: 1400px; margin: 0 auto; }
            
            /* Header styles for Title and Form */
            .header-flex { 
                display: flex; 
                justify-content: space-between; 
                align-items: center; 
                flex-wrap: wrap; 
                margin-bottom: 15px;
                gap: 15px;
            }
            .header-flex h1 { margin: 0; }
            
            /* Form styles */
            .form-box { 
                background: white; 
                padding: 15px 20px; 
                border-radius: 8px; 
                box-shadow: 0 2px 4px rgba(0,0,0,0.1); 
            }
            .form-box form { display: flex; align-items: center; gap: 10px; margin: 0; }
            .form-box label { font-weight: bold; }
            .form-box input[type="number"] { 
                width: 70px; 
                padding: 8px; 
                border: 1px solid #ccc; 
                border-radius: 4px; 
                font-size: 14px;
            }
            .form-box button { 
                padding: 8px 12px; 
                background: #007bff; 
                color: white; 
                border: none; 
                border-radius: 4px; 
                cursor: pointer;
                font-size: 14px;
            }
            .form-box button:hover { background: #0056b3; }

            /* Stats Grid styles */
            .stats-grid { 
                display: grid; 
                grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); 
                gap: 20px; 
                margin-bottom: 20px; 
            }
            .stats-box { 
                background: white; 
                padding: 20px; 
                border-radius: 8px; 
                box-shadow: 0 2px 4px rgba(0,0,0,0.1); 
            }
            .stats-box h3 { margin-top: 0; }
            .stats-box p { margin: 8px 0; }
            .stats-box hr { border: 0; border-top: 1px solid #eee; margin: 10px 0; }
            
            /* Chart box styles */
            .chart-box { 
                background: white; 
                padding: 20px; 
                border-radius: 8px; 
                box-shadow: 0 2px 4px rgba(0,0,0,0.1); 
            }
        </style>
    </head>
    <body>
        <div class="container">
            
            <div class="header-flex">
                <h1>S&P 500 INDEX (SPX) Daily Range Tracker</h1>
                <div class="form-box">
                    <form method="get" action="/">
                        <label for="days">Days to Display:</label>
                        <input type="number" id="days" name="days" value="{{ current_days }}" min="10" max="500">
                        <button type="submit">Update</button>
                    </form>
                </div>
            </div>

            <div class="stats-grid">
                <div class="stats-box">
                    <h3>Market Values</h3>
                    <p>SPX Today: <strong>{{"%.2f"|format(spx_today)}}</strong></p>
                    <p>VIX Today: <strong>{{"%.2f"|format(vix_today)}}</strong></p>
                    <hr>
                    <p style="color:#555;">SPX Yesterday: {{"%.2f"|format(spx_yesterday)}}</p>
                    <p style="color:#555;">VIX Yesterday: {{"%.2f"|format(vix_yesterday)}}</p>
                </div>
                <div class="stats-box">
                    <h3>Today's Actual Range</h3>
                    <p>1σ: <strong>{{"%.2f"|format(pred_today_1l)}} - {{"%.2f"|format(pred_today_1u)}}</strong> ({{ "%.2f"|format(pred_today_1r) }} pts)</p>
                    <p>2σ: <strong>{{"%.2f"|format(pred_today_2l)}} - {{"%.2f"|format(pred_today_2u)}}</strong> ({{ "%.2f"|format(pred_today_2r) }} pts)</p>
                </div>
                <div class="stats-box">
                    <h3>Tomorrow's Predicted Range</h3>
                    <p>1σ: <strong>{{"%.2f"|format(pred_tmrw_1l)}} - {{"%.2f"|format(pred_tmrw_1u)}}</strong> ({{ "%.2f"|format(pred_tmrw_1r) }} pts)</p>
                    <p>2σ: <strong>{{"%.2f"|format(pred_tmrw_2l)}} - {{"%.2f"|format(pred_tmrw_2u)}}</strong> ({{ "%.2f"|format(pred_tmrw_2r) }} pts)</p>
                </div>
                <div class="stats-box">
                    <h3>Model Performance ({{td}} days)</h3>
                    <p>Within 1σ: {{w1}} ({{"%.1f"|format(p1)}}%)</p>
                    <p>Outside 1σ: {{o1}} ({{"%.1f"|format(p4)}}%)</p>
                    <p>Outside 2σ (Rare): {{o2}} ({{"%.1f"|format(p3)}}%)</p>
                </div>
            </div>

            <div class="chart-box">
                {{ chart_html|safe }}
                <p style="font-size:13px;color:#555;margin-top:10px;">
                    <b>Blue Line</b> = SPX Actual Close &nbsp;·&nbsp; 
                    <b>Orange Band</b> = 1σ Predicted Range &nbsp;·&nbsp; 
                    <b>Red Band</b> = 2σ Predicted Range &nbsp;·&nbsp; 
                    <b style="color:red;">Red X</b> = Outside 1σ &nbsp;·&nbsp; 
                    <b style="color:black;">Black X</b> = Outside 2σ (Rare)
                </p>
            </div>
        </div>
    </body>
    </html>
    '''

    # === 9. Pass all variables to the template ===
    return render_template_string(
        html,
        chart_html=fig.to_html(include_plotlyjs='cdn', div_id="chart"),
        
        # Add the 'current_days' for the form
        current_days=days_to_display,
        
        # Market Values (from latest data)
        spx_today=today_stats['SPX'],
        vix_today=today_stats['VIX'],
        spx_yesterday=yesterday_stats['SPX'],
        vix_yesterday=yesterday_stats['VIX'],
        
        # Today's Predictions (from last row of *charted* data)
        pred_today_1u=today_chart['1σ_Upper'],
        pred_today_1l=today_chart['1σ_Lower'],
        pred_today_2u=today_chart['2σ_Upper'],
        pred_today_2l=today_chart['2σ_Lower'],
        pred_today_1r=today_1s_range,
        pred_today_2r=today_2s_range,

        # Tomorrow's Predictions (from latest data)
        pred_tmrw_1u=today_stats['Predicted_1σ_Upper'],
        pred_tmrw_1l=today_stats['Predicted_1σ_Lower'],
        pred_tmrw_2u=today_stats['Predicted_2σ_Upper'],
        pred_tmrw_2l=today_stats['Predicted_2σ_Lower'],
        pred_tmrw_1r=tomorrow_1s_range,
        pred_tmrw_2r=tomorrow_2s_range,

        # Model Performance (from *charted* data)
        td=total_days,
        w1=within_1σ,
        o1=outside_1σ,
        o2=outside_2σ,
        p1=(within_1σ / total_days) * 100 if total_days > 0 else 0,
        p4=(outside_1σ / total_days) * 100 if total_days > 0 else 0,
        p3=(outside_2σ / total_days) * 100 if total_days > 0 else 0
    )


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=True)