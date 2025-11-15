import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import os
import json

# Get the absolute path of the directory where this script is located
PROJECT_DIR = os.path.abspath(os.path.dirname(__file__))
# Define the path for the data file, inside that directory
DATA_FILE = os.path.join(PROJECT_DIR, "spx_data.json")

def get_spx_data():
    # Fetch 500 calendar days
    end_date = datetime.now()
    start_date = end_date - timedelta(days=500) 

    try:
        spx_data = yf.download('^GSPC', start=start_date, end=end_date, progress=False)
        vix_data = yf.download('^VIX', start=start_date, end=end_date, progress=False)
        
        if spx_data.empty or vix_data.empty:
            print("Error: No data fetched from yfinance.")
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

    # Shift for visualization
    df['1σ_Upper'] = df['Predicted_1σ_Upper'].shift(1)
    df['1σ_Lower'] = df['Predicted_1σ_Lower'].shift(1)
    df['2σ_Upper'] = df['Predicted_2σ_Upper'].shift(1)
    df['2σ_Lower'] = df['Predicted_2σ_Lower'].shift(1)

    # Compare today's actual SPX to YESTERDAY'S predicted (shifted) bands
    df['Within_1σ'] = (df['SPX'] >= df['1σ_Lower']) & (df['SPX'] <= df['1σ_Upper'])
    df['Within_2σ'] = (df['SPX'] >= df['2σ_Lower']) & (df['SPX'] <= df['2σ_Upper'])
    df['Outside_1σ'] = ~df['Within_1σ'] & df['Within_2σ']
    df['Outside_2σ'] = ~df['Within_2σ']
    
    # We save the full, clean dataframe (skip first NaN row)
    return df.iloc[1:].copy()

def get_display_data(df):
    """
    Processes the dataframe to get all strings and values
    for the web app.
    """
    # Get data for the last two trading days
    latest = df.iloc[-1]
    previous = df.iloc[-2]

    # --- Date Logic ---
    latest_date_str = latest['Date'].strftime('%a, %b %d')
    previous_date_str = previous['Date'].strftime('%a, %b %d')

    # Logic for next prediction date (handles weekends)
    next_day = latest['Date'] + pd.Timedelta(days=1)
    if next_day.weekday() == 5:  # Saturday
        next_day += pd.Timedelta(days=2)  # Skip to Monday
    elif next_day.weekday() == 6:  # Sunday
        next_day += pd.Timedelta(days=1)  # Skip to Monday
    
    prediction_date_str = next_day.strftime('%a, %b %d')

    # --- Result Logic ---
    if latest['Outside_2σ']:
        latest_result_str = '<strong style="color:black;">Outside 2σ (Rare)</strong>'
    elif latest['Outside_1σ']:
        latest_result_str = '<strong style="color:red;">Outside 1σ</strong>'
    elif latest['Within_1σ']:
        latest_result_str = '<strong style="color:green;">Within 1σ</strong>'
    else:
        latest_result_str = "N/A"

    # --- Compile all data into one dictionary ---
    display_data = {
        "latest_date_str": latest_date_str,
        "previous_date_str": previous_date_str,
        "prediction_date_str": prediction_date_str,
        "latest_result_str": latest_result_str,
        
        # Latest Close Card
        "latest_spx": latest['SPX'],
        "latest_vix": latest['VIX'],
        "previous_spx": previous['SPX'],
        "previous_vix": previous['VIX'],
        
        # Range Test Card
        "test_1s_lower": latest['1σ_Lower'],
        "test_1s_upper": latest['1σ_Upper'],
        "test_2s_lower": latest['2σ_Lower'],
        "test_2s_upper": latest['2σ_Upper'],
        "test_actual_close": latest['SPX'],
        
        # Prediction Card
        "pred_1s_lower": latest['Predicted_1σ_Lower'],
        "pred_1s_upper": latest['Predicted_1σ_Upper'],
        "pred_1s_range": latest['Predicted_1σ_Upper'] - latest['Predicted_1σ_Lower'],
        "pred_2s_lower": latest['Predicted_2σ_Lower'],
        "pred_2s_upper": latest['Predicted_2σ_Upper'],
        "pred_2s_range": latest['Predicted_2σ_Upper'] - latest['Predicted_2σ_Lower'],
    }
    return display_data


if __name__ == "__main__":
    print("Starting data fetch...")
    dataframe = get_spx_data()
    
    if dataframe is not None and not dataframe.empty:
        # 1. Process data for display
        display_data = get_display_data(dataframe)
        
        # 2. Save the raw dataframe (for the chart) as JSON
        dataframe.to_json(DATA_FILE, orient="split", date_format="iso")
        
        # 3. Save the *display data* to a separate JSON file
        # This makes the web app SUPER simple
        display_file_path = os.path.join(PROJECT_DIR, "display_data.json")
        with open(display_file_path, 'w') as f:
            json.dump(display_data, f)
            
        print(f"Successfully saved dataframe to {DATA_FILE}")
        print(f"Successfully saved display data to {display_file_path}")
    else:
        print("Failed to fetch data.")