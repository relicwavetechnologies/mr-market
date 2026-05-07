import { useState } from "react";
import { X } from "lucide-react";
import { useAuthStore } from "@/stores/authStore";

export function AuthModal() {
  const [email, setEmail] = useState("");
  const login = useAuthStore((s) => s.login);
  const setShowAuthModal = useAuthStore((s) => s.setShowAuthModal);

  const handleEmailLogin = async () => {
    if (!email.trim()) return;
    await login(email.trim(), "");
  };

  const handleClose = () => {
    setShowAuthModal(false);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/70 backdrop-blur-sm"
        onClick={handleClose}
      />

      {/* Modal card */}
      <div className="relative z-10 mx-4 w-full max-w-md rounded-2xl border border-border bg-bg-secondary p-8">
        {/* Close button */}
        <button
          onClick={handleClose}
          className="absolute right-4 top-4 rounded-lg p-1.5 text-text-muted transition-colors hover:bg-bg-hover hover:text-text-primary"
        >
          <X size={18} />
        </button>

        {/* Heading */}
        <h2 className="mb-2 text-center text-2xl font-semibold leading-tight text-text-primary">
          Sign up below to unlock the full
          <br />
          potential of Mr. Market
        </h2>
        <p className="mb-8 text-center text-sm text-text-muted">
          By continuing, you agree to our privacy policy.
        </p>

        {/* Social login buttons */}
        <div className="space-y-3">
          <button
            onClick={() => login("user@gmail.com", "")}
            className="flex w-full items-center justify-center gap-3 rounded-xl border border-border bg-bg-tertiary px-4 py-3 text-sm font-medium text-text-primary transition-colors hover:bg-bg-hover"
          >
            <svg viewBox="0 0 24 24" width="18" height="18">
              <path
                fill="#4285F4"
                d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z"
              />
              <path
                fill="#34A853"
                d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
              />
              <path
                fill="#FBBC05"
                d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
              />
              <path
                fill="#EA4335"
                d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
              />
            </svg>
            Continue with Google
          </button>

          <button
            onClick={() => login("user@apple.com", "")}
            className="flex w-full items-center justify-center gap-3 rounded-xl border border-border bg-bg-tertiary px-4 py-3 text-sm font-medium text-text-primary transition-colors hover:bg-bg-hover"
          >
            <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor">
              <path d="M17.05 20.28c-.98.95-2.05.88-3.08.4-1.09-.5-2.08-.48-3.24 0-1.44.62-2.2.44-3.06-.4C2.79 15.25 3.51 7.59 9.05 7.31c1.35.07 2.29.74 3.08.8 1.18-.24 2.31-.93 3.57-.84 1.51.12 2.65.72 3.4 1.8-3.12 1.87-2.38 5.98.48 7.13-.57 1.5-1.31 2.99-2.54 4.09zM12.03 7.25c-.15-2.23 1.66-4.07 3.74-4.25.29 2.58-2.34 4.5-3.74 4.25z" />
            </svg>
            Continue with Apple
          </button>
        </div>

        {/* Divider */}
        <div className="my-6 flex items-center gap-3">
          <div className="h-px flex-1 bg-border" />
          <span className="text-xs text-text-muted">or</span>
          <div className="h-px flex-1 bg-border" />
        </div>

        {/* Email input */}
        <div className="space-y-3">
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleEmailLogin()}
            placeholder="Enter your email"
            className="w-full rounded-xl border border-border bg-bg-tertiary px-4 py-3 text-sm text-text-primary placeholder-text-muted outline-none transition-colors focus:border-accent"
          />
          <button
            onClick={handleEmailLogin}
            className="w-full rounded-xl bg-bg-tertiary px-4 py-3 text-sm font-medium text-text-secondary transition-colors hover:bg-bg-hover hover:text-text-primary"
          >
            Continue with email
          </button>
        </div>

        {/* Close link */}
        <button
          onClick={handleClose}
          className="mt-6 block w-full text-center text-sm text-text-muted transition-colors hover:text-text-secondary"
        >
          Close
        </button>
      </div>
    </div>
  );
}
