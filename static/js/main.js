console.log("Dead Man's Switch Vault loaded");

document.addEventListener("DOMContentLoaded", () => {

    // Button click feedback
    document.querySelectorAll(".btn").forEach((button) => {
        button.addEventListener("click", () => {
            button.classList.add("dms-button-clicked");

            setTimeout(() => {
                button.classList.remove("dms-button-clicked");
            }, 180);
        });
    });


    // Password show / hide
    document.querySelectorAll(".dms-password-toggle").forEach((toggle) => {

        toggle.addEventListener("click", () => {

            const passwordInput = toggle
                .closest(".dms-password-input")
                .querySelector("input");

            const icon = toggle.querySelector(".dms-eye-icon");

            const isPassword = passwordInput.type === "password";

            passwordInput.type = isPassword ? "text" : "password";

            toggle.setAttribute(
                "aria-label",
                isPassword ? "Hide password" : "Show password"
            );

            toggle.setAttribute(
                "aria-pressed",
                isPassword ? "true" : "false"
            );

            if (icon) {
                if (isPassword) {
                    // Eye-off
                    icon.innerHTML = `
                        <path d="M3 3l18 18"/>
                        <path d="M10.6 10.6a2 2 0 0 0 2.8 2.8"/>
                        <path d="M9.9 5.2A10.8 10.8 0 0 1 12 5c6.5 0 10 7 10 7a18.5 18.5 0 0 1-3.1 3.9"/>
                        <path d="M6.1 6.1C3.6 7.8 2 12 2 12s3.5 7 10 7a10.8 10.8 0 0 0 2.1-.2"/>
                    `;
                } else {
                    // Eye
                    icon.innerHTML = `
                        <path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6S2 12 2 12Z"/>
                        <circle cx="12" cy="12" r="2.5"/>
                    `;
                }
            }

        });

    });
        // Logout confirmation
    const logoutModal = document.getElementById("logoutConfirmModal");
    const logoutLinks = document.querySelectorAll(
        ".dms-logout-link[data-logout-confirm]"
    );
    const logoutCancelButtons = document.querySelectorAll(
        "[data-logout-cancel]"
    );

    if (logoutModal) {

        const openLogoutModal = (event) => {
            event.preventDefault();

            logoutModal.classList.add("is-open");
            logoutModal.setAttribute("aria-hidden", "false");

            document.body.classList.add("dms-modal-open");
        };

        const closeLogoutModal = () => {
            logoutModal.classList.remove("is-open");
            logoutModal.setAttribute("aria-hidden", "true");

            document.body.classList.remove("dms-modal-open");
        };

        logoutLinks.forEach((link) => {
            link.addEventListener("click", openLogoutModal);
        });

        logoutCancelButtons.forEach((button) => {
            button.addEventListener("click", closeLogoutModal);
        });

        document.addEventListener("keydown", (event) => {

            if (
                event.key === "Escape" &&
                logoutModal.classList.contains("is-open")
            ) {
                closeLogoutModal();
            }

        });

    }

    // Reusable confirmation modal
    const confirmModal = document.getElementById("dmsConfirmModal");
    const confirmTitle = document.getElementById("dmsConfirmTitle");
    const confirmMessage = document.getElementById("dmsConfirmMessage");
    const confirmSubmit = document.getElementById("dmsConfirmSubmit");
    const confirmCancelButtons = document.querySelectorAll(
        "[data-confirm-cancel]"
    );

    let pendingConfirmationForm = null;

    if (confirmModal && confirmTitle && confirmMessage && confirmSubmit) {

        const closeConfirmModal = () => {
            confirmModal.classList.remove("is-open");
            confirmModal.setAttribute("aria-hidden", "true");
            document.body.classList.remove("dms-modal-open");

            pendingConfirmationForm = null;
        };

        const openConfirmModal = (form) => {
            pendingConfirmationForm = form;

            confirmTitle.textContent =
                form.dataset.confirmTitle || "Are you sure?";

            confirmMessage.textContent =
                form.dataset.confirmMessage ||
                "Please confirm that you want to continue.";

            confirmSubmit.textContent =
                form.dataset.confirmAction || "Confirm";

            confirmSubmit.classList.remove(
                "btn-danger",
                "btn-primary",
                "btn-warning",
                "btn-success",
                "btn-dark"
            );

            confirmSubmit.classList.add(
                form.dataset.confirmButton || "btn-danger"
            );

            confirmModal.classList.add("is-open");
            confirmModal.setAttribute("aria-hidden", "false");
            document.body.classList.add("dms-modal-open");

            confirmSubmit.focus();
        };

        document.querySelectorAll("form[data-confirm]").forEach((form) => {
            form.addEventListener("submit", (event) => {
                if (form.dataset.confirmed === "true") {
                    delete form.dataset.confirmed;
                    return;
                }

                event.preventDefault();
                openConfirmModal(form);
            });
        });

        confirmSubmit.addEventListener("click", () => {
            if (!pendingConfirmationForm) {
                closeConfirmModal();
                return;
            }

            const form = pendingConfirmationForm;

            form.dataset.confirmed = "true";
            closeConfirmModal();

            form.submit();
        });

        confirmCancelButtons.forEach((button) => {
            button.addEventListener("click", closeConfirmModal);
        });

        document.addEventListener("keydown", (event) => {
            if (
                event.key === "Escape" &&
                confirmModal.classList.contains("is-open")
            ) {
                closeConfirmModal();
            }
        });
    }


});