from pgvector.sqlalchemy import VECTOR
from sqlalchemy.dialects.postgresql import TSVECTOR

from app.db.models import EMBEDDING_DIMENSIONS, Base, Chunk, Document


def test_database_metadata_contains_expected_tables() -> None:
    assert set(Base.metadata.tables) == {
        "chunks",
        "documents",
        "evaluation_cases",
        "evaluation_results",
        "query_logs",
    }


def test_chunk_search_columns_have_expected_types() -> None:
    embedding_type = Chunk.__table__.c.embedding.type
    search_vector_type = Chunk.__table__.c.search_vector.type

    assert isinstance(embedding_type, VECTOR)
    assert embedding_type.dim == EMBEDDING_DIMENSIONS
    assert isinstance(search_vector_type, TSVECTOR)
    assert Chunk.__table__.c.search_vector.computed is not None


def test_documents_support_snapshot_and_chunking_variants() -> None:
    unique_constraints = {
        constraint.name: tuple(column.name for column in constraint.columns)
        for constraint in Document.__table__.constraints
        if constraint.name and hasattr(constraint, "columns")
    }

    assert unique_constraints["uq_documents_source_normalized_hash"] == (
        "source_id",
        "normalized_content_hash",
        "chunk_target_tokens",
        "chunk_overlap_tokens",
    )
    assert ("source_id",) not in unique_constraints.values()
    assert "latest_effective_date" in Document.__table__.c
    assert "effective_date" not in Document.__table__.c
