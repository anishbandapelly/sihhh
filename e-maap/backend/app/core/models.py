from datetime import datetime, timezone
from uuid import uuid4
import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB
from .db import Base
from .enums import *

def now(): return datetime.now(timezone.utc)
def uid(): return str(uuid4())
JSON = sa.JSON().with_variant(JSONB(), 'postgresql')
UUID = sa.Uuid(as_uuid=False)
def enum(cls): return sa.Enum(cls, name=cls.__name__.lower(), validate_strings=True)
def pk(): return mapped_column(UUID, primary_key=True, default=uid)
def fk(table, nullable=False): return mapped_column(UUID, sa.ForeignKey(table + '.id'), nullable=nullable)
def timecol(): return mapped_column(sa.DateTime(timezone=True), default=now, nullable=False)

class User(Base):
    __tablename__ = 'users'
    id: Mapped[str] = pk()
    name: Mapped[str] = mapped_column(sa.String(160))
    email: Mapped[str] = mapped_column(sa.String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(sa.Text)
    role: Mapped[Role] = mapped_column(enum(Role))
    active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = timecol()

class Case(Base):
    __tablename__ = 'cases'
    id: Mapped[str] = pk()
    case_type: Mapped[CaseType] = mapped_column(enum(CaseType))
    source: Mapped[str] = mapped_column(sa.String(80))
    status: Mapped[CaseStatus] = mapped_column(enum(CaseStatus), default=CaseStatus.INTAKE)
    priority_band: Mapped[str] = mapped_column(sa.String(16), default='NORMAL')
    priority_reasons: Mapped[dict] = mapped_column(JSON, default=dict)
    parent_case_id: Mapped[str | None] = fk('cases', True)
    shop_name: Mapped[str] = mapped_column(sa.String(200), default='')
    shop_location: Mapped[dict] = mapped_column(JSON, default=dict)
    citizen_session_id: Mapped[str | None] = mapped_column(UUID, nullable=True, index=True)
    public_tracking_token_hash: Mapped[str | None] = mapped_column(sa.String(64), nullable=True)
    created_at: Mapped[datetime] = timecol()
    updated_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), default=now, onupdate=now)
    __table_args__ = (sa.Index('ix_case_queue', 'status', 'priority_band'), sa.Index('ix_case_history', 'created_at', 'status'), sa.Index('ix_case_shop', 'shop_name'), sa.CheckConstraint("priority_band IN ('HIGH','NORMAL','LOW')"))

class Assignment(Base):
    __tablename__ = 'assignments'
    id: Mapped[str] = pk()
    case_id: Mapped[str] = fk('cases')
    inspector_id: Mapped[str] = fk('users')
    status: Mapped[AssignmentStatus] = mapped_column(enum(AssignmentStatus), default=AssignmentStatus.ASSIGNED)
    assigned_at: Mapped[datetime] = timecol()
    downloaded_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    __table_args__ = (sa.UniqueConstraint('case_id', name='uq_assignment_case'),)

class ProductSnapshot(Base):
    __tablename__ = 'product_snapshots'
    id: Mapped[str] = pk()
    case_id: Mapped[str] = fk('cases')
    product_name: Mapped[str] = mapped_column(sa.String(240), default='Unidentified package')
    brand: Mapped[str | None] = mapped_column(sa.String(180))
    manufacturer: Mapped[str] = mapped_column(sa.String(240), default='')
    variant: Mapped[str | None] = mapped_column(sa.String(180))
    net_quantity_text: Mapped[str | None] = mapped_column(sa.String(100))
    batch_lot: Mapped[str | None] = mapped_column(sa.String(100), index=True)
    barcode: Mapped[str | None] = mapped_column(sa.String(100), index=True)
    package_family: Mapped[PackageFamily] = mapped_column(enum(PackageFamily))
    officer_confirmed_json: Mapped[dict] = mapped_column(JSON, default=dict)
    __table_args__ = (sa.UniqueConstraint('case_id'), sa.Index('ix_product_name_lower', sa.func.lower(product_name)), sa.Index('ix_manufacturer_lower', sa.func.lower(manufacturer)))

class EvidencePlanItem(Base):
    __tablename__ = 'evidence_plan_items'
    id: Mapped[str] = pk()
    case_id: Mapped[str] = fk('cases')
    declaration_group: Mapped[str] = mapped_column(sa.String(3))
    required: Mapped[bool] = mapped_column(default=True)
    coverage_state: Mapped[CoverageState] = mapped_column(enum(CoverageState), default=CoverageState.PLANNED)
    absence_eligible: Mapped[bool] = mapped_column(default=False)
    next_capture_prompt: Mapped[str | None] = mapped_column(sa.Text)
    rule_ids: Mapped[list] = mapped_column(JSON, default=list)
    __table_args__ = (sa.UniqueConstraint('case_id', 'declaration_group'),)

