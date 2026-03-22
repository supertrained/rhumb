-- Migration 0069: Capability Expansion Day 25
-- Domains: chatbot, loyalty, marketplace, media
-- New capabilities: 10
-- New mappings: ~36
-- Cumulative target: ~301 capabilities / ~1036 mappings
-- Milestone: 300-capability target reached

-- ============================================================
-- DOMAIN: chatbot (Conversational AI & Live Chat)
-- ============================================================

INSERT INTO capabilities (id, name, domain, description, input_schema, output_schema) VALUES
  ('chatbot.create', 'chatbot.create', 'chatbot', 'Create or configure a chatbot widget or conversation flow', '{"type":"object","required":["name"],"properties":{"name":{"type":"string"},"greeting":{"type":"string"},"fallback_message":{"type":"string"},"channels":{"type":"array","items":{"type":"string","enum":["web","mobile","whatsapp","messenger"]}},"operator_handoff":{"type":"boolean","default":true}}}', '{"type":"object","properties":{"chatbot_id":{"type":"string"},"embed_code":{"type":"string"},"status":{"type":"string"}}}'),
  ('chatbot.send_message', 'chatbot.send_message', 'chatbot', 'Send a message to an active chat conversation', '{"type":"object","required":["conversation_id","message"],"properties":{"conversation_id":{"type":"string"},"message":{"type":"string"},"type":{"type":"string","enum":["text","note","auto_message"],"default":"text"},"author_type":{"type":"string","enum":["bot","operator"],"default":"bot"}}}', '{"type":"object","properties":{"message_id":{"type":"string"},"sent_at":{"type":"string"}}}'),
  ('chatbot.get_history', 'chatbot.get_history', 'chatbot', 'Retrieve message history for a chat conversation', '{"type":"object","required":["conversation_id"],"properties":{"conversation_id":{"type":"string"},"limit":{"type":"integer","default":50}}}', '{"type":"object","properties":{"messages":{"type":"array"},"total":{"type":"integer"},"has_more":{"type":"boolean"}}}')
ON CONFLICT (id) DO NOTHING;

INSERT INTO capability_services (capability_id, provider, tier, cost_per_call, quality_score, is_top_provider) VALUES
  -- chatbot.create
  ('chatbot.create', 'intercom', 'byo', 0.010, 8.1, true),
  ('chatbot.create', 'drift', 'byo', 0.009, 7.8, false),
  ('chatbot.create', 'tidio', 'byo', 0.005, 7.4, false),
  ('chatbot.create', 'crisp', 'byo', 0.004, 7.2, false),
  -- chatbot.send_message
  ('chatbot.send_message', 'intercom', 'byo', 0.003, 8.1, true),
  ('chatbot.send_message', 'drift', 'byo', 0.003, 7.8, false),
  ('chatbot.send_message', 'tidio', 'byo', 0.002, 7.4, false),
  ('chatbot.send_message', 'crisp', 'byo', 0.002, 7.2, false),
  -- chatbot.get_history
  ('chatbot.get_history', 'intercom', 'byo', 0.002, 8.1, true),
  ('chatbot.get_history', 'drift', 'byo', 0.002, 7.8, false),
  ('chatbot.get_history', 'tidio', 'byo', 0.001, 7.4, false)
ON CONFLICT (capability_id, provider) DO NOTHING;

-- ============================================================
-- DOMAIN: loyalty (Loyalty & Rewards Programs)
-- ============================================================

INSERT INTO capabilities (id, name, domain, description, input_schema, output_schema) VALUES
  ('loyalty.add_points', 'loyalty.add_points', 'loyalty', 'Award loyalty points to a customer for a qualifying action', '{"type":"object","required":["customer_id","points"],"properties":{"customer_id":{"type":"string"},"points":{"type":"integer"},"reason":{"type":"string"},"order_id":{"type":"string"},"expires_at":{"type":"string"}}}', '{"type":"object","properties":{"transaction_id":{"type":"string"},"new_balance":{"type":"integer"},"tier":{"type":"string"}}}'),
  ('loyalty.get_balance', 'loyalty.get_balance', 'loyalty', 'Get a customer\'s current loyalty points balance and tier', '{"type":"object","required":["customer_id"],"properties":{"customer_id":{"type":"string"}}}', '{"type":"object","properties":{"customer_id":{"type":"string"},"points":{"type":"integer"},"tier":{"type":"string"},"points_expiring_soon":{"type":"integer"}}}'),
  ('loyalty.redeem', 'loyalty.redeem', 'loyalty', 'Redeem loyalty points for a reward or discount', '{"type":"object","required":["customer_id","points","reward_id"],"properties":{"customer_id":{"type":"string"},"points":{"type":"integer"},"reward_id":{"type":"string"}}}', '{"type":"object","properties":{"redemption_id":{"type":"string"},"coupon_code":{"type":"string"},"remaining_balance":{"type":"integer"}}}')
ON CONFLICT (id) DO NOTHING;

