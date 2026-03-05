// Setup Wizard JavaScript
$(document).ready(function() {
    // Form validation
    $('form').on('submit', function(e) {
        var isValid = true;
        
        $(this).find('input[required], select[required]').each(function() {
            if (!$(this).val()) {
                $(this).addClass('is-invalid');
                isValid = false;
            } else {
                $(this).removeClass('is-invalid');
            }
        });
        
        return isValid;
    });
    
    // Password strength indicator
    $('#id_password').on('keyup', function() {
        var password = $(this).val();
        var strength = 0;
        
        if (password.length >= 8) strength++;
        if (password.match(/[A-Z]/)) strength++;
        if (password.match(/[0-9]/)) strength++;
        if (password.match(/[!@#$%^&*(),.?":{}|<>]/)) strength++;
        
        var meter = $('.password-strength');
        if (meter.length === 0) {
            $(this).after('<div class="password-strength mt-2"></div>');
            meter = $('.password-strength');
        }
        
        var strengthText = ['Weak', 'Fair', 'Good', 'Strong'];
        var strengthColor = ['#dc3545', '#ffc107', '#17a2b8', '#28a745'];
        
        meter.html(`
            <div class="progress" style="height: 5px;">
                <div class="progress-bar" style="width: ${strength * 25}%; background: ${strengthColor[strength-1] || '#dc3545'}"></div>
            </div>
            <small class="text-muted">${strengthText[strength-1] || 'Too weak'}</small>
        `);
    });
    
    // Confirm password match
    $('#id_confirm_password').on('keyup', function() {
        var password = $('#id_password').val();
        var confirm = $(this).val();
        
        if (password !== confirm) {
            $(this).addClass('is-invalid');
            if ($('.password-match-error').length === 0) {
                $(this).after('<div class="password-match-error text-danger mt-1">Passwords do not match</div>');
            }
        } else {
            $(this).removeClass('is-invalid');
            $('.password-match-error').remove();
        }
    });
    
    // Auto-save form data (optional)
    var formData = {};
    $('form input, form select').on('change', function() {
        var field = $(this).attr('name');
        var value = $(this).val();
        formData[field] = value;
        sessionStorage.setItem('setupFormData', JSON.stringify(formData));
    });
    
    // Load saved form data
    var savedData = sessionStorage.getItem('setupFormData');
    if (savedData) {
        formData = JSON.parse(savedData);
        $.each(formData, function(field, value) {
            $('[name="' + field + '"]').val(value);
        });
    }
    
    // Clear session storage on complete
    if (window.location.pathname.includes('complete')) {
        sessionStorage.removeItem('setupFormData');
    }
});