# Hunter Run Outcome Tracker — API

## gate_outcome_service

- `POST /gate-outcomes` — Create a new gate outcome record _(entity: HunterRunOutcome)_
- `GET /gate-outcomes` — Query recorded gate outcomes by filters
- `GET /opportunitys` — List Opportunity records _(entity: Opportunity)_
- `POST /opportunitys` — Create a Opportunity _(entity: Opportunity)_
- `GET /opportunitys/{item_id}` — Fetch one Opportunity _(entity: Opportunity)_
- `DELETE /opportunitys/{item_id}` — Delete a Opportunity _(entity: Opportunity)_

## auth_service

- `POST /login` — Authenticate user credentials
- `GET /protected/gate-outcomes` — Query recorded gate outcomes by filters (authenticated users only)

