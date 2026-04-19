import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { App } from "./App";

describe("App", () => {
  it("shows the login form when there is no authenticated user", () => {
    render(<App initialUser={null} />);

    expect(screen.getByRole("heading", { name: /socialeval login/i })).toBeInTheDocument();
  });

  it("shows the submitter dashboard for submitter users", () => {
    render(
      <App
        initialUser={{
          id: "user-1",
          email: "submitter@example.com",
          role: "submitter",
          display_name: "Submitter",
        }}
      />
    );

    expect(screen.getByText(/投稿者工作台/i)).toBeInTheDocument();
  });

  it("shows the editor dashboard for editor users", () => {
    render(
      <App
        initialUser={{
          id: "user-2",
          email: "editor@example.com",
          role: "editor",
          display_name: "Editor",
        }}
      />
    );

    expect(screen.getByText(/editor dashboard/i)).toBeInTheDocument();
  });

  it("shows the admin dashboard for admin users", () => {
    render(
      <App
        initialUser={{
          id: "user-3",
          email: "admin@example.com",
          role: "admin",
          display_name: "Admin",
        }}
      />
    );

    expect(screen.getByText(/admin dashboard/i)).toBeInTheDocument();
  });
});
