import re
from django import forms
from django.contrib.auth.password_validation import validate_password
from .models import User, Department


class BootstrapFormMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            css_class = "form-select" if isinstance(field.widget, forms.Select) else "form-control"
            field.widget.attrs.setdefault("class", css_class)


class DepartmentChoiceField(forms.ChoiceField):
    """
    Dropdown choice field for departments displaying:
    IS, CS, IT, CYS, AI, DS.
    Seamlessly resolves to the corresponding Department model instance,
    while also accepting direct Department PKs/UUIDs for backwards compatibility.
    """
    DEPARTMENT_NAMES = ["IS", "CS", "IT", "CYS", "AI", "DS"]

    def __init__(self, *args, **kwargs):
        choices = [("", "Select Department")] + [(name, name) for name in self.DEPARTMENT_NAMES]
        kwargs.setdefault("choices", choices)
        kwargs.setdefault("required", True)
        super().__init__(*args, **kwargs)

    def prepare_value(self, value):
        if isinstance(value, Department):
            return value.name if value.name in self.DEPARTMENT_NAMES else str(value.pk)
        return value

    def validate(self, value):
        if self.required and not value:
            raise forms.ValidationError("Please select a department.")
        if not value:
            return
        if value in self.DEPARTMENT_NAMES:
            return
        try:
            if Department.objects.filter(pk=value).exists():
                return
        except (ValueError, TypeError):
            pass
        raise forms.ValidationError("Select a valid department.")

    def clean(self, value):
        val = super().clean(value)
        if not val:
            return None

        # 1. Lookup by UUID/PK
        try:
            dept = Department.objects.filter(pk=val).first()
            if dept:
                return dept
        except (ValueError, TypeError):
            dept = None

        # 2. Lookup or create by predefined department name
        if val in self.DEPARTMENT_NAMES:
            dept, _ = Department.objects.get_or_create(name=val)
            return dept

        # 3. Lookup by name
        dept = Department.objects.filter(name=val).first()
        if dept:
            return dept

        raise forms.ValidationError("Select a valid department.")


class StudentRegistrationForm(BootstrapFormMixin, forms.ModelForm):
    department = DepartmentChoiceField(label="Department")
    password = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(attrs={"placeholder": "***********"}),
        validators=[validate_password],
    )
    confirm_password = forms.CharField(
        label="Confirm Password",
        widget=forms.PasswordInput(attrs={"placeholder": "***********"}),
    )

    class Meta:
        model = User
        fields = ["full_name", "email", "student_id", "department", "phone"]
        widgets = {
            "full_name":  forms.TextInput(attrs={"placeholder": "Full Name"}),
            "email":      forms.EmailInput(attrs={"placeholder": "student@su.edu.ye"}),
            "student_id": forms.TextInput(attrs={"placeholder": "24160126"}),
            "phone":      forms.TextInput(attrs={"placeholder": "77xxxxxxx"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # student_id + department are optional on the model, but required for students
        self.fields["student_id"].required = True
        self.fields["department"].required = True

    def clean_student_id(self):
        student_id = self.cleaned_data.get("student_id", "").strip()
        if not re.match(r"^\d{7,10}$", student_id):
            raise forms.ValidationError("Student ID must be 7 to 10 digits (e.g., 24160126).")
        if User.objects.filter(student_id=student_id).exists():
            raise forms.ValidationError("This Student ID is already registered.")
        return student_id

    def clean(self):
        cleaned_data = super().clean()
        p1 = cleaned_data.get("password")
        p2 = cleaned_data.get("confirm_password")
        if p1 and p2 and p1 != p2:
            self.add_error("confirm_password", "Passwords do not match.")
        return cleaned_data


class LoginForm(BootstrapFormMixin, forms.Form):
    email = forms.EmailField(
        label="Email Address",
        widget=forms.EmailInput(attrs={"placeholder": "user@su.edu.ye", "autofocus": True}),
    )
    password = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(attrs={"placeholder": "••••••••"}),
    )


class StaffInviteForm(BootstrapFormMixin, forms.ModelForm):
    ROLE_CHOICES = [
        (User.Role.SUPERVISOR, "Supervisor"),
        (User.Role.COMMITTEE, "Committee Member"),
        (User.Role.COORDINATOR, "Coordinator"),
        (User.Role.ADMIN, "Administrator"),
    ]
    role = forms.ChoiceField(choices=ROLE_CHOICES)

    class Meta:
        model = User
        fields = [
            "full_name",
            "email",
            "department",
            "role",
            "academic_degree",
            "expertise",
            "max_supervision_load",
        ]


class ProfileUpdateForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = User
        fields = ["full_name", "phone", "department", "academic_degree", "expertise"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.role == User.Role.STUDENT:
            self.fields.pop("academic_degree", None)
            self.fields.pop("expertise", None)


class AdminUserUpdateForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = User
        fields = [
            "full_name", "role", "status", "department",
            "academic_degree", "max_supervision_load",
        ]
