frappe.pages['fsm-dispatcher'].on_page_load = function(wrapper) {
    var page = frappe.ui.make_app_page({
        parent: wrapper,
        title: 'Dispatcher Console',
        single_column: true
    });
    let $container = $(page.body).empty().css({
        "padding": "0",
        "margin": "0",
        "height": "calc(100vh - 100px)",
        "overflow": "hidden",
        "background": "#f8fafc"
    });
    $container.html(`
        <iframe src="/assets/elmrkz_fsm/index.html?v=aa1e555f" style="width: 100%; height: 100%; border: none; display: block;" title="FSM Dispatcher Console"></iframe>
    `);
};
