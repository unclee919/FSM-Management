import unittest

import frappe


class TestWhatsAppOrder(unittest.TestCase):
    def test_whatsapp_settings_fields(self):
        settings = frappe.get_single("FSM Settings")
        for fieldname in (
            "enable_whatsapp_order_ingestion",
            "whatsapp_auto_submit_order",
            "whatsapp_unknown_contact_action",
            "whatsapp_default_item_code",
            "whatsapp_default_service_fee",
            "whatsapp_default_price_list",
            "whatsapp_default_warehouse",
            "whatsapp_default_company",
            "whatsapp_default_currency",
        ):
            self.assertTrue(hasattr(settings, fieldname), fieldname)

    def test_whatsapp_default_fee_is_positive_when_enabled(self):
        settings = frappe.get_single("FSM Settings")
        if settings.enable_whatsapp_order_ingestion:
            self.assertGreater(float(settings.whatsapp_default_service_fee or 0), 0)

    def test_whatsapp_default_warehouse_is_configured_when_enabled(self):
        settings = frappe.get_single("FSM Settings")
        if settings.enable_whatsapp_order_ingestion:
            self.assertTrue(settings.whatsapp_default_company)
            self.assertTrue(settings.whatsapp_default_warehouse)
            self.assertTrue(frappe.db.exists("Warehouse", settings.whatsapp_default_warehouse))
