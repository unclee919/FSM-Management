import frappe

def execute():
    requests = frappe.get_all("Service Request", fields=["name", "scheduled_date", "scheduled_time", "creation", "scheduled_datetime"])
    print(f"Total Service Requests found: {len(requests)}")
    
    count = 0
    for r in requests:
        if not r.scheduled_datetime:
            s_date = str(r.scheduled_date) if r.scheduled_date else str(r.creation).split()[0]
            s_time = str(r.scheduled_time) if r.scheduled_time else "09:00:00"
            s_dt = f"{s_date} {s_time}"
            frappe.db.set_value("Service Request", r.name, "scheduled_datetime", s_dt, update_modified=False)
            count += 1
            
    frappe.db.commit()
    print(f"Successfully updated {count} Service Request records with scheduled_datetime.")

if __name__ == "__main__":
    execute()
