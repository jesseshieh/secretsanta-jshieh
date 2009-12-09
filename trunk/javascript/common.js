var is_mass_validating = false;

// common page level initializations on document ready
function common_init() {
    $(":button").addClass("fg-button ui-state-default ui-corner-all");
    $(":button").hover(function(){
            $(this).addClass("ui-state-hover");
        },
        function(){
            $(this).removeClass("ui-state-hover");
        }
        );
    $(".box").tabs();
}

// you need to implement or override enable_submit() and disable_submit()
var on_invalid = function() {
    this.insertMessage(this.createMessageSpan());
    this.addFieldClass();
    disable_submit();
};

var on_valid = function() {
    this.insertMessage(this.createMessageSpan());
    this.addFieldClass();

    if (!is_mass_validating) {
        is_mass_validating = true;
        this.formObj.removeField(this);
        if (LiveValidation.massValidate(this.formObj.fields)) {
            enable_submit();
        }
        this.formObj.addField(this);
        is_mass_validating = false;
    }
};

var validations = new Array();
function add_detail_validations() {
    // add validation indicator
    var date_validator = new LiveValidation("signup_deadline", {
            validMessage: "\u2714",
            onInvalid: on_invalid,
            onValid: on_valid,
            onBlurWait: 300
        });
    date_validator.add(Validate.Presence, { failureMessage: "\u2716" });
    date_validator.add(Validate.Format, {
            pattern: /(0[1-9]|1[0-2])\/(0[1-9]|[1-2][0-9]|3[0-1])\/[0-9]{4}/,
                failureMessage: "\u2716" });
    validations["signup_deadline"] = date_validator;

    var date_validator = new LiveValidation("exchange_date", {
            validMessage: "\u2714",
            onInvalid: on_invalid,
            onValid: on_valid,
            onBlurWait: 300
        });
    date_validator.add(Validate.Presence, { failureMessage: "\u2716" });
    date_validator.add(Validate.Format, {
            pattern: /^(0[1-9]|1[0-2])\/(0[1-9]|[1-2][0-9]|3[0-1])\/[0-9]{4}$/,
                                                                                failureMessage: "\u2716" });
    validations["exchange_date"] = date_validator;

    price_validator = new LiveValidation("price", {
            validMessage: "\u2714",
            onInvalid: on_invalid,
            onValid: on_valid
        });
    price_validator.add(Validate.Presence, { failureMessage: "\u2716" });
    price_validator.add(Validate.Format, {
            pattern: /^[$]?[0-9]+([.]\d{2})?$/,
                failureMessage: "\u2716" });
    validations["price"] = price_validator;

    var location_validator = new LiveValidation("location", {
            validMessage: "\u2714",
            onInvalid: on_invalid,
            onValid: on_valid
        });
    location_validator.add(Validate.Presence, { failureMessage: "\u2716" });
    validations["location"] = location_validator;

}

