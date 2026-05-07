import { useNavigate } from 'react-router-dom';
import { ArrowLeft, Bug, Moon, Sun } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Separator } from '@/components/ui/separator';
import { useThemeStore } from '@/stores/themeStore';
import { useAuthStore } from '@/stores/authStore';
import { toast } from '@/stores/toastStore';

export function SettingsPage() {
  const navigate = useNavigate();
  const theme = useThemeStore((s) => s.theme);
  const toggleTheme = useThemeStore((s) => s.toggleTheme);
  const user = useAuthStore((s) => s.user);

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-y-auto bg-background">
      <header className="flex h-12 shrink-0 items-center gap-3 border-b border-border/60 px-4">
        <Button
          variant="ghost"
          size="icon-sm"
          onClick={() => navigate(-1)}
          aria-label="Back"
          className="text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="size-4" />
        </Button>
        <h1 className="text-[14px] font-medium text-foreground">Settings</h1>
      </header>

      <div className="mx-auto w-full max-w-2xl px-6 py-10">
        <div className="space-y-10">
          <Section
            title="Account"
            description="Your sign-in identity. Email address is your unique identifier."
          >
            {user ? (
              <Row label="Signed in as">
                <span className="text-[13px] text-foreground">{user.email}</span>
              </Row>
            ) : (
              <p className="text-[13px] text-muted-foreground">
                Not signed in. Click the avatar in the sidebar to sign up or log in.
              </p>
            )}
          </Section>

          <Separator className="bg-border/60" />

          <Section
            title="Appearance"
            description="Theme follows your last choice. Stored locally — not synced."
          >
            <Row label="Theme">
              <Button
                variant="outline"
                size="sm"
                onClick={toggleTheme}
                className="h-8 gap-2 border-border/80"
              >
                {theme === 'dark' ? (
                  <>
                    <Sun className="size-3.5" /> Switch to light
                  </>
                ) : (
                  <>
                    <Moon className="size-3.5" /> Switch to dark
                  </>
                )}
              </Button>
            </Row>
          </Section>

          <Separator className="bg-border/60" />

          <Section
            title="Debug"
            description="Internal-only. Use these to exercise UI surfaces without driving them from the backend."
          >
            <Row label="Toast — info">
              <Button
                variant="outline"
                size="sm"
                onClick={() =>
                  toast.info({ message: 'Heads up — this is an info toast.' })
                }
                className="h-8 gap-2 border-border/80"
              >
                <Bug className="size-3.5" />
                Fire toast
              </Button>
            </Row>
            <Row label="Toast — success">
              <Button
                variant="outline"
                size="sm"
                onClick={() =>
                  toast.success({
                    message: 'Memory saved.',
                    badge: 'Saved',
                  })
                }
                className="h-8 gap-2 border-border/80"
              >
                <Bug className="size-3.5" />
                Fire toast
              </Button>
            </Row>
            <Row label="Toast — warning">
              <Button
                variant="outline"
                size="sm"
                onClick={() =>
                  toast.warning({
                    message: 'OpenAI quota cooldown — retrying soon.',
                  })
                }
                className="h-8 gap-2 border-border/80"
              >
                <Bug className="size-3.5" />
                Fire toast
              </Button>
            </Row>
            <Row label="Toast — error">
              <Button
                variant="outline"
                size="sm"
                onClick={() =>
                  toast.error({ message: 'Stream interrupted. Try again.' })
                }
                className="h-8 gap-2 border-border/80"
              >
                <Bug className="size-3.5" />
                Fire toast
              </Button>
            </Row>
            <Row label="Toast — pro (sticky, with action)">
              <Button
                variant="outline"
                size="sm"
                onClick={() =>
                  toast.pro({
                    message: 'Free preview of advanced search enabled.',
                    action: {
                      label: 'Learn more',
                      onClick: () => toast.info({ message: 'You clicked Learn more.' }),
                    },
                    duration: null,
                  })
                }
                className="h-8 gap-2 border-border/80"
              >
                <Bug className="size-3.5" />
                Fire toast
              </Button>
            </Row>
            <Row label="Toast — burst of 3">
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  toast.info({ message: 'First toast' });
                  setTimeout(() => toast.success({ message: 'Second toast' }), 250);
                  setTimeout(() => toast.warning({ message: 'Third toast' }), 500);
                }}
                className="h-8 gap-2 border-border/80"
              >
                <Bug className="size-3.5" />
                Fire 3
              </Button>
            </Row>
          </Section>
        </div>
      </div>
    </div>
  );
}

function Section({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="space-y-4">
      <div>
        <h2 className="text-[14px] font-semibold text-foreground">{title}</h2>
        {description && (
          <p className="mt-1 text-[12px] text-muted-foreground">{description}</p>
        )}
      </div>
      <div className="space-y-2">{children}</div>
    </section>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4 rounded-lg border border-border/60 bg-card/40 px-4 py-2.5">
      <span className="text-[13px] text-foreground">{label}</span>
      <div className="shrink-0">{children}</div>
    </div>
  );
}
