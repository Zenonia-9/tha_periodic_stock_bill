from odoo import _, models


class ResCompany(models.Model):
    _inherit = "res.company"

    def _get_stock_valuation_account_vals(self, accounts_by_product, at_date=None, extra_aml_vals_list=None):
        if not accounts_by_product:
            return super()._get_stock_valuation_account_vals(
                accounts_by_product, at_date, extra_aml_vals_list,
            )

        periodic_stock_accounts = set()
        for product, accounts in accounts_by_product.items():
            product = product.with_company(self)
            if (
                product.is_storable
                and product.valuation == "periodic"
                and product.categ_id.tha_periodic_stock_bill
                and accounts["valuation"]
            ):
                periodic_stock_accounts.add(accounts["valuation"].id)

        if not periodic_stock_accounts:
            return super()._get_stock_valuation_account_vals(
                accounts_by_product, at_date, extra_aml_vals_list,
            )

        # Closing is account-based. Keep every product assigned to a feature
        # account together, even when only one category enabled the bill rule.
        periodic_products = {
            product: accounts
            for product, accounts in accounts_by_product.items()
            if accounts["valuation"] and accounts["valuation"].id in periodic_stock_accounts
        }
        native_products = {
            product: accounts
            for product, accounts in accounts_by_product.items()
            if not accounts["valuation"] or accounts["valuation"].id not in periodic_stock_accounts
        }

        native_context = dict(self.env.context)
        if "inventory_data" in native_context:
            inventory_data = native_context["inventory_data"] or {}
            native_context["inventory_data"] = {
                account: value
                for account, value in inventory_data.items()
                if account.id not in periodic_stock_accounts
            }
        native_vals = super(ResCompany, self.with_context(native_context))._get_stock_valuation_account_vals(
            native_products, at_date, extra_aml_vals_list,
        )

        if "inventory_data" in self.env.context:
            inventory_data = self.env.context["inventory_data"] or {}
        else:
            inventory_data = self.stock_value(periodic_products, at_date)
        accounting_data = self.stock_accounting_value(periodic_products, at_date)
        extra_balance = self._get_extra_balance(extra_aml_vals_list)

        periodic_vals = []
        accounts = inventory_data.keys() | accounting_data.keys()
        for account in accounts:
            if account.id not in periodic_stock_accounts:
                continue
            counterpart = account.account_stock_variation_id or account.account_stock_expense_id
            if not counterpart:
                continue
            balance = inventory_data.get(account, 0) - accounting_data.get(account, 0)
            balance -= extra_balance.get(account.id, 0)
            if self.currency_id.is_zero(balance):
                continue
            periodic_vals += self._prepare_inventory_aml_vals(
                account,
                counterpart,
                balance,
                _("Closing: Stock Variation Global for company [%(company)s]", company=self.display_name),
            )

        return native_vals + periodic_vals
