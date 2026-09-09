BEGIN;

CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL, 
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- Running upgrade  -> 0001_srs

CREATE TYPE role AS ENUM ('INSPECTOR', 'GOVERNMENT_OFFICER');

CREATE TYPE casetype AS ENUM ('CITIZEN_LEAD', 'INSPECTION', 'SYSTEMIC');

CREATE TYPE casestatus AS ENUM ('INTAKE', 'UNDER_REVIEW', 'ASSIGNED', 'CAPTURING', 'SYNCING', 'ANALYSING', 'AWAITING_VERIFICATION', 'COMPLETED', 'CLOSED');

CREATE TYPE assignmentstatus AS ENUM ('ASSIGNED', 'DOWNLOADED', 'IN_PROGRESS', 'SUBMITTED', 'COMPLETED');

CREATE TYPE packagefamily AS ENUM ('RIGID_CUBOID', 'CURVED_RIGID', 'FLEXIBLE', 'OTHER_PACKAGE');

CREATE TYPE coveragestate AS ENUM ('PLANNED', 'PARTIAL', 'ADEQUATE', 'MANUAL_CONFIRMED');

CREATE TYPE evidencesource AS ENUM ('FIELD_CAPTURE', 'CITIZEN_UPLOAD', 'GOVERNMENT_UPLOAD', 'LISTING_UPLOAD');

CREATE TYPE syncstatus AS ENUM ('LOCAL_ONLY', 'UPLOADING', 'SYNCHRONISED', 'FAILED');

CREATE TYPE analysisstatus AS ENUM ('QUEUED', 'RUNNING', 'SUCCEEDED', 'FAILED');

CREATE TYPE evidencestate AS ENUM ('SUPPORTED', 'CONFLICTING', 'UNRESOLVED', 'OBSCURED_DAMAGED', 'POTENTIALLY_ABSENT', 'NOT_APPLICABLE');

CREATE TYPE findingstatus AS ENUM ('POTENTIAL', 'ACCEPTED', 'CORRECTED', 'REJECTED');

CREATE TYPE action AS ENUM ('ACCEPT', 'CORRECT', 'REJECT');

CREATE TYPE reportstatus AS ENUM ('QUEUED', 'GENERATING', 'READY', 'FAILED');

CREATE TYPE patternstatus AS ENUM ('CANDIDATE', 'APPROVED', 'REJECTED');

CREATE TYPE followupstatus AS ENUM ('ASSIGNED', 'IN_PROGRESS', 'COMPLETED');

CREATE TABLE users (
    id UUID NOT NULL, 
    name VARCHAR(160) NOT NULL, 
    email VARCHAR(254) NOT NULL, 
    password_hash TEXT NOT NULL, 
    role role NOT NULL, 
    active BOOLEAN NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (email)
);

CREATE TABLE cases (
    id UUID NOT NULL, 
    case_type casetype NOT NULL, 
    source VARCHAR(80) NOT NULL, 
    status casestatus NOT NULL, 
    priority_band VARCHAR(16) NOT NULL, 
    priority_reasons JSONB NOT NULL, 
    parent_case_id UUID, 
    shop_name VARCHAR(200) NOT NULL, 
    shop_location JSONB NOT NULL, 
    citizen_session_id UUID, 
    public_tracking_token_hash VARCHAR(64), 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    CHECK (priority_band IN ('HIGH','NORMAL','LOW')), 
    FOREIGN KEY(parent_case_id) REFERENCES cases (id)
);

CREATE INDEX ix_case_shop ON cases (shop_name);

CREATE INDEX ix_case_history ON cases (created_at, status);

CREATE INDEX ix_cases_citizen_session_id ON cases (citizen_session_id);

CREATE INDEX ix_case_queue ON cases (status, priority_band);

CREATE TABLE rules (
    id UUID NOT NULL, 
    rule_code VARCHAR(32) NOT NULL, 
    version VARCHAR(100) NOT NULL, 
    legal_reference TEXT NOT NULL, 
    logic_key VARCHAR(100) NOT NULL, 
    config_json JSONB NOT NULL, 
    effective_from TIMESTAMP WITH TIME ZONE, 
    effective_to TIMESTAMP WITH TIME ZONE, 
    active BOOLEAN NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (rule_code, version)
);

CREATE TABLE assignments (
    id UUID NOT NULL, 
    case_id UUID NOT NULL, 
    inspector_id UUID NOT NULL, 
    status assignmentstatus NOT NULL, 
    assigned_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    downloaded_at TIMESTAMP WITH TIME ZONE, 
    completed_at TIMESTAMP WITH TIME ZONE, 
    PRIMARY KEY (id), 
    CONSTRAINT uq_assignment_case UNIQUE (case_id), 
    FOREIGN KEY(case_id) REFERENCES cases (id), 
    FOREIGN KEY(inspector_id) REFERENCES users (id)
);

