const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

export async function logout() {
  try {
    await fetch(`${API_URL}/auth/logout/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
    });
  } catch {
    // ignore — we're logging out anyway
  }
  localStorage.removeItem("access");
  localStorage.removeItem("refresh"); // cleanup legacy
  window.location.href = "/login";
}
