"""Example: how to create a custom worker for Merkaba.

Workers execute tasks dispatched by the supervisor. Create a worker by
subclassing Worker and registering it for a task type.

Usage in your private package:
    # my_package/workers/my_worker.py
    from merkaba.orchestration.workers import Worker, WorkerResult, register_worker

    class MyWorker(Worker):
        def execute(self, task):
            ...

    register_worker("my_task_type", MyWorker)
"""

from merkaba.orchestration.workers import Worker, WorkerResult, register_worker


class CustomWorker(Worker):
    """A minimal custom worker example.

    The supervisor dispatches tasks to workers based on task_type.
    Register your worker for a task_type and the supervisor will
    automatically route matching tasks to it.
    """

    def execute(self, task: dict) -> WorkerResult:
        prompt = task.get("prompt", "")

        # Use self._ask_llm() for convenient LLM access (returns str)
        response = self._ask_llm(prompt)

        return WorkerResult(
            success=True,
            output={"response": response},
            facts_learned=[{"key": "example", "value": "Worker executed successfully"}],
        )


# Register so the supervisor can dispatch "custom" tasks to this worker
register_worker("custom", CustomWorker)
