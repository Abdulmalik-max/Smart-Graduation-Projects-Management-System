"""
Test suite for the accounts app.

Each test class targets a specific fix:

    ModelNullabilityTests          → department / student_id now nullable
    NamespaceTests                 → no leftover `accounts:` URL prefix
    LoginRedirectTests             → login lands on the right dashboard + `next` works
    StudentRegistrationValidation  → clean() / clean_student_id() actually run
    LoginStatusTests               → status message + 3-strike lockout
    AdminSelfProtectionTests       → admin can't delete or demote themselves
    NavbarTemplateTests            → `<buttonclass=` typo is gone
    PasswordResetFlowTests         → reverse_lazy() targets resolve + email sent
    AuditLogTests                  → audit entries are written
    StaffInviteTests               → invited staff are created without a student_id

Run with:
    python manage.py test accounts -v 2
"""

from django.core import mail
from django.test import TestCase
from django.urls import reverse

from accounts.models import AuditLog, Department, User


# ────────────────────────────────────────────────────────────────────────────
# Helper
# ────────────────────────────────────────────────────────────────────────────
def make_user(email, role=User.Role.STUDENT, status=User.Status.ACTIVE,
              password="Passw0rd!", **extra):
    """Create a user with sane defaults for tests."""
    return User.objects.create_user(
        email=email,
        full_name=extra.pop("full_name", "Test User"),
        password=password,
        role=role,
        status=status,
        **extra,
    )


# ────────────────────────────────────────────────────────────────────────────
# Fix #1 + #2 — Nullable model fields
# ────────────────────────────────────────────────────────────────────────────
class ModelNullabilityTests(TestCase):
    def test_two_staff_users_without_student_id(self):
        """
        Before the fix, the second `create_user` raised IntegrityError
        because two empty `student_id` values collided on the unique index.
        """
        User.objects.create_user(
            email="s1@su.edu.ye", full_name="S1",
            password="p", role=User.Role.SUPERVISOR,
        )
        User.objects.create_user(
            email="s2@su.edu.ye", full_name="S2",
            password="p", role=User.Role.SUPERVISOR,
        )
        self.assertEqual(
            User.objects.filter(student_id__isnull=True).count(), 2
        )

    def test_department_can_be_null(self):
        u = User.objects.create_user(
            email="a@su.edu.ye", full_name="A", password="p",
        )
        self.assertIsNone(u.department)

    def test_superuser_can_be_created_without_department(self):
        su = User.objects.create_superuser(
            email="root@su.edu.ye", full_name="Root", password="p",
        )
        self.assertTrue(su.is_superuser)
        self.assertIsNone(su.department)
        self.assertIsNone(su.student_id)


# ────────────────────────────────────────────────────────────────────────────
# Fix #3 — URL namespace
# ────────────────────────────────────────────────────────────────────────────
class NamespaceTests(TestCase):
    def test_un_namespaced_urls_resolve(self):
        """Every route that previously used `accounts:` must reverse cleanly."""
        for name in [
            "login", "logout", "profile", "student_register",
            "user_list", "staff_invite", "audit_log",
            "password_reset", "password_reset_done",
            "password_reset_confirm", "password_reset_complete",
        ]:
            with self.subTest(name=name):
                self.assertTrue(reverse(name))


