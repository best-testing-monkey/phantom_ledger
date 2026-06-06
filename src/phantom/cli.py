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


@order_app.command("place")
def order_place(
    account: str = typer.Option(..., "--account"),
    ticker: str = typer.Option(..., "--ticker"),
    direction: str = typer.Option(..., "--direction", help="long or short"),
    order_type: str = typer.Option(..., "--type", help="market/limit/stop/stop_limit"),
    quantity: float = typer.Option(..., "--quantity"),
    instrument: str = typer.Option("stock", "--instrument"),
    limit_price: float = typer.Option(None, "--limit-price"),
    stop_price: float = typer.Option(None, "--stop-price"),
    trailing_amount: float = typer.Option(None, "--trailing-amount"),
    trailing_pct: float = typer.Option(None, "--trailing-pct"),
    tp: float = typer.Option(None, "--tp"),
    sl: float = typer.Option(None, "--sl"),
    at: str = typer.Option(None, "--at", help="Historical created_at datetime"),
    good_til: str = typer.Option(None, "--good-til"),
):
    """Place an order."""
    try:
        from rich.panel import Panel

        from phantom.models.order import Order
        from phantom.utils.datetime import parse_datetime

        ph = get_phantom()
        acct = ph.accounts.get(account)
        order_kwargs = dict(
            account_id=acct.id,
            ticker=ticker,
            instrument_type=instrument,
            direction=direction,
            order_type=order_type,
            quantity=quantity,
            limit_price=limit_price,
            stop_price=stop_price,
            trailing_amount=trailing_amount,
            trailing_pct=trailing_pct,
            take_profit=tp,
            stop_loss=sl,
        )
        if at:
            order_kwargs["created_at"] = parse_datetime(at)
        if good_til:
            order_kwargs["good_til"] = parse_datetime(good_til)
        order = ph.orders.place(account_id=acct.id, order=Order(**order_kwargs))
        console.print(
            Panel(
                f"ID: {order.id}\nTicker: {order.ticker}\nDirection: {order.direction}\n"
                f"Type: {order.order_type}\nQuantity: {order.quantity}\nStatus: {order.status}",
                title="Order Placed",
            )
        )
    except PhantomError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1)


@order_app.command("list")
def order_list(
    account: str = typer.Option(..., "--account"),
    status: str = typer.Option(None, "--status"),
):
    """List orders for an account."""
    try:
        from rich.table import Table

        ph = get_phantom()
        orders = ph.orders.list(account_name=account, status=status)
        if not orders:
            console.print("No orders found.")
            return
        table = Table(title=f"Orders — {account}")
        table.add_column("ID")
        table.add_column("Ticker")
        table.add_column("Direction")
        table.add_column("Type")
        table.add_column("Quantity")
        table.add_column("Status")
        table.add_column("Created At")
        for o in orders:
            table.add_row(
                o.id[:8] + "...",
                o.ticker,
                o.direction,
                o.order_type,
                str(o.quantity),
                o.status,
                str(o.created_at)[:19],
            )
        console.print(table)
    except PhantomError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1)


@order_app.command("cancel")
def order_cancel(order_id: str = typer.Argument(...)):
    """Cancel a pending order."""
    try:
        ph = get_phantom()
        ph.orders.cancel(order_id)
        console.print(f"Order {order_id} cancelled.")
    except PhantomError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1)


def _format_duration(entry_datetime) -> str:
    from phantom.utils.datetime import now_utc

    delta = now_utc() - entry_datetime
    days = delta.days
    hours, remainder = divmod(delta.seconds, 3600)
    minutes = remainder // 60
    if days > 0:
        return f"{days}d {hours}h"
    return f"{hours}h {minutes}m"


