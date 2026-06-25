from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from phantom.api.client import Phantom
from phantom.config import get_data_dir

_HERE = Path(__file__).parent


def get_phantom() -> Phantom:
    """Get Phantom instance with data directory from environment."""
    return Phantom(data_dir=str(get_data_dir()))


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(title="Phantom Ledger")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost", "http://127.0.0.1"],
        allow_origin_regex=r"http://localhost:\d+",
        allow_methods=["*"],
        allow_headers=["*"],
    )

    static_dir = _HERE / "static"
    static_dir.mkdir(exist_ok=True)
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    # Register routers
    from phantom.web.routes import api as api_routes
    from phantom.web.routes import brokers, clock, dashboard, orders, positions, simulation

    app.include_router(dashboard.router)
    app.include_router(clock.router)
    app.include_router(positions.router)
    app.include_router(orders.router)
    app.include_router(brokers.router)
    app.include_router(simulation.router)
    app.include_router(api_routes.router)

    return app


templates = Jinja2Templates(directory=_HERE / "templates")
