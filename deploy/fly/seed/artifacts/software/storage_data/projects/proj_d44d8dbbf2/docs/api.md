# GPUcademy — API

## auth_service

- `GET /users` — List User records _(entity: User)_
- `POST /users` — Create a User _(entity: User)_
- `GET /users/{item_id}` — Fetch one User _(entity: User)_
- `DELETE /users/{item_id}` — Delete a User _(entity: User)_

## lesson_service

- `GET /lessons/{item_id}` — Get a lesson by ID _(entity: Lesson)_
- `POST /lessons` — Create a new lesson _(entity: Lesson)_
- `GET /quizs` — List Quiz records _(entity: Quiz)_
- `POST /quizs` — Create a Quiz _(entity: Quiz)_
- `GET /quizs/{item_id}` — Fetch one Quiz _(entity: Quiz)_
- `DELETE /quizs/{item_id}` — Delete a Quiz _(entity: Quiz)_

## progress_service

- `GET /users/{id}/progress` — Get user progress by ID
- `POST /users/{id}/progress` — Update user progress by ID

## quiz_service

- `GET /quizzes/{item_id}` — Get a quiz by ID _(entity: Quiz)_
- `POST /quizzes` — Create a new quiz _(entity: Quiz)_

