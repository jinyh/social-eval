import { FormEvent, useEffect, useState } from "react";
import { ShieldCheck } from "lucide-react";

import {
  activateEditorialUnit,
  addEditorialUnitMember,
  createEditorialPolicyVersion,
  createEditorialUnit,
  createInvitation,
  createJournal,
  createValidationRun,
  freezeEditorialPolicyVersion,
  getModelComparison,
  listInvitations,
  listEditorialPolicies,
  listEditorialPolicyVersions,
  listEditorialUnits,
  listValidationRuns,
  listModelSets,
  listUsers,
  resendInvitation,
  revokeInvitation,
  revokeUserApiKeys,
  returnEditorialUnitToTrial,
  sendUserPasswordReset,
  startCandidateModelRun,
  updateEditorialPolicyVersion,
  updateUser,
} from "@/lib/api";
import type {
  EditorialPolicyProfile,
  EditorialPolicyVersion,
  EditorialUnit,
  Invitation,
  ModelComparison,
  ModelSet,
  User,
  ValidationRun,
} from "@/lib/types";

import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "./ui/card";
import { Input } from "./ui/input";
import { Select } from "./ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "./ui/table";
import { Textarea } from "./ui/textarea";
import {
  AdminSidebar,
  type AdminWorkspaceView,
} from "./AdminSidebar";

