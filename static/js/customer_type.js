(function($) {
    $(document).ready(function() {
        console.log("Customer type JS loaded");
        
        var customerTypeField = $('#id_customer_type');
        var individualFields = $('.individual-fields');
        var businessFields = $('.business-fields');
        
        function toggleFields() {
            var customerType = customerTypeField.val();
            console.log("Customer type changed to:", customerType);
            
            if (customerType === 'individual') {
                individualFields.show();
                businessFields.hide();
                
                // Enable individual fields
                $('#id_first_name').prop('disabled', false);
                $('#id_last_name').prop('disabled', false);
                $('#id_date_of_birth').prop('disabled', false);
                
                // Disable business fields
                $('#id_company_name').prop('disabled', true).val('');
                $('#id_company_registration').prop('disabled', true).val('');
                $('#id_business_type').prop('disabled', true).val('');
                $('#id_website').prop('disabled', true).val('');
            } else if (customerType === 'business') {
                individualFields.hide();
                businessFields.show();
                
                // Enable business fields
                $('#id_company_name').prop('disabled', false);
                $('#id_company_registration').prop('disabled', false);
                $('#id_business_type').prop('disabled', false);
                $('#id_website').prop('disabled', false);
                
                // Disable individual fields
                $('#id_first_name').prop('disabled', true).val('');
                $('#id_last_name').prop('disabled', true).val('');
                $('#id_date_of_birth').prop('disabled', true).val('');
            }
        }
        
        // Initial toggle
        toggleFields();
        
        // Toggle on change
        customerTypeField.change(toggleFields);
    });
})(django.jQuery);