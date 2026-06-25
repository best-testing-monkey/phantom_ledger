from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse

from phantom.errors import NotFoundError, PhantomError
from phantom.web.app import get_phantom, templates

router = APIRouter()


@router.get("/api/equity-snapshot", response_class=HTMLResponse)
async def equity_snapshot(account: str | None = Query(None)):
    """Return equity panel fragment for HTMX."""
    if not account:
        return "<div id='equity-panel' class='error'>Account not specified</div>"

    try:
        ph = get_phantom()
        account_obj = ph.accounts.get(account)

        # Get open positions for unrealized P&L
        positions = ph.positions.list(account_name=account_obj.name, status="open")
        total_unrealized = sum(p.unrealized_pnl for p in positions)

        return templates.TemplateResponse(
            name="_equity_panel.html",
            context={
                "account": account_obj,
                "total_unrealized": total_unrealized,
            },
        )

    except (NotFoundError, PhantomError):
        return "<div id='equity-panel' class='error'>Failed to load equity snapshot</div>"


@router.get("/api/positions-rows", response_class=HTMLResponse)
async def positions_rows(account: str | None = Query(None)):
    """Return positions rows fragment for HTMX."""
    if not account:
        return "<tbody id='positions-tbody'><tr><td colspan='6'>Account not specified</td></tr></tbody>"

    try:
        ph = get_phantom()
        account_obj = ph.accounts.get(account)

        # Get open positions
        positions = ph.positions.list(account_name=account_obj.name, status="open")

        return templates.TemplateResponse(
            name="_positions_rows.html",
            context={
                "positions": positions,
                "account": account_obj,
            },
        )

    except (NotFoundError, PhantomError):
        return "<tbody id='positions-tbody'><tr><td colspan='6'>Failed to load positions</td></tr></tbody>"


@router.get("/api/orders-rows", response_class=HTMLResponse)
async def orders_rows(account: str | None = Query(None)):
    """Return orders rows fragment for HTMX."""
    if not account:
        return "<tbody id='orders-tbody'></tbody>"

    try:
        ph = get_phantom()
        account_obj = ph.accounts.get(account)

        # Get pending orders
        pending_orders = ph.orders.list(account_name=account_obj.name, status="pending")

        return templates.TemplateResponse(
            name="_orders_rows.html",
            context={
                "pending_orders": pending_orders,
                "account": account_obj,
            },
        )

    except (NotFoundError, PhantomError):
        return "<tbody id='orders-tbody'></tbody>"
