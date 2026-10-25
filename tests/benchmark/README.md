# Process benchmarks

Run the suite from the repository root:

```sh
uv run pytest tests/benchmark --benchmark-only --benchmark-save=process
```

Use `--benchmark-disable` to execute each case once, including correctness checks
and cleanup. Filter cases with `-k`, for example `-k 'run and fan_in-16'`.
The existing benchmark workflow runs this suite on both the PR and main branch.
New case IDs have no historical baseline until they are present on both branches.

Each workload uses `LocalProcess`, `AsyncioConnector`, the default dictionary state
backend, and the production `Component.run` loop. Components do minimal integer
work so timings emphasize framework scheduling, channel operations, producer
status checks, and state updates rather than application computation or external
services. Each source emits 1,000 integers.

| Graph | Scale | Cost exercised |
| --- | --- | --- |
| Chain | 3 and 16 total components | Pipeline depth and per-hop overhead |
| Fan-out | 2 and 16 receivers | Output broadcast and concurrent consumers |
| Fan-in | 2 and 16 sources sharing one input field | Input multiplexing and producer status tracking |
| Diamond | 4 components | Branching followed by synchronization of two input fields |
| Feedback | 3 components, one seeded input | Cyclic dependencies and repeated synchronization |

Fan-in delivers `sources * 1,000` messages; fan-out delivers 1,000 messages to
each receiver. Increasing width therefore increases total work. The diamond join
waits for both branches and forwards the first value. The feedback join waits for
a source value and the preceding feedback value, with an initial seed to let it
start. Receiver counts and checksums and all component completion statuses are
checked outside the timed region so lost messages cannot look like a speedup.

Every case reports three timing groups, each with five fresh process instances:

- `init`: `process.init()` only, including wiring, state connection, component
  initialization, and graph validation. Destruction happens outside the timer.
- `run`: `process.run()` only, with initialization and destruction outside the timer.
- `lifecycle`: initialization, execution, and destruction together.

Graph construction is outside all three timers. Each timed call includes one
`Runner.run()` dispatch; event-loop creation and closure are outside the timer.
Construction, initialization, execution, and destruction all use the same running
event loop for each process. Processes are destroyed even when initialization or
execution fails. No initialization delays are patched: in particular,
`LocalProcess` currently waits one second for connections during initialization,
which dominates `init` and `lifecycle` results for small graphs. Keep the separate
`run` group when examining throughput regressions.

These are local in-memory benchmarks. They do not measure serialization,
distributed workers, external brokers, or persistent state backends, whose service
startup and environmental variability require separate benchmark infrastructure.