# ────────────────────────────────────────────────────────────────────────────
# Fix #3 (cont.) + #9 — Login redirects
# ────────────────────────────────────────────────────────────────────────────
class LoginRedirectTests(TestCase):
    def test_admin_login_lands_on_user_list(self):
        make_user("admin@su.edu.ye", role=User.Role.ADMIN,
                  is_staff=True, is_superuser=True)
        resp = self.client.post(
            reverse("login"),
            {"email": "admin@su.edu.ye", "password": "Passw0rd!"},
        )
        self.assertRedirects(resp, reverse("user_list"))

    def test_student_login_lands_on_profile(self):
        make_user("stu@su.edu.ye", role=User.Role.STUDENT)
        resp = self.client.post(
            reverse("login"),
            {"email": "stu@su.edu.ye", "password": "Passw0rd!"},
        )
        self.assertRedirects(resp, reverse("profile"))

    def test_supervisor_login_lands_on_profile(self):
        make_user("sup@su.edu.ye", role=User.Role.SUPERVISOR)
        resp = self.client.post(
            reverse("login"),
            {"email": "sup@su.edu.ye", "password": "Passw0rd!"},
        )
        self.assertRedirects(resp, reverse("profile"))

    def test_next_is_respected(self):
        """Admin's default dashboard is /users/, but ?next= must win."""
        make_user("admin@su.edu.ye", role=User.Role.ADMIN,
                  is_staff=True, is_superuser=True)
        target = reverse("audit_log")
        resp = self.client.post(
            reverse("login"),
            {"email": "admin@su.edu.ye",
             "password": "Passw0rd!",
             "next": target},
        )
        self.assertRedirects(resp, target)

    def test_external_next_is_rejected(self):
        """An absolute URL pointing elsewhere must not be followed."""
        make_user("admin@su.edu.ye", role=User.Role.ADMIN,
                  is_staff=True, is_superuser=True)
        resp = self.client.post(
            reverse("login"),
            {"email": "admin@su.edu.ye",
             "password": "Passw0rd!",
             "next": "https://evil.example.com/"},
        )
        self.assertRedirects(resp, reverse("user_list"))


