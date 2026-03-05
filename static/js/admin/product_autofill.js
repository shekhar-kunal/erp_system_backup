/**
 * Product Auto-fill for ERP Admin Inlines
 *
 * When a product is selected in a Purchase Order Line or Sales Order Line,
 * auto-fills the price (and unit, for PO lines) from the product's defaults.
 *
 * NOTE: This script must NOT use an IIFE that evaluates django.jQuery at load
 * time, because django.jQuery is set by jquery.init.js which loads AFTER this
 * script in Django admin's merged Media order.
 * Use DOMContentLoaded so that all head scripts (including jquery.init.js)
 * have run before we access django.jQuery.
 *
 * Both PurchaseOrderLine and SalesOrderLine use related_name="lines",
 * so the inline prefix is always "lines".  We distinguish PO vs SO by URL path.
 */
document.addEventListener('DOMContentLoaded', function () {
    'use strict';

    var $ = django.jQuery;   // Safe: jquery.init.js has already run by now

    /**
     * Parse the inline prefix and row index from a product select element.
     * Django inline field IDs: id_{prefix}-{index}-{field}
     * e.g. id_lines-0-product
     */
    function parseRowId(selectEl) {
        var m = selectEl.id.match(/^id_(.+)-(\d+)-product$/);
        return m ? { prefix: m[1], idx: m[2] } : null;
    }

    /**
     * Decide which price key to read from the AJAX response.
     * PO lines → cost_price;  SO lines → sale_price.
     */
    function getPriceKey(prefix, idx) {
        var path = window.location.pathname;
        if (path.indexOf('/purchasing/') !== -1) { return 'cost_price'; }
        if (path.indexOf('/sales/')      !== -1) { return 'sale_price'; }
        // Fallback: if a unit field exists in this row it is a PO line
        if ($('#id_' + prefix + '-' + idx + '-unit').length) { return 'cost_price'; }
        return 'sale_price';
    }

    /** Flash a field green to signal it was auto-filled. */
    function flash($el) {
        $el.css({ transition: 'background-color 0.1s', backgroundColor: '#d4edda' });
        setTimeout(function () {
            $el.css({ backgroundColor: '' });
            setTimeout(function () { $el.css({ transition: '' }); }, 400);
        }, 600);
    }

    /** Fill price (and optionally unit) for the inline row. */
    function fillRow(prefix, idx, data) {
        var priceKey = getPriceKey(prefix, idx);

        // Price field
        var priceVal = data[priceKey];
        if (priceVal !== undefined && priceVal !== null) {
            var $price = $('#id_' + prefix + '-' + idx + '-price');
            if ($price.length && parseFloat($price.val() || 0) <= 0) {
                $price.val(priceVal);
                flash($price);
            }
        }

        // Unit field (PO lines only, when product has a base_unit)
        if (data.unit_id) {
            var $unit = $('#id_' + prefix + '-' + idx + '-unit');
            if ($unit.length && !$unit.val()) {
                $unit.val(data.unit_id);
                flash($unit);
            }
        }
    }

    /** Fetch product defaults via AJAX and fill the row. */
    function fetchAndFill(selectEl) {
        var info = parseRowId(selectEl);
        if (!info || !selectEl.value) { return; }

        $.getJSON('/products/ajax/product-info/', { id: selectEl.value })
            .done(function (data) {
                if (data && !data.error) {
                    fillRow(info.prefix, info.idx, data);
                }
            })
            .fail(function () {
                // Silent — AJAX errors don't break the form
            });
    }

    // Handle user product selections (works for dynamically added rows too)
    $(document).on('change', 'select[id$="-product"]', function () {
        fetchAndFill(this);
    });

    // Also catch select2 autocomplete selections
    $(document).on('select2:select', 'select[id$="-product"]', function () {
        fetchAndFill(this);
    });

    // On page load: fill any existing row that has a product but price = 0
    $('select[id$="-product"]').each(function () {
        if (this.value) {
            fetchAndFill(this);
        }
    });
});
