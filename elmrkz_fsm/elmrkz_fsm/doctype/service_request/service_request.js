if (!window.elmrkz_fsm_auto_arrival_listener) {
  window.elmrkz_fsm_auto_arrival_listener = true;
  frappe.realtime.on('fsm_auto_arrived', function(payload) {
    if (!payload || !payload.name) return;
    const distance = payload.distance_meters != null ? `${payload.distance_meters} m` : __('within the configured radius');
    frappe.show_alert({message: __('Arrived at customer: {0} — request marked Delivered', [distance]), indicator: 'green'}, 8);
    if (window.cur_frm && window.cur_frm.doc && window.cur_frm.doc.name === payload.name) window.cur_frm.reload_doc();
  });
}

function fsm_call_with_gps(method, args, done) {
  const send = function(position) {
    const callArgs = Object.assign({}, args || {});
    if (position) {
      callArgs.latitude = position.coords.latitude;
      callArgs.longitude = position.coords.longitude;
    }
    frappe.call({method, args: callArgs, freeze: true, callback: done});
  };
  if (navigator.geolocation) {
    navigator.geolocation.getCurrentPosition(send, () => send(null), {enableHighAccuracy: true, timeout: 8000, maximumAge: 60000});
  } else send(null);
}

function fsm_number(value) {
  const number = parseFloat(value || 0);
  return Number.isFinite(number) ? number : 0;
}

function fsm_completion_total(dialog) {
  const service = fsm_number(dialog.get_value('service_rate'));
  const rows = dialog.get_value('parts') || [];
  return service + rows.reduce((total, row) => total + (fsm_number(row.qty) * fsm_number(row.rate)), 0);
}

