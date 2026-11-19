from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class SessionUsage:
    session_id: str
    title: str | None
    directory: str
    model: str | None
    created_at_ms: int
    input_tokens: int
    output_tokens: int
    reasoning_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    cost: float
    provider: str | None = None

    @property
    def cache_hit_rate(self) -> float | None:
        denominator = self.cache_read_tokens + self.input_tokens
        return self.cache_read_tokens / denominator if denominator else None

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["cache_hit_rate"] = self.cache_hit_rate
        return result
