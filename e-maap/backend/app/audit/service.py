from app.core.models import AuditEvent

def audit(db, actor, case_id, event_type, entity_type, entity_id, payload=None):
    event = AuditEvent(actor_id=getattr(actor, 'user_id', None), case_id=case_id,
        event_type=event_type, entity_type=entity_type, entity_id=str(entity_id), payload=payload or {})
    db.add(event)
    db.flush()
    return event
