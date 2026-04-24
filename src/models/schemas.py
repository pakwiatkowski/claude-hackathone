from typing import Literal, Optional
from pydantic import BaseModel, Field, field_validator


class TicketClassification(BaseModel):
    priority: Literal["P1", "P2", "P3", "P4"]
    category: Literal[
        "password_reset",
        "network",
        "hardware",
        "software",
        "security_incident",
        "other",
    ]
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str = Field(min_length=10)
    auto_resolvable: bool

    @field_validator("confidence")
    @classmethod
    def confidence_precision(cls, v: float) -> float:
        return round(v, 4)


class RouteDecision(BaseModel):
    queue: Literal["tier1", "tier2", "networking", "security", "hardware"]
    escalate: bool
    escalation_reason: Optional[str] = None

    @field_validator("escalation_reason")
    @classmethod
    def reason_required_when_escalating(cls, v: Optional[str], info) -> Optional[str]:
        if info.data.get("escalate") and not v:
            raise ValueError("escalation_reason is required when escalate=True")
        return v


class ToolError(BaseModel):
    isError: bool = True
    reasonCode: str
    guidance: str


class CoordinatorResult(BaseModel):
    ticket_id: str
    priority: str
    category: str
    confidence: float
    queue: Optional[str]
    auto_resolved: bool
    escalated: bool
    escalation_reason: Optional[str]
    retry_count: int
    error_types: list[str]
    reasoning_chain: str


class SpecialistResult(BaseModel):
    ticket_id: str
    user_id: str
    success: bool
    escalate: bool
    escalation_reason: Optional[str] = None
    resolution_summary: Optional[str] = None
