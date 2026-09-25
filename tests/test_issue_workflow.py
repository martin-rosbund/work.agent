"""Actual local Git operations with an in-memory GitHub CLI double; no real publish."""
import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("workflow", ROOT / "skills/github-issue-fix/scripts/issue_workflow.py")
workflow = importlib.util.module_from_spec(spec)
spec.loader.exec_module(workflow)


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        # Keep fixture files in the project cache; no real project checkout used.
        (ROOT / ".cache").mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="issue-skill-", dir=ROOT / ".cache")
        self.root = Path(self.temp.name)
        self.repo = self.root / "checkout"
        self.remote = self.root / "remote.git"
        self.repo.mkdir()
        workflow.git(self.root, "init", "--bare", "--initial-branch=main", str(self.remote))
        workflow.git(self.repo, "init", "--initial-branch=main")
        workflow.git(self.repo, "config", "user.name", "Isolated Test")
        workflow.git(self.repo, "config", "user.email", "test@example.invalid")
        (self.repo / "code.txt").write_text("before\n")
        workflow.git(self.repo, "add", "code.txt")
        workflow.git(self.repo, "commit", "-m", "fixture")
        workflow.git(self.repo, "remote", "add", "origin", str(self.remote))
        workflow.git(self.repo, "push", "-u", "origin", "main")
        self.prs, self.calls = [], []
        self.uncertain_push = False
        self.uncertain_pr = False
        original = workflow.run
        def fake(args, cwd, check=True):
            if args[0] != "gh":
                result = original(args, cwd, check)
                if args[1] == "push" and self.uncertain_push:
                    result.returncode = 1  # Remote accepted; CLI lost confirmation.
                return result
            self.calls.append(args)
            if args[1:3] == ["repo", "view"]:
                data = {"nameWithOwner": "test/project", "defaultBranchRef": {"name": "main"}}
            elif args[1:3] == ["issue", "view"]:
                data = {"number": 123, "title": "Fix timezone", "body": "Bug", "comments": [{"body": "Reproduced"}], "state": "OPEN"}
            elif args[1:3] == ["pr", "list"]:
                data = self.prs
            elif args[1:3] == ["pr", "create"]:
                self.assertIn("--draft", args)
                self.prs.append({"url": "https://github.com/test/project/pull/1", "isDraft": True,
                    "baseRefName": "main", "headRefName": args[args.index("--head") + 1]})
                data = {}
            else:
                raise AssertionError(args)
            return subprocess.CompletedProcess(args, 1 if self.uncertain_pr and args[1:3] == ["pr", "create"] else 0, json.dumps(data), "")
        self.patcher = patch.object(workflow, "run", fake)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        assert self.root.resolve().is_relative_to((ROOT / ".cache").resolve())
        # TemporaryDirectory's Windows Git files may be read-only. Keep failed
        # cleanup isolated, never recursively delete a computed external path.
        import os, stat
        for parent, _, files in os.walk(self.root):
            for name in files:
                os.chmod(Path(parent) / name, stat.S_IWRITE | stat.S_IREAD)
        self.temp.cleanup()

    def test_clean_checkout_branch_before_change_and_draft_publication(self):
        prepared = workflow.prepare("#123", self.repo)
        self.assertEqual(prepared["directory"], str(self.repo))
        self.assertTrue(prepared["branch"].startswith("codex/issue-123-"))
        self.assertEqual(prepared["issue"]["comments"][0]["body"], "Reproduced")
        (self.repo / "code.txt").write_text("fixed\n")
        body = self.root / "body.md"
        body.write_text("Correct timezone conversion.\n\nValidation: fixture test.\n\nCloses #123\n")
        result = workflow.publish("test/project#123", self.repo, "Fix timezone", body, "Fix timezone (#123)", ["code.txt"])
        self.assertEqual(result["url"], self.prs[0]["url"])
        self.assertEqual(workflow.git(self.repo, "status", "--porcelain"), "")
        self.assertIn(prepared["branch"], workflow.git(self.repo, "ls-remote", "--heads", "origin"))
        again = workflow.publish("#123", self.repo, "Fix timezone", body, "Fix timezone (#123)", [])
        self.assertTrue(again["existing"])
        self.assertEqual(sum(c[1:3] == ["pr", "create"] for c in self.calls), 1)

    def test_dirty_checkout_preserved_in_separate_worktree(self):
        (self.repo / "code.txt").write_text("unrelated user changes\n")
        result = workflow.prepare("https://github.com/test/project/issues/123", self.repo)
        self.assertNotEqual(result["directory"], str(self.repo))
        self.assertEqual((self.repo / "code.txt").read_text(), "unrelated user changes\n")
        self.assertEqual((Path(result["directory"]) / "code.txt").read_text(), "before\n")
        self.assertEqual(workflow.git(self.repo, "branch", "--show-current"), "main")

    def test_resume_existing_clean_branch(self):
        first = workflow.prepare("#123", self.repo)
        again = workflow.prepare("#123", self.repo)
        self.assertEqual(first["branch"], again["branch"])
        self.assertEqual(first["directory"], again["directory"])

    def test_uncertain_push_and_pr_are_verified_without_duplicate_mutations(self):
        workflow.prepare("#123", self.repo)
        (self.repo / "code.txt").write_text("fixed\n")
        body = self.root / "body.md"
        body.write_text("Fix with fixture validation. Closes #123\n")
        self.uncertain_push = self.uncertain_pr = True
        result = workflow.publish("#123", self.repo, "Fix", body, "Fix", ["code.txt"])
        self.assertEqual(result["url"], self.prs[0]["url"])
        self.assertEqual(sum(c[1:3] == ["pr", "create"] for c in self.calls), 1)

    def test_existing_staged_changes_are_not_committed(self):
        workflow.prepare("#123", self.repo)
        (self.repo / "unrelated.txt").write_text("user work")
        workflow.git(self.repo, "add", "unrelated.txt")
        body = self.root / "body.md"
        body.write_text("Closes #123\n")
        with self.assertRaisesRegex(ValueError, "Unrelated files"):
            workflow.publish("#123", self.repo, "Fix", body, "Fix", ["code.txt"])
        self.assertIn("unrelated.txt", workflow.git(self.repo, "diff", "--cached", "--name-only"))
        self.assertFalse(self.prs)

    def test_unrelated_clean_branch_uses_worktree(self):
        workflow.git(self.repo, "switch", "-c", "other-work")
        result = workflow.prepare("#123", self.repo)
        self.assertNotEqual(result["directory"], str(self.repo))
        self.assertEqual(workflow.git(self.repo, "branch", "--show-current"), "other-work")

    def test_unpublished_default_branch_commits_are_not_included(self):
        (self.repo / "unrelated.txt").write_text("unpublished user work")
        workflow.git(self.repo, "add", "unrelated.txt")
        workflow.git(self.repo, "commit", "-m", "Unrelated local work")
        result = workflow.prepare("#123", self.repo)
        self.assertNotEqual(result["directory"], str(self.repo))
        self.assertFalse((Path(result["directory"]) / "unrelated.txt").exists())
        self.assertTrue((self.repo / "unrelated.txt").exists())

    def test_dirty_issue_branch_is_never_overwritten(self):
        workflow.prepare("#123", self.repo)
        (self.repo / "code.txt").write_text("unfinished\n")
        with self.assertRaisesRegex(ValueError, "existing issue worktree"):
            workflow.prepare("#123", self.repo)
        self.assertEqual((self.repo / "code.txt").read_text(), "unfinished\n")

    def test_explicit_repository_mismatch_and_non_draft_refused(self):
        with self.assertRaisesRegex(ValueError, "does not match"):
            workflow.prepare("other/project#123", self.repo)
        self.prs.append({"isDraft": False, "baseRefName": "main", "url": "example"})
        with self.assertRaisesRegex(ValueError, "unambiguous draft"):
            workflow.prepare("#123", self.repo)

if __name__ == "__main__":
    unittest.main()
