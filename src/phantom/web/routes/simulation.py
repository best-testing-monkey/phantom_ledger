from datetime import date

from fastapi import APIRouter, Form
from fastapi.responses import RedirectResponse

from phantom.errors import PhantomError
from phantom.web.app import get_phantom
from phantom.web.clock import get_simulated_now

router = APIRouter()


@router.post("/simulation/run")
async def run_simulation(account: str = Form(...)):
    """Run the backtest engine from pending order dates to the simulated clock date."""
    try:
        ph = get_phantom()
        account_obj = ph.accounts.get(account)

        pending = ph.orders.list(account_name=account, status="pending")
        if not pending:
            return RedirectResponse(
                url=f"/?account={account}&error=No+pending+orders+to+simulate", status_code=303
            )

        tickers = list({o.ticker for o in pending})
        start_dt = min(o.created_at for o in pending)
        start = start_dt.date() if hasattr(start_dt, "date") else start_dt

        sim_now = get_simulated_now()
        end = sim_now.date() if sim_now else date.today()

        if start > end:
            return RedirectResponse(
                url=f"/?account={account}&error=Order+dates+are+in+the+future+relative+to+the+simulated+clock",
                status_code=303,
            )

        ph.runner.backtest(account_id=account_obj.id, tickers=tickers, start=start, end=end)
        return RedirectResponse(url=f"/?account={account}", status_code=303)

    except PhantomError as e:
        return RedirectResponse(url=f"/?account={account}&error={e}", status_code=303)
    except Exception as e:
        return RedirectResponse(url=f"/?account={account}&error={e}", status_code=303)
