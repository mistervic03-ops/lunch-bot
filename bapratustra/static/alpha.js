const forms = document.querySelectorAll("[data-remember-name]");
for (const form of forms) {
  const input = form.querySelector('[name="recommended_by"]');
  if (!input) continue;
  if (!input.value) input.value = localStorage.getItem("bapratustra-name") || "";
  form.addEventListener("submit", () => {
    if (input.value.trim()) localStorage.setItem("bapratustra-name", input.value.trim());
  });
}
