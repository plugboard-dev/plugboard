## Main configuration options


Plugboard can either be configured via environment variables or using a `.env` file. Full details on the settings and feature flags can be found in [`plugboard.utils.settings.Settings`][plugboard.utils.settings.Settings].

## Logging

Logging can be configured via the following environment variables:

| Option Name                | Description                                              | Default Value |
|----------------------------|----------------------------------------------------------|---------------|
| `PLUGBOARD_LOG_LEVEL`      | Sets the logging level (e.g., `DEBUG`, `INFO`, `ERROR`)  | `WARNING`     |
| `PLUGBOARD_LOG_STRUCTURED` | Enables logging in JSON format.                          |               |

Plugboard uses [structlog](https://www.structlog.org/en/stable/) as its logging library. For basic changes you can adjust the options above, but for more advanced configuration you may need to call [`structlog.configure()`](https://www.structlog.org/en/stable/configuration.html) and set the options yourself.
