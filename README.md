<h1 align="center">Lanternfish</h1>

<p align="center">
  <strong>Your AI usage limits, always lit.</strong><br>
  Claude and Codex subscription usage in the macOS menu bar, plus API spend, so you stop opening settings pages to check.
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
Anthropic API
    This month  $12.40
DeepSeek API
    Balance  ¥110.00
Updated 14:12
Refresh now
API Keys              ▸
Quit Lanternfish
```

- **No extra login.** It reuses the sign-ins you already have: Claude Code's token in the macOS Keychain and Codex CLI's `~/.codex/auth.json`.
- **Nothing leaves your Mac** except the usage request itself, sent straight to Anthropic and OpenAI.
- **One source failing never hides the other.** A broken source shows `—` and the reason.
- **API spend is opt-in.** Add a key under *API Keys* and that row appears; the menu bar title stays subscriptions only.
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
| Anthropic API, this month | Admin API key (`sk-ant-admin…`) | `GET https://api.anthropic.com/v1/organizations/analytics/cost` (beta) |
| OpenAI API, this month | Admin key | `GET https://api.openai.com/v1/organization/costs` |
| DeepSeek API balance | API key | `GET https://api.deepseek.com/user/balance` |

API keys are entered from the *API Keys* menu and stored in your login Keychain (service `lanternfish`); they never touch a file.
"This month" is the current UTC month. Anthropic cost data usually lags by up to 4 hours; OpenAI's is daily.

The two subscription endpoints are **unofficial**: they are what the official apps use, and they may change without notice.
If a token has expired, Lanternfish tells you to run `claude` or `codex login` again; it never refreshes tokens itself.

## Roadmap

- [x] M1: Claude and Codex subscription limits
- [x] M2: API spend (Anthropic, OpenAI, DeepSeek)
- [ ] M3: `.app` bundle, start at login, alert above 80%
- [ ] M4: logo

## License

MIT
