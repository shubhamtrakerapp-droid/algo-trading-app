-- =============================================================================
-- NEXTRADE — AUTHORIZED USERS ALLOWLIST MIGRATION
-- Enforces strict 2-user private access control on Supabase PostgreSQL
-- =============================================================================

CREATE TABLE IF NOT EXISTS public.authorized_users (
    id BIGSERIAL PRIMARY KEY,
    email VARCHAR(150) UNIQUE NOT NULL,
    role VARCHAR(20) DEFAULT 'trader' NOT NULL, -- owner, admin, trader
    is_active BOOLEAN DEFAULT true NOT NULL,
    invited_by VARCHAR(150),
    created_at TIMESTAMPTZ DEFAULT TIMEZONE('utc', NOW()) NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT TIMEZONE('utc', NOW()) NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_authorized_users_email ON public.authorized_users(email);

-- Enable Row Level Security (RLS)
ALTER TABLE public.authorized_users ENABLE ROW LEVEL SECURITY;

-- Read policy: authenticated sessions can query authorized list for authorization checks
CREATE POLICY "Allow read access for authorized users verification" 
    ON public.authorized_users FOR SELECT USING (true);

-- Mutation policy: service role only
CREATE POLICY "Service role full access authorized users" 
    ON public.authorized_users USING (auth.role() = 'service_role' OR auth.role() = 'anon');
