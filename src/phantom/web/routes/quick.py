from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse

from phantom.config import get_data_dir
from phantom.errors import NotFoundError, PhantomError
from phantom.utils.datetime import now_utc, parse_datetime, to_iso
from phantom.utils.ids import new_id
from phantom.web.app import get_phantom, templates

router = APIRouter()

logger = logging.getLogger(__name__)

# Whitelisted field names — prevents SQL injection via field parameter
_ORDER_FIELDS = frozenset({
    "created_at", "ticker", "instrument_type", "direction", "order_type",
    "quantity", "limit_price", "stop_price", "trailing_amount", "trailing_pct",
    "take_profit", "stop_loss", "fill_price", "good_til", "max_close_datetime",
})
_POSITION_FIELDS = frozenset({"entry_datetime", "exit_datetime"})

_DT_FIELDS = frozenset({
    "created_at", "good_til", "max_close_datetime", "triggered_at", "filled_at",
    "entry_datetime", "exit_datetime",
})
_FLOAT_FIELDS = frozenset({
    "quantity", "limit_price", "stop_price", "trailing_amount", "trailing_pct",
    "take_profit", "stop_loss", "fill_price",
})


@dataclass
class QuickRow:
    order_id: str
    created_at: Optional[datetime]
    ticker: str
    instrument_type: str
    direction: str
    order_type: str
    quantity: float
    limit_price: Optional[float]
    stop_price: Optional[float]
    trailing_amount: Optional[float]
    trailing_pct: Optional[float]
    take_profit: Optional[float]
    stop_loss: Optional[float]
    fill_price: Optional[float]
    good_til: Optional[datetime]
    max_close_datetime: Optional[datetime]
    status: str
    triggered_at: Optional[datetime]
    filled_at: Optional[datetime]
    rejection_reason: Optional[str]
    position_id: Optional[str]
    entry_datetime: Optional[datetime]
    entry_price: Optional[float]
    exit_datetime: Optional[datetime]
    exit_price: Optional[float]


def _load_quick_rows(
    conn: sqlite3.Connection, account_id: str, start_iso: str, end_iso: str
) -> list[QuickRow]:
    rows = conn.execute(
        """
        SELECT
            o.id AS order_id, o.created_at, o.ticker, o.instrument_type, o.direction,
            o.order_type, o.quantity, o.limit_price, o.stop_price, o.trailing_amount,
            o.trailing_pct, o.take_profit, o.stop_loss, o.fill_price, o.good_til,
            o.max_close_datetime, o.status, o.triggered_at, o.filled_at,
            o.rejection_reason, o.position_id,
            p.entry_datetime, p.entry_price, p.exit_datetime, p.exit_price
        FROM orders o
        LEFT JOIN positions p ON o.position_id = p.id
        WHERE o.account_id = ? AND o.created_at >= ? AND o.created_at <= ?
        ORDER BY o.created_at ASC
        """,
        (account_id, start_iso, end_iso),
    ).fetchall()

    result = []
    for r in rows:
        d = dict(r)
        for f in _DT_FIELDS:
            if d.get(f):
                d[f] = parse_datetime(d[f])
        result.append(QuickRow(**d))
    return result


def _known_tickers(conn: sqlite3.Connection, account_id: str) -> list[str]:
    return [
        r[0]
        for r in conn.execute(
            "SELECT DISTINCT ticker FROM orders WHERE account_id = ? ORDER BY ticker",
            (account_id,),
        ).fetchall()
    ]


def _parse_value(field: str, value: str):
    """Convert a raw form string into the appropriate Python/SQL type."""
    if value is None or value == "":
        return None
    if field in _FLOAT_FIELDS:
        try:
            return float(value)
        except ValueError:
            return None
    if field in _DT_FIELDS:
        # Accept "YYYY-MM-DD HH:mm" (space-separated) or "YYYY-MM-DDTHH:MM" (T-separated)
        value = value.strip().replace(" ", "T")
        if len(value) == 16:
            value = value + ":00"
        return value  # stored as ISO TEXT
    return value


