
import { useEffect, useRef, useState } from "react";
import { api } from "../api";

const suggestions = [
  {
    icon: "✉",
    title: "Summarize today's emails",
    description: "Get a quick overview of your inbox",
  },
  {
    icon: "◉",
    title: "Show my unread emails",
    description: "See what you haven't read yet",
  },
  {
    icon: "✓",
    title: "What needs my attention?",
    description: "Find actions, priorities and deadlines",
  },
  {
    icon: "▤",
    title: "Create a document from my emails",
    description: "Use your assistant's document skills",
  },
];

export default function Chat({
  conversationId,
  onConversationCreated,
  onUnauthorized,
  onToggleSidebar,
}) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const bottomRef = useRef(null);
  const inputRef = useRef(null);

  useEffect(() => {
    let cancelled = false;

    async function loadMessages() {
      setMessages([]);
      setError("");

      if (!conversationId) return;

      try {
        const data = await api.getMessages(conversationId);
        if (!cancelled) setMessages(data.messages || []);
      } catch (err) {
        if (err.message === "UNAUTHORIZED") {
          onUnauthorized();
        } else if (!cancelled) {
          setError(err.message);
        }
      }
    }

    loadMessages();
    return () => {
      cancelled = true;
    };
  }, [conversationId, onUnauthorized]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  async function sendMessage(text = input) {
    const message = text.trim();

    if (!message || loading) return;

    setInput("");
    setError("");
    setMessages((previous) => [
      ...previous,
      { role: "user", content: message },
    ]);
    setLoading(true);

    try {
      const result = await api.sendMessage(
        message,
        conversationId || null
      );

      if (result.conversation_id) {
        onConversationCreated(result.conversation_id);
      }

      setMessages((previous) => [
        ...previous,
        {
          role: "assistant",
          content: result.answer || "I couldn't generate a response.",
        },
      ]);
    } catch (err) {
      if (err.message === "UNAUTHORIZED") {
        onUnauthorized();
      } else {
        setError(err.message);
        setMessages((previous) => [
          ...previous,
          {
            role: "assistant",
            content: "I couldn't complete that request. Please try again.",
          },
        ]);
      }
    } finally {
      setLoading(false);
      inputRef.current?.focus();
    }
  }

  function handleSubmit(event) {
    event.preventDefault();
    sendMessage();
  }

  return (
    <main className="chat-main">
      <header className="chat-header">
        <button
          className="icon-button menu-button"
          onClick={onToggleSidebar}
          aria-label="Open menu"
        >
          ☰
        </button>

        <div>
          <h2>Gmail Assistant</h2>
          <p><span className="status-dot" /> Your AI email companion</p>
        </div>

        <span className="header-badge">AI powered</span>
      </header>

      <section className="conversation">
        {messages.length === 0 && (
          <div className="welcome">
            <div className="welcome-icon">✉</div>
            <p className="eyebrow">YOUR PERSONAL EMAIL ASSISTANT</p>
            <h1>What can I help you with?</h1>
            <p className="welcome-description">
              Ask questions about your Gmail, find important tasks,
              or create documents from your emails.
            </p>

            <div className="suggestion-grid">
              {suggestions.map((item) => (
                <button
                  key={item.title}
                  className="suggestion-card"
                  onClick={() => sendMessage(item.title)}
                  disabled={loading}
                >
                  <span className="suggestion-icon">{item.icon}</span>
                  <strong>{item.title}</strong>
                  <span>{item.description}</span>
                </button>
              ))}
            </div>
          </div>
        )}

        <div className="messages">
          {messages.map((message, index) => (
            <div
              key={`${index}-${message.role}`}
              className={`message-row ${message.role}`}
            >
              {message.role === "assistant" && (
                <div className="message-avatar">✦</div>
              )}

              <div className="message-content">
                <span className="message-author">
                  {message.role === "user" ? "You" : "Gmail Assistant"}
                </span>
                <div className="message-bubble">
                  {message.content}
                </div>
              </div>
            </div>
          ))}

          {loading && (
            <div className="message-row assistant">
              <div className="message-avatar">✦</div>
              <div className="message-content">
                <span className="message-author">Gmail Assistant</span>
                <div className="message-bubble typing">
                  <span />
                  <span />
                  <span />
                  <span className="typing-label">Thinking...</span>
                </div>
              </div>
            </div>
          )}

          <div ref={bottomRef} />
        </div>
      </section>

      <footer className="composer-area">
        {error && <p className="error-message">{error}</p>}

        <form className="composer" onSubmit={handleSubmit}>
          <textarea
            ref={inputRef}
            value={input}
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={(event) => {
              if (
                event.key === "Enter" &&
                !event.shiftKey &&
                !event.nativeEvent.isComposing
              ) {
                event.preventDefault();
                handleSubmit(event);
              }
            }}
            placeholder="Ask anything about your Gmail..."
            rows={1}
            disabled={loading}
            aria-label="Message your Gmail assistant"
          />

          <button
            type="submit"
            className="send-button"
            disabled={!input.trim() || loading}
            aria-label="Send message"
          >
            ↑
          </button>
        </form>

        <p className="composer-note">
          Your assistant can make mistakes. Verify important email details.
        </p>
      </footer>
    </main>
  );
}
