import { FormEvent, useEffect, useState } from "react";

import {
  assignExpert,
  createInvitation,
  exportSimpleReport,
  getCurrentUser,
  getInternalReport,
  getPaperStatus,
  getPublicReport,
  getReviewQueue,
  listExperts,
  listMyReviews,
  listPapers,
  listUsers,
  login,
  logout,
  submitReview,
  uploadPaper,
} from "./lib/api";
import type { DimensionScore, PaperListItem, PaperStatus, PublicReport, ReviewQueueItem, ReviewTask, User } from "./lib/types";
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
      setError(err instanceof Error ? err.message : "Login failed");
    }
  };

  return (
    <section className="panel">
      <h1>SocialEval Login</h1>
      <form className="stack" onSubmit={handleSubmit}>
        <label>
          Email
          <input value={email} onChange={(event) => setEmail(event.target.value)} />
        </label>
        <label>
          Password
          <input
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </label>
        <button type="submit">Sign in</button>
        {error ? <p className="error">{error}</p> : null}
      </form>
    </section>
  );
}

type SimpleScoreCardProps = {
  dimensions: DimensionScore[];
};

function SimpleScoreCard({ dimensions }: SimpleScoreCardProps) {
  return (
    <div className="score-card">
      {dimensions.map((dim, index) => (
        <div key={index} className="score-row">
          <div className="score-header">
            <span className="dimension-name">{dim.name_zh}</span>
            <span className="dimension-score">{dim.ai.mean_score.toFixed(1)}分</span>
          </div>
          <p className="dimension-summary">{dim.summary || "暂无总结"}</p>
        </div>
      ))}
    </div>
  );
}

function SubmitterDashboard() {
  const [papers, setPapers] = useState<PaperListItem[]>([]);
  const [selectedPaperId, setSelectedPaperId] = useState<string | null>(null);
  const [status, setStatus] = useState<PaperStatus | null>(null);
  const [report, setReport] = useState<PublicReport | null>(null);
  const [message, setMessage] = useState<string>("");
  const [downloading, setDownloading] = useState<boolean>(false);

  const refreshPapers = async () => setPapers(await listPapers());

  useEffect(() => {
    void refreshPapers().catch(() => setPapers([]));
  }, []);

  useEffect(() => {
    if (papers.length > 0 && !selectedPaperId) {
      setSelectedPaperId(papers[0].paper_id);
    }
  }, [papers, selectedPaperId]);

  useEffect(() => {
    if (selectedPaperId) {
      loadReport(selectedPaperId).catch(() => setReport(null));
    }
  }, [selectedPaperId]);

  const loadReport = async (paperId: string) => {
    setStatus(await getPaperStatus(paperId));
    setReport(await getPublicReport(paperId));
  };

  const handleUpload = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = event.currentTarget;
    const input = form.elements.namedItem("paper") as HTMLInputElement | null;
    const file = input?.files?.[0];
    if (!file) {
      return;
    }
    const payload = await uploadPaper(file);
    setMessage(`上传成功: ${payload.paper_id}`);
    setSelectedPaperId(payload.paper_id);
    await refreshPapers();
    form.reset();
  };

  const handleDownloadReport = async () => {
    if (!selectedPaperId) return;
    setDownloading(true);
    try {
      const blob = await exportSimpleReport(selectedPaperId);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `report-${selectedPaperId}.pdf`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "下载失败");
    } finally {
      setDownloading(false);
    }
  };

  const getStatusLabel = (paperStatus: string): string => {
    const statusMap: Record<string, string> = {
      pending: "待处理",
      prechecking: "准入检查中",
      precheck_failed: "准入检查未通过",
      evaluating: "评价中",
      reviewing: "专家复核中",
      completed: "已完成",
      failed: "处理失败",
    };
    return statusMap[paperStatus] || paperStatus;
  };

  return (
    <div className="dashboard-grid submitter-view">
      <section className="panel upload-section">
        <h2>投稿者工作台</h2>
        <form onSubmit={handleUpload} className="stack">
          <input name="paper" type="file" accept=".pdf,.docx,.txt" />
          <button type="submit">上传论文</button>
        </form>
        {message ? <p className="info-message">{message}</p> : null}
      </section>

      <section className="panel papers-section">
        <h3>我的论文</h3>
        <ul className="list paper-list">
          {papers.length === 0 ? (
            <li className="empty-hint">暂无论文，请上传</li>
          ) : (
            papers.map((paper) => (
              <li
                key={paper.paper_id}
                className={paper.paper_id === selectedPaperId ? "selected" : ""}
                onClick={() => setSelectedPaperId(paper.paper_id)}
              >
                <div className="paper-title">{paper.title ?? paper.original_filename}</div>
                <span className={`paper-status status-${paper.paper_status}`}>
                  {getStatusLabel(paper.paper_status)}
                </span>
              </li>
            ))
          )}
        </ul>
      </section>

      <section className="panel results-section">
        <h3>评价结果</h3>
        {report ? (
          <div className="report-content">
            <div className="report-header">
              <h4 className="report-title">{report.title ?? "未命名论文"}</h4>
              <div className="total-score">
                <span className="score-label">总分</span>
                <span className="score-value">{report.weighted_total.toFixed(1)}</span>
              </div>
            </div>

            <div className="report-conclusion">
              <h5>综合结论</h5>
              <p>{report.conclusion ?? "暂无结论"}</p>
            </div>

            <SimpleScoreCard dimensions={report.dimensions} />

            {report.expert_conclusion ? (
              <div className="expert-comment">
                <h5>专家评语</h5>
                <p>{report.expert_conclusion}</p>
              </div>
            ) : null}

            <button
              type="button"
              className="download-btn"
              onClick={handleDownloadReport}
              disabled={downloading}
            >
              {downloading ? "下载中..." : "下载报告"}
            </button>
          </div>
        ) : (
          <p className="empty-hint">选择一篇论文查看评价结果</p>
        )}
      </section>
    </div>
  );
}

