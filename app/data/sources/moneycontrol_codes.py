"""Static NSE-symbol → Moneycontrol sc_id map for the NIFTY-50 universe.

MC's public autosuggest endpoint returns HTML (not JSON) for unauthenticated
clients, so resolving the sc_id at runtime is unreliable. These codes are
stable identifiers in MC's data model and rarely change.

If you add a ticker to `data/nifty50.csv`, add its sc_id here. Look it up by
visiting `https://www.moneycontrol.com/india/stockpricequote/<sector-slug>/
<company-slug>/<sc_id>` — the sc_id is the trailing path segment.
"""

NSE_TO_MC: dict[str, str] = {
    "RELIANCE": "RI",
    "TCS": "TCS",
    "HDFCBANK": "HDF01",
    "BHARTIARTL": "BA08",
    "ICICIBANK": "ICI02",
    "INFY": "IT",
    "SBIN": "SBI",
    "LT": "LT",
    "ITC": "ITC",
    "HINDUNILVR": "HU",
    "BAJFINANCE": "BAF",
    "KOTAKBANK": "KMB",
    "HCLTECH": "HCL02",
    "MARUTI": "MS24",
    "SUNPHARMA": "SPI",
    "TITAN": "TI01",
    "M&M": "MM",
    "AXISBANK": "AB16",
    "NTPC": "NTP",
    "ASIANPAINT": "AP31",
    "BAJAJFINSV": "BFS",
    "ONGC": "ONG",
    "ULTRACEMCO": "UTC",
    "WIPRO": "W",
    "ADANIENT": "AE13",
    "JSWSTEEL": "JSW01",
    "POWERGRID": "PG06",
    "TATASTEEL": "TIS",
    "TATAMOTORS": "TM03",
    "COALINDIA": "CI11",
    "NESTLEIND": "NI",
    "TECHM": "TM4",
    "HDFCLIFE": "HDF03",
    "ADANIPORTS": "MPS",
    "BAJAJ-AUTO": "BA10",
    "GRASIM": "GI01",
    "DRREDDY": "DRL",
    "INDUSINDBK": "IIB",
    "CIPLA": "C",
    "EICHERMOT": "EM",
    "SBILIFE": "SLI03",
    "HEROMOTOCO": "HHM",
    "APOLLOHOSP": "AH",
    "TATACONSUM": "TT",
    "BRITANNIA": "BIL",
    "DIVISLAB": "DL03",
    "LTIM": "LTI",
    "SHRIRAMFIN": "STF",
    "TRENT": "T",
    "BEL": "BE03",
}
