---
persona: architect
applies_to: connector-management
priority: high
created: 2026-03-12T03:52:30Z
---
{
  "connector": "trello",
  "enabled": true,
  "workspace": "{{workspace}}",
  "board_id": "{{board_id}}",
  "lists": {
    "analyst": "{{list_analyst}}",
    "architect": "{{list_architect}}",
    "security": "{{list_security}}",
    "qa": "{{list_qa}}",
    "regression": "{{list_regression}}"
  },
  "external_id_prefix": "{{external_id_prefix}}",
  "sync": {
    "mode": "push",
    "reconcile_on_start": true
  }
}
