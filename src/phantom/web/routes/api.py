from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse, JSONResponse

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
            },
        )

    except (NotFoundError, PhantomError):
        return "<tbody id='positions-tbody'><tr><td colspan='6'>Failed to load positions</td></tr></tbody>"


@router.get("/api/equity-data")
async def equity_data(account: str | None = Query(None)):
    """Return equity curve data as JSON for Chart.js."""
    if not account:
        return JSONResponse({"labels": [], "values": []})
    try:
        ph = get_phantom()
        account_obj = ph.accounts.get(account)
        from phantom.db.repositories.equity_repo import EquityRepo

        points = EquityRepo(ph._conn).list(account_obj.id)
        labels = [p.timestamp.split("T")[0] for p in points]  # Extract date from ISO string
        values = [p.equity for p in points]
        return JSONResponse({"labels": labels, "values": values})
    except PhantomError:
        return JSONResponse({"labels": [], "values": []})
