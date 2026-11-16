from .models import AuditLog


def log_audit(user, action, entity_type, entity_id, old_value="", new_value="", request=None):
    ip = None
    if request:
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        ip = x_forwarded_for.split(",")[0] if x_forwarded_for else request.META.get("REMOTE_ADDR")
    AuditLog.objects.create(
        user=user if (user and user.is_authenticated) else None,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id),
        old_value=str(old_value),
        new_value=str(new_value),
        ip_address=ip,
    )