class EvidenceItem(Base):
    __tablename__ = 'evidence_items'
    id: Mapped[str] = pk()
    case_id: Mapped[str] = fk('cases')
    captured_by_user_id: Mapped[str | None] = fk('users', True)
    sequence_no: Mapped[int] = mapped_column(sa.Integer)
    source_type: Mapped[EvidenceSource] = mapped_column(enum(EvidenceSource))
    source_context_json: Mapped[dict] = mapped_column(JSON, default=dict)
    storage_key: Mapped[str | None] = mapped_column(sa.String(300))
    mime_type: Mapped[str] = mapped_column(sa.String(50))
    sha256: Mapped[str] = mapped_column(sa.String(64))
    latitude: Mapped[float | None] = mapped_column(sa.Float)
    longitude: Mapped[float | None] = mapped_column(sa.Float)
    accuracy_m: Mapped[float | None] = mapped_column(sa.Float)
    captured_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    synced_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    sync_status: Mapped[SyncStatus] = mapped_column(enum(SyncStatus), default=SyncStatus.LOCAL_ONLY)
    quality_json: Mapped[dict] = mapped_column(JSON, default=dict)
    calibration_json: Mapped[dict | None] = mapped_column(JSON)
    __table_args__ = (sa.UniqueConstraint('case_id', 'sequence_no'), sa.CheckConstraint('sequence_no > 0'), sa.Index('ix_evidence_sync', 'case_id', 'sync_status'))

class ExtractionCandidate(Base):
    __tablename__ = 'extraction_candidates'
    id: Mapped[str] = pk()
    evidence_id: Mapped[str] = fk('evidence_items')
    declaration_group: Mapped[str] = mapped_column(sa.String(3))
    raw_text: Mapped[str] = mapped_column(sa.Text)
    normalized_value: Mapped[dict] = mapped_column(JSON)
    bbox: Mapped[list] = mapped_column(JSON)
    confidence: Mapped[float] = mapped_column(sa.Float)
    extractor: Mapped[str] = mapped_column(sa.String(100))
    created_at: Mapped[datetime] = timecol()
    __table_args__ = (sa.CheckConstraint('confidence >= 0 AND confidence <= 1'),)

class AnalysisRun(Base):
    __tablename__ = 'analysis_runs'
    id: Mapped[str] = pk()
    case_id: Mapped[str] = fk('cases')
    status: Mapped[AnalysisStatus] = mapped_column(enum(AnalysisStatus), default=AnalysisStatus.QUEUED)
    failure_code: Mapped[str | None] = mapped_column(sa.String(100))
    started_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    created_at: Mapped[datetime] = timecol()

class DeclarationResult(Base):
    __tablename__ = 'declaration_results'
    id: Mapped[str] = pk()
    case_id: Mapped[str] = fk('cases')
    declaration_group: Mapped[str] = mapped_column(sa.String(3))
    fused_value: Mapped[dict | None] = mapped_column(JSON)
    evidence_state: Mapped[EvidenceState] = mapped_column(enum(EvidenceState))
    selected_candidate_id: Mapped[str | None] = fk('extraction_candidates', True)
    source_ids: Mapped[list] = mapped_column(JSON, default=list)
    presentation_json: Mapped[dict] = mapped_column(JSON, default=dict)
    review_flags_json: Mapped[list] = mapped_column(JSON, default=list)
    updated_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), default=now, onupdate=now)
    __table_args__ = (sa.UniqueConstraint('case_id', 'declaration_group'),)

class Rule(Base):
    __tablename__ = 'rules'
    id: Mapped[str] = pk()
    rule_code: Mapped[str] = mapped_column(sa.String(32))
    version: Mapped[str] = mapped_column(sa.String(100))
    legal_reference: Mapped[str] = mapped_column(sa.Text)
    logic_key: Mapped[str] = mapped_column(sa.String(100))
    config_json: Mapped[dict] = mapped_column(JSON, default=dict)
    effective_from: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    effective_to: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    active: Mapped[bool] = mapped_column(default=True)
    __table_args__ = (sa.UniqueConstraint('rule_code', 'version'),)

