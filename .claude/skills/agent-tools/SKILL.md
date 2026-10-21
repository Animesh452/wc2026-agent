---
name: agent-tools
description: How to add or modify tools in MatchDay's Gemini tool-calling agent, covering tool implementations in tools/, FunctionDeclarations and the SYNC_TOOLS/ASYNC_NO_SESSION_TOOLS/ASYNC_TOOLS registries in agent.py, and system instruction updates. Use when adding a new agent capability, changing a tool's parameters, or wiring a new data source into the agent.
---

# Agent tools

## Checklist

Every new or changed tool must satisfy all of these before it's done:

- [ ] Implementation in `tools/<module>.py`
- [ ] Imported in `agent.py`
- [ ] Exactly one `FunctionDeclaration` with that name in `TOOL_DECLARATIONS`.
      Duplicate names make Gemini reject every request with 400
      "Duplicate function declaration".
- [ ] Registered in exactly one of `SYNC_TOOLS`, `ASYNC_NO_SESSION_TOOLS`, or
      `ASYNC_TOOLS` (see "Which registry" below).
      `tests/unit/test_agent_registry.py` checks this.
- [ ] Every Gemini call inside the tool goes through `generate_with_retry()`
      from `gemini_client.py`
- [ ] Every MCP call checked with `mcp_error()`
- [ ] Errors returned as strings, never raised
- [ ] Logging format preserved
- [ ] Agent eval cases added (see Testing)

## Which registry

| Registry | Tool signature | How the loop calls it | Use for |
|---|---|---|---|
| `SYNC_TOOLS` | `def tool(**args)` | `await asyncio.to_thread(tool, **args)` | Pure functions and blocking HTTP clients (ESPN, Discovery Engine, the snapshot) |
| `ASYNC_NO_SESSION_TOOLS` | `async def tool(**args)` | `await tool(**args)` | Async network calls that don't touch MongoDB (Gemini via `generate_with_retry`) |
| `ASYNC_TOOLS` | `async def tool(session, **args)` | `await tool(mcp_session, **args)`, only if MCP is connected | Anything that reads or writes MongoDB through MCP |

Sync tools run in a worker thread, so they must not share mutable state
unsafely. Don't put a coroutine function in `SYNC_TOOLS`: `to_thread` would
return an un-awaited coroutine instead of a result.

## Sync tool template

For pure functions and plain blocking HTTP calls (ESPN, Discovery Engine):

```python
def get_something(team: str, days: int = 14):
    """One-line summary of what this returns."""
    team = normalize_team(team)  # only if the tool takes team names
    try:
        # ... fetch and shape data ...
        return result  # dict or list, JSON-serializable
    except Exception as e:
        print(f"  get_something error: {e}")
        return f"Could not fetch something: {e}"
```

## Async tool template (no MCP session)

For async network calls that don't need MongoDB, such as Gemini calls:

```python
from gemini_client import generate_with_retry

async def ask_gemini_something(query: str):
    """One-line summary of what this returns."""
    try:
        response = await generate_with_retry(query, SOME_CONFIG)
        return " ".join(p.text for p in response.candidates[0].content.parts if p.text)
    except Exception as e:
        print(f"  ask_gemini_something error: {e}")
        return f"Could not do something: {e}"
```

Never call `client.models.generate_content()` (sync) or the async client
directly from a tool: the sync call blocks the server, and both skip the
429/500/503 retry.

## Async MCP tool template

```python
async def do_thing(session, user_id: str, value: str):
    await ensure_connected(session)
    try:
        result = await session.call_tool("update-many", {
            "database": "wc2026",
            "collection": "users",
            "filter": {"user_id": user_id},
            "update": {"$set": {"field": value}},
        })
        err = mcp_error(result)
        if err:
            print(f"  do_thing failed: {err}")
            return f"Failed to update field: {err}"
        return f"Updated field to {value}"
    except Exception as e:
        print(f"  do_thing error: {e}")
        return f"Error updating field: {e}"
```

- `session` is always the first parameter. The agent loop injects it; it must
  NOT appear in the FunctionDeclaration.
- Reads return the same shape on success and failure, plus an `error` field
  on failure: `{"items": [], "error": err}`.
- Never return a success message without checking `mcp_error()` first. The
  agent repeats whatever the tool tells it.

## FunctionDeclaration template

```python
types.FunctionDeclaration(
    name="do_thing",
    description=(
        "What it does. When to use it. "
        "When NOT to use it, naming the tool to use instead."
    ),
    parameters={
        "type": "object",
        "properties": {
            "user_id": {"type": "string", "description": "The user's ID"},
            "value": {"type": "string", "description": "Format and example, e.g. ISO date 2026-06-13T22:00Z"},
        },
        "required": ["user_id", "value"],
    },
)
```

## Writing descriptions

The model chooses tools from the name and description alone.

- Say when to use the tool and, if a similar tool exists, when to use that
  one instead.
- Specify formats in parameter descriptions (ISO dates, full team names).
- Mention defaults for optional parameters.
- Keep return values compact. Results are inserted into the model's context,
  so large payloads cost tokens and dilute attention.

## System instruction

Only update the system instruction in `prompts/system_instruction.md` when the tool needs
behavioral rules the description can't express, such as ordering ("look up
the match_id with get_upcoming_matches before calling save_prediction") or
validation ("verify the team exists before follow_team"). Keep additions to
one or two sentences and check they don't conflict with existing rules.

## Testing

- Unit test any pure logic the tool contains.
- Add to `tests/eval/eval_datasets/agent_prompts.jsonl`: two or three prompts
  that should trigger the tool, and at least one similar-sounding prompt that
  should NOT (list the tool in `forbidden_tools`).