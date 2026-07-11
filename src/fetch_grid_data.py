"""
fetch_grid_data.py
~~~~~~~~~~~~~~~~~~
Pulls historical hourly electricity consumption and wind power production
for Finland from the Fingrid Open Data API (data.fingrid.fi) for the full
year of 2023.

If no API key is configured in config.yaml, the script falls back to generating
realistic mock hourly data for Finland (2023) so that the pipeline remains
fully executable and reproducible in environments without API access.

API details:
  - Base URL: https://api.fingrid.fi/v1/variable/{variable_id}/events/json
  - Dataset ID 124: Electricity consumption in Finland (MW/h)
  - Dataset ID 75: Wind power generation - 15 min data (downsampled here to hourly)
  - x-api-key: HTTP header authentication
  - Rate limit: 1 request per 2 seconds, 10,000 requests per day.
"""

import os
import time
import urllib.request
import urllib.parse
import urllib.error
import json
import yaml
import pandas as pd
import numpy as np

# Fingrid API configuration
API_BASE_URL = "https://api.fingrid.fi/v1/variable"
DATASETS = {
    124: "consumption",
    75: "wind_production"
}

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config.yaml")
OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "raw", "grid_data.csv")


def load_api_key() -> str:
    """Load fingrid_api_key from config.yaml."""
    if not os.path.exists(CONFIG_PATH):
        return ""
    with open(CONFIG_PATH, "r") as fh:
        try:
            cfg = yaml.safe_load(fh)
            return cfg.get("fingrid_api_key", "").strip()
        except Exception:
            return ""


def get_mock_grid_data() -> pd.DataFrame:
    """
    Generate high-quality, realistic mock grid data for Finland for the full year of 2023.
    This acts as a fallback if the Fingrid API key is missing or invalid.
    """
    print("Generating realistic mock grid data for Finland (2023) ...")
    
    # 8760 hours in 2023
    timestamps = pd.date_range(
        start="2023-01-01 00:00:00+00:00",
        end="2023-12-31 23:00:00+00:00",
        freq="1h"
    )
    n_hours = len(timestamps)
    
    # Seed for reproducibility
    rng = np.random.default_rng(42)
    
    # Hour of day (0-23), Day of year (0-364)
    hour = timestamps.hour.values
    day_of_year = timestamps.dayofyear.values
    
    # 1. Simulate Consumption (ID 124)
    # Seasonal base: peaks in winter (Jan/Dec) around 11,000 MW, lows in summer (July) around 7,000 MW
    seasonal_factor = 9000 + 2000 * np.cos(2 * np.pi * (day_of_year - 15) / 365)
    # Diurnal cycle: peak during morning/evening, lower at night (amplitude ~1500 MW)
    diurnal_factor = 1000 * np.sin(2 * np.pi * (hour - 6) / 24) - 500 * np.cos(4 * np.pi * (hour - 18) / 24)
    # Weekend effect: lower consumption on Saturdays (index 5) and Sundays (index 6)
    weekday = timestamps.weekday.values
    weekend_factor = np.where(weekday >= 5, 0.90, 1.0)
    
    consumption_noise = rng.normal(0, 300, size=n_hours)
    consumption = ((seasonal_factor + diurnal_factor) * weekend_factor + consumption_noise).round(4)
    # Clamp to realistic bounds
    consumption = np.clip(consumption, 5000, 15000)

    # 2. Simulate Wind Production (ID 75)
    # Wind production is highly variable and correlates loosely with weather cycles
    # We use a mean-reverting random walk with a seasonal baseline
    wind_base = 1800 + 400 * np.cos(2 * np.pi * (day_of_year - 45) / 365)
    wind_noise = rng.normal(0, 450, size=n_hours)
    
    # Generate auto-correlated wind production
    wind = np.zeros(n_hours)
    wind[0] = wind_base[0] + wind_noise[0]
    for t in range(1, n_hours):
        # Mean reverting random walk: 92% weight on previous step, 8% pull to baseline, plus noise
        wind[t] = 0.92 * wind[t-1] + 0.08 * wind_base[t] + wind_noise[t]
        
    wind = wind.round(4)
    # Clamp wind production between 100 MW and 5500 MW (max capacity)
    wind = np.clip(wind, 100, 5500)
    
    df_cons = pd.DataFrame({
        "dataset_id": 124,
        "country": "FI",
        "recorded_at": timestamps,
        "value": consumption,
        "metric": "consumption"
    })
    
    df_wind = pd.DataFrame({
        "dataset_id": 75,
        "country": "FI",
        "recorded_at": timestamps,
        "value": wind,
        "metric": "wind_production"
    })
    
    df_grid = pd.concat([df_cons, df_wind], ignore_index=True)
    return df_grid


