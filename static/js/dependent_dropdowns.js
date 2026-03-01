// Wait for Django's jQuery to be ready
(function() {
    // Function to initialize dependent dropdowns
    function initDependentDropdowns() {
        // Check if django and django.jQuery are available
        if (typeof django !== 'undefined' && django.jQuery) {
            // Use Django's jQuery
            (function($) {
                console.log("✅ Dependent dropdowns JS loaded");
                
                $(document).ready(function() {
                    console.log("📌 Document ready");
                    
                    // Generic function to setup dependent dropdowns with 3 levels
                    function setupDependentDropdowns(config) {
                        var countrySelector = config.countrySelector;
                        var regionSelector = config.regionSelector;
                        var citySelector = config.citySelector;
                        var debug = config.debug || false;
                        
                        var countrySelect = $(countrySelector);
                        var regionSelect = $(regionSelector);
                        var citySelect = $(citySelector);
                        
                        if (debug) {
                            console.log(`Setting up: Country=${countrySelector}, Region=${regionSelector}, City=${citySelector}`);
                            console.log(`Country select found: ${countrySelect.length > 0}`);
                            console.log(`Region select found: ${regionSelect.length > 0}`);
                            console.log(`City select found: ${citySelect.length > 0}`);
                        }
                        
                        // Function to load regions based on country
                        function loadRegions() {
                            var countryId = countrySelect.val();
                            
                            if (debug) console.log(`Country changed to ID: ${countryId}`);
                            
                            if (countryId) {
                                // Show loading in region dropdown
                                regionSelect.html('<option value="">Loading regions...</option>');
                                regionSelect.prop('disabled', true);
                                
                                // Clear and disable city dropdown
                                citySelect.html('<option value="">Select region first</option>');
                                citySelect.prop('disabled', true);
                                
                                // Fetch regions via AJAX
                                $.ajax({
                                    url: '/core/ajax/load-regions/',
                                    data: {
                                        'country': countryId
                                    },
                                    dataType: 'json',
                                    success: function(data) {
                                        if (debug) console.log('Regions loaded:', data);
                                        
                                        // Build options
                                        var options = '<option value="">---------</option>';
                                        $.each(data, function(index, region) {
                                            options += `<option value="${region.id}">${region.name}</option>`;
                                        });
                                        
                                        regionSelect.html(options);
                                        regionSelect.prop('disabled', false);
                                        
                                        // If there was a previously selected region, try to set it
                                        var selectedRegion = regionSelect.data('selected');
                                        if (selectedRegion) {
                                            regionSelect.val(selectedRegion);
                                            regionSelect.removeData('selected');
                                            loadCities(); // Load cities for this region
                                        }
                                    },
                                    error: function(xhr, status, error) {
                                        console.error('Error loading regions:', error);
                                        regionSelect.html('<option value="">Error loading regions</option>');
                                        regionSelect.prop('disabled', false);
                                    }
                                });
                            } else {
                                // No country selected
                                regionSelect.html('<option value="">---------</option>');
                                regionSelect.prop('disabled', true);
                                
                                citySelect.html('<option value="">---------</option>');
                                citySelect.prop('disabled', true);
                            }
                        }
                        
                        // Function to load cities based on region or country
                        function loadCities() {
                            var countryId = countrySelect.val();
                            var regionId = regionSelect.val();
                            
                            if (debug) console.log(`Loading cities - Country: ${countryId}, Region: ${regionId}`);
                            
                            if (regionId) {
                                // Load cities by region
                                citySelect.html('<option value="">Loading cities...</option>');
                                citySelect.prop('disabled', true);
                                
                                $.ajax({
                                    url: '/core/ajax/load-cities-by-region/',
                                    data: {
                                        'region': regionId
                                    },
                                    dataType: 'json',
                                    success: function(data) {
                                        if (debug) console.log('Cities loaded by region:', data);
                                        
                                        var options = '<option value="">---------</option>';
                                        $.each(data, function(index, city) {
                                            options += `<option value="${city.id}">${city.name}</option>`;
                                        });
                                        
                                        citySelect.html(options);
                                        citySelect.prop('disabled', false);
                                        
                                        // Set previously selected city if any
                                        var selectedCity = citySelect.data('selected');
                                        if (selectedCity) {
                                            citySelect.val(selectedCity);
                                            citySelect.removeData('selected');
                                        }
                                    },
                                    error: function(xhr, status, error) {
                                        console.error('Error loading cities by region:', error);
                                        citySelect.html('<option value="">Error loading cities</option>');
                                        citySelect.prop('disabled', false);
                                    }
                                });
                            } else if (countryId) {
                                // Load cities by country (when no region selected)
                                citySelect.html('<option value="">Loading cities...</option>');
                                citySelect.prop('disabled', true);
                                
                                $.ajax({
                                    url: '/core/ajax/load-cities/',
                                    data: {
                                        'country': countryId
                                    },
                                    dataType: 'json',
                                    success: function(data) {
                                        if (debug) console.log('Cities loaded by country:', data);
                                        
                                        var options = '<option value="">---------</option>';
                                        $.each(data, function(index, city) {
                                            options += `<option value="${city.id}">${city.name}</option>`;
                                        });
                                        
                                        citySelect.html(options);
                                        citySelect.prop('disabled', false);
                                        
                                        // Set previously selected city if any
                                        var selectedCity = citySelect.data('selected');
                                        if (selectedCity) {
                                            citySelect.val(selectedCity);
                                            citySelect.removeData('selected');
                                        }
                                    },
                                    error: function(xhr, status, error) {
                                        console.error('Error loading cities by country:', error);
                                        citySelect.html('<option value="">Error loading cities</option>');
                                        citySelect.prop('disabled', false);
                                    }
                                });
                            } else {
                                citySelect.html('<option value="">---------</option>');
                                citySelect.prop('disabled', true);
                            }
                        }
                        
                        // Store initially selected values if any
                        if (regionSelect.val()) {
                            regionSelect.data('selected', regionSelect.val());
                        }
                        if (citySelect.val()) {
                            citySelect.data('selected', citySelect.val());
                        }
                        
                        // Initial load if country preselected
                        if (countrySelect.val()) {
                            loadRegions();
                        }
                        
                        // Event handlers
                        countrySelect.off('change').on('change', function() {
                            loadRegions();
                        });
                        
                        regionSelect.off('change').on('change', function() {
                            loadCities();
                        });
                    }
                    
                    // ============= VENDOR FORMS =============
                    if ($('#id_country').length && $('#id_region').length && $('#id_city').length) {
                        console.log("🔧 Setting up Vendor dropdowns");
                        setupDependentDropdowns({
                            countrySelector: '#id_country',
                            regionSelector: '#id_region',
                            citySelector: '#id_city',
                            debug: false
                        });
                    }
                    
                    // ============= CUSTOMER BILLING ADDRESS =============
                    if ($('#id_billing_country').length && $('#id_billing_region').length && $('#id_billing_city').length) {
                        console.log("🔧 Setting up Customer billing dropdowns");
                        setupDependentDropdowns({
                            countrySelector: '#id_billing_country',
                            regionSelector: '#id_billing_region',
                            citySelector: '#id_billing_city',
                            debug: false
                        });
                    }
                    
                    // ============= CUSTOMER SHIPPING ADDRESS =============
                    if ($('#id_shipping_country').length && $('#id_shipping_region').length && $('#id_shipping_city').length) {
                        console.log("🔧 Setting up Customer shipping dropdowns");
                        setupDependentDropdowns({
                            countrySelector: '#id_shipping_country',
                            regionSelector: '#id_shipping_region',
                            citySelector: '#id_shipping_city',
                            debug: false
                        });
                    }
                    
                    // ============= SAME AS BILLING CHECKBOX =============
                    function setupSameAsBilling() {
                        var sameAsBillingCheckbox = $('#id_same_as_billing');
                        
                        if (!sameAsBillingCheckbox.length) {
                            console.log("No 'same as billing' checkbox found");
                            return;
                        }
                        
                        console.log("Setting up 'same as billing' functionality");
                        
                        // Function to copy billing to shipping
                        function copyBillingToShipping() {
                            console.log("Copying billing to shipping");
                            
                            // Copy text fields - USING CORRECT FIELD NAMES
                            $('#id_shipping_address_line1').val($('#id_billing_address_line1').val());
                            $('#id_shipping_address_line2').val($('#id_billing_address_line2').val());
                            $('#id_shipping_postal_code').val($('#id_billing_postal_code').val()); // FIXED: using correct postal code field
                            
                            // Copy country and trigger change
                            var billingCountry = $('#id_billing_country').val();
                            $('#id_shipping_country').val(billingCountry).trigger('change');
                            
                            // Store region and city to be set after loading
                            var billingRegion = $('#id_billing_region').val();
                            var billingCity = $('#id_billing_city').val();
                            
                            if (billingRegion) {
                                console.log("Waiting for shipping region to load...");
                                // Wait for regions to load, then set region and trigger city load
                                var checkRegionInterval = setInterval(function() {
                                    if ($('#id_shipping_region option[value="' + billingRegion + '"]').length) {
                                        console.log("Shipping region loaded, setting to:", billingRegion);
                                        $('#id_shipping_region').val(billingRegion).trigger('change');
                                        clearInterval(checkRegionInterval);
                                        
                                        // After region loads, set city
                                        if (billingCity) {
                                            var checkCityInterval = setInterval(function() {
                                                if ($('#id_shipping_city option[value="' + billingCity + '"]').length) {
                                                    console.log("Shipping city loaded, setting to:", billingCity);
                                                    $('#id_shipping_city').val(billingCity);
                                                    clearInterval(checkCityInterval);
                                                }
                                            }, 100);
                                        }
                                    }
                                }, 100);
                            } else if (billingCity) {
                                console.log("No region, waiting for shipping city to load...");
                                // No region, just set city after it loads
                                var checkCityInterval = setInterval(function() {
                                    if ($('#id_shipping_city option[value="' + billingCity + '"]').length) {
                                        console.log("Shipping city loaded, setting to:", billingCity);
                                        $('#id_shipping_city').val(billingCity);
                                        clearInterval(checkCityInterval);
                                    }
                                }, 100);
                            }
                        }
                        
                        // Function to clear shipping address
                        function clearShippingAddress() {
                            console.log("Clearing shipping address");
                            
                            // Clear text fields - USING CORRECT FIELD NAMES
                            $('#id_shipping_address_line1').val('');
                            $('#id_shipping_address_line2').val('');
                            $('#id_shipping_postal_code').val(''); // FIXED: using correct postal code field
                            
                            // Clear country and trigger change (which will clear region and city)
                            $('#id_shipping_country').val('').trigger('change');
                            
                            // Manually clear region and city as well (in case change event doesn't handle it)
                            $('#id_shipping_region').empty().append('<option value="">---------</option>').prop('disabled', true);
                            $('#id_shipping_city').empty().append('<option value="">---------</option>').prop('disabled', true);
                        }
                        
                        // Handle checkbox change
                        sameAsBillingCheckbox.on('change', function() {
                            if ($(this).is(':checked')) {
                                copyBillingToShipping();
                            } else {
                                clearShippingAddress();
                            }
                        });
                        
                        // If checkbox is pre-checked (when editing an existing record), run the copy
                        if (sameAsBillingCheckbox.is(':checked')) {
                            console.log("Checkbox is pre-checked, copying on load");
                            // Small delay to ensure all dropdowns are initialized
                            setTimeout(copyBillingToShipping, 500);
                        }
                    }
                    
                    // Initialize same as billing functionality
                    setupSameAsBilling();
                    
                    console.log("✅ All dependent dropdowns initialized");
                });
            })(django.jQuery);
        } else {
            // Django jQuery not loaded yet, try again in 100ms
            console.log("⏳ Waiting for Django jQuery...");
            setTimeout(initDependentDropdowns, 100);
        }
    }
    
    // Start the initialization process
    initDependentDropdowns();
})();