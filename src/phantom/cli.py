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


@account_app.command("list")
def account_list():
    """List all accounts."""
    try:
        ph = get_phantom()
        accounts = ph.accounts.list()
        console.print(accounts)
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
def data_fetch():
    """Fetch market data."""
    try:
        get_phantom()
        console.print("Data fetch not yet implemented")
    except PhantomError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1)


@broker_app.command("list")
def broker_list():
    """List broker profiles."""
    try:
        ph = get_phantom()
        brokers = ph.brokers.list()
        console.print(brokers)
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
