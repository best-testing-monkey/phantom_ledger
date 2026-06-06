import os

from rich.console import Console
import typer

from phantom.errors import PhantomError

app = typer.Typer(help="Phantom Ledger — paper trading and backtesting engine")
account_app = typer.Typer(help="Manage accounts")
order_app = typer.Typer(help="Place and manage orders")
position_app = typer.Typer(help="Manage positions")
note_app = typer.Typer(help="Manage trade notes")
report_app = typer.Typer(help="Generate reports")
data_app = typer.Typer(help="Manage market data")
broker_app = typer.Typer(help="Manage broker profiles")
run_app = typer.Typer(help="Run backtests and paper trading")
replay_app = typer.Typer(help="Replay historical positions")

app.add_typer(account_app, name="account")
app.add_typer(order_app, name="order")
app.add_typer(position_app, name="position")
app.add_typer(note_app, name="note")
app.add_typer(report_app, name="report")
app.add_typer(data_app, name="data")
app.add_typer(broker_app, name="broker")
app.add_typer(run_app, name="run")
app.add_typer(replay_app, name="replay")

console = Console()


def get_phantom():
    from phantom import Phantom

    return Phantom(data_dir=os.environ.get("PHANTOM_DATA", "./data"))


@account_app.command("create")
def account_create(
    name: str = typer.Option(..., "--name", help="Account name"),
    account_type: str = typer.Option(
        ..., "--type", help="Account type: pattern/manual/algorithm/aggregate"
    ),
    broker: str = typer.Option(..., "--broker", help="Broker profile name"),
    capital: float = typer.Option(..., "--capital", help="Starting capital"),
    currency: str = typer.Option("EUR", "--currency", help="Base currency"),
    pattern: str = typer.Option(None, "--pattern", help="Pattern tag (required for pattern type)"),
    algorithm_id: str = typer.Option(None, "--algorithm-id", help="Algorithm ID"),
    algorithm_version: str = typer.Option(None, "--algorithm-version", help="Algorithm version"),
    children: str = typer.Option(None, "--children", help="Comma-separated child account names"),
):
    """Create a new account."""
    try:
        from rich.panel import Panel

        ph = get_phantom()
        child_ids = [c.strip() for c in children.split(",")] if children else None
        account = ph.accounts.create(
            name=name,
            account_type=account_type,
            broker=broker,
            capital=capital,
            currency=currency,
            pattern_tag=pattern,
            algorithm_id=algorithm_id,
            algorithm_version=algorithm_version,
            child_account_ids=child_ids,
        )
        console.print(
            Panel(
                f"ID: {account.id}\nType: {account.account_type}\n"
                f"Broker: {account.broker_profile_id}\n"
                f"Capital: {account.initial_capital} {account.base_currency}",
                title=f"Account: {account.name}",
            )
        )
    except PhantomError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1)


@account_app.command("list")
def account_list():
    """List all accounts."""
    try:
        from rich.table import Table

        ph = get_phantom()
        accounts = ph.accounts.list()
        if not accounts:
            console.print("No accounts found. Use 'phantom account create' to add one.")
            return
        table = Table(title="Accounts")
        table.add_column("Name")
        table.add_column("Type")
        table.add_column("Broker")
        table.add_column("Initial Capital")
        table.add_column("Cash")
        for a in accounts:
            table.add_row(
                a.name,
                a.account_type,
                a.broker_profile_id,
                f"{a.initial_capital:.2f} {a.base_currency}",
                f"{a.cash:.2f} {a.base_currency}",
            )
        console.print(table)
    except PhantomError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1)


@account_app.command("show")
def account_show(name: str = typer.Argument(..., help="Account name")):
    """Show account details."""
    try:
        from rich.panel import Panel

        ph = get_phantom()
        a = ph.accounts.get(name)
        details = (
            f"ID: {a.id}\n"
            f"Type: {a.account_type}\n"
            f"Broker: {a.broker_profile_id}\n"
            f"Currency: {a.base_currency}\n"
            f"Initial Capital: {a.initial_capital:.2f}\n"
            f"Cash: {a.cash:.2f}\n"
            f"Created: {a.created_at}"
        )
        if a.pattern_tag:
            details += f"\nPattern: {a.pattern_tag}"
        if a.algorithm_id:
            details += f"\nAlgorithm: {a.algorithm_id} {a.algorithm_version or ''}"
        console.print(Panel(details, title=f"Account: {a.name}"))
    except PhantomError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1)


