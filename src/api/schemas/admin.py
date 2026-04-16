from pydantic import BaseModel


class AdminTaskActionResponse(BaseModel):
    task_id: str
    task_status: str
    paper_status: str


class BatchStatusResponse(BaseModel):
    batch_id: str
    total: int
    completed: int
    failed: int
