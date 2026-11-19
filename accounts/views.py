from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import SetPasswordForm
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.db.models import Q
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils.encoding import force_bytes, force_str
from django.utils.http import (
    urlsafe_base64_decode,
    urlsafe_base64_encode,
    url_has_allowed_host_and_scheme,
)
from .models import User, AuditLog
from .utils import log_audit
from .decorators import role_required
from .forms import (
    AdminUserUpdateForm,
    LoginForm,
    ProfileUpdateForm,
    StaffInviteForm,
    StudentRegistrationForm,
)


# ********************* Home *********************
def home_view(request):
    """
    Public landing page for guests. Authenticated users are redirected
    directly to their role-based dashboard.
    """
    if request.user.is_authenticated:
        return redirect(get_role_dashboard_url(request.user))
    return render(request, "home.html")


# ********************* Role based Dashboards *********************
def get_role_dashboard_url(user):
    """
    Redirect users to their role-based dashboard.
    """
    dashboard_map = {
        User.Role.ADMIN:       "user_list",
        User.Role.COORDINATOR: "profile",
        User.Role.SUPERVISOR:  "profile",
        User.Role.COMMITTEE:   "profile",
        User.Role.STUDENT:     "profile",
    }
    return dashboard_map.get(user.role, "profile")


# ********************* Students Registration *********************
def student_register_view(request):
    if request.user.is_authenticated:
        return redirect(get_role_dashboard_url(request.user))

    if request.method == "POST":
        form = StudentRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.role = User.Role.STUDENT
            user.status = User.Status.ACTIVE
            user.set_password(form.cleaned_data["password"])
            user.save()

            log_audit(
                user=user,
                action="STUDENT_REGISTERED",
                entity_type="User",
                entity_id=user.user_id,
                new_value=f"Student ID: {user.student_id}",
                request=request,
            )
            messages.success(request, "Account created successfully! Please log in.")
            return redirect("login")
    else:
        form = StudentRegistrationForm()

    return render(request, "accounts/student_register.html", {"form": form})


# ********************* Login *********************
def login_view(request):
    if request.user.is_authenticated:
        return redirect(get_role_dashboard_url(request.user))

    next_url = request.POST.get("next") or request.GET.get("next") or ""

    if request.method == "POST":
        form = LoginForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data["email"].lower().strip()
            password = form.cleaned_data["password"]

            user_obj = User.objects.filter(email=email).first()

            # Locked-out users short-circuit before authenticate()
            if user_obj and user_obj.is_temporarily_locked():
                messages.error(
                    request,
                    "Account locked due to 3 failed login attempts. "
                    "Please try again in 15 minutes.",
                )
                return render(
                    request, "accounts/login.html",
                    {"form": form, "next": next_url},
                )

            user = authenticate(request, email=email, password=password)

            if user is None:
                if user_obj:
                    if user_obj.status == User.Status.INVITED:
                        messages.error(
                            request,
                            "Your account is awaiting activation. "
                            "Please check your email for the activation link.",
                        )
                    else:
                        user_obj.register_failed_login()
                        log_audit(
                            user=user_obj,
                            action="FAILED_LOGIN",
                            entity_type="User",
                            entity_id=user_obj.user_id,
                            new_value=f"Failed attempts: {user_obj.failed_login_attempts}",
                            request=request,
                        )
                        if user_obj.failed_login_attempts >= 3:
                            messages.error(
                                request,
                                "Account locked due to 3 failed login attempts. "
                                "Please try again in 15 minutes.",
                            )
                        else:
                            messages.error(request, "Invalid email or password.")
                else:
                    messages.error(request, "Invalid email or password.")

                return render(
                    request, "accounts/login.html",
                    {"form": form, "next": next_url},
                )

            # Authenticated but status must be allowed
            if user.status == User.Status.INVITED:
                messages.error(
                    request,
                    "Your account is awaiting activation. "
                    "Please check your email for the activation link.",
                )
                return render(
                    request, "accounts/login.html",
                    {"form": form, "next": next_url},
                )

            if user.status in [User.Status.SUSPENDED, User.Status.PENDING_VERIFICATION]:
                messages.error(
                    request,
                    f"Your account status is currently "
                    f"'{user.get_status_display()}'. Contact the Administrator.",
                )
                return render(
                    request, "accounts/login.html",
                    {"form": form, "next": next_url},
                )

            user.reset_failed_logins()
            login(request, user)
            log_audit(
                user=user,
                action="USER_LOGIN",
                entity_type="User",
                entity_id=user.user_id,
                request=request,
            )
            messages.success(request, f"Welcome back, {user.full_name}!")

            if next_url and url_has_allowed_host_and_scheme(
                next_url,
                allowed_hosts={request.get_host()},
                require_https=request.is_secure(),
            ):
                return redirect(next_url)
            return redirect(get_role_dashboard_url(user))
    else:
        form = LoginForm()

    return render(
        request, "accounts/login.html",
        {"form": form, "next": next_url},
    )


# ********************* Logout *********************
@login_required
def logout_view(request):
    log_audit(
        user=request.user,
        action="USER_LOGOUT",
        entity_type="User",
        entity_id=request.user.user_id,
        request=request,
    )
    logout(request)
    messages.info(request, "You have been logged out.")
    return redirect("login")


# ********************* Profile *********************
@login_required
def profile_view(request):
    if request.method == "POST":
        form = ProfileUpdateForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            log_audit(
                user=request.user,
                action="PROFILE_UPDATED",
                entity_type="User",
                entity_id=request.user.user_id,
                request=request,
            )
            messages.success(request, "Profile updated successfully.")
            return redirect("profile")
    else:
        form = ProfileUpdateForm(instance=request.user)

    return render(request, "accounts/profile.html", {"form": form})


