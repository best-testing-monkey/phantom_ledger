"""Clock control routes for manual backtesting time adjustment."""

from datetime import datetime, timezone

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from phantom.web.app import templates
from phantom.web.clock import get_simulated_now, set_simulated_now, step_simulated_now

router = APIRouter()


@router.get("/api/clock", response_class=HTMLResponse)
async def clock_fragment(request: Request):
    """Return the clock panel fragment for HTMX refresh."""
    now = get_simulated_now()
    return templates.TemplateResponse(
        request=request, name="_clock_panel.html", context={"simulated_now": now}
    )


@router.post("/clock/set")
async def clock_set(simulated_now: str = Form(...)):
    """Set the simulated clock to a specific datetime."""
    dt = datetime.fromisoformat(simulated_now).replace(tzinfo=timezone.utc)
    set_simulated_now(dt)
    return RedirectResponse(url="/", status_code=303)


@router.post("/clock/step")
async def clock_step(days: int = Form(...)):
    """Step the simulated clock forward/backward by N days."""
    step_simulated_now(days)
    return RedirectResponse(url="/", status_code=303)
