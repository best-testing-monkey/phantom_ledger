import pytest

from phantom.db.repositories.broker_repo import BrokerRepo
from phantom.engine.margin_engine import MarginEngine
from phantom.models.account import Account
from phantom.models.broker import (
    BrokerProfile,
    CommissionModel,
    DividendModel,
    MarginModel,
    OvernightModel,
    SlippageModel,
    SpreadModel,
    TradingHoursConfig,
)
from phantom.models.position import Position
from phantom.utils.datetime import now_utc


def _cfd_position(margin_required: float) -> Position:
    return Position(
        account_id="test-account-1",
        ticker="TEST",
        instrument_type="cfd",
        direction="long",
        entry_order_id="order-1",
        entry_price=100.0,
        entry_datetime=now_utc(),
        quantity=1.0,
        notional=100.0,
        margin_required=margin_required,
    )


def _stock_position(notional: float) -> Position:
    """Stock position: full notional debited as cash at entry, no real
    margin exposure — margin_required defaults to 0.0, matching what
    OrderManager.handle_fill() sets for instrument_type == 'stock'.
    """
    return Position(
        account_id="test-account-1",
        ticker="STOCK",
        instrument_type="stock",
        direction="long",
        entry_order_id="order-2",
        entry_price=100.0,
        entry_datetime=now_utc(),
        quantity=notional / 100.0,
        notional=notional,
    )


@pytest.fixture
def cfd_broker_profile():
    """Broker profile with CFD margin settings."""
    return BrokerProfile(
        name="CFD_BROKER",
        commission=CommissionModel(model_type="fixed", fixed_fee=1.0),
        spread=SpreadModel(model_type="fixed", fixed_spread_pct=0.0005),
        slippage=SlippageModel(model_type="fixed_pct", fixed_pct=0.0003),
        overnight=OvernightModel(
            long_markup_pct=0.0,
            short_markup_pct=0.0,
            day_divisor=365,
            rate_source="manual",
            manual_rate=0.0,
        ),
        margin=MarginModel(
            default_margin_pct=0.05,  # 5% default margin
            margin_call_level=100.0,  # 100%
            stop_out_level=50.0,  # 50%
        ),
        dividend=DividendModel(
            withholding_rates={"US": 0.15},
            cfd_dividend_adjustment=1.0,
            cfd_short_dividend_charge=1.0,
        ),
        fx_conversion_pct=0.0025,
        fx_base_currency="EUR",
        min_order_size=1.0,
        max_leverage=20.0,
        trading_hours=TradingHoursConfig(
            timezone="America/New_York",
            open="09:30",
            close="16:00",
            pre_market=False,
            post_market=False,
        ),
        supported_instruments=["cfd", "stock"],
    )


@pytest.fixture
def margin_engine():
    """Create a MarginEngine instance."""
    return MarginEngine()


@pytest.fixture
def test_account(cfd_broker_profile, db_conn):
    """Create a test account with broker profile."""
    # Create broker profile first to get its ID
    broker_repo = BrokerRepo(db_conn)
    broker_repo.create(cfd_broker_profile)
    broker_id = broker_repo.get_id_by_name(cfd_broker_profile.name)

    return Account(
        id="test-account-1",
        name="Test Account",
        account_type="manual",
        broker_profile_id=broker_id,
        base_currency="EUR",
        initial_capital=10000.0,
        cash=10000.0,
    )


