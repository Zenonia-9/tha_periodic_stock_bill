from odoo import Command, fields
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestPeriodicStockBill(TransactionCase):
    """All accounting/stock fixtures live in rollback-only test transactions."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env["res.company"].create({
            "name": "Periodic Bill Test Company",
            "currency_id": cls.env.ref("base.USD").id,
            "country_id": cls.env.ref("base.us").id,
            "inventory_valuation": "periodic",
            "cost_method": "average",
        })
        cls.env = cls.env(context=dict(cls.env.context, allowed_company_ids=cls.company.ids))
        cls.stock = cls._account("TST100", "Inventory", "asset_current")
        cls.expense = cls._account("TST600", "Consumption", "expense_direct_cost")
        cls.payable = cls._account("TST200", "Payable", "liability_payable", reconcile=True)
        cls.offset = cls._account("TST300", "Opening", "equity")
        cls.stock.account_stock_expense_id = cls.expense
        cls.journal = cls.env["account.journal"].create({
            "name": "Periodic Test Purchase", "code": "TPB", "type": "purchase",
            "company_id": cls.company.id,
        })
        cls.closing_journal = cls.env["account.journal"].create({
            "name": "Periodic Test Closing", "code": "TPC", "type": "general",
            "company_id": cls.company.id,
        })
        cls.company.write({
            "account_stock_valuation_id": cls.stock.id,
            "account_stock_journal_id": cls.closing_journal.id,
            "expense_account_id": cls.expense.id,
        })
        cls.category = cls.env["product.category"].create({
            "name": "Periodic Bill Test Category",
            "property_valuation": "periodic",
            "property_cost_method": "average",
            "property_stock_valuation_account_id": cls.stock.id,
            "property_account_expense_categ_id": cls.expense.id,
            "tha_periodic_stock_bill": True,
        })
        cls.product = cls.env["product.product"].create({
            "name": "Periodic Bill Test Reagent",
            "is_storable": True,
            "categ_id": cls.category.id,
            "standard_price": 3240,
            "supplier_taxes_id": [Command.clear()],
        })
        cls.vendor = cls.env["res.partner"].create({
            "name": "Periodic Bill Test Vendor",
            "property_account_payable_id": cls.payable.id,
        })
        cls.warehouse = cls.env["stock.warehouse"].search([
            ("company_id", "=", cls.company.id),
        ], limit=1)
        cls.supplier = cls.env.ref("stock.stock_location_suppliers")
        cls.customer = cls.env.ref("stock.stock_location_customers")

    @classmethod
    def _account(cls, code, name, account_type, **values):
        return cls.env["account.account"].create({
            "code": code, "name": name, "account_type": account_type,
            "company_ids": [Command.set(cls.company.ids)], **values,
        })

    def _bill(self, quantity=100, price=3240, product=None, move_type="in_invoice", **values):
        return self.env["account.move"].create({
            "move_type": move_type,
            "company_id": self.company.id,
            "partner_id": self.vendor.id,
            "journal_id": self.journal.id,
            "invoice_date": fields.Date.today(),
            "invoice_line_ids": [Command.create({
                "product_id": (product or self.product).id,
                "quantity": quantity,
                "price_unit": price,
                "tax_ids": [Command.clear()],
            })],
            **values,
        })

    def _stock_move(self, quantity, incoming=True, price=3240, returned_move=None):
        source = self.supplier if incoming else self.warehouse.lot_stock_id
        destination = self.warehouse.lot_stock_id if incoming else self.customer
        if returned_move:
            destination = self.supplier
        move = self.env["stock.move"].create({
            "company_id": self.company.id,
            "product_id": self.product.id,
            "product_uom": self.product.uom_id.id,
            "product_uom_qty": quantity,
            "location_id": source.id,
            "location_dest_id": destination.id,
            "price_unit": price,
            "origin_returned_move_id": returned_move.id if returned_move else False,
        })
        move._action_confirm()
        move._action_assign()
        move.move_line_ids.quantity = quantity
        move.picked = True
        move._action_done()
        return move

    def _balances(self, vals):
        result = {}
        for line in vals:
            result[line["account_id"]] = result.get(line["account_id"], 0) + line["debit"] - line["credit"]
        return result

    def _closing_vals(self):
        products = self.company._get_accounts_by_product(self.product)
        return self.company._get_stock_valuation_account_vals(products)

    def _assert_closing(self, consumption, remaining):
        self.assertAlmostEqual(self.product.total_value, remaining, places=2)
        vals = self._closing_vals()
        balance = self._balances(vals)
        self.assertAlmostEqual(balance.get(self.expense.id, 0), consumption, places=2)
        self.assertAlmostEqual(balance.get(self.stock.id, 0), -consumption, places=2)
        if vals:
            closing = self.env["account.move"].create({
                "journal_id": self.closing_journal.id,
                "date": fields.Date.today(),
                "line_ids": [Command.create(line) for line in vals],
            })
            closing.action_post()
            self.assertFalse(self._closing_vals(), "Unchanged closing must not adjust twice")

    def test_enabled_disabled_and_prospective_drafts(self):
        self.category.tha_periodic_stock_bill = False
        old = self._bill()
        self.assertEqual(old.invoice_line_ids.account_id, self.expense)
        self.category.tha_periodic_stock_bill = True
        self.assertEqual(old.invoice_line_ids.account_id, self.expense)
        enabled = self._bill()
        self.assertEqual(enabled.invoice_line_ids.account_id, self.stock)
        old.action_post()
        enabled.action_post()
        self.assertEqual(old.invoice_line_ids.account_id, self.expense)
        self.assertEqual(enabled.invoice_line_ids.account_id, self.stock)

    def test_company_isolation_and_effective_periodic(self):
        other = self.env["res.company"].create({
            "name": "Periodic Bill Other Company", "inventory_valuation": "real_time",
        })
        self.assertFalse(self.category.with_company(other).tha_periodic_stock_bill)
        self.assertTrue(self.category.tha_periodic_stock_bill)
        self.category.property_valuation = False
        self.company.inventory_valuation = "periodic"
        self.assertEqual(self._bill().invoice_line_ids.account_id, self.stock)
        self.company.inventory_valuation = "real_time"
        self.assertFalse(self._bill().invoice_line_ids.tha_uses_periodic_stock_bill())

    def test_service_and_perpetual_are_native(self):
        service = self.env["product.product"].create({
            "name": "Periodic Bill Test Service", "type": "service",
            "categ_id": self.category.id, "supplier_taxes_id": [Command.clear()],
        })
        bill = self._bill(product=service)
        self.assertEqual(bill.invoice_line_ids.account_id, self.expense)
        self.assertFalse(bill.invoice_line_ids.tha_uses_periodic_stock_bill())
        self.category.property_valuation = "real_time"
        self.assertEqual(self._bill().invoice_line_ids.account_id, self.stock)
        self.assertFalse(self._bill().invoice_line_ids.tha_uses_periodic_stock_bill())

    def test_manual_account_edit_is_preserved(self):
        bill = self._bill()
        bill.invoice_line_ids.account_id = self.expense
        bill.action_post()
        self.assertEqual(bill.invoice_line_ids.account_id, self.expense)
        self.assertFalse(bill.line_ids.filtered(lambda line: line.display_type == "cogs"))

    def test_vendor_refund_and_reversal(self):
        bill = self._bill()
        bill.action_post()
        refund = self._bill(move_type="in_refund", quantity=25)
        refund.action_post()
        self.assertEqual(refund.invoice_line_ids.account_id, self.stock)
        self.assertEqual(refund.invoice_line_ids.credit, 81000)
        reversal = bill._reverse_moves([{"date": fields.Date.today(), "invoice_date": fields.Date.today()}])
        reversal.action_post()
        self.assertEqual(reversal.invoice_line_ids.account_id, self.stock)
        self.assertEqual(reversal.invoice_line_ids.credit, 324000)

    def test_fiscal_mapping_and_native_closing_limit(self):
        mapped = self._account("TST101", "Mapped Inventory", "asset_current")
        mapped.account_stock_expense_id = self.expense
        fiscal = self.env["account.fiscal.position"].create({
            "name": "Periodic Bill Mapping",
            "company_id": self.company.id,
            "account_ids": [Command.create({
                "account_src_id": self.stock.id,
                "account_dest_id": mapped.id,
            })],
        })
        bill = self._bill(fiscal_position_id=fiscal.id)
        self.assertEqual(bill.invoice_line_ids.account_id, mapped)
        with self.assertRaisesRegex(UserError, "fiscal position redirects the stock"):
            bill.action_post()
        self.assertEqual(bill.state, "draft")
        self.assertEqual(bill.invoice_line_ids.account_id, mapped)
        # An identity mapping preserves the native closing account.
        fiscal.account_ids.account_dest_id = self.stock
        identity = self._bill(fiscal_position_id=fiscal.id)
        identity.action_post()
        self.assertEqual(identity.invoice_line_ids.account_id, self.stock)

    def test_company_fallback(self):
        self.category.property_stock_valuation_account_id = False
        self.assertEqual(self._bill().invoice_line_ids.account_id, self.stock)

    def test_missing_stock_fails_before_post(self):
        self.category.property_stock_valuation_account_id = False
        self.company.account_stock_valuation_id = False
        self.env["ir.default"].set(
            "product.category", "property_stock_valuation_account_id", False,
            company_id=self.company.id,
        )
        bill = self._bill()
        with self.assertRaisesRegex(UserError, "Stock Valuation Account"):
            bill.action_post()
        self.assertEqual(bill.state, "draft")

    def test_missing_counterpart_and_journal_fail_before_post(self):
        bill = self._bill()
        self.stock.account_stock_expense_id = False
        with self.assertRaisesRegex(UserError, "closing Variation Account or Expense Account"):
            bill.action_post()
        self.stock.account_stock_expense_id = self.expense
        self.company.account_stock_journal_id = False
        with self.assertRaisesRegex(UserError, "Stock Journal"):
            bill.action_post()
        self.assertEqual(bill.state, "draft")

    def test_invalid_account_type_and_inactive_counterpart(self):
        bill = self._bill()
        self.stock.account_type = "asset_fixed"
        with self.assertRaisesRegex(UserError, "Current Assets"):
            bill.action_post()
        self.stock.account_type = "asset_current"
        self.expense.active = False
        with self.assertRaisesRegex(UserError, "closing Variation Account or Expense Account"):
            bill.action_post()

    def test_counterpart_company_is_checked(self):
        other = self.env["res.company"].create({"name": "Other Closing Company"})
        wrong = self.env["account.account"].create({
            "name": "Wrong Company Expense", "code": "WRONG600",
            "account_type": "expense",
            "company_ids": [Command.set(other.ids)],
        })
        self.stock.account_stock_expense_id = wrong
        with self.assertRaisesRegex(UserError, "valid for this company"):
            self._bill().action_post()

    def test_taxes_discount_and_foreign_currency(self):
        currency = self.env.ref("base.EUR")
        currency.active = True
        self.env["res.currency.rate"].create({
            "name": fields.Date.today(), "currency_id": currency.id,
            "company_id": self.company.id, "rate": 0.5,
        })
        tax_account = self._account("TST110", "Purchase Tax", "asset_current")
        group = self.env["account.tax.group"].create({
            "name": "Periodic Bill Tax", "company_id": self.company.id,
        })
        tax = self.env["account.tax"].create({
            "name": "Periodic Bill 10%", "amount": 10,
            "amount_type": "percent", "type_tax_use": "purchase",
            "company_id": self.company.id, "tax_group_id": group.id,
        })
        tax.invoice_repartition_line_ids.filtered(
            lambda line: line.repartition_type == "tax",
        ).account_id = tax_account
        bill = self._bill(quantity=2, price=100, currency_id=currency.id)
        bill.invoice_line_ids.write({"tax_ids": [Command.set(tax.ids)], "discount": 10})
        bill.action_post()
        self.assertEqual(bill.amount_untaxed, 180)
        self.assertEqual(bill.amount_tax, 18)
        self.assertEqual(bill.amount_total, 198)
        self.assertEqual(bill.invoice_line_ids.account_id, self.stock)
        self.assertEqual(bill.invoice_line_ids.amount_currency, 180)
        self.assertAlmostEqual(sum(bill.line_ids.mapped("balance")), 0)
        self.assertEqual(bill.line_ids.filtered(
            lambda line: line.display_type == "payment_term",
        ).account_id, self.payable)
        self.assertEqual(bill.line_ids.filtered(
            lambda line: line.display_type == "tax",
        ).account_id, tax_account)

    def test_purchase_all_stock_remaining(self):
        self._stock_move(100)
        self._bill().action_post()
        self._assert_closing(0, 324000)

    def test_purchase_half_stock_remaining_and_repeat_public_closing(self):
        self._stock_move(100)
        self._bill().action_post()
        self._stock_move(50, incoming=False)
        self.assertAlmostEqual(self.product.total_value, 162000, places=2)
        action = self.company.action_close_stock_valuation(auto_post=True)
        closing = self.env["account.move"].browse(action["res_id"])
        self.assertEqual(closing.state, "posted")
        self.assertEqual(closing.line_ids.filtered(
            lambda line: line.account_id == self.expense,
        ).debit, 162000)
        with self.assertRaisesRegex(UserError, "Everything is correctly closed"):
            self.company.action_close_stock_valuation(auto_post=True)

    def test_purchase_none_remaining(self):
        self._stock_move(100)
        self._bill().action_post()
        self._stock_move(100, incoming=False)
        self._assert_closing(324000, 0)

    def test_opening_balances_and_consumption(self):
        self._stock_move(50)
        opening = self.env["account.move"].create({
            "journal_id": self.closing_journal.id,
            "line_ids": [
                Command.create({"account_id": self.stock.id, "debit": 162000}),
                Command.create({"account_id": self.offset.id, "credit": 162000}),
            ],
        })
        opening.action_post()
        self._stock_move(100)
        self._bill().action_post()
        self._stock_move(50, incoming=False)
        self._assert_closing(162000, 324000)

    def test_historical_expense_bill_capitalization(self):
        self.category.tha_periodic_stock_bill = False
        bill = self._bill()
        bill.action_post()
        self.category.tha_periodic_stock_bill = True
        self._stock_move(100)
        self.assertEqual(bill.invoice_line_ids.account_id, self.expense)
        # Historical expense needs native capitalization; no bill rewrite.
        self._assert_closing(-324000, 324000)

    def test_partial_receipt_billing_and_price_difference(self):
        self.product.standard_price = 3000
        self._stock_move(50, price=3000)
        self._bill(quantity=100).action_post()
        # Native closing includes the unmatched bill and valuation-price gap.
        self._assert_closing(174000, 150000)

    def test_partial_bill_full_receipt(self):
        self._stock_move(100)
        self._bill(quantity=50).action_post()
        self._assert_closing(-162000, 324000)

    def test_supplier_return_with_credit_note(self):
        receipt = self._stock_move(100)
        self._bill().action_post()
        self._stock_move(25, incoming=False, returned_move=receipt)
        self._bill(quantity=25, move_type="in_refund").action_post()
        self._assert_closing(0, 243000)

    def test_po_bottle_test_uom_avco(self):
        if "purchase.order" not in self.env:
            self.skipTest("Optional purchase_stock integration is not installed")
        bottle = self.env["uom.uom"].create({
            "name": "Periodic Test Bottle of 10",
            "relative_factor": 10,
            "relative_uom_id": self.product.uom_id.id,
        })
        order = self.env["purchase.order"].create({
            "partner_id": self.vendor.id,
            "company_id": self.company.id,
            "order_line": [Command.create({
                "product_id": self.product.id,
                    "product_qty": 10,
                "product_uom_id": bottle.id,
                "price_unit": 32400,
                "tax_ids": [Command.clear()],
            })],
        })
        order.button_confirm()
        picking = order.picking_ids
        picking.action_assign()
        picking.move_ids.move_line_ids.quantity = 100
        picking.move_ids.picked = True
        picking.button_validate()
        action = order.action_create_invoice()
        bill = self.env["account.move"].browse(action["res_id"])
        bill.invoice_date = fields.Date.today()
        self.assertEqual(bill.invoice_line_ids.account_id, self.stock)
        bill.action_post()
        self.assertEqual(self.product.cost_method, "average")
        self.assertEqual(self.product.valuation, "periodic")
        self.assertEqual(self.product.qty_available, 100)
        self.assertAlmostEqual(self.product.total_value, 324000, places=2)
        move = picking.move_ids
        if hasattr(move, "_tha_convert_bill_line_quantity"):
            self.assertEqual(move._tha_convert_bill_line_quantity(bill.invoice_line_ids), 100)
        self.assertEqual(move._get_value_from_account_move(100)["quantity"], 100)
        self._stock_move(50, incoming=False)
        self._assert_closing(162000, 162000)


    def test_inactive_stock_account_is_rejected(self):
        bill = self._bill()
        self.stock.active = False
        with self.assertRaisesRegex(UserError, "active Stock Valuation Account"):
            bill.action_post()
        self.assertEqual(bill.state, "draft")

    def test_bill_defaults_follow_document_company(self):
        other = self.env["res.company"].create({
            "name": "Periodic Bill Document Company",
            "country_id": self.env.ref("base.us").id,
            "currency_id": self.company.currency_id.id,
            "inventory_valuation": "periodic",
        })
        accounts = self.env["account.account"].with_company(other).create([
            {
                "name": "Other Expense", "code": "OTH600", "account_type": "expense",
                "company_ids": [Command.set(other.ids)],
            },
            {
                "name": "Other Stock", "code": "OTH100", "account_type": "asset_current",
                "company_ids": [Command.set(other.ids)],
            },
            {
                "name": "Other Payable", "code": "OTH200", "account_type": "liability_payable",
                "reconcile": True, "company_ids": [Command.set(other.ids)],
            },
        ])
        expense, stock, payable = accounts
        stock.account_stock_expense_id = expense
        other_category = self.category.with_company(other)
        other_category.write({
            "property_valuation": "periodic",
            "property_account_expense_categ_id": expense.id,
            "property_stock_valuation_account_id": stock.id,
        })
        self.vendor.with_company(other).property_account_payable_id = payable
        purchase, closing = self.env["account.journal"].with_company(other).create([
            {"name": "Other Purchase", "code": "OPU", "type": "purchase", "company_id": other.id},
            {"name": "Other Closing", "code": "OCL", "type": "general", "company_id": other.id},
        ])
        other.account_stock_journal_id = closing
        other.account_stock_valuation_id = stock
        other.expense_account_id = expense
        native = self._bill(company_id=other.id, journal_id=purchase.id)
        self.assertEqual(native.invoice_line_ids.account_id, expense)
        other_category.tha_periodic_stock_bill = True
        enabled = self._bill(company_id=other.id, journal_id=purchase.id)
        self.assertEqual(enabled.invoice_line_ids.account_id, stock)
        enabled.action_post()
        self.assertEqual(self._bill().invoice_line_ids.account_id, self.stock)
        self.assertEqual(native.invoice_line_ids.account_id, expense)

    def test_customer_invoice_keeps_native_income_without_cogs(self):
        income = self._account("TST700", "Sales Income", "income")
        receivable = self._account("TST120", "Receivable", "asset_receivable", reconcile=True)
        self.product.property_account_income_id = income
        self.vendor.property_account_receivable_id = receivable
        journal = self.env["account.journal"].create({
            "name": "Periodic Test Sales", "code": "TPS", "type": "sale",
            "company_id": self.company.id,
        })
        invoice = self._bill(move_type="out_invoice", journal_id=journal.id)
        invoice.action_post()
        self.assertEqual(invoice.invoice_line_ids.account_id, income)
        self.assertFalse(invoice.line_ids.filtered(lambda line: line.display_type == "cogs"))


    def test_stock_account_expense_fallback_does_not_require_company_expense(self):
        bill = self._bill()
        self.company.expense_account_id = False
        bill.action_post()
        self.assertEqual(bill.state, "posted")
        other_expense = self._account("TST601", "Different Company Expense", "expense")
        self.company.expense_account_id = other_expense
        self._stock_move(50)
        native = self._balances(self._closing_vals())
        self.assertEqual(native.get(self.expense.id), 162000)
        self.assertNotIn(other_expense.id, native)
        self._assert_closing(162000, 162000)

    def test_missing_company_stock_default_blocks_posting(self):
        bill = self._bill()
        self.company.account_stock_valuation_id = False
        self.category.property_stock_valuation_account_id = self.stock
        self.assertEqual(bill.invoice_line_ids.tha_get_periodic_stock_account(), self.stock)
        self.assertEqual(bill.invoice_line_ids.account_id, self.stock)
        with self.assertRaisesRegex(UserError, "company Stock Valuation Account"):
            bill.action_post()
        self.assertEqual(bill.state, "draft")


    def test_foreign_restricted_accounts_block_before_posting(self):
        currency = self.env.ref("base.EUR")
        currency.active = True
        bill = self._bill(currency_id=currency.id)
        self.expense.currency_id = currency
        with self.assertRaisesRegex(UserError, "company currency"):
            bill.action_post()
        self.assertEqual(bill.state, "draft")
        self.expense.currency_id = False
        self.stock.currency_id = currency
        with self.assertRaisesRegex(UserError, "company currency"):
            bill.action_post()
        self.assertEqual(bill.state, "draft")
