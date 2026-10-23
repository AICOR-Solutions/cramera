# cramera-questions

Asks a CRAM world or a recorded cramera scene questions in the entity query language,
and adds the `questions` plugin to the viewer. Needs krrood from the CRAM workspace. See
the repository README and `docs/architecture.md`.

Without krrood the plugin still loads: its routes answer that krrood is missing, and
its browser module shows the answers recorded in each bundle's `recorded_answers.json`,
which `cramera-record-answers SCENES_DIRECTORY [--scene NAME]` writes in a CRAM
workspace.
