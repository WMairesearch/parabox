# Security and evidence handling

Treat participant programs and inherited artifacts as untrusted input. Execute submissions only inside the configured offline containers, never on the host. Host-local fixture helpers are for repository-authored test programs.

## Execution boundary

Use Linux with rootless Podman on a dedicated host or disposable VM for adversarial work. On macOS, that Linux environment may be a Docker container, which Docker runs inside a Linux VM; Podman inside it still runs every participant container (see `parabox/studies/scripts/docker_batch.py`). Do not mount the host home directory, credentials or the Docker socket into that outer container. Nested rootless Podman may not enforce participant memory limits; record the limits actually in force with the run. Keep container resource limits enabled and the runtime updated. Do not mount home directories, credentials or container-management sockets into workspaces. Containers reduce exposure but do not guarantee protection against every escape.

Provider credentials stay on the host in environment variables or an ignored `.env`. Participant and audit containers have no network; provider requests and dependency installation are separate host operations. Deliberately weak task verifiers are research fixtures, not permission to expose the host.

## Grading and shared records

The synthetic wiki service supplies fixed JSON examples through a Unix socket; requests do not resolve into host filesystem paths. Its read-only service mount contains no container-management socket or credentials. Service requests and tool operations consume the task budget.

Submission seals the service and stops the participant before final export. Independent wiki grading runs each case in a fresh container with read-only candidate code and the current input. Expected answers remain on the host. The ternary task likewise keeps its target on the host. Its shared submission receipts are read-only inside participant containers.

## Artifact safeguards

Release helpers use descriptor-relative, no-follow access for task tools, submission reads, hidden-test writes and cleanup, snapshots and supported outcome inspection. Shared-file inheritance excludes symlinks and special files. Limits are 4 MiB per file, 16 MiB per snapshot, 4,096 entries and depth 32; oversized snapshots fail rather than silently dropping data.

Regression tests cover symlinks, path replacement, FIFOs, limits and cleanup. The task's independent execution audit evaluates participant submissions; it is not an external assessment of framework security. Parabox claims no third-party security audit. Older study-specific orchestration and scorers have a narrower review history; reproduce them in an isolated environment without unrelated files or credentials. Current safeguards do not retroactively describe historical execution.

## Publication and disclosure

Before release, inspect files, history and built packages for secrets, private endpoints, personal information and imported content:

```sh
python -m scripts.release_check --history
python -m scripts.release_check --archive dist/PACKAGE.whl
```

A source `.tar.gz` is also accepted. The scanner checks package contents and the explicit document allowlist; a clean scan is not a complete privacy or rights review. Report affected paths without reproducing secret values.

No private vulnerability-reporting address is currently listed. The maintainer must establish a private disclosure route before remote publication. Do not post credentials or sensitive exploit transcripts in a public issue.
