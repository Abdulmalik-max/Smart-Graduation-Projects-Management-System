function toggleDir() {
    const html = document.getElementById("htmlRoot");
    const css = document.getElementById("bootstrapCss");
    if (html.getAttribute("dir") === "ltr") {
        html.setAttribute("dir", "rtl");
        html.setAttribute("lang", "ar");
        css.href = "{% static 'css/bootstrap.rtl.min.css' %}";
    } else {
        html.setAttribute("dir", "ltr");
        html.setAttribute("lang", "en");
        css.href = "{% static 'css/bootstrap.min.css' %}";
    }
}

function togglePassword(inputId, btn) {
    const input = document.getElementById(inputId);
    const icon = btn.querySelector('i');
    if (input.type === "password") {
        input.type = "text";
        icon.classList.replace("bi-eye", "bi-eye-slash");
    }
    else {
        input.type = "password";
        icon.classList.replace("bi-eye-slash", "bi-eye");
    }
}