@position_app.command("list")
def position_list(
    account: str = typer.Option(None, "--account"),
    status: str = typer.Option(None, "--status"),
):
    """List positions."""
    try:
        from rich.table import Table

        ph = get_phantom()
        positions = ph.positions.list(account_name=account, status=status)
        if not positions:
            console.print("No positions found.")
            return
        table = Table(title="Positions")
        table.add_column("ID")
        table.add_column("Symbol")
        table.add_column("Side")
        table.add_column("Qty", justify="right")
        table.add_column("Entry", justify="right")
        table.add_column("Duration")
        table.add_column("Status")
        for p in positions:
            table.add_row(
                p.id[:8],
                p.ticker,
                p.direction,
                str(p.quantity),
                f"{p.entry_price:.4f}",
                _format_duration(p.entry_datetime),
                p.status,
            )
        console.print(table)
    except PhantomError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1)


@position_app.command("show")
def position_show(position_id: str = typer.Argument(...)):
    """Show position details."""
    try:
        from rich.panel import Panel

        ph = get_phantom()
        p = ph.positions.get(position_id)
        lines = [
            f"ID: {p.id}",
            f"Symbol: {p.ticker}  Type: {p.instrument_type}",
            f"Side: {p.direction}  Qty: {p.quantity}",
            f"Entry: {p.entry_price:.4f}  Duration: {_format_duration(p.entry_datetime)}",
            f"TP: {p.take_profit}  SL: {p.stop_loss}",
            f"Commission Entry: {p.commission_entry:.4f}",
            f"Spread Cost: {p.spread_cost:.4f}",
            f"Overnight: {p.overnight_costs:.4f}",
            f"Status: {p.status}",
        ]
        console.print(Panel("\n".join(lines), title="Position Detail"))
    except PhantomError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1)


@position_app.command("close")
def position_close(
    position_id: str = typer.Argument(...),
    yes: bool = typer.Option(False, "--yes", "-y"),
    reason: str = typer.Option("manual", "--reason"),
    price: float = typer.Option(..., "--price", help="Exit price"),
):
    """Close an open position at specified price."""
    try:
        from rich.panel import Panel

        ph = get_phantom()
        pos = ph.positions.get(position_id)
        if pos.status != "open":
            console.print(f"[red]Error:[/red] Position is already {pos.status}")
            raise typer.Exit(code=1)
        if not yes:
            typer.confirm(f"Close position {position_id[:8]}?", abort=True)
        closed = ph.positions.close(position_id=position_id, close_reason=reason, exit_price=price)
        console.print(
            Panel(
                f"Realized P&L: {closed.realized_pnl:.2f}\n"
                f"Commission paid: {closed.commission_entry + closed.commission_exit:.2f}\n"
                f"Close reason: {closed.close_reason}",
                title=f"Position Closed: {position_id[:8]}",
            )
        )
    except PhantomError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1)


@position_app.command("modify")
def position_modify(
    position_id: str = typer.Argument(...),
    tp: float = typer.Option(None, "--tp"),
    sl: float = typer.Option(None, "--sl"),
):
    """Update take-profit and/or stop-loss on an open position."""
    if tp is None and sl is None:
        console.print("[red]Error:[/red] Provide at least --tp or --sl.")
        raise typer.Exit(code=1)
    try:
        from rich.panel import Panel

        ph = get_phantom()
        position = ph.positions.modify(position_id, take_profit=tp, stop_loss=sl)
        msg = (
            f"Position [bold]{position.id[:8]}[/bold] updated.\n"
            f"TP: {position.take_profit}  SL: {position.stop_loss}"
        )
        console.print(Panel(msg, title="Position Modified"))
    except PhantomError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1)


