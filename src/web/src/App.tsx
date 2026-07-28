import { FormEvent, useEffect, useState } from "react";
import { LogOut, Settings } from "lucide-react";

import { AccountSettings } from "@/components/AccountSettings";
import { AdminWorkspace } from "@/components/AdminWorkspace";
import {
  InvitationActivation,
  EmailVerification,
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
  registerSubmitter,
  resendEmailVerification,
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
  const [passwordAgain, setPasswordAgain] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [affiliation, setAffiliation] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState<"login" | "reset" | "register">("login");
  const [message, setMessage] = useState("");
  const [verificationUrl, setVerificationUrl] = useState("");

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    try {
      if (mode === "reset") {
        await requestPasswordReset(email);
        setMessage("如该邮箱存在有效账户，系统将发送密码重置邮件。");
        setError(null);
        return;
      }
      if (mode === "register") {
        if (password !== passwordAgain) {
          setError("两次输入的密码不一致");
          return;
        }
        const result = await registerSubmitter({
          email,
          displayName,
          affiliation,
          password,
        });
        setMessage(result.message);
        setVerificationUrl(result.verification_url ?? "");
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

  const handleVerificationResend = async () => {
    try {
      const result = await resendEmailVerification(email);
      setMessage(result.message);
      setVerificationUrl(result.verification_url ?? "");
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "验证邮件发送失败");
    }
  };

  return (
    <main className="relative flex min-h-screen items-center justify-center bg-slate-50 p-6">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle className="text-2xl">
            {mode === "reset"
              ? "找回密码"
              : mode === "register"
                ? "投稿人注册"
                : "中国哲学社会科学自主知识创新（法学论文）AI辅助评价系统"}
          </CardTitle>
          <CardDescription>
            {mode === "reset"
              ? "输入账户邮箱，系统将发送限时重置链接。"
              : mode === "register"
                ? "投稿人自行注册；编辑、专家和管理员仍由系统邀请开通。"
                : "登录后进入投稿入口、评审工作台或内部后台。"}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit}>
            {mode === "register" ? (
              <>
                <label className="block space-y-3 text-sm font-medium text-slate-700">
                  姓名
                  <Input value={displayName} onChange={(event) => setDisplayName(event.target.value)} required />
                </label>
                <label className="mt-5 block space-y-3 text-sm font-medium text-slate-700">
                  工作单位（选填）
                  <Input value={affiliation} onChange={(event) => setAffiliation(event.target.value)} />
                </label>
              </>
            ) : null}
            <label className="block space-y-3 text-sm font-medium text-slate-700">
              电子邮箱
              <Input type="email" value={email} onChange={(event) => setEmail(event.target.value)} required />
            </label>
            {mode !== "reset" ? (
              <label className="mt-5 block space-y-3 text-sm font-medium text-slate-700">
                密码
                <Input type="password" value={password} onChange={(event) => setPassword(event.target.value)} minLength={mode === "register" ? 12 : undefined} required />
              </label>
            ) : null}
            {mode === "register" ? (
              <label className="mt-5 block space-y-3 text-sm font-medium text-slate-700">
                再次输入密码
                <Input type="password" value={passwordAgain} onChange={(event) => setPasswordAgain(event.target.value)} minLength={12} required />
              </label>
            ) : null}
            <Button type="submit" className="mt-7 w-full">
              {mode === "reset" ? "发送重置邮件" : mode === "register" ? "注册并发送验证邮件" : "登录"}
            </Button>
            <Button
              type="button"
              variant="ghost"
              className="mt-2 w-full"
              onClick={() => {
                setMode(mode === "reset" ? "login" : "reset");
                setError(null);
                setMessage("");
                setVerificationUrl("");
              }}
            >
              {mode === "reset" ? "返回登录" : "忘记密码"}
            </Button>
            <Button
              type="button"
              variant="ghost"
              className="w-full"
              onClick={() => {
                setMode(mode === "register" ? "login" : "register");
                setError(null);
                setMessage("");
                setVerificationUrl("");
              }}
            >
              {mode === "register" ? "已有账户，返回登录" : "投稿人注册"}
            </Button>
            {message ? <p className="rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-700">{message}</p> : null}
            {verificationUrl ? (
              <a className="mt-2 block text-sm text-blue-700 underline" href={verificationUrl}>
                打开本地测试验证链接
              </a>
            ) : null}
            {mode === "register" && message ? (
              <Button
                type="button"
                variant="outline"
                className="mt-2 w-full"
                onClick={() => void handleVerificationResend()}
              >
                重新发送验证邮件
              </Button>
            ) : null}
            {error ? <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p> : null}
          </form>
        </CardContent>
      </Card>
      <footer className="absolute bottom-4 left-0 w-full text-center text-xs text-slate-400">
        沪交ICP备20260213号
      </footer>
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
  if (window.location.pathname === "/verify-email") {
    return <EmailVerification />;
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
            <h1 className="text-lg font-semibold tracking-tight text-slate-950">自主知识创新法学评价系统</h1>
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
