from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from phantom.errors import NotFoundError, PhantomError, ValidationError
from phantom.models.order import Order
from phantom.web.app import get_phantom, templates
from phantom.web.clock import get_simulated_now

router = APIRouter()

PAGE_SIZE = 50


@router.get("/orders", response_class=HTMLResponse)
async def order_history(request: Request, account: str | None = None, page: int = 1):
    """Render the order history page."""
    if not account:
        return RedirectResponse(url="/?error=account+required", status_code=303)
    try:
        ph = get_phantom()
        account_obj = ph.accounts.get(account)
        all_orders = ph.orders.list(account_name=account)
        # Sort newest first
        all_orders.sort(key=lambda o: o.created_at, reverse=True)
        total = len(all_orders)
        start = (page - 1) * PAGE_SIZE
        orders = all_orders[start : start + PAGE_SIZE]
        return templates.TemplateResponse(
            request=request,
            name="order_history.html",
            context={
                "account": account_obj,
                "orders": orders,
                "page": page,
                "total": total,
                "page_size": PAGE_SIZE,
                "has_prev": page > 1,
                "has_next": start + PAGE_SIZE < total,
            },
        )
    except NotFoundError:
        return RedirectResponse(url="/?error=account+not+found", status_code=303)
    except PhantomError as e:
        return RedirectResponse(url=f"/?error={e}", status_code=303)


@router.post("/orders/{order_id}/cancel")
async def cancel_order(order_id: str, account: str = Form(...)):
    """Cancel a pending order."""
    try:
        ph = get_phantom()
        ph.orders.cancel(order_id)
        return RedirectResponse(url=f"/orders?account={account}", status_code=303)
    except PhantomError as e:
        return RedirectResponse(url=f"/orders?account={account}&error={e}", status_code=303)


@router.post("/orders/{order_id}/fill")
async def fill_order(
    request: Request,
    order_id: str,
    fill_price: float = Form(...),
    account: str = Form(...),
):
    """Manually fill a pending order at a specified price."""
    try:
        ph = get_phantom()
        # Use simulated clock for fill datetime if set
        fill_dt = get_simulated_now()
        ph.orders.fill_manual(order_id, fill_price, fill_datetime=fill_dt)
        return RedirectResponse(url=f"/?account={account}", status_code=303)
    except PhantomError as e:
        return RedirectResponse(url=f"/?account={account}&error={e}", status_code=303)


@router.post("/orders/{order_id}/modify")
async def modify_order(
    order_id: str,
    account: str = Form(...),
    limit_price: float | None = Form(None),
    stop_loss: float | None = Form(None),
    take_profit: float | None = Form(None),
):
    """Modify a pending order's prices."""
    try:
        ph = get_phantom()
        ph.orders.modify(
            order_id,
            limit_price=limit_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )
        return RedirectResponse(url=f"/orders?account={account}", status_code=303)
    except PhantomError as e:
        return RedirectResponse(url=f"/orders?account={account}&error={e}", status_code=303)


@router.get("/orders/new", response_class=HTMLResponse)
async def order_form_page(request: Request):
    """Render the order placement form page."""
    try:
        ph = get_phantom()
        accounts = ph.accounts.list()
        sim_now = get_simulated_now()
        simulated_date = sim_now.date().isoformat() if sim_now else ""

        return templates.TemplateResponse(
            request=request,
            name="order_form.html",
            context={
                "accounts": accounts,
                "error": None,
                "simulated_date": simulated_date,
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

        # Use simulated clock for created_at if set, otherwise wall clock
        from phantom.utils.datetime import now_utc

        order_time = get_simulated_now() or now_utc()

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
            created_at=order_time,
        )

        # Place the order
        placed_order = ph.orders.place(account_id, order)

        # On success, render confirmation page
        accounts = ph.accounts.list()
        account_obj = next((a for a in accounts if a.id == account_id), None)
        return templates.TemplateResponse(
            request=request,
            name="order_confirmation.html",
            context={
                "order": placed_order,
                "account": account_obj,
            },
        )

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
