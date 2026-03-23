-- Migration 0087: Sync credential_modes in capability_services with rhumb_managed_capabilities
--
-- Problem: capability_services only advertises credential_modes = ['byo'] even when
-- rhumb_managed_capabilities has an active config for the same (capability_id, service_slug).
-- This prevents the new auto-resolve feature (commit 6557568) from detecting managed availability.
--
-- Fix: For every enabled managed config, add 'rhumb_managed' to the credential_modes array
-- in the corresponding capability_services row (if not already present).

UPDATE capability_services cs
SET credential_modes = array_append(cs.credential_modes, 'rhumb_managed')
FROM rhumb_managed_capabilities rmc
WHERE rmc.capability_id = cs.capability_id
  AND rmc.service_slug = cs.service_slug
  AND rmc.enabled = true
  AND NOT ('rhumb_managed' = ANY(cs.credential_modes));
