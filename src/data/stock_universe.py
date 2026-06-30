"""S&P 500 stock universe used for watchlist replacement scanning."""

# ~500 S&P 500 constituents. Scanned in order during replacement runs;
# the current watchlist members are automatically skipped.
STOCK_UNIVERSE = [
    # Mega-cap / current watchlist
    "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA", "BRK.B",
    "LLY", "AVGO", "JPM", "V", "UNH", "MA", "XOM", "COST", "HD",
    "PG", "JNJ", "ABBV", "CRM", "NFLX", "AMD", "BAC", "KO", "MRK",
    "PEP", "TMO", "ORCL", "ACN", "LIN", "WMT", "CSCO", "MCD", "ABT",
    "DIS", "ADBE", "DHR", "WFC", "INTC", "QCOM", "INTU", "TXN", "PM",
    "NOW", "IBM", "GE", "CAT", "AMAT", "GS",
    # Technology
    "LRCX", "MU", "KLAC", "SNPS", "CDNS", "ANSS", "FTNT", "PANW",
    "CRWD", "ZS", "OKTA", "DDOG", "SNOW", "PLTR", "UBER", "LYFT",
    "TTD", "SHOP", "SQ", "PYPL", "TWLO", "ZM", "DOCU", "WORK",
    "NET", "CFLT", "MDB", "ESTC", "GTLB", "HUBS", "BILL", "COUP",
    "MSCI", "SPGI", "ICE", "CME", "CBOE", "MCO", "FIS", "FISV",
    "GPN", "WEX", "JKHY", "BR", "SSNC",
    # Healthcare
    "BMY", "AMGN", "GILD", "BIIB", "REGN", "VRTX", "ILMN", "IQV",
    "ZBH", "SYK", "BSX", "MDT", "BDX", "EW", "ISRG", "ALGN",
    "DXCM", "IDXX", "PODD", "NVAX", "MRNA", "BNTX", "PFE", "CVS",
    "CI", "HUM", "ELV", "MOH", "CNC", "HCA", "THC", "UHS", "LPLA",
    "MCK", "CAH", "ABC", "PRGO", "ENDP", "PKI", "A", "RMD",
    # Financials
    "MS", "C", "USB", "PNC", "TFC", "COF", "AXP", "DFS", "SYF",
    "ALLY", "CMA", "FITB", "HBAN", "RF", "KEY", "CFG", "MTB",
    "ZION", "BOKF", "FHN", "SNV", "PBCT", "TCF", "WAL", "EWBC",
    "BK", "STT", "NTRS", "IVZ", "BEN", "AMG", "TROW", "VRTS",
    "PFG", "LNC", "AFL", "MET", "PRU", "AIG", "ALL", "TRV",
    "CB", "HIG", "WR", "MKL", "RLI", "CINF",
    # Consumer Discretionary
    "NKE", "SBUX", "LOW", "TJX", "ROST", "BURL", "GPS", "ANF",
    "AEO", "URBN", "LULU", "RH", "WSM", "BBY", "BBWI", "ETSY",
    "EBAY", "AMZN", "W", "CHWY", "CVNA", "KMX", "AZO", "ORLY",
    "AAP", "GPC", "GM", "F", "STLA", "TM", "HMC", "RIVN",
    "LCID", "NKLA", "BLNK", "MAR", "HLT", "H", "WH", "IHG",
    "CCL", "RCL", "NCLH", "LVS", "MGM", "WYNN", "CZR",
    # Consumer Staples
    "MO", "PM", "BTI", "MDLZ", "HSY", "GIS", "K", "CPB", "SJM",
    "CAG", "MKC", "HRL", "TSN", "KHC", "POST", "LANC", "BGS",
    "CLX", "CHD", "CL", "EL", "PRGO", "AVP", "COTY", "REV",
    "SFM", "KR", "ACI", "SYY", "US", "PFGC", "USFD",
    # Energy
    "CVX", "COP", "EOG", "SLB", "HAL", "BKR", "OXY", "DVN",
    "FANG", "MPC", "VLO", "PSX", "PBF", "DK", "HFC", "WMB",
    "KMI", "OKE", "EPD", "ET", "MPLX", "PAA", "TRGP", "AM",
    "AR", "EQT", "RRC", "CNX", "SWN", "COG",
    # Industrials
    "HON", "MMM", "RTX", "LMT", "NOC", "GD", "BA", "LHX",
    "TDG", "HEI", "HEICO", "TXT", "DRS", "KTOS", "AVAV",
    "UPS", "FDX", "CHRW", "EXPD", "XPO", "ODFL", "SAIA",
    "JBHT", "WERN", "KNX", "HTZ", "AVIS", "URI", "AHCO",
    "PWR", "PRIM", "MTZ", "EME", "MYR", "J", "EXPO",
    "PH", "EMR", "ITW", "DOV", "AME", "GWW", "MSM",
    "ROP", "XYL", "MIDD", "WTS", "CFX", "TRMK",
    # Materials
    "FCX", "NEM", "GOLD", "AEM", "KGC", "AG", "HL", "CDE",
    "AA", "CENX", "ATI", "MP", "ENPH", "SEDG",
    "DD", "DOW", "LYB", "WLK", "OLN", "CC", "RPM",
    "SHW", "PPG", "AXTA", "IOSP", "NPK", "ESE",
    "NUE", "STLD", "CLF", "X", "CMC", "RS",
    # Utilities
    "NEE", "DUK", "SO", "D", "AEP", "EXC", "SRE", "PCG",
    "PEG", "EIX", "XEL", "WEC", "DTE", "ETR", "FE", "CNP",
    "AES", "NI", "OGE", "EVRG", "POR", "AVA", "NWE",
    "AWK", "CWT", "MSEX", "YORW",
    # Real Estate
    "AMT", "PLD", "CCI", "EQIX", "PSA", "EQR", "AVB", "ESS",
    "MAA", "UDR", "CPT", "NNN", "O", "WPC", "SPG", "MAC",
    "TCO", "SLG", "BXP", "KIM", "REG", "FRT", "ROIC",
    "DRE", "FR", "EGP", "REXR", "TRNO", "COLD",
    # Communication Services
    "T", "VZ", "TMUS", "CHTR", "CMCSA", "DISH", "LUMN",
    "OMC", "IPG", "WPP", "PUBM", "MGNI", "TTD", "APPS",
    "EA", "TTWO", "ATVI", "RBLX", "U", "MTCH", "BMBL",
    "SNAP", "PINS", "TWTR", "SPOT", "YELP", "IAC",
]