# ────────────────────────────────────────────────────────────────────────────
# Fix #4 — Validation methods that used to live inside Meta
# ────────────────────────────────────────────────────────────────────────────
class StudentRegistrationValidationTests(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(name="CS")

    def _payload(self, **overrides):
        base = {
            "full_name": "New Student",
            "email": "new@su.edu.ye",
            "student_id": "24160126",
            "department": self.dept.pk,
            "phone": "777777777",
            "password": "ComplexP@ss1",
            "confirm_password": "ComplexP@ss1",
        }
        base.update(overrides)
        return base

    def test_clean_methods_are_on_the_form_not_meta(self):
        """Regression guard for the `Meta`-nesting bug."""
        from accounts.forms import StudentRegistrationForm
        self.assertIn("clean", StudentRegistrationForm.__dict__)
        self.assertIn("clean_student_id", StudentRegistrationForm.__dict__)

    def test_mismatched_passwords_are_rejected(self):
        resp = self.client.post(
            reverse("student_register"),
            self._payload(confirm_password="DifferentP@ss1"),
        )
        self.assertEqual(resp.status_code, 200)         # form redisplayed
        self.assertContains(resp, "do not match")
        self.assertFalse(
            User.objects.filter(email="new@su.edu.ye").exists()
        )

    def test_bad_student_id_format_is_rejected(self):
        resp = self.client.post(
            reverse("student_register"),
            self._payload(student_id="abc"),
        )
        self.assertContains(resp, "7 to 10 digits")
        self.assertFalse(
            User.objects.filter(email="new@su.edu.ye").exists()
        )

    def test_duplicate_student_id_is_rejected(self):
        self.client.post(reverse("student_register"), self._payload())
        resp = self.client.post(
            reverse("student_register"),
            self._payload(email="another@su.edu.ye"),
        )
        self.assertContains(resp, "already registered")

    def test_valid_registration_succeeds(self):
        resp = self.client.post(
            reverse("student_register"), self._payload(),
        )
        self.assertRedirects(resp, reverse("login"))
        u = User.objects.get(email="new@su.edu.ye")
        self.assertEqual(u.role, User.Role.STUDENT)
        self.assertEqual(u.status, User.Status.ACTIVE)
        self.assertEqual(u.student_id, "24160126")

    def test_department_dropdown_contains_required_choices(self):
        from accounts.forms import StudentRegistrationForm
        form = StudentRegistrationForm()
        choices = [c[0] for c in form.fields["department"].choices if c[0]]
        self.assertEqual(choices, ["IS", "CS", "IT", "CYS", "AI", "DS"])

        resp = self.client.get(reverse("student_register"))
        self.assertEqual(resp.status_code, 200)
        for dept in ["IS", "CS", "IT", "CYS", "AI", "DS"]:
            self.assertContains(resp, f'<option value="{dept}">{dept}</option>')

    def test_registration_with_named_department_choice(self):
        resp = self.client.post(
            reverse("student_register"),
            self._payload(email="is_student@su.edu.ye", student_id="24160999", department="IS"),
        )
        self.assertRedirects(resp, reverse("login"))
        u = User.objects.get(email="is_student@su.edu.ye")
        self.assertIsNotNone(u.department)
        self.assertEqual(u.department.name, "IS")

    def test_invalid_department_choice_is_rejected(self):
        resp = self.client.post(
            reverse("student_register"),
            self._payload(department="INVALID_DEPT"),
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Select a valid department")


# ────────────────────────────────────────────────────────────────────────────
# Fix #5 + #10 — Status message + 3-strike lockout
# ────────────────────────────────────────────────────────────────────────────
class LoginStatusTests(TestCase):
    def test_suspended_user_sees_display_text_not_bound_method(self):
        make_user("susp@su.edu.ye", status=User.Status.SUSPENDED)
        resp = self.client.post(
            reverse("login"),
            {"email": "susp@su.edu.ye", "password": "Passw0rd!"},
        )
        body = resp.content.decode()
        # Human-readable display text
        self.assertIn("Suspended", body)
        # The old bug printed "<bound method ...>"
        self.assertNotIn("bound method", body)

    def test_invited_user_is_told_to_check_email(self):
        make_user("inv@su.edu.ye", status=User.Status.INVITED)
        resp = self.client.post(
            reverse("login"),
            {"email": "inv@su.edu.ye", "password": "Passw0rd!"},
        )
        self.assertContains(resp, "activation")

    def test_three_failed_attempts_locks_account(self):
        u = make_user("victim@su.edu.ye")
        for _ in range(3):
            self.client.post(
                reverse("login"),
                {"email": "victim@su.edu.ye", "password": "wrong"},
            )
        u.refresh_from_db()
        self.assertEqual(u.failed_login_attempts, 3)
        self.assertIsNotNone(u.locked_until)
        self.assertEqual(u.status, User.Status.LOCKED)

        # A 4th attempt with the *correct* password must still be blocked.
        resp = self.client.post(
            reverse("login"),
            {"email": "victim@su.edu.ye", "password": "Passw0rd!"},
        )
        self.assertContains(resp, "locked")

    def test_successful_login_resets_failed_counter(self):
        u = make_user("ok@su.edu.ye")
        u.register_failed_login()
        u.register_failed_login()
        u.refresh_from_db()
        self.assertEqual(u.failed_login_attempts, 2)

        self.client.post(
            reverse("login"),
            {"email": "ok@su.edu.ye", "password": "Passw0rd!"},
        )
        u.refresh_from_db()
        self.assertEqual(u.failed_login_attempts, 0)
        self.assertIsNone(u.locked_until)


# ────────────────────────────────────────────────────────────────────────────
# Fix #11 — Admin self-protection
# ────────────────────────────────────────────────────────────────────────────
class AdminSelfProtectionTests(TestCase):
    def setUp(self):
        self.admin = make_user(
            "admin@su.edu.ye", role=User.Role.ADMIN,
            is_staff=True, is_superuser=True,
        )
        self.client.force_login(self.admin)

    def test_admin_cannot_delete_self(self):
        resp = self.client.post(
            reverse("user_modify", args=[self.admin.pk]),
            {"delete_user": "1"},
        )
        self.assertRedirects(resp, reverse("user_list"))
        self.assertTrue(User.objects.filter(pk=self.admin.pk).exists())

    def test_admin_cannot_demote_self(self):
        resp = self.client.post(
            reverse("user_modify", args=[self.admin.pk]),
            {
                "full_name": "Admin",
                "role": User.Role.STUDENT,
                "status": User.Status.ACTIVE,
                "department": "",
                "academic_degree": User.AcademicDegree.NONE,
                "max_supervision_load": 5,
            },
        )
        self.assertRedirects(resp, reverse("user_list"))
        self.admin.refresh_from_db()
        self.assertEqual(self.admin.role, User.Role.ADMIN)


# ────────────────────────────────────────────────────────────────────────────
# Fix #6 — Navbar typo
# ────────────────────────────────────────────────────────────────────────────
class NavbarTemplateTests(TestCase):
    def test_navbar_toggler_is_well_formed(self):
        html = self.client.get(reverse("login")).content.decode()
        self.assertNotIn("<buttonclass=", html)
        self.assertIn('class="navbar-toggler"', html)


# ────────────────────────────────────────────────────────────────────────────
# Fix #3 (cont.) — Password reset flow uses reverse_lazy correctly
# ────────────────────────────────────────────────────────────────────────────
class PasswordResetFlowTests(TestCase):
    def test_reset_request_redirects_and_sends_email(self):
        make_user("u@su.edu.ye")
        resp = self.client.post(
            reverse("password_reset"), {"email": "u@su.edu.ye"},
        )
        self.assertRedirects(resp, reverse("password_reset_done"))

        # Test runner swaps in the locmem backend, so mail.outbox is populated.
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("u@su.edu.ye", mail.outbox[0].to)
        self.assertIn("/reset/", mail.outbox[0].body)

    def test_unknown_email_still_redirects(self):
        """Password-reset must not leak which emails exist."""
        resp = self.client.post(
            reverse("password_reset"), {"email": "ghost@su.edu.ye"},
        )
        self.assertRedirects(resp, reverse("password_reset_done"))
        self.assertEqual(len(mail.outbox), 0)


# ────────────────────────────────────────────────────────────────────────────
# Audit log
# ────────────────────────────────────────────────────────────────────────────
class AuditLogTests(TestCase):
    def test_login_creates_audit_entry(self):
        make_user("u@su.edu.ye")
        self.client.post(
            reverse("login"),
            {"email": "u@su.edu.ye", "password": "Passw0rd!"},
        )
        self.assertTrue(
            AuditLog.objects.filter(action="USER_LOGIN").exists()
        )

    def test_failed_login_is_audited(self):
        make_user("u@su.edu.ye")
        self.client.post(
            reverse("login"),
            {"email": "u@su.edu.ye", "password": "wrong"},
        )
        self.assertTrue(
            AuditLog.objects.filter(action="FAILED_LOGIN").exists()
        )

    def test_admin_delete_creates_audit_entry(self):
        admin = make_user(
            "admin@su.edu.ye", role=User.Role.ADMIN,
            is_staff=True, is_superuser=True,
        )
        victim = make_user("victim@su.edu.ye")
        self.client.force_login(admin)
        self.client.post(
            reverse("user_modify", args=[victim.pk]),
            {"delete_user": "1"},
        )
        self.assertTrue(
            AuditLog.objects.filter(action="USER_DELETED").exists()
        )


# ────────────────────────────────────────────────────────────────────────────
# Fix #2 (end-to-end) — Staff invite works without a student_id
# ────────────────────────────────────────────────────────────────────────────
class StaffInviteTests(TestCase):
    def setUp(self):
        self.admin = make_user(
            "admin@su.edu.ye", role=User.Role.ADMIN,
            is_staff=True, is_superuser=True,
        )
        self.dept = Department.objects.create(name="CS")
        self.client.force_login(self.admin)

    def test_invite_creates_invited_user_with_null_student_id(self):
        resp = self.client.post(
            reverse("staff_invite"),
            {
                "full_name": "New Supervisor",
                "email": "sup@su.edu.ye",
                "department": self.dept.pk,
                "role": User.Role.SUPERVISOR,
                "academic_degree": User.AcademicDegree.MASTER,
                "expertise": "AI, ML",
                "max_supervision_load": 5,
            },
        )
        self.assertRedirects(resp, reverse("user_list"))

        u = User.objects.get(email="sup@su.edu.ye")
        self.assertEqual(u.role, User.Role.SUPERVISOR)
        self.assertEqual(u.status, User.Status.INVITED)
        self.assertIsNone(u.student_id)              # ← the whole point
        self.assertFalse(u.has_usable_password())    # invited users can't log in yet

    def test_two_invites_in_a_row_dont_collide(self):
        """Before the student_id fix, the second invite raised IntegrityError."""
        for i in (1, 2):
            self.client.post(
                reverse("staff_invite"),
                {
                    "full_name": f"Sup {i}",
                    "email": f"sup{i}@su.edu.ye",
                    "department": self.dept.pk,
                    "role": User.Role.SUPERVISOR,
                    "academic_degree": User.AcademicDegree.MASTER,
                    "expertise": "AI",
                    "max_supervision_load": 5,
                },
            )
        self.assertEqual(
            User.objects.filter(role=User.Role.SUPERVISOR).count(), 2
        )