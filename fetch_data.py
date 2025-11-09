import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import os

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

if __name__ == "__main__":
    print("Starting data fetch...")
    dataframe = get_spx_data()
    
    if dataframe is not None:
        # Save to the disk as JSON in the project directory
        dataframe.to_json(DATA_FILE, orient="split", date_format="iso")
        print(f"Successfully fetched and saved data to {DATA_FILE}")
    else:
        print("Failed to fetch data.")