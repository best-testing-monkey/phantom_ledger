# E4: Data Layer

Fetch, cache, and serve price and reference rate data.

## Stories

- [ ] **E4-S01** `MVP` — Implement HistoricalProvider: fetch OHLCV from yfinance, cache as Parquet files keyed by ticker, serve from cache on subsequent calls
- [ ] **E4-S02** `MVP` — Implement Parquet cache management: check freshness (last date in cache vs today), append new bars on fetch, handle splits/adjustments by re-downloading
- [ ] **E4-S03** `MVP` — CLI: `phantom data fetch --ticker AAPL --start 2024-01-01` — populate local cache
- [ ] **E4-S04** `MVP` — Implement DataProvider protocol and make HistoricalProvider conform to it
- [ ] **E4-S05** `P2` — Implement dividend data fetching: extract ex-dates and amounts from yfinance, cache alongside price data
- [ ] **E4-S06** `P2` — Implement reference rate fetcher: SOFR from NY Fed API, ESTR from ECB SDMX API, cache as CSV/Parquet
- [ ] **E4-S07** `P2` — CLI: `phantom data fetch-rates --rate SOFR --start 2024-01-01`
- [ ] **E4-S08** `P2` — Implement LiveProvider: get_current_price() via yfinance real-time, get_bid_ask() via Alpaca free API
- [ ] **E4-S09** `P2` — Implement data staleness detection: warn if cache is older than N days when entering paper-trade mode
