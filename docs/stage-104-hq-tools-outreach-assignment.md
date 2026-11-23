# Stage 104: Run safe variant assignment from HQ Tools

The PC runner catalog now exposes **Waterfall experiments: assign outreach variants** in HQ Tools. The user selects a combined paired enrichment CSV from `my-lists`, supplies the experiment ID and a stable seed, and the local runner invokes the assignment command. Its resulting `*-outreach-assigned.csv` is surfaced as an output. The source stays on the PC and is not modified or uploaded.

Use the assigned output as the only source for these leads when copying it into an Engine's imports. Keep the paired A/B source CSV in `my-lists`, outside the Engine imports folder, so the Engine's new cross-variant guard does not see the unassigned pair.

This is a local runner catalog change: the connected PC must fetch the toolkit update and restart its runner before the new HQ Tool appears. No `dbi-citadel` UI code or server migration was needed because HQ Tools renders tools from the connected PC's catalog.

Validation for this slice: catalog generator execution, Python compilation, and `git diff --check`; no test suite was run.
