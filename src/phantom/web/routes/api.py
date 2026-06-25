from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse

from phantom.errors import NotFoundError, PhantomError
from phantom.web.app import get_phantom, templates

router = APIRouter()


@router.get("/api/equity-snapshot", response_class=HTMLResponse)
async def equity_snapshot(request: Request, account: str | None = Query(None)):
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
            request=request,
            name="_equity_panel.html",
            context={
                "account": account_obj,
                "total_unrealized": total_unrealized,
            },
        )

    except (NotFoundError, PhantomError):
        return "<div id='equity-panel' class='error'>Failed to load equity snapshot</div>"


@router.get("/api/positions-rows", response_class=HTMLResponse)
async def positions_rows(request: Request, account: str | None = Query(None)):
    """Return positions rows fragment for HTMX."""
    if not account:
        return "<tbody id='positions-tbody'><tr><td colspan='6'>Account not specified</td></tr></tbody>"

    try:
        ph = get_phantom()
        account_obj = ph.accounts.get(account)

        # Get open positions
        positions = ph.positions.list(account_name=account_obj.name, status="open")

        return templates.TemplateResponse(
            request=request,
            name="_positions_rows.html",
            context={
                "positions": positions,
                "account": account_obj,
            },
        )

    except (NotFoundError, PhantomError):
        return "<tbody id='positions-tbody'><tr><td colspan='6'>Failed to load positions</td></tr></tbody>"


@router.get("/api/orders-rows", response_class=HTMLResponse)
async def orders_rows(request: Request, account: str | None = Query(None)):
    """Return orders rows fragment for HTMX."""
    if not account:
        return "<tbody id='orders-tbody'></tbody>"

    try:
        ph = get_phantom()
        account_obj = ph.accounts.get(account)

        # Get pending orders
        pending_orders = ph.orders.list(account_name=account_obj.name, status="pending")

        return templates.TemplateResponse(
            request=request,
            name="_orders_rows.html",
            context={
                "pending_orders": pending_orders,
                "account": account_obj,
            },
        )

    except (NotFoundError, PhantomError):
        return "<tbody id='orders-tbody'></tbody>"


@router.get("/api/price", response_class=HTMLResponse)
async def price_lookup(ticker: str | None = Query(None), date: str | None = Query(None)):
    """Return an HTML price hint for the order form (HTMX target)."""
    if not ticker or not ticker.strip():
        return ""
    try:
        from datetime import date as date_type
        from datetime import timedelta

        from phantom.config import get_data_dir
        from phantom.data.yahoo import HistoricalProvider

        lookup_date = date_type.fromisoformat(date) if date else date_type.today()
        provider = HistoricalProvider(data_dir=str(get_data_dir()))
        bars = provider.get_bars(
            ticker.upper(), lookup_date - timedelta(days=5), lookup_date + timedelta(days=1)
        )
        if bars.empty:
            return f"<span style='color:#e74c3c;'>No cached data for {ticker.upper()} — run: phantom data fetch --ticker {ticker.upper()}</span>"
        available = bars[bars.index.date <= lookup_date]
        if available.empty:
            available = bars
        row = available.iloc[-1]
        price = float(row["Close"])
        bar_date = available.index[-1].date().isoformat()
        return f"<span style='color:#27ae60;'>Close on {bar_date}: <strong>${price:.4f}</strong></span>"
    except Exception as e:
        return f"<span style='color:#95a5a6;'>{e}</span>"


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
        labels = [p.timestamp.split("T")[0] for p in points]
        values = [p.equity for p in points]
        return JSONResponse({"labels": labels, "values": values})
    except Exception:
        return JSONResponse({"labels": [], "values": []})
