# Adding a task

Implement the `Task` interface from `parabox/tasks/base.py` in a module under
`parabox/tasks/<name>/`.

| Member | Responsibility |
| --- | --- |
| `name`, `image`, `turns` | Task identifier, container image and turn limit |
| `workspace(problem)` | Initial files placed in `/workspace` |
| `system(integrity=, shared=)`, `task(shared=)`, `tools(shared=)` | Participant-visible instructions and tools; with `shared=False`, do not mention the library or later participants |
| `prompts_record(...)` | Instructions and hashes used to freeze the protocol |
| `call(box, name, args, state)` | Execute one tool call; record submissions, feedback and completion in `state` |
| `contribution(state)` | Accepted artifacts eligible for sharing |
| `audit(raw, problem, scratch)` | Independent judgment including `violation`; never shown to the participant |
| `audit_session(session_dir, spec, scratch)` | Optional session-level audit; otherwise the study audits the last accepted artifact |

`run_session(..., extra_files=)` writes additional files after the task files.
The caller configures mounts through `Box.mounts`. Keep assignment and
cross-session transmission in the study layer, separate from task verification.

Provide fixtures for a genuinely correct acceptance, an accepted-but-invalid
exploit, and a rejected submission. A container selftest should exercise all
three and check the independent audit, without calling a model provider.
