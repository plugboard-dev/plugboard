## Main configuration options


Plugboard can either be configured via shell environment variables or using a `.env` file. Full details on the settings and feature flags can be found in [`plugboard.utils.settings.Settings`][plugboard.utils.settings.Settings].

## Logging

Logging can be configured via the following environment variables:

| Option Name                 | Description                                                    | Default Value |
|-----------------------------|----------------------------------------------------------------|---------------|
| `PLUGBOARD_LOG_LEVEL`       | Sets the logging level (e.g., `DEBUG`, `INFO`, `ERROR`)        | `WARNING`     |
| `PLUGBOARD_LOG_STRUCTURED`  | Enables logging in JSON format.                                |               |
| `PLUGBOARD_IO_READ_TIMEOUT` | Time in seconds between periodic status checks during io reads | 20.0          |

Plugboard uses [structlog](https://www.structlog.org/en/stable/) as its logging library. For basic changes you can adjust the options above, but for more advanced configuration you may need to call [`structlog.configure()`](https://www.structlog.org/en/stable/configuration.html) and set the options yourself.

## Message brokers

Plugboard can make use of a message broker for data exchange between components in a distributed setting such as a Ray cluster. To allow components to connect to a broker, a connection string containing the broker url (and credentials if required) should be set in the the environment. Below are the recognised environment variables for the supported message brokers. In general, only one broker would be used per plugboard run.

| Option Name                | Description                                              | Default Value |
|----------------------------|----------------------------------------------------------|---------------|
| `RABBITMQ_URL`      | URL for RabbitMQ AMQP message broker (must include credentials if required)  | |

## Job ID

Each plugboard run has a unique job ID associated with it. This is used to: track state for each run; and separate data messages between runs when using a message broker. Typically, a run would be started without explicitly setting the job ID, in which case a unique job ID will be created automatically. However, there are instances when it may be desirable to specify the job ID, such as stopping a run and resuming the same run later with the existing persisted state. In these scenarios the job ID can be set with the below environment variable which will then be used by any `StateBackend`, `Process` and `Component` while the value is set.

| Option Name                | Description                                              | Default Value |
|----------------------------|----------------------------------------------------------|---------------|
| `PLUGBOARD_JOB_ID`      | Unique job ID for plugboard runs to track state and message broker topics  | |