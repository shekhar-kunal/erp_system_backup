(function($) {
    $(document).ready(function() {
        console.log("Duplicate confirmation JS loaded");
        
        // Look for duplicate name warnings in the form
        function checkForDuplicateWarning() {
            var nameField = $('#id_name');
            var errorList = nameField.closest('.form-row').find('.errorlist');
            
            if (errorList.length > 0 && errorList.text().includes('already exists')) {
                console.log("Duplicate name detected");
                
                // Store form data before submission
                var form = $('form');
                var formData = form.serialize();
                sessionStorage.setItem('pendingFormData', formData);
                
                // Show confirmation dialog
                if (confirm('A vendor with this name already exists. Do you want to save anyway?')) {
                    // User confirmed, submit with confirm_duplicate flag
                    $('<input>').attr({
                        type: 'hidden',
                        name: 'confirm_duplicate',
                        value: 'on'
                    }).appendTo(form);
                    
                    return true;
                } else {
                    // User cancelled, prevent form submission
                    return false;
                }
            }
            return true;
        }
        
        // Intercept form submission
        $('form').on('submit', function(e) {
            // Check if this is a vendor form
            if ($('#id_name').length > 0 && $('#id_code').length > 0) {
                return checkForDuplicateWarning();
            }
            return true;
        });
    });
})(django.jQuery);