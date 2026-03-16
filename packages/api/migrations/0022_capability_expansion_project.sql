-- Migration: 0022_capability_expansion_project
-- Description: Add project management domain + spreadsheet domain + compute domain to capability registry
-- Date: 2026-03-16
-- Trigger: Demand intelligence gap analysis — these are top credibility gaps

-- ============================================================
-- NEW CAPABILITIES
-- ============================================================

-- Project Management (Issue Tracking)
INSERT INTO capabilities (id, domain, action, description, input_hint, outcome) VALUES
('project.create_issue', 'project', 'create_issue', 'Create a new issue, task, or ticket', 'title, description, priority?, assignee?, labels?', 'Issue created with tracking ID'),
('project.update_issue', 'project', 'update_issue', 'Update status, fields, or assignment of an issue', 'issue_id, status?, assignee?, labels?, comment?', 'Issue updated'),
('project.list_issues', 'project', 'list_issues', 'List or search issues with filters', 'project?, status?, assignee?, label?, query?', 'Array of matching issues'),
('project.create_sprint', 'project', 'create_sprint', 'Create a sprint or iteration', 'name, start_date, end_date, goal?', 'Sprint created with ID')
ON CONFLICT (id) DO NOTHING;

-- Spreadsheet / Structured Data
INSERT INTO capabilities (id, domain, action, description, input_hint, outcome) VALUES
('spreadsheet.read', 'spreadsheet', 'read', 'Read cells, rows, or ranges from a spreadsheet', 'spreadsheet_id, range, sheet?', 'Cell values as structured data'),
('spreadsheet.write', 'spreadsheet', 'write', 'Write or append data to a spreadsheet', 'spreadsheet_id, range, values, sheet?', 'Cells written'),
('spreadsheet.create', 'spreadsheet', 'create', 'Create a new spreadsheet or table', 'title, columns?, initial_data?', 'New spreadsheet with ID'),
('spreadsheet.query', 'spreadsheet', 'query', 'Query structured data with filters or formulas', 'spreadsheet_id, filter?, formula?', 'Matching rows')
ON CONFLICT (id) DO NOTHING;

-- Compute / Code Execution
INSERT INTO capabilities (id, domain, action, description, input_hint, outcome) VALUES
('compute.execute_code', 'compute', 'execute_code', 'Execute code in a sandboxed environment', 'language, code, timeout?', 'stdout, stderr, exit_code, artifacts'),
('compute.create_sandbox', 'compute', 'create_sandbox', 'Create a persistent sandbox environment', 'language, packages?, memory?', 'sandbox_id'),
('compute.run_function', 'compute', 'run_function', 'Execute a serverless function', 'function_id, input', 'Function output')
ON CONFLICT (id) DO NOTHING;

-- ============================================================
-- CAPABILITY-SERVICE MAPPINGS
-- ============================================================

-- Project Management services
INSERT INTO capability_services (capability_id, service_slug, credential_modes, auth_method, endpoint_pattern, cost_per_call, free_tier_calls, notes) VALUES
-- Linear (AN 7.02)
('project.create_issue', 'linear', '{byo,agent_vault}', 'bearer', 'POST /graphql (IssueCreate)', NULL, NULL, 'GraphQL API, excellent agent ergonomics'),
('project.update_issue', 'linear', '{byo,agent_vault}', 'bearer', 'POST /graphql (IssueUpdate)', NULL, NULL, NULL),
('project.list_issues', 'linear', '{byo,agent_vault}', 'bearer', 'POST /graphql (Issues query)', NULL, NULL, NULL),
('project.create_sprint', 'linear', '{byo,agent_vault}', 'bearer', 'POST /graphql (CycleCreate)', NULL, NULL, 'Linear uses Cycles instead of Sprints'),

-- Jira (AN 6.48)
('project.create_issue', 'jira', '{byo,agent_vault}', 'basic', 'POST /rest/api/3/issue', NULL, NULL, 'REST API, requires project key'),
('project.update_issue', 'jira', '{byo,agent_vault}', 'basic', 'PUT /rest/api/3/issue/{issueIdOrKey}', NULL, NULL, NULL),
('project.list_issues', 'jira', '{byo,agent_vault}', 'basic', 'POST /rest/api/3/search (JQL)', NULL, NULL, 'JQL search, powerful but complex'),
('project.create_sprint', 'jira', '{byo,agent_vault}', 'basic', 'POST /rest/agile/1.0/sprint', NULL, NULL, 'Requires Jira Software'),

