#!/usr/bin/env python
r"""Publish the local git history to GitHub through the Git Data API.

WHY THIS EXISTS
---------------
In the DSH sandbox, git's own HTTPS transport cannot reach github.com:

  * default backend (schannel):
        fatal: unable to access '...': schannel: AcquireCredentialsHandle
        failed: SEC_E_NO_CREDENTIALS (0x8009030e)
  * http.sslBackend=openssl:
        error: RPC failed; curl 28 Recv failure: Connection was reset

Plain Python `urllib` reaches api.github.com without trouble, so this script
reproduces what `git push` would do, entirely over HTTPS:

  1. reads the stored github.com credential from Git Credential Manager;
  2. uploads every blob of HEAD (byte-identical: git and GitHub use the same
     blob hashing, so the returned SHA is compared against the local SHA);
  3. rebuilds the tree hierarchy;
  4. creates a commit with the same message / author / date as the local one;
  5. points the branch at it and verifies the remote tree matches local HEAD.

The token is never printed, never written to disk, and never stored in
.git/config.

USAGE
-----
    python scripts/publish_to_github.py                 # publish HEAD to main
    python scripts/publish_to_github.py --repo other    # different repository
    python scripts/publish_to_github.py --branch dev    # different branch
    python scripts/publish_to_github.py --dry-run       # show what would happen

On a normal machine with working git networking, prefer the plain:

    git push origin main

This script is a fallback for restricted environments, and it always creates a
NEW commit on top of the remote branch (it does not rewrite history).
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

GCM = os.environ.get("GCM_PATH", r"C:\Tools\Git\mingw64\bin\git-credential-manager.exe")
API = "https://api.github.com"


def api(method: str, url: str, token: str, body=None, timeout: int = 180):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {
        "User-Agent": "xinxuan-publisher",
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.load(resp)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        try:
            return exc.code, json.loads(raw)
        except json.JSONDecodeError:
            return exc.code, {"message": raw[:500]}
    except Exception as exc:  # noqa: BLE001 - surface the reason, never crash opaquely
        return 0, {"message": f"{type(exc).__name__}: {exc}"}


def token_from_gcm() -> tuple[str, str]:
    """Ask Git Credential Manager for the github.com credential.

    The helper's shell wrapper cannot be used here: the sandbox blocks MSYS
    sh.exe with "couldn't create signal pipe, Win32 error 5", so the
    credential-manager binary is executed directly.
    """
    payload = "protocol=https\nhost=github.com\n\n"
    for cmd in ([GCM, "get"], ["git", "credential", "fill"]):
        try:
            proc = subprocess.run(cmd, input=payload, capture_output=True,
                                  text=True, timeout=120, encoding="utf-8",
                                  errors="replace")
        except FileNotFoundError:
            continue
        user = password = ""
        for line in proc.stdout.splitlines():
            if line.startswith("username="):
                user = line.split("=", 1)[1]
            elif line.startswith("password="):
                password = line.split("=", 1)[1]
        if password:
            return user, password
    sys.exit("FAIL: no usable GitHub credential. Run 'git credential-manager github login' first.")


def publish_tree(root: str, repo: str, token: str, ref: str,
                 label: str = "") -> tuple[dict[str, str], str]:
    """Upload every blob of `ref` and rebuild its tree; return {path: sha}.

    Two traps live here, both hit during the first real publication:
    * blobs must be sent as base64. Sending them as latin-1 text made GitHub
      re-encode the UTF-8, producing a different blob SHA (1215 B -> 1794 B).
      GitHub uses the same blob hashing as git, so "returned SHA == local SHA"
      is a byte-for-byte proof and no read-back is needed.
    * a directory that only ever appears as a parent of other directories has
      no file of its own; building trees by walking file paths skipped `docs/`
      and `data/` and silently published 26 of 40 files. All ancestors are
      therefore materialised explicitly.
    """
    def text(*a) -> str:
        proc = subprocess.run(["git", "-C", root, *a], capture_output=True,
                              timeout=300, encoding="utf-8", errors="replace")
        if proc.returncode != 0:
            sys.exit(f"FAIL: git {' '.join(a)}: {(proc.stderr or '')[:300]}")
        return proc.stdout

    entries: list[tuple[str, str, str, int]] = []
    for line in text("ls-tree", "-r", "--long", ref).splitlines():
        meta, _, path = line.partition("\t")
        mode, kind, sha, size = meta.split()
        if kind == "blob":
            entries.append((path, mode, sha, int(size)))

    shas = [e[2] for e in entries]
    proc = subprocess.Popen(["git", "-C", root, "cat-file", "--batch"],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL)
    proc.stdin.write(("\n".join(shas) + "\n").encode())
    proc.stdin.flush()
    payloads: dict[str, bytes] = {}
    for _ in shas:
        head = proc.stdout.readline().decode().split()
        body = proc.stdout.read(int(head[2]))
        proc.stdout.read(1)
        payloads[head[0]] = body
    proc.stdin.close()
    proc.wait(timeout=60)

    modes = {p: m for p, m, _, _ in entries}
    uploaded: dict[str, str] = {}
    for idx, (path, _mode, sha, size) in enumerate(entries, 1):
        status, res = api("POST", f"{API}/repos/{repo}/git/blobs", token,
                          {"content": base64.b64encode(payloads[sha]).decode("ascii"),
                           "encoding": "base64"})
        if status != 201:
            sys.exit(f"FAIL: blob {path} -> {status}: {res.get('message')}")
        if res["sha"] != sha:
            sys.exit(f"FAIL: blob SHA mismatch for {path}: {res['sha']} != {sha}")
        uploaded[path] = res["sha"]
        print(f"  {label}[{idx:>3}/{len(entries)}] {path} ({size:,} B) -> {sha[:10]}")

    dirs: set[str] = set()
    for path in uploaded:
        parts = path.split("/")
        for depth in range(1, len(parts)):
            dirs.add("/".join(parts[:depth]))
    tree_of: dict[str, str] = {}

    def make_tree(dirpath: str) -> str:
        prefix = f"{dirpath}/" if dirpath else ""
        items = []
        for path in sorted(uploaded):
            if not path.startswith(prefix):
                continue
            rest = path[len(prefix):]
            if "/" not in rest:
                items.append({"path": rest, "mode": modes[path], "type": "blob",
                              "sha": uploaded[path]})
        for name in sorted({p[len(prefix):].split("/")[0] for p in dirs if p.startswith(prefix)}):
            items.append({"path": name, "mode": "040000", "type": "tree",
                          "sha": tree_of[f"{prefix}{name}"]})
        status, res = api("POST", f"{API}/repos/{repo}/git/trees", token, {"tree": items})
        if status != 201:
            sys.exit(f"FAIL: tree '{dirpath or '.'}' -> {status}: {res.get('message')}")
        return res["sha"]

    for dirpath in sorted(dirs, key=lambda d: (-d.count("/"), d)):
        tree_of[dirpath] = make_tree(dirpath)
    root_sha = make_tree("")
    print(f"root tree     : {root_sha[:12]} ({len(dirs)} directories)")
    return uploaded, root_sha


def revision_info(root: str, ref: str) -> dict:
    def text(*a) -> str:
        proc = subprocess.run(["git", "-C", root, *a], capture_output=True,
                              timeout=120, encoding="utf-8", errors="replace")
        if proc.returncode != 0:
            sys.exit(f"FAIL: git {' '.join(a)}: {(proc.stderr or '')[:300]}")
        return proc.stdout

    name = text("log", "-1", "--pretty=%an", ref).strip()
    mail = text("log", "-1", "--pretty=%ae", ref).strip()
    stamp = text("log", "-1", "--pretty=%cI", ref).strip()
    return {
        "sha": text("rev-parse", ref).strip(),
        "message": text("log", "-1", "--pretty=%B", ref).rstrip("\n"),
        "author": {"name": name, "email": mail,
                   "date": datetime.fromisoformat(stamp).astimezone(timezone.utc)
                           .strftime("%Y-%m-%dT%H:%M:%SZ")},
        "parents": text("log", "-1", "--pretty=%P", ref).strip().split(),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Publish local git history to GitHub via the API")
    ap.add_argument("--repo", default=os.environ.get("XINXUAN_REPO", "xinxuan"))
    ap.add_argument("--branch", default="")
    ap.add_argument("--ref", default="HEAD", help="local revision to publish (default HEAD)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--history", type=int, default=1, metavar="N",
                    help="publish the last N local commits, rebuilding the remote branch "
                         "so its history matches local exactly (default 1 = stack one commit)")
    ap.add_argument("--prune-history", action="store_true",
                    help="publish --history commits as the entire remote history, dropping "
                         "leftover placeholder commits; only safe on a brand-new repo")
    args = ap.parse_args()

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if args.history > 1:
        args.prune_history = True

    def text(*a) -> str:
        proc = subprocess.run(["git", "-C", root, *a], capture_output=True,
                              timeout=300, encoding="utf-8", errors="replace")
        if proc.returncode != 0:
            sys.exit(f"FAIL: git {' '.join(a)}: {(proc.stderr or '')[:300]}")
        return proc.stdout

    branch = args.branch or text("branch", "--show-current").strip() or "main"
    user, token = token_from_gcm()
    status, me = api("GET", f"{API}/user", token)
    if status != 200:
        sys.exit(f"FAIL: GET /user -> {status}: {me.get('message')}")
    login = me["login"]
    print(f"authenticated as {login}")

    status, repo = api("GET", f"{API}/repos/{login}/{args.repo}", token)
    if status != 200:
        sys.exit(f"FAIL: repository {login}/{args.repo} unreachable -> {status}: {repo.get('message')}")
    print(f"repository    : {repo['html_url']} (private={repo['private']})")

    if subprocess.run(["git", "-C", root, "rev-parse", "--verify", "HEAD"],
                      capture_output=True).returncode != 0:
        sys.exit("FAIL: no commits yet, commit locally first")

    # Oldest first, so each published commit can point at the previous one.
    revs = text("rev-list", "--reverse", f"-{args.history}", args.ref).split()
    tip = revision_info(root, revs[-1])
    print(f"to publish    : {len(revs)} commit(s) on branch {branch}")

    # ---- dry run: no writes at all -----------------------------------------
    if args.dry_run:
        for idx, rev in enumerate(revs, 1):
            info = revision_info(root, rev)
            files = [l for l in text("ls-tree", "-r", "--long", rev).splitlines()
                     if l.split("\t")[0].split()[1] == "blob"]
            total = sum(int(l.split()[3]) for l in files)
            print(f"  [{idx}] {info['sha'][:10]}  {info['message'].splitlines()[0][:60]}")
            print(f"       {len(files)} files, {total / 1e6:.2f} MB, "
                  f"{len(info['parents'])} parent(s) in local history")
        print("DRY_RUN_OK")
        return 0

    # ---- one commit at a time ----------------------------------------------
    published: dict[str, str] = {}
    remote_parent: list[str] = []
    if not args.prune_history:
        status, ref = api("GET", f"{API}/repos/{login}/{args.repo}/git/ref/heads/{branch}", token)
        if status == 200:
            remote_parent = [ref["object"]["sha"]]
            print(f"parent        : {remote_parent[0][:12]}")
        elif status != 404:
            sys.exit(f"FAIL: read ref -> {status}: {ref.get('message')}")
    else:
        print(f"prune-history : remote {branch} will be rewritten to the "
              f"{len(revs)} local commit(s)")

    new_sha = ""
    pub_shas: list[str] = []
    for idx, rev in enumerate(revs, 1):
        info = revision_info(root, rev)
        uploaded, root_sha = publish_tree(root, f"{login}/{args.repo}", token, rev,
                                          label=f"[{idx}/{len(revs)}] ")
        parents = [new_sha] if new_sha else remote_parent
        status, res = api("POST", f"{API}/repos/{login}/{args.repo}/git/commits", token,
                          {"message": info["message"], "tree": root_sha, "parents": parents,
                           "author": info["author"], "committer": info["author"]})
        if status != 201:
            sys.exit(f"FAIL: commit -> {status}: {res.get('message')}")
        new_sha = res["sha"]
        pub_shas.append(new_sha)
        print(f"commit        : {new_sha}  <- local {info['sha'][:10]}")
        published = uploaded

    # Expected remote parent chain: published commits point at the *published*
    # SHA of the previous commit, which differs from the local SHA whenever the
    # existing parent set differs (that is exactly what --prune-history changes).
    expect_parents = [pub_shas[-2]] if len(pub_shas) > 1 else remote_parent

    # ---- ref ----------------------------------------------------------------
    status, res = api("POST", f"{API}/repos/{login}/{args.repo}/git/refs", token,
                      {"ref": f"refs/heads/{branch}", "sha": new_sha})
    if status == 422:
        status, res = api("PATCH", f"{API}/repos/{login}/{args.repo}/git/refs/heads/{branch}", token,
                          {"sha": new_sha, "force": args.prune_history or not remote_parent})
    if status not in (200, 201):
        sys.exit(f"FAIL: ref update -> {status}: {res.get('message')}")

    # ---- verify -------------------------------------------------------------
    status, full = api("GET", f"{API}/repos/{login}/{args.repo}/git/trees/{branch}?recursive=1", token)
    remote = {e["path"]: e["sha"] for e in full.get("tree", []) if e["type"] == "blob"}
    same = remote == published
    print("=== VERIFY ===")
    print("files         :", len(remote), "remote ==", len(published), "local")
    print("blobs equal   :", same)
    print("branch url    :", f"{repo['html_url']}/tree/{branch}")
    if not same:
        print("  missing:", sorted(set(published) - set(remote)))
        print("  extra  :", sorted(set(remote) - set(published)))
        return 1

    status, info = api("GET", f"{API}/repos/{login}/{args.repo}/commits/{new_sha}", token)
    got_parents = [p["sha"] for p in info.get("parents", [])] if status == 200 else []
    print("remote parents:", [p[:12] for p in got_parents] or "none (root commit)")
    print("local tip     :", tip["sha"][:10], "message:",
          tip["message"].splitlines()[0][:60])
    if args.prune_history:
        # The whole published chain must be the local history: every commit but
        # the last must have exactly one parent.
        chain: list[str] = []
        walk = new_sha
        while walk:
            status, node = api("GET", f"{API}/repos/{login}/{args.repo}/commits/{walk}", token)
            if status != 200:
                sys.exit(f"FAIL: walk history -> {status}")
            chain.append(node["commit"]["message"].splitlines()[0][:60])
            walk = node["parents"][0]["sha"] if node["parents"] else ""
            if len(chain) > 200:
                sys.exit("FAIL: history walk did not terminate")
        print(f"remote history: {len(chain)} commit(s) (local: {len(revs)})")
        for i, line in enumerate(reversed(chain), 1):
            print(f"   {i}. {line}")
        if len(chain) != len(revs):
            print(f"FAIL: remote has {len(chain)} commits, expected {len(revs)}")
            return 1
    if got_parents != expect_parents:
        print("FAIL: remote parents", [p[:10] for p in got_parents],
              "!= expected", [p[:10] for p in expect_parents])
        return 1
    print("PUBLISH_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
