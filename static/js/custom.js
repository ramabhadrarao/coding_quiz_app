// Custom JavaScript for Coding Quiz App

// Function to handle code editor initialization
function initializeCodeEditor(editorId, language, readOnly = false) {
    // Code Mirror language modes mapping
    const modeMap = {
        'python': 'python',
        'c': 'text/x-csrc',
        'java': 'text/x-java',
        // Add more languages as needed
    };
    
    const editorElement = document.getElementById(editorId);
    
    if (!editorElement) return null;
    
    // Initialize CodeMirror editor
    const editor = CodeMirror.fromTextArea(editorElement, {
        lineNumbers: true,
        mode: modeMap[language] || 'text/plain',
        theme: 'dracula',
        matchBrackets: true,
        autoCloseBrackets: true,
        indentUnit: 4,
        tabSize: 4,
        indentWithTabs: false,
        extraKeys: {"Tab": "indentMore", "Shift-Tab": "indentLess"},
        readOnly: readOnly
    });
    
    return editor;
}

// Function to update timer display
function updateTimerDisplay(element, seconds) {
    if (!element) return;
    
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = seconds % 60;
    const formattedTime = `${minutes.toString().padStart(2, '0')}:${remainingSeconds.toString().padStart(2, '0')}`;
    
    element.textContent = formattedTime;
    
    // Add warning classes as time gets low
    if (seconds <= 60) { // Less than 1 minute
        element.classList.add('timer-danger');
        element.classList.remove('timer-warning');
    } else if (seconds <= 300) { // Less than 5 minutes
        element.classList.add('timer-warning');
        element.classList.remove('timer-danger');
    }
}

// Function to handle quiz timer
function startQuizTimer(elementId, initialSeconds, submissionId, submitFormId) {
    const timerElement = document.getElementById(elementId);
    if (!timerElement) return;
    
    let remainingSeconds = initialSeconds;
    
    // Update timer display
    updateTimerDisplay(timerElement, remainingSeconds);
    
    // Update timer every second
    const timerInterval = setInterval(() => {
        remainingSeconds--;
        
        if (remainingSeconds <= 0) {
            // Time's up - submit the quiz
            clearInterval(timerInterval);
            document.getElementById(submitFormId).submit();
            return;
        }
        
        updateTimerDisplay(timerElement, remainingSeconds);
    }, 1000);
    
    // Sync with server time every 30 seconds
    setInterval(() => {
        fetch(`/api/time-remaining/${submissionId}`)
            .then(response => response.json())
            .then(data => {
                remainingSeconds = data.timeRemaining;
                updateTimerDisplay(timerElement, remainingSeconds);
            })
            .catch(error => console.error('Error fetching time:', error));
    }, 30000);
}

// Function to run code in the live test area
function setupCodeRunner(editor, runButtonId, inputId, outputId, languageSelectId) {
    const runButton = document.getElementById(runButtonId);
    if (!runButton) return;
    
    runButton.addEventListener('click', () => {
        const code = editor.getValue();
        const language = document.getElementById(languageSelectId).value;
        const input = document.getElementById(inputId).value;
        
        // Show the test area
        const outputElement = document.getElementById(outputId);
        outputElement.textContent = 'Running code...';
        
        // Send to API
        fetch('/api/run-code', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                code: code,
                language: language,
                stdin: input
            })
        })
        .then(response => response.json())
        .then(data => {
            let output = '';
            
            if (!data.success) {
                output = `Error: ${data.error}`;
            } else {
                const result = data.run;
                if (result.stderr) {
                    output = `Error:\n${result.stderr}`;
                } else {
                    output = result.stdout || 'No output';
                }
            }
            
            outputElement.textContent = output;
        })
        .catch(error => {
            outputElement.textContent = `Error: ${error.message}`;
        });
    });
}

// Setup modal confirmation for destructive actions
function setupConfirmDialog(triggerSelector, actionSelector, cancelSelector) {
    document.querySelectorAll(triggerSelector).forEach(trigger => {
        trigger.addEventListener('click', (e) => {
            e.preventDefault();
            
            const modal = new bootstrap.Modal(document.getElementById(trigger.dataset.modalTarget));
            
            document.querySelector(actionSelector).addEventListener('click', () => {
                document.getElementById(trigger.dataset.formTarget).submit();
            });
            
            document.querySelector(cancelSelector).addEventListener('click', () => {
                modal.hide();
            });
            
            modal.show();
        });
    });
}

// Document ready handler
document.addEventListener('DOMContentLoaded', function() {
    // Initialize tooltips
    var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
    
    // Auto-hide alerts after 5 seconds
    setTimeout(() => {
        document.querySelectorAll('.alert').forEach(alert => {
            const bsAlert = new bootstrap.Alert(alert);
            bsAlert.close();
        });
    }, 5000);
});

// Form validation enhancement
function setupFormValidation(formId) {
    const form = document.getElementById(formId);
    if (!form) return;
    
    form.addEventListener('submit', (event) => {
        if (!form.checkValidity()) {
            event.preventDefault();
            event.stopPropagation();
        }
        
        form.classList.add('was-validated');
    });
}
