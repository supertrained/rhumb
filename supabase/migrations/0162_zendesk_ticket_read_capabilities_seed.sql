-- AUD-18 Wave 1c: Zendesk ticket read capabilities seed
-- Adds ticket.search, ticket.get, ticket.list_comments to the capabilities catalog.

INSERT INTO capabilities (id, domain, action, description, input_hint, outcome)
VALUES
  (
    'ticket.search',
    'ticket',
    'search',
    'Search Zendesk tickets from a scoped support_ref with bounded results.',
    'Provide support_ref plus a free-text Zendesk ticket query.',
    'Returns bounded Zendesk ticket summaries with provider attribution.'
  ),
  (
    'ticket.get',
    'ticket',
    'get',
    'Fetch one Zendesk ticket from a scoped support_ref.',
    'Provide support_ref plus a ticket_id.',
    'Returns bounded plain-text Zendesk ticket details with provider attribution.'
  ),
  (
    'ticket.list_comments',
    'ticket',
    'list_comments',
    'Fetch Zendesk ticket comments from a scoped support_ref.',
    'Provide support_ref plus a ticket_id; public comments only by default.',
    'Returns bounded Zendesk ticket comments with provider attribution.'
  )
ON CONFLICT (id) DO UPDATE
SET
  domain = EXCLUDED.domain,
  action = EXCLUDED.action,
  description = EXCLUDED.description,
  input_hint = EXCLUDED.input_hint,
  outcome = EXCLUDED.outcome;
