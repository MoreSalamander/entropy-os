# Hunter Run Outcome Tracker — API

## gate_outcome_service

- `GET /gate-outcomes` — Get all gate outcomes
- `POST /gate-outcomes` — Create a new gate outcome
- `GET /hunter_run_outcomes` — List HunterRunOutcome records _(entity: HunterRunOutcome)_
- `POST /hunter_run_outcomes` — Create a HunterRunOutcome _(entity: HunterRunOutcome)_
- `GET /hunter_run_outcomes/{item_id}` — Fetch one HunterRunOutcome _(entity: HunterRunOutcome)_
- `DELETE /hunter_run_outcomes/{item_id}` — Delete a HunterRunOutcome _(entity: HunterRunOutcome)_
- `GET /opportunitys` — List Opportunity records _(entity: Opportunity)_
- `POST /opportunitys` — Create a Opportunity _(entity: Opportunity)_
- `GET /opportunitys/{item_id}` — Fetch one Opportunity _(entity: Opportunity)_
- `DELETE /opportunitys/{item_id}` — Delete a Opportunity _(entity: Opportunity)_

## auth_service

- `POST /login` — Login user
- `GET /logout` — Logout user

