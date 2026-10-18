# Error Before/After: get_ticket with invalid ticket ID

## Docstring Change

### Before (old docstring)

```
"Retrieve a support ticket by its ID and return the ticket text, customer ID, and linked order ID."
```

Tells the model nothing about the ID format or what happens on failure.

### After (new docstring -- written as a prompt)

```
"Look up a support ticket by ticket_id (format: Tnnn, e.g. T002, T008).
Returns the ticket text, customer_id, and linked order_id.
If the ticket is not found, returns a message with the expected ID format
so you can ask the user to double-check rather than retrying the same call."
```

Tells the model:
- What the ID format looks like (Tnnn)
- Gives examples (T002, T008)
- Explains that not-found is a message, not a crash
- Instructs the model to ask the user rather than retry

---

## Error Path Change

### Before (old error return)

```python
return {"error": "not_found", "ticket_id": ticket_id}
```

Output when calling get_ticket("T999"):
```json
{"error": "not_found", "ticket_id": "T999"}
```

The model sees "not_found" but has no context about what a valid ID looks like.
It cannot distinguish a typo from a deleted ticket from a dead server.

### After (new recoverable error return)

```python
from agent.tickets import TICKETS
available = sorted(TICKETS.keys())[:5]
return {
    "error": "not_found",
    "ticket_id": ticket_id,
    "hint": f"Ticket {ticket_id} not found -- IDs look like Tnnn (e.g. {', '.join(available)}). Ask the user to verify.",
}
```

Output when calling get_ticket("T999"):
```json
{
  "error": "not_found",
  "ticket_id": "T999",
  "hint": "Ticket T999 not found -- IDs look like Tnnn (e.g. T002, T003, T004, T007, T008). Ask the user to verify."
}
```

---

## Model Transcript Comparison

### Before -- opaque error

```
User:      What is the status of ticket T999?
Assistant: [calls get_ticket(ticket_id="T999")]
Tool:      {"error": "not_found", "ticket_id": "T999"}
Assistant: [calls get_ticket(ticket_id="T999")]   <-- retries same call
Tool:      {"error": "not_found", "ticket_id": "T999"}
Assistant: [calls get_ticket(ticket_id="T999")]   <-- retries again
Tool:      {"error": "not_found", "ticket_id": "T999"}
Assistant: I'm sorry, I was unable to retrieve ticket T999.
```

3 wasted turns. No useful feedback to the user.

### After -- recoverable error

```
User:      What is the status of ticket T999?
Assistant: [calls get_ticket(ticket_id="T999")]
Tool:      {"error": "not_found", "ticket_id": "T999", "hint": "Ticket T999 not found -- IDs look like Tnnn (e.g. T002, T003, T004, T007, T008). Ask the user to verify."}
Assistant: I could not find ticket T999. Valid ticket IDs look like T002, T003, T004, etc.
           Could you double-check the ticket number?
```

1 turn. Clear feedback. User knows what to do next.
