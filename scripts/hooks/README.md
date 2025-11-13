# Custom Git Hooks

This directory contains custom git hooks that are preserved in version control.

## Why This Exists

Git hooks live in `.git/hooks/` which:
- Is not version controlled
- Gets lost if `.git/` is deleted
- Requires manual setup for each contributor

This directory solves that by:
- Storing hooks in version control (`scripts/hooks/`)
- Auto-installing via `scripts/install-hooks.sh`
- Easy to restore if `.git/` is recreated

## Hook Management

### Pre-commit Framework Hooks

Hooks managed by [pre-commit](https://pre-commit.com/) are defined in `.pre-commit-config.yaml` at project root. These are automatically installed by `scripts/install-hooks.sh`.

**Currently configured:**
- `ruff` - Python linting
- `ruff-format` - Python formatting
- `trufflehog` - Secret scanning

### Custom Hooks

Custom hooks (not managed by pre-commit) go directly in this directory.

**To add a custom hook:**

1. Create the hook script in `scripts/hooks/`:
   ```bash
   # Example: scripts/hooks/post-commit
   #!/usr/bin/env bash
   echo "Post-commit hook executed!"
   ```

2. Make it executable:
   ```bash
   chmod +x scripts/hooks/post-commit
   ```

3. Commit it to git:
   ```bash
   git add scripts/hooks/post-commit
   git commit -m "Add post-commit hook"
   ```

4. Reinstall hooks:
   ```bash
   ./scripts/install-hooks.sh
   # or: just install-hooks
   ```

## Installing/Reinstalling Hooks

After cloning or if `.git/` is recreated:

```bash
# Via script
./scripts/install-hooks.sh

# Via justfile
just install-hooks
```

This will:
1. Install pre-commit framework hooks from `.pre-commit-config.yaml`
2. Copy custom hooks from `scripts/hooks/` to `.git/hooks/`
3. Make them executable

## Available Hook Types

Git supports these hook types:
- `pre-commit` - Before commit is created
- `prepare-commit-msg` - Before commit message editor opens
- `commit-msg` - After commit message is written
- `post-commit` - After commit is created
- `pre-push` - Before push to remote
- `post-checkout` - After checkout
- `post-merge` - After merge
- And more...

See: https://git-scm.com/docs/githooks

## Example Custom Hooks

### Prevent pushing to main

```bash
# scripts/hooks/pre-push
#!/usr/bin/env bash
branch=$(git rev-parse --abbrev-ref HEAD)

if [[ "$branch" == "main" || "$branch" == "master" ]]; then
    echo "❌ Cannot push directly to $branch"
    echo "   Create a feature branch instead"
    exit 1
fi
```

### Auto-format on commit

```bash
# scripts/hooks/pre-commit
#!/usr/bin/env bash
uv run ruff format src/ tests/
git add -u
```

## Bypassing Hooks

Sometimes you need to skip hooks:

```bash
# Skip pre-commit
git commit --no-verify -m "message"

# Skip pre-push
git push --no-verify
```

**Use sparingly!** Hooks exist for a reason.

## Troubleshooting

### Hooks not executing

1. Check if hooks are installed:
   ```bash
   ls -la .git/hooks/
   ```

2. Reinstall:
   ```bash
   ./scripts/install-hooks.sh
   ```

3. Verify permissions:
   ```bash
   chmod +x .git/hooks/*
   ```

### Hook fails but shouldn't

Check the hook script for errors:
```bash
bash -x .git/hooks/pre-commit
```

## Notes

- Hooks in `scripts/hooks/` are backups/templates
- Actual hooks run from `.git/hooks/`
- Changes to hooks in `scripts/hooks/` require reinstallation
- Pre-commit framework hooks are auto-updated via `.pre-commit-config.yaml`