export function AdminWorkspace() {
  const [users, setUsers] = useState<User[]>([]);
  const [invitations, setInvitations] = useState<Invitation[]>([]);
  const [userQuery, setUserQuery] = useState("");
  const [userRole, setUserRole] = useState("");
  const [userStatus, setUserStatus] = useState("");
  const [inviteEmail, setInviteEmail] = useState("new-user@example.com");
  const [inviteRole, setInviteRole] = useState<User["role"]>("editor");
  const [activeView, setActiveView] =
    useState<AdminWorkspaceView>("overview");
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [mobileNavigationOpen, setMobileNavigationOpen] = useState(false);
  const [message, setMessage] = useState("");
  const [units, setUnits] = useState<EditorialUnit[]>([]);
  const [policies, setPolicies] = useState<string[]>([]);
  const [selectedUnitId, setSelectedUnitId] = useState("");
  const [selectedEditorId, setSelectedEditorId] = useState("");
  const [membershipRole, setMembershipRole] = useState<
    "editor" | "unit_admin"
  >("editor");
  const [journalCode, setJournalCode] = useState("");
  const [journalName, setJournalName] = useState("");
  const [unitCode, setUnitCode] = useState("default");
  const [unitName, setUnitName] = useState("");
  const [policyKey, setPolicyKey] = useState("");
  const [sampleCount, setSampleCount] = useState(0);
  const [activationReason, setActivationReason] = useState("");
  const [manifestSha256, setManifestSha256] = useState("");
  const [manifestFileName, setManifestFileName] = useState("");
  const [modelSets, setModelSets] = useState<ModelSet[]>([]);
  const [candidateSubmissionId, setCandidateSubmissionId] = useState("");
  const [policyVersions, setPolicyVersions] = useState<
    EditorialPolicyVersion[]
  >([]);
  const [validationRuns, setValidationRuns] = useState<ValidationRun[]>([]);
  const [selectedPolicyVersionId, setSelectedPolicyVersionId] = useState("");
  const [policyVersionNumber, setPolicyVersionNumber] = useState("1.2");
  const [policyModelSet, setPolicyModelSet] = useState(
    "six-dimension-v2-candidate"
  );
  const [policyProfile, setPolicyProfile] = useState<EditorialPolicyProfile>({
    fit_focus: "",
    accepted_scope: [],
    excluded_scope: [],
    column_positioning: [],
    article_types: [],
    target_readers: [],
    special_notes: "",
  });
  const [modelComparison, setModelComparison] =
    useState<ModelComparison | null>(null);

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

  useEffect(() => {
    if (!selectedUnitId) return;
    void Promise.all([
      listEditorialPolicyVersions(selectedUnitId),
      listValidationRuns(selectedUnitId),
    ]).then(([versions, validations]) => {
      setPolicyVersions(versions);
      setValidationRuns(validations);
      const unit = units.find((item) => item.id === selectedUnitId);
      const preferred =
        versions.find(
          (version) =>
            version.id ===
            (unit?.trial_policy_version_id ?? unit?.active_policy_version_id)
        ) ?? versions[0];
      if (preferred) selectPolicyVersion(preferred);
    });
  }, [selectedUnitId, units]);

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
    await addEditorialUnitMember(
      selectedUnitId,
      selectedEditorId,
      membershipRole
    );
    setMessage("已更新编辑单元成员关系。");
  };

  const handleCreateValidation = async () => {
    const trialPolicy = policyVersions.find(
      (version) => version.id === selectedUnit?.trial_policy_version_id
    );
    if (!selectedUnitId || !trialPolicy) return;
    const validation = await createValidationRun(
      selectedUnitId,
      sampleCount,
      manifestSha256,
      activationReason,
      trialPolicy
    );
    setValidationRuns((current) => [validation, ...current]);
    setMessage("验证记录已登记，请由当前单元负责人在编辑工作台签署。");
  };

  const handleActivate = async () => {
    const trialPolicy = policyVersions.find(
      (version) => version.id === selectedUnit?.trial_policy_version_id
    );
    const validation = validationRuns.find(
      (row) =>
        row.policy_version_id === trialPolicy?.id && row.status === "signed"
    );
    if (!selectedUnitId || !trialPolicy || !validation) return;
    await activateEditorialUnit(
      selectedUnitId,
      activationReason,
      validation.id,
      trialPolicy.id
    );
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

  const handleLoadComparison = async () => {
    if (!candidateSubmissionId.trim()) return;
    setModelComparison(
      await getModelComparison(candidateSubmissionId.trim())
    );
  };

  const handleManifestFile = async (file: File | undefined) => {
    if (!file) return;
    setManifestFileName(file.name);
    setManifestSha256(await sha256File(file));
  };

  const selectPolicyVersion = (version: EditorialPolicyVersion) => {
    setSelectedPolicyVersionId(version.id);
    setPolicyVersionNumber(version.version);
    setPolicyModelSet(version.model_set_version);
    setPolicyProfile(normalizePolicyProfile(version.profile));
  };

  const handleSavePolicyDraft = async () => {
    if (!selectedUnitId) return;
    const selected = policyVersions.find(
      (version) => version.id === selectedPolicyVersionId
    );
    const input = {
      version: policyVersionNumber,
      based_on_id: selected?.status === "draft"
        ? selected.based_on_id
        : selected?.id,
      model_set_version: policyModelSet,
      profile: policyProfile,
    };
    const saved =
      selected?.status === "draft"
        ? await updateEditorialPolicyVersion(selected.id, input)
        : await createEditorialPolicyVersion(selectedUnitId, input);
    setMessage(`期刊策略草稿 ${saved.version} 已保存。`);
    const versions = await listEditorialPolicyVersions(selectedUnitId);
    setPolicyVersions(versions);
    selectPolicyVersion(
      versions.find((version) => version.id === saved.id) ?? saved
    );
  };

  const handleFreezePolicy = async () => {
    const selected = policyVersions.find(
      (version) => version.id === selectedPolicyVersionId
    );
    if (!selected || selected.status !== "draft") return;
    const frozen = await freezeEditorialPolicyVersion(selected.id);
    setMessage(`策略 ${frozen.version} 已冻结并进入试运行。`);
    await refresh();
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
  const selectedPolicyVersion = policyVersions.find(
    (version) => version.id === selectedPolicyVersionId
  );
  const trialPolicy = policyVersions.find(
    (version) => version.id === selectedUnit?.trial_policy_version_id
  );
  const signedValidation = validationRuns.find(
    (row) =>
      row.policy_version_id === trialPolicy?.id && row.status === "signed"
  );

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
    <div className="flex items-start gap-5">
      <AdminSidebar
        activeView={activeView}
        onViewChange={setActiveView}
        collapsed={sidebarCollapsed}
        onCollapsedChange={setSidebarCollapsed}
        mobileOpen={mobileNavigationOpen}
        onMobileOpenChange={setMobileNavigationOpen}
      />
      <main className="min-w-0 flex-1 space-y-5">
      {message ? (
        <p className="rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-700">
          {message}
        </p>
      ) : null}
      {activeView === "overview" ? (
        <>
          <Card>
            <CardHeader>
              <CardTitle>系统总览</CardTitle>
              <CardDescription>
                查看账户、期刊和策略启用情况；具体操作请从左侧进入对应模块。
              </CardDescription>
            </CardHeader>
            <CardContent className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              <SummaryMetric label="用户总数" value={users.length} />
              <SummaryMetric
                label="已验证投稿人"
                value={users.filter((user) => user.role === "submitter" && user.email_verified_at).length}
              />
              <SummaryMetric label="编辑单元" value={units.length} />
              <SummaryMetric
                label="正式启用"
                value={units.filter((unit) => unit.rollout_state === "active").length}
              />
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>账号开通规则</CardTitle>
              <CardDescription>
                投稿人通过登录页自行注册并验证邮箱；编辑、专家和管理员由内部邀请开通。
              </CardDescription>
            </CardHeader>
          </Card>
        </>
      ) : null}
      {activeView === "users" ? (
      <div className="space-y-5">
        <div>
          <h2 className="text-xl font-semibold text-slate-950">用户与权限</h2>
          <p className="mt-1 text-sm text-slate-500">
            先查看和维护现有用户，再处理内部成员邀请。
          </p>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>用户目录</CardTitle>
            <CardDescription>
              筛选用户、调整角色、停用账户或发送密码重置邮件。
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="mb-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-[minmax(260px,1fr)_180px_160px]">
              <Input
                value={userQuery}
                onChange={(event) => setUserQuery(event.target.value)}
                placeholder="搜索姓名或邮箱"
              />
              <Select value={userRole} onChange={(event) => setUserRole(event.target.value)}>
                <option value="">全部角色</option>
                <option value="submitter">投稿人</option>
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
            <Table className="min-w-[900px]">
              <TableHeader>
                <TableRow>
                  <TableHead>用户</TableHead>
                  <TableHead>角色</TableHead>
                  <TableHead>状态</TableHead>
                  <TableHead>最后登录</TableHead>
                  <TableHead>操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredUsers.length === 0 ? (
                  <TableRow>
                    <TableCell
                      colSpan={5}
                      className="py-10 text-center text-sm text-slate-500"
                    >
                      没有符合当前筛选条件的用户。
                    </TableCell>
                  </TableRow>
                ) : (
                  filteredUsers.map((user) => (
                    <TableRow key={user.id}>
                      <TableCell className="font-medium text-slate-950">
                        {user.display_name ?? "未命名"}
                        <span className="mt-1 block text-xs font-normal text-slate-500">
                          {user.email}
                        </span>
                        {user.affiliation ? (
                          <span className="mt-1 block text-xs font-normal text-slate-500">
                            {user.affiliation}
                          </span>
                        ) : null}
                      </TableCell>
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
                          <option value="submitter">投稿人</option>
                          <option value="editor">编辑</option>
                          <option value="expert">专家</option>
                          <option value="admin">管理员</option>
                        </Select>
                      </TableCell>
                      <TableCell>
                        <div className="space-y-1">
                          <Badge variant={user.is_active === false ? "neutral" : "success"}>
                            {user.is_active === false ? "已停用" : "已启用"}
                          </Badge>
                          {user.role === "submitter" ? (
                            <span className="block text-xs text-slate-500">
                              {user.email_verified_at ? "邮箱已验证" : "邮箱待验证"}
                            </span>
                          ) : null}
                          {user.role === "admin" ? (
                            <span className="block text-xs text-slate-500">
                              {user.mfa_enabled ? "已启用双因素认证" : "待设置双因素认证"}
                            </span>
                          ) : null}
                          {user.password_reset_required ? (
                            <span className="block text-xs text-amber-700">
                              待完成密码重置
                            </span>
                          ) : null}
                        </div>
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
                                "该用户的接口密钥已全部撤销。"
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
                  ))
                )}
              </TableBody>
            </Table>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <div className="flex items-center gap-3">
              <div className="rounded-xl border border-blue-100 bg-blue-50 p-2 text-blue-700">
                <ShieldCheck className="h-5 w-5" />
              </div>
              <div>
                <CardTitle>邀请内部成员</CardTitle>
                <CardDescription>邀请编辑、专家或管理员开通内部账户。</CardDescription>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            <form
              onSubmit={handleInvite}
              className="grid gap-4 md:grid-cols-[minmax(0,1fr)_220px_auto] md:items-end"
            >
              <label className="block space-y-2 text-sm font-medium text-slate-700">
                邮箱
                <Input
                  value={inviteEmail}
                  onChange={(event) => setInviteEmail(event.target.value)}
                />
              </label>
              <label className="block space-y-2 text-sm font-medium text-slate-700">
                角色
                <Select
                  value={inviteRole}
                  onChange={(event) =>
                    setInviteRole(event.target.value as User["role"])
                  }
                >
                  <option value="editor">编辑</option>
                  <option value="expert">专家</option>
                  <option value="admin">管理员</option>
                </Select>
              </label>
              <Button type="submit" className="md:min-w-32">创建邀请</Button>
            </form>
          </CardContent>
        </Card>
      </div>
      ) : null}

      {activeView === "policies" ? (
      <Card>
        <CardHeader>
          <CardTitle>期刊策略管理</CardTitle>
          <CardDescription>
            这里只维护期刊适配口径与已部署模型集。六维、五轴、综合参考分和提示词仍由版本化配置发布。
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            <Select
              value={selectedUnitId}
              onChange={(event) => setSelectedUnitId(event.target.value)}
              aria-label="期刊编辑单元"
            >
              {units.map((unit) => (
                <option key={unit.id} value={unit.id}>
                  {unit.journal_name} · {unit.name}
                </option>
              ))}
            </Select>
            <Select
              value={selectedPolicyVersionId}
              onChange={(event) => {
                const version = policyVersions.find(
                  (item) => item.id === event.target.value
                );
                if (version) selectPolicyVersion(version);
              }}
            >
              {policyVersions.map((version) => (
                <option key={version.id} value={version.id}>
                  第 {version.version} 版 · {policyStatusLabel(version.status)}
                </option>
              ))}
            </Select>
            <Input
              value={policyVersionNumber}
              onChange={(event) => setPolicyVersionNumber(event.target.value)}
              placeholder="新版本号，如 1.2"
            />
            <Select
              value={policyModelSet}
              onChange={(event) => setPolicyModelSet(event.target.value)}
            >
              {modelSets.map((modelSet) => (
                <option key={modelSet.name} value={modelSet.name}>
                  {modelSet.status === "production"
                    ? "稳定四模型"
                    : "新四模型试运行"}
                </option>
              ))}
            </Select>
          </div>
          <Textarea
            value={policyProfile.fit_focus}
            onChange={(event) =>
              setPolicyProfile((current) => ({
                ...current,
                fit_focus: event.target.value,
              }))
            }
            placeholder="本刊关注方向"
          />
          <div className="grid gap-3 md:grid-cols-2">
            <PolicyListField
              label="收稿范围"
              value={policyProfile.accepted_scope}
              onChange={(accepted_scope) =>
                setPolicyProfile((current) => ({
                  ...current,
                  accepted_scope,
                }))
              }
            />
            <PolicyListField
              label="明确排除范围"
              value={policyProfile.excluded_scope}
              onChange={(excluded_scope) =>
                setPolicyProfile((current) => ({
                  ...current,
                  excluded_scope,
                }))
              }
            />
            <PolicyListField
              label="栏目定位"
              value={policyProfile.column_positioning}
              onChange={(column_positioning) =>
                setPolicyProfile((current) => ({
                  ...current,
                  column_positioning,
                }))
              }
            />
            <PolicyListField
              label="稿件类型"
              value={policyProfile.article_types}
              onChange={(article_types) =>
                setPolicyProfile((current) => ({
                  ...current,
                  article_types,
                }))
              }
            />
            <PolicyListField
              label="目标读者"
              value={policyProfile.target_readers}
              onChange={(target_readers) =>
                setPolicyProfile((current) => ({
                  ...current,
                  target_readers,
                }))
              }
            />
            <label className="space-y-2 text-sm font-medium text-slate-700">
              特别说明
              <Textarea
                value={policyProfile.special_notes}
                onChange={(event) =>
                  setPolicyProfile((current) => ({
                    ...current,
                    special_notes: event.target.value,
                  }))
                }
                placeholder="没有可留空"
              />
            </label>
          </div>
          <div className="flex flex-wrap gap-3">
            <Button
              type="button"
              variant="secondary"
              onClick={handleSavePolicyDraft}
              disabled={
                !selectedUnitId ||
                !policyProfile.fit_focus.trim() ||
                policyProfile.accepted_scope.length === 0 ||
                policyProfile.target_readers.length === 0
              }
            >
              {selectedPolicyVersion?.status === "draft"
                ? "保存草稿"
                : "基于此版本创建草稿"}
            </Button>
            <Button
              type="button"
              onClick={handleFreezePolicy}
              disabled={selectedPolicyVersion?.status !== "draft"}
            >
              冻结并进入试运行
            </Button>
          </div>
          {selectedPolicyVersion ? (
            <details className="rounded-xl border border-slate-200 px-4 py-3 text-xs text-slate-600">
              <summary className="cursor-pointer font-medium text-slate-700">
                查看技术审计信息
              </summary>
              <p className="mt-2 break-all">
                内容摘要：{selectedPolicyVersion.content_sha256}
              </p>
              <p className="mt-1">
                模型配置：{selectedPolicyVersion.model_set_version}
              </p>
              <p className="mt-1">
                互评协议：{selectedPolicyVersion.review_protocol_version}
              </p>
            </details>
          ) : null}
        </CardContent>
      </Card>
      ) : null}

      {activeView === "users" ? (
      <Card>
        <CardHeader>
          <CardTitle>邀请记录</CardTitle>
          <CardDescription>查看、重新发送或撤销尚未使用的账户邀请。</CardDescription>
        </CardHeader>
        <CardContent>
          <Table className="min-w-[720px]">
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
              {invitations.length === 0 ? (
                <TableRow>
                  <TableCell
                    colSpan={5}
                    className="py-10 text-center text-sm text-slate-500"
                  >
                    暂无内部成员邀请记录。
                  </TableCell>
                </TableRow>
              ) : (
                invitations.map((invitation) => (
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
                ))
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
      ) : null}

      {activeView === "units" ? (
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
      ) : null}

      {activeView === "activation" ? (
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
            <div className="grid gap-3 sm:grid-cols-[1fr_160px_auto]">
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
              <Select
                value={membershipRole}
                onChange={(event) =>
                  setMembershipRole(
                    event.target.value as "editor" | "unit_admin"
                  )
                }
              >
                <option value="editor">编辑</option>
                <option value="unit_admin">单元负责人</option>
              </Select>
              <Button
                type="button"
                variant="secondary"
                onClick={handleAddMember}
                disabled={!selectedUnitId || !selectedEditorId}
              >
                更新成员
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
                <div className="flex flex-wrap items-center gap-3 rounded-xl border border-slate-200 p-3">
                  <label className="cursor-pointer rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50">
                    选择样本清单
                    <input
                      type="file"
                      className="hidden"
                      onChange={(event) =>
                        void handleManifestFile(event.target.files?.[0])
                      }
                    />
                  </label>
                  <span className="text-sm text-slate-600">
                    {manifestFileName || "尚未选择文件"}
                  </span>
                  {manifestSha256 ? (
                    <span className="w-full break-all text-xs text-slate-500">
                      本地计算摘要：{manifestSha256}
                    </span>
                  ) : null}
                </div>
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
              <div className="flex flex-wrap gap-3">
                <Button
                  type="button"
                  variant="secondary"
                  onClick={handleCreateValidation}
                  disabled={
                    !trialPolicy ||
                    sampleCount < 1 ||
                    !/^[0-9a-f]{64}$/.test(manifestSha256) ||
                    activationReason.trim().length < 5
                  }
                >
                  登记验证记录
                </Button>
                <Button
                  type="button"
                  onClick={handleActivate}
                  disabled={
                    !trialPolicy ||
                    !signedValidation ||
                    activationReason.trim().length < 5
                  }
                >
                  使用编辑签署并正式启用
                </Button>
              </div>
            )}
            {trialPolicy ? (
              <p className="text-xs leading-5 text-slate-500">
                当前试运行策略：第 {trialPolicy.version} 版；
                {signedValidation
                  ? "单元负责人已经签署。"
                  : "尚待单元负责人签署验证记录。"}
              </p>
            ) : null}
          </CardContent>
        </Card>
      ) : null}

      {activeView === "models" ? (
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
          <div className="grid gap-3 md:grid-cols-[1fr_auto_auto]">
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
            <Button
              type="button"
              variant="secondary"
              onClick={handleLoadComparison}
              disabled={!candidateSubmissionId.trim()}
            >
              查看新旧模型比较
            </Button>
          </div>
          {modelComparison ? (
            <div className="rounded-xl border border-slate-200 bg-white p-4">
              <p className="font-medium text-slate-900">
                新旧模型任务：{modelComparison.items.length} 组
              </p>
              <div className="mt-3 grid gap-2 md:grid-cols-2">
                {modelComparison.items.map((item) => (
                  <div
                    key={item.task_id}
                    className="rounded-lg bg-slate-50 px-3 py-2 text-sm text-slate-700"
                  >
                    <p>
                      {item.run_role === "candidate"
                        ? "新四模型"
                        : "原四模型"}
                      ：{taskStatusLabel(item.status)}
                    </p>
                    <p className="mt-1 text-xs text-slate-500">
                      已形成 {item.metrics.length} 个维度结果
                    </p>
                  </div>
                ))}
              </div>
              {modelComparison.deltas?.length ? (
                <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                  {modelComparison.deltas.map((delta) => (
                    <div
                      key={delta.dimension_key}
                      className="rounded-lg border border-slate-100 px-3 py-2 text-xs text-slate-600"
                    >
                      {dimensionLabel(delta.dimension_key)}：
                      {delta.delta >= 0 ? "+" : ""}
                      {delta.delta.toFixed(1)} 分
                    </div>
                  ))}
                </div>
              ) : null}
            </div>
          ) : null}
          <p className="text-xs leading-5 text-slate-500">
            仅用于获授权样本的校准、冻结测试和最终验证。候选模型通过编辑签字前不得切换为生产配置。
          </p>
        </CardContent>
      </Card>
      ) : null}
      </main>
    </div>
  );
}

