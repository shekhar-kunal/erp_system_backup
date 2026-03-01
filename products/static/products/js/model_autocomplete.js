(function($) {
    $(document).ready(function() {
        console.log("Model autocomplete initialized");
        
        function initModelAutocomplete() {
            var $modelSelect = $('#id_model_number');
            var $brandSelect = $('#id_brand');
            
            if (!$modelSelect.length || !$brandSelect.length) return;
            
            var ajaxUrl = $modelSelect.data('ajax-url');
            
            // Initialize select2 if available, otherwise use our custom AJAX
            if (typeof $.fn.select2 !== 'undefined') {
                // Use Select2 if available
                $modelSelect.select2({
                    ajax: {
                        url: ajaxUrl,
                        dataType: 'json',
                        delay: 250,
                        data: function(params) {
                            return {
                                term: params.term,
                                brand_id: $brandSelect.val()
                            };
                        },
                        processResults: function(data) {
                            return {
                                results: data.results
                            };
                        },
                        cache: true
                    },
                    placeholder: 'Select model number...',
                    minimumInputLength: 0,
                    allowClear: true
                });
            } else {
                // Fallback: Load models via AJAX when brand changes
                function loadModels() {
                    var brandId = $brandSelect.val();
                    
                    $.ajax({
                        url: ajaxUrl,
                        data: {
                            brand_id: brandId
                        },
                        success: function(data) {
                            var options = '<option value="">---------</option>';
                            data.results.forEach(function(item) {
                                options += `<option value="${item.id}">${item.text}</option>`;
                            });
                            $modelSelect.html(options);
                        }
                    });
                }
                
                // Load on brand change
                $brandSelect.on('change', loadModels);
                
                // Initial load
                loadModels();
            }
        }
        
        initModelAutocomplete();
    });
})(django.jQuery);