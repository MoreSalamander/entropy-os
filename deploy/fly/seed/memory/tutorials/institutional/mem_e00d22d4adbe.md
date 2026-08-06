---
id: mem_e00d22d4adbe
category: artifact
title: 'Capstone: build and document an API'
source_artifact_id: art_8d835ffce0e9
tags:
- tutorial
- deep_dive
- detailed
created_at: '2026-08-01T02:22:55.971684+00:00'
provenance:
  created_by: tutorial-generator-agent
  rationale: 'single-use tutorial from: ''Capstone: build and document an API'', scope=deep_dive/detailed'
  accepted_because: 'usable: 5 material(s), 5 section(s), 13 step(s), scope respected'
  source_id: mem_ad9631039576
  source_title: 'Capstone: build and document an API'
  source_url: file:///Users/0ne29/Documents/myAIstro-vault/BE102 - W4 - Capstone-
    build and document an API.md
  source_channel: BE102
  depth: deep_dive
  reading_style: detailed
  include_typing_practice: true
  container_image: veritas-tutorial-e00d22d4adbe:local
---

```json
{
  "overview": "Build a fully functional RESTful CRUD API for a 'car' resource using Flask, implement centralized validation logic, and generate interactive Swagger documentation using Flasgger.",
  "materials": [
    "Python 3",
    "Flask",
    "Flasgger",
    "Postman (for testing)",
    "Project folder"
  ],
  "sections": [
    {
      "title": "Environment Setup",
      "intro": "Prepare your local development environment and install the necessary dependencies.",
      "steps": [
        {
          "instruction": "Create a virtual environment using Python 3.",
          "code": "python3 -m venv venv"
        },
        {
          "instruction": "Activate the virtual environment (Mac/Linux).",
          "code": "source venv/bin/activate"
        },
        {
          "instruction": "Install Flask and Flasgger.",
          "code": "pip install Flask flasgger"
        }
      ],
      "tip": "If using Windows PowerShell, the activation command is `.\\venv\\Scripts\\activate`."
    },
    {
      "title": "Base Application Setup",
      "intro": "Initialize a basic Flask app with an in-memory data store.",
      "steps": [
        {
          "instruction": "Create app.py and implement the base server logic.",
          "code": "from flask import Flask\n\napp = Flask(__name__)\n\ncars = []  # in-memory \"database\"\nnext_id = 1\n\n@app.route(\"/\")\ndef home():\n    return \"Cars API is running!\"\n\nif __name__ == \"__main__\":\n    app.run(debug=True)"
        }
      ]
    },
    {
      "title": "CRUD Implementation",
      "intro": "Build the core functionality for Creating, Reading, Updating, and Deleting car resources.",
      "steps": [
        {
          "instruction": "Implement the POST /cars route to create a new car with basic validation.",
          "code": "@app.route(\"/cars\", methods=[\"POST\"])\ndef create_car():\n    global next_id\n    data = request.get_json()\n    if not data or \"make\" not in data or \"model\" not in data:\n        return jsonify({\"error\": \"BAD_REQUEST\", \"message\": \"Fields 'make' and 'model' are required.\"}), 400\n\n    new_car = {\n        \"id\": next_id,\n        \"make\": data[\"make\"],\n        \"model\": data[\"model\"],\n        \"engine\": data.get(\"engine\"),\n        \"doors\": data.get(\"doors\"),\n        \"transmission\": data.get(\"transmission\")\n    }\n    cars.append(new_car)\n    next_id += 1\n    return jsonify(new_car), 201"
        },
        {
          "instruction": "Implement the GET /cars route to list all cars.",
          "code": "@app.route(\"/cars\", methods=[\"GET\"])\ndef list_cars():\n    return jsonify(cars), 200"
        },
        {
          "instruction": "Implement the GET /cars/<id> route to fetch a specific car.",
          "code": "@app.route(\"/cars/<int:car_id>\", methods=[\"GET\"])\ndef get_car(car_id):\n    for car in cars:\n        if car[\"id\"] == car_id:\n            return jsonify(car), 200\n    return jsonify({\"error\": \"NOT_FOUND\", \"message\": f\"Car with id {car_id} not found.\"}), 404"
        },
        {
          "instruction": "Implement the PUT /cars/<id> route to update an existing car.",
          "code": "@app.route(\"/cars/<int:car_id>\", methods=[\"PUT\"])\ndef update_car(car_id):\n    data = request.get_json()\n    if not data or \"make\" not in data or \"model\" not in data:\n        return jsonify({\"error\": \"BAD_REQUEST\", \"message\": \"Fields 'make' and 'model' are required.\"}), 400\n\n    for car in cars:\n        if car[\"id\"] == car_id:\n            car[\"make\"] = data[\"make\"]\n            car[\"model\"] = data[\"model\"]\n            car[\"engine\"] = data.get(\"engine\")\n            car[\"doors\"] = data.get(\"doors\")\n            car[\"transmission\"] = data.get(\"transmission\")\n            return jsonify(car), 200\n    return jsonify({\"error\": \"NOT_FOUND\", \"message\": f\"Car with id {car_id} not found.\"}), 404"
        },
        {
          "instruction": "Implement the DELETE /cars/<id> route to remove a car.",
          "code": "@app.route(\"/cars/<int:car_id>\", methods=[\"DELETE\"])\ndef delete_car(car_id):\n    for index, car in enumerate(cars):\n        if car[\"id\"] == car_id:\n            cars.pop(index)\n            return \"\", 204\n    return jsonify({\"error\": \"NOT_FOUND\", \"message\": f\"Car with id {car_id} not found.\"}), 404"
        }
      ]
    },
    {
      "title": "Refactor: Centralized Validation",
      "intro": "Replace inline validation checks with a reusable helper function to follow DRY (Don't Repeat Yourself) principles.",
      "steps": [
        {
          "instruction": "Define the validate_car helper function.",
          "code": "def validate_car(data):\n    if not data:\n        return {\"error\": \"BAD_REQUEST\", \"message\": \"Request body must be JSON.\"}\n    required_fields = [\"make\", \"model\"]\n    missing = [field for field in required_fields if field not in data]\n    if missing:\n        return {\"error\": \"BAD_REQUEST\", \"message\": f\"Missing required fields: {', '.join(missing)}\"}\n    return None"
        },
        {
          "instruction": "Update the create_car and update_car routes to use the helper.",
          "code": "# Example for create_car\ndata = request.get_json()\nerror = validate_car(data)\nif error:\n    return jsonify(error), 400"
        }
      ]
    },
    {
      "title": "Documentation with Flasgger",
      "intro": "Integrate Swagger documentation to make the API discoverable and testable via a web UI.",
      "steps": [
        {
          "instruction": "Initialize Flasgger in the app configuration.",
          "code": "from flasgger import Swagger\n\napp = Flask(__name__)\nswagger = Swagger(app)"
        },
        {
          "instruction": "Add YAML docstrings to each route for Swagger generation.",
          "code": "\"\"\"\n# Example for GET /cars\nList all cars\n---\ntags:\n  - Cars\nresponses:\n  200:\n    description: A list of cars\n    content:\n      application/json:\n        schema:\n          type: array\n          items:\n            type: object\n\"\"\""
        }
      ],
      "tip": "Access the documentation at http://127.0.0.1:5000/apidocs to view and test endpoints."
    }
  ],
  "reference": [
    "Status Codes: 200 (OK), 201 (Created), 204 (No Content), 400 (Bad Request), 404 (Not Found)",
    "Endpoint Paths: /cars, /cars/<int:car_id>",
    "Validation Logic: Required fields are 'make' and 'model'"
  ]
}
```
