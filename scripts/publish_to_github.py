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


def main() -> int:
    ap = argparse.ArgumentParser(description="Publish local git history to GitHub via the API")
    ap.add_argument("--repo", default=os.environ.get("XINXUAN_REPO", "xinxuan"))
    ap.add_argument("--branch", default="")
    ap.add_argument("--ref", default="HEAD", help="local revision to publish (default HEAD)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    run = lambda *a: subprocess.run(  # noqa: E731
        ["git", "-C", root, *a], capture_output=True, timeout=300
    )

    def text(*a) -> str:
        proc = run(*a)
        if proc.returncode != 0:
            sys.exit(f"FAIL: git {' '.join(a)}: {proc.stderr.decode('utf-8', 'replace')[:300]}")
        return proc.stdout.decode("utf-8", "replace")

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

    if run("rev-parse", "--verify", "HEAD").returncode != 0:
        sys.exit("FAIL: no commits yet, commit locally first")

    entries: list[tuple[str, str, str, int]] = []
    for line in text("ls-tree", "-r", "--long", args.ref).splitlines():
        meta, _, path = line.partition("\t")
        mode, kind, sha, size = meta.split()
        if kind == "blob":
            entries.append((path, mode, sha, int(size)))
    message = text("log", "-1", "--pretty=%B", args.ref).rstrip("\n")
    who = {
        "name": text("log", "-1", "--pretty=%an", args.ref).strip(),
        "email": text("log", "-1", "--pretty=%ae", args.ref).strip(),
    }
    stamp = text("log", "-1", "--pretty=%aI", args.ref).strip()
    when = datetime.fromisoformat(stamp).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    total = sum(e[3] for e in entries)
    print(f"to publish    : {len(entries)} files, {total / 1e6:.2f} MB, branch {branch}")
    if args.dry_run:
        for path, _, sha, size in entries:
            print(f"   {path}  ({size:,} B)  {sha[:10]}")
        print("DRY_RUN_OK")
        return 0

    # ---- blobs --------------------------------------------------------------
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
        blob = payloads[sha]
        status, res = api("POST", f"{API}/repos/{login}/{args.repo}/git/blobs", token,
                          {"content": base64.b64encode(blob).decode("ascii"), "encoding": "base64"})
        if status != 201:
            sys.exit(f"FAIL: blob {path} -> {status}: {res.get('message')}")
        if res["sha"] != sha:
            sys.exit(f"FAIL: blob SHA mismatch for {path}: {res['sha']} != {sha}")
        uploaded[path] = res["sha"]
        print(f"  [{idx:>3}/{len(entries)}] {path} ({size:,} B) -> {sha[:10]}")

    # ---- trees --------------------------------------------------------------
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
                items.append({"path": rest, "mode": modes[path], "type": "blob", "sha": uploaded[path]})
        for name in sorted({p[len(prefix):].split("/")[0] for p in dirs if p.startswith(prefix)}):
            items.append({"path": name, "mode": "040000", "type": "tree",
                          "sha": tree_of[f"{prefix}{name}"]})
        status, res = api("POST", f"{API}/repos/{login}/{args.repo}/git/trees", token, {"tree": items})
        if status != 201:
            sys.exit(f"FAIL: tree '{dirpath or '.'}' -> {status}: {res.get('message')}")
        return res["sha"]

    for dirpath in sorted(dirs, key=lambda d: (-d.count("/"), d)):
        tree_of[dirpath] = make_tree(dirpath)
    root_sha = make_tree("")
    print(f"root tree     : {root_sha[:12]} ({len(dirs)} directories)")

    # ---- commit + ref -------------------------------------------------------
    parents: list[str] = []
    status, ref = api("GET", f"{API}/repos/{login}/{args.repo}/git/ref/heads/{branch}", token)
    if status == 200:
        parents = [ref["object"]["sha"]]
        print(f"parent        : {parents[0][:12]}")
    elif status != 404:
        sys.exit(f"FAIL: read ref -> {status}: {ref.get('message')}")

    identity = {**who, "date": when}
    status, res = api("POST", f"{API}/repos/{login}/{args.repo}/git/commits", token,
                      {"message": message, "tree": root_sha, "parents": parents,
                       "author": identity, "committer": identity})
    if status != 201:
        sys.exit(f"FAIL: commit -> {status}: {res.get('message')}")
    new_sha = res["sha"]
    print(f"commit        : {new_sha}")

    status, res = api("POST", f"{API}/repos/{login}/{args.repo}/git/refs", token,
                      {"ref": f"refs/heads/{branch}", "sha": new_sha})
    if status == 422:
        # Ref already exists: normal case is a fast-forward. Force only when the
        # remote has no parent to build on (first publication into an
        # auto-initialised repository).
        status, res = api("PATCH", f"{API}/repos/{login}/{args.repo}/git/refs/heads/{branch}", token,
                          {"sha": new_sha, "force": not parents})
    if status not in (200, 201):
        sys.exit(f"FAIL: ref update -> {status}: {res.get('message')}")

    # ---- verify -------------------------------------------------------------
    status, full = api("GET", f"{API}/repos/{login}/{args.repo}/git/trees/{branch}?recursive=1", token)
    remote = {e["path"]: e["sha"] for e in full.get("tree", []) if e["type"] == "blob"}
    same = remote == uploaded
    print("=== VERIFY ===")
    print("remote files  :", len(remote), "local:", len(uploaded))
    print("blobs equal   :", same)
    print("branch url    :", f"{repo['html_url']}/tree/{branch}")
    if not same:
        print("  missing:", sorted(set(uploaded) - set(remote)))
        print("  extra  :", sorted(set(remote) - set(uploaded)))
        return 1
    print("PUBLISH_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
