#!/usr/bin/env python3
"""
Rebuild the calendar and publish it if it changed.

    python publish.py            # build, commit if the output changed, push if a remote exists
    python publish.py --no-push  # build and commit only

Called by ../_fpr.py after every calendar write (cal-upsert, cal-push, detect) and after a
leg is marked done, so the public page follows _calendar.json without a manual step.

A failed validation writes nothing and publishes nothing: the last good page stays up.
Every run appends one line to ../_logs/earnings-calendar-publish.log.
"""
import datetime, os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(os.path.dirname(HERE), "_logs", "earnings-calendar-publish.log")
FILES = ["index.html", "data.json", "calendar.ics", "earnings-calendar.csv"]
ENV = dict(os.environ, GIT_TERMINAL_PROMPT="0", PYTHONIOENCODING="utf-8")


def run(*cmd, timeout=90):
    return subprocess.run(cmd, cwd=HERE, env=ENV, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout)


def log(msg):
    line = f"{datetime.datetime.now().astimezone().isoformat(timespec='seconds')}  {msg}"
    print(line)
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def main():
    b = run(sys.executable, "build.py")
    summary = (b.stdout.strip().splitlines() or [""])
    if b.returncode != 0:
        log("BUILD FAILED, nothing published: " + " | ".join(summary[:6]) + b.stderr.strip()[-300:])
        return 1
    for w in [s for s in summary if s.startswith("WARN")]:
        log(w)

    if not os.path.isdir(os.path.join(HERE, ".git")):
        log("built; no git repository here, nothing published")
        return 0
    run("git", "add", "--", *FILES)
    if run("git", "diff", "--cached", "--quiet").returncode == 0:
        log("built; no change")
        return 0
    c = run("git", "commit", "-m", f"Calendar update {datetime.date.today().isoformat()}")
    if c.returncode != 0:
        log("COMMIT FAILED: " + (c.stderr or c.stdout).strip()[-300:])
        return 1
    if "--no-push" in sys.argv or not run("git", "remote").stdout.strip():
        log("committed; not pushed (no remote or --no-push)")
        return 0
    p = run("git", "push", "origin", "HEAD", timeout=120)
    if p.returncode != 0:
        log("PUSH FAILED (commit kept, next run pushes it): " + p.stderr.strip()[-300:])
        return 1
    log("published: " + next((s for s in summary if s.startswith("OK")), "ok"))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as ex:  # never let a publish problem reach the caller as a traceback
        log(f"PUBLISH ERROR: {ex.__class__.__name__}: {ex}")
        sys.exit(1)
