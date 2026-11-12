# AI Developer Workflow (ADW) System

ADW automates software development by integrating GitHub issues with Copilot CLI to classify issues, generate plans, implement solutions, and create pull requests.

## Quick Start

### 1. Set Environment Variables

```bash
export GITHUB_REPO_URL="https://github.com/owner/repository"
export COPILOT_CODE_PATH="/path/to/copilot"  # Optional, defaults to "copilot"
export GITHUB_PAT="ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"  # Optional, only if using different account than 'gh auth login'
```

### 2. Install Prerequisites

```bash
# GitHub CLI
brew install gh              # macOS
# or: sudo apt install gh    # Ubuntu/Debian
# or: winget install --id GitHub.cli  # Windows

# Copilot CLI
# Follow instructions at https://docs.github.com/en/copilot/how-tos/copilot-cli/install-copilot-cli

# Python dependency manager (uv)
curl -LsSf https://astral.sh/uv/install.sh | sh  # macOS/Linux
# or: powershell -c "irm https://astral.sh/uv/install.ps1 | iex"  # Windows

# Authenticate GitHub
gh auth login
copilot login
```

### 3. Run ADW

```bash
cd adws/

# Process a single issue manually
uv run adw_plan_build.py 123

# Run continuous monitoring (polls every 20 seconds)
uv run trigger_cron.py

# Start webhook server (for instant GitHub events)
uv run trigger_webhook.py
```

## Script Usage Guide

### adw_plan_build.py - Process Single Issue

Executes the complete ADW workflow for a specific GitHub issue.

```bash
# Basic usage
uv run adw_plan_build.py 456

# What it does:
# 1. Fetches issue #456 from GitHub
# 2. Creates feature branch
# 3. Classifies issue type (/chore, /bug, /feature)
# 4. Generates implementation plan
# 5. Implements the solution
# 6. Creates commits and pull request
```

**Example output:**
```
ADW ID: e5f6g7h8
issue_command: /feature
Working on branch: feat-456-e5f6g7h8-add-user-authentication
plan_file_path: specs/add-user-authentication-system-plan.md
Pull request created: https://github.com/owner/repo/pull/789
```

### trigger_cron.py - Automated Monitoring

Continuously monitors GitHub for new issues or "adw" comments.

```bash
# Start monitoring
uv run trigger_cron.py

# Processes issues when:
# - New issue has no comments
# - Latest comment on any issue is exactly "adw"

# Example log output:
# 2024-01-15 10:30:45 - Starting ADW cron trigger
# 2024-01-15 10:30:46 - Issue #123 has no comments - processing
# 2024-01-15 10:30:47 - Issue #456 - latest comment is 'adw' - processing
```

**Production deployment with systemd:**
```bash
# Create service file: /etc/systemd/system/adw-cron.service
sudo systemctl enable adw-cron
sudo systemctl start adw-cron
```

### trigger_webhook.py - GitHub Webhook Server

Receives real-time GitHub events for instant processing.

```bash
# Start webhook server (default port 8001)
uv run trigger_webhook.py

# Custom port
PORT=3000 uv run trigger_webhook.py

# Configure GitHub webhook:
# URL: https://your-server.com/gh-webhook
# Events: Issues, Issue comments
```

**Endpoints:**
- `/gh-webhook` - Receives GitHub events
- `/health` - Health check endpoint

## How ADW Works

1. **Issue Classification**: Analyzes GitHub issue and determines type:
   - `/chore` - Maintenance, documentation, refactoring
   - `/bug` - Bug fixes and corrections
   - `/feature` - New features and enhancements

2. **Planning**: `sdlc_planner` agent creates implementation plan with:
   - Technical approach
   - Step-by-step tasks
   - File modifications
   - Testing requirements

3. **Implementation**: `sdlc_implementor` agent executes the plan:
   - Analyzes codebase
   - Implements changes
   - Runs tests
   - Ensures quality

4. **Integration**: Creates git commits and pull request:
   - Semantic commit messages
   - Links to original issue
   - Implementation summary

## Common Usage Scenarios

### Process a bug report
```bash
# User reports bug in issue #789
uv run adw_plan_build.py 789
# ADW analyzes, creates fix, and opens PR
```

### Enable automatic processing
```bash
# Start cron monitoring
uv run trigger_cron.py
# New issues are processed automatically
# Users can comment "adw" to trigger processing
```

### Deploy webhook for instant response
```bash
# Start webhook server
uv run trigger_webhook.py
# Configure in GitHub settings
# Issues processed immediately on creation
```

## Troubleshooting

### Environment Issues
```bash
# Check required variables
env | grep -E "(GITHUB|COPILOT)"

# Verify GitHub auth
gh auth status

# Test Copilot
copilot --version
```

### Common Errors

**"Copilot CLI is not installed"**
```bash
which copilot  # Check if installed
# Reinstall from https://docs.github.com/en/copilot/how-tos/copilot-cli/install-copilot-cli
```

**"Missing GITHUB_PAT"** (Optional - only needed if using different account than 'gh auth login')
```bash
export GITHUB_PAT=$(gh auth token)
```

**"Agent execution failed"**
```bash
# Check agent output
cat agents/*/sdlc_planner/raw_output.jsonl | tail -1 | jq .
```

### Debug Mode
```bash
export ADW_DEBUG=true
uv run adw_plan_build.py 123  # Verbose output
```

## Configuration

### ADW Tracking
Each workflow run gets a unique 8-character ID (e.g., `a1b2c3d4`) that appears in:
- Issue comments: `a1b2c3d4_ops: ✅ Starting ADW workflow`
- Output files: `agents/a1b2c3d4/sdlc_planner/raw_output.jsonl`
- Git commits and PRs

### Model Selection
Workflow requests select `sonnet` or `opus`; `agent.py` maps these to Copilot model IDs.
The selected models must be available to your Copilot account.

The workflow loads skills from `.github/skills/`, which refer to the existing
templates in `.claude/commands/`. Template arguments are passed as a JSON array.
Each workflow invocation trusts this repository and uses `--allow-all`, so run
it only in a repository and environment you trust.

### Output Structure
```
agents/
├── a1b2c3d4/
│   ├── sdlc_planner/
│   │   └── raw_output.jsonl
│   └── sdlc_implementor/
│       └── raw_output.jsonl
```

## Security Best Practices

- Store tokens as environment variables, never in code
- Use GitHub fine-grained tokens with minimal permissions
- Set up branch protection rules
- Require PR reviews for ADW changes
- Monitor API usage and set billing alerts

## Technical Details

### Core Components
- `agent.py` - Copilot CLI integration
- `data_types.py` - Pydantic models for type safety
- `github.py` - GitHub API operations
- `adw_plan_build.py` - Main workflow orchestration (plan & build)

### Branch Naming
```
{type}-{issue_number}-{adw_id}-{slug}
```
Example: `feat-456-e5f6g7h8-add-user-authentication`

### Commit Format
```
{type}: {description} for #{issue_number}

Generated with ADW ID: {adw_id}
🤖 Generated with Copilot
```

### API Rate Limits
- GitHub: 5000 requests/hour (authenticated)
- Copilot: Based on your plan and available models
- Automatic retry with exponential backoff