function EditorDashboard() {
  const [queue, setQueue] = useState<ReviewQueueItem[]>([]);
  const [experts, setExperts] = useState<User[]>([]);
  const [selectedExpertId, setSelectedExpertId] = useState<string>("");
  const [internalReport, setInternalReport] = useState<string>("");

  const refresh = async () => {
    const [queueItems, expertItems] = await Promise.all([getReviewQueue(), listExperts()]);
    setQueue(queueItems);
    setExperts(expertItems);
    setSelectedExpertId(expertItems[0]?.id ?? "");
  };

  useEffect(() => {
    void refresh().catch(() => {
      setQueue([]);
      setExperts([]);
      setSelectedExpertId("");
    });
  }, []);

  return (
    <div className="dashboard-grid">
      <section className="panel">
        <h2>Editor Dashboard</h2>
        <button
          type="button"
          onClick={async () => {
            if (!queue[0] || !selectedExpertId) return;
            await assignExpert(queue[0].task_id, [selectedExpertId]);
            await refresh();
          }}
        >
          Assign first queued task
        </button>
        <select value={selectedExpertId} onChange={(event) => setSelectedExpertId(event.target.value)}>
          {experts.map((expert) => (
            <option value={expert.id} key={expert.id}>
              {expert.display_name ?? expert.email}
            </option>
          ))}
        </select>
      </section>

      <section className="panel">
        <h3>Review Queue</h3>
        <ul className="list">
          {queue.map((item) => (
            <li key={item.task_id}>
              <div>{item.paper_title ?? item.paper_id}</div>
              <small>{item.low_confidence_dimensions.join(", ")}</small>
              <button
                type="button"
                onClick={async () => setInternalReport(JSON.stringify(await getInternalReport(item.paper_id), null, 2))}
              >
                Open internal report
              </button>
            </li>
          ))}
        </ul>
      </section>

      <section className="panel">
        <h3>Internal Report</h3>
        <pre>{internalReport || "Select a queued item to inspect its report."}</pre>
      </section>
    </div>
  );
}

function ExpertDashboard() {
  const [reviews, setReviews] = useState<ReviewTask[]>([]);

  const refresh = async () => setReviews(await listMyReviews());

  useEffect(() => {
    void refresh().catch(() => setReviews([]));
  }, []);

  return (
    <div className="dashboard-grid">
      <section className="panel">
        <h2>Expert Dashboard</h2>
        <ul className="list">
          {reviews.map((review) => (
            <li key={review.review_id}>
              <span>{review.task_id}</span>
              <span>{review.status}</span>
              <button
                type="button"
                onClick={async () => {
                  await submitReview(review.review_id);
                  await refresh();
                }}
              >
                Submit standard review
              </button>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}

function AdminDashboard() {
  const [users, setUsers] = useState<User[]>([]);
  const [inviteEmail, setInviteEmail] = useState("new-user@example.com");
  const [inviteRole, setInviteRole] = useState("submitter");

  const refresh = async () => setUsers(await listUsers());

  useEffect(() => {
    void refresh().catch(() => setUsers([]));
  }, []);

  return (
    <div className="dashboard-grid">
      <section className="panel">
        <h2>Admin Dashboard</h2>
        <form
          className="stack"
          onSubmit={async (event) => {
            event.preventDefault();
            await createInvitation(inviteEmail, inviteRole);
            await refresh();
          }}
        >
          <input value={inviteEmail} onChange={(event) => setInviteEmail(event.target.value)} />
          <select value={inviteRole} onChange={(event) => setInviteRole(event.target.value)}>
            <option value="submitter">Submitter</option>
            <option value="editor">Editor</option>
            <option value="expert">Expert</option>
            <option value="admin">Admin</option>
          </select>
          <button type="submit">Create invitation</button>
        </form>
      </section>

      <section className="panel">
        <h3>User Directory</h3>
        <ul className="list">
          {users.map((user) => (
            <li key={user.id}>
              {user.display_name ?? user.email} — {user.role}
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}

function RoleDashboard({ user }: { user: User }) {
  if (user.role === "submitter") {
    return <SubmitterDashboard />;
  }
  if (user.role === "editor") {
    return <EditorDashboard />;
  }
  if (user.role === "expert") {
    return <ExpertDashboard />;
  }
  return <AdminDashboard />;
}

export function App({ initialUser }: AppProps) {
  const [user, setUser] = useState<User | null | undefined>(initialUser);

  useEffect(() => {
    if (initialUser !== undefined) {
      return;
    }
    void getCurrentUser()
      .then((currentUser) => setUser(currentUser))
      .catch(() => setUser(null));
  }, [initialUser]);

  if (user === undefined) {
    return <div className="shell"><p>Loading session…</p></div>;
  }

  if (user === null) {
    return (
      <div className="shell">
        <LoginForm onLoggedIn={setUser} />
      </div>
    );
  }

  return (
    <div className="shell">
      <header className="app-header">
        <div>
          <h1>SocialEval</h1>
          <p>{user.display_name ?? user.email}</p>
        </div>
        <button
          type="button"
          onClick={async () => {
            await logout();
            setUser(null);
          }}
        >
          Sign out
        </button>
      </header>
      <RoleDashboard user={user} />
    </div>
  );
}
