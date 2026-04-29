import { FormEvent, useEffect, useState } from "react";
import { ShieldCheck } from "lucide-react";

import { createInvitation, listUsers } from "@/lib/api";
import type { User } from "@/lib/types";

import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "./ui/card";
import { Input } from "./ui/input";
import { Select } from "./ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "./ui/table";

export function AdminWorkspace() {
  const [users, setUsers] = useState<User[]>([]);
  const [inviteEmail, setInviteEmail] = useState("new-user@example.com");
  const [inviteRole, setInviteRole] = useState<User["role"]>("submitter");
  const [message, setMessage] = useState("");

  const refresh = async () => setUsers(await listUsers());

  useEffect(() => {
    void refresh().catch(() => setUsers([]));
  }, []);

  const handleInvite = async (event: FormEvent) => {
    event.preventDefault();
    await createInvitation(inviteEmail, inviteRole);
    setMessage(`已创建邀请：${inviteEmail}`);
    await refresh();
  };

  return (
    <div className="grid gap-5 lg:grid-cols-[360px_1fr]">
      <Card>
        <CardHeader>
          <div className="flex items-center gap-3">
            <div className="rounded-xl border border-blue-100 bg-blue-50 p-2 text-blue-700">
              <ShieldCheck className="h-5 w-5" />
            </div>
            <div>
              <CardTitle>内部后台</CardTitle>
              <CardDescription>用户目录与邀请制账号管理。</CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleInvite}>
            <label className="block space-y-3 text-sm font-medium text-slate-700">
              邮箱
              <Input value={inviteEmail} onChange={(event) => setInviteEmail(event.target.value)} />
            </label>
            <label className="mt-6 block space-y-3 text-sm font-medium text-slate-700">
              角色
              <Select value={inviteRole} onChange={(event) => setInviteRole(event.target.value as User["role"])}>
                <option value="submitter">学生/投稿人</option>
                <option value="editor">编辑</option>
                <option value="expert">专家</option>
                <option value="admin">管理员</option>
              </Select>
            </label>
            <Button type="submit" className="mt-8 w-full">创建邀请</Button>
          </form>
          {message ? <p className="mt-3 rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-700">{message}</p> : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>用户目录</CardTitle>
          <CardDescription>管理员入口保持独立后台风格，不混入评审主流程。</CardDescription>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>用户</TableHead>
                <TableHead>邮箱</TableHead>
                <TableHead>角色</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {users.map((user) => (
                <TableRow key={user.id}>
                  <TableCell className="font-medium text-slate-950">{user.display_name ?? "未命名"}</TableCell>
                  <TableCell>{user.email}</TableCell>
                  <TableCell><Badge variant="neutral">{roleLabel[user.role]}</Badge></TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}

const roleLabel: Record<User["role"], string> = {
  submitter: "学生/投稿人",
  editor: "编辑",
  expert: "专家",
  admin: "管理员",
};
