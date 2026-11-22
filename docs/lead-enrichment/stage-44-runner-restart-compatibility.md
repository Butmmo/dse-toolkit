# Stage 44: Advertise safe toolkit runner restart support

The toolkit runner's public catalog now advertises `runner.restart.v1` only when its built-in restart handler is available. Its runner version is bumped to 1.2. The app uses this capability marker to avoid sending the restart job to older installations that treat its empty script path as an error.

An older runner must be updated and started manually once; it cannot bootstrap a remote restart it does not understand. No database migration is required. No automated tests were run.
