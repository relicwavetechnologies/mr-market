import { useState } from 'react';
import { Apple, Loader2, Lock, Mail, UserRound } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Separator } from '@/components/ui/separator';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { useAuthStore } from '@/stores/authStore';

type Mode = 'login' | 'signup';

export function AuthModal() {
  const [mode, setMode] = useState<Mode>('login');
  const [email, setEmail] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [password, setPassword] = useState('');
  const [localError, setLocalError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const login = useAuthStore((s) => s.login);
  const signup = useAuthStore((s) => s.signup);
  const showAuthModal = useAuthStore((s) => s.showAuthModal);
  const setShowAuthModal = useAuthStore((s) => s.setShowAuthModal);
  const authError = useAuthStore((s) => s.authError);

  const handleSubmit = async () => {
    const trimmedEmail = email.trim();
    const trimmedName = displayName.trim();
    if (!trimmedEmail || !password || (mode === 'signup' && !trimmedName)) return;
    setSubmitting(true);
    setLocalError(null);
    try {
      if (mode === 'signup') await signup(trimmedEmail, password, trimmedName);
      else await login(trimmedEmail, password);
      setEmail('');
      setDisplayName('');
      setPassword('');
    } catch (err) {
      setLocalError((err as Error).message || 'Authentication failed');
    } finally {
      setSubmitting(false);
    }
  };

  const submitDisabled =
    submitting || !email.trim() || !password || (mode === 'signup' && !displayName.trim());

  return (
    <Dialog open={showAuthModal} onOpenChange={setShowAuthModal}>
      <DialogContent className="max-w-md gap-0 border-border/80 bg-card p-7 sm:rounded-2xl">
        <DialogHeader className="space-y-2 text-center">
          <DialogTitle className="text-center font-serif text-2xl font-normal leading-tight tracking-tight">
            Sign in to Midas
          </DialogTitle>
          <DialogDescription className="text-center text-xs text-muted-foreground">
            Keep your research history available across sessions.
          </DialogDescription>
        </DialogHeader>

        <div className="mt-6 space-y-2.5">
          <Button
            variant="outline"
            disabled
            className="h-11 w-full justify-center gap-3 rounded-xl border-border/80 bg-secondary/40 text-sm font-medium"
            title="Coming soon"
          >
            <svg viewBox="0 0 24 24" className="size-4">
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
          </Button>

          <Button
            variant="outline"
            disabled
            className="h-11 w-full justify-center gap-3 rounded-xl border-border/80 bg-secondary/40 text-sm font-medium"
            title="Coming soon"
          >
            <Apple className="size-4" />
            Continue with Apple
          </Button>
        </div>

        <div className="my-5 flex items-center gap-3">
          <Separator className="flex-1 bg-border/60" />
          <span className="text-[11px] uppercase tracking-wider text-muted-foreground">or</span>
          <Separator className="flex-1 bg-border/60" />
        </div>

        <Tabs value={mode} onValueChange={(value) => setMode(value as Mode)}>
          <TabsList className="mb-4 grid h-9 grid-cols-2 rounded-xl bg-secondary/50 p-1">
            <TabsTrigger value="login" className="rounded-lg text-xs">
              Login
            </TabsTrigger>
            <TabsTrigger value="signup" className="rounded-lg text-xs">
              Sign up
            </TabsTrigger>
          </TabsList>
        </Tabs>

        <div className="space-y-2.5">
          {mode === 'signup' && (
            <div className="relative">
              <UserRound className="absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
              <input
                type="text"
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                placeholder="Display name"
                className="h-11 w-full rounded-xl border border-border/80 bg-secondary/40 pl-10 pr-3 text-sm text-foreground placeholder:text-muted-foreground outline-none transition-colors focus:border-foreground/40"
              />
            </div>
          )}
          <div className="relative">
            <Mail className="absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="Email"
              autoComplete="email"
              className="h-11 w-full rounded-xl border border-border/80 bg-secondary/40 pl-10 pr-3 text-sm text-foreground placeholder:text-muted-foreground outline-none transition-colors focus:border-foreground/40"
            />
          </div>
          <div className="relative">
            <Lock className="absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && void handleSubmit()}
              placeholder="Password"
              autoComplete={mode === 'signup' ? 'new-password' : 'current-password'}
              className="h-11 w-full rounded-xl border border-border/80 bg-secondary/40 pl-10 pr-3 text-sm text-foreground placeholder:text-muted-foreground outline-none transition-colors focus:border-foreground/40"
            />
          </div>
          {(localError || authError) && (
            <p className="rounded-lg border border-accent-red/30 bg-accent-red/5 px-3 py-2 text-xs text-accent-red">
              {localError || authError}
            </p>
          )}
          <Button
            onClick={handleSubmit}
            disabled={submitDisabled}
            className="h-11 w-full rounded-xl bg-foreground text-sm font-medium text-background hover:bg-foreground/90"
          >
            {submitting && <Loader2 className="mr-2 size-4 animate-spin" />}
            {mode === 'signup' ? 'Create account' : 'Login'}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
