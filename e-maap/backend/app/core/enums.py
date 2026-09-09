"""Canonical vocabulary: SRS 16.2 plus the six approved contract corrections."""
from enum import StrEnum

class Role(StrEnum):
    INSPECTOR = 'INSPECTOR'
    GOVERNMENT_OFFICER = 'GOVERNMENT_OFFICER'

class CaseType(StrEnum):
    CITIZEN_LEAD = 'CITIZEN_LEAD'
    INSPECTION = 'INSPECTION'
    SYSTEMIC = 'SYSTEMIC'

class CaseStatus(StrEnum):
    INTAKE = 'INTAKE'
    UNDER_REVIEW = 'UNDER_REVIEW'
    ASSIGNED = 'ASSIGNED'
    CAPTURING = 'CAPTURING'
    SYNCING = 'SYNCING'
    ANALYSING = 'ANALYSING'
    AWAITING_VERIFICATION = 'AWAITING_VERIFICATION'
    COMPLETED = 'COMPLETED'
    CLOSED = 'CLOSED'

class AssignmentStatus(StrEnum):
    ASSIGNED = 'ASSIGNED'
    DOWNLOADED = 'DOWNLOADED'
    IN_PROGRESS = 'IN_PROGRESS'
    SUBMITTED = 'SUBMITTED'
    COMPLETED = 'COMPLETED'

class SyncStatus(StrEnum):
    LOCAL_ONLY = 'LOCAL_ONLY'
    UPLOADING = 'UPLOADING'
    SYNCHRONISED = 'SYNCHRONISED'
    FAILED = 'FAILED'

class AnalysisStatus(StrEnum):
    QUEUED = 'QUEUED'
    RUNNING = 'RUNNING'
    SUCCEEDED = 'SUCCEEDED'
    FAILED = 'FAILED'

class EvidenceState(StrEnum):
    SUPPORTED = 'SUPPORTED'
    CONFLICTING = 'CONFLICTING'
    UNRESOLVED = 'UNRESOLVED'
    OBSCURED_DAMAGED = 'OBSCURED_DAMAGED'
    POTENTIALLY_ABSENT = 'POTENTIALLY_ABSENT'
    NOT_APPLICABLE = 'NOT_APPLICABLE'

class FindingStatus(StrEnum):
    POTENTIAL = 'POTENTIAL'
    ACCEPTED = 'ACCEPTED'
    CORRECTED = 'CORRECTED'
    REJECTED = 'REJECTED'

class PatternStatus(StrEnum):
    CANDIDATE = 'CANDIDATE'
    APPROVED = 'APPROVED'
    REJECTED = 'REJECTED'

class ReportStatus(StrEnum):
    QUEUED = 'QUEUED'
    GENERATING = 'GENERATING'
    READY = 'READY'
    FAILED = 'FAILED'

class EvidenceSource(StrEnum):
    FIELD_CAPTURE = 'FIELD_CAPTURE'
    CITIZEN_UPLOAD = 'CITIZEN_UPLOAD'
    GOVERNMENT_UPLOAD = 'GOVERNMENT_UPLOAD'
    LISTING_UPLOAD = 'LISTING_UPLOAD'

class CoverageState(StrEnum):
    PLANNED = 'PLANNED'
    PARTIAL = 'PARTIAL'
    ADEQUATE = 'ADEQUATE'
    MANUAL_CONFIRMED = 'MANUAL_CONFIRMED'

class PackageFamily(StrEnum):
    RIGID_CUBOID = 'RIGID_CUBOID'
    CURVED_RIGID = 'CURVED_RIGID'
    FLEXIBLE = 'FLEXIBLE'
    OTHER_PACKAGE = 'OTHER_PACKAGE'

class Action(StrEnum):
    ACCEPT = 'ACCEPT'
    CORRECT = 'CORRECT'
    REJECT = 'REJECT'

class FollowupStatus(StrEnum):
    ASSIGNED = 'ASSIGNED'
    IN_PROGRESS = 'IN_PROGRESS'
    COMPLETED = 'COMPLETED'

class BriefStatus(StrEnum):
    DRAFT = 'DRAFT'
    APPROVED = 'APPROVED'
    REJECTED = 'REJECTED'

GROUPS = {'D01': 'Commodity name', 'D02': 'Manufacturer / packer', 'D03': 'Net quantity', 'D04': 'MRP', 'D05': 'Month / year', 'D06': 'Consumer care'}
PUBLIC_STATUS = {'INTAKE': 'Submitted', 'UNDER_REVIEW': 'Under Review', 'ASSIGNED': 'Inspection Assigned', 'CAPTURING': 'Inspection Assigned', 'SYNCING': 'Inspection Assigned', 'ANALYSING': 'Inspection Assigned', 'AWAITING_VERIFICATION': 'Inspection Assigned', 'COMPLETED': 'Inspection Completed', 'CLOSED': 'Closed'}

