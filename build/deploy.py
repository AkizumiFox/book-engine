"""
Build System Deploy Module
==========================
Deploys built output to a directory for GitHub Pages. The deploy-dir (e.g. site/)
is a git clone of the public repo; it contains only built HTML, PDFs, and book.
"""

import re
import shutil
import subprocess

from .book import Book
from .utils import print_step, print_success, print_error


def _git(deploy_dir, *args) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=str(deploy_dir), capture_output=True, text=True)


REDIRECT_PAGE = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>Moved</title>
<link rel="canonical" href="{target}">
<script>location.replace("{target}" + location.hash);</script>
<meta http-equiv="refresh" content="0; url={target}">
</head><body><p>This page has moved to <a href="{target}">{target}</a>.</p></body></html>
"""


def write_redirects(book: Book, deploy_dir) -> int:
    """Stub pages for moved paths: config "redirects" maps an old path to a new one
    (both relative to the site root). An old path ending in "/" redirects every page
    under it to the same file name under the new directory."""
    count = 0
    for old, new in book.config.get("redirects", {}).items():
        if old.endswith("/"):
            targets = {name: new.rstrip("/") + "/" + name
                       for name in [p.name for p in (book.html_dir / new.rstrip("/")).glob("*.html")]}
            # old file names that no longer exist fall back to the new chapter index
            for name in book.config.get("redirect-files", {}).get(old, []):
                targets.setdefault(name, new.rstrip("/") + "/index.html")
            items = [(old + name, target) for name, target in targets.items()]
        else:
            items = [(old, new)]
        for old_path, target in items:
            stub = deploy_dir / old_path
            if stub.exists():
                continue  # a real page lives here
            depth = old_path.count("/")
            stub.parent.mkdir(parents=True, exist_ok=True)
            stub.write_text(REDIRECT_PAGE.format(target="../" * depth + target), encoding="utf-8")
            count += 1
    if count:
        print_success(f"Redirect stubs: {count}")
    return count


def is_stale_chapter_dir(name: str, chapter_slugs) -> bool:
    """A chapter directory left in the HTML output by an earlier build, under a slug the
    book no longer uses. Such a directory must not be published: its pages are stale, and
    publishing one at an old URL also stops `write_redirects` writing the redirect that
    should stand there, because it finds a real page and steps aside.

    `[a-z]*` is load-bearing. A chapter directory may carry a letter after its number
    (`ch24a-notation`), and without it `ch23a-notation` fails to match, is taken for a live
    chapter and is republished. That is a real bug this function was extracted to fix.
    """
    return bool(re.match(r"ch\d+[a-z]*-", name)) and name not in chapter_slugs


def deploy(book: Book, run_build: bool = True, push: bool = False) -> bool:
    """
    Build and check the book (if run_build), then replace the contents of deploy-dir with
    the HTML output, keeping .git. If push=True, commit and push from deploy-dir.
    Returns True on success.
    """
    from .cli import build_all
    from .check import check

    deploy_dir = book.path(book.config.get("deploy-dir", "site"))
    deploy_repo = book.config.get("deploy-repo", "")

    if run_build:
        if not build_all(book):
            print_error("Build failed; not deploying.")
            return False
        if not check(book):
            print_error("Check failed; not deploying.")
            return False

    html_dir = book.html_dir
    if not html_dir.exists():
        print_error(f"HTML output not found: {html_dir}")
        print_error("Run './build.py all' first.")
        return False

    if not deploy_dir.exists():
        if deploy_repo:
            print_step(f"Cloning {deploy_repo} into {deploy_dir}...")
            result = subprocess.run(["git", "clone", deploy_repo, str(deploy_dir)], capture_output=True, text=True)
            if result.returncode != 0:
                print_error(f"git clone failed: {result.stderr}")
                return False
        else:
            deploy_dir.mkdir(parents=True)

    print_step(f"Deploying to {deploy_dir}...")
    git_dir = deploy_dir / ".git"
    for item in deploy_dir.iterdir():
        if item.name == ".git":
            continue
        if item.is_dir():
            shutil.rmtree(item)
        else:
            item.unlink()

    chapter_slugs = {c.slug for c in book.chapters}
    for item in html_dir.iterdir():
        if item.is_dir() and is_stale_chapter_dir(item.name, chapter_slugs):
            continue  # output of a chapter that was renamed or removed (stale build files)
        if item.name.startswith("_"):
            continue  # a scratch harness built by hand for measuring or testing, never published
        if item.is_dir():
            shutil.copytree(item, deploy_dir / item.name)
        else:
            shutil.copy2(item, deploy_dir / item.name)

    write_redirects(book, deploy_dir)

    deploy_domain = book.config.get("deploy-domain", "")
    if deploy_domain:
        (deploy_dir / "CNAME").write_text(deploy_domain.strip(), encoding="utf-8")
    print_success(f"Deployed to {deploy_dir}")

    if not git_dir.exists():
        return True
    if not push:
        print_step(f"Next: cd {deploy_dir.name} && git add -A && git commit -m 'Deploy' && git push")
        return True

    print_step("Pushing to remote...")
    result = _git(deploy_dir, "add", "-A")
    if result.returncode != 0:
        print_error(f"git add failed: {result.stderr}")
        return False
    result = _git(deploy_dir, "commit", "-m", "Deploy")
    if result.returncode != 0:
        if "nothing to commit" not in result.stdout + result.stderr:
            print_error(f"git commit failed: {result.stderr}")
            return False
        print_success("No changes to commit.")
    push_url = book.config.get("deploy-push-url")
    result = _git(deploy_dir, "push", *([push_url, "HEAD"] if push_url else []))
    if result.returncode != 0:
        print_error(f"git push failed: {result.stderr}")
        return False
    print_success("Pushed to remote.")
    return True
