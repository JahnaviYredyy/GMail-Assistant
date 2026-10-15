
import { api } from "../api";

export default function Login({ error }) {
  return (
    <main className="login-page">
      <div className="login-card">
        <div className="brand-icon">✉</div>

        <p className="eyebrow">YOUR PERSONAL EMAIL ASSISTANT</p>
        <h1>Gmail, made simpler.</h1>

        <p className="login-description">
          Find important emails, summarize conversations,
          track deadlines, and create documents using AI.
        </p>

        <button
          className="google-button"
          onClick={api.loginWithGoogle}
        >
          <svg width="20" height="20" viewBox="0 0 48 48">
            <path fill="#EA4335" d="M24 9.5c3.5 0 6.6 1.2 9 3.5l6.7-6.7C35.6 2.4 30.2 0 24 0 14.6 0 6.5 5.4 3 13.2l7.8 6.1C12.5 13.5 17.8 9.5 24 9.5Z"/>
            <path fill="#4285F4" d="M46.1 24.5c0-1.6-.1-3.2-.4-4.7H24v9h12.4c-.6 3-2.3 5.6-4.9 7.3l7.5 5.8c4.4-4.1 7.1-10.1 7.1-17.4Z"/>
            <path fill="#FBBC05" d="M10.8 28.7a14.5 14.5 0 0 1 0-9.4L3 13.2a24 24 0 0 0 0 21.6l7.8-6.1Z"/>
            <path fill="#34A853" d="M24 48c6.5 0 12-2.1 16-6.1l-7.5-5.8c-2.1 1.4-4.9 2.2-8.5 2.2-6.2 0-11.5-4-13.2-9.5L3 34.8C6.5 42.6 14.6 48 24 48Z"/>
          </svg>
          Continue with Google
        </button>

        {error && <p className="error-message">{error}</p>}

        <p className="privacy-note">
          You'll choose your Google account and grant Gmail
          permissions when requested.
        </p>
      </div>
    </main>
  );
}
