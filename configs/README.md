# Model configuration records

These historical configurations retain model identifiers and request options,
not working provider accounts. Deployment-specific Alibaba endpoints were
replaced by `https://provider.example/v1`. Original settings remain in the
source repository and frozen run evidence.

For a new experiment, copy [`examples/model.example.json`](../examples/model.example.json)
to a private file and supply your provider URL, model ID and credential
environment-variable name. Keep the secret value outside JSON and version
control. The example endpoint and model are intentionally unusable.

Follow [running and extending](../docs/running.md) to prepare a run.
Configuration hashes become part of its frozen record; changing a public
template does not change a historical experiment.
