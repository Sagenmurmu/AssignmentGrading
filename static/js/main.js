document.addEventListener('DOMContentLoaded', function() {
    // Only initialize file upload handling if we're on the submission page
    const dropZone = document.getElementById('drop-zone');
    const fileInput = document.getElementById('file-upload');
    const extractButton = document.getElementById('extract-text');
    const answerTextarea = document.getElementById('answer');
    const gradingForm = document.getElementById('grading-form');

    if (dropZone && fileInput && extractButton && answerTextarea) {
        // Add click handler for the drop zone
        dropZone.addEventListener('click', () => {
            fileInput.click(); // Trigger file input when drop zone is clicked
        });

        // Drag and drop functionality
        ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
            dropZone.addEventListener(eventName, preventDefaults, false);
        });

        function preventDefaults(e) {
            e.preventDefault();
            e.stopPropagation();
        }

        ['dragenter', 'dragover'].forEach(eventName => {
            dropZone.addEventListener(eventName, highlight, false);
        });

        ['dragleave', 'drop'].forEach(eventName => {
            dropZone.addEventListener(eventName, unhighlight, false);
        });

        function highlight(e) {
            dropZone.classList.add('drop-zone-active');
        }

        function unhighlight(e) {
            dropZone.classList.remove('drop-zone-active');
        }

        dropZone.addEventListener('drop', handleDrop, false);

        function handleDrop(e) {
            const dt = e.dataTransfer;
            const files = dt.files;
            fileInput.files = files;
            handleFiles(files);
        }

        fileInput.addEventListener('change', function() {
            handleFiles(this.files);
        });

        function handleFiles(files) {
            if (files.length > 0) {
                const file = files[0];
                if (!file.type.match('image.*') && !file.type.match('application/pdf')) {
                    alert('Please upload an image or PDF file');
                    return;
                }
                const fileName = file.name;
                dropZone.querySelector('.drop-zone-prompt').innerHTML = `
                    <i class="bi bi-file-earmark-text"></i>
                    <p>${fileName}</p>
                `;
            }
        }

        // Extract text functionality
        extractButton.addEventListener('click', async function() {
            const file = fileInput.files[0];
            if (!file) {
                alert('Please select a file first');
                return;
            }

            const formData = new FormData();
            formData.append('file', file);

            try {
                extractButton.disabled = true;
                extractButton.innerHTML = '<i class="bi bi-hourglass"></i> Extracting...';

                const response = await fetch('/extract', {
                    method: 'POST',
                    body: formData
                });

                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }

                const result = await response.json();

                if (result.success) {
                    answerTextarea.value = result.text;
                } else {
                    throw new Error(result.error || 'Error extracting text');
                }
            } catch (error) {
                console.error('Error:', error);
                alert('Error extracting text: ' + error.message);
            } finally {
                extractButton.disabled = false;
                extractButton.innerHTML = '<i class="bi bi-eye"></i> Extract Text';
            }
        });
    }
});