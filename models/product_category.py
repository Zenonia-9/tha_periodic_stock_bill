from odoo import fields, models


class ProductCategory(models.Model):
    _inherit = "product.category"

    tha_periodic_stock_bill = fields.Boolean(
        string="Stock Account on Vendor Bills",
        company_dependent=True,
        default=False,
        help="For storable products with Periodic valuation, default vendor bills and "
             "credit notes to the stock account. Consumption expense is recognized "
             "by native inventory closing, after physical usage is recorded in stock. "
             "Reconcile every category sharing that stock account before enabling.",
    )
