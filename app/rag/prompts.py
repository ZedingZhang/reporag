from __future__ import annotations

SYSTEM_PROMPT = """\
You are RepoRAG, a codebase understanding assistant.

Answer the user's question using only the provided evidence.
If the evidence is insufficient, say that you do not have enough information.
Do not invent APIs, files, functions, classes, maintainers, issues, or pull requests.
Every factual claim about the repository must be supported by a citation.
Prefer concise answers with direct file paths and line references.
If the user asks in Chinese, answer in Chinese. If the user asks in English, answer in English.
"""

QUESTION_CLASSIFIER_PROMPT = """\
Classify the user's question about a code repository into one of these types:
- architecture: questions about project structure, design patterns, module organization
- code_location: questions about where something is implemented or defined
- issue_context: questions about bugs, issues, or pull request discussions
- usage: questions about how to use, configure, or run the project
- debugging: questions about errors, troubleshooting, or specific problems

Question: {question}

Return ONLY the classification label from the list above.
"""

QUERY_REWRITE_PROMPT = """\
Given a user question about a code repository, generate 2-4 alternative search queries
that would help retrieve relevant code, documentation, issues, and pull requests.

For code-related questions, supplement with keywords like function names, file names, error messages.
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
- Include citations using the [url] format after each factual claim.
- If evidence is insufficient, state clearly that you don't have enough information.
- Be concise and specific about file paths and line numbers.
"""
