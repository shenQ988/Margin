# Margin

Margin is a local reading companion built on nanobot. It connects to WeRead,
helps you explore your shelf and notes, and can create grounded reading
recommendations from books available in WeRead.

## Requirements

- Python 3.11 or newer
- [uv](https://docs.astral.sh/uv/)
- [Bun](https://bun.sh/) when running the Web UI from a source checkout
- An LLM provider API key, configured during setup
- Optional: a WeRead Agent API key for shelf, notes, and catalog features

## Run locally

Clone the repository and install the Python environment:

```bash
git clone <your-repository-url>
cd nanobot
uv sync --all-extras --dev
```

Run the interactive setup wizard. It creates your local configuration and
asks for an LLM provider and API key:

```bash
uv run margin onboard --wizard
```

Start the app and open the URL printed in the terminal:

```bash
uv run margin webui
```

The gateway exposes a health check at `http://127.0.0.1:18790/health` by
default. Stop it with `Ctrl+C`.

## Enable WeRead features

Set a WeRead Agent API key before starting Margin:

```bash
export WEREAD_API_KEY="wrk-your-key"
uv run margin webui
```

The key is optional: without it, general chat still works, but Margin cannot
read your WeRead shelf, notes, or search the WeRead catalog.

Try prompts such as:

- `What's on my bookshelf?`
- `Show my highlights in Pride and Prejudice.`
- `Recommend more books by Jane Austen.`
- `I want to go deeper into product management. Recommend three books available in WeRead.`

## Web UI development

Run the gateway in one terminal:

```bash
uv run margin gateway
```

Then run the Vite development server in another:

```bash
cd webui
bun install
bun run dev
```

The development server proxies API and WebSocket traffic to the local gateway.

## Verify changes

```bash
# Python tests
uv run pytest

# Lint
uv run ruff check nanobot/

# Web UI tests
cd webui && bun run test
```

## Configuration

Margin stores local configuration under `~/.nanobot/config.json`. Re-run the
setup wizard whenever you want to change provider settings:

```bash
uv run margin onboard --wizard
```

Never commit API keys or your local `~/.nanobot` configuration.
