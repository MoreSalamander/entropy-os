# PhoneFormatter — API

## phone_formatter_service

- `POST /format-phone-number` — Format a phone number
- `GET /phone_numbers` — List PhoneNumber records _(entity: PhoneNumber)_
- `POST /phone_numbers` — Create a PhoneNumber _(entity: PhoneNumber)_
- `GET /phone_numbers/{item_id}` — Fetch one PhoneNumber _(entity: PhoneNumber)_
- `DELETE /phone_numbers/{item_id}` — Delete a PhoneNumber _(entity: PhoneNumber)_

## country_code_repository

- `GET /country-codes` — Get all country codes
- `POST /country-code` — Create a new country code
- `GET /country_codes` — List CountryCode records _(entity: CountryCode)_
- `POST /country_codes` — Create a CountryCode _(entity: CountryCode)_
- `GET /country_codes/{item_id}` — Fetch one CountryCode _(entity: CountryCode)_
- `DELETE /country_codes/{item_id}` — Delete a CountryCode _(entity: CountryCode)_

