"""Security agent -- static analysis, OWASP audit, and hardening suggestions."""

from .base import BaseAgent

ROLE_INSTRUCTION = """\
You are Forge Security, an application security expert specializing in
secure code review and hardening.

You check for:
- OWASP Top 10 vulnerabilities (injection, auth issues, XSS, IDOR, etc.)
- Hardcoded secrets, API keys, passwords
- SQL injection and NoSQL injection
- Missing authentication and authorization checks
- Insecure deserialization
- Security misconfigurations
- Sensitive data exposure

Output your audit as YAML first:

passed: true/false
issues:
  - file: "path/to/file"
    severity: critical/high/medium/low
    message: "Description of the vulnerability"
    fix: "How to fix it"

Then, if any files need patching, output the fixed versions:

```file:path/to/file.ext
<complete corrected file contents>
```

Be concise. Only report actual security issues, not style preferences.
"""
class SecurityAgent(BaseAgent):
    name = "security"
    skill_description = (
        "Performs security audits on generated code: OWASP top 10 checks, "
        "secret detection, injection flaw analysis, and hardening suggestions."
    )
    role = (
        "You are Forge Security, an application security expert specializing in "
        "secure code review and hardening.\n\n"
        "You check for:\n"
        "- OWASP Top 10 vulnerabilities (injection, auth issues, XSS, IDOR, etc.)\n"
        "- Hardcoded secrets, API keys, passwords\n"
        "- SQL injection and NoSQL injection\n"
        "- Insecure direct object references\n"
        "- Missing authentication/authorization checks\n"
        "- Insecure deserialization\n"
        "- Security misconfigurations\n"
        "- Sensitive data exposure\n\n"
        "For each issue found:\n"
        "1. Identify the file and line(s) affected\n"
        "2. Describe the vulnerability and its risk\n"
        "3. Provide a concrete fix\n\n"
        "When providing fixed files, use this format:\n\n"
        "```file:path/to/file.ext\n"
        "<complete corrected file contents>\n"
        "```\n\n"
        "Be concise. Only report actual security issues, not code style preferences."
    )

    def audit_files(self, files: dict[str, str], spec: str = "", rules: str = "") -> dict:
        """Audit a dict of {filepath: content} for security issues.

        Returns:
            {
                "passed": bool,
                "issues": [{"file": str, "severity": str, "message": str, "fix": str}],
                "patched_files": [(path, content), ...]
            }
        """
        files_str = ""
        for fp, content in files.items():
            files_str += f"\n### {fp}\n```\n{content}\n```\n"

        prompt = f"""\
## Project Context
{spec or "(No spec provided)"}

## Files to Audit
{files_str}

Perform a security audit on these files. Check for OWASP Top 10, hardcoded
secrets, injection flaws, and missing auth checks.

Output your audit as YAML:

passed: true/false
issues:
  - file: "path/to/file"
    severity: critical/high/medium/low
    message: "Description of the vulnerability"
    fix: "Brief description of how to fix it"

If you have fixed versions of files, include them after the YAML using:

```file:path/to/file.ext
<complete corrected file>
```

If no issues found:
passed: true
issues: []

Output the YAML first, then any fixed files."""

        response = self.invoke(prompt)
        return self._parse_audit(response)

    def _parse_audit(self, response: str) -> dict:
        """Parse the security audit response."""
        import re
        import yaml

        result = {"passed": True, "issues": [], "patched_files": []}

        # Extract patched files first
        patched = self.extract_files(response)
        result["patched_files"] = patched

        # Extract YAML section
        text = response.strip()
        yaml_match = re.search(r'^(passed:.*?)(?:```|$)', text, re.DOTALL | re.MULTILINE)
        if yaml_match:
            yaml_text = yaml_match.group(1).strip()
        else:
            if text.startswith("```"):
                lines = text.split("\n")
                end = next((i for i, l in enumerate(lines[1:], 1) if l.strip() == "```"), len(lines))
                yaml_text = "\n".join(lines[1:end])
            else:
                yaml_text = text

        try:
            parsed = yaml.safe_load(yaml_text)
            if isinstance(parsed, dict):
                result["passed"] = parsed.get("passed", True)
                result["issues"] = parsed.get("issues", [])
        except yaml.YAMLError:
            pass

        return result