function fsm_show_completion_dialog(frm) {
  frappe.call({method: 'elmrkz_fsm.completion.get_completion_context', args: {name: frm.doc.name}, freeze: true}).then(function(contextResponse) {
    if (!contextResponse || contextResponse.exc || !contextResponse.message) return;
    const context = contextResponse.message;
    const orderRows = (context.order_items || []).map(row => ({
      type: 'Sales Order', label: __('Original Sales Order'), item_code: row.item_code, item_name: row.item_name || row.item_code,
      qty: fsm_number(row.qty), rate: fsm_number(row.rate), locked: true
    }));
    const recordedParts = (context.spare_parts || []).map(row => ({
      type: 'Spare Part', label: __(row.source_type || 'Received Spare Part'), item_code: row.item_code, item_name: row.item_name || row.item_code,
      qty: fsm_number(row.qty), rate: fsm_number(row.rate), locked: true
    }));
    const serviceRow = {type: 'Service', label: __('Service'), item_code: context.service_item_code, item_name: context.service_item_code, qty: 1, rate: fsm_number(context.service_rate), locked: false};
    const fixedRows = orderRows.concat([serviceRow], recordedParts);
    const dialog = new frappe.ui.Dialog({
      title: __('Complete Service Request'),
      size: 'large',
      fields: [
        {fieldtype: 'HTML', fieldname: 'intro', options: '<div class="alert alert-info">Original Sales Order lines and received spare parts are included automatically. Only the service rate and any additional spare-part rows can be edited.</div>'},
        {fieldtype: 'HTML', fieldname: 'invoice_lines_preview', options: '<div class="fsm-invoice-lines"></div>'},
        {fieldtype: 'Table', fieldname: 'parts', label: __('Add Spare Parts'), cannot_add_rows: false, in_place_edit: true, fields: [
          {fieldtype: 'Link', fieldname: 'item_code', label: __('Spare Part'), options: 'Item', in_list_view: 1, reqd: 1, get_query: () => ({filters: {is_stock_item: 1, disabled: 0}}), description: __('Only enabled stock items with Maintain Stock enabled are available.')},
          {fieldtype: 'Float', fieldname: 'qty', label: __('Qty'), in_list_view: 1, reqd: 1},
          {fieldtype: 'Currency', fieldname: 'rate', label: __('Rate'), in_list_view: 1, reqd: 1}
        ]},
        {fieldtype: 'Select', fieldname: 'payment_method', label: __('Payment Method'), options: 'Cash\nTransfer', default: 'Cash', reqd: 1},
        {fieldtype: 'Attach', fieldname: 'payment_proof', label: __('Transfer Payment Proof'), depends_on: "eval:doc.payment_method == 'Transfer'", description: __('Required only for Transfer payment.')},
        {fieldtype: 'HTML', fieldname: 'total_preview', options: '<div style="padding:14px;border-radius:8px;background:#f5f9ff;font-size:18px;font-weight:700;">' + __('Grand Total') + ': <span class="fsm-grand-total">0.00</span></div>'}
      ],
      primary_action_label: __('Confirm and Create Invoice'),
      primary_action: function() {
        const values = dialog.get_values();
        if (!values) return;
        const total = update_total();
        if (values.payment_method === 'Transfer' && !values.payment_proof) {
          frappe.msgprint({title: __('Payment Proof Required'), message: __('Attach the transfer payment proof before submitting.'), indicator: 'red'});
          return;
        }
        const button = dialog.get_primary_btn();
        button.prop('disabled', true);
        fsm_call_with_gps('elmrkz_fsm.completion.complete_service_request', {
          name: frm.doc.name,
          service_item_code: context.service_item_code,
          service_rate: serviceRow.rate,
          parts: JSON.stringify(values.parts || []),
          payment_method: values.payment_method,
          payment_proof: values.payment_proof || null
        }, function(response) {
          if (response && !response.exc) {
            const result = response.message || {};
            frappe.show_alert({message: __('Completed. Invoice {0} — Total {1}', [result.sales_invoice || '—', result.grand_total || total]), indicator: 'green'}, 8);
            dialog.hide();
            frm.reload_doc();
          } else button.prop('disabled', false);
        });
      }
    });
    const esc = value => frappe.utils.escape_html(String(value == null ? '' : value));
    const render_fixed_rows = function() {
      const html = '<div class="table-responsive"><table class="table table-bordered" style="margin-bottom:0"><thead><tr><th>' + __('Type') + '</th><th>' + __('Item') + '</th><th style="width:110px">' + __('Qty') + '</th><th style="width:150px">' + __('Rate') + '</th><th style="width:150px">' + __('Amount') + '</th></tr></thead><tbody>' + fixedRows.map((row, index) => {
        const rateCell = row.type === 'Service' ? '<input class="form-control fsm-service-rate" type="number" min="0" step="0.01" value="' + row.rate.toFixed(2) + '">' : '<span>' + row.rate.toFixed(2) + '</span>';
        return '<tr data-row-index="' + index + '"><td>' + esc(row.label) + '</td><td><strong>' + esc(row.item_code) + '</strong><br><small class="text-muted">' + esc(row.item_name) + '</small></td><td>' + row.qty.toFixed(3) + '</td><td>' + rateCell + '</td><td class="fsm-row-amount">' + (row.qty * row.rate).toFixed(2) + '</td></tr>';
      }).join('') + '</tbody></table></div>';
      dialog.fields_dict.invoice_lines_preview.$wrapper.html(html);
      dialog.fields_dict.invoice_lines_preview.$wrapper.find('.fsm-service-rate').on('input change', function() {
        serviceRow.rate = fsm_number(this.value);
        update_total();
      });
    };
    const update_total = function() {
      const fixedTotal = fixedRows.reduce((sum, row) => sum + row.qty * row.rate, 0);
      const extraTotal = (dialog.get_value('parts') || []).reduce((sum, row) => sum + fsm_number(row.qty) * fsm_number(row.rate), 0);
      const total = fixedTotal + extraTotal;
      dialog.fields_dict.invoice_lines_preview.$wrapper.find('tbody tr').each(function(index) {
        const row = fixedRows[index];
        if (row) $(this).find('.fsm-row-amount').text((row.qty * row.rate).toFixed(2));
      });
      dialog.fields_dict.total_preview.$wrapper.find('.fsm-grand-total').text(total.toFixed(2));
      return total;
    };
    dialog.fields_dict.parts.$wrapper.on('change input', update_total);
    dialog.show();
    render_fixed_rows();
    update_total();
  });
}

