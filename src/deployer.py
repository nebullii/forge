"""Deployer - handles deployment to various platforms."""

import os
import subprocess
from pathlib import Path


class Deployer:
    """Handles deployment to various platforms."""

    def __init__(self, config: dict, target: str = None):
        self.config = config
        deploy_config = config.get("deploy", {})
        self.target = target or deploy_config.get("default", "gcloud")
        self.target_config = deploy_config.get(self.target, {})

    def run(self) -> str:
        """Deploy and return the URL."""
        deployers = {
            "gcloud": self._deploy_gcloud,
            "vercel": self._deploy_vercel,
            "railway": self._deploy_railway,
            "render": self._deploy_render,
            "fly": self._deploy_fly,
        }

        if self.target not in deployers:
            raise ValueError(f"Unknown deployment target: {self.target}")

        return deployers[self.target]()

    def _deploy_gcloud(self) -> str:
        """Deploy to Google Cloud Run."""
        project = self.target_config.get("project") or os.environ.get("GCLOUD_PROJECT")
        region = self.target_config.get("region", "us-central1")
        service_name = Path.cwd().name

        if not project:
            # Try to get from gcloud config
            result = subprocess.run(
                ["gcloud", "config", "get-value", "project"],
                capture_output=True, text=True
            )
            project = result.stdout.strip()

        if not project:
            raise ValueError("No GCloud project configured. Set GCLOUD_PROJECT or run 'gcloud config set project <id>'")

        # Build and deploy
        cmd = [
            "gcloud", "run", "deploy", service_name,
            "--source", ".",
            "--region", region,
            "--platform", "managed",
            "--allow-unauthenticated",
            "--memory", "256Mi",
            "--cpu", "1",
            "--min-instances", "0",
            "--max-instances", "2",
            "--project", project,
        ]

        print(f"   Running: {' '.join(cmd[:6])}...")
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            print(result.stderr)
            raise RuntimeError("Cloud Run deployment failed")

        # Get service URL
        url_cmd = [
            "gcloud", "run", "services", "describe", service_name,
            "--region", region,
            "--project", project,
            "--format", "value(status.url)"
        ]
        url_result = subprocess.run(url_cmd, capture_output=True, text=True)
        return url_result.stdout.strip()

    def _deploy_vercel(self) -> str:
        """Deploy to Vercel."""
        token = self.target_config.get("token") or os.environ.get("VERCEL_TOKEN")

        if not token:
            raise ValueError("No Vercel token configured. Set VERCEL_TOKEN")

        cmd = ["vercel", "--prod", "--yes", "--token", token]
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            print(result.stderr)
            raise RuntimeError("Vercel deployment failed")

        # Extract URL from output
        for line in result.stdout.split("\n"):
            if "https://" in line:
                return line.strip()

        return "Deployed (check Vercel dashboard for URL)"

    def _deploy_railway(self) -> str:
        """Deploy to Railway."""
        token = self.target_config.get("token") or os.environ.get("RAILWAY_TOKEN")

        if not token:
            raise ValueError("No Railway token configured. Set RAILWAY_TOKEN")

        # Railway CLI deployment
        cmd = ["railway", "up", "--detach"]
        env = os.environ.copy()
        env["RAILWAY_TOKEN"] = token

        result = subprocess.run(cmd, capture_output=True, text=True, env=env)

        if result.returncode != 0:
            print(result.stderr)
            raise RuntimeError("Railway deployment failed")

        return "Deployed (check Railway dashboard for URL)"

    def _deploy_render(self) -> str:
        """Deploy to Render."""
        api_key = self.target_config.get("api_key") or os.environ.get("RENDER_API_KEY")

        if not api_key:
            raise ValueError("No Render API key configured. Set RENDER_API_KEY")

        # Render requires a render.yaml or manual setup
        render_yaml = Path("render.yaml")
        if not render_yaml.exists():
            render_yaml.write_text("""services:
  - type: web
    name: {name}
    env: docker
    plan: free
    healthCheckPath: /
""".format(name=Path.cwd().name))

        print("   Created render.yaml")
        print("   Push to GitHub and connect repo at https://dashboard.render.com")
        return "Manual: Connect repo at https://dashboard.render.com"

    def _deploy_fly(self) -> str:
        """Deploy to Fly.io."""
        # Check if fly.toml exists
        fly_toml = Path("fly.toml")
        if not fly_toml.exists():
            # Initialize
            app_name = Path.cwd().name.replace("_", "-")
            subprocess.run(["fly", "launch", "--name", app_name, "--no-deploy", "--yes"])

        # Deploy
        result = subprocess.run(["fly", "deploy"], capture_output=True, text=True)

        if result.returncode != 0:
            print(result.stderr)
            raise RuntimeError("Fly.io deployment failed")

        # Get URL
        app_name = Path.cwd().name.replace("_", "-")
        return f"https://{app_name}.fly.dev"
