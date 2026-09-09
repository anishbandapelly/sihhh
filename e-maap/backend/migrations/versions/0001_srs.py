"""SRS operational model and approved addendum. Single initial prototype revision."""
from alembic import op
from app.core.db import Base
from app.core import models

revision = '0001_srs'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    bind = op.get_bind()
    Base.metadata.create_all(bind)
    if bind.dialect.name != 'postgresql': return
    op.execute("""CREATE FUNCTION immutable_history() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN RAISE EXCEPTION 'Append-only history cannot be modified'; END $$""")
    for table in ('audit_events', 'verification_events'):
        op.execute(f'CREATE TRIGGER immutable_{table} BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION immutable_history()')
    op.execute("""CREATE FUNCTION guard_absence() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF NEW.evidence_state = 'POTENTIALLY_ABSENT' AND NOT EXISTS (
        SELECT 1 FROM evidence_plan_items p WHERE p.case_id=NEW.case_id
        AND p.declaration_group=NEW.declaration_group AND p.absence_eligible=true
      ) THEN RAISE EXCEPTION 'Coverage required before absence'; END IF;
      RETURN NEW;
    END $$""")
    op.execute('CREATE TRIGGER guard_absence BEFORE INSERT OR UPDATE ON declaration_results FOR EACH ROW EXECUTE FUNCTION guard_absence()')
    op.execute("""CREATE FUNCTION guard_verified_finding() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF NEW.status <> 'POTENTIAL' AND NOT EXISTS (
        SELECT 1 FROM verification_events v WHERE v.finding_id=NEW.id
      ) THEN RAISE EXCEPTION 'Officer verification event required'; END IF;
      RETURN NEW;
    END $$""")
    op.execute('CREATE CONSTRAINT TRIGGER guard_verified_finding AFTER INSERT OR UPDATE ON findings DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION guard_verified_finding()')
    op.execute("""CREATE FUNCTION guard_pattern_member() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF NOT EXISTS (SELECT 1 FROM findings f JOIN verification_events v ON v.finding_id=f.id
        WHERE f.id=NEW.finding_id AND f.status IN ('ACCEPTED','CORRECTED'))
      THEN RAISE EXCEPTION 'Pattern member must be officer verified'; END IF;
      RETURN NEW;
    END $$""")
    op.execute('CREATE TRIGGER guard_pattern_member BEFORE INSERT OR UPDATE ON pattern_members FOR EACH ROW EXECUTE FUNCTION guard_pattern_member()')

def downgrade():
    Base.metadata.drop_all(op.get_bind())
    if op.get_bind().dialect.name == 'postgresql':
        for name in ('immutable_history','guard_absence','guard_verified_finding','guard_pattern_member'):
            op.execute(f'DROP FUNCTION IF EXISTS {name}() CASCADE')