INSERT INTO capability_services (capability_id, provider, tier, cost_per_call, quality_score, is_top_provider) VALUES
  -- loyalty.add_points
  ('loyalty.add_points', 'loyaltylion', 'byo', 0.004, 7.8, true),
  ('loyalty.add_points', 'yotpo', 'byo', 0.005, 7.9, false),
  ('loyalty.add_points', 'stamp-me', 'byo', 0.003, 7.3, false),
  ('loyalty.add_points', 'smile-io', 'byo', 0.004, 7.7, false),
  -- loyalty.get_balance
  ('loyalty.get_balance', 'loyaltylion', 'byo', 0.002, 7.8, true),
  ('loyalty.get_balance', 'yotpo', 'byo', 0.002, 7.9, false),
  ('loyalty.get_balance', 'smile-io', 'byo', 0.002, 7.7, false),
  -- loyalty.redeem
  ('loyalty.redeem', 'loyaltylion', 'byo', 0.005, 7.8, true),
  ('loyalty.redeem', 'yotpo', 'byo', 0.006, 7.9, false),
  ('loyalty.redeem', 'smile-io', 'byo', 0.005, 7.7, false)
ON CONFLICT (capability_id, provider) DO NOTHING;

-- ============================================================
-- DOMAIN: marketplace (Marketplace Listing & Discovery)
-- ============================================================

INSERT INTO capabilities (id, name, domain, description, input_schema, output_schema) VALUES
  ('marketplace.list_item', 'marketplace.list_item', 'marketplace', 'Publish a product or service listing to a marketplace', '{"type":"object","required":["title","price"],"properties":{"title":{"type":"string"},"description":{"type":"string"},"price":{"type":"number"},"currency":{"type":"string","default":"USD"},"images":{"type":"array"},"category":{"type":"string"},"sku":{"type":"string"},"quantity":{"type":"integer"}}}', '{"type":"object","properties":{"listing_id":{"type":"string"},"url":{"type":"string"},"status":{"type":"string"}}}'),
  ('marketplace.search', 'marketplace.search', 'marketplace', 'Search marketplace listings by keyword, category, or price range', '{"type":"object","required":["query"],"properties":{"query":{"type":"string"},"category":{"type":"string"},"price_min":{"type":"number"},"price_max":{"type":"number"},"sort":{"type":"string","enum":["relevance","price_asc","price_desc","newest"]},"limit":{"type":"integer","default":20}}}', '{"type":"object","properties":{"listings":{"type":"array"},"total":{"type":"integer"}}}')
ON CONFLICT (id) DO NOTHING;

INSERT INTO capability_services (capability_id, provider, tier, cost_per_call, quality_score, is_top_provider) VALUES
  -- marketplace.list_item
  ('marketplace.list_item', 'shopify', 'byo', 0.004, 8.2, true),
  ('marketplace.list_item', 'ebay', 'byo', 0.005, 7.9, false),
  ('marketplace.list_item', 'etsy', 'byo', 0.004, 7.7, false),
  ('marketplace.list_item', 'woocommerce', 'byo', 0.003, 7.4, false),
  -- marketplace.search
  ('marketplace.search', 'shopify', 'byo', 0.002, 8.2, true),
  ('marketplace.search', 'ebay', 'byo', 0.002, 7.9, false),
  ('marketplace.search', 'etsy', 'byo', 0.002, 7.7, false)
ON CONFLICT (capability_id, provider) DO NOTHING;

-- ============================================================
-- DOMAIN: media (Video & Media Publishing)
-- ============================================================

INSERT INTO capabilities (id, name, domain, description, input_schema, output_schema) VALUES
  ('media.publish', 'media.publish', 'media', 'Publish or schedule a video or media asset to a hosting platform', '{"type":"object","required":["title","file_url"],"properties":{"title":{"type":"string"},"file_url":{"type":"string"},"description":{"type":"string"},"tags":{"type":"array"},"privacy":{"type":"string","enum":["public","private","unlisted"],"default":"public"},"scheduled_at":{"type":"string"}}}', '{"type":"object","properties":{"media_id":{"type":"string"},"url":{"type":"string"},"status":{"type":"string"},"thumbnail_url":{"type":"string"}}}'),
  ('media.get_analytics', 'media.get_analytics', 'media', 'Retrieve view and engagement analytics for a published media asset', '{"type":"object","required":["media_id"],"properties":{"media_id":{"type":"string"},"date_from":{"type":"string"},"date_to":{"type":"string"}}}', '{"type":"object","properties":{"views":{"type":"integer"},"play_rate":{"type":"number"},"watch_time_sec":{"type":"integer"},"engagement_score":{"type":"number"}}}')
ON CONFLICT (id) DO NOTHING;

INSERT INTO capability_services (capability_id, provider, tier, cost_per_call, quality_score, is_top_provider) VALUES
  -- media.publish
  ('media.publish', 'mux', 'byo', 0.010, 8.3, true),
  ('media.publish', 'vimeo', 'byo', 0.008, 7.9, false),
  ('media.publish', 'wistia', 'byo', 0.009, 7.8, false),
  ('media.publish', 'youtube', 'byo', 0.005, 8.0, false),
  -- media.get_analytics
  ('media.get_analytics', 'mux', 'byo', 0.005, 8.3, true),
  ('media.get_analytics', 'vimeo', 'byo', 0.004, 7.9, false),
  ('media.get_analytics', 'wistia', 'byo', 0.004, 7.8, false),
  ('media.get_analytics', 'youtube', 'byo', 0.003, 8.0, false)
ON CONFLICT (capability_id, provider) DO NOTHING;
