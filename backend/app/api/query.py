import time
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import QueryLog
from app.db.session import get_db_session
from app.generation.abstention import should_abstain_for_scope
from app.generation.answer import build_grounded_response
from app.ingestion.embed import EmbeddingProviderError, embed_text
from app.retrieval.search import hybrid_search, keyword_search, vector_search
from app.schemas.query import QueryRequest, QueryResponse

router = APIRouter(tags=["query"])


@router.post("/query", response_model=QueryResponse)
def query(
    request: QueryRequest,
    session: Session = Depends(get_db_session),  # noqa: B008
) -> QueryResponse:
    started = time.perf_counter()
    try:
        query_embedding = None
        if should_abstain_for_scope(request.question):
            passages = []
        else:
            if request.retrieval_mode in {"vector", "hybrid"} and get_settings().openai_api_key:
                query_embedding = embed_text(request.question)
            if request.retrieval_mode == "keyword":
                passages = keyword_search(session, request.question, limit=request.top_k)
            elif request.retrieval_mode == "vector":
                if query_embedding is None:
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail="Vector retrieval requires a configured OPENAI_API_KEY.",
                    )
                passages = vector_search(session, query_embedding, limit=request.top_k)
            else:
                passages = hybrid_search(
                    session,
                    request.question,
                    limit=request.top_k,
                    vector_embedding=query_embedding,
                )
    except EmbeddingProviderError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Embedding provider unavailable: {error}",
        ) from error
    except SQLAlchemyError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is unavailable. Start PostgreSQL and apply migrations.",
        ) from error
    configuration = f"{request.retrieval_mode}-top-{request.top_k}"
    if request.retrieval_mode == "hybrid" and query_embedding is None:
        configuration = f"hybrid-keyword-only-top-{request.top_k}"
    response = build_grounded_response(
        passages,
        retrieval_configuration=configuration,
        top_k=request.top_k,
    )
    try:
        session.add(
            QueryLog(
                question=request.question,
                answer=response.answer,
                abstained=response.abstained,
                retrieved_chunk_ids=[UUID(chunk.chunk_id) for chunk in response.retrieved_chunks],
                retrieval_configuration={
                    "mode": request.retrieval_mode,
                    "top_k": request.top_k,
                    "configuration": configuration,
                },
                prompt_version=response.prompt_version,
                latency_ms=max(0, int((time.perf_counter() - started) * 1000)),
            )
        )
        session.commit()
    except SQLAlchemyError:
        session.rollback()
    return response