def _default_range() -> tuple[str, str]:
    today = date.today()
    return (today - timedelta(days=30)).isoformat(), today.isoformat()


def _price_at(provider, ticker: str, dt: datetime) -> Optional[float]:
    try:
        bars = provider.get_bars(
            ticker, dt.date() - timedelta(days=10), dt.date() + timedelta(days=1)
        )
        if bars.empty:
            return None
        available = bars[bars.index <= dt]
        if available.empty:
            available = bars
        return float(available.iloc[-1]["Close"])
    except Exception:
        return None


def _recalculate(
    conn: sqlite3.Connection, account_id: str, start_iso: str, end_iso: str
) -> None:
    """Re-derive entry_price / exit_price / realized_pnl for all positions in range."""
    from phantom.data.yahoo import HistoricalProvider

    provider = HistoricalProvider(data_dir=str(get_data_dir()))
    rows = _load_quick_rows(conn, account_id, start_iso, end_iso)

    for row in rows:
        if not row.position_id:
            continue

        updates: dict = {}

        if row.entry_datetime:
            ep = _price_at(provider, row.ticker, row.entry_datetime)
            if ep is not None:
                updates["entry_price"] = ep

        if row.exit_datetime:
            xp = _price_at(provider, row.ticker, row.exit_datetime)
            if xp is not None:
                updates["exit_price"] = xp

        entry_price = updates.get("entry_price", row.entry_price)
        exit_price = updates.get("exit_price", row.exit_price)

        if entry_price is not None and exit_price is not None and row.quantity:
            dir_sign = 1 if row.direction == "long" else -1
            cost_row = conn.execute(
                """SELECT commission_entry, commission_exit, spread_cost, slippage_cost,
                          overnight_costs, fx_conversion_cost
                   FROM positions WHERE id = ?""",
                (row.position_id,),
            ).fetchone()
            total_costs = (
                sum(
                    (cost_row[k] or 0)
                    for k in [
                        "commission_entry",
                        "commission_exit",
                        "spread_cost",
                        "slippage_cost",
                        "overnight_costs",
                        "fx_conversion_cost",
                    ]
                )
                if cost_row
                else 0.0
            )
            updates["realized_pnl"] = (
                (exit_price - entry_price) * row.quantity * dir_sign - total_costs
            )

        if updates:
            set_clause = ", ".join(f"{k} = ?" for k in updates)
            conn.execute(
                f"UPDATE positions SET {set_clause} WHERE id = ?",
                [*updates.values(), row.position_id],
            )

    conn.commit()


def _template_ctx(
    account_obj,
    accounts,
    rows,
    tickers,
    start,
    end,
    extra=None,
) -> dict:
    ctx = {
        "account": account_obj,
        "accounts": accounts,
        "rows": rows,
        "tickers": tickers,
        "start": start,
        "end": end,
    }
    if extra:
        ctx.update(extra)
    return ctx


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/quick", response_class=HTMLResponse)
async def quick_page(
    request: Request,
    account: str | None = Query(None),
    start: str | None = Query(None),
    end: str | None = Query(None),
):
    default_start, default_end = _default_range()
    start = start or default_start
    end = end or default_end

    try:
        ph = get_phantom()
        accounts = ph.accounts.list()

        if not accounts:
            return templates.TemplateResponse(
                request=request,
                name="quick.html",
                context={"accounts": [], "account": None, "rows": [], "tickers": [],
                         "start": start, "end": end, "no_accounts": True},
            )

        try:
            account_obj = ph.accounts.get(account) if account else accounts[0]
        except NotFoundError:
            account_obj = accounts[0]

        start_iso = f"{start}T00:00:00"
        end_iso = f"{end}T23:59:59"
        rows = _load_quick_rows(ph._conn, account_obj.id, start_iso, end_iso)
        tickers = _known_tickers(ph._conn, account_obj.id)

        return templates.TemplateResponse(
            request=request,
            name="quick.html",
            context=_template_ctx(account_obj, accounts, rows, tickers, start, end,
                                  {"no_accounts": False}),
        )

    except PhantomError as e:
        return templates.TemplateResponse(
            request=request,
            name="quick.html",
            context={"accounts": [], "account": None, "rows": [], "tickers": [],
                     "start": start, "end": end, "error": str(e), "no_accounts": False},
        )


