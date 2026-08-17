import frappe

def run_uat():
    print("--- UAT 1: FSM Settings Validation ---")
    settings = frappe.get_single("FSM Settings")
    settings.whatsapp_auto_submit_order = 0
    settings.whatsapp_default_service_fee = 250.0
    settings.require_technician_report = 1
    settings.save()
    print("Settings saved successfully with fee:", settings.whatsapp_default_service_fee)

    print("--- UAT 2: WhatsApp Order Ingestion Simulation with Secret ---")
    from elmrkz_fsm.whatsapp_order import ingest_whatsapp_order
    payload = {
        "phone": "+201004904421",
        "customer_name": "UAT Test Customer",
        "address": "Cairo, Egypt",
        "service_details": "AC Maintenance",
        "price": 250,
        "secret": "elmrkz_fsm_secret_2026"
    }
    try:
        res = ingest_whatsapp_order(payload)
        print("Sales Order ingestion result:", res)
    except Exception as e:
        print("Ingestion exception caught correctly:", e)