class TestMarginEngineCheck:
    """Tests for MarginEngine.check()"""

    def test_check_ok_status(self, margin_engine, test_account, cfd_broker_profile):
        """Test margin status is 'ok' when margin level is above margin_call_level."""
        # Account has 10000 EUR, open position market value is 50000 EUR
        # used_margin = sum(margin_required) = 50000 * 0.05 = 2500 EUR
        # level = (10000 / 2500) * 100 = 400%
        # Status should be 'ok' since 400 > 100 (margin_call_level)
        status = margin_engine.check(
            test_account,
            cfd_broker_profile,
            [_cfd_position(50000.0 * cfd_broker_profile.margin.default_margin_pct)],
        )

        assert status.status == "ok"
        assert status.level == 400.0
        assert status.margin_call_level == 100.0
        assert status.stop_out_level == 50.0

    def test_check_margin_call_status(self, margin_engine, test_account, cfd_broker_profile):
        """Test margin status is 'margin_call' when level is between thresholds."""
        # Account has 10000 EUR, open position market value is 250000 EUR
        # used_margin = sum(margin_required) = 250000 * 0.05 = 12500 EUR
        # level = (10000 / 12500) * 100 = 80%
        # Status should be 'margin_call' since 80 is between 100 and 50
        status = margin_engine.check(
            test_account,
            cfd_broker_profile,
            [_cfd_position(250000.0 * cfd_broker_profile.margin.default_margin_pct)],
        )

        assert status.status == "margin_call"
        assert 50.0 < status.level < 100.0  # Approximately 80%

    def test_check_stop_out_status(self, margin_engine, test_account, cfd_broker_profile):
        """Test margin status is 'stop_out' when level is below stop_out_level."""
        # Account has 10000 EUR, open position market value is 500000 EUR
        # used_margin = sum(margin_required) = 500000 * 0.05 = 25000 EUR
        # level = (10000 / 25000) * 100 = 40%
        # Status should be 'stop_out' since 40 <= 50
        status = margin_engine.check(
            test_account,
            cfd_broker_profile,
            [_cfd_position(500000.0 * cfd_broker_profile.margin.default_margin_pct)],
        )

        assert status.status == "stop_out"
        assert status.level == 40.0

    def test_check_zero_margin_infinity_level(
        self, margin_engine, test_account, cfd_broker_profile
    ):
        """Test margin level is infinity when no margin is used."""
        # No open positions
        status = margin_engine.check(test_account, cfd_broker_profile, [])

        assert status.status == "ok"
        assert status.level == float("inf")

    def test_check_low_cash_high_leverage_stop_out(self, margin_engine, cfd_broker_profile):
        """Test stop-out with reduced account cash."""
        # Account with only 2000 EUR
        account = Account(
            id="test-account-low-cash",
            name="Low Cash Account",
            account_type="manual",
            broker_profile_id="cfd_broker",
            base_currency="EUR",
            initial_capital=10000.0,
            cash=2000.0,
        )
        # Open position market value is 100000 EUR
        # used_margin = sum(margin_required) = 100000 * 0.05 = 5000 EUR
        # level = (2000 / 5000) * 100 = 40%
        # Status should be 'stop_out'
        status = margin_engine.check(
            account,
            cfd_broker_profile,
            [_cfd_position(100000.0 * cfd_broker_profile.margin.default_margin_pct)],
        )

        assert status.status == "stop_out"
        assert status.level == 40.0

    def test_check_ignores_stock_position_margin(
        self, margin_engine, test_account, cfd_broker_profile
    ):
        """Stock positions must never contribute to used_margin, even when
        their notional dwarfs the CFD position's — check() should produce
        the identical result whether the stock position is present or not.
        """
        cfd_position = _cfd_position(2500.0)
        stock_position = _stock_position(notional=100000.0)

        status_with_stock = margin_engine.check(
            test_account, cfd_broker_profile, [stock_position, cfd_position]
        )
        status_cfd_only = margin_engine.check(test_account, cfd_broker_profile, [cfd_position])

        assert status_with_stock.level == status_cfd_only.level
        assert status_with_stock.status == status_cfd_only.status
        # used_margin = 2500 (CFD only); level = (10000 / 2500) * 100 = 400%
        assert status_with_stock.level == 400.0
        assert status_with_stock.status == "ok"


class TestMarginCallWarning:
    """Tests for MarginEngine.handle_margin_call()"""

    def test_margin_call_warning_sets_timestamp(
        self, margin_engine, test_account, cfd_broker_profile, db_conn
    ):
        """Test that margin_call_at is set exactly once on first call."""
        from phantom.db.repositories.account_repo import AccountRepo

        account_repo = AccountRepo(db_conn)
        account_repo.create(test_account)

        # Create margin status in warning range
        # used_margin = sum(margin_required) = 250000 * 0.05 = 12500 EUR
        status = margin_engine.check(
            test_account,
            cfd_broker_profile,
            [_cfd_position(250000.0 * cfd_broker_profile.margin.default_margin_pct)],
        )
        assert status.status == "margin_call"

        # First call should set margin_call_at
        margin_engine.handle_margin_call(test_account, status, account_repo)
        assert test_account.margin_call_at is not None
        first_timestamp = test_account.margin_call_at

        # Get the persisted account
        persisted = account_repo.get(test_account.id)
        assert persisted.margin_call_at == first_timestamp

        # Second call should NOT change margin_call_at (idempotent)
        margin_engine.handle_margin_call(test_account, status, account_repo)
        assert test_account.margin_call_at == first_timestamp

    def test_margin_call_warning_with_dispatcher(
        self, margin_engine, test_account, cfd_broker_profile, db_conn
    ):
        """Test that margin_call event is emitted when dispatcher is provided."""
        from phantom.db.repositories.account_repo import AccountRepo

        account_repo = AccountRepo(db_conn)
        account_repo.create(test_account)

        class MockDispatcher:
            def __init__(self):
                self.events = []

            def emit(self, event_type, payload):
                self.events.append((event_type, payload))

        dispatcher = MockDispatcher()
        # used_margin = sum(margin_required) = 250000 * 0.05 = 12500 EUR
        status = margin_engine.check(
            test_account,
            cfd_broker_profile,
            [_cfd_position(250000.0 * cfd_broker_profile.margin.default_margin_pct)],
        )

        margin_engine.handle_margin_call(test_account, status, account_repo, dispatcher=dispatcher)

        assert len(dispatcher.events) == 1
        assert dispatcher.events[0][0] == "margin_warning"
        assert dispatcher.events[0][1]["account_id"] == test_account.id


