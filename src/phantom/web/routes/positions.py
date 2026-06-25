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
            # Sort newest-first
            notes = sorted(notes, key=lambda n: n.created_at, reverse=True)
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


@router.post("/positions/{position_id}/notes")
async def add_note(
    request: Request,
    position_id: str,
    content: str = Form(...),
    title: str | None = Form(None),
):
    """Create a new trade note for a position."""
    try:
        if not content.strip():
            ph = get_phantom()
            position = ph.positions.get(position_id)
            account = ph.accounts.get(position.account_id)
            notes = ph.notes.list(position_id=position_id)
            notes = sorted(notes, key=lambda n: n.created_at, reverse=True)
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
                    "error": "Note content cannot be empty",
                },
            )
        ph = get_phantom()
        position = ph.positions.get(position_id)
        ph.notes.add(
            position_id=position_id,
            account_id=position.account_id,
            content=content,
            title=title or None,
        )
        return RedirectResponse(url=f"/positions/{position_id}", status_code=303)
    except PhantomError as e:
        return RedirectResponse(url=f"/positions/{position_id}?error={e}", status_code=303)


@router.post("/positions/{position_id}/notes/{note_id}/delete")
async def delete_note(position_id: str, note_id: str):
    """Delete a trade note."""
    try:
        ph = get_phantom()
        ph.notes.delete(note_id)
    except Exception:
        pass
    return RedirectResponse(url=f"/positions/{position_id}", status_code=303)
