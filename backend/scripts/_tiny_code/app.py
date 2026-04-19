from fastapi import FastAPI

app = FastAPI()


@app.get("/todos")
def list_todos():
    return []


@app.post("/todos")
def create_todo(item: dict):
    return item
