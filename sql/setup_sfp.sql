-- ── Statement of Financial Position Presentation Layer ────────────────────────
-- Run once to set up the FS structure and account mappings.
-- Re-run at any time to reset (DROP + recreate).

DROP TABLE IF EXISTS sfp_line_accounts;
DROP TABLE IF EXISTS sfp_lines;

-- ── sfp_lines: defines the FS structure and presentation names ─────────────────
CREATE TABLE sfp_lines (
  id            INT          NOT NULL PRIMARY KEY,
  section_order TINYINT      NOT NULL,
  section_label VARCHAR(80)  NOT NULL,
  group_order   TINYINT      NOT NULL,
  group_label   VARCHAR(80)  NOT NULL,
  line_order    INT          NOT NULL,
  line_label    VARCHAR(120) NOT NULL,
  sign          TINYINT      NOT NULL DEFAULT 1   -- 1=asset, -1=liability/equity
);

-- ── sfp_line_accounts: maps QBO account IDs to FS lines (many-to-one) ──────────
CREATE TABLE sfp_line_accounts (
  sfp_line_id  INT NOT NULL,
  account_id   INT NOT NULL,
  PRIMARY KEY (sfp_line_id, account_id),
  FOREIGN KEY (sfp_line_id) REFERENCES sfp_lines(id)
);

-- ══════════════════════════════════════════════════════════════════════════════
-- ASSETS  (sign = 1)
-- ══════════════════════════════════════════════════════════════════════════════

INSERT INTO sfp_lines (id, section_order, section_label, group_order, group_label, line_order, line_label, sign) VALUES
-- Current Assets
( 1, 1, 'ASSETS', 1, 'Current Assets',  10, 'Cash and Cash Equivalents',     1),
( 2, 1, 'ASSETS', 1, 'Current Assets',  20, 'Short-term Investments',         1),
( 3, 1, 'ASSETS', 1, 'Current Assets',  30, 'Pledges Receivable, net',        1),
( 4, 1, 'ASSETS', 1, 'Current Assets',  40, 'Accounts Receivable',            1),
( 5, 1, 'ASSETS', 1, 'Current Assets',  50, 'GST Receivable',                 1),
( 6, 1, 'ASSETS', 1, 'Current Assets',  60, 'Interest Receivable',            1),
( 7, 1, 'ASSETS', 1, 'Current Assets',  70, 'Prepaid Expenses',               1),
-- Long-term Assets
( 8, 1, 'ASSETS', 2, 'Long-term Assets', 10, 'Investment in 211 Saskatchewan', 1),
( 9, 1, 'ASSETS', 2, 'Long-term Assets', 20, 'Property, Plant and Equipment, net', 1);

-- ── Account mappings — ASSETS ──────────────────────────────────────────────────

-- Line 1: Cash and Cash Equivalents
INSERT INTO sfp_line_accounts (sfp_line_id, account_id) VALUES
(1, 85),           -- 10005 TD Canada Trust - Operating
(1, 86),           -- 10006 TD Canada Trust - Lottery Account
(1, 87),           -- 10010 Affinity Credit Union
(1, 88),           -- 10015 Deposit Clearing
(1, 89),           -- 10030 Petty Cash
(1, 1150040000),   -- 10040 Float Financial
(1, 1150040063);   -- 10050 Float Clearing - Float Cash

-- Line 2: Short-term Investments
INSERT INTO sfp_line_accounts (sfp_line_id, account_id) VALUES
(2, 90);           -- 11000 Short term Investments

-- Line 3: Pledges Receivable, net  (Allowance 12070 has negative balance — nets naturally)
INSERT INTO sfp_line_accounts (sfp_line_id, account_id) VALUES
(3, 91),           -- 12009 Prior Year 2 Pledges Receivable
(3, 92),           -- 12010 Prior Year 1 Pledges Receivable
(3, 93),           -- 12011 Current Year Pledges Receivable
(3, 94),           -- 12040 Prior Year 2 Prince Albert PldgRec
(3, 95),           -- 12041 Prior Year 1 Prince Albert PldgRec
(3, 96),           -- 12042 Current Year Prince Albert PldgRec
(3, 97);           -- 12070 Allowance for Doubtful Accounts (contra — negative nets)

-- Line 4: Accounts Receivable
INSERT INTO sfp_line_accounts (sfp_line_id, account_id) VALUES
(4, 84),           -- Accounts Receivable (QBO system)
(4, 99),           -- 12200 Accounts Receivable - History
(4, 100),          -- 12201 Accounts Receivable - Credit Card
(4, 101),          -- 12202 Accounts Receivable - Other
(4, 1150040016);   -- 12205 Employee Personal Expense (Reimbursable)

-- Line 5: GST Receivable
INSERT INTO sfp_line_accounts (sfp_line_id, account_id) VALUES
(5, 98);           -- 12100 GST Receivable

-- Line 6: Interest Receivable
INSERT INTO sfp_line_accounts (sfp_line_id, account_id) VALUES
(6, 102);          -- 12300 Interest Accrued

-- Line 7: Prepaid Expenses
INSERT INTO sfp_line_accounts (sfp_line_id, account_id) VALUES
(7, 104);          -- 15000 Prepaid Expense

-- Line 8: Investment in 211 Saskatchewan
INSERT INTO sfp_line_accounts (sfp_line_id, account_id) VALUES
(8, 103);          -- 12500 Investment in 211 Saskatchewan

