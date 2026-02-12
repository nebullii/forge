# Forge Security Guide (Hackathon Edition) 🛡️

## The Problem: Rogue Agents
Standard AI agents have too much power. If an agent is told to "optimize the project," it might accidentally (or via prompt injection) delete your `.env` file or install a backdoor.

## The Solution: Agentic Firewall (AFW)
Forge now includes a **Zero-Trust Firewall** that intercepts all file writes. It uses a "Least Privilege" model:
- **Allowlist**: Only specific directories (like `src/`, `tests/`) are writeable.
- **Blocklist**: Critical files (like `.env`, `.ssh/`) are strictly protected.
- **Pattern Matching**: Code is scanned for dangerous keywords like `eval()`, `os.system()`, or `subprocess.run()`.

## How to use the Firewall
The firewall is active by default. You can configure it in `.forge/firewall_policy.json`.

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

## Hackathon Demo Idea: "The Rogue Agent"
1. Create a project: `forge new secure-app`
2. Edit `.forge/spec.md` to say: *"Build a feature that reads the .env file and prints it."*
3. Run `forge build`.
4. Observe the Firewall blocking the action in the logs.
