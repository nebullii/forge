# Build Rules

## Stack
- Language: Python 3.10+
- CLI Framework: Click or Typer
- Config: python-dotenv for env vars
- Packaging: pyproject.toml

## Structure
```
/
├── src/
│   └── mytool/
│       ├── __init__.py
│       ├── cli.py         # Command definitions
│       ├── commands/      # Subcommand handlers
│       │   ├── __init__.py
│       │   └── process.py
│       └── utils.py       # Helper functions
├── pyproject.toml
├── README.md
└── LICENSE
```

## pyproject.toml Template
```toml
[project]
name = "mytool"
version = "0.1.0"
description = "What it does"
requires-python = ">=3.10"
dependencies = [
    "click>=8.0",
    "rich>=13.0",  # Pretty output
]

[project.scripts]
mytool = "mytool.cli:main"

[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"
```

## CLI Pattern (Click)
```python
import click

@click.group()
@click.version_option()
def main():
    """Your tool description."""
    pass

@main.command()
@click.argument('input_file')
@click.option('--output', '-o', help='Output file')
def process(input_file, output):
    """Process a file."""
    click.echo(f"Processing {input_file}")

if __name__ == '__main__':
    main()
```

## CLI Pattern (Typer)
```python
import typer
app = typer.Typer()

@app.command()
def process(input_file: str, output: str = None):
    """Process a file."""
    print(f"Processing {input_file}")

if __name__ == '__main__':
    app()
```

## Constraints
- Fast startup time (< 100ms)
- Work offline
- Clear error messages
- Non-zero exit codes on error

## Output Rules
- Use stderr for errors/warnings
- Use stdout for actual output
- Support --quiet and --verbose flags
- Use Rich for colored output (optional)

## Config Handling
```python
# ~/.mytool/config.json or ~/.config/mytool/
import os
from pathlib import Path

CONFIG_DIR = Path.home() / ".config" / "mytool"
CONFIG_FILE = CONFIG_DIR / "config.json"
```

## Error Handling
```python
import sys
import click

def error(message):
    click.echo(f"Error: {message}", err=True)
    sys.exit(1)
```

## Testing
```bash
# Install locally for testing
pip install -e .

# Run
mytool --help
```

## Deploy Target
- PyPI: `pip install mytool`
- GitHub Releases: Binary with pyinstaller
- Homebrew: Formula for macOS
