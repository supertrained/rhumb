-- Migration 0031: Org credit deduction + release RPCs
-- Phase 0 payment follow-up (WU-0.4)

CREATE OR REPLACE FUNCTION deduct_org_credits(
    p_org_id TEXT,
    p_amount_cents INTEGER,
    p_execution_id TEXT DEFAULT NULL
) RETURNS JSONB AS $$
DECLARE
    v_balance BIGINT;
    v_remaining BIGINT;
    v_ledger_id UUID;
BEGIN
    IF p_amount_cents IS NULL OR p_amount_cents <= 0 THEN
        SELECT balance_usd_cents
        INTO v_balance
        FROM org_credits
        WHERE org_id = p_org_id
        LIMIT 1;

        RETURN jsonb_build_object(
            'allowed', true,
            'remaining_cents', COALESCE(v_balance, 0),
            'ledger_id', NULL
        );
    END IF;

    -- Lock wallet row so check + decrement is atomic.
    SELECT balance_usd_cents
    INTO v_balance
    FROM org_credits
    WHERE org_id = p_org_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN jsonb_build_object(
            'allowed', false,
            'reason', 'no_org_credits',
            'balance_cents', 0
        );
    END IF;

    IF v_balance < p_amount_cents THEN
        RETURN jsonb_build_object(
            'allowed', false,
            'reason', 'insufficient_credits',
            'balance_cents', v_balance
        );
    END IF;

    v_remaining := v_balance - p_amount_cents;

    UPDATE org_credits
    SET balance_usd_cents = v_remaining,
        updated_at = now()
    WHERE org_id = p_org_id;

    INSERT INTO credit_ledger (
        org_id,
        event_type,
        amount_usd_cents,
        balance_after_usd_cents,
        capability_execution_id,
        description
    )
    VALUES (
        p_org_id,
        'debit',
        -p_amount_cents,
        v_remaining,
        p_execution_id,
        'Capability execution debit'
    )
    RETURNING id INTO v_ledger_id;

    RETURN jsonb_build_object(
        'allowed', true,
        'remaining_cents', v_remaining,
        'ledger_id', v_ledger_id::TEXT
    );
END;
$$ LANGUAGE plpgsql;


CREATE OR REPLACE FUNCTION release_org_credits(
    p_org_id TEXT,
    p_amount_cents INTEGER,
    p_execution_id TEXT DEFAULT NULL
) RETURNS JSONB AS $$
DECLARE
    v_balance BIGINT;
    v_remaining BIGINT;
    v_ledger_id UUID;
BEGIN
    IF p_amount_cents IS NULL OR p_amount_cents <= 0 THEN
        SELECT balance_usd_cents
        INTO v_balance
        FROM org_credits
        WHERE org_id = p_org_id
        LIMIT 1;

        RETURN jsonb_build_object(
            'released', true,
            'idempotent', true,
            'remaining_cents', COALESCE(v_balance, 0),
            'ledger_id', NULL
        );
    END IF;

    -- Lock wallet row so idempotency check + refund stays consistent.
    SELECT balance_usd_cents
    INTO v_balance
    FROM org_credits
    WHERE org_id = p_org_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN jsonb_build_object(
            'released', false,
            'reason', 'no_org_credits',
            'balance_cents', 0
        );
    END IF;

    -- Idempotent replay: if already released for this execution, no-op.
    IF p_execution_id IS NOT NULL AND EXISTS (
        SELECT 1
        FROM credit_ledger
        WHERE org_id = p_org_id
          AND capability_execution_id = p_execution_id
          AND event_type = 'reservation_released'
        LIMIT 1
    ) THEN
        RETURN jsonb_build_object(
            'released', true,
            'idempotent', true,
            'remaining_cents', v_balance,
            'ledger_id', NULL
        );
    END IF;

    -- Safety: only release if there was a matching debit when execution_id is provided.
    IF p_execution_id IS NOT NULL AND NOT EXISTS (
        SELECT 1
        FROM credit_ledger
        WHERE org_id = p_org_id
          AND capability_execution_id = p_execution_id
          AND event_type = 'debit'
          AND amount_usd_cents = -p_amount_cents
        LIMIT 1
    ) THEN
        RETURN jsonb_build_object(
            'released', false,
            'reason', 'no_matching_debit',
            'balance_cents', v_balance
        );
    END IF;

    v_remaining := v_balance + p_amount_cents;

    UPDATE org_credits
    SET balance_usd_cents = v_remaining,
        updated_at = now()
    WHERE org_id = p_org_id;

    INSERT INTO credit_ledger (
        org_id,
        event_type,
        amount_usd_cents,
        balance_after_usd_cents,
        capability_execution_id,
        description
    )
    VALUES (
        p_org_id,
        'reservation_released',
        p_amount_cents,
        v_remaining,
        p_execution_id,
        'Capability execution refund/release'
    )
    RETURNING id INTO v_ledger_id;

    RETURN jsonb_build_object(
        'released', true,
        'idempotent', false,
        'remaining_cents', v_remaining,
        'ledger_id', v_ledger_id::TEXT
    );
END;
$$ LANGUAGE plpgsql;
