class PhantomError(Exception):
    """Base class — never raise directly."""


class NotFoundError(PhantomError):
    def __init__(self, entity: str, identifier: str) -> None:
        self.entity = entity
        self.identifier = identifier
        super().__init__(f"{entity} not found: {identifier}")


class InsufficientFundsError(PhantomError):
    def __init__(self, account_id: str, required: float, available: float) -> None:
        self.account_id = account_id
        self.required = required
        self.available = available
        super().__init__(
            f"Insufficient funds in account '{account_id}': "
            f"required {required:.2f}, available {available:.2f}"
        )


class MarginError(PhantomError):
    def __init__(self, account_id: str, margin_level: float) -> None:
        self.account_id = account_id
        self.margin_level = margin_level
        super().__init__(f"Margin level {margin_level:.1%} in account '{account_id}'")


class ValidationError(PhantomError):
    def __init__(self, message: str) -> None:
        super().__init__(message)


class DataError(PhantomError):
    def __init__(self, message: str) -> None:
        super().__init__(message)


class ProfileError(PhantomError):
    def __init__(self, message: str) -> None:
        super().__init__(message)
