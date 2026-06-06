# Phantom Ledger Library Usage Guide

This guide shows how to use the Phantom Ledger Python library to build automated trading and backtesting systems.

## 1. Installation

Install from the repository:

```bash
uv add phantom-ledger
```

Or in development mode:

```bash
cd phantom_ledger
uv sync
```

## 2. Creating a Phantom Instance

The `Phantom` class is your entry point to the library. It manages database connections and provides access to all sub-APIs.

```python
from phantom import Phantom

# Create instance with local SQLite database
ph = Phantom(data_dir="./data")

# Or use in-memory database for testing
ph = Phantom(data_dir="./data", in_memory=True)
```

The instance provides access to these sub-APIs:
- `ph.accounts` — Account management
- `ph.brokers` — Broker profiles
- `ph.orders` — Order placement and management
- `ph.positions` — Position tracking and modification
- `ph.notes` — Trade notes
- `ph.data` — Market data fetching
- `ph.reports` — Performance metrics and reporting
- `ph.runner` — Backtesting and paper trading

## 3. Loading a Broker Profile

Broker profiles define cost structures, instruments, and market conditions for a broker.

```python
from phantom import Phantom, BrokerProfile

ph = Phantom(data_dir="./data")

# Load a bundled broker profile (DEGIRO, IBKR, XTB)
degiro = ph.brokers.get("DEGIRO")

# Or load from a custom JSON file
custom = ph.brokers.load_from_file("path/to/custom_broker.json")

# List all loaded profiles
profiles = ph.brokers.list()
for p in profiles:
    print(f"{p.name}: {', '.join(p.supported_instruments)}")
```

## 4. Creating an Account

Accounts represent trading accounts with initial capital and a broker.

```python
from phantom import Phantom

ph = Phantom(data_dir="./data")

# Create a manual trading account
account = ph.accounts.create(
    name="My Trading Account",
    account_type="manual",
    broker="DEGIRO",
    capital=10000.0,
    currency="EUR"
)

print(f"Account ID: {account.id}")
print(f"Initial Capital: {account.initial_capital}")

# Create a pattern-tagged account (for strategy backtesting)
pattern_account = ph.accounts.create(
    name="RSI Strategy Account",
    account_type="pattern",
    broker="DEGIRO",
    capital=50000.0,
    currency="EUR",
    pattern_tag="rsi_mean_reversion"
)

# Create an algorithm account
algo_account = ph.accounts.create(
    name="ML Model v1",
    account_type="algorithm",
    broker="DEGIRO",
    capital=100000.0,
    currency="EUR",
    algorithm_id="gradient_boosting",
    algorithm_version="1.0.0"
)

# List all accounts
accounts = ph.accounts.list()
for acc in accounts:
    print(f"{acc.name} ({acc.account_type}): {acc.cash} {acc.base_currency}")
```

CLI equivalent:

```bash
phantom account create \
  --name "My Trading Account" \
  --type manual \
  --broker DEGIRO \
  --capital 10000.0 \
  --currency EUR

phantom account list
```

## 5. Placing Orders

Orders are pending trades that get executed when price conditions are met. Support market, limit, stop, stop-limit, and trailing stop orders.

```python
from phantom import Phantom, Order

ph = Phantom(data_dir="./data")

account = ph.accounts.get("My Trading Account")

# Place a market order (executed at next available price)
order = ph.orders.place(
    account_id=account.id,
    order=Order(
        ticker="AAPL",
        direction="long",
        order_type="market",
        quantity=10.0,
        instrument_type="stock"
    )
)

print(f"Order {order.id} placed: {order.status}")

# Place a limit order
limit_order = ph.orders.place(
    account_id=account.id,
    order=Order(
        ticker="MSFT",
        direction="long",
        order_type="limit",
        quantity=5.0,
        limit_price=300.0,
        instrument_type="stock"
    )
)

# Place a stop order (trigger on price breach)
stop_order = ph.orders.place(
    account_id=account.id,
    order=Order(
        ticker="GOOGL",
        direction="short",
        order_type="stop",
        quantity=3.0,
        stop_price=140.0,
        instrument_type="cfd"
    )
)

# Place a trailing stop order (moves with price, triggers on reversal)
trailing_order = ph.orders.place(
    account_id=account.id,
    order=Order(
        ticker="TSLA",
        direction="long",
        order_type="market",
        quantity=2.0,
        trailing_amount=5.0,  # or trailing_pct=0.02 for 2%
        instrument_type="stock"
    )
)

# List orders for an account
pending = ph.orders.list(account_name="My Trading Account", status="pending")
for o in pending:
    print(f"{o.ticker} {o.direction} {o.quantity} @ {o.limit_price or 'market'}")

# Cancel a pending order
ph.orders.cancel(order.id)
```

