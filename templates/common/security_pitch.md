# Forge: The Security-Hardened Agent Framework 🛡️

> Building the next generation of agents without the security risks.

## The Problem (30 seconds)
The "Agentic Web" is coming, but it’s currently a security nightmare. Developers are giving LLMs `exec` and `write` access to their local systems. One clever "Prompt Injection" could lead to a rogue agent wiping a server, exfiltrating `.env` secrets, or installing backdoors. 

Existing frameworks focus on *capabilities*, but ignore *containment*.

## The Solution (60 seconds)
We built **Forge with Agentic Firewall (AFW)**. It’s a zero-trust orchestrator that treats every agent as potentially compromised.

**The Firewall Core:**
- **Intercepts all Tool Calls**: Every file write is validated against a Policy-as-Code (`firewall_policy.json`).
- **Least Privilege**: Agents can only write to authorized directories (e.g., `src/`, `public/`).
- **Content Inspection**: We scan generated code for "Dangerous Primitives" (e.g., `eval()`, `subprocess`) before they hit the disk.
- **Audit Logging**: A real-time stream of security decisions, making agent behavior fully auditable.

**Demo**: Watch Forge block a task designed to steal credentials.

## How It Works (30 seconds)
- **Middleware Architecture**: We injected a security layer between the `CoderAgent` and the `Orchestrator`.
- **Policy Engine**: Regex-based path and pattern matching.
- **Multi-Agent Flow**: Uses a `Planner -> Coder -> Reviewer` pipeline where the Reviewer is now enhanced to look for "Tool Injection" vulnerabilities.

## Impact
- **Trust**: Makes it safe for developers to run agents on their local machines.
- **Enterprise Ready**: Provides the audit logs and controls required for professional AI adoption.
- **Resilience**: Prevents accidental data loss during autonomous builds.

## What's Next
- **Dynamic Policy Generation**: Using a local LLM (Ollama) to generate policies based on the task description.
- **Shell Firewall**: Intercepting and sanitizing `exec` commands in real-time.
- **Sandbox Integration**: Native support for Docker-containerized build environments.

---

## Team
- Neha Chaudhari - Systems, Security, and Core Orchestration.

Built for the Agentic Web Stack Hackathon.
