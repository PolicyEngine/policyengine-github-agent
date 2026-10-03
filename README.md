# PolicyEngine GitHub Bot

GitHub App that automatically responds to issues and reviews PRs on PolicyEngine repositories using Claude.

## Setup

1. Create a GitHub App with the required permissions (issues: read/write)
2. Copy `.env.example` to `.env` and fill in your credentials
3. Run locally: `uv run uvicorn policyengine_github_bot.main:app --reload`

The Anthropic API helpers for issue replies, PR reviews, and re-reviews default to
`claude-sonnet-5-5`. Issue replies use low effort; reviews use medium effort.
All three use adaptive thinking, native structured output, and a 16,000-token
limit, including thinking tokens.
`ANTHROPIC_MODEL` (including values in `.env` or Cloud Run) overrides this default;
overrides need native structured output and effort support in both Claude and the
installed PydanticAI model profile. Webhook PR reviews and engineering tasks run
through Claude Code, which selects its model independently.

## Deployment

Deploy to Cloud Run:

```bash
gcloud run deploy policyengine-github-bot \
  --source . \
  --set-env-vars "GITHUB_APP_ID=...,ANTHROPIC_API_KEY=..." \
  --set-secrets "GITHUB_PRIVATE_KEY=github-private-key:latest,GITHUB_WEBHOOK_SECRET=github-webhook-secret:latest"
```
