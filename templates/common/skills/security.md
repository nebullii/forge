# Security Skills

## OWASP Top 5 — Check Every Time
Run all five checks on every audit:
1. **Injection** — SQL, command, path traversal. Look for f-strings in SQL or os.system() calls.
2. **Broken Authentication** — hardcoded credentials, weak session tokens, missing auth on sensitive routes.
3. **Sensitive Data Exposure** — secrets in source code, error messages leaking stack traces, unencrypted sensitive fields.
4. **Security Misconfiguration** — CORS set to `*` in production, debug mode on, directory listing enabled.
5. **XSS** — unsanitized user input rendered as HTML via dangerouslySetInnerHTML or direct DOM writes.

## Severity Guide
- **critical**: exploit leads to RCE, data exfiltration, or auth bypass → rewrite the affected file completely
- **high**: significant risk but requires specific conditions → rewrite the affected file completely
- **medium**: real issue but limited blast radius → describe the fix as a recommendation, no code rewrite
- **low/info**: best practices, not active vulnerabilities → skip entirely, do not report

## Auto-Fix Rules
For critical and high severity findings:
- Output the complete corrected file — not a diff, not a snippet, the whole file
- Prefer the minimal fix that removes the vulnerability without changing behavior

## What NOT to Flag
- Missing HTTPS termination (handled at the proxy/platform layer)
- Lack of rate limiting on non-authentication endpoints
- Absence of CAPTCHA
- Missing audit logs for non-sensitive operations
- Any issue that would only affect a local development environment
