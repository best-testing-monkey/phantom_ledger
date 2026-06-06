from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse

from phantom.errors import NotFoundError, PhantomError
from phantom.reports.cost_comparison import compare_broker_costs
from phantom.web.app import get_phantom, templates

router = APIRouter()


@router.get("/brokers/compare", response_class=HTMLResponse)
async def broker_comparison(request: Request, account: str | None = Query(None)):
    """Render the broker comparison page."""
    if not account:
        return templates.TemplateResponse(
            request=request,
            name="broker_comparison.html",
            context={
                "account": None,
                "comparison": None,
                "error": "account parameter is required",
            },
            status_code=400,
        )

    try:
        ph = get_phantom()

        # Get account
        try:
            account_obj = ph.accounts.get(account)
        except NotFoundError:
            return templates.TemplateResponse(
                request=request,
                name="broker_comparison.html",
                context={
                    "account": None,
                    "comparison": None,
                    "error": f"Account {account} not found",
                },
                status_code=404,
            )

        # Get all positions for the account
        positions = ph.positions.list(account_name=account_obj.name)

        # Get all broker profiles
        brokers = ph.brokers.list()
        profile_names = [b.name for b in brokers]

        if not profile_names:
            return templates.TemplateResponse(
                request=request,
                name="broker_comparison.html",
                context={
                    "account": account_obj,
                    "comparison": None,
                    "error": "No broker profiles available",
                },
            )

        # Compare broker costs
        comparison = compare_broker_costs(positions, profile_names, ph.brokers.get)

        # Find cheapest broker
        cheapest_broker = min(comparison.items(), key=lambda x: x[1].total_cost)[0]

        return templates.TemplateResponse(
            request=request,
            name="broker_comparison.html",
            context={
                "account": account_obj,
                "comparison": comparison,
                "cheapest_broker": cheapest_broker,
            },
        )

    except PhantomError as e:
        return templates.TemplateResponse(
            request=request,
            name="broker_comparison.html",
            context={
                "account": None,
                "comparison": None,
                "error": str(e),
            },
        )
