"""Tool-calling success rate evaluation harness for the reading agent.

Fully separate from production agent code (`nanobot/agent/`): this package
never imports or modifies `nanobot/bus/events.py`, `nanobot/bus/queue.py`,
or `nanobot/agent/tools/weread.py`. It drives the real `AgentRunner` (the
shared tool-calling loop) directly, against a self-contained stub tool
registry (see `eval/stub_tools.py`) and a real, configured `LLMProvider` —
so it measures actual model tool-selection behavior, not scripted
responses.

Run with: python -m eval.run_eval
"""
