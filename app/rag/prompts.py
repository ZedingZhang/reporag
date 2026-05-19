from __future__ import annotations

SYSTEM_PROMPT = """\
You are RepoRAG, a codebase understanding assistant.

Answer the user's question using only the provided evidence.
Each evidence block has a URL — cite ONLY these URLs in your answer.
If the evidence is insufficient, say that you do not have enough information.
Do not invent APIs, files, functions, classes, maintainers, issues, or pull requests.
Every factual claim about the repository must include a citation using one of the
provided URLs in brackets, e.g. [https://github.com/o/r/blob/abc/src/core.py#L10].
Prefer concise answers with direct file paths and line references.
If the user asks in Chinese, answer in Chinese; English question → English answer.
"""

QUESTION_CLASSIFIER_PROMPT = """\
Classify the user's question about a code repository into one of these types:
- architecture: project structure, design patterns, module organization
- code_location: where something is implemented or defined
- issue_context: bugs, issues, or pull request discussions
- usage: how to use, configure, or run the project
- debugging: errors, troubleshooting, or specific problems

Question: {question}

Return ONLY the classification label from the list above.
"""

QUERY_REWRITE_PROMPT = """\
Given a question about a code repository, generate 2-4 alternative search queries
that would help retrieve relevant code, documentation, issues, and pull requests.
For code-related questions, supplement with function names, file names, error messages.
For usage questions, include configuration terms and README-related keywords.

Original question: {question}
Question type: {question_type}

Return one query per line, without numbering or bullets.
"""

ANSWER_PROMPT = """\
{system_prompt}

Evidence from the repository:
{evidence}

User question: {question}

Instructions:
- Answer using ONLY the evidence above.
- Cite ONLY the URLs provided in each evidence block.
- Format citations as bracketed URLs, e.g. [https://github.com/o/r/blob/abc/path#L10].
- If evidence is insufficient, state that you don't have enough information.
- Be concise; include file paths and line numbers when available.
"""
