"""Tool registry and dispatch checks for the agent loop (no network calls)."""

import asyncio
import inspect
import threading
from collections import Counter

from google.genai import types

import agent

REGISTRIES = {
    "SYNC_TOOLS": agent.SYNC_TOOLS,
    "ASYNC_NO_SESSION_TOOLS": agent.ASYNC_NO_SESSION_TOOLS,
    "ASYNC_TOOLS": agent.ASYNC_TOOLS,
}


def test_declaration_names_are_unique():
    names = Counter(d.name for d in agent.TOOL_DECLARATIONS)
    assert [n for n, count in names.items() if count > 1] == []


def test_every_declared_tool_is_registered_exactly_once():
    declared = {d.name for d in agent.TOOL_DECLARATIONS}
    for name in declared:
        homes = [reg for reg, tools in REGISTRIES.items() if name in tools]
        assert len(homes) == 1, (name, homes)
    registered = set().union(*REGISTRIES.values())
    assert registered == declared


def test_sync_tools_are_plain_functions():
    # The loop runs these with asyncio.to_thread; a coroutine function there
    # would return an un-awaited coroutine instead of a result.
    for name, fn in agent.SYNC_TOOLS.items():
        assert not inspect.iscoroutinefunction(fn), name


def test_async_tools_are_coroutine_functions():
    for registry in ("ASYNC_NO_SESSION_TOOLS", "ASYNC_TOOLS"):
        for name, fn in REGISTRIES[registry].items():
            assert inspect.iscoroutinefunction(fn), (registry, name)


def test_web_search_tools_do_not_need_mcp_session():
    assert {"web_search", "head_to_head"} <= set(agent.ASYNC_NO_SESSION_TOOLS)


def response(*parts: types.Part) -> types.GenerateContentResponse:
    return types.GenerateContentResponse(
        candidates=[types.Candidate(content=types.Content(role="model", parts=list(parts)))]
    )


def test_dispatch_runs_sync_tools_in_thread_and_async_tools_without_session(monkeypatch):
    """One turn: the model calls a sync tool and web_search, then answers."""
    replies = [
        response(
            types.Part(function_call=types.FunctionCall(name="get_world_cup_results", args={"stage": "final"})),
            types.Part(function_call=types.FunctionCall(name="web_search", args={"query": "q"})),
        ),
        response(types.Part(text="Spain won.")),
    ]

    async def fake_generate(contents, config):
        return replies.pop(0)

    sync_threads, search_calls = [], []

    def fake_results(stage=None, team=None):
        sync_threads.append(threading.current_thread())
        return {"count": 1}

    async def fake_web_search(query):
        search_calls.append(query)
        return "result"

    monkeypatch.setattr(agent, "generate_with_retry", fake_generate)
    monkeypatch.setitem(agent.SYNC_TOOLS, "get_world_cup_results", fake_results)
    monkeypatch.setitem(agent.ASYNC_NO_SESSION_TOOLS, "web_search", fake_web_search)

    user_id = "test_dispatch_user"
    try:
        # mcp_session=None: no-session tools must still run without MongoDB.
        text = asyncio.run(agent.run_agent("who won?", mcp_session=None, user_id=user_id))
        history = agent.CONVERSATIONS[user_id]
    finally:
        agent.CONVERSATIONS.pop(user_id, None)

    assert text == "Spain won."
    assert len(sync_threads) == 1
    assert sync_threads[0] is not threading.current_thread()
    assert search_calls == ["q"]
    # user message, model function calls, function responses, final answer
    assert len(history) == 4
    responses = [p.function_response.response["result"] for p in history[2].parts]
    assert responses == ['{"count": 1}', '"result"']
