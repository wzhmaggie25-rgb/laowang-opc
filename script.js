const dialogs = [...document.querySelectorAll("dialog")];
const toast = document.getElementById("toast");
let toastTimer;
function notify(message) {
  (document.querySelector("dialog[open]") || document.body).appendChild(toast);
  toast.textContent = message;
  toast.classList.add("visible");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove("visible"), 2600);
}
document.querySelectorAll("[data-dialog]").forEach(button => {
  button.addEventListener("click", () => {
    document.querySelectorAll("dialog[open]").forEach(dialog => dialog.close());
    document.getElementById(button.dataset.dialog).showModal();
  });
});
dialogs.forEach(dialog => {
  dialog.querySelector(".close-dialog").addEventListener("click", () => dialog.close());
  dialog.addEventListener("click", event => {
    const rect = dialog.getBoundingClientRect();
    if (event.target === dialog && (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom)) dialog.close();
  });
  dialog.querySelectorAll("[data-close]").forEach(link => link.addEventListener("click", () => dialog.close()));
});
async function copy(text) {
  try {
    await navigator.clipboard.writeText(text);
    notify("已复制。");
  } catch {
    const area = document.createElement("textarea");
    area.value = text;
    area.style.position = "fixed";
    area.style.opacity = "0";
    (document.querySelector("dialog[open]") || document.body).appendChild(area);
    area.select();
    const copied = document.execCommand("copy");
    area.remove();
    notify(copied ? "已复制。" : "暂时无法复制，请手动复制页面里的内容。");
  }
}
document.querySelectorAll("[data-copy]").forEach(button => {
  button.addEventListener("click", () => copy(button.dataset.copy));
});

// Reading pages already link to /#about. Reuse the existing introduction.
const aboutDialog = document.getElementById("about-dialog");
function syncAboutHash() {
  if (location.hash === "#about") {
    dialogs.forEach(dialog => {
      if (dialog !== aboutDialog && dialog.open) dialog.close();
    });
    if (!aboutDialog.open) aboutDialog.showModal();
  } else if (aboutDialog.open) {
    aboutDialog.close();
  }
}
aboutDialog.addEventListener("close", () => {
  if (location.hash === "#about") {
    history.replaceState(null, "", location.pathname + location.search + "#home");
  }
});
window.addEventListener("hashchange", syncAboutHash);
syncAboutHash();
