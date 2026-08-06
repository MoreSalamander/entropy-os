---
id: mem_96b6f737c9db
category: artifact
title: 'DataHub 201: Introduction to DataHub Actions Framework'
source_artifact_id: art_3db86503b5c8
tags:
- tutorial
- overview
- essentials_only
created_at: '2026-08-01T02:05:58.230664+00:00'
provenance:
  created_by: tutorial-generator-agent
  rationale: 'single-use tutorial from: ''DataHub 201: Introduction to DataHub Actions
    Framework'', scope=overview/essentials_only'
  accepted_because: 'usable: 4 material(s), 4 section(s), 10 step(s), scope respected'
  source_id: mem_eca734ad8db3
  source_title: 'DataHub 201: Introduction to DataHub Actions Framework'
  source_url: https://youtube.com/watch?v=lrx8LFbe7w0&is=GmnS08iuPn0qbqg0
  source_channel: DataHub
  depth: overview
  reading_style: essentials_only
  include_typing_practice: false
  container_image: veritas-tutorial-96b6f737c9db:local
---

```json
{
  "overview": "This guide introduces the DataHub Actions framework, which allows users to react to changes in DataHub (such as entity creation or metadata updates) by triggering notifications, propagations, or custom logic.",
  "materials": [
    "DataHub Actions module",
    "Kafka (only supported event source)",
    "Action config file",
    "Python (for custom actions)"
  ],
  "sections": [
    {
      "title": "Core Concepts",
      "intro": "Understanding the difference between data ingestion and action execution.",
      "steps": [
        {
          "instruction": "Identify events as 'changes' (e.g., entity creation, removal) and actions as the resulting operations (e.g., notifications, propagations)."
        }
      ]
    },
    {
      "title": "Execution & Configuration",
      "intro": "How to set up and run standard or custom actions.",
      "steps": [
        {
          "instruction": "Install the DataHub Actions module."
        },
        {
          "instruction": "Configure the Action config file with a pipeline name, source (Kafka), optional filters, and action type."
        },
        {
          "instruction": "Execute actions using the 'dataactions' command instead of 'data ingest'."
        }
      ]
    },
    {
      "title": "Custom Actions",
      "intro": "Steps to create a bespoke action by extending the framework.",
      "steps": [
        {
          "instruction": "Define a custom action by extending the ActionBased class in Python."
        },
        {
          "instruction": "Override the three core functions: create, act (main logic), and close."
        },
        {
          "instruction": "Install the custom action as a package or place it in the same directory."
        },
        {
          "instruction": "Run the custom action by specifying the package name, file name, and class name."
        }
      ]
    },
    {
      "title": "Tag Propagation Example",
      "intro": "A specific use case where tags are automatically applied to downstream assets.",
      "steps": [
        {
          "instruction": "Configure the action type as 'tag propagation' in the config file."
        },
        {
          "instruction": "Run the pipeline using 'dataactions' followed by the configuration filename."
        }
      ]
    }
  ],
  "reference": [
    "Supported Event Sources: Kafka",
    "Standard Actions: Hello World (JSON print), Slack (notifications), Propagation (tags, terms, snowflake)"
  ]
}
```
