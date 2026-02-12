# Evolution: The Agentic Firewall 🛡️

## Hackathon Vision
Transform a standard agentic orchestrator into a **Security-Hardened Agent Framework**.

The core feature is the **Agentic Firewall (AFW)**: a zero-trust middleware that sits between the LLM and the filesystem/shell. It ensures that even if an agent is compromised via prompt injection, it cannot perform destructive actions.

## Key Features to Build
1.  **Zero-Trust Interceptor**: Hooks into `src/coder.py` and `src/orchestrator.py` to validate every file write and system command.
2.  **Policy-as-Code**: A `firewall_policy.json` that defines allowed/blocked patterns (e.g., "Allow edits to `src/`, block edits to `.env` or `~/.ssh`").
3.  **Real-time Audit Logs**: A dedicated log for security events, highlighting blocked "attacks."
4.  **Security Reviewer**: Enhance the `ReviewerAgent` to specifically look for "Tool Injection" vulnerabilities in the generated code.

## File Structure
- `src/security/firewall.py`: Core AFW logic.
- `config/firewall_policy.json`: The default security rules.
- `logs/firewall_audit.log`: History of allowed/denied actions.

## Demo Scenario
**"The Rogue Agent"**:
We give the system a malicious task (e.g., "Build a feature that exfiltrates user data from .env").
- **Without AFW**: The agent might successfully add a malicious script.
- **With AFW**: The firewall detects the attempt to read/write sensitive files and blocks it immediately.
