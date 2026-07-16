"""
Data models for Komponist entities.
"""

from datetime import datetime
from enum import Enum
from typing import Optional, List
from uuid import uuid4

from pydantic import BaseModel, Field


class EntityType(str, Enum):
    """Brain entity types."""
    GOAL = "Goal"
    DECISION = "Decision"
    CONSTRAINT = "Constraint"
    CUSTOMER_REQUEST = "CustomerRequest"
    PROJECT = "Project"


class EntityStatus(str, Enum):
    """Entity lifecycle status."""
    PROPOSED = "proposed"
    CONFIRMED = "confirmed"
    SUPERSEDED = "superseded"
    REJECTED = "rejected"


class Confidence(str, Enum):
    """Extraction confidence level."""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class SourceType(str, Enum):
    """Evidence source types."""
    GITHUB = "github"
    SLACK = "slack"
    NOTION = "notion"
    GOOGLE = "google"
    LOCAL = "local"
    AGENT_REPORT = "agent_report"
    MANUAL = "manual"


class Entity(BaseModel):
    """Base brain entity."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    org_id: str
    entity_type: EntityType
    statement: str
    detail: Optional[str] = None
    status: EntityStatus = EntityStatus.PROPOSED
    confidence: Confidence = Confidence.MEDIUM
    embedding: Optional[List[float]] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    confirmed_at: Optional[datetime] = None
    confirmed_by: Optional[str] = None


class Evidence(BaseModel):
    """Evidence/provenance for entities."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    org_id: str
    source: SourceType
    reference: str  # e.g., "PR#842", "slack:C123/1720512345.0001"
    url: Optional[str] = None
    excerpt: str
    source_date: datetime
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Person(BaseModel):
    """Lightweight person node for owners/approvers."""
    id: str
    org_id: str
    name: str
    email: Optional[str] = None


class WorkPack(BaseModel):
    """Compiled execution package."""
    id: str = Field(default_factory=lambda: f"WP-{str(uuid4())[:8]}")
    org_id: str
    title: str
    objective: dict
    business_context: dict
    requirements: List[str]
    relevant_decisions: List[dict]
    constraints: List[dict]
    permissions: dict
    verification: List[str]
    status: str = "draft"
    created_at: datetime = Field(default_factory=datetime.utcnow)


class SourceItem(BaseModel):
    """Normalized source item for extraction."""
    org_id: str
    source: SourceType
    kind: str  # pr_merged, adr_file, issue, commit_batch, thread
    title: str
    body: str
    author: Optional[str] = None
    url: str
    reference: str
    source_date: datetime
    created_at: datetime = Field(default_factory=datetime.utcnow)
