# cramera-questions

Adds the `questions` plugin to the viewer: recorded cramera scenes are asked questions
in the entity query language. The questions are answered by `cramera-bridge`'s question
engine (`cramera_bridge.questions`), which needs krrood from the CRAM workspace; install it
with the `cram` extra. The plugin imports nothing of either itself. See the repository
README and `docs/architecture.md`.

Without them the plugin still loads: its routes answer what is missing, and
its browser module shows the answers recorded in each bundle's `recorded_answers.json`,
which `cramera-record-answers SCENES_DIRECTORY [--scene NAME]` of `cramera-bridge` writes
in a CRAM workspace.
