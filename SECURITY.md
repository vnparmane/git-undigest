# Security Policy

## Supported Versions

Only the latest release on the `main` branch receives security updates.

| Version | Supported |
|---------|-----------|
| 0.2.x   | Yes       |
| < 0.2   | No        |

## Reporting a Vulnerability

If you discover a security vulnerability in git-undigest, please report it
privately by emailing **16848858+anomalyco@users.noreply.github.com**.

**Do not open a public GitHub issue for security vulnerabilities.**

We will acknowledge receipt within 48 hours and aim to provide an initial
assessment within 5 business days. We will keep you informed of the progress
toward a fix and release.

## Expected Response Times

| Stage | Expected Time |
|-------|---------------|
| Acknowledgment | 48 hours |
| Initial assessment | 5 business days |
| Fix development | Determined by severity |
| Release | Coordinated with reporter |

## Scope

Security-sensitive code is primarily in:

- `src/git_undigest/validator.py` — path traversal detection
- `src/git_undigest/writer.py` — atomic writes, backup logic
- `src/git_undigest/parser.py` — file I/O and decompression

The package aims to be a safe consumer of untrusted digest files. We
encourage security researchers to test these modules specifically.
