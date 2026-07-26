import { FormEvent, useEffect, useState } from "react";
import { ShieldCheck } from "lucide-react";

import {
  activateEditorialUnit,
  addEditorialUnitMember,
  createEditorialUnit,
  createInvitation,
  createJournal,
  createValidationRun,
  listInvitations,
  listEditorialPolicies,
  listEditorialUnits,
  listModelSets,
  listUsers,
  resendInvitation,
  revokeInvitation,
  revokeUserApiKeys,
  returnEditorialUnitToTrial,
  sendUserPasswordReset,
  startCandidateModelRun,
  signValidationRun,
  updateUser,
} from "@/lib/api";
import type { EditorialUnit, Invitation, ModelSet, User } from "@/lib/types";

import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "./ui/card";
import { Input } from "./ui/input";
import { Select } from "./ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "./ui/table";
import { Textarea } from "./ui/textarea";

export function AdminWorkspace() {
  const [users, setUsers] = useState<User[]>([]);
  const [invitations, setInvitations] = useState<Invitation[]>([]);
  const [userQuery, setUserQuery] = useState("");
  const [userRole, setUserRole] = useState("");
  const [userStatus, setUserStatus] = useState("");
  const [inviteEmail, setInviteEmail] = useState("new-user@example.com");
  const [inviteRole, setInviteRole] = useState<User["role"]>("submitter");
  const [message, setMessage] = useState("");
  const [units, setUnits] = useState<EditorialUnit[]>([]);
  const [policies, setPolicies] = useState<string[]>([]);
  const [selectedUnitId, setSelectedUnitId] = useState("");
  const [selectedEditorId, setSelectedEditorId] = useState("");
  const [journalCode, setJournalCode] = useState("");
  const [journalName, setJournalName] = useState("");
  const [unitCode, setUnitCode] = useState("default");
  const [unitName, setUnitName] = useState("");
  const [policyKey, setPolicyKey] = useState("");
  const [sampleCount, setSampleCount] = useState(0);
  const [activationReason, setActivationReason] = useState("");
  const [manifestSha256, setManifestSha256] = useState("");
  const [modelSets, setModelSets] = useState<ModelSet[]>([]);
  const [candidateSubmissionId, setCandidateSubmissionId] = useState("");

  const refresh = async () => {
    const [userRows, invitationRows, unitRows, policyRows, modelSetRows] = await Promise.all([
      listUsers(),
      listInvitations(),
      listEditorialUnits(),
      listEditorialPolicies(),
      listModelSets(),
    ]);
    setUsers(userRows);
    setInvitations(invitationRows);
    setUnits(unitRows);
    setPolicies(policyRows);
    setModelSets(modelSetRows);
    setSelectedUnitId((current) => current || unitRows[0]?.id || "");
    setSelectedEditorId(
      (current) =>
        current || userRows.find((user) => user.role === "editor")?.id || ""
    );
    setPolicyKey((current) => current || policyRows[0] || "");
  };

  useEffect(() => {
    void refresh().catch(() => setUsers([]));
  }, []);

  const handleInvite = async (event: FormEvent) => {
    event.preventDefault();
    await createInvitation(inviteEmail, inviteRole);
    setMessage(`已创建邀请：${inviteEmail}`);
    await refresh();
  };

  const handleCreateUnit = async (event: FormEvent) => {
    event.preventDefault();
    const journal = await createJournal(journalCode, journalName);
    await createEditorialUnit(
      journal.id,
      unitCode,
      unitName,
      policyKey
    );
    setMessage(`已创建试运行编辑单元：${unitName}`);
    setJournalCode("");
    setJournalName("");
    setUnitName("");
    await refresh();
  };

  const handleAddMember = async () => {
    if (!selectedUnitId || !selectedEditorId) return;
    await addEditorialUnitMember(selectedUnitId, selectedEditorId);
    setMessage("已更新编辑单元成员关系。");
  };

  const handleActivate = async () => {
    if (!selectedUnitId) return;
    const validation = await createValidationRun(
      selectedUnitId,
      sampleCount,
      manifestSha256,
      activationReason
    );
    await signValidationRun(validation.id);
    await activateEditorialUnit(selectedUnitId, activationReason, validation.id);
    setMessage("编辑单元已转为正式启用；该操作已写入审计日志。");
    await refresh();
  };

  const handleReturnToTrial = async () => {
    if (!selectedUnitId || activationReason.trim().length < 5) return;
    if (
      !window.confirm(
        "确定将该编辑单元退回试运行吗？新的智能建议将恢复为扣留展示，历史记录不会删除。"
      )
    ) {
      return;
    }
    await returnEditorialUnitToTrial(
      selectedUnitId,
      activationReason.trim()
    );
    setMessage("编辑单元已退回试运行；历史评价和决定记录均已保留。");
    await refresh();
  };

  const handleCandidateRun = async () => {
    if (!candidateSubmissionId.trim()) return;
    const result = await startCandidateModelRun(candidateSubmissionId.trim());
    setMessage(`候选模型任务已创建：${result.task_id}`);
  };

  const filteredUsers = users.filter((user) => {
    const keyword = userQuery.trim().toLocaleLowerCase("zh-CN");
    const matchesKeyword =
      !keyword ||
      user.email.toLocaleLowerCase("zh-CN").includes(keyword) ||
      (user.display_name ?? "").toLocaleLowerCase("zh-CN").includes(keyword);
    const matchesRole = !userRole || user.role === userRole;
    const matchesStatus =
      !userStatus ||
      (userStatus === "active" ? user.is_active !== false : user.is_active === false);
    return matchesKeyword && matchesRole && matchesStatus;
  });
  const selectedUnit = units.find((unit) => unit.id === selectedUnitId);

  const runUserAction = async (
    action: () => Promise<unknown>,
    successMessage: string
  ) => {
    try {
      await action();
      setMessage(successMessage);
      await refresh();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "操作失败");
    }
  };

  return (
    <div className="space-y-5">
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
          <CardDescription>筛选用户、调整角色、停用账户或发送密码重置邮件。</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="mb-4 grid gap-3 md:grid-cols-3">
            <Input
              value={userQuery}
              onChange={(event) => setUserQuery(event.target.value)}
              placeholder="搜索姓名或邮箱"
            />
            <Select value={userRole} onChange={(event) => setUserRole(event.target.value)}>
              <option value="">全部角色</option>
              <option value="submitter">学生/投稿人</option>
              <option value="editor">编辑</option>
              <option value="expert">专家</option>
              <option value="admin">管理员</option>
            </Select>
            <Select value={userStatus} onChange={(event) => setUserStatus(event.target.value)}>
              <option value="">全部状态</option>
              <option value="active">已启用</option>
              <option value="inactive">已停用</option>
            </Select>
          </div>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>用户</TableHead>
                <TableHead>邮箱</TableHead>
                <TableHead>角色</TableHead>
                <TableHead>状态</TableHead>
                <TableHead>最后登录</TableHead>
                <TableHead>操作</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filteredUsers.map((user) => (
                <TableRow key={user.id}>
                  <TableCell className="font-medium text-slate-950">{user.display_name ?? "未命名"}</TableCell>
                  <TableCell>{user.email}</TableCell>
                  <TableCell>
                    <Select
                      value={user.role}
                      onChange={(event) =>
                        void runUserAction(
                          () =>
                            updateUser(user.id, {
                              role: event.target.value as User["role"],
                            }),
                          "用户角色已更新。"
                        )
                      }
                    >
                      <option value="submitter">学生/投稿人</option>
                      <option value="editor">编辑</option>
                      <option value="expert">专家</option>
                      <option value="admin">管理员</option>
                    </Select>
                  </TableCell>
                  <TableCell>
                    <Badge variant={user.is_active === false ? "neutral" : "success"}>
                      {user.is_active === false ? "已停用" : "已启用"}
                    </Badge>
                    {user.role === "admin" ? (
                      <span className="ml-2 text-xs text-slate-500">
                        {user.mfa_enabled ? "已启用双因素认证" : "待设置双因素认证"}
                      </span>
                    ) : null}
                    {user.password_reset_required ? (
                      <span className="ml-2 text-xs text-amber-700">
                        待完成密码重置
                      </span>
                    ) : null}
                  </TableCell>
                  <TableCell>
                    {user.last_login_at
                      ? new Date(user.last_login_at).toLocaleString("zh-CN")
                      : "尚未登录"}
                  </TableCell>
                  <TableCell>
                    <div className="flex flex-wrap gap-2">
                      <Button
                        type="button"
                        size="sm"
                        variant="secondary"
                        onClick={() =>
                          void runUserAction(
                            () => sendUserPasswordReset(user.id),
                            "密码重置邮件已进入发送队列。"
                          )
                        }
                      >
                        重置密码
                      </Button>
                      <Button
                        type="button"
                        size="sm"
                        variant="secondary"
                        onClick={() =>
                          void runUserAction(
                            () => revokeUserApiKeys(user.id),
                            "该用户的 API Key 已全部撤销。"
                          )
                        }
                      >
                        撤销 Key
                      </Button>
                      <Button
                        type="button"
                        size="sm"
                        variant={user.is_active === false ? "outline" : "destructive"}
                        onClick={() =>
                          void runUserAction(
                            () =>
                              updateUser(user.id, {
                                is_active: user.is_active === false,
                              }),
                            user.is_active === false ? "用户已恢复。" : "用户已停用。"
                          )
                        }
                      >
                        {user.is_active === false ? "恢复" : "停用"}
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>邀请记录</CardTitle>
          <CardDescription>查看、重新发送或撤销尚未使用的账户邀请。</CardDescription>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>邮箱</TableHead>
                <TableHead>角色</TableHead>
                <TableHead>状态</TableHead>
                <TableHead>有效期至</TableHead>
                <TableHead>操作</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {invitations.map((invitation) => (
                <TableRow key={invitation.id}>
                  <TableCell>{invitation.email}</TableCell>
                  <TableCell>{roleLabel[invitation.role]}</TableCell>
                  <TableCell>
                    <Badge variant={invitation.status === "pending" ? "warning" : "neutral"}>
                      {invitationStatusLabel[invitation.status]}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    {new Date(invitation.expires_at).toLocaleString("zh-CN")}
                  </TableCell>
                  <TableCell>
                    <div className="flex gap-2">
                      <Button
                        type="button"
                        size="sm"
                        variant="secondary"
                        disabled={invitation.status === "used" || invitation.status === "revoked"}
                        onClick={() =>
                          void runUserAction(
                            () => resendInvitation(invitation.id),
                            "邀请已经重新发送。"
                          )
                        }
                      >
                        重新发送
                      </Button>
                      <Button
                        type="button"
                        size="sm"
                        variant="destructive"
                        disabled={invitation.status === "used" || invitation.status === "revoked"}
                        onClick={() =>
                          void runUserAction(
                            () => revokeInvitation(invitation.id),
                            "邀请已经撤销。"
                          )
                        }
                      >
                        撤销
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <div className="grid gap-5 xl:grid-cols-[1fr_1fr]">
        <Card>
          <CardHeader>
            <CardTitle>期刊与编辑单元</CardTitle>
            <CardDescription>
              新增单元只能选择已部署策略，且一律从试运行开始。
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form className="grid gap-3 md:grid-cols-2" onSubmit={handleCreateUnit}>
              <Input
                value={journalCode}
                onChange={(event) => setJournalCode(event.target.value)}
                placeholder="期刊代码，如 new-law"
                required
              />
              <Input
                value={journalName}
                onChange={(event) => setJournalName(event.target.value)}
                placeholder="期刊名称"
                required
              />
              <Input
                value={unitCode}
                onChange={(event) => setUnitCode(event.target.value)}
                placeholder="编辑单元代码"
                required
              />
              <Input
                value={unitName}
                onChange={(event) => setUnitName(event.target.value)}
                placeholder="编辑单元名称"
                required
              />
              <Select
                value={policyKey}
                onChange={(event) => setPolicyKey(event.target.value)}
              >
                {policies.map((policy) => (
                  <option key={policy} value={policy}>{policy}</option>
                ))}
              </Select>
              <Button type="submit" disabled={!policyKey}>创建试运行单元</Button>
            </form>
            <div className="mt-5 space-y-2">
              {units.map((unit) => (
                <div
                  key={unit.id}
                  className="flex items-center justify-between rounded-xl border border-slate-200 p-3"
                >
                  <div>
                    <p className="text-sm font-medium text-slate-950">{unit.name}</p>
                    <p className="text-xs text-slate-500">
                      {unit.policy_key} · v{unit.policy_version}
                    </p>
                  </div>
                  <Badge variant={unit.rollout_state === "active" ? "success" : "warning"}>
                    {unit.rollout_state === "active" ? "正式启用" : "试运行"}
                  </Badge>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>成员与启用门禁</CardTitle>
            <CardDescription>
              成员按编辑单元隔离；正式启用需要样本验证和编辑签字。
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <Select
              value={selectedUnitId}
              onChange={(event) => setSelectedUnitId(event.target.value)}
            >
              {units.map((unit) => (
                <option key={unit.id} value={unit.id}>{unit.name}</option>
              ))}
            </Select>
            <div className="grid gap-3 sm:grid-cols-[1fr_auto]">
              <Select
                value={selectedEditorId}
                onChange={(event) => setSelectedEditorId(event.target.value)}
              >
                {users.filter((user) => user.role === "editor").map((editor) => (
                  <option key={editor.id} value={editor.id}>
                    {editor.display_name ?? editor.email}
                  </option>
                ))}
              </Select>
              <Button
                type="button"
                variant="secondary"
                onClick={handleAddMember}
                disabled={!selectedUnitId || !selectedEditorId}
              >
                添加编辑
              </Button>
            </div>
            {selectedUnit?.rollout_state !== "active" ? (
              <>
                <Input
                  type="number"
                  min={1}
                  value={sampleCount}
                  onChange={(event) => setSampleCount(Number(event.target.value))}
                  placeholder="试运行验证样本数"
                />
                <Input
                  value={manifestSha256}
                  onChange={(event) =>
                    setManifestSha256(event.target.value.trim())
                  }
                  placeholder="样本清单 SHA-256（64 位小写十六进制）"
                  pattern="[0-9a-f]{64}"
                />
              </>
            ) : null}
            <Textarea
              value={activationReason}
              onChange={(event) => setActivationReason(event.target.value)}
              placeholder={
                selectedUnit?.rollout_state === "active"
                  ? "填写退回试运行的原因（至少 5 个字符）"
                  : "填写验证结论和编辑签字说明（至少 5 个字符）"
              }
            />
            {selectedUnit?.rollout_state === "active" ? (
              <Button
                type="button"
                variant="destructive"
                onClick={handleReturnToTrial}
                disabled={activationReason.trim().length < 5}
              >
                退回试运行
              </Button>
            ) : (
              <Button
                type="button"
                onClick={handleActivate}
                disabled={
                  !selectedUnitId ||
                  sampleCount < 1 ||
                  !/^[0-9a-f]{64}$/.test(manifestSha256) ||
                  activationReason.trim().length < 5
                }
              >
                验证并正式启用
              </Button>
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>六维模型升级验证</CardTitle>
          <CardDescription>
            候选模型对同一匿名稿并行运行，使用独立任务记录，不覆盖当前生产结果；五轴模型保持不变。
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-3 lg:grid-cols-2">
            {modelSets.map((modelSet) => (
              <div
                key={modelSet.name}
                className="rounded-xl border border-slate-200 bg-slate-50 p-4"
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="font-medium text-slate-950">
                      {modelSet.status === "production"
                        ? "当前生产模型集"
                        : "候选验证模型集"}
                    </p>
                    <p className="mt-1 text-xs text-slate-500">
                      配置快照：{modelSet.name}
                    </p>
                  </div>
                  <Badge
                    variant={
                      modelSet.status === "production" ? "success" : "warning"
                    }
                  >
                    {modelSet.status === "production" ? "生产使用中" : "尚未批准"}
                  </Badge>
                </div>
                <ul className="mt-3 space-y-1 text-sm text-slate-700">
                  {modelSet.provider_names.map((modelName, index) => (
                    <li key={modelName}>
                      模型{["甲", "乙", "丙", "丁"][index]}：{modelName}
                    </li>
                  ))}
                </ul>
                <p className="mt-3 text-xs text-slate-600">
                  第二轮方式：
                  {modelSet.review_mode === "all_peers"
                    ? "四模型匿名互评"
                    : "分组交叉复核"}
                </p>
              </div>
            ))}
          </div>
          <div className="grid gap-3 md:grid-cols-[1fr_auto]">
            <Input
              value={candidateSubmissionId}
              onChange={(event) => setCandidateSubmissionId(event.target.value)}
              placeholder="填写已有编辑投稿编号"
            />
            <Button
              type="button"
              onClick={handleCandidateRun}
              disabled={!candidateSubmissionId.trim()}
            >
              创建候选模型并行任务
            </Button>
          </div>
          <p className="text-xs leading-5 text-slate-500">
            仅用于获授权样本的校准、冻结测试和最终验证。候选模型通过编辑签字前不得切换为生产配置。
          </p>
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

const invitationStatusLabel: Record<Invitation["status"], string> = {
  pending: "待使用",
  used: "已使用",
  expired: "已过期",
  revoked: "已撤销",
};
