from __future__ import annotations

import os

import requests
import streamlit as st

API_BASE = os.environ.get("API_BASE", "http://api:8000")

st.set_page_config(page_title="RepoRAG", page_icon="", layout="wide")

st.title("RepoRAG")
tab_main, tab_agent = st.tabs(["Q&A", "Agent"])


def _get_repo_list() -> list[dict]:
    try:
        resp = requests.get(f"{API_BASE}/api/repos", timeout=10)
        if resp.status_code == 200:
            return resp.json().get("repos", [])
    except requests.ConnectionError:
        pass
    return []


def _select_repo():
    repos = _get_repo_list()
    options = {f"{r['owner']}/{r['name']} ({r['status']})": r["id"] for r in repos}
    if options:
        label = st.sidebar.selectbox("Indexed Repositories", list(options.keys()))
        st.session_state["selected_repo_id"] = options[label]
    else:
        st.sidebar.info("No repositories indexed yet.")
        st.session_state.pop("selected_repo_id", None)


# ========== Q&A Tab ==========
with tab_main:
    repo_id = st.session_state.get("selected_repo_id")
    question = st.text_input(
        "Ask a question about the repository...",
        disabled=not repo_id,
        placeholder="e.g., Where is authentication implemented?",
        key="qa_question",
    )
    c1, c2, _ = st.columns([1, 1, 6])
    with c1:
        ask = st.button("Ask", disabled=not (repo_id and question))
    with c2:
        top_k = st.selectbox("Top K", [4, 8, 16], index=1, label_visibility="collapsed")

    if ask and repo_id and question:
        with st.spinner("Searching and generating answer..."):
            try:
                resp = requests.post(
                    f"{API_BASE}/api/chat",
                    json={"repo_id": repo_id, "question": question, "top_k": top_k},
                    timeout=120,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    st.markdown("### Answer")
                    st.markdown(data["answer"])
                    confidence = data.get("confidence", "low")
                    color_map = {"high": "green", "medium": "orange", "low": "red"}
                    st.caption(f"Confidence: :{color_map.get(confidence, 'grey')}[{confidence}]")
                    if data.get("citations"):
                        st.markdown("### Citations")
                        for i, cit in enumerate(data["citations"], 1):
                            loc = ""
                            if cit.get("path"):
                                loc = f" — `{cit['path']}`"
                                ls = cit.get("line_start")
                                le = cit.get("line_end")
                                if ls:
                                    loc += f":L{ls}"
                                    if le and le != ls:
                                        loc += f"-L{le}"
                            st.markdown(f"{i}. [{cit['title']}]({cit['url']}){loc}")
                    if data.get("retrieved_chunks"):
                        n = len(data["retrieved_chunks"])
                        with st.expander(f"Retrieved Chunks ({n})"):
                            for i, chunk in enumerate(data["retrieved_chunks"], 1):
                                ctype = chunk.get("chunk_type", "?")
                                cscore = chunk.get("score", 0)
                                st.markdown(f"**Chunk {i}** ({ctype}, score: {cscore:.4f})")
                                if chunk.get("path"):
                                    st.caption(f"`{chunk['path']}`")
                                st.code(chunk.get("content", "")[:800], language="text")
                else:
                    st.error(f"Error: {resp.text}")
            except requests.ConnectionError:
                st.error(f"Cannot connect to API at {API_BASE}")

# ========== Agent Tab ==========
with tab_agent:
    repo_id = st.session_state.get("selected_repo_id")
    st.subheader("Agent Run")

    task = st.text_input(
        "Task description",
        disabled=not repo_id,
        placeholder="e.g., Find citation validation and propose tests.",
        key="agent_task",
    )
    mode = st.selectbox("Mode", ["plan_only", "propose_patch", "execute_after_approval"], index=0)
    c1, c2, _ = st.columns([1, 1, 6])
    with c1:
        run_agent = st.button("Run Agent", disabled=not (repo_id and task))
    with c2:
        agent_top_k = st.selectbox("K", [4, 8, 16], index=1, key="agent_topk",
                                   label_visibility="collapsed")

    if run_agent and repo_id and task:
        with st.spinner("Agent is planning..."):
            try:
                resp = requests.post(
                    f"{API_BASE}/api/agent/runs",
                    json={"repo_id": repo_id, "task": task, "mode": mode, "top_k": agent_top_k},
                    timeout=180,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    st.session_state["agent_run_id"] = data["run_id"]
                    st.success(f"Run created: `{data['run_id']}`")
                else:
                    st.error(f"Failed: {resp.text}")
            except requests.ConnectionError:
                st.error(f"Cannot connect to API at {API_BASE}")

    run_id = st.session_state.get("agent_run_id")
    if run_id:
        if st.button("Refresh Run"):
            pass

        try:
            resp = requests.get(f"{API_BASE}/api/agent/runs/{run_id}", timeout=30)
            if resp.status_code == 200:
                run = resp.json()
                st.markdown(f"**Status:** `{run['status']}` | **Mode:** `{run['mode']}`")
                st.markdown(f"**Task:** {run['task']}")

                if run.get("plan") and run["plan"].get("plan"):
                    st.markdown("### Plan")
                    for i, step in enumerate(run["plan"]["plan"], 1):
                        risk = step.get("risk_level", "?")
                        files = ", ".join(step.get("files", [])[:5]) or "(none)"
                        st.markdown(
                            f"**{i}.** {step.get('goal', '?')} "
                            f"(risk: `{risk}`, files: `{files}`)"
                        )

                if run.get("result"):
                    result = run["result"]
                    patch = result.get("proposed_patch", "")
                    if patch and patch.strip():
                        st.markdown("### Proposed Patch")
                        st.code(patch[:4000], language="diff")

                if run.get("approvals"):
                    st.markdown("### Approvals")
                    for appr in run["approvals"]:
                        st.markdown(
                            f"- `{appr['approval_id']}`: **{appr['action_type']}** "
                            f"({appr['risk_level']}, {appr['status']})"
                        )
                        if appr["status"] == "pending":
                            aid = appr['approval_id']
                            short_id = aid[:8]
                            base = f"{API_BASE}/api/agent/approvals/{aid}/resolve"
                            c1, c2, c3 = st.columns([1, 1, 6])
                            with c1:
                                if st.button(f"Approve {short_id}", key=f"a_{aid}"):
                                    r = requests.post(
                                        base,
                                        json={"decision": "approved", "comment": ""},
                                        timeout=10,
                                    )
                                    if r.status_code == 200:
                                        st.rerun()
                            with c2:
                                if st.button(f"Reject {short_id}", key=f"r_{aid}"):
                                    r = requests.post(
                                        base,
                                        json={"decision": "rejected",
                                              "comment": "Rejected via UI"},
                                        timeout=10,
                                    )
                                    if r.status_code == 200:
                                        st.rerun()

                if run.get("steps"):
                    with st.expander(f"Steps ({len(run['steps'])})"):
                        for s in run["steps"]:
                            st.markdown(
                                f"- `{s['node_name']}` ({s['status']}, "
                                f"{s.get('latency_ms', 0) or 0}ms)"
                            )

            elif resp.status_code != 200:
                st.warning(f"Run not found: {resp.status_code}")
        except requests.ConnectionError:
            st.error(f"Cannot connect to API at {API_BASE}")


# ========== Sidebar ==========
with st.sidebar:
    st.header("Index a Repository")
    repo_url = st.text_input(
        "GitHub Repository URL",
        placeholder="https://github.com/pallets/click",
        key="sidebar_repo_url",
    )
    c1, c2 = st.columns(2)
    with c1:
        include_issues = st.checkbox("Issues", value=True)
    with c2:
        include_prs = st.checkbox("Pull Requests", value=True)
    if st.button("Index Repository", disabled=not repo_url):
        try:
            resp = requests.post(
                f"{API_BASE}/api/repos/index",
                json={
                    "repo_url": repo_url.strip(),
                    "include_issues": include_issues,
                    "include_pull_requests": include_prs,
                }, timeout=30,
            )
            if resp.status_code == 200:
                d = resp.json()
                st.success(f"Indexing started! Repo ID: `{d['repo_id']}`")
            else:
                st.error(f"Failed: {resp.text}")
        except requests.ConnectionError:
            st.error(f"Cannot connect to API at {API_BASE}")
    st.divider()
    _select_repo()
