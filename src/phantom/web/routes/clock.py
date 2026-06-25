"""Clock control routes for manual backtesting time adjustment."""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from phantom.web.app import get_phantom, templates
from phantom.web.clock import get_simulated_now, set_simulated_now, step_simulated_now

logger = logging.getLogger(__name__)
router = APIRouter()


def _run_simulation_to(new_dt: datetime) -> None:
    """Run backtest for all accounts with pending orders up to new_dt. Silently skips on error."""
    try:
        ph = get_phantom()
        accounts = ph.accounts.list()
        for account in accounts:
            try:
                pending = ph.orders.list(account_name=account.name, status="pending")
                relevant = [o for o in pending if o.created_at <= new_dt]
                if not relevant:
                    continue
                tickers = list({o.ticker for o in relevant})
                start_dt = min(o.created_at for o in relevant)
                start = start_dt.date() if hasattr(start_dt, "date") else start_dt
                end = new_dt.date() if hasattr(new_dt, "date") else new_dt
                if start > end:
                    continue
                logger.info("Auto-simulation: account %s tickers %s %s→%s", account.name, tickers, start, end)
                ph.runner.backtest(account_id=account.id, tickers=tickers, start=start, end=end)
            except Exception:
                logger.exception("Auto-simulation failed for account %s", account.name)
    except Exception:
        logger.exception("Auto-simulation: could not load accounts")


@router.get("/api/clock", response_class=HTMLResponse)
async def clock_fragment(request: Request):
    """Return the clock panel fragment for HTMX refresh."""
    now = get_simulated_now()
    return templates.TemplateResponse(
        request=request, name="_clock_panel.html", context={"simulated_now": now}
    )


@router.post("/clock/set")
async def clock_set(simulated_now: str = Form(...), account: str | None = Form(None)):
    """Set the simulated clock. If moving forward, auto-runs simulation for pending orders."""
    old_dt = get_simulated_now()
    dt = datetime.fromisoformat(simulated_now).replace(tzinfo=timezone.utc)
    set_simulated_now(dt)
    if old_dt is None or dt > old_dt:
        _run_simulation_to(dt)
    redirect = f"/?account={account}" if account else "/"
    return RedirectResponse(url=redirect, status_code=303)


@router.post("/clock/step")
async def clock_step(days: int = Form(...), account: str | None = Form(None)):
    """Step the simulated clock. Forward steps auto-run simulation for pending orders."""
    new_dt = step_simulated_now(days)
    if days > 0:
        _run_simulation_to(new_dt)
    redirect = f"/?account={account}" if account else "/"
    return RedirectResponse(url=redirect, status_code=303)
