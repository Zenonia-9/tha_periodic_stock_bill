# Validation evidence

Release 19.0.1.0.5, local Docker Odoo 19.0-20260630, 2026-10-28.

## Final result

- Python AST syntax: 8 files passed.
- XML syntax: 1 manifest data file passed with lxml.
- Manifest: isolated stock_account dependency, declared data exists, version
  19.0.1.0.5. Initial installation used requested 19.0.1.0.0; subsequent installed
  corrections bumped the version as required by project AGENTS.md.
- Module Git staged diff whitespace check passed.
- Independent Mira review found a forced-foreign-account-currency closing risk.
  The focused revision rejects such stock/counterpart accounts before posting;
  Mira's recheck reported No findings.
- Scratch deployment combination: **51 tests passed, 0 failures, 0 errors**,
  2026-10-28 06:39:09 UTC, process 778, exit 0. Counts are 27 new-addon tests plus
  24 existing tha_purchase_bill_uom_valuation_fix tests. Odoo's per-module stats
  include setup/teardown and therefore show higher counts. No scenario skipped.
- Final local THA release upgrade: **27 tests passed, 0 failures, 0 errors**, 2026-10-28 06:41:17 UTC, process 787, exit 0 (44.59 seconds); no scenario skipped.
- Final restart, last 300 project log lines, and read-only accounting/default-off
  verification: confirmed by the coordinator; restart succeeded, registry/HTTP ready, no post-restart ERROR or CRITICAL; details below.

## Environments and commands

Local THA originally had tha_stock_costing 19.0.1.7.0 installed. The 24-test
compatibility run passed there before the final native-closing guards were added.

The user clarified that the remote live database uses
tha_purchase_bill_uom_valuation_fix, not tha_stock_costing. A separate retained
local database, THA_periodic_stock_bill_native_20261028, was created for that
combination. An ORM check confirmed tha_purchase_bill_uom_valuation_fix
19.0.1.0.5 installed and tha_stock_costing uninstalled. No THA addon was uninstalled.
The new addon depends on neither optional addon.

Initial scratch installation passed 48 tests (24 new + 24 existing). The final
consistent release run used:

```powershell
docker exec odoo_19 odoo -d THA_periodic_stock_bill_native_20261028 -u tha_periodic_stock_bill,tha_purchase_bill_uom_valuation_fix --stop-after-init --http-port=8079 --gevent-port=8089 --max-cron-threads=0 --test-enable --test-tags /tha_periodic_stock_bill,/tha_purchase_bill_uom_valuation_fix
```

Both modules must be named in -u for both post-install suites to execute.
The initial scratch installer let the main server discover its database and run
scheduled jobs; unrelated attachment garbage collection hit a lock timeout while
tests held transactions. After installation, 32 scheduled jobs were disabled by
ORM **only in the scratch database**, guarded by an exact database-name assertion.
The final consistent test run completed successfully. The scratch database is
retained; no database cleanup/deletion was performed.

The first module installation used -i in THA. Subsequent versions used -u:

```powershell
docker exec odoo_19 odoo -d THA -u tha_periodic_stock_bill --stop-after-init --http-port=8079 --gevent-port=8089 --max-cron-threads=0 --test-enable --test-tags /tha_periodic_stock_bill
```

## New-addon scenario coverage

All tests are TransactionCase tests using rollback-only accounting/stock fixtures.

| Test method (prefix test_) | Asserted behavior |
| --- | --- |
| enabled_disabled_and_prospective_drafts | Disabled native expense, enabled stock, old draft preserved after enabling and posting |
| company_isolation_and_effective_periodic | Company-specific flag and effective company valuation fallback |
| bill_defaults_follow_document_company | Real bills use document-company expense/stock and configuration; other company isolated |
| company_fallback | Native company stock-account fallback |
| service_and_perpetual_are_native | Service expense and native perpetual stock behavior |
| manual_account_edit_is_preserved | Explicit manual expense override survives posting |
| vendor_refund_and_reversal | Vendor refund and bill reversal credit stock |
| fiscal_mapping_and_native_closing_limit | Mapped draft default preserved, changed stock mapping blocks posting, identity mapping posts |
| missing_stock_fails_before_post | Missing category/company/fallback stock blocks posting |
| missing_counterpart_and_journal_fail_before_post | Missing closing counterpart and company journal block posting |
| missing_company_stock_default_blocks_posting | Native closing company default required even with explicit category account |
| invalid_account_type_and_inactive_counterpart | Non-inventory stock type and archived counterpart rejected |
| inactive_stock_account_is_rejected | Archived stock account rejected before posting |
| counterpart_company_is_checked | Foreign-company closing account rejected |
| stock_account_expense_fallback_does_not_require_company_expense | Stock-account closing expense is used without requiring a matching company default |
| foreign_restricted_accounts_block_before_posting | Foreign-currency-restricted counterpart or stock account rejected, including foreign-currency bill |
| taxes_discount_and_foreign_currency | Native purchase tax, discount, payable, balancing and foreign amount retained |
| customer_invoice_keeps_native_income_without_cogs | Customer invoice retains income and has no periodic COGS lines |
| purchase_all_stock_remaining | Purchase 324,000, remaining 324,000, no consumption adjustment |
| purchase_half_stock_remaining_and_repeat_public_closing | Actual native public closing posts expense 162,000, repeat has no duplicate |
| purchase_none_remaining | Purchase 324,000, no stock, expense 324,000 |
| opening_balances_and_consumption | Opening stock/ledger plus purchase and consumption reconcile |
| historical_expense_bill_capitalization | Posted historical expense bill preserved; native closing capitalizes remaining stock |
| partial_receipt_billing_and_price_difference | Partial standalone receipt at cost 3,000 versus bill at 3,240 includes quantity/price timing difference |
| partial_bill_full_receipt | Partial billing/full receipt capitalizes native difference, no duplicate after posting |
| supplier_return_with_credit_note | Physical supplier return and vendor credit note reconcile with remaining valuation |
| po_bottle_test_uom_avco | Actual PO-generated bill defaults to stock; 10 bottles of 10 tests become 100 stock units, AVCO 324,000 then half consumption 162,000 |

