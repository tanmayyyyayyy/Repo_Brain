# Claude Code Integration Guide

This integration enables **RepoBrain Preflight** inside [Claude Code](https://github.com/anthropics/claude-code), preventing the agent from modifying protected files, hardcoding credentials, or injecting insecure shell pipelines *before* changes hit disk.

---

## 1. How It Works

Claude Code supports tool execution hooks. Before Claude executes `Edit` or `Write` tools:
1. The hook passes the intended target file and replacement content to `repobrain preflight`.
2. RepoBrain Shield evaluates:
   - **Protected Paths**: Rejects edits to `.github/workflows/`, `repobrain.yml`, `secrets/`, or certificates.
   - **Secrets**: Rejects accidental commits of AWS, GitHub, GCP, or OpenAI API keys.
   - **Prompt Injections**: Detects and rejects malicious instructions hidden in code comments.
   - **Risky Commands**: Flags unverified shell piping (`curl | bash`, `Invoke-Expression`).
3. If Shield flags a blocking finding, `preflight` exits code 1 with JSON details, returning an error to Claude so it can self-correct immediately without breaking CI.

---

## 2. Setup Instructions

### Option A: Project Configuration (`.claude/settings.json`)
Copy the hook configuration into your project root:
```bash
mkdir -p .claude
cp integrations/claude-code/settings.json .claude/settings.json
```

### Option B: Global Claude Code Hooks (`~/.claude/hooks.json`)
Merge `integrations/claude-code/hooks.json` into your user Claude configuration:
```json
{
  "hooks": {
    "preToolExecution": {
      "commands": [
        {
          "tools": ["Edit", "Write", "Replace"],
          "command": "python -m repobrain preflight --actor claude --path \"$TOOL_INPUT_FILE\" --content-file \"$TOOL_INPUT_CONTENT_TMP\""
        }
      ]
    }
  }
}
```

---

## 3. Manual Verification

Test the preflight hook directly against a forbidden path:
```bash
python -m repobrain preflight --actor claude --path .github/workflows/ci.yml
```

Expected JSON response (exit code 1):
```json
{
  "actor": "claude",
  "ai": true,
  "decision": "block",
  "reason": "blocked by policy: .github/workflows/ci.yml is in protected paths",
  "findings": [
    {
      "severity": "block",
      "rule": "blocked-path",
      "file": ".github/workflows/ci.yml",
      "message": "AI actors are not permitted to edit protected path: .github/workflows/"
    }
  ]
}
```

When Claude receives this block, it immediately explains to the user that `.github/workflows/ci.yml` is protected and requests human permission.