@router.get("/api/quick/rows", response_class=HTMLResponse)
async def quick_rows_fragment(
    request: Request,
    account: str = Query(...),
    start: str = Query(...),
    end: str = Query(...),
):
    ph = get_phantom()
    account_obj = ph.accounts.get(account)
    start_iso = f"{start}T00:00:00"
    end_iso = f"{end}T23:59:59"
    rows = _load_quick_rows(ph._conn, account_obj.id, start_iso, end_iso)
    tickers = _known_tickers(ph._conn, account_obj.id)
    return templates.TemplateResponse(
        request=request,
        name="_quick_rows.html",
        context=_template_ctx(account_obj, None, rows, tickers, start, end),
    )


@router.post("/api/quick/rebuild-equity")
async def rebuild_equity(
    account: str = Query(...),
):
    """Recompute daily mark-to-market equity snapshots from historical price data."""
    try:
        import pandas as pd
        from datetime import timezone
        from phantom.data.yahoo import HistoricalProvider
        from phantom.db.repositories.equity_repo import EquityRepo
        from phantom.models.equity_point import EquityPoint

        ph = get_phantom()
        account_obj = ph.accounts.get(account)

        all_pos = ph._conn.execute(
            """
            SELECT p.ticker, p.entry_datetime, p.exit_datetime,
                   p.entry_price, p.realized_pnl,
                   o.direction, o.quantity
            FROM positions p
            JOIN orders o ON o.position_id = p.id
            WHERE p.account_id = ?
            ORDER BY p.entry_datetime ASC
            """,
            (account_obj.id,),
        ).fetchall()

        if not all_pos:
            return JSONResponse({"status": "ok", "points": 0})

        positions = [
            {
                "ticker": r["ticker"],
                "entry_dt": parse_datetime(r["entry_datetime"]) if r["entry_datetime"] else None,
                "exit_dt": parse_datetime(r["exit_datetime"]) if r["exit_datetime"] else None,
                "entry_price": r["entry_price"],
                "realized_pnl": r["realized_pnl"] or 0.0,
                "direction": r["direction"],
                "quantity": r["quantity"] or 0.0,
            }
            for r in all_pos
        ]

        earliest = min(p["entry_dt"] for p in positions if p["entry_dt"])
        latest = max(
            (p["exit_dt"] or now_utc()) for p in positions if p["entry_dt"]
        )

        provider = HistoricalProvider(data_dir=str(get_data_dir()))
        active_tickers = {p["ticker"] for p in positions if p["entry_dt"]}

        price_series: dict[str, pd.Series] = {}
        for ticker in active_tickers:
            try:
                bars = provider.get_bars(
                    ticker,
                    earliest.date() - timedelta(days=1),
                    latest.date() + timedelta(days=1),
                )
                if not bars.empty:
                    price_series[ticker] = bars["Close"]
            except Exception:
                pass

        def _last_price(ticker: str, d) -> Optional[float]:
            series = price_series.get(ticker)
            if series is None:
                return None
            ts = pd.Timestamp(d)
            idx = series.index
            if idx.tz is not None:
                ts = ts.tz_localize(idx.tz)
            sub = series[idx.normalize() <= ts]
            return float(sub.iloc[-1]) if not sub.empty else None

        # Collect all trading days across all price series
        trading_dates: set = set()
        for series in price_series.values():
            for ts in series.index:
                d = ts.date() if hasattr(ts, "date") else ts
                if earliest.date() <= d <= latest.date():
                    trading_dates.add(d)

        initial = account_obj.initial_capital
        new_points: list[EquityPoint] = []

        for d in sorted(trading_dates):
            day_dt = datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
            equity = initial
            unrealized = 0.0
            for pos in positions:
                if pos["entry_dt"] is None or pos["entry_dt"].date() > d:
                    continue
                if pos["exit_dt"] and pos["exit_dt"].date() <= d:
                    equity += pos["realized_pnl"]
                else:
                    price = _last_price(pos["ticker"], d)
                    ep = pos["entry_price"]
                    if price is not None and ep is not None:
                        sign = 1 if pos["direction"] == "long" else -1
                        u = (price - ep) * pos["quantity"] * sign
                        unrealized += u
                        equity += u
            new_points.append(EquityPoint(
                account_id=account_obj.id,
                timestamp=to_iso(day_dt),
                equity=round(equity, 4),
                cash=account_obj.cash,
                unrealized_pnl=round(unrealized, 4),
            ))

        # Replace existing rows for this account
        ph._conn.execute("DELETE FROM equity_curve WHERE account_id = ?", (account_obj.id,))
        repo = EquityRepo(ph._conn)
        for pt in new_points:
            ph._conn.execute(
                "INSERT INTO equity_curve "
                "(id, account_id, timestamp, equity, cash, unrealized_pnl, used_margin, drawdown_pct) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (pt.id, pt.account_id, pt.timestamp, pt.equity,
                 pt.cash, pt.unrealized_pnl, pt.used_margin, pt.drawdown_pct),
            )
        ph._conn.commit()

        return JSONResponse({"status": "ok", "points": len(new_points)})
    except Exception as e:
        return JSONResponse({"status": "error", "detail": str(e)}, status_code=500)


