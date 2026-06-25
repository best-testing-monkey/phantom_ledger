from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from phantom.errors import NotFoundError, PhantomError
from phantom.web.app import get_phantom, templates

router = APIRouter()


@router.get("/positions/{position_id}", response_class=HTMLResponse)
async def position_detail(request: Request, position_id: str):
    """Render the position detail page."""
    try:
        ph = get_phantom()
        position = ph.positions.get(position_id)

        # Get account for reference
        account = ph.accounts.get(position.account_id)

        # Get notes for this position (if any)
        notes = []
        try:
            notes = ph.notes.list(position_id=position_id)
            # Truncate notes to 500 chars
            for note in notes:
                if len(note.content) > 500:
                    note.content = note.content[:497] + "..."
        except Exception:
            # Notes may not be available
            pass

        # Calculate duration if position is closed
        duration_days = None
        if position.exit_datetime and position.entry_datetime:
            duration_days = (position.exit_datetime - position.entry_datetime).days

        return templates.TemplateResponse(
            request=request,
            name="position_detail.html",
            context={
                "position": position,
                "account": account,
                "notes": notes,
                "duration_days": duration_days,
            },
        )

    except NotFoundError:
        return templates.TemplateResponse(
            request=request,
            name="position_detail.html",
            context={
                "position": None,
                "account": None,
                "notes": [],
                "error": f"Position {position_id} not found",
            },
            status_code=404,
        )
    except PhantomError as e:
        return templates.TemplateResponse(
            request=request,
            name="position_detail.html",
            context={
                "position": None,
                "account": None,
                "notes": [],
                "error": str(e),
            },
            status_code=500,
        )


@router.post("/positions/{position_id}/close")
async def close_position(
    request: Request,
    position_id: str,
    exit_price: float = Form(...),
    account: str = Form(...),
):
    """Close an open position."""
    try:
        ph = get_phantom()
        ph.positions.close(position_id, close_reason="manual", exit_price=exit_price)
        return RedirectResponse(url=f"/?account={account}", status_code=303)
    except PhantomError as e:
        # Re-render position detail with error
        position = ph.positions.get(position_id)
        account_obj = ph.accounts.get(position.account_id)
        notes = []
        try:
            notes = ph.notes.list(position_id=position_id)
            notes = sorted(notes, key=lambda n: n.created_at, reverse=True)
        except Exception:
            pass
        duration_days = None
        if position.exit_datetime and position.entry_datetime:
            duration_days = (position.exit_datetime - position.entry_datetime).days
        return templates.TemplateResponse(
            request=request,
            name="position_detail.html",
            context={
                "position": position,
                "account": account_obj,
                "notes": notes,
                "duration_days": duration_days,
                "error": str(e),
            },
        )
