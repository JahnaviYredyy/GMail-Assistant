
const API_BASE = (
  import.meta.env.VITE_API_BASE_URL || "http://localhost:8000"
).replace(/\/+$/, "");

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    credentials: "include",
    headers: {
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...options.headers,
    },
  });

  if (response.status === 401) {
    throw new Error("UNAUTHORIZED");
  }

  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail || "Something went wrong.");
  }

  if (response.status === 204) {
    return null;
  }

  return response.json();
}

export const api = {
  getCurrentUser: () => request("/api/auth/me"),

  loginWithGoogle: () => {
    window.location.assign(`${API_BASE}/auth/google`);
  },

  logout: () =>
    request("/api/auth/logout", {
      method: "POST",
    }),

  getChats: () => request("/api/chats"),

  getMessages: (conversationId) =>
    request(
      `/api/chats/${encodeURIComponent(conversationId)}/messages`
    ),

  sendMessage: (message, conversationId) =>
    request("/api/chat", {
      method: "POST",
      body: JSON.stringify({
        message,
        conversation_id: conversationId,
      }),
    }),
};
