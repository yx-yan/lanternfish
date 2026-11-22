<h1 align="center">Lanternfish</h1>

<p align="center">
  <strong>Your AI usage limits, always lit.</strong><br>
  Claude and Codex subscription usage in the macOS menu bar, so you stop opening two settings pages to check.
</p>

```
C 16% · X 58%
```

Click it for the details:

```
Claude (pro)
    5-hour  16%  ·  resets in 4h 29m
    Weekly  20%  ·  resets in 19h 49m
Codex (plus)
    5-hour  58%  ·  resets in 3h 32m
    Weekly  13%  ·  resets in 3d 22h
Updated 14:12
Refresh now
Quit Lanternfish
```

- **No extra login.** It reuses the sign-ins you already have: Claude Code's token in the macOS Keychain and Codex CLI's `~/.codex/auth.json`.
- **Nothing leaves your Mac** except the usage request itself, sent straight to Anthropic and OpenAI.
- **One source failing never hides the other.** A broken source shows `—` and the reason.
- Refreshes every 5 minutes, or press ⌘R in the menu.

## Quick start

You need macOS, Python 3.12, and at least one of [Claude Code](https://claude.com/claude-code) or [Codex CLI](https://github.com/openai/codex) signed in with a subscription.

```bash
python3.12 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/lanternfish          # print usage once in the terminal
.venv/bin/python -m lanternfish  # start the menu bar app
```

## How it works

| Source | Credential | Endpoint |
|---|---|---|
| Claude subscription | Keychain item `Claude Code-credentials` | `GET https://api.anthropic.com/api/oauth/usage` |
| Codex subscription | `~/.codex/auth.json` | `GET https://chatgpt.com/backend-api/wham/usage` |

Both endpoints are **unofficial**: they are what the official apps use, and they may change without notice.
If a token has expired, Lanternfish tells you to run `claude` or `codex login` again; it never refreshes tokens itself.

## Roadmap

- [x] M1: Claude and Codex subscription limits
- [ ] M2: API spend (Anthropic, OpenAI, DeepSeek)
- [ ] M3: `.app` bundle, start at login, alert above 80%
- [ ] M4: logo

## License

MIT
