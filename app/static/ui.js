function openModal() {
    document.getElementById("modal").classList.remove("hidden");
}

function closeModal() {
    document.getElementById("modal").classList.add("hidden");
}

// Toast rendering
function showToast(message, type = "success") {
    const container = document.getElementById("toast-container");

    const toast = document.createElement("div");
    toast.className = `px-4 py-2 text-white rounded shadow ${
        type === "success" ? "bg-green-600" : "bg-red-600"
    }`;

    toast.innerText = message;

    container.appendChild(toast);

    setTimeout(() => toast.remove(), 3000);
}

// Let backend trigger toasts
document.body.addEventListener("htmx:afterSwap", (e) => {
    if (e.detail.target.id === "toast-container") {
        openToastArea();
    }
});