@router.get("/api/quick/equity-data")
async def quick_equity_data(
    account: str = Query(...),
    start: str = Query(...),
    end: str = Query(...),
):
    try:
        from phantom.db.repositories.equity_repo import EquityRepo

        ph = get_phantom()
        account_obj = ph.accounts.get(account)
        start_dt = parse_datetime(f"{start}T00:00:00+00:00")
        end_dt = parse_datetime(f"{end}T23:59:59+00:00")

        all_points = EquityRepo(ph._conn).list(account_obj.id)
        visible = [
            p for p in all_points
            if start_dt <= parse_datetime(p.timestamp) <= end_dt
        ]

        equity_curve = [
            {"x": int(parse_datetime(p.timestamp).timestamp() * 1000), "y": p.equity}
            for p in visible
        ]

        # Entry/exit markers from positions in range, y-value interpolated from the curve
        all_pos = ph._conn.execute(
            """
            SELECT p.ticker, p.entry_datetime, p.exit_datetime, p.realized_pnl,
                   o.direction
            FROM positions p
            JOIN orders o ON o.position_id = p.id
            WHERE p.account_id = ?
            ORDER BY p.entry_datetime ASC
            """,
            (account_obj.id,),
        ).fetchall()

        def _equity_at(dt: datetime) -> Optional[float]:
            ms = int(dt.timestamp() * 1000)
            val = None
            for pt in equity_curve:
                if pt["x"] <= ms:
                    val = pt["y"]
                else:
                    break
            return val

        markers = []
        for r in all_pos:
            entry_dt = parse_datetime(r["entry_datetime"]) if r["entry_datetime"] else None
            exit_dt = parse_datetime(r["exit_datetime"]) if r["exit_datetime"] else None

            if entry_dt and start_dt <= entry_dt <= end_dt:
                y = _equity_at(entry_dt)
                if y is not None:
                    markers.append({
                        "x": int(entry_dt.timestamp() * 1000),
                        "y": y,
                        "ticker": r["ticker"],
                        "type": "entry",
                        "direction": r["direction"],
                    })

            if exit_dt and start_dt <= exit_dt <= end_dt:
                y = _equity_at(exit_dt)
                if y is not None:
                    markers.append({
                        "x": int(exit_dt.timestamp() * 1000),
                        "y": y,
                        "ticker": r["ticker"],
                        "type": "exit",
                        "direction": r["direction"],
                        "pnl": r["realized_pnl"] or 0.0,
                    })

        return JSONResponse({"equity_curve": equity_curve, "markers": markers})
    except Exception:
        return JSONResponse({"equity_curve": [], "markers": []})


