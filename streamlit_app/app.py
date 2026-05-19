from __future__ import annotations

import streamlit as st

st.set_page_config(page_title="RepoRAG", page_icon="", layout="wide")

st.title("RepoRAG")
st.markdown("### GitHub Repository RAG Assistant")

st.sidebar.header("Index a Repository")
repo_url = st.sidebar.text_input(
    "GitHub Repository URL",
    placeholder="https://github.com/pallets/click",
)
if st.sidebar.button("Index Repository", disabled=not repo_url):
    st.sidebar.info("Indexing not yet implemented. Coming in Phase 2.")

st.sidebar.divider()
st.sidebar.header("Select Repository")
st.sidebar.selectbox("Indexed Repositories", ["(none)"])

question = st.text_input("Ask a question about the repository...")
if st.button("Ask") and question:
    st.info("Q&A not yet implemented. Coming in Phase 4.")