@order_app.command("list")
def order_list():
    """List all orders."""
    try:
        ph = get_phantom()
        orders = ph.orders.list()
        console.print(orders)
    except PhantomError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1)


@position_app.command("list")
def position_list():
    """List all positions."""
    try:
        ph = get_phantom()
        positions = ph.positions.list()
        console.print(positions)
    except PhantomError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1)


@note_app.command("list")
def note_list():
    """List all notes."""
    try:
        ph = get_phantom()
        notes = ph.notes.list()
        console.print(notes)
    except PhantomError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1)


@report_app.command("show")
def report_show():
    """Show report."""
    try:
        get_phantom()
        console.print("Report not yet implemented")
    except PhantomError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1)


@data_app.command("fetch")
def data_fetch(
    ticker: str = typer.Option(..., "--ticker", help="Ticker symbol"),
    start: str = typer.Option(..., "--start", help="Start date (YYYY-MM-DD)"),
    end: str = typer.Option(None, "--end", help="End date (YYYY-MM-DD), defaults to today"),
):
    """Fetch and cache historical price data."""
    from datetime import date, datetime

    try:
        ph = get_phantom()
        start_dt = datetime.fromisoformat(start)
        end_dt = (
            datetime.fromisoformat(end)
            if end
            else datetime.combine(date.today(), datetime.min.time())
        )
        with console.status(f"Fetching {ticker}..."):
            df = ph.data.fetch_prices(ticker=ticker, start=start_dt, end=end_dt)
        console.print(f"Fetched {len(df)} bars for {ticker}")
    except PhantomError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1)


@broker_app.command("list")
def broker_list():
    """List all loaded broker profiles."""
    try:
        from rich.table import Table

        ph = get_phantom()
        profiles = ph.brokers.list()
        if not profiles:
            console.print("No broker profiles loaded. Use 'phantom broker load <file>' to add one.")
            return
        table = Table(title="Broker Profiles")
        table.add_column("Name")
        table.add_column("Supported Instruments")
        table.add_column("Commission Type")
        table.add_column("FX Cost")
        for p in profiles:
            table.add_row(
                p.name,
                ", ".join(p.supported_instruments),
                p.commission.model_type,
                f"{p.fx_conversion_pct:.2%}",
            )
        console.print(table)
    except PhantomError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1)


@broker_app.command("show")
def broker_show(name: str = typer.Argument(..., help="Broker profile name")):
    """Show details of a broker profile."""
    try:
        from rich.panel import Panel

        ph = get_phantom()
        p = ph.brokers.get(name)
        details = (
            f"Commission: {p.commission.model_type} "
            f"(fee={p.commission.fixed_fee})\n"
            f"Spread: {p.spread.model_type}\n"
            f"Slippage: {p.slippage.model_type}\n"
            f"Overnight rate source: {p.overnight.rate_source}\n"
            f"Margin call level: {p.margin.margin_call_level}\n"
            f"Stop-out level: {p.margin.stop_out_level}\n"
            f"FX cost: {p.fx_conversion_pct:.2%}\n"
            f"Base currency: {p.fx_base_currency}\n"
            f"Max leverage: {p.max_leverage}x\n"
            f"Instruments: {', '.join(p.supported_instruments)}"
        )
        console.print(Panel(details, title=f"Broker: {p.name}"))
    except PhantomError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1)


@run_app.command("backtest")
def run_backtest():
    """Run a backtest."""
    try:
        get_phantom()
        console.print("Backtest not yet implemented")
    except PhantomError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1)


@replay_app.command("account")
def replay_account():
    """Replay account history."""
    try:
        get_phantom()
        console.print("Replay not yet implemented")
    except PhantomError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
