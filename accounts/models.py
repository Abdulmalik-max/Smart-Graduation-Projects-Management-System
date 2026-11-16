import uuid
from datetime import timedelta
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone


class Department(models.Model):
    DEPARTMENTS = ["IS", "CS", "IT", "CYS", "AI", "DS"]
    DEPARTMENT_CHOICES = [(d, d) for d in DEPARTMENTS]

    dept_id = models.UUIDField(primary_key=True, editable=False, default=uuid.uuid4)
    name = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True)

    def __str__(self):
        return self.name


# -------------------------------------------------------------------------------------------------------

class UserManager(BaseUserManager):
    def create_user(self, email, full_name, password=None, **extra_fields):
        if not email:
            raise ValueError("Users must have an email address.")
        email = self.normalize_email(email)
        user = self.model(email=email, full_name=full_name, **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save()
        return user

    def create_superuser(self, email, full_name, password=None, **extra_fields):
        extra_fields.setdefault("role", User.Role.ADMIN)
        extra_fields.setdefault("status", User.Status.ACTIVE)
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        return self.create_user(email, full_name, password, **extra_fields)


# ------------------------------------------------------------------------------------------------------
class User(AbstractBaseUser, PermissionsMixin):
    class Role(models.TextChoices):
        STUDENT = "STUDENT", "Student"
        SUPERVISOR = "SUPERVISOR", "Supervisor"
        COMMITTEE = "COMMITTEE", "Committee Member"
        COORDINATOR = "COORDINATOR", "Coordinator"
        ADMIN = "ADMIN", "Administrator"

    class Status(models.TextChoices):
        PENDING_VERIFICATION = "PENDING_VERIFICATION", "Pending Verification"
        PENDING_APPROVAL = "PENDING_APPROVAL", "Pending Approval"
        INVITED = "INVITED", "Invited"
        ACTIVE = "ACTIVE", "Active"
        SUSPENDED = "SUSPENDED", "Suspended"
        LOCKED = "LOCKED", "Locked"

    class AcademicDegree(models.TextChoices):
        NONE = "NONE", "N/A"
        MASTER = "MASTER", "Master's"
        PHD = "PHD", "PhD"

    user_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True, max_length=255)
    username = models.CharField(max_length=100, unique=True, blank=True, null=True)
    full_name = models.CharField(max_length=255)
    phone = models.CharField(max_length=13, blank=True)
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, related_name='users', null=True, blank=True)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.STUDENT)
    status = models.CharField(max_length=25, choices=Status.choices, default=Status.PENDING_VERIFICATION)

    # Student-specific field
    student_id = models.CharField(max_length=15, unique=True, blank=True, null=True, help_text="University Student ID")

    # Supervisor/Committee AI-matching fields
    academic_degree = models.CharField(max_length=15, choices=AcademicDegree.choices, default=AcademicDegree.NONE)
    expertise = models.TextField(blank=True, help_text="Comma-separated research domains/keywords")
    max_supervision_load = models.PositiveIntegerField(default=5)

    # Security & 3-failed-attempts lockout
    failed_login_attempts = models.PositiveSmallIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["full_name"]

    def is_temporarily_locked(self):
        if self.locked_until and timezone.now() < self.locked_until:
            return True
        if self.locked_until and timezone.now() >= self.locked_until:
            self.failed_login_attempts = 0
            self.locked_until = None
            if self.status == self.Status.LOCKED:
                self.status = self.Status.ACTIVE
            self.save(update_fields=["failed_login_attempts", "locked_until", "status"])
        return False

    def register_failed_login(self):
        self.failed_login_attempts += 1
        if self.failed_login_attempts >= 3:
            self.locked_until = timezone.now() + timedelta(minutes=15)
            self.status = self.Status.LOCKED
        self.save(update_fields=["failed_login_attempts", "locked_until", "status"])

    def reset_failed_logins(self):
        if self.failed_login_attempts > 0 or self.locked_until:
            self.failed_login_attempts = 0
            self.locked_until = None
            self.save(update_fields=["failed_login_attempts", "locked_until"])

    def get_full_name(self):
        return self.full_name

    def get_short_name(self):
        return self.full_name.split()[0] if self.full_name else self.email

    def __str__(self):
        return f"{self.full_name} ({self.get_role_display()})"


# -----------------------------------------------------------------------------------------------------------------

class AuditLog(models.Model):
    audit_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="audit_logs")
    action = models.CharField(max_length=150)
    entity_type = models.CharField(max_length=100)
    entity_id = models.CharField(max_length=64)  # Supports UUID strings cleanly
    old_value = models.TextField(blank=True)
    new_value = models.TextField(blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.action} by {self.user} at {self.created_at:%Y-%m-%d %H:%M}"
