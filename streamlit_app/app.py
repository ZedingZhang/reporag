from __future__ import annotations

import os

import requests
import streamlit as st

API_BASE = os.environ.get("API_BASE", "http://api:8000")

st.set_page_config(page_title="RepoRAG", page_icon="", layout="wide")

st.title("RepoRAG")
st.markdown("### GitHub Repository RAG Assistant")

# --- Sidebar: Index a repo ---
st.sidebar.header("Index a Repository")
repo_url = st.sidebar.text_input(
    "GitHub Repository URL",
    placeholder="https://github.com/pallets/click",
)
col1, col2 = st.sidebar.columns(2)
with col1:
    include_issues = st.checkbox("Issues", value=True)
with col2:
    include_prs = st.checkbox("Pull Requests", value=True)

if st.sidebar.button("Index Repository", disabled=not repo_url):
    with st.sidebar:
        try:
            resp = requests.post(
                f"{API_BASE}/api/repos/index",
                json={
                    "repo_url": repo_url.strip(),
                    "include_issues": include_issues,
                    "include_pull_requests": include_prs,
                },
                timeout=30,
            )
            if resp.status_code == 200:
                data = resp.json()
                st.success(f"Indexing started!\n\nRepo ID: `{data['repo_id']}`")
            else:
                st.error(f"Failed: {resp.text}")
        except requests.ConnectionError:
            st.error(f"Cannot connect to API at {API_BASE}")

st.sidebar.divider()

# --- Sidebar: Select repo ---
st.sidebar.header("Select Repository")
try:
    resp = requests.get(f"{API_BASE}/api/repos", timeout=10)
    if resp.status_code == 200:
        repos = resp.json().get("repos", [])
        repo_options = {
            f"{r['owner']}/{r['name']} ({r['status']})": r["id"]
            for r in repos
        }
        if repo_options:
            selected_label = st.sidebar.selectbox(
                "Indexed Repositories",
                list(repo_options.keys()),
                key="selected_label",
            )
            selected_id = repo_options[selected_label]
            st.session_state["selected_repo_id"] = selected_id
        else:
            st.sidebar.info("No repositories indexed yet.")
            st.session_state.pop("selected_repo_id", None)
    else:
        st.sidebar.warning("API not available")
        st.session_state.pop("selected_repo_id", None)
except requests.ConnectionError:
    st.sidebar.warning(f"Cannot connect to API at {API_BASE}")
    st.session_state.pop("selected_repo_id", None)

# --- Main: Q&A ---
repo_id = st.session_state.get("selected_repo_id")
question = st.text_input(
    "Ask a question about the repository...",
    disabled=not repo_id,
    placeholder="e.g., Where is authentication implemented?",
)

col1, col2, col3 = st.columns([1, 1, 6])
with col1:
    ask = st.button("Ask", disabled=not (repo_id and question))
with col2:
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
                color = {"high": "green", "medium": "orange", "low": "red"}.get(confidence, "grey")
                st.caption(f"Confidence: :{color}[{confidence}]")

                if data.get("citations"):
                    st.markdown("### Citations")
                    for i, cit in enumerate(data["citations"], 1):
                        loc = ""
                        if cit.get("path"):
                            loc = f" — `{cit['path']}`"
                            if cit.get("line_start"):
                                loc += f":L{cit['line_start']}"
                                if cit.get("line_end") and cit["line_end"] != cit["line_start"]:
                                    loc += f"-L{cit['line_end']}"
                        st.markdown(f"{i}. [{cit['title']}]({cit['url']}){loc}")

                if data.get("retrieved_chunks"):
                    n_chunks = len(data['retrieved_chunks'])
                    with st.expander(f"Retrieved Chunks ({n_chunks})"):
                        for i, chunk in enumerate(data["retrieved_chunks"], 1):
                            ctype = chunk.get('chunk_type', '?')
                            cscore = chunk.get('score', 0)
                            st.markdown(
                                f"**Chunk {i}** ({ctype}, score: {cscore:.4f})"
                            )
                            if chunk.get("path"):
                                st.caption(f"`{chunk['path']}`")
                            st.code(chunk.get("content", "")[:800], language="text")
            else:
                st.error(f"Error: {resp.text}")
        except requests.ConnectionError:
            st.error(f"Cannot connect to API at {API_BASE}")
        except requests.Timeout:
            st.error("Request timed out — generation is taking too long.")
