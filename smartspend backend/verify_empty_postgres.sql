-- Read-only observation only. Does not migrate or authorize a backup exemption.
-- Run in the existing project's SQL editor; no credentials or user rows emitted.
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL statement_timeout = '15s';
DO $$
DECLARE
    relation record;
    populated boolean;
    checked integer := 0;
    nonempty integer := 0;
    versions integer[];
    names text[];
BEGIN
    SELECT array_agg(c.relname::text ORDER BY c.relname) INTO names
    FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
    WHERE n.nspname='smartspend' AND c.relkind IN ('r','p');
    IF names IS NULL OR NOT names @> ARRAY['users','credentials','auth_sessions',
        'transactions','budgets','bills','bill_payments','chat_messages',
        'expense_proposals','import_batches','smartspend_schema']::text[] THEN
        RAISE EXCEPTION 'Application schema incomplete; emptiness not certified';
    END IF;
    SELECT array_agg(version ORDER BY version) INTO versions FROM smartspend.smartspend_schema;
    IF versions IS DISTINCT FROM ARRAY[4] AND versions IS DISTINCT FROM ARRAY[5] THEN
        RAISE EXCEPTION 'Unexpected schema version; emptiness not certified';
    END IF;
    FOR relation IN
        SELECT c.relname, (r.rolsuper OR r.rolbypassrls OR
            (c.relowner=r.oid AND NOT c.relforcerowsecurity)) AS visible
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        CROSS JOIN pg_roles r
        WHERE n.nspname='smartspend' AND c.relkind IN ('r','p')
            AND r.rolname=current_user AND c.relname<>'smartspend_schema'
        ORDER BY c.relname
    LOOP
        IF NOT relation.visible THEN
            RAISE EXCEPTION 'Unfiltered row visibility unavailable; emptiness not certified';
        END IF;
        EXECUTE format('SELECT EXISTS (SELECT 1 FROM smartspend.%I)', relation.relname) INTO populated;
        checked := checked + 1;
        IF populated THEN nonempty := nonempty + 1; END IF;
    END LOOP;
    RAISE NOTICE 'Schema version: %, application data tables checked: %, nonempty tables: %, all empty: %',
        versions, checked, nonempty, nonempty=0;
END $$;
ROLLBACK;
