document.addEventListener('DOMContentLoaded', function() {
    const brandForm = document.getElementById('brandForm');
    const generateBtn = document.getElementById('generateBtn');
    const loadingPrompts = document.getElementById('loadingPrompts');
    const promptResults = document.getElementById('promptResults');
    const promptContainer = document.querySelector('.prompt-container');
    const videoLoading = document.getElementById('videoLoading');
    
    let brandInput = '';
    let selectedPromptCard = null; // Seçilen prompt kartını takip etmek için değişken
    
    // Prompt kartını seçili olarak işaretleyen fonksiyon
    function selectPromptCard(card) {
        // Önceki seçili kartı temizle
        if (selectedPromptCard) {
            selectedPromptCard.classList.remove('selected');
        }
        
        // Yeni kartı seç
        card.classList.add('selected');
        selectedPromptCard = card;
    }
    
    brandForm.addEventListener('submit', function(e) {
        e.preventDefault();
        
        const brandInput = document.getElementById('brandInput').value;
        if (!brandInput) {
            alert('Lütfen marka/ürün bilgisi girin');
            return;
        }
        
        // Eski promptları ve video sonuçlarını gizle
        promptResults.classList.add('hidden');
        if (document.getElementById('videoResult')) {
            document.getElementById('videoResult').classList.add('hidden');
        }
        promptContainer.innerHTML = ''; // Eski promptları temizle
        selectedPromptCard = null; // Seçili prompt kartını sıfırla
        
        // Promptları oluşturma işlemi
        loadingPrompts.classList.remove('hidden');
        
        // Yeni API endpoint'ine istek at
        fetch('/generate-prompt', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                text: brandInput,
                feature_type: 'video'
            })
        })
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! Status: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            if (data.error) {
                alert('Hata: ' + data.error);
                return;
            }
            
            // Hide loading state
            loadingPrompts.classList.add('hidden');
            
            // Log function calls if they exist
            if (data.function_calls && data.function_calls.length > 0) {
                console.log('Function calls:', data.function_calls);
            }
            
            // Log prompts to console
            if (data.prompt_data && data.prompt_data.length > 0) {
                console.log('\n📝 Generated Prompts:');
                data.prompt_data.forEach((item, index) => {
                    console.log(`\nPrompt ${index + 1}:`);
                    console.log('Style:', item.style);
                    console.log('Prompt:', item.prompt);
                    console.log('------------------------');
                });
            } else if (data.prompts && data.prompts.length > 0) {
                console.log('\n📝 Generated Prompts:');
                data.prompts.forEach((prompt, index) => {
                    console.log(`\nPrompt ${index + 1}:`);
                    console.log(prompt);
                    console.log('------------------------');
                });
            } else {
                console.log('No prompts were generated');
            }
            
            // Update aspect ratio selection
            updateSelectedAspectRatio();
        })
        .catch(error => {
            loadingPrompts.classList.add('hidden');
            console.error('API hatası:', error);
            alert('Bir hata oluştu: ' + error.message);
        });
    });
    
    function generateVideo(prompt, brandInput, aspectRatio) {
        // Seçilen prompt ve aspect ratio ile video oluştur
        promptResults.classList.add('hidden'); // Prompt sonuçlarını gizle
        videoLoading.classList.remove('hidden');
        
        const formData = new FormData();
        formData.append('prompt', prompt);
        formData.append('brand_input', brandInput);
        formData.append('aspect_ratio', aspectRatio);
        
        fetch('/generate_video', {
            method: 'POST',
            body: formData
        })
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! Status: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            videoLoading.classList.add('hidden');
            
            if (data.error) {
                alert('Hata: ' + data.error);
                promptResults.classList.remove('hidden');
                return;
            }
            
            // Video oluşturulduğunda video.html sayfasına yönlendir
            window.location.href = `/video?video_url=${encodeURIComponent(data.video_url)}&prompt=${encodeURIComponent(data.prompt)}&brand=${encodeURIComponent(data.brand_input)}`;
        })
        .catch(error => {
            videoLoading.classList.add('hidden');
            promptResults.classList.remove('hidden');
            console.error('Video oluşturma hatası:', error);
            alert('Bir hata oluştu: ' + error.message);
        });
    }
    
    // Aspect ratio seçimi için
    function updateSelectedAspectRatio() {
        const aspectRatioInputs = document.querySelectorAll('.aspect-ratio-input');
        const aspectRatioOptions = document.querySelectorAll('.aspect-ratio-option');
        
        aspectRatioOptions.forEach(option => {
            const input = option.querySelector('input');
            if (input.checked) {
                option.classList.add('selected');
            } else {
                option.classList.remove('selected');
            }
        });
        
        // Her bir radio input için event listener ekle
        aspectRatioInputs.forEach(input => {
            input.addEventListener('change', function() {
                aspectRatioOptions.forEach(option => {
                    const optionInput = option.querySelector('input');
                    if (optionInput.checked) {
                        option.classList.add('selected');
                    } else {
                        option.classList.remove('selected');
                    }
                });
            });
        });
    }
    
    // Sayfada "Oluştur" butonuna tıklandığında seçili prompt ile video oluştur
    document.addEventListener('click', function(e) {
        if (e.target.classList.contains('create-video-btn')) {
            if (!selectedPromptCard) {
                alert('Lütfen önce bir prompt seçin');
                return;
            }
            
            // Seçilen prompt ve aspect ratio ile video oluştur
            const promptContent = selectedPromptCard.querySelector('.prompt-content p');
            const aspectRatio = document.querySelector('input[name="aspectRatio"]:checked').value;
            const brandInputValue = document.getElementById('brandInput').value;
            
            generateVideo(promptContent.textContent, brandInputValue, aspectRatio);
        }
    });
}); 