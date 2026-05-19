from __future__ import annotations

from app.retrieval.hybrid import _reciprocal_rank_fusion
from app.retrieval.vector import ScoredChunk


def _make_chunk(
    chunk_id: str, chunk_type: str = "code_symbol", score: float = 0.0,
) -> ScoredChunk:
    return ScoredChunk(
        chunk_id=chunk_id, content=f"Content of {chunk_id}",
        path=f"/path/{chunk_id}", chunk_type=chunk_type, score=score,
    )


class TestReciprocalRankFusion:
    def test_rrf_combines_rankings(self) -> None:
        a = [
            _make_chunk("a1", score=0.9),
            _make_chunk("a2", score=0.8),
            _make_chunk("a3", score=0.7),
        ]
        b = [
            _make_chunk("a2", score=0.95),
            _make_chunk("b1", score=0.85),
            _make_chunk("a3", score=0.75),
        ]
        fused = _reciprocal_rank_fusion(a, b, k=60)
        assert len(fused) == 4
        scores = {c.chunk_id: c.score for c in fused}
        assert scores["a2"] > scores["a1"]
        assert "b1" in scores
        fused_by_id = {c.chunk_id: c for c in fused}
        assert fused_by_id["a2"].retrieval_sources == {"vector", "keyword"}
        assert fused_by_id["a1"].retrieval_sources == {"vector"}
        assert fused_by_id["b1"].retrieval_sources == {"keyword"}

    def test_rrf_empty_lists(self) -> None:
        fused = _reciprocal_rank_fusion([], [], k=60)
        assert len(fused) == 0

    def test_rrf_single_list(self) -> None:
        a = [_make_chunk("a1"), _make_chunk("a2"), _make_chunk("a3")]
        fused = _reciprocal_rank_fusion(a, [], k=60)
        assert len(fused) == 3
        assert fused[0].chunk_id == "a1"

    def test_rrf_stable_ordering(self) -> None:
        a = [_make_chunk(f"a{i}") for i in range(5)]
        b = [_make_chunk(f"a{i}") for i in range(5)]
        fused1 = _reciprocal_rank_fusion(a, b, k=60)
        fused2 = _reciprocal_rank_fusion(a, b, k=60)
        ids1 = [c.chunk_id for c in fused1]
        ids2 = [c.chunk_id for c in fused2]
        assert ids1 == ids2

    def test_rrf_with_type_weights(self) -> None:
        a = [
            _make_chunk("md1", chunk_type="markdown_section"),
            _make_chunk("code1", chunk_type="code_symbol"),
        ]
        b = [
            _make_chunk("code1", chunk_type="code_symbol"),
            _make_chunk("md1", chunk_type="markdown_section"),
        ]
        code_heavy = _reciprocal_rank_fusion(
            a, b, k=60,
            weights={"markdown_section": 0.5, "code_symbol": 1.5},
        )
        code_chunk = next(c for c in code_heavy if c.chunk_id == "code1")
        md_chunk = next(c for c in code_heavy if c.chunk_id == "md1")
        assert code_chunk.score > md_chunk.score


class TestScoredChunk:
    def test_scored_chunk_fields(self) -> None:
        chunk = _make_chunk("test1", chunk_type="markdown_section", score=0.95)
        assert chunk.chunk_id == "test1"
        assert chunk.chunk_type == "markdown_section"
        assert chunk.score == 0.95
        assert chunk.content == "Content of test1"
        assert chunk.path == "/path/test1"
