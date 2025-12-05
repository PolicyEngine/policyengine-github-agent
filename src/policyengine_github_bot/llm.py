"""LLM integration for generating responses using pydantic-ai."""

import logfire
from pydantic_ai import Agent

from policyengine_github_bot.config import get_settings
from policyengine_github_bot.models import (
    GitHubIssue,
    GitHubPullRequest,
    IssueResponse,
    PRReReviewResponse,
    PRReviewResponse,
)

# Instrument pydantic-ai with logfire for tracing LLM calls
logfire.instrument_pydantic_ai()

BASE_SYSTEM_PROMPT = """You are PolicyEngine's GitHub bot.

Be concise. Avoid unnecessary preamble or filler.
Use sentence case everywhere (not Title Case).
Be friendly but professional. Don't be overly formal.
If you need more information, ask specific clarifying questions."""


def get_issue_agent(repo_context: str | None = None) -> Agent[None, IssueResponse]:
    """Create an agent for responding to GitHub issues."""
    settings = get_settings()

    system = BASE_SYSTEM_PROMPT + "\n\nYou respond to issues with helpful, accurate information."
    if repo_context:
        system += f"\n\nRepository context:\n{repo_context}"

    return Agent(
        f"anthropic:{settings.anthropic_model}",
        output_type=IssueResponse,
        system_prompt=system,
    )


def get_pr_review_agent(repo_context: str | None = None) -> Agent[None, PRReviewResponse]:
    """Create an agent for reviewing pull requests."""
    settings = get_settings()

    system = (
        BASE_SYSTEM_PROMPT
        + """

You are a thorough, forensic code reviewer. Your job is to catch issues before they hit production.

## Review methodology

1. **Understand intent**: What is this PR trying to do? Does it match the description?

2. **Logic review**: Trace through the code mentally. Does it actually work?
   - Check conditional logic carefully (off-by-one, boundary conditions, negation errors)
   - Verify loops terminate and handle empty/single/many cases
   - Check null/undefined handling and type coercion
   - Look for race conditions or state management issues

3. **Edge cases**: Think adversarially. What inputs could break this?
   - Empty inputs, None/null values, negative numbers, zero
   - Very large inputs, unicode, special characters
   - Concurrent access, network failures, timeouts
   - What happens if dependencies fail?

4. **Validate assumptions**: The code makes assumptions. Are they valid?
   - Are magic numbers/strings explained and correct?
   - Do hardcoded values match documentation/specs?
   - Are external API contracts being followed correctly?

5. **Red-team the code**: How could this be exploited or misused?
   - Security: injection, auth bypass, data exposure, SSRF
   - Reliability: what fails silently? What could cause data loss?
   - Performance: O(n²) loops, memory leaks, unbounded growth

6. **Data quality** (for code using data/microdata):
   - Are data assumptions valid? (column names, types, ranges, distributions)
   - What if data has missing values, NaNs, infinities, or outliers?
   - Are weights handled correctly? Is the sample representative?
   - Do calculations make sense at individual AND aggregate levels?
   - Are results plausible? (sanity check: poverty rates, avg incomes, totals)
   - Is there data leakage or incorrect joins?

7. **Style and maintainability**:
   - Is the code clear and self-documenting?
   - Are names descriptive? Is there unnecessary complexity?
   - Could this be simpler while doing the same thing?

8. **Test coverage**: Are the changes tested? Are edge cases covered?

## Inline comments

You MUST provide inline comments on specific lines of code.
- Each comment needs: path (file path), line (line number in the new file), body (your comment)
- The line number should be from the RIGHT side of the diff (the new version)
- Look at @@ hunk headers for line numbers (e.g. @@ -10,5 +12,7 @@ means new lines start at 12)
- Be specific: "This will fail if X is empty" not "Consider edge cases"

## Approval decisions

- **APPROVE**: Code is correct, handles edge cases, and is ready to merge. Use sparingly - \
only when you're confident there are no issues.
- **REQUEST_CHANGES**: Use when you find:
  - Bugs or logic errors that will cause incorrect behaviour
  - Missing error handling that could cause crashes/failures
  - Security vulnerabilities
  - Missing tests for new functionality
  - Incorrect assumptions or hardcoded values that are wrong
  Don't be afraid to request changes - it's better to catch issues now than in production.
- **COMMENT**: Suggestions, questions, or minor improvements that aren't blocking."""
    )

    if repo_context:
        system += f"\n\nRepository context:\n{repo_context}"

    return Agent(
        f"anthropic:{settings.anthropic_model}",
        output_type=PRReviewResponse,
        system_prompt=system,
    )


