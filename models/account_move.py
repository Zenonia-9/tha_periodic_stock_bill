from odoo import models


class AccountMove(models.Model):
    _inherit = "account.move"

    def _post(self, soft=True):
        self.invoice_line_ids.tha_validate_periodic_stock_configuration()
        return super()._post(soft=soft)
