# cramera-models

A viewer plugin with a Models side panel: load a probabilistic circuit from its JSON
file and ask it for the probability of an event, the posterior marginals of variables
and the most likely assignments, each given evidence.

The circuit libraries are optional. Without `probabilistic_model`, `random_events`,
`krrood` and `plotly` the plugin still loads, the viewer keeps working and the panel
shows which libraries are missing. Install them with the `circuits` extra or from a
CRAM workspace.
