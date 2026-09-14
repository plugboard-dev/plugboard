::: plugboard.process
    options:
      members:
      - Process
      - LocalProcess
      - RayProcess

`RayProcess` runs concurrent lifecycle calls in an `asyncio.TaskGroup`. When a
call fails, it cancels sibling waits, requests cancellation of the corresponding
Ray calls, and raises an `ExceptionGroup` containing the failures observed before
cancellation. It does not wait for every component to fail or finish normally.

Remote cancellation is cooperative: actor methods must yield to their event loop
to be interrupted. Remote cleanup may still be running when the exception is
raised, and local component attributes may reflect an interrupted operation.
Attribute refreshes during error propagation are limited to five seconds; refresh
errors are logged so the original failure is preserved.
