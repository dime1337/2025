# Currency Exchange Dashboard
import requests
from bs4 import BeautifulSoup
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import streamlit as st
from datetime import datetime, timedelta
import io
import logging
from requests.adapters import HTTPAdapter, Retry
import json
from typing import List
import time
import numpy as np

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ===== Streamlit page config =====
st.set_page_config(
    page_title="Currency Exchange Dashboard", 
    layout="wide",
    initial_sidebar_state="expanded"
)
st.title("Currency Exchange Rate Dashboard")
st.markdown(
    """
    Track current and historical currency exchange rates.
    Supports CSV download, interactive charts, and multiple base currencies.
    """
)

# ===== Sidebar User Inputs =====
st.sidebar.header("Settings")

base_currency = st.sidebar.selectbox(
    "Select base currency:",
    ["USD", "EUR", "GBP", "JPY", "TRY", "INR", "CNY", "CAD"],
    index=0
)

days_range = st.sidebar.slider(
    "Historical data range (days):", 
    min_value=1, 
    max_value=30, 
    value=7
)

# Add refresh button
if st.sidebar.button("🔄 Refresh Data"):
    st.cache_data.clear()
    st.rerun()

# ===== Utility Functions =====

def requests_get_with_retry(url: str, retries=3, backoff=0.3, timeout=10) -> requests.Response:
    """
    Performs an HTTP GET request with retries and backoff to handle transient errors.
    """
    session = requests.Session()
    retry_strategy = Retry(
        total=retries,
        backoff_factor=backoff,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["HEAD", "GET", "OPTIONS"],
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    
    try:
        response = session.get(url, timeout=timeout, headers=headers)
        response.raise_for_status()
        return response
    except requests.RequestException as e:
        logger.error(f"Request failed for {url}: {e}")
        raise

def format_date(date_obj: datetime) -> str:
    """
    Format datetime object to YYYY-MM-DD string.
    """
    return date_obj.strftime("%Y-%m-%d")

def parse_exchange_table(soup: BeautifulSoup) -> pd.DataFrame:
    """
    Parse live exchange rate table from BeautifulSoup object into a DataFrame.
    """
    try:
        table = soup.find("table", class_="tablesorter ratesTable")
        if not table:
            logger.warning("Exchange rate table not found")
            return pd.DataFrame()
        
        rows = table.find_all("tr")[1:]  # skip header
        data = []
        
        for row in rows:
            cols = row.find_all("td")
            if len(cols) >= 2:
                currency = cols[0].text.strip()
                try:
                    rate = float(cols[1].text.strip().replace(',', ''))
                    data.append({"Currency": currency, "Rate": rate})
                except ValueError as e:
                    logger.warning(f"Could not parse rate for {currency}: {e}")
                    continue
        
        return pd.DataFrame(data)
    except Exception as e:
        logger.error(f"Error parsing exchange table: {e}")
        return pd.DataFrame()

def safe_json_load(res: requests.Response) -> dict:
    """
    Safely parse JSON from a requests.Response object.
    """
    try:
        return res.json()
    except json.JSONDecodeError as e:
        logger.error(f"Failed to decode JSON response: {e}")
        return {}

def generate_date_list(days: int) -> List[str]:
    """
    Generate list of past N dates in YYYY-MM-DD format.
    """
    return [
        (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d") 
        for i in range(days)
    ][::-1]

# ===== Scraper Functions =====

@st.cache_data(ttl=300, show_spinner=True)  # Cache for 5 minutes
def scrape_live_rates(base: str) -> pd.DataFrame:
    """
    Scrapes live exchange rates from x-rates.com for a given base currency.
    Returns a DataFrame with Currency and Rate.
    """
    url = f"https://www.x-rates.com/table/?from={base}&amount=1"
    
    try:
        with st.spinner(f"Fetching live rates for {base}..."):
            response = requests_get_with_retry(url)
            soup = BeautifulSoup(response.text, "html.parser")
            df = parse_exchange_table(soup)
            
            if df.empty:
                st.warning("No live exchange rate data found.")
            else:
                logger.info(f"Successfully fetched {len(df)} live rates for {base}")
            
            return df
    except Exception as e:
        st.error(f"Error fetching live exchange data: {e}")
        logger.error(f"Failed to scrape live rates for {base}: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=600, show_spinner=True)  # Cache for 10 minutes
def fetch_historical_data(base: str, days: int) -> pd.DataFrame:
    """
    Fetches historical exchange rate data using exchangerate.host API
    for the last 'days' days for the selected base currency.
    """
    all_data = []
    dates = generate_date_list(days)
    
    target_currencies = ["EUR", "USD", "JPY", "GBP", "TRY", "CAD", "INR", "CNY"]
    if base in target_currencies:
        target_currencies.remove(base)
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for i, date in enumerate(dates):
        status_text.text(f"Fetching data for {date}...")
        progress_bar.progress((i + 1) / len(dates))
        
        url = f"https://api.exchangerate.host/{date}?base={base}&symbols={','.join(target_currencies)}"
        
        try:
            res = requests_get_with_retry(url)
            json_data = safe_json_load(res)
            rates = json_data.get("rates", {})
            
            for curr, val in rates.items():
                all_data.append({"Date": date, "Currency": curr, "Rate": val})
            
            # Add small delay to avoid rate limiting
            time.sleep(0.1)
            
        except Exception as e:
            st.warning(f"Failed to fetch data for {date}: {e}")
            logger.warning(f"Failed to fetch historical data for {date}: {e}")
            continue
    
    progress_bar.empty()
    status_text.empty()
    
    df_hist = pd.DataFrame(all_data)
    if df_hist.empty:
        st.info("No historical data could be retrieved.")
    else:
        logger.info(f"Successfully fetched {len(df_hist)} historical records for {base}")
    
    return df_hist

# ===== Main App Logic =====

# Live rates
st.subheader(f"Live Exchange Rates for 1 {base_currency}")
live_df = scrape_live_rates(base_currency)

if live_df.empty:
    st.warning(
        "No live data available. Please check your internet connection or try another base currency."
    )
else:
    # Format the dataframe for better display
    display_df = live_df.copy()
    display_df['Rate'] = display_df['Rate'].round(4)
    st.dataframe(display_df, use_container_width=True)

# Historical rates
st.subheader(f"Historical Rates (Last {days_range} Days) for {base_currency}")
hist_df = fetch_historical_data(base_currency, days_range)

if hist_df.empty:
    st.warning("Could not load historical data.")
else:
    # Format the dataframe for better display
    display_hist_df = hist_df.copy()
    display_hist_df['Rate'] = display_hist_df['Rate'].round(4)
    st.dataframe(display_hist_df, use_container_width=True)

# ===== Visualizations =====

# Bar Chart: Top 10 Live Rates
if not live_df.empty:
    st.subheader(f"Top 10 Exchange Rates for 1 {base_currency}")
    top10 = live_df.sort_values(by="Rate", ascending=False).head(10)
    
    fig1, ax1 = plt.subplots(figsize=(12, 6))
    bars = ax1.bar(top10["Currency"], top10["Rate"], color="skyblue", alpha=0.7)
    ax1.set_ylabel("Rate")
    ax1.set_xlabel("Currency")
    ax1.set_title(f"Top 10 Exchange Rates for {base_currency}")
    ax1.tick_params(axis="x", rotation=45)
    
    # Add value labels on bars
    for bar in bars:
        height = bar.get_height()
        ax1.text(bar.get_x() + bar.get_width()/2., height,
                f'{height:.4f}', ha='center', va='bottom')
    
    plt.tight_layout()
    st.pyplot(fig1)

# Line Chart: Historical Trend
if not hist_df.empty:
    st.subheader(f"Exchange Rate Trends (Last {days_range} Days)")
    
    unique_currencies = sorted(hist_df["Currency"].unique())
    selected_currencies = st.multiselect(
        "Select currencies to compare:", 
        unique_currencies, 
        default=unique_currencies[:3] if len(unique_currencies) >= 3 else unique_currencies
    )
    
    if selected_currencies:
        fig2, ax2 = plt.subplots(figsize=(14, 7))
        sns.set(style="whitegrid")
        
        colors = plt.cm.Set3(np.linspace(0, 1, len(selected_currencies)))
        
        for i, currency in enumerate(selected_currencies):
            subset = hist_df[hist_df["Currency"] == currency]
            if not subset.empty:
                ax2.plot(subset["Date"], subset["Rate"], 
                        label=currency, color=colors[i], linewidth=2, marker='o')
        
        ax2.set_title(f"Exchange Rate Trends vs {base_currency}")
        ax2.set_ylabel("Rate")
        ax2.set_xlabel("Date")
        ax2.tick_params(axis="x", rotation=45)
        ax2.legend()
        plt.tight_layout()
        st.pyplot(fig2)

# ===== CSV Export =====
def convert_df_to_csv(df: pd.DataFrame) -> bytes:
    """
    Converts DataFrame to CSV bytes for download.
    """
    buffer = io.StringIO()
    df.to_csv(buffer, index=False)
    return buffer.getvalue().encode("utf-8")

if not hist_df.empty:
    col1, col2 = st.columns(2)
    
    with col1:
        csv_bytes = convert_df_to_csv(hist_df)
        st.download_button(
            label="⬇ Download Historical Data as CSV",
            data=csv_bytes,
            file_name=f"{base_currency}_historical_rates_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv",
        )
    
    with col2:
        if not live_df.empty:
            live_csv_bytes = convert_df_to_csv(live_df)
            st.download_button(
                label="⬇ Download Live Data as CSV",
                data=live_csv_bytes,
                file_name=f"{base_currency}_live_rates_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv",
            )

# ===== Status Messages =====
st.markdown("---")
col1, col2 = st.columns(2)

with col1:
    if live_df.empty:
        st.info("⚠️ Waiting for valid live data or check your internet connection...")
    else:
        st.success(f"✅ Live data successfully loaded! ({len(live_df)} currencies)")

with col2:
    if hist_df.empty:
        st.info("⚠️ Waiting for historical data or try adjusting the date range...")
    else:
        st.success(f"✅ Historical data successfully loaded! ({len(hist_df)} records)")

# Add footer
st.markdown("---")
st.markdown(
    f"""
    <div style='text-align: center; color: #666; font-size: 0.8em;'>
        Data sources: x-rates.com (live rates) and exchangerate.host (historical data)<br>
        Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    </div>
    """,
    unsafe_allow_html=True
)