from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from phantom.errors import NotFoundError, PhantomError
from phantom.web.app import get_phantom, templates
from phantom.web.clock import get_simulated_now

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, account: str | None = None, page: int = 1):
    """Render the dashboard page."""
    PAGE_SIZE = 25
    page = max(1, page)

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
                    "page": 1,
                    "total_closed": 0,
                    "page_size": PAGE_SIZE,
                    "has_prev": False,
                    "has_next": False,
                    "trade_start": 0,
                    "trade_end": 0,
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
                        "page": 1,
                        "total_closed": 0,
                        "page_size": PAGE_SIZE,
                        "has_prev": False,
                        "has_next": False,
                        "trade_start": 0,
                        "trade_end": 0,
                        "error": f"Account {account} not found",
                        "simulated_now": get_simulated_now(),
                    },
                )

        simulated_now = get_simulated_now()

        # All positions for this account
        all_positions = ph.positions.list(account_name=account_obj.name)

        if simulated_now:
            # Only show positions whose entry predates simulated clock
            visible = [p for p in all_positions if p.entry_datetime and p.entry_datetime <= simulated_now]
            # Open at simulated_now: genuinely open, or closed with exit in the "future"
            positions = [
                p for p in visible
                if p.status == "open"
                or (p.status == "closed" and p.exit_datetime and p.exit_datetime > simulated_now)
            ]
            closed_at_now = [
                p for p in visible
                if p.status == "closed" and p.exit_datetime and p.exit_datetime <= simulated_now
            ]
            # Only pending orders created at or before simulated clock
            all_pending = ph.orders.list(account_name=account_obj.name, status="pending")
            pending_orders = [o for o in all_pending if o.created_at <= simulated_now]
        else:
            positions = ph.positions.list(account_name=account_obj.name, status="open")
            pending_orders = ph.orders.list(account_name=account_obj.name, status="pending")
            closed_at_now = [p for p in all_positions if p.status == "closed" and p.exit_datetime]

        all_closed = sorted(closed_at_now, key=lambda p: p.exit_datetime, reverse=True)
        total_closed = len(all_closed)
        start = (page - 1) * PAGE_SIZE
        recent_trades = all_closed[start : start + PAGE_SIZE]

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
                "page": page,
                "total_closed": total_closed,
                "page_size": PAGE_SIZE,
                "has_prev": page > 1,
                "has_next": start + PAGE_SIZE < total_closed,
                "trade_start": start + 1 if total_closed > 0 else 0,
                "trade_end": min(start + PAGE_SIZE, total_closed),
                "total_unrealized": total_unrealized,
                "report": report,
                "no_accounts": False,
                "simulated_now": simulated_now,
                "simulated_date": simulated_now.date().isoformat() if simulated_now else "",
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
                "page": 1,
                "total_closed": 0,
                "page_size": PAGE_SIZE,
                "has_prev": False,
                "has_next": False,
                "trade_start": 0,
                "trade_end": 0,
                "error": str(e),
                "simulated_now": get_simulated_now(),
            },
        )