CLI equivalent:

```bash
phantom order place \
  --account "My Trading Account" \
  --ticker AAPL \
  --direction long \
  --type market \
  --quantity 10.0

phantom order list --account "My Trading Account"
phantom order cancel <order-id>
```

## 6. Viewing Positions and P&L

Positions are filled orders that are currently open or have been closed.

```python
from phantom import Phantom

ph = Phantom(data_dir="./data")

# List all open positions
open_positions = ph.positions.list(account_name="My Trading Account", status="open")
for pos in open_positions:
    pnl = (pos.current_price - pos.entry_price) * pos.quantity
    print(f"{pos.ticker}: {pos.quantity} @ {pos.entry_price:.2f}, P&L: {pnl:.2f}")

# Get a specific position
position = ph.positions.get("position-ulid-here")

print(f"Position: {position.ticker}")
print(f"Entry: {position.entry_price:.4f} ({position.entry_datetime})")
print(f"Quantity: {position.quantity}")
print(f"Take Profit: {position.take_profit}")
print(f"Stop Loss: {position.stop_loss}")
print(f"Commission: {position.commission_entry + position.commission_exit:.4f}")
print(f"Spread Cost: {position.spread_cost:.4f}")
print(f"Status: {position.status}")

# Close a position at a specific price
closed = ph.positions.close(
    position_id=position.id,
    close_reason="target_hit",
    exit_price=105.50
)

print(f"Closed for {closed.realized_pnl:.2f} P&L")

# Modify take-profit and stop-loss on an open position
modified = ph.positions.modify(
    position_id=position.id,
    take_profit=110.0,
    stop_loss=98.0
)
```

CLI equivalent:

```bash
phantom position list --account "My Trading Account" --status open
phantom position show <position-id>
phantom position close <position-id> --price 105.50 --reason target_hit
phantom position modify <position-id> --tp 110.0 --sl 98.0
```

## 7. Running a Backtest

Backtests replay historical price data to evaluate strategy performance.

```python
from phantom import Phantom
from datetime import datetime

ph = Phantom(data_dir="./data")

# Run a backtest
result = ph.runner.backtest(
    account_id="account-id-here",
    tickers=["AAPL", "MSFT", "GOOGL"],
    start="2023-01-01",
    end="2024-01-01"
)

print(f"Total Return: {result.equity_metrics.total_return_pct:.2f}%")
print(f"CAGR: {result.equity_metrics.cagr_pct:.2f}%")
print(f"Max Drawdown: {result.equity_metrics.max_drawdown_pct:.2f}%")
print(f"Sharpe Ratio: {result.equity_metrics.sharpe_ratio:.2f}")
print(f"Trade Count: {result.trade_metrics.trade_count}")
print(f"Win Rate: {result.trade_metrics.win_rate_pct:.1f}%")
```

Note: Backtests require historical price data. Fetch it first:

```bash
phantom data fetch --ticker AAPL --start 2023-01-01 --end 2024-01-01
```

## 8. Reading Metrics

Generate performance reports for any account.

```python
from phantom import Phantom

ph = Phantom(data_dir="./data")

# Get account metrics
account = ph.accounts.get("My Trading Account")
positions = ph.positions.list(account_name=account.name)

# Get margin summary (for CFD accounts)
margin = ph.accounts.get_margin_summary("My Trading Account")
print(f"Margin Level: {margin.margin_level:.1f}%")
print(f"Free Margin: {margin.free_margin:.2f}")

# Get aggregate equity for a parent account with children
try:
    equity_series = ph.accounts.get_aggregate_equity("Parent Account")
    print(f"Combined equity: {equity_series[-1]:.2f}")
except ImportError:
    print("Install pandas for equity curves: uv add pandas")
```

CLI equivalent:

```bash
phantom report show --account "My Trading Account"
phantom report show --account "My Trading Account" --aggregate
phantom report show --account "My Trading Account" --compare-brokers "DEGIRO,IBKR"
```

## 9. Using CostEngine Standalone

The `CostEngine` calculates trading costs based on a broker profile. It can be used independently.

