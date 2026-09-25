console.log("Dead Man's Switch Vault loaded");

document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll(".btn").forEach((button) => {
        button.addEventListener("click", () => {
            button.classList.add("dms-button-clicked");

            setTimeout(() => {
                button.classList.remove("dms-button-clicked");
            }, 180);
        });
    });
});