# ********************* Staff Invite *********************
@role_required(User.Role.ADMIN)
def staff_invite_view(request):
    if request.method == "POST":
        form = StaffInviteForm(request.POST)
        if form.is_valid():
            staff_user = form.save(commit=False)
            staff_user.status = User.Status.INVITED
            staff_user.set_unusable_password()
            staff_user.save()

            uid = urlsafe_base64_encode(force_bytes(staff_user.pk))
            token = default_token_generator.make_token(staff_user)
            activation_path = reverse(
                "activate_staff",
                kwargs={"uidb64": uid, "token": token},
            )
            activation_url = request.build_absolute_uri(activation_path)

            send_mail(
                subject="SGPMS - Staff Account Invitation",
                message=(
                    f"Hello {staff_user.full_name},\n\n"
                    f"An account has been created for you as "
                    f"{staff_user.get_role_display()}.\n"
                    f"Click the link below to set your password and "
                    f"activate your account:\n{activation_url}"
                ),
                from_email="admin@su.edu.ye",
                recipient_list=[staff_user.email],
                fail_silently=True,
            )

            log_audit(
                user=request.user,
                action="STAFF_ACCOUNT_INVITED",
                entity_type="User",
                entity_id=staff_user.user_id,
                new_value=f"Role: {staff_user.role}, Email: {staff_user.email}",
                request=request,
            )
            messages.success(
                request,
                f"Staff account created with status 'Invited'. "
                f"Activation link: {activation_url}",
            )
            return redirect("user_list")
    else:
        form = StaffInviteForm()

    return render(request, "accounts/staff_invite.html", {"form": form})


# ********************* Activate Staff Account *********************
def activate_staff_account_view(request, uidb64, token):
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    if user is not None and default_token_generator.check_token(user, token):
        if request.method == "POST":
            form = SetPasswordForm(user, request.POST)
            if form.is_valid():
                form.save()
                user.status = User.Status.ACTIVE
                user.save(update_fields=["status"])
                log_audit(
                    user=user,
                    action="STAFF_ACCOUNT_ACTIVATED",
                    entity_type="User",
                    entity_id=user.user_id,
                    request=request,
                )
                messages.success(
                    request,
                    "Your password has been set and your account is now active!",
                )
                return redirect("login")
        else:
            form = SetPasswordForm(user)

        for field in form.fields.values():
            field.widget.attrs.setdefault("class", "form-control")

        return render(
            request, "accounts/set_invited_password.html",
            {"form": form, "validlink": True},
        )

    return render(
        request, "accounts/set_invited_password.html",
        {"validlink": False},
    )


# ********************* User List *********************
@role_required(User.Role.ADMIN)
def user_list_view(request):
    query = request.GET.get("q", "").strip()
    role_filter = request.GET.get("role", "")
    status_filter = request.GET.get("status", "")

    users = User.objects.select_related("department").order_by("-created_at")
    if query:
        users = users.filter(
            Q(full_name__icontains=query)
            | Q(email__icontains=query)
            | Q(student_id__icontains=query)
        )
    if role_filter:
        users = users.filter(role=role_filter)
    if status_filter:
        users = users.filter(status=status_filter)

    return render(
        request,
        "accounts/user_list.html",
        {
            "users": users,
            "roles": User.Role.choices,
            "statuses": User.Status.choices,
        },
    )


# ********************* Modify and Delete Users *********************
@role_required(User.Role.ADMIN)
def user_update_or_delete_view(request, user_id):
    target_user = get_object_or_404(User, user_id=user_id)

    if request.method != "POST":
        return redirect("user_list")

    # *** Delete ***
    if "delete_user" in request.POST:
        if target_user == request.user:
            messages.error(request, "You cannot delete your own account.")
            return redirect("user_list")

        email_copy = target_user.email
        target_user.delete()
        log_audit(
            user=request.user,
            action="USER_DELETED",
            entity_type="User",
            entity_id=user_id,
            old_value=email_copy,
            request=request,
        )
        messages.warning(request, f"User {email_copy} deleted.")
        return redirect("user_list")

    # *** Update ***
    old_state = f"Role={target_user.role}, Status={target_user.status}"
    form = AdminUserUpdateForm(request.POST, instance=target_user)

    if form.is_valid():
        updated = form.save(commit=False)

        if target_user == request.user and updated.role != User.Role.ADMIN:
            messages.error(request, "You cannot demote your own admin account.")
            return redirect("user_list")

        updated.save()
        log_audit(
            user=request.user,
            action="USER_MODIFIED",
            entity_type="User",
            entity_id=updated.user_id,
            old_value=old_state,
            new_value=f"Role={updated.role}, Status={updated.status}",
            request=request,
        )
        messages.success(request, f"Updated {updated.full_name} successfully.")
        return redirect("user_list")

    # Validation failed - surface the errors instead of silent redirect
    error_summary = "; ".join(
        f"{field}: {', '.join(errs)}" for field, errs in form.errors.items()
    )
    messages.error(request, f"Could not update user. {error_summary}")
    return redirect("user_list")


# ************************* Audit Log *************************
@role_required(User.Role.ADMIN)
def audit_log_view(request):
    action_filter = request.GET.get("action", "").strip()
    user_query = request.GET.get("user", "").strip()

    logs = AuditLog.objects.select_related("user").all()
    if action_filter:
        logs = logs.filter(action__icontains=action_filter)
    if user_query:
        logs = logs.filter(
            Q(user__full_name__icontains=user_query)
            | Q(user__email__icontains=user_query)
        )

    return render(request, "accounts/audit_log.html", {"logs": logs[:200]})