async def generate_issue_response(
    issue: GitHubIssue,
    repo_context: str | None = None,
    conversation: list[dict] | None = None,
) -> str:
    """Generate a response to a GitHub issue using Claude."""
    logfire.info(
        "Generating issue response",
        issue_number=issue.number,
        issue_title=issue.title,
        has_repo_context=repo_context is not None,
        conversation_length=len(conversation) if conversation else 0,
    )

    agent = get_issue_agent(repo_context)

    prompt = f"""Please respond to this GitHub issue:

Title: {issue.title}

Body:
{issue.body or "(no body provided)"}"""

    if conversation:
        prompt += "\n\nConversation history:\n"
        for comment in conversation:
            role = "You" if comment["is_bot"] else comment["author"]
            prompt += f"\n{role}:\n{comment['body']}\n"

    prompt += "\n\nProvide a helpful response."

    result = await agent.run(prompt)

    logfire.info(
        "Generated response",
        issue_number=issue.number,
        response_length=len(result.output.content),
    )

    return result.output.content


async def generate_pr_review(
    pr: GitHubPullRequest,
    diff: str,
    files_changed: list[dict],
    repo_context: str | None = None,
) -> PRReviewResponse:
    """Generate a PR review using Claude."""
    logfire.info(
        "Generating PR review",
        pr_number=pr.number,
        pr_title=pr.title,
        files_changed=len(files_changed),
        diff_length=len(diff),
        has_repo_context=repo_context is not None,
    )

    agent = get_pr_review_agent(repo_context)

    files_summary = "\n".join(
        f"- {f['filename']} (+{f.get('additions', 0)}/-{f.get('deletions', 0)})"
        for f in files_changed
    )

    prompt = f"""Please review this pull request:

Title: {pr.title}

Description:
{pr.body or "(no description provided)"}

Files changed:
{files_summary}

Diff (with line numbers from @@ headers showing new file line positions):
```diff
{diff}
```

Provide a thorough but concise review. Include inline comments on specific lines where you have \
feedback. Use the line numbers from the RIGHT side of the diff (the + lines in the new version). \
Each inline comment should reference a specific file path and line number."""

    result = await agent.run(prompt)

    logfire.info(
        "Generated PR review",
        pr_number=pr.number,
        approval=result.output.approval,
        comment_count=len(result.output.comments),
    )

    return result.output


def get_pr_rereview_agent(
    repo_context: str | None = None,
) -> Agent[None, PRReReviewResponse]:
    """Create an agent for re-reviewing pull requests."""
    settings = get_settings()

    system = (
        BASE_SYSTEM_PROMPT
        + """

You are re-reviewing a pull request after changes were made. Your job is to:
1. Check if previous review comments have been addressed
2. Decide what to do with each open thread
3. Only add NEW comments if there are genuinely new issues

For each open thread, you must decide:
- RESOLVE: The issue has been fixed. Use this when the code change addresses the concern.
- REPLY: The issue is NOT fixed or needs follow-up. Provide a reply explaining why.

IMPORTANT: Do NOT post a whole new review unless there are genuinely NEW issues to comment on.
- If all threads are resolved and no new issues, just resolve threads (no new_comments needed)
- If threads need replies, reply to them (no new_comments needed)
- Only use new_comments for issues on lines NOT already covered by existing threads

Be concise in replies. Examples:
- "Fixed, thanks!"
- "This still needs attention - the edge case for X isn't handled."
- "Good improvement, but consider also handling Y."
"""
    )

    if repo_context:
        system += f"\n\nRepository context:\n{repo_context}"

    return Agent(
        f"anthropic:{settings.anthropic_model}",
        output_type=PRReReviewResponse,
        system_prompt=system,
    )


async def generate_pr_rereview(
    pr: GitHubPullRequest,
    diff: str,
    files_changed: list[dict],
    open_threads: list[dict],
    rereview_context: str,
    repo_context: str | None = None,
) -> PRReReviewResponse:
    """Generate a re-review response for a PR."""
    logfire.info(
        "Generating PR re-review",
        pr_number=pr.number,
        pr_title=pr.title,
        open_thread_count=len(open_threads),
    )

    agent = get_pr_rereview_agent(repo_context)

    files_summary = "\n".join(
        f"- {f['filename']} (+{f.get('additions', 0)}/-{f.get('deletions', 0)})"
        for f in files_changed
    )

    # Build thread list for the prompt
    threads_text = ""
    for i, thread in enumerate(open_threads):
        comments = thread.get("comments", {}).get("nodes", [])
        if comments:
            first = comments[0]
            author = first.get("author", {}).get("login", "unknown")
            body = first.get("body", "(no body)")
            threads_text += f"\n[Thread {i}] by @{author}:\n{body}\n"

    prompt = f"""Re-review this pull request.

Title: {pr.title}

Description:
{pr.body or "(no description provided)"}

Files changed:
{files_summary}

Current diff:
```diff
{diff}
```

Context for this re-review:
{rereview_context}

Open threads that need your attention:
{threads_text}

For each thread above, decide whether to RESOLVE it (if fixed) or REPLY (if not fixed).
Only add new_comments if there are genuinely NEW issues not covered by existing threads."""

    result = await agent.run(prompt)

    logfire.info(
        "Generated PR re-review",
        pr_number=pr.number,
        thread_actions=len(result.output.thread_actions),
        new_comments=len(result.output.new_comments),
    )

    return result.output
