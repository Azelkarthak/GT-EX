document.addEventListener("DOMContentLoaded", function () {
    const gunitInput = document.getElementById('lob-input');
    const gunitForm = document.getElementById('gunit-input');
    const output = document.getElementById('output');
    const dropdownID = document.getElementById('lob_select');
    const baseMethodInput = document.getElementById('base_method_input');
    const classNameInput = document.getElementById('class_name_input');
    const selectedFeaturesInput = document.getElementById('selected-features');
    const uploadBtn = document.getElementById('upload-gunit');

    let gunitInputDisplayed = false;

    // Function to show the form and hide output
    function showForm() {
        if (gunitInput) gunitInput.style.display = 'block';
        if (gunitForm) gunitForm.style.display = 'block';
        if (output) output.style.display = 'none';
        gunitInputDisplayed = true;
    }

    // Function to hide form and show output
    function showOutput() {
        if (gunitInput) gunitInput.style.display = 'none';
        if (gunitForm) gunitForm.style.display = 'none';
        if (output) output.style.display = 'block';
        gunitInputDisplayed = false;
    }

    // Handle page load state
    function handleInitialState() {
        const hasResponse = window.hasResponse || false; // Set by your template
        if (hasResponse) {
            showOutput();
        } else {
            showForm();
        }
    }

    // Reset form state on page reload
    window.addEventListener('pageshow', function(event) {
        if (event.persisted) {
            // Page is loaded from cache (browser back/forward)
            showForm();
        }
    });

    // Handle LOB dropdown changes
    dropdownID.addEventListener('change', function (event) {
        const selectedLOB = event.target.value;
        if (selectedLOB && selectedLOB !== "") {
            document.getElementById("selected_lob").value = selectedLOB;
            showForm();
        } else {
            if (gunitInput) gunitInput.style.display = 'none';
            if (gunitForm) gunitForm.style.display = 'none';
            gunitInputDisplayed = false;
        }
    });

    // Form validation and submission
    uploadBtn.addEventListener('click', (event) => {
        event.preventDefault();
        if (validateForm()) {
            document.getElementById('uploadGunit').submit();
        }
    });

    // Initialize the page state
    handleInitialState();

    // Your existing validation function
    function validateForm() {
        let isValid = true;
        const lob = document.getElementById('lob');
        const builder = document.getElementById('builder');
        const gunitType = document.querySelectorAll('input[name="gunit_type"]:checked');
        const baseMethodTextarea = document.getElementById('base_method_textarea');
        const className = document.getElementById('class_name');

        if (!lob.value) {
            isValid = false;
            alert('Please select a Line Of Business.');
        }

        if (!builder.value) {
            isValid = false;
            alert('Please select a Builder.');
        }

        if (gunitType.length === 0) {
            isValid = false;
            alert('Please select a Gunit Type.');
        }

        if (gunitType.length > 0) {
            if (gunitType[0].value === 'base_method' && !baseMethodTextarea.value.trim()) {
                isValid = false;
                alert('Please enter the Base Method.');
            }

            if (gunitType[0].value === 'class' && !className.value.trim()) {
                isValid = false;
                alert('Please enter the Class Name.');
            }
        }

        return isValid;
    }
});