def _human_bytes(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    elif size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


def _open_editor(title: str) -> str | None:
    from pathlib import Path
    import subprocess
    import tempfile

    editor = os.environ.get("EDITOR", "vi")
    header = f"# {title}\n\n"
    tmp = tempfile.NamedTemporaryFile(suffix=".md", mode="w", delete=False, encoding="utf-8")
    try:
        tmp.write(header)
        tmp.flush()
        tmp.close()
        subprocess.run([editor, tmp.name], check=False)
        content = Path(tmp.name).read_text(encoding="utf-8")
        if not content.strip() or content.strip() == header.strip():
            return None
        return content
    finally:
        Path(tmp.name).unlink(missing_ok=True)


@note_app.command("add")
def note_add(
    position_id: str = typer.Argument(..., help="Position ULID"),
    title: str = typer.Option(..., "--title"),
    file: str = typer.Option(None, "--file"),
):
    """Add a note to a position."""
    try:
        from rich.panel import Panel

        ph = get_phantom()
        pos = ph.positions.get(position_id)
        if file:
            note = ph.notes.create_from_file(
                position_id=position_id,
                account_id=pos.account_id,
                title=title,
                source_path=file,
            )
        else:
            content = _open_editor(title)
            if content is None:
                console.print("Aborted: note was empty.")
                return
            note = ph.notes.create(
                position_id=position_id,
                account_id=pos.account_id,
                title=title,
                content=content,
            )
        console.print(
            Panel(
                f"[bold]ID:[/bold] {note.id}\n"
                f"[bold]Title:[/bold] {note.title}\n"
                f"[bold]Size:[/bold] {_human_bytes(note.content_size)}\n"
                f"[bold]Path:[/bold] {note.file_path}",
                title="Note Created",
            )
        )
    except PhantomError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1)


@note_app.command("list")
def note_list(position_id: str = typer.Argument(..., help="Position ULID")):
    """List all notes for a position."""
    try:
        from rich.table import Table

        ph = get_phantom()
        ph.positions.get(position_id)
        notes = ph.notes.list(position_id)
        if not notes:
            console.print(f"No notes found for position {position_id}.")
            return
        table = Table(title=f"Notes for {position_id[:12]}")
        table.add_column("Note ID")
        table.add_column("Title")
        table.add_column("Size", justify="right")
        table.add_column("Created At")
        for note in notes:
            table.add_row(
                note.id[:12], note.title, _human_bytes(note.content_size), note.created_at
            )
        console.print(table)
    except PhantomError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1)


@note_app.command("show")
def note_show(note_id: str = typer.Argument(..., help="Note ULID")):
    """Print note content to stdout (pipe-friendly)."""
    try:
        ph = get_phantom()
        content = ph.notes.read(note_id)
        print(content, end="")
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


@replay_app.command("all")
def replay_all(account: str = typer.Option(..., "--account")):
    """Replay all un-replayed positions for an account."""
    try:
        from rich.progress import Progress

        ph = get_phantom()
        positions = ph.positions.list(account_name=account, replay_completed_at=None)
        if not positions:
            console.print("No un-replayed positions found.")
            return
        closed_count = 0
        with Progress() as progress:
            task = progress.add_task("Replaying...", total=len(positions))
            for pos in positions:
                progress.update(task, description=f"[cyan]{pos.ticker}[/cyan]")
                try:
                    result = ph.replay.replay_position(pos)
                    if result.status == "closed":
                        closed_count += 1
                except PhantomError as e:
                    console.print(f"[yellow]Warning:[/yellow] {pos.id}: {e}")
                progress.advance(task)
        console.print(
            f"Replayed {len(positions)} positions: "
            f"{closed_count} closed, {len(positions) - closed_count} still open"
        )
    except PhantomError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1)


@replay_app.command("single")
def replay_single(
    position_id: str = typer.Option(..., "--position"),
    force: bool = typer.Option(False, "--force"),
):
    """Replay a single position by ID."""
    try:
        from rich.panel import Panel

        ph = get_phantom()
        pos = ph.positions.get(position_id)
        if pos.replay_completed_at and not force:
            console.print("[red]Error:[/red] Position already replayed. Use --force to re-run.")
            raise typer.Exit(code=1)
        if force:
            ph.positions.reset_replay(position_id)
            pos = ph.positions.get(position_id)
        with console.status("Replaying..."):
            result = ph.replay.replay_position(pos)
        if result.status == "closed":
            details = (
                f"Ticker: {result.ticker}\nDirection: {result.direction}\n"
                f"Entry: {result.entry_price:.4f}\nClose: {result.exit_price:.4f}\n"
                f"Reason: {result.close_reason}\nP&L: {result.realized_pnl:.2f}"
            )
        else:
            details = (
                f"Ticker: {result.ticker}\nDirection: {result.direction}\n"
                f"Entry: {result.entry_price:.4f}\nStatus: still open"
            )
        console.print(Panel(details, title="Replay Result"))
    except PhantomError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
