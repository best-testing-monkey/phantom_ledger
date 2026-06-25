from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from phantom.errors import NotFoundError, PhantomError
from phantom.web.app import get_phantom, templates

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
                    "positions": [],
                    "recent_trades": [],
                    "page": 1,
                    "total_closed": 0,
                    "page_size": PAGE_SIZE,
                    "has_prev": False,
                    "has_next": False,
                    "trade_start": 0,
                    "trade_end": 0,
                    "no_accounts": True,
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
                        "positions": [],
                        "recent_trades": [],
                        "page": 1,
                        "total_closed": 0,
                        "page_size": PAGE_SIZE,
                        "has_prev": False,
                        "has_next": False,
                        "trade_start": 0,
                        "trade_end": 0,
                        "error": f"Account {account} not found",
                    },
                )

        # Get open positions
        positions = ph.positions.list(account_name=account_obj.name, status="open")

        # Get closed trades with pagination
        all_positions = ph.positions.list(account_name=account_obj.name)
        closed_trades = [p for p in all_positions if p.status == "closed" and p.exit_datetime]
        all_closed = sorted(closed_trades, key=lambda p: p.exit_datetime, reverse=True)
        total_closed = len(all_closed)
        start = (page - 1) * PAGE_SIZE
        recent_trades = all_closed[start : start + PAGE_SIZE]

        # Calculate total unrealized P&L
        total_unrealized = sum(p.unrealized_pnl for p in positions)

        return templates.TemplateResponse(
            request=request,
            name="dashboard.html",
            context={
                "account": account_obj,
                "positions": positions,
                "recent_trades": recent_trades,
                "page": page,
                "total_closed": total_closed,
                "page_size": PAGE_SIZE,
                "has_prev": page > 1,
                "has_next": start + PAGE_SIZE < total_closed,
                "trade_start": start + 1 if total_closed > 0 else 0,
                "trade_end": min(start + PAGE_SIZE, total_closed),
                "total_unrealized": total_unrealized,
                "no_accounts": False,
            },
        )

    except PhantomError as e:
        return templates.TemplateResponse(
            request=request,
            name="dashboard.html",
            context={
                "account": None,
                "positions": [],
                "recent_trades": [],
                "page": 1,
                "total_closed": 0,
                "page_size": PAGE_SIZE,
                "has_prev": False,
                "has_next": False,
                "trade_start": 0,
                "trade_end": 0,
                "error": str(e),
            },
        )
