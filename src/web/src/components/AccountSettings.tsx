import { FormEvent, useEffect, useState } from "react";
import { KeyRound, LockKeyhole, ShieldCheck } from "lucide-react";

import {
  changePassword,
  createApiKey,
  listApiKeys,
  regenerateMfaRecoveryCodes,
  revokeApiKey,
} from "@/lib/api";
import type { ApiKeyMetadata, CreatedApiKey, User } from "@/lib/types";

import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "./ui/card";
import { Input } from "./ui/input";
import { Select } from "./ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "./ui/table";

export function AccountSettings({
  user,
  onUserChanged,
}: {
  user: User;
  onUserChanged: (user: User) => void;
}) {
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [newPasswordAgain, setNewPasswordAgain] = useState("");
  const [revokeKeys, setRevokeKeys] = useState(true);
  const [keys, setKeys] = useState<ApiKeyMetadata[]>([]);
  const [keyName, setKeyName] = useState("");
  const [keyDays, setKeyDays] = useState(90);
  const [createdKey, setCreatedKey] = useState<CreatedApiKey | null>(null);
  const [mfaPassword, setMfaPassword] = useState("");
  const [mfaCode, setMfaCode] = useState("");
  const [recoveryCodes, setRecoveryCodes] = useState<string[]>([]);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const refreshKeys = async () => {
    setKeys(await listApiKeys());
  };

  useEffect(() => {
    void refreshKeys().catch(() => setKeys([]));
  }, []);

  const handlePassword = async (event: FormEvent) => {
    event.preventDefault();
    if (newPassword !== newPasswordAgain) {
      setError("两次输入的新密码不一致");
      return;
    }
    try {
      const updated = await changePassword(
        currentPassword,
        newPassword,
        revokeKeys
      );
      onUserChanged(updated);
      setCurrentPassword("");
      setNewPassword("");
      setNewPasswordAgain("");
      setError("");
      setMessage("密码已经更新，其他登录会话已失效。");
      await refreshKeys();
    } catch (err) {
      setError(err instanceof Error ? err.message : "密码修改失败");
    }
  };

  const handleCreateKey = async (event: FormEvent) => {
    event.preventDefault();
    try {
      const result = await createApiKey(keyName.trim(), keyDays);
      setCreatedKey(result);
      setKeyName("");
      setError("");
      setMessage("接口密钥已创建，请立即复制保存。");
      await refreshKeys();
    } catch (err) {
      setError(err instanceof Error ? err.message : "接口密钥创建失败");
    }
  };

  const handleRecoveryCodes = async (event: FormEvent) => {
    event.preventDefault();
    try {
      const codes = await regenerateMfaRecoveryCodes(mfaPassword, mfaCode);
      setRecoveryCodes(codes);
      setMfaPassword("");
      setMfaCode("");
      setError("");
      setMessage("新的恢复码已生成，旧恢复码已全部失效。");
    } catch (err) {
      setError(err instanceof Error ? err.message : "恢复码生成失败");
    }
  };

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-xl font-semibold text-slate-950">账户设置</h2>
        <p className="mt-1 text-sm text-slate-500">
          当前账户：{user.display_name ?? user.email}（{user.email}）
        </p>
      </div>

      {message ? (
        <p className="rounded-lg bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
          {message}
        </p>
      ) : null}
      {error ? (
        <p className="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </p>
      ) : null}

      <Card>
        <CardHeader>
          <div className="flex items-center gap-3">
            <LockKeyhole className="h-5 w-5 text-blue-700" />
            <div>
              <CardTitle>修改密码</CardTitle>
              <CardDescription>
                密码至少 12 个字符。修改后其他登录会话立即失效。
              </CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <form className="grid gap-4 lg:grid-cols-3" onSubmit={handlePassword}>
            <Input
              type="password"
              value={currentPassword}
              onChange={(event) => setCurrentPassword(event.target.value)}
              placeholder="当前密码"
              required
            />
            <Input
              type="password"
              value={newPassword}
              onChange={(event) => setNewPassword(event.target.value)}
              placeholder="新密码"
              minLength={12}
              required
            />
            <Input
              type="password"
              value={newPasswordAgain}
              onChange={(event) => setNewPasswordAgain(event.target.value)}
              placeholder="再次输入新密码"
              minLength={12}
              required
            />
            <label className="flex items-center gap-2 text-sm text-slate-700 lg:col-span-2">
              <input
                type="checkbox"
                checked={revokeKeys}
                onChange={(event) => setRevokeKeys(event.target.checked)}
              />
              同时撤销全部接口密钥
            </label>
            <Button type="submit">更新密码</Button>
          </form>
        </CardContent>
      </Card>

      {user.mfa_enabled ? (
        <Card>
          <CardHeader>
            <div className="flex items-center gap-3">
              <ShieldCheck className="h-5 w-5 text-blue-700" />
              <div>
                <CardTitle>双因素认证恢复码</CardTitle>
                <CardDescription>
                  重新生成会立即废止原恢复码；每个新恢复码只能使用一次。
                </CardDescription>
              </div>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            <form
              className="grid gap-3 md:grid-cols-[1fr_180px_auto]"
              onSubmit={handleRecoveryCodes}
            >
              <Input
                type="password"
                value={mfaPassword}
                onChange={(event) => setMfaPassword(event.target.value)}
                placeholder="当前密码"
                required
              />
              <Input
                value={mfaCode}
                onChange={(event) => setMfaCode(event.target.value)}
                placeholder="动态验证码"
                minLength={6}
                required
              />
              <Button type="submit">重新生成</Button>
            </form>
            {recoveryCodes.length ? (
              <div className="rounded-xl border border-amber-200 bg-amber-50 p-4">
                <p className="font-medium text-amber-900">
                  请立即离线保存，关闭后不再显示
                </p>
                <div className="mt-3 grid grid-cols-2 gap-2 font-mono text-sm text-amber-950 md:grid-cols-5">
                  {recoveryCodes.map((code) => (
                    <code key={code}>{code}</code>
                  ))}
                </div>
                <Button
                  type="button"
                  variant="secondary"
                  className="mt-3"
                  onClick={() => setRecoveryCodes([])}
                >
                  我已保存
                </Button>
              </div>
            ) : null}
          </CardContent>
        </Card>
      ) : null}

      <Card>
        <CardHeader>
          <div className="flex items-center gap-3">
            <KeyRound className="h-5 w-5 text-blue-700" />
            <div>
              <CardTitle>接口密钥</CardTitle>
              <CardDescription>
                Key 明文只显示一次，最长有效 90 天。
              </CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-5">
          <form className="grid gap-3 md:grid-cols-[1fr_180px_auto]" onSubmit={handleCreateKey}>
            <Input
              value={keyName}
              onChange={(event) => setKeyName(event.target.value)}
              placeholder="用途名称"
              required
            />
            <Select
              value={keyDays}
              onChange={(event) => setKeyDays(Number(event.target.value))}
            >
              <option value={30}>30 天</option>
              <option value={60}>60 天</option>
              <option value={90}>90 天</option>
            </Select>
            <Button type="submit">创建 Key</Button>
          </form>

          {createdKey ? (
            <div className="rounded-xl border border-amber-200 bg-amber-50 p-4">
              <p className="font-medium text-amber-900">请立即复制，关闭后不再显示</p>
              <code className="mt-2 block break-all text-sm text-amber-950">
                {createdKey.api_key}
              </code>
              <Button
                type="button"
                variant="secondary"
                className="mt-3"
                onClick={() => setCreatedKey(null)}
              >
                我已保存
              </Button>
            </div>
          ) : null}

          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>名称</TableHead>
                <TableHead>前缀</TableHead>
                <TableHead>有效期至</TableHead>
                <TableHead>状态</TableHead>
                <TableHead>操作</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {keys.map((key) => (
                <TableRow key={key.id}>
                  <TableCell>{key.name ?? "未命名"}</TableCell>
                  <TableCell>{key.key_prefix}…</TableCell>
                  <TableCell>{new Date(key.expires_at).toLocaleDateString("zh-CN")}</TableCell>
                  <TableCell>
                    <Badge variant={key.is_active ? "success" : "neutral"}>
                      {key.is_active ? "有效" : "已撤销"}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    <Button
                      type="button"
                      size="sm"
                      variant="secondary"
                      disabled={!key.is_active}
                      onClick={async () => {
                        await revokeApiKey(key.id);
                        await refreshKeys();
                      }}
                    >
                      撤销
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
