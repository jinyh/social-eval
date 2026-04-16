import { FormEvent, useEffect, useMemo, useState } from "react";

import {
  assignExpert,
  createInvitation,
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
import type { PaperListItem, PaperStatus, ReviewQueueItem, ReviewTask, User } from "./lib/types";
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

function SubmitterDashboard() {
  const [papers, setPapers] = useState<PaperListItem[]>([]);
  const [status, setStatus] = useState<PaperStatus | null>(null);
  const [report, setReport] = useState<string>("");
  const [message, setMessage] = useState<string>("");

  const refreshPapers = async () => setPapers(await listPapers());

  useEffect(() => {
    void refreshPapers().catch(() => setPapers([]));
  }, []);

  const handleUpload = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = event.currentTarget;
    const input = form.elements.namedItem("paper") as HTMLInputElement | null;
    const file = input?.files?.[0];
    if (!file) {
      return;
    }
    const payload = await uploadPaper(file);
    setMessage(`Uploaded paper ${payload.paper_id}`);
    setStatus(await getPaperStatus(payload.paper_id));
    setReport(JSON.stringify(await getPublicReport(payload.paper_id), null, 2));
    await refreshPapers();
    form.reset();
  };

  const latestPaperId = useMemo(() => papers[0]?.paper_id, [papers]);

  return (
    <div className="dashboard-grid">
      <section className="panel">
        <h2>Submitter Dashboard</h2>
        <form onSubmit={handleUpload} className="stack">
          <input name="paper" type="file" accept=".pdf,.docx,.txt" />
          <button type="submit">Upload paper</button>
        </form>
        {message ? <p>{message}</p> : null}
        <button
          type="button"
          onClick={async () => {
            if (!latestPaperId) return;
            setStatus(await getPaperStatus(latestPaperId));
            setReport(JSON.stringify(await getPublicReport(latestPaperId), null, 2));
          }}
        >
          Refresh latest status
        </button>
      </section>

      <section className="panel">
        <h3>My Papers</h3>
        <ul className="list">
          {papers.map((paper) => (
            <li key={paper.paper_id}>
              <strong>{paper.title ?? paper.original_filename}</strong>
              <span>{paper.paper_status}</span>
            </li>
          ))}
        </ul>
      </section>

      <section className="panel">
        <h3>Latest Status</h3>
        <pre>{status ? JSON.stringify(status, null, 2) : "No status loaded yet."}</pre>
      </section>

      <section className="panel">
        <h3>Public Report</h3>
        <pre>{report || "No report loaded yet."}</pre>
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