@router.put("/api/quick/row/{order_id}", response_class=HTMLResponse)
async def update_quick_row(order_id: str, request: Request):
    form = await request.form()
    field = form.get("field", "")
    account = form.get("account", "")
    start = form.get("start", "")
    end = form.get("end", "")
    value = form.get(field) if field else None

    ph = get_phantom()

    if field and field in (_ORDER_FIELDS | _POSITION_FIELDS):
        parsed = _parse_value(field, value)
        try:
            if field in _ORDER_FIELDS:
                ph._conn.execute(
                    f"UPDATE orders SET {field} = ? WHERE id = ?",
                    (parsed, order_id),
                )
                if field == "created_at":
                    pos = ph._conn.execute(
                        "SELECT position_id FROM orders WHERE id = ?", (order_id,)
                    ).fetchone()
                    if pos and pos["position_id"]:
                        ph._conn.execute(
                            "UPDATE positions SET entry_datetime = ? WHERE id = ?",
                            (parsed, pos["position_id"]),
                        )
            else:  # position field
                pos = ph._conn.execute(
                    "SELECT position_id FROM orders WHERE id = ?", (order_id,)
                ).fetchone()
                if pos and pos["position_id"]:
                    ph._conn.execute(
                        f"UPDATE positions SET {field} = ? WHERE id = ?",
                        (parsed, pos["position_id"]),
                    )
            ph._conn.commit()
        except Exception:
            pass

    account_obj = ph.accounts.get(account)
    start_iso = f"{start}T00:00:00"
    end_iso = f"{end}T23:59:59"
    _recalculate(ph._conn, account_obj.id, start_iso, end_iso)
    rows = _load_quick_rows(ph._conn, account_obj.id, start_iso, end_iso)
    tickers = _known_tickers(ph._conn, account_obj.id)

    response = templates.TemplateResponse(
        request=request,
        name="_quick_rows.html",
        context=_template_ctx(account_obj, None, rows, tickers, start, end),
    )
    response.headers["HX-Trigger"] = "equityRefresh"
    return response


@router.delete("/api/quick/row/{order_id}", response_class=HTMLResponse)
async def delete_quick_row(
    order_id: str,
    request: Request,
    account: str = Query(...),
    start: str = Query(...),
    end: str = Query(...),
):
    ph = get_phantom()
    try:
        row = ph._conn.execute(
            "SELECT position_id FROM orders WHERE id = ?", (order_id,)
        ).fetchone()
        position_id = row["position_id"] if row else None
        # Break the circular FK (orders.position_id → positions, positions.entry_order_id → orders)
        # before deleting either row.
        ph._conn.execute("UPDATE orders SET position_id = NULL WHERE id = ?", (order_id,))
        if position_id:
            ph._conn.execute("DELETE FROM positions WHERE id = ?", (position_id,))
        ph._conn.execute("DELETE FROM orders WHERE id = ?", (order_id,))
        ph._conn.commit()
    except Exception:
        logger.exception("Failed to delete order %s", order_id)

    account_obj = ph.accounts.get(account)
    start_iso = f"{start}T00:00:00"
    end_iso = f"{end}T23:59:59"
    rows = _load_quick_rows(ph._conn, account_obj.id, start_iso, end_iso)
    tickers = _known_tickers(ph._conn, account_obj.id)

    response = templates.TemplateResponse(
        request=request,
        name="_quick_rows.html",
        context=_template_ctx(account_obj, None, rows, tickers, start, end),
    )
    response.headers["HX-Trigger"] = "equityRefresh"
    return response