class TestHandleStopOut:
    """Tests for MarginEngine.handle_stop_out().

    handle_stop_out() only reads account.cash/account.id and calls
    position_manager.close() (which itself only calls cost_engine.exit_costs
    and returns a model_copy — no DB access at all), so these tests use a
    real PositionManager/CostEngine pair but pass position_repo=None and
    account_repo=None: nothing in the code path under test touches either.
    """

    def _position_manager(self, broker_profile):
        from phantom.costs.engine import CostEngine
        from phantom.engine.position_manager import PositionManager

        cost_engine = CostEngine(broker_profile)
        return PositionManager(position_repo=None, account_repo=None, cost_engine=cost_engine)

    def test_stock_position_never_liquidated(self, margin_engine, cfd_broker_profile):
        """A stock position must never be included in the stop-out cascade,
        even when the account is in stop_out driven purely by a CFD position.
        """
        account = Account(
            id="test-account-mixed",
            name="Mixed Account",
            account_type="manual",
            broker_profile_id="cfd_broker",
            base_currency="EUR",
            initial_capital=10000.0,
            cash=2000.0,
        )
        cfd_position = _cfd_position(margin_required=5000.0)
        stock_position = _stock_position(notional=100000.0)

        position_manager = self._position_manager(cfd_broker_profile)
        last_close = {"TEST": 100.0, "STOCK": 100.0}

        # used_margin = 5000 (CFD only, stock never contributes)
        # level = (2000 / 5000) * 100 = 40% <= 50 (stop_out_level) -> stop-out
        closed = margin_engine.handle_stop_out(
            account=account,
            open_positions=[stock_position, cfd_position],
            broker_profile=cfd_broker_profile,
            current_bar_timestamp=now_utc(),
            position_manager=position_manager,
            account_repo=None,
            last_close=last_close,
        )

        closed_ids = [p.id for p in closed]
        assert stock_position.id not in closed_ids
        assert cfd_position.id in closed_ids

    def test_closes_largest_loss_first(self, margin_engine, cfd_broker_profile):
        """When multiple CFD positions are stop-out candidates, the position
        with the largest unrealized loss is closed first (and, in this
        scenario, closed before the account recovers above stop_out_level).
        """
        account = Account(
            id="test-account-order",
            name="Order Test Account",
            account_type="manual",
            broker_profile_id="cfd_broker",
            base_currency="EUR",
            initial_capital=10000.0,
            cash=100.0,
        )

        position_a = Position(
            account_id=account.id,
            ticker="AAA",
            instrument_type="cfd",
            direction="long",
            entry_order_id="order-a",
            entry_price=100.0,
            entry_datetime=now_utc(),
            quantity=10.0,
            notional=1000.0,
            margin_required=1000.0,
        )
        position_b = Position(
            account_id=account.id,
            ticker="BBB",
            instrument_type="cfd",
            direction="long",
            entry_order_id="order-b",
            entry_price=100.0,
            entry_datetime=now_utc(),
            quantity=10.0,
            notional=1000.0,
            margin_required=1000.0,
        )
        # position_a has the larger unrealized loss (-200) vs position_b (-50)
        last_close = {"AAA": 80.0, "BBB": 95.0}

        position_manager = self._position_manager(cfd_broker_profile)

        # used_margin (both) = 2000; level = (100 / 2000) * 100 = 5% -> stop-out.
        # After closing A: used_margin = 1000 (B only); level = 10% -> still
        # stop-out, so B closes too. Passing positions out of loss order
        # (b, a) in open_positions to prove the sort, not insertion order,
        # determines close sequence.
        closed = margin_engine.handle_stop_out(
            account=account,
            open_positions=[position_b, position_a],
            broker_profile=cfd_broker_profile,
            current_bar_timestamp=now_utc(),
            position_manager=position_manager,
            account_repo=None,
            last_close=last_close,
        )

        assert [p.id for p in closed] == [position_a.id, position_b.id]
