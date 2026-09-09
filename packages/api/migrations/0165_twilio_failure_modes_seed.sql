-- Seed published Twilio failure modes so Index / MCP / service pages
-- do not treat an empty list as a clean bill of health (issue #42).
-- Idempotent: skip rows that already exist for the same slug + title.

INSERT INTO failure_modes (
  service_slug,
  category,
  title,
  description,
  severity,
  frequency,
  agent_impact,
  workaround
)
SELECT
  seed.service_slug,
  seed.category,
  seed.title,
  seed.description,
  seed.severity,
  seed.frequency,
  seed.agent_impact,
  seed.workaround
FROM (
  VALUES
    (
      'twilio',
      'auth',
      'Phone number and 10DLC verification wall',
      'Before an agent can send messages, Twilio requires a provisioned number plus country-specific registration. US long-code traffic needs A2P 10DLC campaign approval, which is a human-reviewed carrier process that typically takes 1-7 business days. Agents can start the workflow via API but cannot complete it autonomously.',
      'high',
      'common',
      'First-message latency of days, not seconds. Agents that treat number purchase as sufficient send-authority will queue messages that carriers later reject.',
      'Complete 10DLC or local registration before granting send authority. Separate ''number purchased'' from ''allowed to send''. Surface needs-human-review when carrier approval is still pending.'
    ),
    (
      'twilio',
      'cost',
      'Per-message pricing varies by country, carrier, and segment',
      'Twilio prices per message with rates that change by destination country, originating number type, SMS vs MMS, carrier surcharges, and segment count for messages over 160 characters. There is no single price an agent can cache.',
      'high',
      'common',
      'Budget enforcement silently undercounts. A US SMS at ~$0.0079 can become several times that for international, MMS, or multi-segment bodies.',
      'Call the Twilio pricing API for the destination before send, or maintain a surcharge table. Fail closed when the estimated cost is unknown instead of guessing.'
    ),
    (
      'twilio',
      'rate-limiting',
      'Carrier send limits are not API rate-limit headers',
      'The Twilio API will accept large queues quickly, but carrier networks throttle delivery: about 1 SMS/second for US long codes, 3/second for toll-free, and higher for short codes. Those limits are not returned as standard rate-limit headers.',
      'high',
      'common',
      'API 200/queued does not mean delivered. Agents that fire a burst after ''accepted'' responses can trigger carrier filtering or delayed delivery without a 429.',
      'Throttle by number type, not by API acceptance. Treat queued vs delivered as different states. Watch status callbacks before retrying.'
    ),
    (
      'twilio',
      'error-handling',
      'Accepted-but-undelivered and opaque carrier filtering',
      'Messages can be accepted by Twilio and still end undelivered or filtered by the destination carrier. Carrier filtering is often opaque: the create-message call succeeds, and only a later status callback (or never) reveals failure.',
      'high',
      'occasional',
      'Agents report success to users after create-message succeeds, then never learn the SMS failed. Retry logic may send duplicates if idempotency keys are not reused.',
      'Join create-message, status callback, provider message id, and idempotency key in one trace. Require typed outcomes for sent, queued, delivered, failed, undelivered, and needs-human-review before claiming success.'
    )
) AS seed(service_slug, category, title, description, severity, frequency, agent_impact, workaround)
WHERE NOT EXISTS (
  SELECT 1
  FROM failure_modes existing
  WHERE existing.service_slug = seed.service_slug
    AND existing.title = seed.title
    AND existing.resolved_at IS NULL
);
