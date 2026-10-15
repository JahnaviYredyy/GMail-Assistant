
import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import Login from "./components/Login";
import Chat from "./components/Chat";
import Sidebar from "./components/Sidebar";

export default function App() {
  const [user, setUser] = useState(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [authError, setAuthError] = useState("");
  const [chats, setChats] = useState([]);
  const [conversationId, setConversationId] = useState(null);
  const [mobileOpen, setMobileOpen] = useState(false);

  const refreshChats = useCallback(async () => {
    try {
      const data = await api.getChats();
      setChats(data.chats || []);
    } catch (err) {
      if (err.message === "UNAUTHORIZED") {
        setUser(null);
      } else {
        console.error("Could not load chats:", err.message);
      }
    }
  }, []);

  const handleUnauthorized = useCallback(() => {
    setUser(null);
    setChats([]);
    setConversationId(null);
    setAuthError("Your session has expired. Please sign in again.");
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function initialize() {
      try {
        const data = await api.getCurrentUser();

        if (cancelled) return;

        setUser(data.user);
        const chatData = await api.getChats();

        if (!cancelled) setChats(chatData.chats || []);
      } catch (err) {
        if (cancelled) return;

        if (err.message !== "UNAUTHORIZED") {
          setAuthError(
            "Cannot connect to the backend. Make sure the Python server is running."
          );
        }
      } finally {
        if (!cancelled) setAuthLoading(false);
      }
    }

    initialize();
    return () => {
      cancelled = true;
    };
  }, []);

  async function handleLogout() {
    try {
      await api.logout();
    } catch (err) {
      console.error("Logout error:", err.message);
    } finally {
      setUser(null);
      setChats([]);
      setConversationId(null);
      setAuthError("");
    }
  }

  function handleNewChat() {
    setConversationId(null);
    setMobileOpen(false);
  }

  function handleConversationCreated(id) {
    setConversationId(id);
    refreshChats();
  }

  if (authLoading) {
    return (
      <div className="loading-screen">
        <div className="welcome-icon">✉</div>
        <p>Connecting to Gmail Assistant...</p>
      </div>
    );
  }

  if (!user) {
    return <Login error={authError} />;
  }

  return (
    <div className="app-shell">
      <Sidebar
        user={user}
        chats={chats}
        activeChat={conversationId}
        onNewChat={handleNewChat}
        onSelectChat={setConversationId}
        onLogout={handleLogout}
        mobileOpen={mobileOpen}
        onClose={() => setMobileOpen(false)}
      />

      <Chat
        key={conversationId || "new-chat"}
        conversationId={conversationId}
        onConversationCreated={handleConversationCreated}
        onUnauthorized={handleUnauthorized}
        onToggleSidebar={() => setMobileOpen(true)}
      />
    </div>
  );
}
