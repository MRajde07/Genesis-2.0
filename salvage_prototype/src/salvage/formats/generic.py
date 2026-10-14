"""Conservative fallback for inputs not claimed by a known plugin."""
from .base import FormatPlugin, Result


class GenericPlugin(FormatPlugin):
    name = "UNKNOWN"

    def detect(self, data: bytes) -> float:
        # Fallback is eligible for every input, but has no format evidence.
        return 0.01

    def decode(self, data: bytes) -> Result:
        return Result(format="UNKNOWN", status="unsupported")
