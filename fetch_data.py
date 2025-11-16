import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import os
import json

# --- Configuration ---

# Get the absolute path of the directory where this script is located
# __file__ is a special variable that holds the path to the current script
PROJECT_DIR = os.path.abspath(os.path.dirname(__file__))

# Define the full path for the JSON file where the raw chart data will be saved
DATA_FILE = os.path.join(PROJECT_DIR, "spx_data.json")

# Define the full path for the JSON file where the display-ready stats will be saved
DISPLAY_FILE = os.path.join(PROJECT_DIR, "display_data.json")


def get_spx_data():
    """
    Fetches SPX and VIX data from yfinance and calculates 1σ and 2σ bands.
    """
    # --- 1. Data Fetching ---
    
    # Set the date range: from 500 calendar days ago until today
    end_date = datetime.now()
    start_date = end_date - timedelta(days=500) 

    print("Fetching data from yfinance...")
    try:
        # Download S&P 500 (SPX) data
        spx_data = yf.download('^GSPC', start=start_date, end=end_date, progress=False, auto_adjust=True)
        # Download VIX (Volatility Index) data
        vix_data = yf.download('^VIX', start=start_date, end=end_date, progress=False, auto_adjust=True)
        
        if spx_data.empty or vix_data.empty:
            print("Error: No data fetched from yfinance.")
            return None
    except Exception as e:
        print(f"Error downloading data from yfinance: {e}")
        return None

    # --- 2. Data Preparation ---

    # Create a new DataFrame, using the SPX index (trading days) as the base
    df = pd.DataFrame()
    df['Date'] = spx_data.index
    df['SPX'] = spx_data['Close'].values
    
    # Align VIX data to SPX trading days. 
    # 'ffill' (forward fill) handles days when SPX traded but VIX might not have,
    # by carrying over the last known VIX value.
    df['VIX'] = vix_data['Close'].reindex(spx_data.index, method='ffill').values

    # --- 3. Sigma (Volatility) Calculation ---

    # Convert the VIX (annualized volatility) to a daily volatility (Daily Sigma).
    #
    # **LOGIC FOR 15.87:**
    # The VIX index represents expected *annualized* volatility as a percentage.
    # To get the expected *daily* volatility, we must de-annualize it.
    # We do this by dividing by the square root of the number of trading days
    # in a year, which is approximately 252.
    #
    # sqrt(252) ≈ 15.8745
    #
    # So, 15.87 is our constant for de-annualizing the VIX.
    # Example: If VIX = 15.87, Daily_Sigma = 1.0. This implies an expected 1% daily move.
    df['Daily_Sigma'] = df['VIX'] / 15.87

    # --- 4. Predictive Band Calculation ---

    # Calculate the 1-sigma (1 standard deviation) predicted price range
    # This range represents where the price is expected to close ~68% of the time.
    df['Predicted_1σ_Upper'] = df['SPX'] * (1 + df['Daily_Sigma'] / 100)
    df['Predicted_1σ_Lower'] = df['SPX'] * (1 - df['Daily_Sigma'] / 100)
    
    # Calculate the 2-sigma (2 standard deviations) predicted price range
    # This range represents where the price is expected to close ~95% of the time.
    df['Predicted_2σ_Upper'] = df['SPX'] * (1 + 2 * df['Daily_Sigma'] / 100)
    df['Predicted_2σ_Lower'] = df['SPX'] * (1 - 2 * df['Daily_Sigma'] / 100)

    # --- 5. Data Shifting for "Next Day" Analysis ---

    # We shift the predicted bands by one day.
    # This allows us to compare *today's* actual close price (SPX)
    # with *yesterday's* prediction for today.
    df['1σ_Upper'] = df['Predicted_1σ_Upper'].shift(1)
    df['1σ_Lower'] = df['Predicted_1σ_Lower'].shift(1)
    df['2σ_Upper'] = df['Predicted_2σ_Upper'].shift(1)
    df['2σ_Lower'] = df['Predicted_2σ_Lower'].shift(1)

    # --- 6. Performance Analysis (Model Backtest) ---

    # Check if today's SPX close fell *within* yesterday's 1σ predicted band
    df['Within_1σ'] = (df['SPX'] >= df['1σ_Lower']) & (df['SPX'] <= df['1σ_Upper'])
    
    # Check if today's SPX close fell *within* yesterday's 2σ predicted band
    df['Within_2σ'] = (df['SPX'] >= df['2σ_Lower']) & (df['SPX'] <= df['2σ_Upper'])
    
    # Flag days that were outside 1σ but still inside 2σ
    # The '~' operator means 'Not'
    df['Outside_1σ'] = ~df['Within_1σ'] & df['Within_2σ']
    
    # Flag days that were rare (outside the 2σ band)
    df['Outside_2σ'] = ~df['Within_2σ']
    
    # Return the completed dataframe.
    # We skip the first row (iloc[1:]) because it will have NaN (Not a Number)
    # values due to the .shift(1) operation.
    return df.iloc[1:].copy()

