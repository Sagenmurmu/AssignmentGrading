document.addEventListener('DOMContentLoaded', function() {
    const dropZone = document.getElementById('drop-zone');
    const fileInput = document.getElementById('file-upload');
    const extractButton = document.getElementById('extract-text');
    const answerTextarea = document.getElementById('answer');

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

            const result = await response.json();
            
            if (result.success) {
                answerTextarea.value = result.text;
            } else {
                alert('Error extracting text: ' + result.error);
            }
        } catch (error) {
            alert('Error uploading file: ' + error);
        } finally {
            extractButton.disabled = false;
            extractButton.innerHTML = '<i class="bi bi-eye"></i> Extract Text';
        }
    });
});