The price-difference fixture explicitly sets the product cost before a standalone
receipt. An unlinked stock.move.price_unit is not its native valuation source;
the receipt uses the product cost. No valuation override was added to this addon.

The existing UoM-fix suite additionally covers fractional conversion, bill-date
cutoff, refunds, partial billing, current-native allocation passthrough and repair
preview/rollback boundaries. Its legacy-algorithm tests use explicit controlled
patches; the new addon PO integration runs the installed native implementation.

## Corrections during validation

The initial 21-test run had fixture/API errors (stock.move has no name field on
this Odoo build) and a transient variable mismatch caused by a delayed patch
tool write. Those were corrected. A later single valuation-fixture expectation
was corrected to set the actual native product cost, then 24 tests passed.
The .4 missing-company-default test needed to reassign a category override
after clearing its company-dependent fallback; the .5 fixture now isolates that
specific guard. Earlier failed runs are superseded by the final results above.

The local runtime's native closing implementation falls back from the stock
account Variation Account to the company Expense Account. The addon now
preserves account-level closing for feature-enabled periodic stock accounts by
using each account's Variation Account, then its Expense Account. This is
covered by the rollback-only partial-consumption test; it does not post a live
closing entry or reconcile existing production balances.

## Remaining limits

- No remote live database deployment, configuration mutation, or live accounting
  reconciliation was performed. Local test results do not establish remote
  runtime/source parity.
- Histopathology is enabled in local THA and the affected bill is posted. Its
  existing balances still need account-wide reconciliation before actual close.
- Stock-account Expense Account 600186 is now used by the addon closing override
  for enabled periodic stock categories; the actual company close was not run.
- The closing probe did not commit a new closing move; bill 4513 remains posted.
- The addon does not repair existing posted entries, stock valuation, old drafts,
  purchase UoM defects, or physical usage records. Native closing can include
  timing and price differences as well as consumption.


## Local THA product closing probe, 2026-10-28

Addon 19.0.1.0.8 was upgraded in THA and its focused Odoo suite completed with
27 tests passing and no failures. That suite exercised the public company closing
action in rollback fixtures; the actual-product calculation is reported below.

For product 6196, [[HP 0021]] Confirm Anti-ER, category Histopathology, company
Shop Sphere:

- Bill 4513 is posted for 324,000 MMK to stock account 8487 / 140120.
- Current on-hand quantity is 300 Test units, valuation 972,000, and the posted
  stock-account balance is also 972,000. The product-specific closing
  calculation therefore returns no adjustment today.
- In a rollback-only half-stock scenario, remaining product value of 486,000
  produces Dr 600186 / Cr 140120 for 486,000. The stock-account-specific
  closing fallback works while the company Expense Account is blank.
- The current full-company close calculation proposes a separate
  5,371,160 Dr 140120 / Cr 600186 adjustment. This is an account-wide inventory
  versus ledger difference across products using that account; no close move
  was created. Reconcile that account's full product/category balances before
  running the actual company closing action.

Shop Sphere's Stock Journal is set to journal 211, Inventory Valuation, and its
company Stock Valuation Account is 8487. The company Expense Account remains
blank. No closing move was posted during the product probe.

## Restart and project logs

After the 19.0.1.0.8 upgrade and focused tests, the Odoo service restart and
project-log review are recorded in the task completion notes. The full-company
closing calculation above is read-only; it is not approval to post the proposed
5,371,160 adjustment.
