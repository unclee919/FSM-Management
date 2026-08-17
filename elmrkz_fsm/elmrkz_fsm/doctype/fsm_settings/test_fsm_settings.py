import unittest
import frappe

class TestFSMSettings(unittest.TestCase):
    def test_settings_validation(self):
        settings = frappe.get_single("FSM Settings")
        settings.whatsapp_auto_submit_order = 0
        settings.whatsapp_default_service_fee = 250.0
        settings.require_technician_report = 1
        settings.save()
        self.assertEqual(settings.whatsapp_default_service_fee, 250.0)
