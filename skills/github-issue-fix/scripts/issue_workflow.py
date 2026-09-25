"""Deterministic Git mechanics; no implementation, test claims or autonomous trigger."""
import argparse
import json
import re
import subprocess
import unicodedata
from pathlib import Path


def run(args, cwd, check=True):
    result = subprocess.run(args, cwd=cwd, text=True, encoding="utf-8", capture_output=True)
    if check and result.returncode:
        # Git/gh errors may include authenticated URLs. Avoid echoing raw stderr.
        raise RuntimeError(f"{args[0]} {args[1]} failed (exit {result.returncode}). Check repository access/authentication locally.")
    return result


def git(cwd, *args):
    return run(["git", *args], cwd).stdout.strip()


def gh(cwd, *args):
    return json.loads(run(["gh", *args], cwd).stdout)


def resolve(reference, cwd):
    current = gh(cwd, "repo", "view", "--json", "nameWithOwner,defaultBranchRef")
    match = re.fullmatch(r"(?:(?P<repo>[\w.-]+/[\w.-]+))?#(?P<number>[1-9][0-9]*)", reference)
    if not match:
        match = re.fullmatch(r"https://github\.com/(?P<repo>[\w.-]+/[\w.-]+)/issues/(?P<number>[1-9][0-9]*)/?", reference)
    if not match:
        raise ValueError("Use #123, owner/repository#123 or a GitHub issue URL.")
    repository = match.group("repo") or current["nameWithOwner"]
    if repository.casefold() != current["nameWithOwner"].casefold():
        raise ValueError("Explicit issue repository does not match this checkout. Locate or clone that repository first.")
    return repository, int(match.group("number")), current["defaultBranchRef"]["name"]


def pull_requests(cwd, repository, branch):
    return gh(cwd, "pr", "list", "--repo", repository, "--head", branch, "--state", "open",
              "--json", "url,isDraft,headRefName,baseRefName")


def ensure_draft(rows, default):
    if len(rows) > 1 or any(not row["isDraft"] or row["baseRefName"] != default for row in rows):
        raise ValueError("An existing PR is not an unambiguous draft against the default branch. Inspect it before proceeding.")


def prepare(reference, cwd):
    cwd = Path(git(cwd, "rev-parse", "--show-toplevel"))
    repository, number, default = resolve(reference, cwd)
    issue = gh(cwd, "issue", "view", str(number), "--repo", repository, "--json", "number,title,body,comments,url,state,labels,assignees")
    git(cwd, "fetch", "origin", default)
    dirty = bool(git(cwd, "status", "--porcelain"))
    current = git(cwd, "branch", "--show-current")
    if not dirty and current == default:
        git(cwd, "pull", "--ff-only", "origin", default)
    clean_default = (not dirty and current == default and
                     git(cwd, "rev-parse", "HEAD") == git(cwd, "rev-parse", "refs/remotes/origin/" + default))
    prefix = f"codex/issue-{number}-"
    branches = git(cwd, "for-each-ref", "--format=%(refname:short)", "refs/heads/" + prefix + "*").splitlines()
    # Fetch matching remote branches without overwriting any local branch.
    remote = git(cwd, "ls-remote", "--heads", "origin", "refs/heads/" + prefix + "*")
    remote_branches = [line.split("\t", 1)[1].removeprefix("refs/heads/") for line in remote.splitlines() if line]
    candidates = sorted(set(branches + remote_branches))
    if len(candidates) > 1:
        raise ValueError("Several issue branches exist. Inspect their PRs and choose the matching branch before continuing.")
    slug = re.sub(r"[^a-z0-9]+", "-", unicodedata.normalize("NFKD", issue["title"]).encode("ascii", "ignore").decode().lower()).strip("-")[:45] or "fix"
    branch = candidates[0] if candidates else prefix + slug
    prs = pull_requests(cwd, repository, branch)
    ensure_draft(prs, default)
    occupied = {}
    location = None
    for line in git(cwd, "worktree", "list", "--porcelain").splitlines():
        if line.startswith("worktree "):
            location = line[9:]
        elif line.startswith("branch refs/heads/"):
            occupied[line.removeprefix("branch refs/heads/")] = location
    if branch in occupied:
        target = Path(occupied[branch])
        if git(target, "status", "--porcelain"):
            raise ValueError("The existing issue worktree has changes. Preserve and inspect them before controlled resumption.")
        if branch in remote_branches:
            git(target, "fetch", "origin", branch)
            git(target, "merge", "--ff-only", "FETCH_HEAD")
    elif clean_default and not candidates:
        git(cwd, "switch", "-c", branch)
        target = cwd
    else:
        target = cwd.parent / (cwd.name + "-issue-" + str(number))
        if target.exists():
            raise ValueError("The issue worktree directory already exists; inspect it instead of overwriting it.")
        if branch in branches:
            git(cwd, "worktree", "add", str(target), branch)
        elif branch in remote_branches:
            git(cwd, "fetch", "origin", branch)
            git(cwd, "worktree", "add", "-b", branch, str(target), "FETCH_HEAD")
        else:
            git(cwd, "worktree", "add", "-b", branch, str(target), "refs/remotes/origin/" + default)
    return {"repository": repository, "default_branch": default, "branch": branch,
            "directory": str(target), "issue": issue, "draft_pr": prs[0]["url"] if prs else None}


