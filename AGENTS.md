## Cursor Cloud specific instructions

### Overview

nanobot is an ultra-lightweight personal AI assistant framework (Python >=3.11). It provides a CLI agent (`nanobot agent`) and a gateway server (`nanobot gateway`) that connects to chat platforms. There is no database; all state is file-based under `~/.nanobot/`.

### Running commands

- `$HOME/.local/bin` must be on `PATH` (already added to `~/.bashrc`).
- Standard dev commands are documented in the README and `pyproject.toml`:
  - **Lint:** `ruff check .` (113 pre-existing lint issues in the codebase; this is expected)
  - **Tests:** `pytest tests/` (231 tests, all passing)
  - **Run CLI:** `nanobot agent -m "Hello"` (requires an LLM API key)
  - **Run gateway:** `nanobot gateway` (requires an LLM API key + channel tokens)

### LLM API key requirement

The core functionality requires at least one LLM provider API key in `~/.nanobot/config.json`. Without it, `nanobot agent` exits with `Error: No API key configured.` To configure:

```bash
nanobot onboard  # creates default config if missing
```

Then edit `~/.nanobot/config.json` and set a provider key, e.g.:

```json
{
  "providers": {
    "openrouter": {
      "apiKey": "sk-or-v1-xxx"
    }
  }
}
```

If the `OPENROUTER_API_KEY` secret is available in the environment, you can inject it with:

```bash
python3 -c "
import json, os, pathlib
p = pathlib.Path.home() / '.nanobot' / 'config.json'
c = json.loads(p.read_text())
c['providers']['openrouter']['apiKey'] = os.environ['OPENROUTER_API_KEY']
p.write_text(json.dumps(c, indent=2))
"
```

### Gotchas

- The `nanobot/templates/AGENTS.md` file is a template for the bot's workspace, not the repository-level `AGENTS.md`.
- `ruff` config lives in `pyproject.toml` (line-length=100, ignores E501).
- `pytest` is configured with `asyncio_mode = "auto"` and `testpaths = ["tests"]`.
- The WhatsApp bridge (`bridge/`) is an optional Node.js sub-component; it is not needed for core development.