function fsm_show_spare_part_dialog(frm) {
  const dialog = new frappe.ui.Dialog({
    title: __('Waiting for Spare Part'),
    fields: [
      {fieldtype: 'HTML', fieldname: 'intro', options: '<div class="alert alert-warning">Choose how the spare part will reach your van.</div>'},
      {fieldtype: 'Select', fieldname: 'request_type', label: __('Request Type'), options: 'Purchase\nTransfer', default: 'Purchase', reqd: 1},
      {fieldtype: 'Link', fieldname: 'item_code', label: __('Item Code'), options: 'Item', reqd: 1, get_query: () => ({filters: {is_stock_item: 1, disabled: 0}}), description: __('Only Items with Maintain Stock enabled and Disabled turned off are available.')},
      {fieldtype: 'Float', fieldname: 'qty', label: __('Quantity'), reqd: 1, default: 1},
      {fieldtype: 'Currency', fieldname: 'rate', label: __('Purchase Rate'), depends_on: "eval:doc.request_type == 'Purchase'", description: __('Required for a purchase receipt.')},
      {fieldtype: 'Link', fieldname: 'to_technician', label: __('Other Technician'), options: 'Technician Profile', depends_on: "eval:doc.request_type == 'Transfer'", description: __('The other technician will receive an approval notification.')}
    ],
    primary_action_label: __('Confirm Purchase'),
    primary_action: function() {
      const values = dialog.get_values();
      if (!values) return;
      if (values.request_type === 'Transfer' && !values.to_technician) {
        frappe.msgprint({title: __('Technician Required'), message: __('Select the other technician for a transfer.'), indicator: 'red'});
        return;
      }
      const button = dialog.get_primary_btn();
      button.prop('disabled', true);
      fsm_call_with_gps('elmrkz_fsm.completion.request_spare_part', {
        name: frm.doc.name,
        request_type: values.request_type,
        item_code: values.item_code,
        qty: values.qty,
        rate: values.rate || 0,
        to_technician: values.to_technician || null
      }, function(response) {
        if (response && !response.exc) {
          const result = response.message || {};
          frappe.show_alert({message: result.request_type === 'Purchase' ? __('Part received in your van warehouse') : __('Transfer request sent for approval'), indicator: 'green'}, 8);
          dialog.hide();
          frm.reload_doc();
        } else button.prop('disabled', false);
      });
    }
  });
  const update_spare_part_action_label = function() {
    const requestType = dialog.get_value('request_type') || 'Purchase';
    const label = requestType === 'Purchase' ? __('Confirm Purchase') : __('Send Transfer Request');
    dialog.get_primary_btn().text(label);
  };
  dialog.fields_dict.request_type.$input.on('change', update_spare_part_action_label);
  dialog.show();
  update_spare_part_action_label();
}

frappe.ui.form.on('Service Request', {
  refresh(frm) {
    if (frm.is_new()) return;
    if (frm.doc.workflow_state === 'On the Way') {
      frm.add_custom_button(__('Open Driving Route'), () => {
        frappe.call({method: 'elmrkz_fsm.fsm_actions.map_url', args: {name: frm.doc.name}}).then(r => {
          if (r.message) window.open(r.message, '_blank');
          else frappe.msgprint(__('No valid customer and technician coordinates are available.'));
        });
      }, __('FSM Actions'));
    }
    const isManager = frappe.user.has_role('FSM Manager') || frappe.user.has_role('Service Manager') || frappe.user.has_role('System Manager') || frappe.session.user === 'Administrator';
    if (isManager && !['Completed', 'Cancelled', 'Delivered', 'On the Way', 'In Progress'].includes(frm.doc.workflow_state)) {
      frm.add_custom_button(__('Assign / Reassign Technician'), () => {
        frappe.call({method: 'elmrkz_fsm.fsm_actions.get_assignable_technicians'}).then(r => {
          const technicians = r.message || [];
          if (!technicians.length) return frappe.msgprint(__('No technician with a linked user account is available.'));
          const options = technicians.map(t => `${t.name}::${t.technician_name || t.name} — ${t.availability_status || __('Unknown status')}${t.user ? ` — ${t.user}` : ''}`).join('\n');
          frappe.prompt([{
            label: __('Technician'),
            fieldname: 'technician',
            fieldtype: 'Select',
            options,
            reqd: 1,
            description: __('This FSM control updates technician ownership, routing, and the assignment notification. Use the standard Assign To tool only for general Desk tasks; it does not assign a field technician.')
          }], values => {
            const technician = values.technician.split('::')[0];
            frappe.call({method: 'elmrkz_fsm.fsm_actions.manager_assign_technician', args: {name: frm.doc.name, technician}, freeze: true, freeze_message: __('Assigning and sending notification...')}).then(response => {
              if (!response.exc) { frappe.show_alert({message: __('Assigned and notification sent'), indicator: 'green'}); frm.reload_doc(); }
            });
          }, __('FSM Assignment'), __('Confirm Assignment'));
        });
      }, __('FSM Assignment'));
    }
    frappe.call({method: 'elmrkz_fsm.fsm_actions.available_actions', args: {name: frm.doc.name}}).then(r => {
      (r.message || []).filter(t => t.action !== 'Cancel').forEach(t => {
        frm.add_custom_button(__(t.action || 'Advance'), () => {
          if (t.action === 'Complete') return fsm_show_completion_dialog(frm);
          if (t.action === 'Waiting for Part') return fsm_show_spare_part_dialog(frm);
          fsm_call_with_gps('elmrkz_fsm.fsm_actions.transition_service_request', {name: frm.doc.name, action: t.action}, () => frm.reload_doc());
        }, __('FSM Actions'));
      });
    });
  }
});

frappe.ui.form.on('Service Request', 'onload_post_render', function(frm) {
  if (frm.doc.workflow_state === 'Assigned' && frm.doc.assigned_technician) frm.dashboard.set_headline_alert(__('Waiting for technician approval'), 'orange');
});