class RuleResult(Base):
    __tablename__ = 'rule_results'
    id: Mapped[str] = pk()
    case_id: Mapped[str] = fk('cases')
    rule_id: Mapped[str] = fk('rules')
    declaration_result_id: Mapped[str | None] = fk('declaration_results', True)
    result_state: Mapped[str] = mapped_column(sa.String(70))
    reason_code: Mapped[str | None] = mapped_column(sa.String(80))
    inputs_json: Mapped[dict] = mapped_column(JSON, default=dict)
    explanation: Mapped[str] = mapped_column(sa.Text)
    created_at: Mapped[datetime] = timecol()

class Finding(Base):
    __tablename__ = 'findings'
    id: Mapped[str] = pk()
    case_id: Mapped[str] = fk('cases')
    rule_result_id: Mapped[str] = fk('rule_results')
    status: Mapped[FindingStatus] = mapped_column(enum(FindingStatus), default=FindingStatus.POTENTIAL)
    verified_value: Mapped[dict | None] = mapped_column(JSON)
    severity: Mapped[int] = mapped_column(sa.Integer, default=1)
    created_at: Mapped[datetime] = timecol()
    updated_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), default=now, onupdate=now)
    __table_args__ = (sa.Index('ix_finding_pattern', 'rule_result_id', 'status'),)

class VerificationEvent(Base):
    __tablename__ = 'verification_events'
    id: Mapped[str] = pk()
    finding_id: Mapped[str] = fk('findings')
    officer_id: Mapped[str] = fk('users')
    action: Mapped[Action] = mapped_column(enum(Action))
    corrected_value: Mapped[dict | None] = mapped_column(JSON)
    reason: Mapped[str] = mapped_column(sa.Text)
    created_at: Mapped[datetime] = timecol()
    __table_args__ = (sa.UniqueConstraint('finding_id'), sa.CheckConstraint('length(reason) > 0'))

class Report(Base):
    __tablename__ = 'reports'
    id: Mapped[str] = pk()
    case_id: Mapped[str] = fk('cases')
    status: Mapped[ReportStatus] = mapped_column(enum(ReportStatus), default=ReportStatus.QUEUED)
    storage_key: Mapped[str | None] = mapped_column(sa.String(300))
    editable_storage_key: Mapped[str | None] = mapped_column(sa.String(300))
    generated_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    failure_code: Mapped[str | None] = mapped_column(sa.String(100))
    __table_args__ = (sa.Index('ix_report_history', 'case_id', 'generated_at'),)

class PatternCandidate(Base):
    __tablename__ = 'pattern_candidates'
    id: Mapped[str] = pk()
    status: Mapped[PatternStatus] = mapped_column(enum(PatternStatus), default=PatternStatus.CANDIDATE)
    pattern_level: Mapped[str] = mapped_column(sa.String(50))
    rule_code: Mapped[str] = mapped_column(sa.String(32))
    match_factors: Mapped[dict] = mapped_column(JSON, default=dict)
    verified_count: Mapped[int] = mapped_column(sa.Integer)
    retailer_count: Mapped[int] = mapped_column(sa.Integer)
    created_at: Mapped[datetime] = timecol()
    reviewed_by: Mapped[str | None] = fk('users', True)
    reviewed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))

class PatternMember(Base):
    __tablename__ = 'pattern_members'
    pattern_id: Mapped[str] = mapped_column(UUID, sa.ForeignKey('pattern_candidates.id'), primary_key=True)
    finding_id: Mapped[str] = mapped_column(UUID, sa.ForeignKey('findings.id'), primary_key=True)
    match_reason: Mapped[dict] = mapped_column(JSON, default=dict)

class Followup(Base):
    __tablename__ = 'followups'
    id: Mapped[str] = pk()
    systemic_case_id: Mapped[str] = fk('cases')
    assigned_to: Mapped[str] = fk('users')
    status: Mapped[FollowupStatus] = mapped_column(enum(FollowupStatus), default=FollowupStatus.ASSIGNED)
    note: Mapped[str | None] = mapped_column(sa.Text)
    due_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    created_at: Mapped[datetime] = timecol()
    updated_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), default=now, onupdate=now)

class AuditEvent(Base):
    __tablename__ = 'audit_events'
    id: Mapped[str] = pk()
    actor_id: Mapped[str | None] = fk('users', True)
    case_id: Mapped[str | None] = fk('cases', True)
    event_type: Mapped[str] = mapped_column(sa.String(80))
    entity_type: Mapped[str] = mapped_column(sa.String(60))
    entity_id: Mapped[str] = mapped_column(UUID)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = timecol()
    __table_args__ = (sa.Index('ix_audit_entity', 'entity_type', 'entity_id', 'created_at'),)