def publish(reference, cwd, title, body_file, message, files):
    repository, number, default = resolve(reference, cwd)
    branch = git(cwd, "branch", "--show-current")
    if not branch.startswith(f"codex/issue-{number}-") or branch == default:
        raise ValueError("Publication requires the issue branch, created before implementation.")
    body = Path(body_file).read_text(encoding="utf-8")
    if not re.search(rf"(?i)\b(?:closes|fixes|resolves)\s+#{number}\b", body):
        raise ValueError("PR description must link this issue with Closes #number.")
    prs = pull_requests(cwd, repository, branch)
    ensure_draft(prs, default)
    root = Path(git(cwd, "rev-parse", "--show-toplevel")).resolve()
    checked_files = []
    for name in files:
        path = (root / name).resolve()
        if not path.is_relative_to(root) or name.startswith("-"):
            raise ValueError("Only explicitly reviewed repository-relative files may be staged.")
        checked_files.append(path.relative_to(root).as_posix())
    staged = set(git(cwd, "diff", "--cached", "--name-only").splitlines())
    if staged - set(checked_files):
        raise ValueError("Unrelated files are already staged; leave them unchanged and inspect first.")
    if checked_files:
        git(cwd, "add", "--", *checked_files)
    if git(cwd, "diff", "--cached", "--name-only"):
        git(cwd, "commit", "-m", message)
    # Resuming after a previous successful push creates no new commit.
    local = git(cwd, "rev-parse", "HEAD")
    result = run(["git", "push", "--set-upstream", "origin", branch], cwd, check=False)
    if result.returncode:
        remote = git(cwd, "ls-remote", "--heads", "origin", "refs/heads/" + branch)
        if not remote.startswith(local + "\t"):
            raise RuntimeError("Push result is not confirmed by the remote; local work retained. Do not retry blindly.")
    if prs:
        return {"url": prs[0]["url"], "existing": True, "branch": branch}
    result = run(["gh", "pr", "create", "--repo", repository, "--draft", "--base", default,
                  "--head", branch, "--title", title, "--body-file", str(Path(body_file).resolve())], cwd, check=False)
    # Always inspect remote state, including after an uncertain CLI result.
    prs = pull_requests(cwd, repository, branch)
    ensure_draft(prs, default)
    if not prs:
        raise RuntimeError("Draft PR creation is not confirmed. Inspect GitHub before retrying; branch was retained.")
    return {"url": prs[0]["url"], "existing": False, "branch": branch}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["prepare", "publish"])
    parser.add_argument("reference")
    parser.add_argument("--cwd", default=".")
    parser.add_argument("--title")
    parser.add_argument("--body-file")
    parser.add_argument("--message")
    parser.add_argument("--files", nargs="*", default=[])
    args = parser.parse_args()
    if args.action == "prepare":
        result = prepare(args.reference, args.cwd)
    else:
        if not all([args.title, args.body_file, args.message]):
            parser.error("publish requires --title, --body-file and --message")
        result = publish(args.reference, args.cwd, args.title, args.body_file, args.message, args.files)
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
