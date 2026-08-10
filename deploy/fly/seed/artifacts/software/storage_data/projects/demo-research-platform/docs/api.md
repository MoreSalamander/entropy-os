# Cerebro — API

## search_service

- `GET /users` — List User records _(entity: User)_
- `POST /users` — Create a User _(entity: User)_
- `GET /users/{item_id}` — Fetch one User _(entity: User)_
- `DELETE /users/{item_id}` — Delete a User _(entity: User)_

## dataset_service

- `POST /datasets` — Create a new dataset _(entity: Dataset)_
- `GET /datasets/{id}` — Get a dataset by ID _(entity: Dataset)_

## access_control_service

- `POST /users/{id}/roles` — Assign a role to a user

## session_service

- `POST /sessions` — Create a new session

