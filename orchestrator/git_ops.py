"""Git automation: branch creation and commits per phase."""

import subprocess
from pathlib import Path
from config import PROJECT_ROOT


class GitOps:
    def __init__(self, project_root: Path = PROJECT_ROOT):
        self.root = project_root

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _git(self, *args: str, check: bool = True) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git", *args],
            cwd=str(self.root),
            capture_output=True,
            text=True,
            check=check,
        )

    def _current_branch(self) -> str:
        return self._git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()

    def _branch_exists(self, name: str) -> bool:
        result = self._git("branch", "--list", name, check=False)
        return bool(result.stdout.strip())

    # ── Public API ─────────────────────────────────────────────────────────────

    def ensure_phase_branch(self, phase: str) -> None:
        """Create phase/{phase} branch from current HEAD if it doesn't exist."""
        branch = f"phase/{phase}"
        if not self._branch_exists(branch):
            self._git("branch", branch)
            print(f"    [git] created branch {branch}")

    def create_feat_branch(self, feat: str) -> None:
        """Create and checkout feat/{feat} from current HEAD."""
        branch = f"feat/{feat}"
        if self._branch_exists(branch):
            self._git("checkout", branch)
        else:
            self._git("checkout", "-b", branch)
        print(f"    [git] checked out {branch}")

    def commit(self, role: str, phase: str, subject: str, paths: list[str]) -> None:
        """
        Stage given paths and create a conventional commit.

        Commit type mapping:
          planner / builder → feat
          reviewer          → docs
          fixer             → fix
        """
        type_map = {
            "planner":  "feat",
            "builder":  "feat",
            "reviewer": "docs",
            "fixer":    "fix",
        }
        commit_type = type_map.get(role, "chore")
        message = f"{commit_type}({role}): {subject}"

        # Stage only specified paths that exist
        staged = []
        for p in paths:
            full = self.root / p
            if full.exists():
                self._git("add", str(full))
                staged.append(p)

        if not staged:
            print(f"    [git] nothing to stage for {role}")
            return

        self._git("commit", "-m", message)
        print(f"    [git] committed: {message}")

    def merge_feat_to_phase(self, feat: str, phase: str) -> None:
        """
        Merge feat/{feat} into phase/{phase} with --no-ff.
        Leaves the phase branch checked out.
        """
        feat_branch  = f"feat/{feat}"
        phase_branch = f"phase/{phase}"

        self.ensure_phase_branch(phase)
        self._git("checkout", phase_branch)
        self._git("merge", "--no-ff", feat_branch, "-m", f"merge: {feat_branch} → {phase_branch}")
        print(f"    [git] merged {feat_branch} → {phase_branch}")

    # ── Phase-level helpers ────────────────────────────────────────────────────

    def commit_planner(self, iteration: int = 0) -> None:
        feat = "planner-architecture"
        self.create_feat_branch(feat)
        paths = [
            "plan.md",
            "docs/architecture.md", "docs/data-flow.md", "docs/tradeoff.md",
            "docs/failure-case.md", "docs/kafka-design.md",
            "conversation", "cost",
        ]
        self.commit("planner", "P1", "define full system architecture and data pipeline design", paths)
        self.merge_feat_to_phase(feat, "planner")

    def commit_builder(self) -> None:
        feat = "builder-implementation"
        self.create_feat_branch(feat)
        paths = [
            "producer", "consumer", "api", "infra", "plan.md",
            "conversation", "cost",
        ]
        self.commit("builder", "P2", "implement full backend with docker-compose and openapi spec", paths)
        self.merge_feat_to_phase(feat, "builder")

    def commit_reviewer(self, iteration: int) -> None:
        feat = f"reviewer-iter{iteration}"
        self.create_feat_branch(feat)
        paths = ["conversation", "cost"]
        self.commit("reviewer", f"P3-iter{iteration}", f"add review report for iteration {iteration}", paths)
        self.merge_feat_to_phase(feat, f"iter-{iteration}")

    def commit_fixer(self, iteration: int) -> None:
        feat = f"fixer-iter{iteration}"
        self.create_feat_branch(feat)
        # Stage all modified tracked files + conversation + cost
        self._git("add", "-u")
        self._git("add", str(self.root / "conversation"), str(self.root / "cost"))
        result = self._git("diff", "--cached", "--name-only", check=False)
        if result.stdout.strip():
            self._git(
                "commit", "-m",
                f"fix(fixer): apply fixes for iteration {iteration}",
            )
            print(f"    [git] committed fixer iteration {iteration}")
        else:
            print(f"    [git] nothing to commit for fixer iteration {iteration}")
        self.merge_feat_to_phase(feat, f"iter-{iteration}")
