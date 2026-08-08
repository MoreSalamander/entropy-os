# GPUcademy 2.0 — API

## curriculum_service

- `GET /lessons/{item_id}` —  _(entity: Lesson)_

## quiz_service

- `POST /quizzes/{lesson_id}` — 
- `GET /user_progress` —  _(entity: User)_
- `GET /quiz_results` — List QuizResult records _(entity: QuizResult)_
- `POST /quiz_results` — Create a QuizResult _(entity: QuizResult)_
- `GET /quiz_results/{item_id}` — Fetch one QuizResult _(entity: QuizResult)_
- `DELETE /quiz_results/{item_id}` — Delete a QuizResult _(entity: QuizResult)_

## auth_service

- `POST /login` — 
- `GET /user_info` —  _(entity: User)_

## example_service

- `GET /examples/{concept}` — 

## public_api

- `GET /content/{lesson_id}` — 

