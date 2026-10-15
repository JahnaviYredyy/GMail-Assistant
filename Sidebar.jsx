
export default function Sidebar({
  chats,
  activeChat,
  onNewChat,
  onSelectChat,
  onLogout,
  user,
  mobileOpen,
  onClose,
}) {
  return (
    <>
      {mobileOpen && (
        <button
          className="sidebar-overlay"
          aria-label="Close sidebar"
          onClick={onClose}
        />
      )}

      <aside className={`sidebar ${mobileOpen ? "sidebar-open" : ""}`}>
        <div className="sidebar-brand">
          <span className="brand-icon small">✉</span>
          <span>Gmail Assistant</span>
          <button
            className="icon-button mobile-close"
            onClick={onClose}
            aria-label="Close sidebar"
          >
            ×
          </button>
        </div>

        <button className="new-chat-button" onClick={onNewChat}>
          <span>＋</span> New chat
        </button>

        <p className="sidebar-label">YOUR CONVERSATIONS</p>

        <div className="chat-history">
          {chats.map((chat) => (
            <button
              key={chat.id}
              className={`history-item ${
                activeChat === chat.id ? "active" : ""
              }`}
              onClick={() => {
                onSelectChat(chat.id);
                onClose();
              }}
              title={chat.title}
            >
              <span>◷</span>
              <span className="history-title">{chat.title}</span>
            </button>
          ))}

          {chats.length === 0 && (
            <p className="empty-history">Your chats will appear here.</p>
          )}
        </div>

        <div className="sidebar-footer">
          <div className="user-avatar">
            {(user?.name || user?.email || "U")[0].toUpperCase()}
          </div>

          <div className="user-info">
            <strong>{user?.name || "Signed-in user"}</strong>
            <span>{user?.email || ""}</span>
          </div>

          <button
            className="icon-button"
            onClick={onLogout}
            title="Sign out"
            aria-label="Sign out"
          >
            ↪
          </button>
        </div>
      </aside>
    </>
  );
}
