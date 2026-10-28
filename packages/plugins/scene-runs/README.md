# cramera-scene-runs

A **Runs** tab for the cramera viewer: it starts the robot runs a server offers, one at
a time, has the page follow each run live, stops it, and replays its recording. It is
meant for a viewer served behind a password-checking proxy
(`cramera --public-origin ...`), where the pages it serves may start and stop runs and
step through a run's queries, but change nothing else.

```bash
pip install -e packages/plugins/scene-runs
CRAMERA_SCENE_RUNS=/etc/cramera-phone/runs.json cramera --public-origin https://cramera.example.org --port 8724
```

The catalog file names the runs, in the order the tab offers them:

```json
{
  "runs": [
    {
      "identifier": "pr2_transfer",
      "label": "PR2 vessel transfer",
      "command": ["python", "-m", "cramera_bridge.demos.query_stepping",
                  "--bundle", "/srv/cramera-phone/demos/aicor_medical_lab",
                  "--name", "{recording}"],
      "scene": "aicor_medical_lab_pr2_query_stepper"
    }
  ]
}
```

- `identifier`: lowercase letters, digits and `_`, at most 48 characters.
- `command`: run as a process of its own, in a process group the tab stops as a whole;
  `{recording}` becomes a new recording name, `<identifier>_<YYYYmmdd_HHMMSS>`. The
  run's live publisher should listen on `127.0.0.1:8765`, where the viewer's relay reads
  it, and save its recording into the viewer's local scenes directory.
- `scene`: optionally, a recording of the run the tab offers to replay.

The commands stay on the server; pages see only the identifiers, labels and scenes. A
run that ends with exit code 0 and whose recording the viewer finds has **recorded**;
one that ends otherwise has **failed**, and the tab shows the end of its output, which
is kept in `scene-runs/` of cramera's data directory. Without `CRAMERA_SCENE_RUNS` the
plugin offers no runs and adds no tab. It imports nothing of CRAM.
