# AutoCAD File Safety v0.1: local file handling boundary

## Scope and evidence

The previous `app.py` upload endpoint joined the caller-controlled `session_id` and original filename into local paths without validating either; the agent result-upload endpoint also wrote to a caller-selected session/file path without checking the upload registry. The `api/upload`, `api/session`, `api/results` and agent-result responses could expose absolute server paths.

This change protects the **upload-session storage path**, not every possible local filesystem operation. It is NOT a full security review or public multi-tenant service hardening.

## Contract

- Normal upload remains `POST /api/upload` multipart field `files`, optional `session_id`, optional `client_id`; successful responses still expose `success`, `session_id`, `files`, `count`. The `files` entries now expose only `name` and `size`, not server-side `path`.
- Session ID, when supplied, must be 1–64 ASCII letters/digits, underscores or hyphens. Empty/omitted ID gets a fresh random server-generated ID. A reused or stale session directory returns HTTP 409 instead of overwriting files.
- Filenames must be one portable `.dwg` basename of at most 170 characters. Reject directory components (including Windows backslashes), control characters, Windows device names, trailing dots/spaces, invalid extensions and duplicate case-insensitive names in one upload. Extension is **not** DWG content/malware validation.
- Total upload request limit is 64 MiB (Flask `MAX_CONTENT_LENGTH`), with JSON HTTP 413 on excess. Large legitimate DWGs require a reviewed limit change; this is a total-request limit, not a per-file parser.
- Files are created exclusively in a *new* upload session. If any write fails, only this attempt's files are removed; nothing outside the session is touched.
- `GET /api/session/<id>` and `GET /api/results/<id>` no longer disclose server paths. Download endpoints require a recorded session and owned filename, and verify the resolved path remains under upload root.
- Agent result upload keeps the previous endpoint and input formats (multipart or raw body), but only for an uploaded DWG in a known session. Valid agent retries replace their own named output atomically.
- The `api/start` legacy direct-path mode remains available **only when no `session_id` was supplied**; an unknown session is now rejected rather than falling back to caller-supplied paths.
- Queued agents for upload sessions receive names and IDs rather than local paths. In-progress task JSON omits the internal `dwg_path`.

## Verification (no AutoCAD)

```sh
python -m pip install "flask>=3.0,<5" "httpx>=0.28,<1" "Pillow>=10,<13" "requests>=2.32,<3"
python -m compileall -q app.py file_safety.py tests
python -m unittest discover -s tests -p "test_file_safety.py" -v
```

The [file safety workflow](../.github/workflows/file-safety.yml) runs these on Linux and Windows. The tests use Flask's in-process test client, temporary directories and fake bytes, never open real DWGs or invoke AutoCAD, public endpoints, AI services or a hardware agent. Check the workflow run against this PR's exact **head SHA** before claiming success.

## Remaining risks and non-goals

- **Local-only service.** `app.run` still binds `127.0.0.1`. The application has no authentication or access controls for agent registration and the legacy local-folder scan/start API. **Do not expose it to the Internet or untrusted LANs.** Authentication, client isolation, sharing, and deployment require a separate proposal and approval.
- `/api/scan` and legacy `files_data` workflows intentionally accept user-selected **local paths**. Those are not sandboxed under upload root and should be used only by a trusted local operator.
- No DWG binary signature/geometry validation, antivirus scan, content inspection, CAD accuracy test, deletion of old data, symlink race guarantee under concurrent local attackers, or upload rate limiting.
- Upload metadata and agent registration remain in-memory. A service restart invalidates session references but leaves ignored local files on disk. Do not run automatic cleanup on unknown files.
- Files larger than the default 64 MiB request limit will now be rejected. Duplicate uploads into an existing session return HTTP 409; the UI currently makes a fresh session for each upload. These are intentional validation changes.
- Real Windows COM interaction, actual DWG content and geometry accuracy still require later manual approval and verification.

## Reversal and review

All changes live in a separate Git branch and Draft PR. No changes are made directly to `main`; no merging or auto-merge. To abandon the change, close the PR and retain the branch for inspection. If a merge is subsequently approved, revert that merge commit rather than rewriting main history.
