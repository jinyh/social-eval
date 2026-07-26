import { FormEvent, useEffect, useState } from "react";

import {
  acceptInvitation,
  confirmEmailVerification,
  confirmMfa,
  confirmPasswordReset,
  setupMfa,
  verifyMfa,
} from "@/lib/api";
import type { LoginChallenge, MfaSetup, User } from "@/lib/types";

import { Button } from "./ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "./ui/card";
import { Input } from "./ui/input";

function tokenFromFragment(): string {
  return new URLSearchParams(window.location.hash.slice(1)).get("token") ?? "";
}

function AuthCard({ children }: { children: React.ReactNode }) {
  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-50 p-6">
      <Card className="w-full max-w-lg">{children}</Card>
    </main>
  );
}

export function InvitationActivation() {
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [passwordAgain, setPasswordAgain] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (password !== passwordAgain) {
      setError("两次输入的密码不一致");
      return;
    }
    try {
      await acceptInvitation(tokenFromFragment(), displayName, password);
      window.history.replaceState(null, "", "/");
      setMessage("账户已经激活，请返回登录。");
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "账户激活失败");
    }
  };

  return (
    <AuthCard>
      <CardHeader>
        <CardTitle>激活账户</CardTitle>
        <CardDescription>设置姓名和至少 12 个字符的登录密码。</CardDescription>
      </CardHeader>
      <CardContent>
        <form className="space-y-4" onSubmit={handleSubmit}>
          <Input value={displayName} onChange={(event) => setDisplayName(event.target.value)} placeholder="姓名" required />
          <Input type="password" value={password} onChange={(event) => setPassword(event.target.value)} placeholder="密码" minLength={12} required />
          <Input type="password" value={passwordAgain} onChange={(event) => setPasswordAgain(event.target.value)} placeholder="再次输入密码" minLength={12} required />
          <Button type="submit" className="w-full">激活账户</Button>
        </form>
        {message ? <p className="mt-4 text-sm text-emerald-700">{message}</p> : null}
        {error ? <p className="mt-4 text-sm text-red-700">{error}</p> : null}
        {message ? <Button className="mt-4 w-full" variant="secondary" onClick={() => window.location.assign("/")}>返回登录</Button> : null}
      </CardContent>
    </AuthCard>
  );
}

export function EmailVerification() {
  const [message, setMessage] = useState("正在验证邮箱……");
  const [error, setError] = useState("");

  useEffect(() => {
    const token = tokenFromFragment();
    if (!token) {
      setMessage("");
      setError("验证链接缺少令牌，请重新发送验证邮件。");
      return;
    }
    void confirmEmailVerification(token)
      .then(() => {
        window.history.replaceState(null, "", "/");
        setMessage("邮箱验证成功，现在可以登录并投稿。");
      })
      .catch((err: unknown) => {
        setMessage("");
        setError(err instanceof Error ? err.message : "邮箱验证失败");
      });
  }, []);

  return (
    <AuthCard>
      <CardHeader>
        <CardTitle>验证投稿邮箱</CardTitle>
        <CardDescription>验证成功后，投稿人账户才会正式启用。</CardDescription>
      </CardHeader>
      <CardContent>
        {message ? <p className="text-sm text-emerald-700">{message}</p> : null}
        {error ? <p className="text-sm text-red-700">{error}</p> : null}
        <Button
          className="mt-4 w-full"
          variant="secondary"
          onClick={() => window.location.assign("/")}
        >
          返回登录
        </Button>
      </CardContent>
    </AuthCard>
  );
}

export function PasswordResetConfirmation() {
  const [password, setPassword] = useState("");
  const [passwordAgain, setPasswordAgain] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (password !== passwordAgain) {
      setError("两次输入的密码不一致");
      return;
    }
    try {
      await confirmPasswordReset(tokenFromFragment(), password);
      window.history.replaceState(null, "", "/");
      setMessage("密码已经重置，所有旧会话和接口密钥均已失效。");
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "密码重置失败");
    }
  };

  return (
    <AuthCard>
      <CardHeader>
        <CardTitle>重置密码</CardTitle>
        <CardDescription>设置至少 12 个字符的新密码。</CardDescription>
      </CardHeader>
      <CardContent>
        <form className="space-y-4" onSubmit={handleSubmit}>
          <Input type="password" value={password} onChange={(event) => setPassword(event.target.value)} placeholder="新密码" minLength={12} required />
          <Input type="password" value={passwordAgain} onChange={(event) => setPasswordAgain(event.target.value)} placeholder="再次输入新密码" minLength={12} required />
          <Button type="submit" className="w-full">重置密码</Button>
        </form>
        {message ? <p className="mt-4 text-sm text-emerald-700">{message}</p> : null}
        {error ? <p className="mt-4 text-sm text-red-700">{error}</p> : null}
        {message ? <Button className="mt-4 w-full" variant="secondary" onClick={() => window.location.assign("/")}>返回登录</Button> : null}
      </CardContent>
    </AuthCard>
  );
}

export function MfaChallenge({
  challenge,
  onLoggedIn,
}: {
  challenge: LoginChallenge;
  onLoggedIn: (user: User) => void;
}) {
  const [setup, setSetup] = useState<MfaSetup | null>(null);
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const [result, setResult] = useState<{ user: User; codes: string[] } | null>(null);

  useEffect(() => {
    if (challenge.status !== "mfa_setup_required") return;
    void setupMfa()
      .then(setSetup)
      .catch((err: unknown) =>
        setError(err instanceof Error ? err.message : "双因素认证初始化失败")
      );
  }, [challenge.status]);

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    try {
      if (challenge.status === "mfa_setup_required") {
        const response = await confirmMfa(code);
        setResult({ user: response.user, codes: response.recovery_codes });
      } else {
        onLoggedIn(await verifyMfa(code));
      }
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "验证码校验失败");
    }
  };

  if (result) {
    return (
      <AuthCard>
        <CardHeader>
          <CardTitle>保存恢复码</CardTitle>
          <CardDescription>每个恢复码只能使用一次，请离线妥善保存。</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 gap-2 rounded-xl bg-slate-100 p-4 font-mono text-sm">
            {result.codes.map((item) => <span key={item}>{item}</span>)}
          </div>
          <Button className="mt-5 w-full" onClick={() => onLoggedIn(result.user)}>我已保存，进入系统</Button>
        </CardContent>
      </AuthCard>
    );
  }

  return (
    <AuthCard>
      <CardHeader>
        <CardTitle>
          {challenge.status === "mfa_setup_required" ? "设置管理员双因素认证" : "双因素认证"}
        </CardTitle>
        <CardDescription>
          {challenge.status === "mfa_setup_required"
            ? "使用认证器扫描二维码并输入动态验证码。"
            : "请输入认证器动态验证码或一次性恢复码。"}
        </CardDescription>
      </CardHeader>
      <CardContent>
        {setup ? (
          <div className="mb-5">
            <div
              className="mx-auto w-52 bg-white p-2"
              dangerouslySetInnerHTML={{ __html: setup.qr_svg }}
            />
            <p className="mt-3 break-all text-xs text-slate-500">手动密钥：{setup.secret}</p>
          </div>
        ) : null}
        <form className="space-y-4" onSubmit={handleSubmit}>
          <Input value={code} onChange={(event) => setCode(event.target.value)} placeholder="动态验证码或恢复码" required />
          <Button type="submit" className="w-full">验证</Button>
        </form>
        {error ? <p className="mt-4 text-sm text-red-700">{error}</p> : null}
      </CardContent>
    </AuthCard>
  );
}
