# Margin

Margin is a stateful AI reading agent that combines long-term conversational memory with tool-grounded access to WeRead. It is designed around two reliability problems in agent systems: preserving useful context across long-running interactions and deciding when and how to invoke external tools.

Choosing what to read next is difficult because reading is cumulative. A useful recommendation depends not only on a reader’s stated interests, but also on what they have actually read, where they paused, which ideas they highlighted, what they found confusing, and what kind of explanation helps them learn.

Generic chatbots can offer one-off book lists, but they lack a reliable view of this ongoing context. They may repeat books already on the reader’s shelf, miss the difference between a book that was opened and one that was deeply studied, or make recommendations without checking whether a book is available in the reader’s reading app.

Margin is designed for one focused workflow: helping a reader decide what to study next. It combines persistent context about the reader’s goals, conceptual gaps, and preferences with live WeRead data about their shelf, notes, progress, and catalog availability. The result is a small, grounded reading plan: what to read next, why it fits the reader’s current path, and what gap it helps fill.

<img src="rsc/poster.png" alt="Margin poster" width="520" />

```text
User
 │
 ▼
┌───────────────────────────┐
│       Margin Agent        │
│   reasoning + tool routing│
└──────────┬────────────────┘
           │
     ┌─────┴─────┐
     ▼           ▼
WeRead Tools   Conversation History
├─ bookshelf          │
├─ notes              ▼
└─ catalog search  Memory Consolidation
                       │
                       ▼
                 Long-Term Memory
                       │
                       └──► Future agent context
```
## Architecture

- Agent loop: Incoming WebSocket or channel messages are placed on an async message bus. AgentLoop resolves the session, builds prompt context, and delegates model/tool iterations to AgentRunner. Tool results are appended to the active session before the model produces the final response.

- Memory: Session transcripts are persisted separately from long-term memory. MemoryStore maintains history.jsonl and durable workspace memory such as memory/MEMORY.md; Consolidator compresses older session material into summaries and durable facts. ContextBuilder injects long-term memory, eligible recent history, workspace instructions, active skills, and any session summary into the system prompt.

- Tool routing: The model receives typed tool schemas through ToolRegistry. Calls are validated, executed, and returned into the conversation loop. Live-state requests are routed to tools rather than answered from long-term memory, preventing stale shelf, progress, note, and catalog information.

- WeRead integration: WeRead integration: The native weread tool calls the WeRead Agent Gateway. The advisor actions fan out to /shelf/sync, /user/notebooks, and /store/search; results are cross-analyzed to classify reading depth, remove owned books and duplicate editions, and return only validated recommendation candidates.

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
