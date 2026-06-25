from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from phantom.errors import PhantomError, ValidationError
from phantom.models.order import Order
from phantom.web.app import get_phantom, templates

router = APIRouter()


@router.post("/orders/{order_id}/cancel")
async def cancel_order(order_id: str, account: str = Form(...)):
    """Cancel a pending order."""
    try:
        ph = get_phantom()
        ph.orders.cancel(order_id)
        return RedirectResponse(url=f"/?account={account}", status_code=303)
    except PhantomError as e:
        return RedirectResponse(url=f"/?account={account}&error={e}", status_code=303)


@router.get("/orders/new", response_class=HTMLResponse)
async def order_form_page(request: Request):
    """Render the order placement form page."""
    try:
        ph = get_phantom()
        accounts = ph.accounts.list()

        return templates.TemplateResponse(
            request=request,
            name="order_form.html",
            context={
                "accounts": accounts,
                "error": None,
            },
        )

    except PhantomError as e:
        return templates.TemplateResponse(
            request=request,
            name="order_form.html",
            context={
                "accounts": [],
                "error": str(e),
            },
        )


@router.post("/orders/new", response_class=HTMLResponse)
async def place_order(
    request: Request,
    account_id: str = Form(...),
    symbol: str = Form(...),
    side: str = Form(...),
    quantity: float = Form(...),
    order_type: str = Form(...),
    limit_price: float | None = Form(None),
    stop_loss: float | None = Form(None),
    take_profit: float | None = Form(None),
):
    """Place a new order."""
    try:
        ph = get_phantom()

        # Validate inputs
        if not account_id or not symbol or not side or quantity <= 0:
            accounts = ph.accounts.list()
            return templates.TemplateResponse(
                request=request,
                name="order_form.html",
                context={
                    "accounts": accounts,
                    "error": "Invalid form data",
                },
            )

        # Create order object
        order = Order(
            account_id=account_id,
            ticker=symbol.upper(),
            instrument_type="stock",
            direction=side,
            order_type=order_type,
            quantity=quantity,
            limit_price=limit_price if order_type == "limit" else None,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )

        # Place the order
        ph.orders.place(account_id, order)

        # On success, redirect to position detail (if filled) or order confirmation
        # For now, redirect to dashboard
        return RedirectResponse(url="/", status_code=303)

    except ValidationError as e:
        accounts = ph.accounts.list()
        return templates.TemplateResponse(
            request=request,
            name="order_form.html",
            context={
                "accounts": accounts,
                "error": str(e),
            },
        )
    except PhantomError as e:
        accounts = ph.accounts.list()
        return templates.TemplateResponse(
            request=request,
            name="order_form.html",
            context={
                "accounts": accounts,
                "error": str(e),
            },
        )
