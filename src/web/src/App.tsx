import { FormEvent, useEffect, useState } from "react";
import { LogOut } from "lucide-react";

import { AdminWorkspace } from "@/components/AdminWorkspace";
import { ReviewWorkspace } from "@/components/ReviewWorkspace";
import { SubmitterPortal } from "@/components/SubmitterPortal";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { getCurrentUser, login, logout } from "@/lib/api";
import { isMockLoginPage } from "@/lib/mockData";
import type { User } from "@/lib/types";
import "./styles.css";

type AppProps = {
  initialUser?: User | null;
};

function LoginForm({ onLoggedIn }: { onLoggedIn: (user: User) => void }) {
  const [email, setEmail] = useState("submitter@example.com");
  const [password, setPassword] = useState("secret123");
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    try {
      const user = await login(email, password);
      setError(null);
      onLoggedIn(user);
    } catch (err) {
      setError(err instanceof Error ? err.message : "登录失败");
    }
  };

  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-50 p-6">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle className="text-2xl">SocialEval Login</CardTitle>
          <CardDescription>登录后进入学生入口、评审工作台或内部后台。</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit}>
            <label className="block space-y-3 text-sm font-medium text-slate-700">
              Email
              <Input value={email} onChange={(event) => setEmail(event.target.value)} />
            </label>
            <label className="mt-5 block space-y-3 text-sm font-medium text-slate-700">
              Password
              <Input type="password" value={password} onChange={(event) => setPassword(event.target.value)} />
            </label>
            <Button type="submit" className="mt-7 w-full">Sign in</Button>
            {error ? <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p> : null}
          </form>
        </CardContent>
      </Card>
    </main>
  );
}

function RoleDashboard({ user }: { user: User }) {
  if (user.role === "submitter") return <SubmitterPortal />;
  if (user.role === "editor" || user.role === "expert") return <ReviewWorkspace user={user} />;
  return <AdminWorkspace />;
}

export function App({ initialUser }: AppProps) {
  const [user, setUser] = useState<User | null | undefined>(initialUser);

  useEffect(() => {
    if (initialUser !== undefined) return;
    if (isMockLoginPage()) {
      setUser(null);
      return;
    }
    void getCurrentUser()
      .then((currentUser) => setUser(currentUser))
      .catch(() => setUser(null));
  }, [initialUser]);

  if (user === undefined) {
    return <div className="flex min-h-screen items-center justify-center bg-slate-50 text-sm text-slate-500">Loading session...</div>;
  }

  if (user === null) return <LoginForm onLoggedIn={setUser} />;

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="sticky top-0 z-20 border-b border-slate-200 bg-white/95 backdrop-blur">
        <div className="mx-auto flex max-w-[1600px] items-center justify-between gap-4 px-4 py-4 sm:px-6 lg:px-8">
          <div>
            <h1 className="text-lg font-semibold tracking-tight text-slate-950">SocialEval</h1>
            <p className="text-sm text-slate-500">{user.display_name ?? user.email}</p>
          </div>
          <Button
            type="button"
            variant="secondary"
            onClick={async () => {
              await logout();
              setUser(null);
            }}
          >
            <LogOut className="h-4 w-4" />
            Sign out
          </Button>
        </div>
      </header>
      <div className="mx-auto max-w-[1600px] px-4 py-6 sm:px-6 lg:px-8">
        <RoleDashboard user={user} />
      </div>
    </div>
  );
}
