import frappe


def migrate():
    """Move User.van_warehouse values to Technician Profile and remove the User field."""
    profile_meta = frappe.get_meta("Technician Profile")
    if not profile_meta.has_field("van_warehouse"):
        frappe.throw("Technician Profile must contain van_warehouse before migration")

    user_field_exists = bool(frappe.db.exists("Custom Field", "User-van_warehouse"))
    migrated = []

    if user_field_exists:
        profiles = frappe.get_all(
            "Technician Profile",
            fields=["name", "user", "van_warehouse"],
            limit_page_length=0,
        )
        for profile in profiles:
            if not profile.user:
                continue
            source_value = frappe.db.get_value("User", profile.user, "van_warehouse")
            if source_value and source_value != profile.van_warehouse:
                frappe.db.set_value(
                    "Technician Profile",
                    profile.name,
                    "van_warehouse",
                    source_value,
                    update_modified=False,
                )
                migrated.append({"profile": profile.name, "user": profile.user, "warehouse": source_value})

        frappe.delete_doc(
            "Custom Field",
            "User-van_warehouse",
            force=True,
            ignore_permissions=True,
        )

    frappe.clear_cache(doctype="User")
    frappe.clear_cache(doctype="Technician Profile")
    frappe.db.commit()
    return {
        "migrated": migrated,
        "migrated_count": len(migrated),
        "user_field_removed": not frappe.db.exists("Custom Field", "User-van_warehouse"),
    }


if __name__ == "__main__":
    print(migrate())