def fetch_dataset_chunk(dataset_id: int, api_key: str, start_time: str, end_time: str) -> list:
    """Fetch data for a specific dataset ID and time chunk with retry logic and rate limit compliance."""
    params = {
        "start_time": start_time,
        "end_time": end_time
    }
    query_string = urllib.parse.urlencode(params)
    url = f"{API_BASE_URL}/{dataset_id}/events/json?{query_string}"
    
    req = urllib.request.Request(url)
    req.add_header("Accept", "application/json")
    req.add_header("x-api-key", api_key)
    
    max_retries = 3
    backoff = 2.0
    
    for attempt in range(max_retries):
        # Fingrid rate limit: max 1 request per 2 seconds
        time.sleep(2.0)
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                if response.status == 200:
                    return json.loads(response.read().decode("utf-8"))
                else:
                    print(f"  Warning: Received status code {response.status}. Retrying...")
        except urllib.error.HTTPError as e:
            if e.code == 429:
                print(f"  [429 Too Many Requests] Rate limit hit. Backing off for {backoff}s...")
                time.sleep(backoff)
                backoff *= 2.0
            elif e.code in (401, 403):
                raise PermissionError("Fingrid API key is unauthorized or invalid (401/403).")
            else:
                print(f"  HTTP error: {e.code}. Retrying in {backoff}s...")
                time.sleep(backoff)
                backoff *= 2.0
        except Exception as e:
            print(f"  Network error: {e}. Retrying in {backoff}s...")
            time.sleep(backoff)
            backoff *= 2.0
            
    print(f"  Error: Failed to fetch dataset {dataset_id} for range {start_time} to {end_time} after {max_retries} attempts.")
    return []


def fetch_fingrid_data(api_key: str) -> pd.DataFrame:
    """Fetch full year 2023 grid data by dividing it into monthly chunks."""
    print("Connecting to Fingrid Open Data API ...")
    
    # 2023 monthly boundaries
    months = pd.date_range(start="2023-01-01", end="2024-01-01", freq="MS")
    
    all_chunks = []
    
    for dataset_id, metric in DATASETS.items():
        print(f"Fetching dataset {dataset_id} ({metric}) chunk-by-chunk ...")
        for i in range(len(months) - 1):
            start_str = months[i].strftime("%Y-%m-%dT%H:%M:%SZ")
            end_str = (months[i+1] - pd.Timedelta(seconds=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
            
            print(f"  -> Pulling chunk: {months[i].strftime('%B %Y')} ...")
            chunk_data = fetch_dataset_chunk(dataset_id, api_key, start_str, end_str)
            
            if not chunk_data:
                # If we encounter an authentication error, raise it immediately to trigger fallback
                raise RuntimeError("API fetch returned empty data or auth failed.")
                
            df_chunk = pd.DataFrame(chunk_data)
            df_chunk["dataset_id"] = dataset_id
            df_chunk["metric"] = metric
            df_chunk["country"] = "FI"
            all_chunks.append(df_chunk)
            
    df_raw = pd.concat(all_chunks, ignore_index=True)
    
    # Rename columns and parse timestamps
    df_raw["recorded_at"] = pd.to_datetime(df_raw["start_time"])
    df_raw["value"] = pd.to_numeric(df_raw["value"])
    
    # Downsample to consistent hourly resolution
    print("Downsampling 15-minute readings to hourly average (mean) ...")
    df_raw = df_raw.set_index("recorded_at")
    
    # Group by dataset_id and resample to 1-hour intervals
    df_hourly = df_raw.groupby(["dataset_id", "metric", "country"]).resample("1h")["value"].mean().reset_index()
    
    # Clean up column ordering
    df_hourly = df_hourly[["dataset_id", "country", "recorded_at", "value", "metric"]]
    return df_hourly


def main():
    api_key = load_api_key()
    
    # Check if api_key is configured/valid placeholder
    if not api_key or api_key == "YOUR_ACTUAL_API_KEY":
        print("Notice: No valid 'fingrid_api_key' configured in config.yaml.")
        df_grid = get_mock_grid_data()
    else:
        try:
            df_grid = fetch_fingrid_data(api_key)
            print("✓ Successfully fetched actual data from Fingrid API.")
        except Exception as exc:
            print(f"Fingrid API request failed: {exc}")
            print("Falling back to generating realistic mock grid data...")
            df_grid = get_mock_grid_data()
            
    # Save to CSV
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    df_grid.to_csv(OUTPUT_PATH, index=False)
    print(f"✓ Wrote {len(df_grid):,} grid data rows to: {os.path.abspath(OUTPUT_PATH)}")


if __name__ == "__main__":
    main()
