from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from phantom.errors import NotFoundError, PhantomError
from phantom.web.app import get_phantom, templates
from phantom.web.clock import get_simulated_now

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, account: str | None = None):
    """Render the dashboard page."""
    try:
        ph = get_phantom()
        accounts = ph.accounts.list()

        if not accounts:
            return templates.TemplateResponse(
                request=request,
                name="dashboard.html",
                context={
                    "account": None,
                    "accounts": accounts,
                    "positions": [],
                    "pending_orders": [],
                    "recent_trades": [],
                    "report": {},
                    "no_accounts": True,
                    "simulated_now": get_simulated_now(),
                },
            )

        # Use first account if not specified
        if account is None:
            account_obj = accounts[0]
        else:
            try:
                account_obj = ph.accounts.get(account)
            except NotFoundError:
                return templates.TemplateResponse(
                    request=request,
                    name="dashboard.html",
                    context={
                        "account": None,
                        "accounts": accounts,
                        "positions": [],
                        "pending_orders": [],
                        "recent_trades": [],
                        "report": {},
                        "error": f"Account {account} not found",
                        "simulated_now": get_simulated_now(),
                    },
                )

        # Get open positions
        positions = ph.positions.list(account_name=account_obj.name, status="open")

        # Get pending orders
        pending_orders = ph.orders.list(account_name=account_obj.name, status="pending")

        # Get recent closed trades (last 10)
        all_positions = ph.positions.list(account_name=account_obj.name)
        closed_trades = [p for p in all_positions if p.status == "closed" and p.exit_datetime]
        recent_trades = sorted(closed_trades, key=lambda p: p.exit_datetime, reverse=True)[:10]

        # Calculate total unrealized P&L
        total_unrealized = sum(p.unrealized_pnl for p in positions)

        # Get account metrics (performance summary)
        report = {}
        try:
            report = ph.reports.account_metrics(account_obj.name)
        except Exception:
            pass

        return templates.TemplateResponse(
            request=request,
            name="dashboard.html",
            context={
                "account": account_obj,
                "accounts": accounts,
                "positions": positions,
                "pending_orders": pending_orders,
                "recent_trades": recent_trades,
                "total_unrealized": total_unrealized,
                "report": report,
                "no_accounts": False,
                "simulated_now": get_simulated_now(),
            },
        )

    except PhantomError as e:
        return templates.TemplateResponse(
            request=request,
            name="dashboard.html",
            context={
                "account": None,
                "accounts": [],
                "positions": [],
                "pending_orders": [],
                "recent_trades": [],
                "report": {},
                "error": str(e),
                "simulated_now": get_simulated_now(),
            },
        )