CREATE TABLE product_snapshots (
    id UUID NOT NULL, 
    case_id UUID NOT NULL, 
    product_name VARCHAR(240) NOT NULL, 
    brand VARCHAR(180), 
    manufacturer VARCHAR(240) NOT NULL, 
    variant VARCHAR(180), 
    net_quantity_text VARCHAR(100), 
    batch_lot VARCHAR(100), 
    barcode VARCHAR(100), 
    package_family packagefamily NOT NULL, 
    officer_confirmed_json JSONB NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (case_id), 
    FOREIGN KEY(case_id) REFERENCES cases (id)
);

CREATE INDEX ix_product_snapshots_batch_lot ON product_snapshots (batch_lot);

CREATE INDEX ix_product_name_lower ON product_snapshots (lower(product_name));

CREATE INDEX ix_manufacturer_lower ON product_snapshots (lower(manufacturer));

CREATE INDEX ix_product_snapshots_barcode ON product_snapshots (barcode);

CREATE TABLE evidence_plan_items (
    id UUID NOT NULL, 
    case_id UUID NOT NULL, 
    declaration_group VARCHAR(3) NOT NULL, 
    required BOOLEAN NOT NULL, 
    coverage_state coveragestate NOT NULL, 
    absence_eligible BOOLEAN NOT NULL, 
    next_capture_prompt TEXT, 
    rule_ids JSONB NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (case_id, declaration_group), 
    FOREIGN KEY(case_id) REFERENCES cases (id)
);

CREATE TABLE evidence_items (
    id UUID NOT NULL, 
    case_id UUID NOT NULL, 
    captured_by_user_id UUID, 
    sequence_no INTEGER NOT NULL, 
    source_type evidencesource NOT NULL, 
    source_context_json JSONB NOT NULL, 
    storage_key VARCHAR(300), 
    mime_type VARCHAR(50) NOT NULL, 
    sha256 VARCHAR(64) NOT NULL, 
    latitude FLOAT, 
    longitude FLOAT, 
    accuracy_m FLOAT, 
    captured_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    synced_at TIMESTAMP WITH TIME ZONE, 
    sync_status syncstatus NOT NULL, 
    quality_json JSONB NOT NULL, 
    calibration_json JSONB, 
    PRIMARY KEY (id), 
    UNIQUE (case_id, sequence_no), 
    CHECK (sequence_no > 0), 
    FOREIGN KEY(case_id) REFERENCES cases (id), 
    FOREIGN KEY(captured_by_user_id) REFERENCES users (id)
);

CREATE INDEX ix_evidence_sync ON evidence_items (case_id, sync_status);

CREATE TABLE analysis_runs (
    id UUID NOT NULL, 
    case_id UUID NOT NULL, 
    status analysisstatus NOT NULL, 
    failure_code VARCHAR(100), 
    started_at TIMESTAMP WITH TIME ZONE, 
    completed_at TIMESTAMP WITH TIME ZONE, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(case_id) REFERENCES cases (id)
);

CREATE TABLE reports (
    id UUID NOT NULL, 
    case_id UUID NOT NULL, 
    status reportstatus NOT NULL, 
    storage_key VARCHAR(300), 
    editable_storage_key VARCHAR(300), 
    generated_at TIMESTAMP WITH TIME ZONE, 
    failure_code VARCHAR(100), 
    PRIMARY KEY (id), 
    FOREIGN KEY(case_id) REFERENCES cases (id)
);

CREATE INDEX ix_report_history ON reports (case_id, generated_at);

CREATE TABLE pattern_candidates (
    id UUID NOT NULL, 
    status patternstatus NOT NULL, 
    pattern_level VARCHAR(50) NOT NULL, 
    rule_code VARCHAR(32) NOT NULL, 
    match_factors JSONB NOT NULL, 
    verified_count INTEGER NOT NULL, 
    retailer_count INTEGER NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    reviewed_by UUID, 
    reviewed_at TIMESTAMP WITH TIME ZONE, 
    PRIMARY KEY (id), 
    FOREIGN KEY(reviewed_by) REFERENCES users (id)
);

CREATE TABLE followups (
    id UUID NOT NULL, 
    systemic_case_id UUID NOT NULL, 
    assigned_to UUID NOT NULL, 
    status followupstatus NOT NULL, 
    note TEXT, 
    due_at TIMESTAMP WITH TIME ZONE, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(systemic_case_id) REFERENCES cases (id), 
    FOREIGN KEY(assigned_to) REFERENCES users (id)
);

CREATE TABLE audit_events (
    id UUID NOT NULL, 
    actor_id UUID, 
    case_id UUID, 
    event_type VARCHAR(80) NOT NULL, 
    entity_type VARCHAR(60) NOT NULL, 
    entity_id UUID NOT NULL, 
    payload JSONB NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(actor_id) REFERENCES users (id), 
    FOREIGN KEY(case_id) REFERENCES cases (id)
);

CREATE INDEX ix_audit_entity ON audit_events (entity_type, entity_id, created_at);

