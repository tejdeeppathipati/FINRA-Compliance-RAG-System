from fastapi import APIRouter, HTTPException, status

from app.schemas.query import QueryRequest, QueryResponse

router = APIRouter(tags=["query"])


@router.post("/query", response_model=QueryResponse)
def query(_: QueryRequest) -> QueryResponse:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Query pipeline is not implemented in the baseline.",
    )

