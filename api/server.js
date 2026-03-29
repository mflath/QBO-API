const express = require("express");
const mysql   = require("mysql2/promise");
const cors    = require("cors");

const app = express();
app.use(cors());
app.use(express.json());

// ── Database connection pool ───────────────────────────────────────────────────
const pool = mysql.createPool({
  host:     process.env.DB_HOST     || "localhost",
  database: process.env.DB_NAME     || "qbo",
  user:     process.env.DB_USER     || "root",
  password: process.env.DB_PASS     || "",
  waitForConnections: true,
  connectionLimit: 10,
});

// ── Helper ─────────────────────────────────────────────────────────────────────
function buildWhere(conditions) {
  if (!conditions.length) return "";
  return "WHERE " + conditions.join(" AND ");
}

// ── GET /api/gl ────────────────────────────────────────────────────────────────
// Filters: start_date, end_date, account_id, class_name, department
app.get("/api/gl", async (req, res) => {
  try {
    const { start_date, end_date, account_id, class_name, department } = req.query;
    const conditions = [];
    const params     = [];

    if (start_date)  { conditions.push("g.txn_date >= ?");       params.push(start_date); }
    if (end_date)    { conditions.push("g.txn_date <= ?");        params.push(end_date); }
    if (account_id)  { conditions.push("g.account_id = ?");       params.push(account_id); }
    if (class_name)  { conditions.push("g.class_name = ?");       params.push(class_name); }
    if (department)  { conditions.push("g.department = ?");       params.push(department); }

    const [rows] = await pool.query(`
      SELECT
        a.id              AS account_id,
        a.acct_num        AS account_number,
        a.name            AS account_name,
        a.classification,
        a.account_type,
        DATE_FORMAT(g.txn_date, '%Y-%m-%d') AS txn_date,
        g.txn_id,
        g.doc_num,
        g.description,
        g.debit,
        g.credit,
        g.class_name,
        g.department
      FROM gl_lines g
      JOIN accounts a ON a.id = g.account_id
      ${buildWhere(conditions)}
      ORDER BY a.acct_num, a.name, g.txn_date
    `, params);

    res.json(rows);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// ── GET /api/trial-balance ─────────────────────────────────────────────────────
// Filters: start_date, end_date, account_id, classification
// Returns long-format rows: account + month_end + balance
app.get("/api/trial-balance", async (req, res) => {
  try {
    const { start_date, end_date, account_id, classification } = req.query;
    const conditions = [];
    const params     = [];

    if (start_date)      { conditions.push("mb.month_end >= ?");      params.push(start_date); }
    if (end_date)        { conditions.push("mb.month_end <= ?");       params.push(end_date); }
    if (account_id)      { conditions.push("mb.account_id = ?");      params.push(account_id); }
    if (classification)  { conditions.push("a.classification = ?");   params.push(classification); }

    const [rows] = await pool.query(`
      SELECT
        a.id              AS account_id,
        a.acct_num        AS account_number,
        a.name            AS account_name,
        a.fully_qualified_name,
        a.classification,
        a.account_type,
        DATE_FORMAT(mb.month_end, '%Y-%m-%d') AS month_end,
        mb.balance
      FROM monthly_balances mb
      JOIN accounts a ON a.id = mb.account_id
      ${buildWhere(conditions)}
      ORDER BY a.acct_num, a.name, mb.month_end
    `, params);

    res.json(rows);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// ── GET /api/trial-balance-wide ────────────────────────────────────────────────
// Returns pivoted trial balance: one row per account, one column per month-end
// Params: start_date (required), end_date (required), classification (optional)
app.get("/api/trial-balance-wide", async (req, res) => {
  function getMonthEnds(start, end) {
    const ends = [];
    const [sy, sm] = start.split("-").map(Number);
    let year = sy, month = sm;
    while (true) {
      // new Date(year, month, 0) = last day of `month` (1-based)
      const last = new Date(year, month, 0);
      const y  = last.getFullYear();
      const m  = String(last.getMonth() + 1).padStart(2, "0");
      const d  = String(last.getDate()).padStart(2, "0");
      const iso = `${y}-${m}-${d}`;
      if (iso > end) break;
      ends.push(iso);
      if (month === 12) { year++; month = 1; } else { month++; }
    }
    return ends;
  }

  try {
    const { start_date, end_date, classification } = req.query;
    if (!start_date || !end_date) {
      return res.status(400).json({ error: "start_date and end_date are required" });
    }

    const monthEnds = getMonthEnds(start_date, end_date);
    if (monthEnds.length === 0) return res.json([]);

    const conditions = [`mb.month_end IN (${monthEnds.map(() => "?").join(",")})`];
    const params     = [...monthEnds];
    if (classification) { conditions.push("a.classification = ?"); params.push(classification); }

    const [rows] = await pool.query(`
      SELECT
        a.id              AS account_id,
        a.acct_num        AS account_number,
        a.name            AS account_name,
        a.fully_qualified_name,
        a.classification,
        a.account_type,
        DATE_FORMAT(mb.month_end, '%Y-%m-%d') AS month_end,
        mb.balance
      FROM monthly_balances mb
      JOIN accounts a ON a.id = mb.account_id
      WHERE ${conditions.join(" AND ")}
      ORDER BY a.acct_num, a.name, mb.month_end
    `, params);

    // Pivot: one row per account, one property per month
    const accountMap = new Map();
    for (const row of rows) {
      if (!accountMap.has(row.account_id)) {
        accountMap.set(row.account_id, {
          account_number:       row.account_number,
          account_name:         row.account_name,
          fully_qualified_name: row.fully_qualified_name,
          classification:       row.classification,
          account_type:         row.account_type,
        });
      }
      const idx = monthEnds.indexOf(row.month_end);
      if (idx >= 0) {
        accountMap.get(row.account_id)[`m${String(idx + 1).padStart(2, "0")}`] = parseFloat(row.balance);
      }
    }

    res.json(Array.from(accountMap.values()));
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// ── GET /api/accounts ──────────────────────────────────────────────────────────
// Filters: classification, account_type, active
app.get("/api/accounts", async (req, res) => {
  try {
    const { classification, account_type, active } = req.query;
    const conditions = [];
    const params     = [];

    if (classification) { conditions.push("classification = ?");  params.push(classification); }
    if (account_type)   { conditions.push("account_type = ?");    params.push(account_type); }
    if (active !== undefined) { conditions.push("active = ?");    params.push(active === "true" ? 1 : 0); }

    const [rows] = await pool.query(`
      SELECT
        id              AS account_id,
        acct_num        AS account_number,
        name,
        fully_qualified_name,
        classification,
        account_type,
        account_subtype,
        active,
        current_balance
      FROM accounts
      ${buildWhere(conditions)}
      ORDER BY acct_num, name
    `, params);

    res.json(rows);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// ── GET /api/sfp ───────────────────────────────────────────────────────────────
// Statement of Financial Position — presentation-layer driven flat rows for ARJS
// Params: date1 (required, YYYY-MM-DD month-end), date2 (optional, comparative)
// Structure defined in sfp_lines / sfp_line_accounts tables (see sql/setup_sfp.sql)
app.get("/api/sfp", async (req, res) => {
  try {
    const { date1, date2 } = req.query;
    if (!date1) return res.status(400).json({ error: "date1 is required" });
    const d2 = date2 || null;

    // Fetch all mapped balances for both dates in one query
    const [rows] = await pool.query(`
      SELECT
        sl.id           AS line_id,
        sl.section_order,
        sl.section_label,
        sl.group_order,
        sl.group_label,
        sl.line_order,
        sl.line_label,
        sl.sign,
        sla.account_id,
        mb1.balance     AS balance1,
        mb2.balance     AS balance2
      FROM sfp_lines sl
      JOIN sfp_line_accounts sla ON sla.sfp_line_id = sl.id
      LEFT JOIN monthly_balances mb1
        ON mb1.account_id = sla.account_id
        AND DATE_FORMAT(mb1.month_end, '%Y-%m-%d') = ?
      LEFT JOIN monthly_balances mb2
        ON mb2.account_id = sla.account_id
        AND DATE_FORMAT(mb2.month_end, '%Y-%m-%d') = ?
      ORDER BY sl.section_order, sl.group_order, sl.line_order
    `, [date1, d2]);

    // Accumulate balances into section → group → line hierarchy
    const sections = new Map();

    for (const row of rows) {
      if (!sections.has(row.section_order)) {
        sections.set(row.section_order, { label: row.section_label, groups: new Map() });
      }
      const section = sections.get(row.section_order);

      if (!section.groups.has(row.group_order)) {
        section.groups.set(row.group_order, { label: row.group_label, lines: new Map() });
      }
      const group = section.groups.get(row.group_order);

      if (!group.lines.has(row.line_id)) {
        group.lines.set(row.line_id, {
          label: row.line_label, order: row.line_order, sign: row.sign,
          balance1: 0, balance2: 0, has1: false, has2: false
        });
      }
      const line = group.lines.get(row.line_id);

      if (row.balance1 !== null) { line.balance1 += parseFloat(row.balance1) * row.sign; line.has1 = true; }
      if (row.balance2 !== null) { line.balance2 += parseFloat(row.balance2) * row.sign; line.has2 = true; }
    }

    // Build flat output array
    const output = [];
    const sectionTotals = new Map();

    for (const [, section] of [...sections.entries()].sort((a, b) => a[0] - b[0])) {
      output.push({ type: "section_header", label: section.label, balance1: null, balance2: null, variance: null, pct_change: null });
      let secTotal1 = 0, secTotal2 = 0;

      for (const [, group] of [...section.groups.entries()].sort((a, b) => a[0] - b[0])) {
        const linesSorted = [...group.lines.values()].sort((a, b) => a.order - b.order);
        const visibleLines = linesSorted.filter(l => l.has1 || l.has2);
        if (visibleLines.length === 0) continue;

        output.push({ type: "subsection_header", label: group.label, balance1: null, balance2: null, variance: null, pct_change: null });
        let grpTotal1 = 0, grpTotal2 = 0;

        for (const line of visibleLines) {
          const b1 = line.has1 ? parseFloat(line.balance1.toFixed(2)) : null;
          const b2 = (d2 && line.has2) ? parseFloat(line.balance2.toFixed(2)) : null;
          const variance  = (b1 !== null && b2 !== null) ? parseFloat((b1 - b2).toFixed(2)) : null;
          const pct_change = (variance !== null && b2 !== 0) ? parseFloat(((variance / Math.abs(b2)) * 100).toFixed(1)) : null;
          output.push({ type: "account", label: line.label, balance1: b1, balance2: b2, variance, pct_change });
          grpTotal1 += b1 ?? 0;
          grpTotal2 += b2 ?? 0;
        }

        const gv = d2 ? parseFloat((grpTotal1 - grpTotal2).toFixed(2)) : null;
        const gp = (gv !== null && grpTotal2 !== 0) ? parseFloat(((gv / Math.abs(grpTotal2)) * 100).toFixed(1)) : null;
        output.push({ type: "subsection_total", label: `Total ${group.label}`,
          balance1: parseFloat(grpTotal1.toFixed(2)), balance2: d2 ? parseFloat(grpTotal2.toFixed(2)) : null,
          variance: gv, pct_change: gp });
        secTotal1 += grpTotal1;
        secTotal2 += grpTotal2;
      }

      const sv = d2 ? parseFloat((secTotal1 - secTotal2).toFixed(2)) : null;
      const sp = (sv !== null && secTotal2 !== 0) ? parseFloat(((sv / Math.abs(secTotal2)) * 100).toFixed(1)) : null;
      output.push({ type: "section_total", label: `TOTAL ${section.label}`,
        balance1: parseFloat(secTotal1.toFixed(2)), balance2: d2 ? parseFloat(secTotal2.toFixed(2)) : null,
        variance: sv, pct_change: sp });
      sectionTotals.set(section.label, { b1: secTotal1, b2: secTotal2 });
    }

    const liab = sectionTotals.get("LIABILITIES") ?? { b1: 0, b2: 0 };
    const eq   = sectionTotals.get("NET ASSETS")  ?? { b1: 0, b2: 0 };
    const gt1  = parseFloat((liab.b1 + eq.b1).toFixed(2));
    const gt2  = d2 ? parseFloat((liab.b2 + eq.b2).toFixed(2)) : null;
    const gtv  = d2 ? parseFloat((gt1 - gt2).toFixed(2)) : null;
    const gtp  = (gtv !== null && gt2 !== 0) ? parseFloat(((gtv / Math.abs(gt2)) * 100).toFixed(1)) : null;
    output.push({ type: "grand_total", label: "TOTAL LIABILITIES AND NET ASSETS",
      balance1: gt1, balance2: gt2, variance: gtv, pct_change: gtp });

    res.json(output);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// ── GET /api/filters ───────────────────────────────────────────────────────────
// Returns distinct values for filter dropdowns
app.get("/api/filters", async (req, res) => {
  try {
    const [[classes], [departments], [classifications]] = await Promise.all([
      pool.query("SELECT DISTINCT class_name FROM gl_lines WHERE class_name != '' ORDER BY class_name"),
      pool.query("SELECT DISTINCT department FROM gl_lines WHERE department != '' ORDER BY department"),
      pool.query("SELECT DISTINCT classification FROM accounts WHERE classification != '' ORDER BY classification"),
    ]);

    res.json({
      classes:         classes.map(r => r.class_name),
      departments:     departments.map(r => r.department),
      classifications: classifications.map(r => r.classification),
    });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// ── Start ──────────────────────────────────────────────────────────────────────
const PORT = process.env.PORT || 3001;
app.listen(PORT, () => {
  console.log(`QBO API running at http://localhost:${PORT}`);
  console.log(`  GET /api/gl              — GL detail`);
  console.log(`  GET /api/trial-balance   — monthly balances`);
  console.log(`  GET /api/accounts        — chart of accounts`);
  console.log(`  GET /api/filters         — filter dropdown values`);
});
