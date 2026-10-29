# THA Periodic Stock Vendor Bills

Version 19.0.1.0.8 (initial install: 19.0.1.0.0). Depends only on stock_account.

Selected company/category combinations default storable, effectively Periodic
vendor bill and credit-note product lines to the native stock valuation account.
AVCO and Periodic valuation are unchanged. Native taxes, discounts, payable,
currency conversion, refunds, PO billing and manual account editing remain in use.
The addon creates no consumption entries during bill posting and no customer-invoice COGS entries; consumption expense is recognized at closing.

## Configuration and rollout

1. In the intended company, reconcile the entire stock account: opening balance,
   historical expense-based purchases, receipts, bills, returns, physical usage,
   valuation and any other category/product using the account. Native closing
   works by account, not independently by category.
2. Keep Inventory Valuation = Periodic and Cost Method = AVCO on the category
   (or verify their effective company fallback).
3. Keep the ordinary category/product Expense Account correctly configured.
   This addon does not replace it. Disabled categories retain native account
   selection, even when their existing Expense Account is itself a stock account.
4. Set a valid Stock Account (category, native property fallback, or company).
   It must be active, valid for the document company, and Current Assets.
   Stock and closing counterpart accounts must have no forced foreign currency;
   native closing entries use the company currency. Foreign-currency bills
   remain supported on unrestricted accounts.
5. Configure a valid closing Variation Account or stock-account Expense
   Account for every stock account used by enabled categories. For those enabled
   periodic stock accounts, the addon uses the account's Variation Account, then
   its own Expense Account during closing. This keeps category ledgers separate
   even on Odoo builds whose native fallback is company-wide. Closing remains
   account-based, so reconcile every product/category sharing each account.
6. Configure the company's native Stock Journal: active Miscellaneous journal
   valid for that company. Category stock journal alone does not supply the
   journal used by res.company.action_close_stock_valuation.
7. Set a valid company Stock Valuation Account as well; the running native
   closing action requires it even when a category supplies its own account.
8. Run the scenario in a test transaction/staging copy and reconcile the ledger.
   Only then may an accounting manager enable Stock Account on Vendor Bills
   on the category in the selected company.

Installation does not enable any category, modify accounts/journals, rewrite
posted bills, or request recomputation of existing draft accounts. Changing
products/fiscal positions in a draft still invokes normal native defaulting.
Manual account overrides remain permitted; posting validates the enabled
configuration without forcing the line back to stock.

## Fiscal positions

The draft default uses native fiscal-position account mapping. As confirmed for
this rollout, posting is blocked when that mapping changes the stock account.
Native closing aggregates each product's original stock account and ignores
fiscal-position account mapping; allowing a different mapped stock account could
leave its bill debit outside closing and overstate inventory. Remove the stock
account mapping before posting and recreate/reselect the line through normal
native editing, or disable this feature and reconcile the accounting setup.
Identity mappings are allowed.

## Closing

Record physical reagent usage with stock operations. Run native inventory
closing in the correct company and period. Native closing compares remaining
inventory valuation with the posted stock-account balance, including vendor bill
debits and previous posted closings.

With no opening balance, tax or other movement:

| State after purchase of 324,000 | Remaining value | Closing consumption expense |
| --- | ---: | ---: |
| All stock remaining | 324,000 | 0 |
| Half remaining | 162,000 | 162,000 |
| No stock remaining | 0 | 324,000 |

The bill is Dr Stock / Cr Payable. For half remaining the closing is
Dr Consumption Expense 162,000 / Cr Stock 162,000. Post the first closing before
repeating it; unchanged valuation/ledger yields no second adjustment.

Opening balances and historical expense bills require account-wide
reconciliation. Closing can capitalize historical expense purchases or adjust
for unmatched receipt/bill quantities and price differences; its result is not
necessarily consumption alone. Until closing, the stock ledger may differ from
physical stock valuation.

## Read-only local THA baseline, 2026-10-28

Pip inspected local THA runtime facts before installation using a read-only ORM
transaction. These are not assertions about the remote live database:

- Affected matching setup: Shop Sphere, company 4; Histopathology, category 142.
- Effective valuation Periodic, costing AVCO.
- Stock account 8487 / 140120: active Current Assets, company 4.
- Category Expense Account is also 8487 / 140120. This is an existing mapping;
  native behavior can already debit stock even with the new feature disabled.
- Native stock closing Expense Account and Variation Account are both blank.
- Company and category Stock Journal are both blank.
- Final read-only verification also confirms company Expense Account is blank.
- Company default Stock Valuation Account is blank; the running native closing
  action also requires this default.
- Proposed expense 8486 / 600186: active Cost of Revenue, company 4.
- Posted stock ledger: debit 648,000, credit 0, two lines.
- Proposed consumption expense ledger: debit 324,000, credit 0, one line.
- Matching storable product: quantity 200, valuation 648,000.
- Category 142 is the only category explicitly mapped to stock account 8487;
  fallback mappings and all posted balances still need reconciliation.
- No native closing move found for company 4.
- tha_stock_costing installed at 19.0.1.7.0.

**Activation is not complete.** The missing closing counterpart/journal,
company default stock account, dual expense fallback alignment and existing
balances must be resolved and reconciled before enabling Histopathology.
These local settings and accounting records were not changed by this addon.
No remote deployment or remote configuration change was performed.

## Installation and checks

New install:

```powershell
docker exec odoo_19 odoo -d THA -i tha_periodic_stock_bill --stop-after-init --http-port=8079 --gevent-port=8089 --max-cron-threads=0 --test-enable --test-tags /tha_periodic_stock_bill
docker restart odoo_19
Get-Content .\logs\server.log -Tail 300
```

Use -u instead of -i for subsequent updates, and bump the manifest version.
Tests are post-install TransactionCase fixtures in rollback-only transactions.
They do not permanently enable a category or post test financial/stock records.
PO and bottle/test UoM checks run when purchase_stock is installed. The live
deployment uses tha_purchase_bill_uom_valuation_fix, not tha_stock_costing; the
latter is installed only in local THA. Neither addon is a dependency of this
module. Separate validation uses the live addon combination without
tha_stock_costing. See VALIDATION.md
for actual executed results and material gaps.