function normalizePolicyProfile(
  profile: EditorialPolicyProfile
): EditorialPolicyProfile {
  return {
    ...profile,
    accepted_scope:
      profile.accepted_scope?.length > 0
        ? profile.accepted_scope
        : [profile.fit_focus],
    excluded_scope: profile.excluded_scope ?? [],
    column_positioning: profile.column_positioning ?? [],
    article_types: profile.article_types ?? ["法学研究论文"],
    target_readers:
      profile.target_readers?.length > 0
        ? profile.target_readers
        : ["法学研究者与法律实务工作者"],
    special_notes: profile.special_notes ?? "",
  };
}

function SummaryMetric({
  label,
  value,
}: {
  label: string;
  value: number;
}) {
  return (
    <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
      <p className="text-sm text-slate-500">{label}</p>
      <p className="mt-2 text-2xl font-semibold text-slate-950">{value}</p>
    </div>
  );
}

function PolicyListField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string[];
  onChange: (value: string[]) => void;
}) {
  return (
    <label className="space-y-2 text-sm font-medium text-slate-700">
      {label}
      <Textarea
        value={value.join("\n")}
        onChange={(event) =>
          onChange(
            event.target.value
              .split("\n")
              .map((item) => item.trim())
              .filter(Boolean)
          )
        }
        placeholder="每行填写一项"
      />
    </label>
  );
}

export async function sha256File(file: File): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", await file.arrayBuffer());
  return Array.from(new Uint8Array(digest))
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

function policyStatusLabel(status: EditorialPolicyVersion["status"]): string {
  return {
    draft: "草稿",
    trial: "试运行",
    active: "正式使用",
    retired: "历史版本",
  }[status];
}

function taskStatusLabel(status: string): string {
  return (
    {
      pending: "等待处理",
      processing: "处理中",
      reviewing: "等待专家复核",
      completed: "已完成",
      failed: "处理失败",
    }[status] ?? "状态待确认"
  );
}

function dimensionLabel(key: string): string {
  return (
    {
      problem_originality: "研究创新性",
      literature_insight: "现状洞察度",
      analytical_framework: "理论建构力",
      logical_coherence: "逻辑连贯性",
      conclusion_consensus: "学术共识度",
      forward_extension: "前瞻延展性",
    }[key] ?? "评价维度"
  );
}

const roleLabel: Record<User["role"], string> = {
  submitter: "投稿人",
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
