from flask import Flask, render_template, request
import plotly.graph_objs as go
import pandas as pd
from datetime import datetime, timedelta
import os
import json
import numpy as np

# Initialize the Flask application
app = Flask(__name__)

# --- Configuration: Define file paths ---
# Get the absolute path of the directory where this script is located
PROJECT_DIR = os.path.abspath(os.path.dirname(__file__))
# Path to the raw data file (for the chart)
DATA_FILE = os.path.join(PROJECT_DIR, "spx_data.json")
# Path to the pre-processed stats file (for the cards)
DISPLAY_FILE = os.path.join(PROJECT_DIR, "display_data.json")

# --- Main Application Route ---

@app.route('/')
def index():
    """
    Main route for the web application.
    This function runs every time a user visits the homepage.
    """
    
    # === 1. Get and Validate 'days' Query Parameter ===
    # Check if the user provided a 'days' value in the URL (e.g., /?days=60)
    # Default to 40 days if not provided.
    try:
        days_to_display = int(request.args.get('days', 40))
    except ValueError:
        # Handle non-integer input
        days_to_display = 40
    
    # Enforce min/max limits for 'days'
    if days_to_display < 10: days_to_display = 10
    if days_to_display > 500: days_to_display = 500 # 500 is our max data fetch

    # === 2. Read Data Files ===
    try:
        # Read the raw data (for the chart) from its JSON file
        # 'orient="split"' tells pandas how the JSON is structured
        df_clean = pd.read_json(DATA_FILE, orient="split")
        # Ensure the 'Date' column is converted back to datetime objects
        df_clean['Date'] = pd.to_datetime(df_clean['Date'])
        
        # Read the pre-processed display data (for the cards)
        with open(DISPLAY_FILE, 'r') as f:
            display_data = json.load(f)
            
    except FileNotFoundError:
        # Error handling if the data files don't exist
        # This happens if 'fetch_data.py' hasn't run successfully yet.
        return """
        <body style="font-family: Arial, sans-serif; padding: 20px;">
        <h1>Data file not found.</h1>
        <p>The daily data-fetching job has not run yet. Please run the 'fetch_data' task in the PythonAnywhere 'Tasks' tab.</p>
        </body>
        """
    except Exception as e:
        # Catch-all for other read errors
        return f"<h1>An error occurred reading the data file: {e}</h1>"

    # Validate that the data is usable
    if df_clean.empty or len(df_clean) < 2:
         return "<h1>Error: Loaded data is empty or invalid.</h1>"

    # === 3. Filter Data for Chart ===
    # Select the last 'N' days of data for the chart, based on user input
    df = df_clean.tail(days_to_display).copy()
    
    if df.empty or len(df) < 2:
         return "<h1>Error: Not enough processed data to display after filtering.</h1>"
            
    # === 4. Build Plotly Chart ===
    fig = go.Figure()

    # --- Add "Tomorrow's" Prediction Box ---
    # Create a "fake" date for tomorrow to anchor the prediction bands
    tomorrow_date = pd.Timestamp(df['Date'].iloc[-1]) + pd.Timedelta(days=1)
    
    # Create a single-row DataFrame for tomorrow's prediction data
    # We get this data from the 'display_data' dict, which was pre-calculated.
    df_tomorrow = pd.DataFrame({
        'Date': [tomorrow_date],
        'SPX': [np.nan], #'SPX': [pd.NA], # No 'SPX' value for tomorrow yet
        '1σ_Lower': [display_data['pred_1s_lower']],
        '1σ_Upper': [display_data['pred_1s_upper']],
        '2σ_Lower': [display_data['pred_2s_lower']],
        '2σ_Upper': [display_data['pred_2s_upper']],
    })
    # Append this "tomorrow" data to the historical data
    df_all = pd.concat([df, df_tomorrow], ignore_index=True)

    # --- Add Chart Traces (Layers) ---
    # The order here matters (from back to front)
    
    # 2σ Band (Red, dotted)
    fig.add_trace(go.Scatter(x=df_all['Date'], y=df_all['2σ_Upper'], name='2σ Upper', line=dict(color='red', dash='dot', width=1), showlegend=False, hovertemplate='2σ Upper: %{y:.2f}<extra></extra>'))
    fig.add_trace(go.Scatter(x=df_all['Date'], y=df_all['2σ_Lower'], name='2σ Band', line=dict(color='red', dash='dot', width=1), fill='tonexty', fillcolor='rgba(255,0,0,0.05)', showlegend=False, hovertemplate='2σ Lower: %{y:.2f}<extra></extra>'))
    
    # 1σ Band (Orange, dashed)
    fig.add_trace(go.Scatter(x=df_all['Date'], y=df_all['1σ_Upper'], name='1σ Upper', line=dict(color='orange', dash='dash', width=1.5), showlegend=False, hovertemplate='1σ Upper: %{y:.2f}<extra></extra>'))
    fig.add_trace(go.Scatter(x=df_all['Date'], y=df_all['1σ_Lower'], name='1σ Band', line=dict(color='orange', dash='dash', width=1.5), fill='tonexty', fillcolor='rgba(255,165,0,0.1)', showlegend=False, hovertemplate='1σ Lower: %{y:.2f}<extra></extra>'))
    
    # SPX Price (Blue, solid line with markers)
    fig.add_trace(go.Scatter(x=df['Date'], y=df['SPX'], name='SPX Actual Close', mode='lines+markers', line=dict(color='blue', width=2), marker=dict(size=5, color='blue'), hovertemplate='SPX Close: %{y:.2f}<extra></extra>'))
    
    # Markers for "Outside 1σ" (Red 'x')
    df_outside_1σ = df[df['Outside_1σ']]
    if not df_outside_1σ.empty:
        fig.add_trace(go.Scatter(x=df_outside_1σ['Date'], y=df_outside_1σ['SPX'], mode='markers', name='Outside 1σ', marker=dict(color='red', size=11, symbol='x', line=dict(width=2, color='red')), hovertemplate='Outside 1σ: %{y:.2f}<extra></extra>', showlegend=False))

    # Markers for "Outside 2σ" (Black 'x')
    df_outside_2σ = df[df['Outside_2σ']]
    if not df_outside_2σ.empty:
        fig.add_trace(go.Scatter(x=df_outside_2σ['Date'], y=df_outside_2σ['SPX'], mode='markers', name='Outside 2σ (Rare)', marker=dict(color='black', size=12, symbol='x', line=dict(width=2.5, color='black')), hovertemplate='Outside 2σ: %{y:.2f}<extra></extra>', showlegend=False))
    
    # Add a shaded rectangle for the "prediction" area
    fig.add_shape(type="rect", 
                  x0=df['Date'].iloc[-1], # Start at last data point
                  x1=tomorrow_date,        # End at "tomorrow"
                  y0=df.iloc[-1]['2σ_Lower'], # Use '2σ_Lower' from *today's* prediction
                  y1=df.iloc[-1]['2σ_Upper'], # Use '2σ_Upper' from *today's* prediction
                  fillcolor="rgba(150,150,150,0.08)", line=dict(color="gray", width=1, dash="dot"), layer="below")
    
    # Add text label for the prediction area
    fig.add_annotation(x=tomorrow_date, y=df.iloc[-1]['2σ_Upper'], text="Prediction (Range Only)", showarrow=False, xanchor="right", yanchor="bottom", font=dict(size=12, color="gray"))

    # --- Final Chart Layout ---
    fig.update_layout(
        title=f"SPX Actual vs Predicted σ Bands (Data as of {display_data['latest_date_str']})",
        xaxis_title='Date', yaxis_title='Price',
        hovermode='x unified', # Shows all tooltips for a given date at once
        template='plotly_white',
        height=600,
        showlegend=False
    )

    # === 5. Calculate Model Performance Stats ===
    # Calculate simple statistics based on the 'N' days of data being shown
    total_days = len(df)
    within_1σ = df['Within_1σ'].sum()
    outside_1σ = df['Outside_1σ'].sum()
    outside_2σ = df['Outside_2σ'].sum()


    # === 6. Render the Template ===
    # Pass all the calculated variables into the HTML string
    return render_template(
        "index.html",
        chart_html=fig.to_html(include_plotlyjs='cdn', div_id="chart"),
        current_days=days_to_display,
        
        # Pass the whole display_data dictionary
        display=display_data,
        
        # Model Performance stats
        td=total_days,
        w1=within_1σ,
        o1=outside_1σ,
        o2=outside_2σ,
        p1=(within_1σ / total_days) * 100 if total_days > 0 else 0,
        p4=(outside_1σ / total_days) * 100 if total_days > 0 else 0,
        p3=(outside_2σ / total_days) * 100 if total_days > 0 else 0
    )

# --- Main Execution ---

# This block runs ONLY when the script is executed directly (e.g., `python app.py`)
if __name__ == '__main__':
    # Get port from environment variable, default to 10000
    port = int(os.environ.get('PORT', 10000))
    # Run the app. debug=True allows for auto-reloading on code changes.
    # Set debug=False for production on PythonAnywhere.
    app.run(host='0.0.0.0', port=port, debug=True)