CREATE TABLE extraction_candidates (
    id UUID NOT NULL, 
    evidence_id UUID NOT NULL, 
    declaration_group VARCHAR(3) NOT NULL, 
    raw_text TEXT NOT NULL, 
    normalized_value JSONB NOT NULL, 
    bbox JSONB NOT NULL, 
    confidence FLOAT NOT NULL, 
    extractor VARCHAR(100) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    CHECK (confidence >= 0 AND confidence <= 1), 
    FOREIGN KEY(evidence_id) REFERENCES evidence_items (id)
);

CREATE TABLE declaration_results (
    id UUID NOT NULL, 
    case_id UUID NOT NULL, 
    declaration_group VARCHAR(3) NOT NULL, 
    fused_value JSONB, 
    evidence_state evidencestate NOT NULL, 
    selected_candidate_id UUID, 
    source_ids JSONB NOT NULL, 
    presentation_json JSONB NOT NULL, 
    review_flags_json JSONB NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (case_id, declaration_group), 
    FOREIGN KEY(case_id) REFERENCES cases (id), 
    FOREIGN KEY(selected_candidate_id) REFERENCES extraction_candidates (id)
);

CREATE TABLE rule_results (
    id UUID NOT NULL, 
    case_id UUID NOT NULL, 
    rule_id UUID NOT NULL, 
    declaration_result_id UUID, 
    result_state VARCHAR(70) NOT NULL, 
    reason_code VARCHAR(80), 
    inputs_json JSONB NOT NULL, 
    explanation TEXT NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(case_id) REFERENCES cases (id), 
    FOREIGN KEY(rule_id) REFERENCES rules (id), 
    FOREIGN KEY(declaration_result_id) REFERENCES declaration_results (id)
);

CREATE TABLE findings (
    id UUID NOT NULL, 
    case_id UUID NOT NULL, 
    rule_result_id UUID NOT NULL, 
    status findingstatus NOT NULL, 
    verified_value JSONB, 
    severity INTEGER NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(case_id) REFERENCES cases (id), 
    FOREIGN KEY(rule_result_id) REFERENCES rule_results (id)
);

CREATE INDEX ix_finding_pattern ON findings (rule_result_id, status);

CREATE TABLE verification_events (
    id UUID NOT NULL, 
    finding_id UUID NOT NULL, 
    officer_id UUID NOT NULL, 
    action action NOT NULL, 
    corrected_value JSONB, 
    reason TEXT NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (finding_id), 
    CHECK (length(reason) > 0), 
    FOREIGN KEY(finding_id) REFERENCES findings (id), 
    FOREIGN KEY(officer_id) REFERENCES users (id)
);

CREATE TABLE pattern_members (
    pattern_id UUID NOT NULL, 
    finding_id UUID NOT NULL, 
    match_reason JSONB NOT NULL, 
    PRIMARY KEY (pattern_id, finding_id), 
    FOREIGN KEY(pattern_id) REFERENCES pattern_candidates (id), 
    FOREIGN KEY(finding_id) REFERENCES findings (id)
);

CREATE FUNCTION immutable_history() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN RAISE EXCEPTION 'Append-only history cannot be modified'; END $$;

CREATE TRIGGER immutable_audit_events BEFORE UPDATE OR DELETE ON audit_events FOR EACH ROW EXECUTE FUNCTION immutable_history();

CREATE TRIGGER immutable_verification_events BEFORE UPDATE OR DELETE ON verification_events FOR EACH ROW EXECUTE FUNCTION immutable_history();

CREATE FUNCTION guard_absence() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF NEW.evidence_state = 'POTENTIALLY_ABSENT' AND NOT EXISTS (
        SELECT 1 FROM evidence_plan_items p WHERE p.case_id=NEW.case_id
        AND p.declaration_group=NEW.declaration_group AND p.absence_eligible=true
      ) THEN RAISE EXCEPTION 'Coverage required before absence'; END IF;
      RETURN NEW;
    END $$;

CREATE TRIGGER guard_absence BEFORE INSERT OR UPDATE ON declaration_results FOR EACH ROW EXECUTE FUNCTION guard_absence();

CREATE FUNCTION guard_verified_finding() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF NEW.status <> 'POTENTIAL' AND NOT EXISTS (
        SELECT 1 FROM verification_events v WHERE v.finding_id=NEW.id
      ) THEN RAISE EXCEPTION 'Officer verification event required'; END IF;
      RETURN NEW;
    END $$;

CREATE CONSTRAINT TRIGGER guard_verified_finding AFTER INSERT OR UPDATE ON findings DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION guard_verified_finding();

CREATE FUNCTION guard_pattern_member() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF NOT EXISTS (SELECT 1 FROM findings f JOIN verification_events v ON v.finding_id=f.id
        WHERE f.id=NEW.finding_id AND f.status IN ('ACCEPTED','CORRECTED'))
      THEN RAISE EXCEPTION 'Pattern member must be officer verified'; END IF;
      RETURN NEW;
    END $$;

CREATE TRIGGER guard_pattern_member BEFORE INSERT OR UPDATE ON pattern_members FOR EACH ROW EXECUTE FUNCTION guard_pattern_member();

INSERT INTO alembic_version (version_num) VALUES ('0001_srs') RETURNING alembic_version.version_num;

COMMIT;

