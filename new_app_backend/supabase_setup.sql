-- ═══════════════════════════════════════════════════════
--  SUPABASE SETUP SQL
--  Run in: Supabase Dashboard -> SQL Editor -> New Query
--  Project: uzvywflybfafameoqwhp
-- ═══════════════════════════════════════════════════════

-- ═════════════════════════════════════════════
--  TABLE 1: challans (traffic fine data)
--  Skip if you already created this table
-- ═════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS challans (
  id BIGSERIAL PRIMARY KEY,
  country TEXT NOT NULL DEFAULT 'India',
  state_name TEXT NOT NULL DEFAULT 'National',
  offense TEXT NOT NULL,
  keywords TEXT[] NOT NULL DEFAULT '{}',
  section TEXT DEFAULT 'N/A',
  description TEXT DEFAULT '',
  fine_amount INTEGER DEFAULT 0,
  first_offense TEXT,
  repeat_offense TEXT,
  imprisonment TEXT,
  vehicle_type TEXT DEFAULT 'all',
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- RLS: Public read, service role full access
ALTER TABLE challans ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Allow public read challans" ON challans;
CREATE POLICY "Allow public read challans" ON challans FOR SELECT USING (true);
DROP POLICY IF EXISTS "Allow service role all challans" ON challans;
CREATE POLICY "Allow service role all challans" ON challans FOR ALL USING (true) WITH CHECK (true);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_challans_country_state ON challans(country, state_name);
CREATE INDEX IF NOT EXISTS idx_challans_keywords ON challans USING GIN(keywords);


-- ═════════════════════════════════════════════
--  TABLE 2: legal_pdfs (PDF document metadata)
--  This is the NEW table for Legal PDFs
-- ═════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS legal_pdfs (
  id BIGSERIAL PRIMARY KEY,
  filename TEXT NOT NULL,
  display_name TEXT NOT NULL,
  category TEXT DEFAULT 'General',
  country TEXT DEFAULT 'India',
  state_name TEXT DEFAULT 'ALL',
  file_size_bytes BIGINT DEFAULT 0,
  file_url TEXT NOT NULL,
  storage_path TEXT NOT NULL,
  uploaded_by TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- RLS: Public read, service role full access
ALTER TABLE legal_pdfs ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Allow public read pdfs" ON legal_pdfs;
CREATE POLICY "Allow public read pdfs" ON legal_pdfs FOR SELECT USING (true);
DROP POLICY IF EXISTS "Allow service role all pdfs" ON legal_pdfs;
CREATE POLICY "Allow service role all pdfs" ON legal_pdfs FOR ALL USING (true) WITH CHECK (true);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_legal_pdfs_state ON legal_pdfs(state_name);
CREATE INDEX IF NOT EXISTS idx_legal_pdfs_name ON legal_pdfs(display_name);


-- ═════════════════════════════════════════════
--  STORAGE BUCKET: legal-pdfs
--  For storing uploaded PDF files
--  NOTE: Also create this in Dashboard ->
--        Storage -> New Bucket
--        Name: legal-pdfs
--        Public: ON
--        Max size: 50MB
--        Allowed types: application/pdf
-- ═════════════════════════════════════════════

-- Storage policy: allow public download
INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES ('legal-pdfs', 'legal-pdfs', true, 52428800, ARRAY['application/pdf'])
ON CONFLICT (id) DO NOTHING;

-- Allow anyone to read files from the bucket
CREATE POLICY "Allow public read storage" ON storage.objects
  FOR SELECT USING (bucket_id = 'legal-pdfs');

-- Allow service role to upload/delete
CREATE POLICY "Allow service upload storage" ON storage.objects
  FOR INSERT WITH CHECK (bucket_id = 'legal-pdfs');

CREATE POLICY "Allow service delete storage" ON storage.objects
  FOR DELETE USING (bucket_id = 'legal-pdfs');
