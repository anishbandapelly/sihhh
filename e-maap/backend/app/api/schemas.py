from datetime import datetime
from uuid import UUID
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict, model_validator
from app.core.enums import PackageFamily, Action, FollowupStatus

class Contract(BaseModel):
    model_config = ConfigDict(extra='forbid')

class Login(Contract):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=8, max_length=200)

class ProductInput(Contract):
    product_name: str = Field(min_length=1, max_length=240)
    brand: str | None = None
    manufacturer: str = ''
    variant: str | None = None
    net_quantity_text: str | None = None
    batch_lot: str | None = None
    barcode: str | None = None
    package_family: PackageFamily = PackageFamily.RIGID_CUBOID

class ScanCreate(Contract):
    package_family: PackageFamily
    product_name: str = 'Unidentified package'

class ComplaintCreate(Contract):
    scan_id: UUID
    product_snapshot: ProductInput
    shop_name: str = Field(min_length=2, max_length=200)
    shop_location: dict = Field(default_factory=dict)
    declaration_corrections: dict = Field(default_factory=dict)
    confirmed: Literal[True]

class EvidenceContext(Contract):
    view_role: str
    search_groups: list[Literal['D01','D02','D03','D04','D05','D06']] = Field(default_factory=list)
    observed_condition: Literal['CLEAR','OBSCURED_DAMAGED'] = 'CLEAR'
    inspected_area: str = ''
    replacement_for: UUID | None = None
    note: str = Field(default='', max_length=2000)

class Calibration(Contract):
    calibration_source: Literal['REFERENCE_MARKER','FIXTURE_KNOWN_SCALE']
    reference_id: str = Field(min_length=1)
    reference_length_mm: float = Field(gt=0)
    reference_length_px: float = Field(gt=0)
    reference_bbox: list[float] = Field(min_length=4, max_length=4)
    @model_validator(mode='after')
    def reference_region_valid(self):
        x1,y1,x2,y2=self.reference_bbox
        if not (0<=x1<x2<=1 and 0<=y1<y2<=1): raise ValueError('Calibration requires a normalised source reference region')
        return self
    @property
    def px_per_mm(self): return self.reference_length_px / self.reference_length_mm

class EvidenceCreate(Contract):
    id: UUID
    sequence_no: int = Field(gt=0)
    sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    mime_type: Literal['image/jpeg','image/png']
    captured_at: datetime
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    accuracy_m: float | None = Field(default=None, ge=0)
    source_context_json: EvidenceContext
    quality: dict = Field(default_factory=dict)
    calibration_json: Calibration | None = None
    @model_validator(mode='after')
    def utc_required(self):
        if self.captured_at.tzinfo is None: raise ValueError('captured_at must include a timezone')
        return self

class SyncComplete(Contract):
    evidence_ids: list[UUID] = Field(min_length=1)

class ProfileChange(Contract):
    package_family: PackageFamily
    reason: str = Field(min_length=1)
    product_snapshot: ProductInput | None = None

class CoverageConfirmation(Contract):
    plan_item_ids: list[UUID] = Field(min_length=1)
    evidence_ids: list[UUID] = Field(min_length=1)
    inspected_areas: list[str] = Field(min_length=1)
    reason: str = Field(min_length=1)

class SourceReference(Contract):
    evidence_id: UUID
    bbox: list[float] = Field(min_length=4, max_length=4)
    candidate_id: UUID | None = None
    @model_validator(mode='after')
    def valid_box(self):
        x1,y1,x2,y2=self.bbox
        if not (0 <= x1 < x2 <= 1 and 0 <= y1 < y2 <= 1): raise ValueError('bbox is normalised [x1,y1,x2,y2]')
        return self

class Verification(Contract):
    action: Action
    corrected_value: dict | None = None
    reason: str = Field(min_length=1, max_length=3000)
    @model_validator(mode='after')
    def correction_required(self):
        if self.action == Action.CORRECT and not self.corrected_value: raise ValueError('CORRECT requires corrected_value')
        return self

class DeclarationReview(Verification):
    source_refs: list[SourceReference] = Field(min_length=1)

class PriorityOverride(Contract):
    priority_band: Literal['HIGH','NORMAL','LOW']
    reason: str = Field(min_length=1, max_length=3000)

class AssignmentCreate(Contract):
    inspector_id: UUID
    brief_id: UUID | None = None
    reason: str = Field(min_length=1)

class Decision(Contract):
    decision: Literal['APPROVE','REJECT']
    reason: str = Field(min_length=1)

class FollowupCreate(Contract):
    assigned_to: UUID
    note: str = Field(min_length=1)
    due_at: datetime | None = None
    brief_id: UUID | None = None

class FollowupUpdate(Contract):
    status: FollowupStatus
    note: str = Field(min_length=1)

class CopilotQuery(Contract):
    context_type: Literal['case','pattern']
    context_id: UUID
    prompt_key_or_text: str = Field(min_length=1, max_length=2000)

class BriefCreate(Contract):
    context_type: Literal['case','pattern']
    context_id: UUID
    draft_id: UUID | None = None
    content: str | None = Field(default=None, max_length=20000)
