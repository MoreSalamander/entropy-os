# String Reverser — API

## string_reverser_service

- `POST /reverse-string` — Reverse input string with correct character order
- `GET /string_reversal_requests` — List StringReversalRequest records _(entity: StringReversalRequest)_
- `POST /string_reversal_requests` — Create a StringReversalRequest _(entity: StringReversalRequest)_
- `GET /string_reversal_requests/{item_id}` — Fetch one StringReversalRequest _(entity: StringReversalRequest)_
- `DELETE /string_reversal_requests/{item_id}` — Delete a StringReversalRequest _(entity: StringReversalRequest)_
- `GET /string_reversal_responses` — List StringReversalResponse records _(entity: StringReversalResponse)_
- `POST /string_reversal_responses` — Create a StringReversalResponse _(entity: StringReversalResponse)_
- `GET /string_reversal_responses/{item_id}` — Fetch one StringReversalResponse _(entity: StringReversalResponse)_
- `DELETE /string_reversal_responses/{item_id}` — Delete a StringReversalResponse _(entity: StringReversalResponse)_

## input_limiter_service

- `POST /reverse-string` — Reverse input string with correct character order (limited length)

## debugging_service

- `GET /debugging/input-string` — Retrieve stored input string for debugging purposes

## performance_monitor_service

- `GET /performance/monitoring` — Monitor performance of reversing strings in under 10ms for typical inputs

## unicode_support_service

- `POST /reverse-string/unicode-support` — Reverse input string with correct character order, supporting Unicode characters and non-ASCII encodings

