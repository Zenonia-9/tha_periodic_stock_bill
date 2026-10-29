from odoo import _, models
from odoo.exceptions import UserError


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    def tha_uses_periodic_stock_bill(self):
        self.ensure_one()
        line = self.with_company(self.company_id)
        return (
            line.display_type == "product"
            and line.move_id.move_type in ("in_invoice", "in_refund")
            and line.product_id.is_storable
            and line.product_id.valuation == "periodic"
            and line.product_id.categ_id.tha_periodic_stock_bill
        )

    def tha_get_periodic_stock_account(self):
        self.ensure_one()
        line = self.with_company(self.company_id)
        return line.product_id.product_tmpl_id.get_product_accounts(
            fiscal_pos=line.move_id.fiscal_position_id,
        )["stock_valuation"]

    def _compute_account_id(self):
        super()._compute_account_id()
        # Keep native dependencies: changing a category must not rewrite drafts.
        for line in self:
            if line.tha_uses_periodic_stock_bill():
                account = line.tha_get_periodic_stock_account()
                if account:
                    line.account_id = account

    def tha_validate_periodic_stock_configuration(self):
        for line in self:
            if not line.tha_uses_periodic_stock_bill():
                continue
            company = line.company_id
            stock = line.tha_get_periodic_stock_account()

            def valid_account(account, types):
                return (
                    account
                    and account.active
                    and account.account_type in types
                    and (not account.currency_id or account.currency_id == company.currency_id)
                    and account.filtered_domain(account._check_company_domain(company))
                )

            raw_stock = line.with_company(company).product_id.product_tmpl_id._get_product_accounts()["stock_valuation"]
            if stock and stock != raw_stock:
                raise UserError(_(
                    "Stock Account on Vendor Bills: fiscal position redirects the stock "
                    "account for %(product)s from %(source)s to %(destination)s. Native "
                    "inventory closing uses the product's original stock account. Remove "
                    "this stock-account mapping before posting, or disable this feature "
                    "for the category and reconcile the accounting configuration.",
                    product=line.product_id.display_name,
                    source=raw_stock.display_name,
                    destination=stock.display_name,
                ))
            error = False
            if not valid_account(stock, ("asset_current",)):
                error = _("Set an active Stock Valuation Account of type Current Assets "
                          "for this company (on the category or company), without a forced "
                          "foreign currency: native closing uses the company currency.")
            else:
                counterpart = stock.account_stock_variation_id or stock.account_stock_expense_id
                if not valid_account(counterpart, ("expense", "expense_direct_cost")):
                    error = _("Set an active closing Variation Account or Expense Account "
                              "of type Expenses or Cost of Revenue on the stock account, "
                              "valid for this company and without a forced foreign currency "
                              "(native closing uses the company currency).")
                elif stock.account_stock_expense_id and not valid_account(
                    stock.account_stock_expense_id, ("expense", "expense_direct_cost"),
                ):
                    error = _("The stock account's closing Expense Account must be active, "
                              "valid for this company and of type Expenses or Cost of Revenue, "
                              "without a forced foreign currency (closing uses the company currency).")
                elif not valid_account(company.account_stock_valuation_id, ("asset_current",)):
                    error = _("Set an active company Stock Valuation Account of type "
                              "Current Assets, valid for this company and without a forced "
                              "foreign currency (native closing uses the company currency).")
                elif not company.account_stock_journal_id or not (
                    company.account_stock_journal_id.active
                    and company.account_stock_journal_id.type == "general"
                    and company.account_stock_journal_id.filtered_domain(
                        company.account_stock_journal_id._check_company_domain(company),
                    )
                ):
                    error = _("Set an active company Stock Journal of type Miscellaneous "
                              "for native inventory closing.")
            if error:
                raise UserError(_(
                    "Stock Account on Vendor Bills: configuration error for %(product)s "
                    "(category %(category)s, company %(company)s). %(error)s",
                    product=line.product_id.display_name,
                    category=line.product_id.categ_id.display_name,
                    company=company.display_name,
                    error=error,
                ))
