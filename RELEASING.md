# Repository and PyPI setup

This checkout is prepared locally. GitHub provisioning, pushing, PyPI registration, and
release publication are separate actions.

1. Set up a public repository with release-tag creation allowed and protection against
   tag updates, deletion, and force-pushes. Keep required CI disabled until its checks
   are verified.

2. Review and commit this bootstrap branch, then push and integrate it into `main`. Run
   CI, observe the exact check context and GitHub App integration ID, and enable
   required CI in a follow-up infrastructure change. Do not guess the ID.
3. Create the GitHub environment `pypi` with appropriate release approval rules.
4. In PyPI's Publishing settings, add a pending GitHub trusted publisher:

   | Field             | Value                   |
   | ----------------- | ----------------------- |
   | PyPI project      | `pytest-sentry-capture` |
   | GitHub owner      | `adamcik`               |
   | Repository        | `pytest-sentry-capture` |
   | Workflow filename | `release.yml`           |
   | Environment       | `pypi`                  |

   Name availability is not a reservation. The first successful trusted upload creates
   the project. No API-token secret is needed.
5. Run `nix fmt -- --ci`, `nix flake check`, and `nix build`. Inspect wheel and sdist
   metadata and try the README example against the installed wheel.
6. Choose a version, create its `vVERSION` tag, and publish an approved GitHub release
   for that tag. `release.yml` checks the project, builds and inspects distributions,
   verifies their versions, and publishes through OIDC. The PyPI job does not rebuild
   artifacts and is the only job with `id-token: write`.

Versions come from Git tags via hatch-vcs. Git-free source snapshots use `0.0.0` for
local/Nix builds; untagged Git checkouts produce development versions. The release
workflow refuses both. PyPI releases are immutable; inspect the artifacts before
approving.

The bootstrap does not enable automerge or register a trusted publisher for you.
