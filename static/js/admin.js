document.addEventListener("DOMContentLoaded", function () {
  var stack = document.querySelector("[data-flash-stack]");
  if (stack) {
    setTimeout(function () {
      stack.classList.add("is-hidden");
    }, 4000);
  }
});

document.addEventListener("click", function (event) {
  var confirmForm = event.target.closest("form[data-confirm]");
  if (confirmForm) {
    var message = confirmForm.getAttribute("data-confirm") || "Are you sure?";
    if (!confirm(message)) {
      event.preventDefault();
      return;
    }
  }

  var promptForm = event.target.closest("form[data-prompt]");
  if (promptForm) {
    var promptText = promptForm.getAttribute("data-prompt") || "Provide a reason";
    var reason = prompt(promptText);
    if (!reason) {
      event.preventDefault();
      return;
    }
    var input = promptForm.querySelector(".js-cancel-reason");
    if (input) input.value = reason;
  }
});
