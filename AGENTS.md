# RoonDeck working expectations

## Publishing completed changes

The user expects requested RoonDeck changes to be delivered through the updater, not left as local edits.

- After implementing and proportionately verifying requested changes, commit the relevant changes, push to `origin/main`, and publish a GitHub release with the next appropriate semantic version and concise release notes.
- Update the application version, changelog, documented current release, and affected web asset cache versions as appropriate.
- Do not ask for publishing confirmation on every build. The user has explicitly authorised this routine workflow, including direct pushes to `main` and GitHub releases.
- Do not overwrite unrelated user changes, force-push, or publish known failing work. Report meaningful blockers or operations needing authority beyond this workflow.
- Confirm the release was published before claiming it is available through the updater. Publishing a release does not authorise remotely installing it or restarting the user's Pi.
- State verification accurately: local browser fixtures and automated tests do not prove native GTK behaviour on the actual touchscreen.

## Conserve GitHub Actions usage

GitHub-hosted runtime is limited. Do not use repeated pushes or GitHub Actions runs as the development loop for layout work.

- Run unit tests, native rendering, screenshot capture, and the complete supported screen-size matrix locally while developing.
- Keep intermediate fixes local. Consolidate related changes and push only after the local checks pass.
- Do not make a sequence of speculative CI-only commits to adjust screenshot geometry or workflow assertions. Reproduce and resolve those failures locally first.
- For an ordinary release, trigger GitHub Actions only once for the final release candidate. A second run is acceptable only when the first uncovers a failure that could not reasonably be reproduced locally.
- Do not rerun successful jobs, duplicate equivalent workflows, or run the full matrix merely to obtain screenshots that can be generated locally.
- Prefer one consolidated required workflow over multiple workflows that repeat setup, builds, or the same test suites.
- Before pushing, inspect workflow triggers and batch commits so a single release candidate does not cause avoidable runs.
- If a proposed change would materially increase GitHub Actions minutes, explain why and get the user's approval first.
