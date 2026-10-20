# Maintaining BlackHole Arena

Notes for repository maintainers. Contributors should read
[CONTRIBUTING.md](../CONTRIBUTING.md) instead.

## Branch protection on `main`

Configure under **Settings → Branches → Add rule** for `main`:

- ✅ **Require a pull request before merging** (require at least 1 approval).
- ✅ **Require status checks to pass before merging** — select the **Tests**
  workflow (both Python versions) and **Docs**.
- ✅ **Require branches to be up to date before merging.**
- ✅ **Do not allow bypassing the above settings** (optional but recommended).

> **Never add a `paths:` filter to the `pull_request` trigger of a workflow you
> mark as a required check.** GitHub reports a required check that did not run as
> permanently "Expected", which blocks the merge with no way to clear it. A
> new-player PR touches only `players/custom/`, so a `docs/**` filter
> on `Docs` would make every student submission unmergeable. Both `Tests` and
> `Docs` therefore run unconditionally on pull requests.

This makes the PR review the real gate: nothing lands on `main` without passing
CI and a human review.

## GitHub Pages

**Settings → Pages → Build and deployment → Source: GitHub Actions.** The
[`pages.yml`](workflows/pages.yml) workflow assembles and deploys the site.

> **It must be "GitHub Actions", not "Deploy from a branch".** Branch-based
> serving can only publish files committed to the repo, and the browser bundle
> `web/py.zip` is *generated* by [`build_web.py`](../scripts/build_web.py) and is
> git-ignored. Point Pages at a branch and you get the README rendered by Jekyll
> at the root and a permanent 404 on `py.zip`, so the app never boots. If
> `deploy-pages` fails with "Get Pages site failed", this setting is why.

## Read the Docs

The docs are published by Read the Docs, configured by
[`.readthedocs.yaml`](../.readthedocs.yaml). RTD only builds a repository that has
been **imported once, by hand** — there is no way to do this from the repo:

1. Sign in at [readthedocs.org](https://readthedocs.org) and **Import a Project**.
2. Pick `jparisu/blackhole-arena`. Accept the webhook it offers.
3. Note the **slug** it assigns (currently `blackhole-arena`) — it becomes the hostname
   `https://<slug>.readthedocs.io`. If the slug is not `blackhole-arena`, update
   `site_url` in [`mkdocs.yml`](../mkdocs.yml), the `Documentation` URL in
   [`pyproject.toml`](../pyproject.toml), the README badge, and the links in
   `.github/ISSUE_TEMPLATE/config.yml`.

Note that [`docs.yml`](workflows/docs.yml) only *builds* the site as a fast CI
check (`mkdocs build --strict`) and discards the output. RTD is the sole publisher,
so if RTD is not imported, there are **no published docs at all** even with a green
`Docs` workflow.

## Never write a CI-skip token in a commit message

GitHub scans the **whole** commit message — subject *and* body — for
`[skip ci]`, `[ci skip]`, `[no ci]`, `[skip actions]` and `[actions skip]`, and
suppresses **every** workflow on that push. It does not care that the token
appears inside a quotation.

This has already bitten this repo once: the commit that *removed* the skip token
from [`tournament.yml`](workflows/tournament.yml) quoted the token in its own
message while explaining the change, so that push ran no CI at all.

When writing about it — in a commit message, a PR description or a release note —
describe it ("the skip-CI token", "a CI-skip marker") instead of pasting it. The
token inside a workflow *file* is harmless; only the commit message matters.

## Keeping the scheduled tournament alive

GitHub **disables `schedule:` triggers after 60 days of repository inactivity**
and emails the owner. Over a long vacation the weekly tournament will silently
stop; re-enable it from the Actions tab (or push any commit) when the course
resumes.

## Reviewing a new-player PR

Every submission runs untrusted-but-reviewed code. Your review is the security
and correctness gate. Check the acceptance criteria from
[submit-a-player](https://blackhole-arena.readthedocs.io/en/latest/game/upload-a-bot/submit-a-player/):

1. **Design** — one file in `players/custom/`, one line in
   `players/custom/players.yaml`, subclasses `Player`, unique `name`. A
   submission must not touch `players/builtin/`.
2. **Correctness** — CI green; legal moves; no mutation of `state`; no
   errors/timeouts against the reference bots. The **Custom players** workflow is
   the one that judges the submission: it discovers every bot in
   `players/custom/players.yaml` and checks identity, legal moves and full games
   against `random`. The **Tests** workflow deliberately skips submitted bots, so
   a broken one fails only its own check — never an unrelated pull request.
3. **No malware** — read the code in full. Reject on sight: network, filesystem,
   subprocess, `eval`/`exec`, `os`/`sys` manipulation, obfuscation, or attempts
   to read secrets or escape the sandbox.

A player that errors or times out is **not merged**, even if the tournament would
survive it.

> **Note.** PRs from forks run with a **read-only token and no secrets**, so a
> submitted bot cannot damage the repo during CI — but it *does execute*, which is
> exactly why the tournament's timeouts and forfeit handling are mandatory.
