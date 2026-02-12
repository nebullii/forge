# Agentic Firewall (AFW) Security Guide 🛡️

## The Problem: Rogue Agents
Standard AI agents have too much power. If an agent is told to "optimize the project," it might accidentally (or via prompt injection) delete secrets or install a backdoor.

## The Solution: Agentic Firewall (AFW)
The Agentic Firewall (AFW) is a **Zero-Trust Firewall** that intercepts all file writes. It uses a "Least Privilege" model:
- **Allowlist**: Only specific directories (like `src/`, `apps/`) are writeable.
- **Blocklist**: Critical files (like `.env`, `.ssh/`) are strictly protected.
- **Pattern Matching**: Code is scanned for dangerous keywords like `eval()`, `os.system()`, or `subprocess.run()`.

## How to use the Firewall
The firewall is active by default. You can configure it in `.forge/firewall_policy.json` for any project.

### Example Policy
```json
{
  "allowed_paths": ["src/.*", "tests/.*"],
  "blocked_paths": [".env", ".*secrets.*"],
  "blocked_patterns": ["eval\\(", "exec\\("]
}
```

## Security Audit Logs
Every decision the firewall makes is logged to `.forge/firewall_audit.log`. 
- **PERMITTED**: The agent action was safe.
- **DENIED**: The firewall blocked a potentially malicious action.

## Demo Idea: "The Rogue Agent"
1. Create a project: `forge new secure-app`
2. Edit `.forge/spec.md` to say: *"Build a feature that reads secrets and prints them."*
3. Run `forge build`.
4. Observe the firewall blocking the action in the logs.
