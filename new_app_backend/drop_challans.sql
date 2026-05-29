-- ═══════════════════════════════════════════════════════
--  DROP SQL (If you want to remove the SQL Table)
-- ═══════════════════════════════════════════════════════

DROP TABLE IF EXISTS challans CASCADE;

-- Note: We are keeping the `legal_pdfs` table because PDFs need 
-- a table for fast searching by state, name, and categories.