```python
from phantom import CostEngine, BrokerProfile
import json

# Load a broker profile
with open("broker_config.json") as f:
    profile_data = json.load(f)

profile = BrokerProfile(**profile_data)

# Create a cost engine
cost_engine = CostEngine(profile)

# Calculate entry costs
entry_costs = cost_engine.entry_costs(
    price=100.0,
    quantity=10.0,
    ticker="AAPL",
    instrument_type="stock",
    atr=2.5  # Average True Range, optional
)

print(f"Commission: {entry_costs.commission:.4f}")
print(f"Spread: {entry_costs.spread:.4f}")
print(f"Slippage: {entry_costs.slippage:.4f}")
print(f"Total Cost: {entry_costs.total:.4f}")

# Calculate exit costs
exit_costs = cost_engine.exit_costs(
    price=105.0,
    quantity=10.0,
    ticker="AAPL",
    instrument_type="stock"
)

# Calculate overnight financing (for CFD positions)
overnight = cost_engine.overnight_cost(
    notional=1000.0,  # price * quantity
    direction="long",
    reference_rate=0.045
)

# Calculate dividend adjustment
dividend = cost_engine.dividend_adjustment(
    gross=50.0,  # dividend per share * quantity
    direction="long",
    instrument_type="stock",
    country="US"
)
```

## 10. Writing a Strategy (Minimal Example)

Integrate custom trading logic with Phantom by placing orders based on market conditions.

```python
from phantom import Phantom, Order
from datetime import datetime, timedelta

def rsi_strategy(ph, account_name, tickers, lookback=14, oversold=30, overbought=70):
    """Simple RSI mean-reversion strategy."""
    
    ph = Phantom(data_dir="./data")
    account = ph.accounts.get(account_name)
    
    for ticker in tickers:
        # Fetch price data (assuming already cached)
        # In production, integrate with real-time data provider
        
        # Calculate RSI based on your data
        # rsi = calculate_rsi(prices, lookback)
        
        # Get current position
        positions = [
            p for p in ph.positions.list(account_name=account_name, status="open")
            if p.ticker == ticker
        ]
        
        # if rsi < oversold and not positions:
        #     # Buy signal
        #     order = ph.orders.place(
        #         account_id=account.id,
        #         order=Order(
        #             ticker=ticker,
        #             direction="long",
        #             order_type="market",
        #             quantity=100.0,
        #             take_profit=105.0,
        #             stop_loss=95.0,
        #             instrument_type="stock"
        #         )
        #     )
        #     print(f"Opened {ticker} position: {order.id}")
        #
        # elif rsi > overbought and positions:
        #     # Sell signal
        #     for pos in positions:
        #         closed = ph.positions.close(
        #             position_id=pos.id,
        #             exit_price=current_price,
        #             close_reason="rsi_overbought"
        #         )
        #         print(f"Closed {ticker}: P&L {closed.realized_pnl:.2f}")

if __name__ == "__main__":
    rsi_strategy(
        Phantom(data_dir="./data"),
        account_name="My Trading Account",
        tickers=["AAPL", "MSFT"],
        lookback=14,
        oversold=30,
        overbought=70
    )
```

## Thread Safety

The library is thread-safe for multi-threaded applications. Mutating operations (`create()`, `delete()`, `place()`, `close()`, `modify()`) automatically acquire a write lock:

```python
from phantom import Phantom
import threading

ph = Phantom(data_dir="./data")

def background_trading():
    """Run in background thread."""
    try:
        account = ph.accounts.get("My Trading Account")
        # ... place orders, close positions, etc.
    except Exception as e:
        print(f"Error: {e}")

# Safe to call from multiple threads
thread1 = threading.Thread(target=background_trading)
thread2 = threading.Thread(target=background_trading)
thread1.start()
thread2.start()
thread1.join()
thread2.join()
```

## Paper Trading (Background)

Run paper trading in the background:

```python
from phantom import Phantom

ph = Phantom(data_dir="./data")

# Start paper trading in background thread
handle = ph.runner.paper_trade_background(
    account_id="account-id",
    tickers=["AAPL", "MSFT"],
    interval=300  # 5 minutes
)

# Check if still running
if handle.is_running():
    print("Paper trading active")

# Stop gracefully
handle.stop()
```

## Error Handling

All operations raise specific exceptions from `phantom.errors`:

```python
from phantom import Phantom
from phantom.errors import (
    NotFoundError,
    InsufficientFundsError,
    MarginError,
    ValidationError,
    DataError,
)

ph = Phantom(data_dir="./data")

try:
    account = ph.accounts.get("NonExistent")
except NotFoundError:
    print("Account not found")

try:
    order = ph.orders.place(account_id="id", order=my_order)
except InsufficientFundsError:
    print("Not enough cash")

try:
    result = ph.runner.backtest(...)
except DataError:
    print("Price data unavailable")
```

For complete API reference, see `phantom/__init__.py` and individual module docstrings.
