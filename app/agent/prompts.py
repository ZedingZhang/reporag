from __future__ import annotations

SYSTEM_PROMPT = """\
You are a repository maintenance planning agent.
You must use only the provided repository evidence. Do not invent file paths.
"""

TASK_CLASSIFIER_PROMPT = """\
Classify this repository maintenance task into one of:
- bugfix
- test_failure
- refactor
- docs
- question

Task: {task}

Return ONLY the classification label.
"""

PLANNER_PROMPT = """\
You are a repository maintenance planning agent.
You must use only the provided repository evidence. Do not invent file paths.

Task:
{task}

Repository evidence:
{evidence}

Return JSON with these keys:
- task_type: one of bugfix, test_failure, refactor, docs, question
- summary: one-sentence summary of the plan
- steps: list of steps, each with:
    goal, files (list of paths), evidence_urls (list of URLs), risk_level (low/medium/high),
    requires_approval (true/false)
- suggested_tests: list of test commands or file paths
- uncertainty: brief note on what is unclear or missing
"""

SUMMARIZER_PROMPT = """\
Summarize this agent run for a developer.

Task: {task}
Mode: {mode}
Task type: {task_type}
Plan: {plan}
Status: {status}
Errors: {errors}

Include:
- what was requested
- what context was used
- proposed plan
- remaining risks and next steps

Be concise.
"""
