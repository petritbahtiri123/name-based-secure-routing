from __future__ import annotations

from nbsr.protocol.registry import ErrorCode


class ProtocolViolation(ValueError):
    def __init__(
        self,
        code: ErrorCode,
        message: str = "Invalid NBSR protocol data",
    ) -> None:
        if not isinstance(code, ErrorCode):
            raise TypeError("code must be an ErrorCode")
        super().__init__(message)
        self.code = code


class InvalidTransition(ProtocolViolation):
    def __init__(self) -> None:
        super().__init__(
            ErrorCode.NBSR_E_INTERNAL,
            "Invalid NBSR state transition",
        )
