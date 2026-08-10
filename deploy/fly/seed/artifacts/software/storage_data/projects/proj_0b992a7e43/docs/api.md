# Hunter Run Tracker — API

## hunt_service

- `GET /hunter_runs` — List HunterRun records _(entity: HunterRun)_
- `POST /hunter_runs` — Create a HunterRun _(entity: HunterRun)_
- `GET /hunter_runs/{item_id}` — Fetch one HunterRun _(entity: HunterRun)_
- `DELETE /hunter_runs/{item_id}` — Delete a HunterRun _(entity: HunterRun)_

## gate_outcome_service

- `GET /gate-outcomes/{item_id}` — Get gate outcome by ID _(entity: GateOutcome)_
- `GET /gate-outcomes` — Get all gate outcomes

## auth_service

- `POST /login` — Login user
- `GET /logout` — Logout user

## csv_export_service

- `GET /exports/{id}` — Get hunt data in CSV format

