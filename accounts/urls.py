from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy
from . import views


urlpatterns = [
    # Home / Landing
    path('', views.home_view, name='home'),

    # Accounts Managing
    path('register/', views.student_register_view, name='student_register'),
    path('login/', views.login_view, name='login'),
    path("logout/", views.logout_view, name="logout"),
    path("profile/", views.profile_view, name="profile"),

    # Staff Invitation & Activation
    path("staff/invite/", views.staff_invite_view, name="staff_invite"),
    path("staff/activate/<uidb64>/<token>/", views.activate_staff_account_view, name="activate_staff"),

    # Admin User Management & Audit Log
    path("users/", views.user_list_view, name="user_list"),
    path("users/<uuid:user_id>/modify/", views.user_update_or_delete_view, name="user_modify"),
    path("audit-log/", views.audit_log_view, name="audit_log"),

    # Forgot Password Flow  — reverse_lazy targets are now un-namespaced
    path(
        "password-reset/",
        auth_views.PasswordResetView.as_view(
            template_name="accounts/password_reset_form.html",
            email_template_name="accounts/password_reset_email.html",
            success_url=reverse_lazy("password_reset_done"),
        ),
        name="password_reset",
    ),
    path(
        "password-reset/done/",
        auth_views.PasswordResetDoneView.as_view(
            template_name="accounts/password_reset_done.html"
        ),
        name="password_reset_done",
    ),
    path(
        "reset/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="accounts/password_reset_confirm.html",
            success_url=reverse_lazy("password_reset_complete"),
        ),
        name="password_reset_confirm",
    ),
    path(
        "reset/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="accounts/password_reset_confirm.html",
            success_url=reverse_lazy("password_reset_complete"),
        ),
        name="password_reset_confirm",
    ),
    path(
        "reset/done/",
        auth_views.PasswordResetCompleteView.as_view(
            template_name="accounts/password_reset_complete.html"
        ),
        name="password_reset_complete",
    ),
]
