# Security and evidence handling

Participant code is untrusted. Run it only through the configured offline
container boundary. Do not execute participant submissions on the host.
The local fixture runner is only for repository-authored fixtures.

Model API credentials are read on the host from environment variables or
an ignored `.env`. Do not mount home directories, credentials or a container
socket into participant workspaces. Rootless Podman is recommended. Network
is disabled for participant and audit containers; host-side provider calls
still require network access.

Containers are not a guarantee against every escape. Use a dedicated host or
VM for adversarial evaluation, retain resource limits, and keep the runtime
updated. Verifier loopholes are intentional research fixtures; distinguish
them from an unintended host or credential exposure.

## Host-side artifact access

The release code uses descriptor-relative, no-follow operations for
Python/Lean tool access and submission reads, Python hidden-test writes and
cleanup, population/chain snapshots, and unified outcome artifact inspection.
Symlinks and special files are not inherited as shared files. Artifact reads
are limited to 4 MiB per file; snapshots to 16 MiB, 4,096 entries and depth 32.
Oversized trees fail explicitly rather than being silently truncated. These
are release safeguards, not the instrument that produced peer composition's results.

Tests exercise real task entry points, external file/directory symlinks,
path replacement after validation, FIFOs, snapshot limits and cache cleanup.
They are regression evidence, not an exhaustive security audit. Historical
study-specific orchestration/scorers have not received the same boundary
review. Run historical reproduction or analysis of untrusted artifacts only
in a disposable VM without credentials or unrelated host files. The preserved
historical source is research evidence, not a hardened execution service.

Before publishing, inspect tracked files and Git history for credentials,
private endpoints, personal information and imported content. A pattern scan
is a triage aid, not proof that a repository is safe to publish. Never print
suspected secret values in a report; report paths and findings instead.

No public private-disclosure address is configured yet. Before publication,
the maintainer should enable private vulnerability reporting on the hosting
platform and document that route. Do not publish exploit transcripts or
credentials in a public issue. Remote publication is a separate release step.
