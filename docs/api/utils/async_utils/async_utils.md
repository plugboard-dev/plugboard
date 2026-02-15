# async_utils

The `async_utils` module provides utilities for working with asynchronous code in Plugboard. These utilities are particularly useful when you need to bridge between synchronous and asynchronous code, or when you want to gather results from multiple coroutines with better error handling.

## Functions

::: plugboard.utils.async_utils
    options:
      members:
      - run_coro_sync
      - gather_except

## Usage

### run_coro_sync

The [`run_coro_sync`][plugboard.utils.async_utils.run_coro_sync] function allows you to run an asynchronous coroutine from synchronous code. This is particularly useful in CLI applications, scripts, or when integrating async Plugboard components into synchronous workflows.

**Example:**

```python
from plugboard.utils import run_coro_sync
from plugboard.process import LocalProcess

async def run_my_process():
    process = LocalProcess(components=[...])
    await process.run()
    return process.state

# Run the async function from synchronous code
result = run_coro_sync(run_my_process())
```

**Key features:**

- Automatically detects if an event loop is already running
- If a loop is running, executes the coroutine in a separate thread with its own event loop
- If no loop exists, creates one and runs the coroutine directly
- Supports optional timeout parameter

**When to use:**

- In CLI entry points (as used in `plugboard process run`)
- In synchronous scripts that need to call async Plugboard APIs
- In test fixtures that need to run async setup/teardown from sync test runners
- When integrating Plugboard with synchronous frameworks or libraries

### gather_except

The [`gather_except`][plugboard.utils.async_utils.gather_except] function is similar to `asyncio.gather` but provides better error handling by collecting all exceptions that occur and raising them as an `ExceptionGroup`.

**Example:**

```python
from plugboard.utils import gather_except

async def fetch_data_a():
    # ... fetch data from source A
    return data_a

async def fetch_data_b():
    # ... fetch data from source B  
    return data_b

# Gather results from multiple coroutines
try:
    results = await gather_except(
        fetch_data_a(),
        fetch_data_b()
    )
    data_a, data_b = results
except ExceptionGroup as eg:
    # Handle all exceptions that occurred
    for exc in eg.exceptions:
        print(f"Error: {exc}")
```

**Key features:**

- Returns results if all coroutines succeed
- Raises an `ExceptionGroup` containing all exceptions if any coroutines fail
- All coroutines are awaited even if some fail (similar to `return_exceptions=True`)

**When to use:**

- When you need to run multiple independent operations in parallel
- When you want comprehensive error reporting from parallel operations
- In distributed process execution (as used in `RayProcess`)
- When connecting multiple components in parallel
