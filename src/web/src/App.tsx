import { FormEvent, useEffect, useState } from "react";
import { LogOut, Settings } from "lucide-react";

import { AccountSettings } from "@/components/AccountSettings";
import { AdminWorkspace } from "@/components/AdminWorkspace";
import {
  InvitationActivation,
  MfaChallenge,
  PasswordResetConfirmation,
} from "@/components/AuthFlows";
import { EditorialWorkspace } from "@/components/EditorialWorkspace";
import { ReviewWorkspace } from "@/components/ReviewWorkspace";
import { SubmitterPortal } from "@/components/SubmitterPortal";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  getCurrentUser,
  login,
  logout,
  requestPasswordReset,
} from "@/lib/api";
import { isMockLoginPage } from "@/lib/mockData";
import type { LoginChallenge, User } from "@/lib/types";
import "./styles.css";

type AppProps = {
  initialUser?: User | null;
};

function LoginForm({
  onLoggedIn,
  onChallenge,
}: {
  onLoggedIn: (user: User) => void;
  onChallenge: (challenge: LoginChallenge) => void;
}) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [resetMode, setResetMode] = useState(false);
  const [message, setMessage] = useState("");

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    try {
      if (resetMode) {
        await requestPasswordReset(email);
        setMessage("如该邮箱存在有效账户，系统将发送密码重置邮件。");
        setError(null);
        return;
      }
      const result = await login(email, password);
      setError(null);
      if ("status" in result) {
        onChallenge(result);
      } else {
        onLoggedIn(result);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "登录失败");
    }
  };

  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-50 p-6">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle className="text-2xl">
            {resetMode ? "找回密码" : "中国自主知识创新（法学论文）评价系统"}
          </CardTitle>
          <CardDescription>
            {resetMode
              ? "输入账户邮箱，系统将发送限时重置链接。"
              : "登录后进入投稿入口、评审工作台或内部后台。"}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit}>
            <label className="block space-y-3 text-sm font-medium text-slate-700">
              电子邮箱
              <Input value={email} onChange={(event) => setEmail(event.target.value)} />
            </label>
            {!resetMode ? (
              <label className="mt-5 block space-y-3 text-sm font-medium text-slate-700">
                密码
                <Input type="password" value={password} onChange={(event) => setPassword(event.target.value)} />
              </label>
            ) : null}
            <Button type="submit" className="mt-7 w-full">
              {resetMode ? "发送重置邮件" : "登录"}
            </Button>
            <Button
              type="button"
              variant="ghost"
              className="mt-2 w-full"
              onClick={() => {
                setResetMode((current) => !current);
                setError(null);
                setMessage("");
              }}
            >
              {resetMode ? "返回登录" : "忘记密码"}
            </Button>
            {message ? <p className="rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-700">{message}</p> : null}
            {error ? <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p> : null}
          </form>
        </CardContent>
      </Card>
    </main>
  );
}

function RoleDashboard({ user }: { user: User }) {
  if (user.role === "submitter") return <SubmitterPortal />;
  if (user.role === "editor") return <EditorialWorkspace user={user} />;
  if (user.role === "expert") return <ReviewWorkspace user={user} />;
  return <AdminWorkspace />;
}

export function App({ initialUser }: AppProps) {
  const [user, setUser] = useState<User | null | undefined>(initialUser);
  const [challenge, setChallenge] = useState<LoginChallenge | null>(null);
  const [showAccount, setShowAccount] = useState(false);

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
    return <div className="flex min-h-screen items-center justify-center bg-slate-50 text-sm text-slate-500">正在加载登录状态……</div>;
  }

  if (window.location.pathname === "/activate") {
    return <InvitationActivation />;
  }
  if (window.location.pathname === "/reset-password") {
    return <PasswordResetConfirmation />;
  }
  if (challenge) {
    return (
      <MfaChallenge
        challenge={challenge}
        onLoggedIn={(loggedInUser) => {
          setChallenge(null);
          setUser(loggedInUser);
        }}
      />
    );
  }
  if (user === null) {
    return (
      <LoginForm
        onLoggedIn={setUser}
        onChallenge={setChallenge}
      />
    );
  }

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="sticky top-0 z-20 border-b border-slate-200 bg-white/95 backdrop-blur">
        <div className="mx-auto flex max-w-[1600px] items-center justify-between gap-4 px-4 py-4 sm:px-6 lg:px-8">
          <div>
            <h1 className="text-lg font-semibold tracking-tight text-slate-950">中国自主知识创新（法学论文）评价系统</h1>
            <p className="text-sm text-slate-500">{user.display_name ?? user.email}</p>
          </div>
          <div className="flex items-center gap-2">
            <Button
              type="button"
              variant="secondary"
              onClick={() => setShowAccount((current) => !current)}
            >
              <Settings className="h-4 w-4" />
              {showAccount ? "返回工作台" : "账户设置"}
            </Button>
            <Button
              type="button"
              variant="secondary"
              onClick={async () => {
                await logout();
                setUser(null);
              }}
            >
              <LogOut className="h-4 w-4" />
              退出登录
            </Button>
          </div>
        </div>
      </header>
      <div className="mx-auto max-w-[1600px] px-4 py-6 sm:px-6 lg:px-8">
        {showAccount ? (
          <AccountSettings user={user} onUserChanged={setUser} />
        ) : (
          <RoleDashboard user={user} />
        )}
      </div>
    </div>
  );
}
