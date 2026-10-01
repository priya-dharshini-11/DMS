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

});