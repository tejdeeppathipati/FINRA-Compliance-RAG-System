from app.retrieval.rank_fusion import RankedItem, reciprocal_rank_fusion


def test_rrf_rewards_items_found_by_both_retrievers() -> None:
    vector = [RankedItem("a", "A"), RankedItem("b", "B")]
    keyword = [RankedItem("b", "B"), RankedItem("c", "C")]

    fused = reciprocal_rank_fusion([vector, keyword], rrf_k=60)

    assert fused[0][0] == "B"
    assert [value for value, _ in fused] == ["B", "A", "C"]


def test_rrf_rejects_invalid_constant() -> None:
    try:
        reciprocal_rank_fusion([], rrf_k=0)
    except ValueError as error:
        assert str(error) == "rrf_k must be positive"
    else:
        raise AssertionError("Expected ValueError")