-- Asana (AN 6.85)
('project.create_issue', 'asana', '{byo,agent_vault}', 'bearer', 'POST /api/1.0/tasks', NULL, NULL, 'Uses tasks instead of issues'),
('project.update_issue', 'asana', '{byo,agent_vault}', 'bearer', 'PUT /api/1.0/tasks/{task_gid}', NULL, NULL, NULL),
('project.list_issues', 'asana', '{byo,agent_vault}', 'bearer', 'GET /api/1.0/tasks?project={project_gid}', NULL, NULL, NULL),

-- ClickUp (AN 6.21)
('project.create_issue', 'clickup', '{byo,agent_vault}', 'bearer', 'POST /api/v2/list/{list_id}/task', NULL, NULL, 'Uses tasks in lists'),
('project.update_issue', 'clickup', '{byo,agent_vault}', 'bearer', 'PUT /api/v2/task/{task_id}', NULL, NULL, NULL),
('project.list_issues', 'clickup', '{byo,agent_vault}', 'bearer', 'GET /api/v2/list/{list_id}/task', NULL, NULL, NULL),

-- GitHub Issues (AN 8.40)
('project.create_issue', 'github', '{byo,agent_vault}', 'bearer', 'POST /repos/{owner}/{repo}/issues', NULL, NULL, 'Dual-purpose: devops + project management'),
('project.update_issue', 'github', '{byo,agent_vault}', 'bearer', 'PATCH /repos/{owner}/{repo}/issues/{number}', NULL, NULL, NULL),
('project.list_issues', 'github', '{byo,agent_vault}', 'bearer', 'GET /repos/{owner}/{repo}/issues', NULL, NULL, NULL)
ON CONFLICT (capability_id, service_slug) DO NOTHING;

-- Spreadsheet services
INSERT INTO capability_services (capability_id, service_slug, credential_modes, auth_method, endpoint_pattern, cost_per_call, free_tier_calls, notes) VALUES
-- Airtable (AN 7.15)
('spreadsheet.read', 'airtable', '{byo,agent_vault}', 'bearer', 'GET /v0/{baseId}/{tableIdOrName}', NULL, NULL, 'Flexible structured data store'),
('spreadsheet.write', 'airtable', '{byo,agent_vault}', 'bearer', 'POST /v0/{baseId}/{tableIdOrName}', NULL, NULL, NULL),
('spreadsheet.create', 'airtable', '{byo,agent_vault}', 'bearer', 'POST /v0/meta/bases/{baseId}/tables', NULL, NULL, NULL),
('spreadsheet.query', 'airtable', '{byo,agent_vault}', 'bearer', 'GET /v0/{baseId}/{tableIdOrName}?filterByFormula=...', NULL, NULL, 'Airtable formula-based filtering'),

-- Notion databases (AN 7.33)
('spreadsheet.read', 'notion', '{byo,agent_vault}', 'bearer', 'POST /v1/databases/{id}/query', NULL, NULL, 'Notion databases function as spreadsheets'),
('spreadsheet.write', 'notion', '{byo,agent_vault}', 'bearer', 'POST /v1/pages', NULL, NULL, 'Creates page (row) in database'),
('spreadsheet.create', 'notion', '{byo,agent_vault}', 'bearer', 'POST /v1/databases', NULL, NULL, NULL),
('spreadsheet.query', 'notion', '{byo,agent_vault}', 'bearer', 'POST /v1/databases/{id}/query', NULL, NULL, 'Rich filter + sort support')
ON CONFLICT (capability_id, service_slug) DO NOTHING;

-- Compute services (not yet scored — added as mappings for future scoring)
-- Note: E2B, Modal, Replit need to be added to services table and scored first
-- These mappings are ready for when services are added

-- ============================================================
-- NEW BUNDLE: Issue-to-Sprint Pipeline
-- ============================================================

INSERT INTO capability_bundles (id, name, description, example, value_proposition) VALUES
('project.plan_sprint', 'Plan Sprint from Issues', 'List issues → Create sprint → Assign issues to sprint', 'Pull all P0 bugs, create next sprint, assign them', 'Automated sprint planning from issue backlog — replaces manual triage')
ON CONFLICT (id) DO NOTHING;

INSERT INTO bundle_capabilities (bundle_id, capability_id, sequence_order) VALUES
('project.plan_sprint', 'project.list_issues', 1),
('project.plan_sprint', 'project.create_sprint', 2),
('project.plan_sprint', 'project.update_issue', 3)
ON CONFLICT (bundle_id, capability_id) DO NOTHING;
