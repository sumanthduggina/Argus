# Folder: firetiger-demo/ingestion/event_schema.py
# 
# These are the core data models used EVERYWHERE in the project.
# Every other file imports from here.
# Build these first before anything else.

from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List
import uuid


class EventSchema(BaseModel):
    """
    One EventSchema object is created for EVERY request to the Flask app.
    The middleware builds this automatically - route handlers never touch it.
    
    This flows like:
    Flask request → middleware captures → EventSchema built → sent to collector
    """
    
    # When the request happened
    timestamp: datetime = Field(default_factory=datetime.now)
    
    # Which route was hit
    endpoint: str                    # e.g. "/checkout"
    method: str                      # e.g. "GET"
    status_code: int                 # e.g. 200, 500
    
    # Performance metrics - this is what we watch for regressions
    latency_ms: float                # total request time in milliseconds
    db_query_count: int              # how many DB queries fired during request
    db_query_time_ms: float          # total time spent in database
    
    # Who made the request - for customer-level tracking
    user_id: str                     # UUID of the customer
    session_id: str                  # their session
    
    # System health
    memory_mb: float                 # process memory at time of request
    
    # This is CRITICAL - ties every event to a specific deploy
    # When regression detected, we know exactly which commit caused it
    commit_sha: str
    
    # Only populated when something went wrong
    error_message: Optional[str] = None


class RegressionEvent(BaseModel):
    """
    Built by the detector when it confirms a regression.
    Passed to the agent orchestrator to kick off investigation.
    
    Contains everything the agent needs to start investigating
    without having to re-query the database.
    """
    
    # What endpoint is affected
    affected_endpoint: str
    
    # How bad is it (standard deviations from normal)
    anomaly_score: float
    
    # Before/after comparison
    latency_before_ms: float         # normal baseline latency
    latency_after_ms: float          # current broken latency
    query_count_before: float        # normal query count
    query_count_after: float         # current query count
    
    # Which commit introduced this - key for git diff investigation
    commit_sha: str
    
    # Which customers are feeling this pain
    affected_user_ids: List[str]
    
    # When the regression started
    detected_at: datetime = Field(default_factory=datetime.now)
    
    # Unique ID for this incident
    incident_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])


class Hypothesis(BaseModel):
    """
    One hypothesis from the agent about what caused the regression.
    The hypothesize step returns a list of 3 of these.
    """
    rank: int                        # 1 = most likely
    title: str                       # short name e.g. "N+1 Query Problem"
    description: str                 # detailed explanation
    confidence_score: float          # 0.0 to 1.0
    supporting_signals: List[str]    # observations that support this
    evidence_needed: List[str]       # what data would confirm this
    similar_past_incident_id: Optional[int] = None


class Characterization(BaseModel):
    """
    Built by the characterize step - pure data, no Claude involved.
    Describes exactly what is happening before we try to explain why.
    """
    affected_endpoint: str
    all_endpoints_affected: bool     # true = infra problem, false = code problem
    affected_user_ids: List[str]
    regression_start_time: datetime
    commit_sha: str
    
    latency_before_ms: float
    latency_after_ms: float
    latency_multiplier: float        # e.g. 56.7x slower
    
    query_count_before: float
    query_count_after: float
    query_multiplier: float
    
    db_time_before_ms: float
    db_time_after_ms: float
    
    memory_before_mb: float
    memory_after_mb: float


class RootCause(BaseModel):
    """
    The agent's confirmed conclusion after examining all evidence.
    """
    confirmed_hypothesis_title: str
    confidence_score: float
    evidence_chain: List[str]        # step by step reasoning
    affected_code_location: str      # file + function name
    affected_code_snippet: str       # the actual bad code


class FixPackage(BaseModel):
    """
    Everything needed to fix the problem and open a PR.
    """
    fix_summary: str
    original_code: str               # exact code to replace
    fixed_code: str                  # the replacement
    explanation: str
    risk_level: str                  # "low", "medium", "high"
    risk_reasoning: str
    side_effects: List[str]
    rollback_instructions: str
    verification_checklist: List[str]
    pr_title: str
    pr_description: str


class IncidentReport(BaseModel):
    """
    The complete record of one incident from detection to resolution.
    Saved to knowledge graph when incident closes.
    """
    incident_id: str
    regression: RegressionEvent
    characterization: Characterization
    hypotheses: List[Hypothesis]
    root_cause: RootCause
    fix: FixPackage
    
    # Filled in after resolution
    resolved: bool = False
    resolved_at: Optional[datetime] = None
    time_to_detect_sec: Optional[float] = None
    time_to_resolve_sec: Optional[float] = None