@router.post("/api/quick/order", response_class=HTMLResponse)
async def create_quick_order(request: Request):
    form = await request.form()
    account = form.get("account", "")
    start = form.get("start", "")
    end = form.get("end", "")
    ticker = (form.get("ticker") or "").upper().strip()
    direction = form.get("direction") or "long"
    order_type = form.get("order_type") or "market"
    try:
        quantity = float(form.get("quantity") or 0)
    except ValueError:
        quantity = 0.0

    ph = get_phantom()
    account_obj = ph.accounts.get(account)

    if ticker and direction and order_type and quantity > 0:
        order_id = new_id()
        created_iso = to_iso(now_utc())

        entry_datetime_raw = (form.get("entry_datetime") or "").strip()
        exit_datetime_raw  = (form.get("exit_datetime") or "").strip()

        entry_iso = _parse_value("entry_datetime", entry_datetime_raw) if entry_datetime_raw else None
        exit_iso  = _parse_value("exit_datetime",  exit_datetime_raw)  if exit_datetime_raw  else None

        # Insert the order first (position_id set to NULL until position is created)
        ph._conn.execute(
            """INSERT INTO orders
               (id, account_id, ticker, instrument_type, direction, order_type,
                quantity, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (order_id, account_obj.id, ticker, "stock", direction, order_type,
             quantity, "pending", created_iso),
        )

        if entry_iso:
            from phantom.data.yahoo import HistoricalProvider
            provider = HistoricalProvider(data_dir=str(get_data_dir()))

            entry_price: Optional[float] = None
            exit_price:  Optional[float] = None

            try:
                entry_dt = parse_datetime(entry_iso)
                entry_price = _price_at(provider, ticker, entry_dt)
            except Exception:
                pass

            if exit_iso:
                try:
                    exit_dt = parse_datetime(exit_iso)
                    exit_price = _price_at(provider, ticker, exit_dt)
                except Exception:
                    pass

            realized_pnl: Optional[float] = None
            if entry_price is not None and exit_price is not None:
                dir_sign = 1 if direction == "long" else -1
                realized_pnl = (exit_price - entry_price) * quantity * dir_sign

            position_id = new_id()
            position_status = "closed" if exit_iso else "open"
            # entry_price NOT NULL — use 0.0 as fallback when price cache has no data
            ep_stored = entry_price if entry_price is not None else 0.0
            notional = ep_stored * quantity

            ph._conn.execute(
                """INSERT INTO positions
                   (id, account_id, ticker, instrument_type, direction,
                    entry_order_id, entry_price, entry_datetime, quantity, notional,
                    exit_price, exit_datetime, realized_pnl,
                    status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (position_id, account_obj.id, ticker, "stock", direction,
                 order_id, ep_stored, entry_iso, quantity, notional,
                 exit_price, exit_iso, realized_pnl,
                 position_status, created_iso),
            )

            ph._conn.execute(
                "UPDATE orders SET status = 'filled', position_id = ? WHERE id = ?",
                (position_id, order_id),
            )

        ph._conn.commit()

    start_iso = f"{start}T00:00:00"
    end_iso = f"{end}T23:59:59"
    rows = _load_quick_rows(ph._conn, account_obj.id, start_iso, end_iso)
    tickers = _known_tickers(ph._conn, account_obj.id)

    response = templates.TemplateResponse(
        request=request,
        name="_quick_rows.html",
        context=_template_ctx(account_obj, None, rows, tickers, start, end),
    )
    response.headers["HX-Trigger"] = "equityRefresh"
    return response
