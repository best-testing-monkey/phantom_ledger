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
        # used_margin = 50000 * 0.05 = 2500 EUR
        # level = (10000 / 2500) * 100 = 400%
        # Status should be 'ok' since 400 > 100 (margin_call_level)
        status = margin_engine.check(test_account, cfd_broker_profile, 50000.0)

        assert status.status == "ok"
        assert status.level == 400.0
        assert status.margin_call_level == 100.0
        assert status.stop_out_level == 50.0

    def test_check_margin_call_status(self, margin_engine, test_account, cfd_broker_profile):
        """Test margin status is 'margin_call' when level is between thresholds."""
        # Account has 10000 EUR, open position market value is 250000 EUR
        # used_margin = 250000 * 0.05 = 12500 EUR
        # level = (10000 / 12500) * 100 = 80%
        # Status should be 'margin_call' since 80 is between 100 and 50
        status = margin_engine.check(test_account, cfd_broker_profile, 250000.0)

        assert status.status == "margin_call"
        assert 50.0 < status.level < 100.0  # Approximately 80%

    def test_check_stop_out_status(self, margin_engine, test_account, cfd_broker_profile):
        """Test margin status is 'stop_out' when level is below stop_out_level."""
        # Account has 10000 EUR, open position market value is 500000 EUR
        # used_margin = 500000 * 0.05 = 25000 EUR
        # level = (10000 / 25000) * 100 = 40%
        # Status should be 'stop_out' since 40 <= 50
        status = margin_engine.check(test_account, cfd_broker_profile, 500000.0)

        assert status.status == "stop_out"
        assert status.level == 40.0

    def test_check_zero_margin_infinity_level(
        self, margin_engine, test_account, cfd_broker_profile
    ):
        """Test margin level is infinity when no margin is used."""
        # No open positions
        status = margin_engine.check(test_account, cfd_broker_profile, 0.0)

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
        # used_margin = 100000 * 0.05 = 5000 EUR
        # level = (2000 / 5000) * 100 = 40%
        # Status should be 'stop_out'
        status = margin_engine.check(account, cfd_broker_profile, 100000.0)

        assert status.status == "stop_out"
        assert status.level == 40.0


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
        status = margin_engine.check(test_account, cfd_broker_profile, 250000.0)
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
        status = margin_engine.check(test_account, cfd_broker_profile, 250000.0)

        margin_engine.handle_margin_call(test_account, status, account_repo, dispatcher=dispatcher)

        assert len(dispatcher.events) == 1
        assert dispatcher.events[0][0] == "margin_warning"
        assert dispatcher.events[0][1]["account_id"] == test_account.id
        assert dispatcher.events[0][1]["margin_level"] > 0
