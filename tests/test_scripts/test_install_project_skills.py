from __future__ import annotations

import subprocess
import sys
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2] / "scripts" / "install_project_skills.py"
)


def test_install_project_skills_creates_symlinks_for_each_skill(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    skill_root = repo_root / "agent-skills"
    target_dir = tmp_path / "target-skills"

    for skill_name in ("skill-one", "skill-two"):
        skill_dir = skill_root / skill_name
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            f"---\nname: {skill_name}\ndescription: test\n---\n", encoding="utf-8"
        )

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--repo-root",
            str(repo_root),
            "--target-dir",
            str(target_dir),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert (target_dir / "skill-one").is_symlink()
    assert (target_dir / "skill-two").is_symlink()
    assert (target_dir / "skill-one").resolve() == skill_root / "skill-one"
    assert (target_dir / "skill-two").resolve() == skill_root / "skill-two"


def test_install_project_skills_fails_when_no_skills_exist(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / "agent-skills").mkdir(parents=True)
    target_dir = tmp_path / "target-skills"

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--repo-root",
            str(repo_root),
            "--target-dir",
            str(target_dir),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "No project skills found" in result.stderr