def get_display_data(df):
    """
    Processes the full dataframe to extract only the key metrics
    needed for the web app's display cards.
    
    This pre-calculation makes the Flask app faster, as it doesn't
    have to do any math, just read a simple JSON file.
    
    Args:
        df (pd.DataFrame): The full, processed dataframe from get_spx_data()

    Returns:
        dict: A dictionary of all values needed for the HTML template.
    """
    
    # Get the last row (latest trading day)
    latest = df.iloc[-1]
    # Get the second-to-last row (previous trading day)
    previous = df.iloc[-2]

    # --- Date Logic ---
    # Format dates for display (e.g., "Fri, Nov 14")
    latest_date_str = latest['Date'].strftime('%a, %b %d')
    previous_date_str = previous['Date'].strftime('%a, %b %d')

    # Calculate the date for the *next* prediction.
    # This handles weekends by skipping from Friday to Monday.
    next_day = latest['Date'] + pd.Timedelta(days=1)
    if next_day.weekday() == 5:  # 5 = Saturday
        next_day += pd.Timedelta(days=2)  # Skip to Monday
    elif next_day.weekday() == 6:  # 6 = Sunday
        next_day += pd.Timedelta(days=1)  # Skip to Monday
    
    prediction_date_str = next_day.strftime('%a, %b %d')

    # --- Result String Logic ---
    # Create the formatted HTML string for the "Result" card
    if latest['Outside_2σ']:
        latest_result_str = '<strong style="color:black;">Outside 2σ (Rare)</strong>'
    elif latest['Outside_1σ']:
        latest_result_str = '<strong style="color:red;">Outside 1σ</strong>'
    elif latest['Within_1σ']:
        latest_result_str = '<strong style="color:green;">Within 1σ</strong>'
    else:
        # Fallback, should not normally be hit
        latest_result_str = "N/A"

    # --- Compile all data into one dictionary ---
    # This dictionary will be saved as 'display_data.json'
    display_data = {
        # General Info
        "latest_date_str": latest_date_str,
        "previous_date_str": previous_date_str,
        "prediction_date_str": prediction_date_str,
        "latest_result_str": latest_result_str,
        
        # Latest Close Card
        "latest_spx": latest['SPX'],
        "latest_vix": latest['VIX'],
        "previous_spx": previous['SPX'],
        "previous_vix": previous['VIX'],
        
        # Range Test Card (Today's close vs Yesterday's prediction)
        "test_1s_lower": latest['1σ_Lower'],
        "test_1s_upper": latest['1σ_Upper'],
        "test_2s_lower": latest['2σ_Lower'],
        "test_2s_upper": latest['2σ_Upper'],
        "test_actual_close": latest['SPX'],
        
        # Prediction Card (Today's close used to predict Tomorrow)
        "pred_1s_lower": latest['Predicted_1σ_Lower'],
        "pred_1s_upper": latest['Predicted_1σ_Upper'],
        "pred_1s_range": latest['Predicted_1σ_Upper'] - latest['Predicted_1σ_Lower'],
        "pred_2s_lower": latest['Predicted_2σ_Lower'],
        "pred_2s_upper": latest['Predicted_2σ_Upper'],
        "pred_2s_range": latest['Predicted_2σ_Upper'] - latest['Predicted_2σ_Lower'],
    }
    return display_data


# --- Main Execution ---

# This block runs ONLY when the script is executed directly (e.g., `python fetch_data.py`)
# It will NOT run when this file is imported by another script.
if __name__ == "__main__":
    print("Starting daily data fetch and processing job...")
    
    # 1. Fetch and process all data
    dataframe = get_spx_data()
    
    if dataframe is not None and not dataframe.empty:
        # 2. Process data for the display cards
        display_data = get_display_data(dataframe)
        
        # 3. Save the raw dataframe (for the chart) as JSON
        # 'orient="split"' is an efficient format that pandas can read back easily
        # 'date_format="iso"' ensures dates are stored in a standard YYYY-MM-DDTHH:MM:SS format
        dataframe.to_json(DATA_FILE, orient="split", date_format="iso")
        
        # 4. Save the simple *display data* to its own JSON file
        # This makes the web app super simple and fast.
        with open(DISPLAY_FILE, 'w') as f:
            json.dump(display_data, f, indent=4) # indent=4 makes it human-readable
            
        print(f"Successfully saved dataframe to {DATA_FILE}")
        print(f"Successfully saved display data to {DISPLAY_FILE}")
    else:
        print("Failed to fetch or process data. No files were updated.")