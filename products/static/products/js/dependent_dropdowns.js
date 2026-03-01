// Dependent dropdowns for Product Admin - IMPROVED VERSION
(function() {
    // Function to initialize when django.jQuery is ready
    function initDependentDropdowns($) {
        console.log("====================================");
        console.log("Dependent dropdowns initialized with improved error handling");
        console.log("====================================");
        
        $(document).ready(function() {
            var $brandSelect = $('#id_brand');
            var $modelSelect = $('#id_model_number');
            
            console.log("Brand select found:", $brandSelect.length > 0);
            console.log("Model select found:", $modelSelect.length > 0);
            
            if (!$brandSelect.length || !$modelSelect.length) {
                console.warn("Required selects not found - this page may not need dependent dropdowns");
                return;
            }
            
            // Store current model ID for preserving selection
            var currentModelId = $modelSelect.val();
            console.log("Initial brand value:", $brandSelect.val());
            console.log("Initial model value:", currentModelId);
            
            function loadModels(brandId) {
                console.log("------------------------------------");
                console.log("loadModels called with brandId:", brandId);
                
                // Clear dropdown if no brand selected
                if (!brandId) {
                    console.log("No brand selected, clearing model dropdown");
                    $modelSelect.html('<option value="">---------</option>');
                    
                    // If we had a current model, we need to show it anyway
                    if (currentModelId) {
                        console.log("But we have a current model ID:", currentModelId);
                        loadModelsWithCurrent();
                    }
                    return;
                }
                
                // Show loading state
                $modelSelect.html('<option value="">Loading models...</option>');
                $modelSelect.prop('disabled', true);
                
                var ajaxUrl = '/products/ajax/load-models/';
                console.log("AJAX URL:", ajaxUrl);
                console.log("Request data:", {
                    'brand_id': brandId,
                    'current_model_id': currentModelId
                });
                
                $.ajax({
                    url: ajaxUrl,
                    data: {
                        'brand_id': brandId,
                        'current_model_id': currentModelId
                    },
                    dataType: 'json',
                    timeout: 5000, // 5 second timeout
                    success: function(response) {
                        console.log("AJAX success! Full response:", response);
                        
                        // Check if response has success flag (new format)
                        if (response.success === false) {
                            console.error("Server returned error:", response.error);
                            $modelSelect.html('<option value="">Error: ' + (response.error || 'Unknown error') + '</option>');
                            $modelSelect.prop('disabled', false);
                            return;
                        }
                        
                        // Handle both old and new response formats
                        var models = response.models || response.results || [];
                        
                        if (!models || models.length === 0) {
                            console.log("No models found for this brand");
                            $modelSelect.html('<option value="">No models available for this brand</option>');
                            $modelSelect.prop('disabled', false);
                            return;
                        }
                        
                        console.log("Processing", models.length, "models");
                        
                        var options = '<option value="">---------</option>';
                        var foundCurrent = false;
                        
                        $.each(models, function(index, model) {
                            // Handle both object formats
                            var id = model.id;
                            var name = model.name || model.text || 'Unknown';
                            var code = model.code || '';
                            var displayName = code ? name + ' (' + code + ')' : name;
                            
                            // Check if this is the currently selected model
                            var selected = (id == currentModelId) ? 'selected' : '';
                            if (selected) {
                                foundCurrent = true;
                                console.log("Found current model in list:", displayName);
                            }
                            
                            options += `<option value="${id}" ${selected}>${displayName}</option>`;
                        });
                        
                        // If current model wasn't in the list but we have one, add it manually
                        if (currentModelId && !foundCurrent) {
                            console.log("Current model not in list, will be added by server");
                            // Server should have included it, but if not, we'll note it
                        }
                        
                        $modelSelect.html(options);
                        $modelSelect.prop('disabled', false);
                        
                        console.log("Dropdown updated successfully");
                    },
                    error: function(xhr, status, error) {
                        console.error("AJAX error:", error);
                        console.error("Status:", status);
                        console.error("Response:", xhr.responseText);
                        
                        var errorMsg = 'Error loading models';
                        if (status === 'timeout') {
                            errorMsg = 'Request timeout - please try again';
                        } else if (xhr.status === 404) {
                            errorMsg = 'AJAX endpoint not found';
                        } else if (xhr.status === 500) {
                            errorMsg = 'Server error - check logs';
                        }
                        
                        $modelSelect.html('<option value="">' + errorMsg + '</option>');
                        $modelSelect.prop('disabled', false);
                    }
                });
            }
            
            // Special function to load just the current model
            function loadModelsWithCurrent() {
                if (!currentModelId) return;
                
                $.ajax({
                    url: '/products/ajax/load-models/',
                    data: {
                        'current_model_id': currentModelId
                    },
                    dataType: 'json',
                    success: function(response) {
                        var models = response.models || response.results || [];
                        var options = '<option value="">---------</option>';
                        
                        $.each(models, function(index, model) {
                            if (model.id == currentModelId) {
                                var name = model.name || model.text || 'Unknown';
                                var code = model.code || '';
                                var displayName = code ? name + ' (' + code + ')' : name;
                                options += `<option value="${model.id}" selected>${displayName}</option>`;
                            }
                        });
                        
                        $modelSelect.html(options);
                    }
                });
            }
            
            // Initial load if brand is selected
            var initialBrandId = $brandSelect.val();
            if (initialBrandId) {
                loadModels(initialBrandId);
            } else if (currentModelId) {
                // If no brand but we have a model, load just that model
                loadModelsWithCurrent();
            }
            
            // Handle brand change events
            $brandSelect.on('change', function() {
                var newBrandId = $(this).val();
                console.log("Brand changed to:", newBrandId);
                loadModels(newBrandId);
            });
            
            // Also handle when brand is cleared
            $brandSelect.on('select2:clear', function() {
                console.log("Brand cleared");
                loadModels(null);
            });
        });
    }

    // Check if django.jQuery is already available
    if (window.django && window.django.jQuery) {
        initDependentDropdowns(window.django.jQuery);
    } else {
        // If not, wait for it to load
        console.log("Waiting for django.jQuery to load...");
        var checkInterval = setInterval(function() {
            if (window.django && window.django.jQuery) {
                clearInterval(checkInterval);
                console.log("django.jQuery loaded, initializing...");
                initDependentDropdowns(window.django.jQuery);
            }
        }, 50);
        
        // Timeout after 5 seconds
        setTimeout(function() {
            clearInterval(checkInterval);
            console.error("Failed to load django.jQuery after 5 seconds");
        }, 5000);
    }
})();