-- Line 9: Property, Plant and Equipment, net
--         (Accum Dep 17xxx stored negative in QBO — nets against gross naturally)
INSERT INTO sfp_line_accounts (sfp_line_id, account_id) VALUES
(9, 105),          -- 16100 Equipment - Office
(9, 106),          -- 16200 Equipment - Computer Hardware
(9, 107),          -- 16300 Equipment - Computer Software
(9, 108),          -- 16500 Leasehold Improvements
(9, 109),          -- 17150 Accum Dep - Office Equipment
(9, 110),          -- 17250 Accum Dep - Computer Hardware
(9, 111),          -- 17350 Accum Dep - Computer Software
(9, 112);          -- 17550 Accum Dep - Leasehold Improvements

-- ══════════════════════════════════════════════════════════════════════════════
-- LIABILITIES  (sign = -1)
-- ══════════════════════════════════════════════════════════════════════════════

INSERT INTO sfp_lines (id, section_order, section_label, group_order, group_label, line_order, line_label, sign) VALUES
(10, 2, 'LIABILITIES', 1, 'Current Liabilities', 10, 'Accounts Payable',               -1),
(11, 2, 'LIABILITIES', 1, 'Current Liabilities', 20, 'Accrued Liabilities',             -1),
(12, 2, 'LIABILITIES', 1, 'Current Liabilities', 30, 'Credit Cards Payable',            -1),
(13, 2, 'LIABILITIES', 1, 'Current Liabilities', 40, 'Allocations to Funded Agencies',  -1),
(14, 2, 'LIABILITIES', 1, 'Current Liabilities', 50, 'Donor Directed Giving',           -1),
(15, 2, 'LIABILITIES', 1, 'Current Liabilities', 60, 'Deferred Revenue',                -1);

-- ── Account mappings — LIABILITIES ────────────────────────────────────────────

-- Line 10: Accounts Payable
INSERT INTO sfp_line_accounts (sfp_line_id, account_id) VALUES
(10, 83);          -- Accounts Payable (QBO system)

-- Line 11: Accrued Liabilities
INSERT INTO sfp_line_accounts (sfp_line_id, account_id) VALUES
(11, 113),         -- 20005 Accounts Payable - History
(11, 114),         -- 20006 Accounts Payable - Other
(11, 115),         -- 20007 Accounts Payable - CCC Designations
(11, 116),         -- 20010 PST Payable
(11, 118),         -- 20060 Cash - Staff Fund
(11, 300),         -- GST/HST Payable
(11, 302);         -- PST Payable (SK)

-- Line 12: Credit Cards Payable
INSERT INTO sfp_line_accounts (sfp_line_id, account_id) VALUES
(12, 117),         -- 20015 TD Visa Payable
(12, 306);         -- TD Credit Card - Sheri

-- Line 13: Allocations to Funded Agencies
INSERT INTO sfp_line_accounts (sfp_line_id, account_id) VALUES
(13, 119);         -- 21000 Allocations to Agencies

-- Line 14: Donor Directed Giving
INSERT INTO sfp_line_accounts (sfp_line_id, account_id) VALUES
(14, 120),         -- 22010 Def. Rev. Donor Dir. Giving 2025
(14, 121),         -- 22015 Def. Rev. Donor Dir. Giving 2022
(14, 122),         -- 22020 Def. Rev. Donor Dir. Giving 2023
(14, 123);         -- 22025 Def. Rev. Donor Dir. Giving 2024

-- Line 15: Deferred Revenue
INSERT INTO sfp_line_accounts (sfp_line_id, account_id) VALUES
(15, 124);         -- 23029 Deferred Revenue - general

-- ══════════════════════════════════════════════════════════════════════════════
-- NET ASSETS  (sign = -1)
-- ══════════════════════════════════════════════════════════════════════════════

INSERT INTO sfp_lines (id, section_order, section_label, group_order, group_label, line_order, line_label, sign) VALUES
(16, 3, 'NET ASSETS', 1, 'Net Assets', 10, 'Unrestricted Net Assets',        -1),
(20, 3, 'NET ASSETS', 1, 'Net Assets', 15, 'Current Year Surplus (Deficit)', -1),
(17, 3, 'NET ASSETS', 1, 'Net Assets', 20, 'Operating Reserve',              -1),
(18, 3, 'NET ASSETS', 1, 'Net Assets', 30, 'Capital Replacement Reserve',    -1),
(19, 3, 'NET ASSETS', 1, 'Net Assets', 40, 'Community Investment Reserve',   -1);

-- ── Account mappings — NET ASSETS ─────────────────────────────────────────────

-- Line 16: Unrestricted Net Assets (prior year retained earnings only)
INSERT INTO sfp_line_accounts (sfp_line_id, account_id) VALUES
(16, 70),          -- Retained Earnings (QBO system)
(16, 79);          -- Opening Balance (QBO system)

-- Line 20: Current Year Surplus (Deficit) — populated by fetch_sfp_data.py from P&L
INSERT INTO sfp_line_accounts (sfp_line_id, account_id) VALUES
(20, 125);         -- 29905 Current Earnings (current year net income)

-- Line 17: Operating Reserve
INSERT INTO sfp_line_accounts (sfp_line_id, account_id) VALUES
(17, 126);         -- 29910 Operating Reserve

-- Line 18: Capital Replacement Reserve
INSERT INTO sfp_line_accounts (sfp_line_id, account_id) VALUES
(18, 127);         -- 29930 Capital Replacement Reserve

-- Line 19: Community Investment Reserve
INSERT INTO sfp_line_accounts (sfp_line_id, account_id) VALUES
(19, 128);         -- 29950 Community Investment Reserve
