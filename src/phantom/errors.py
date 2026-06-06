class PhantomError(Exception):
    """Base exception for all Phantom Ledger errors."""


class NotFoundError(PhantomError):
    def __init__(self, entity_type: str, identifier: str):
        self.entity_type = entity_type
        self.identifier = identifier
        super().__init__(f"{entity_type} not found: {identifier}")


class InsufficientFundsError(PhantomError):
    def __init__(self, account_id: str, required: float, available: float):
        self.account_id = account_id
        self.required = required
        self.available = available
        super().__init__(
            f"Insufficient funds in {account_id}: need {required:.2f}, have {available:.2f}"
        )


class MarginError(PhantomError):
    pass


class ValidationError(PhantomError):
    pass


class DataError(PhantomError):
    pass


class ProfileError(PhantomError):
    pass
