# Deployment Guide

## Option 1: PyPI (Recommended)

Publish so anyone can `pip install` your tool.

### Prepare pyproject.toml
```toml
[project]
name = "your-tool-name"
version = "0.1.0"
description = "What it does"
authors = [{ name = "Your Name", email = "you@example.com" }]
requires-python = ">=3.10"
dependencies = ["click>=8.0"]

[project.scripts]
yourtool = "yourtool.cli:main"

[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"
```

### Build and upload
```bash
# Install build tools
pip install build twine

# Build
python -m build

# Upload to PyPI (need account at pypi.org)
twine upload dist/*

# Users can now install
pip install your-tool-name
```

---

## Option 2: GitHub Releases

Share downloadable binaries.

### Create binary with PyInstaller
```bash
pip install pyinstaller
pyinstaller --onefile src/yourtool/cli.py --name yourtool
```

### Upload to GitHub
1. Go to your repo > Releases
2. Click "Create a new release"
3. Upload the binary from `dist/`
4. Add installation instructions

### Users install
```bash
# Download from releases, then
chmod +x yourtool
./yourtool --help
```

---

## Option 3: Homebrew (macOS)

Create a Homebrew formula.

### Create formula
```ruby
# yourtool.rb
class Yourtool < Formula
  desc "What it does"
  homepage "https://github.com/you/yourtool"
  url "https://github.com/you/yourtool/archive/v0.1.0.tar.gz"
  sha256 "..."

  depends_on "python@3.10"

  def install
    virtualenv_install_with_resources
  end
end
```

### Submit to homebrew-core or host your own tap
```bash
brew tap you/tools
brew install yourtool
```

---

## Option 4: pipx (User Install)

For tools that should be installed globally:

```bash
# Users install with pipx
pipx install your-tool-name
```

---

## Versioning

Use semantic versioning:
- `0.1.0` - Initial release
- `0.1.1` - Bug fixes
- `0.2.0` - New features
- `1.0.0` - Stable release

---

## Pre-Publish Checklist

- [ ] `--help` shows useful information
- [ ] All commands work as expected
- [ ] pyproject.toml has correct metadata
- [ ] README has installation and usage examples
- [ ] LICENSE file included
- [ ] No hardcoded paths or secrets
