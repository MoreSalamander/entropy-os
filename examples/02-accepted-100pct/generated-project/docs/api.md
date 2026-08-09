# Hunter Run Outcome Tracker — API

## opportunity_service

- `GET /opportunities` — List all opportunities
- `POST /opportunities` — Create a new opportunity
- `GET /opportunities/{item_id}` — Get an opportunity by ID _(entity: Opportunity)_
- `PUT /opportunities/{item_id}` — Update an opportunity _(entity: Opportunity)_

## auth_service

- `POST /login` — Login user
- `GET /me` — Get current user

## export_service

- `GET /opportunities/export` — Export opportunities to CSV

