"""Exercise the real Anthropic request serialization without provider access."""

import json

import httpx
import pytest
from anthropic import AsyncAnthropic
from pydantic_ai.exceptions import ContentFilterError
from pydantic_ai.providers.anthropic import AnthropicProvider

from policyengine_github_bot import llm
from policyengine_github_bot.config import Settings
from policyengine_github_bot.models import IssueResponse, PRReReviewResponse, PRReviewResponse

AGENT_CASES = [
    pytest.param(
        llm.get_issue_agent,
        IssueResponse(content="Please include a reproducer."),
        "low",
        id="issue",
    ),
    pytest.param(
        llm.get_pr_review_agent,
        PRReviewResponse(
            summary="Handle an empty input.",
            approval="REQUEST_CHANGES",
            comments=[{"path": "example.py", "line": 10, "body": "Check for an empty input."}],
        ),
        "medium",
        id="review",
    ),
    pytest.param(
        llm.get_pr_rereview_agent,
        PRReReviewResponse(
            thread_actions=[{"thread_index": 0, "action": "RESOLVE", "reply": None}],
            new_comments=[],
            summary=None,
            approval=None,
        ),
        "medium",
        id="rereview",
    ),
]


def make_settings(**overrides):
    """Keep tests independent of local credentials and .env files."""
    return Settings(
        _env_file=None,
        github_app_id=1,
        github_private_key="test-private-key",
        github_webhook_secret="test-secret",
        anthropic_api_key="test-api-key",
        **overrides,
    )


def assert_closed_objects(schema):
    """Check nested definitions as well as the top-level structured output."""
    if isinstance(schema, dict):
        if schema.get("type") == "object":
            assert schema["additionalProperties"] is False
        for value in schema.values():
            assert_closed_objects(value)
    elif isinstance(schema, list):
        for value in schema:
            assert_closed_objects(value)


@pytest.mark.parametrize("factory, expected, effort", AGENT_CASES)
@pytest.mark.parametrize("stop_reason", ["end_turn", "refusal"])
async def test_anthropic_native_output(monkeypatch, factory, expected, effort, stop_reason):
    """Check wire parameters, mixed content, and refusals across every agent."""
    settings = make_settings(anthropic_model="claude-sonnet-5-5")
    monkeypatch.setattr(llm, "get_settings", lambda: settings)
    requests = []
    # Split on a JSON whitespace boundary: the wrapper may join text blocks with newlines.
    first, rest = json.dumps(expected.model_dump(), indent=2).split("\n", 1)

    def respond(request):
        body = json.loads(request.content)
        requests.append(body)
        return httpx.Response(
            200,
            json={
                "id": "msg_offline_test",
                "type": "message",
                "role": "assistant",
                "model": body["model"],
                "content": [
                    {"type": "thinking", "thinking": "Check the context.", "signature": "test"},
                    {"type": "text", "text": first},
                    {"type": "text", "text": rest},
                ],
                "stop_reason": stop_reason,
                "stop_sequence": None,
                "usage": {"input_tokens": 20, "output_tokens": 40},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http_client:
        async with AsyncAnthropic(api_key="test-api-key", http_client=http_client) as client:
            provider = AnthropicProvider(anthropic_client=client)

            def offline_provider(*, api_key):
                assert api_key == settings.anthropic_api_key
                return provider

            monkeypatch.setattr(llm, "AnthropicProvider", offline_provider)
            agent = factory(repo_context="Offline test repository")
            if stop_reason == "refusal":
                # Even schema-valid text must never be accepted when the model refuses.
                with pytest.raises(ContentFilterError):
                    await agent.run("Respond to this GitHub request.")
            else:
                result = await agent.run("Respond to this GitHub request.")
                assert isinstance(result.output, type(expected))
                assert result.output == expected

    assert len(requests) == 1
    body = requests[0]
    assert body["model"] == "claude-sonnet-5-5"
    assert body["output_config"]["effort"] == effort
    output_format = body["output_config"]["format"]
    assert output_format["type"] == "json_schema"
    assert_closed_objects(output_format["schema"])
    assert body["max_tokens"] >= 16000
    for unsupported in ("temperature", "top_p", "top_k", "thinking", "tools", "tool_choice"):
        assert unsupported not in body
    assert body["messages"][-1]["role"] == "user"


def test_default_anthropic_model(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    assert make_settings().anthropic_model == "claude-sonnet-5-5"


def test_anthropic_model_environment_override(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_MODEL", "operator-selected-model")
    assert make_settings().anthropic_model == "operator-selected-model"
