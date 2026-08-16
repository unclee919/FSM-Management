frappe.ui.form.on('FSM Settings', {
	refresh: function(frm) {
		frm.trigger('render_map');
	},
	validate: function(frm) {
		if (!frm.doc.enable_whatsapp_order_ingestion) {
			return;
		}

		if (flt(frm.doc.whatsapp_default_service_fee) <= 0) {
			frappe.throw(__('Default Service Visit Fee must be greater than zero when WhatsApp Order Ingestion is enabled.'));
		}
		if (!frm.doc.whatsapp_default_company) {
			frappe.throw(__('Default Company is required when WhatsApp Order Ingestion is enabled.'));
		}
		if (!frm.doc.whatsapp_default_warehouse) {
			frappe.throw(__('Default Warehouse is required when WhatsApp Order Ingestion is enabled.'));
		}
		if (!frm.doc.whatsapp_default_item_code) {
			frappe.throw(__('Default Service Item is required when WhatsApp Order Ingestion is enabled.'));
		}
	},
	company_latitude: function(frm) {
		frm.trigger('render_map');
	},
	company_longitude: function(frm) {
		frm.trigger('render_map');
	},
	render_map: function(frm) {
		if (frm.doc.company_latitude && frm.doc.company_longitude) {
			const lat = frm.doc.company_latitude;
			const lon = frm.doc.company_longitude;
			const html = `
				<div style="width: 100%; height: 300px; border: 1px solid #d1d8dd; border-radius: 4px; overflow: hidden;">
					<iframe
						width="100%"
						height="100%"
						frameborder="0"
						style="border:0"
						src="https://maps.google.com/maps?q=${lat},${lon}&z=15&output=embed"
						allowfullscreen>
					</iframe>
				</div>
			`;
			frm.get_field('map_preview').$wrapper.html(html);
		} else {
			frm.get_field('map_preview').$wrapper.html('<div class="text-muted" style="padding: 20px; border: 1px dashed #d1d8dd; text-align: center;">Coordinates required for map preview.</div>');
		}
	},
	fetch_location: function(frm) {
		if (navigator.geolocation) {
			navigator.geolocation.getCurrentPosition(
				(position) => {
					const lat = position.coords.latitude;
					const lon = position.coords.longitude;

					frm.set_value('company_latitude', lat);
					frm.set_value('company_longitude', lon);
					frm.set_value('google_maps_link', `https://www.google.com/maps?q=${lat},${lon}`);

					frappe.show_alert({
						message: __('Location fetched and Map updated'),
						indicator: 'green'
					});

					frm.save();
				},
				(error) => {
					let msg = __('Could not fetch location.');
					if (error.code === error.PERMISSION_DENIED) {
						msg = __('Location permission denied by browser.');
					}
					frappe.msgprint(msg);
				},
				{
					enableHighAccuracy: true,
					timeout: 5000,
					maximumAge: 0
				}
			);
		} else {
			frappe.msgprint(__('Geolocation is not supported by this browser.'));
		}
	},
	google_maps_link: function(frm) {
		if (frm.doc.google_maps_link) {
			const link = frm.doc.google_maps_link;
			const regex = /@?([-+]?\d{1,3}\.\d+),([-+]?\d{1,3}\.\d+)/;
			const match = link.match(regex);

			let found = false;
			if (match) {
				frm.set_value('company_latitude', parseFloat(match[1]));
				frm.set_value('company_longitude', parseFloat(match[2]));
				found = true;
			} else {
				const pairRegex = /([-+]?\d{1,3}\.\d+)[, ]+([-+]?\d{1,3}\.\d+)/;
				const pairMatch = link.match(pairRegex);
				if (pairMatch) {
					frm.set_value('company_latitude', parseFloat(pairMatch[1]));
					frm.set_value('company_longitude', parseFloat(pairMatch[2]));
					found = true;
				}
			}

			if (found) {
				frappe.show_alert({
					message: __('Coordinates extracted and Map updated'),
					indicator: 'blue'
				});
				frm.save();
			}
		}
	}
});
