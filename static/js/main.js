// Global variables
let currentImageContainer = null;

// Global functions
function submitImageSelection() {
    if (!currentImageContainer) {
        console.warn('⚠️ Görsel seçilmedi!');
        alert('Lütfen bir görsel seçin');
        return;
    }

    const selectedImageUrl = currentImageContainer.getAttribute('data-url');
    console.log('🖼️ Seçilen görsel:', selectedImageUrl);

    // Generate prompts for the selected image
    fetch('/generate-prompt', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            text: selectedImageUrl,
            feature_type: 'image'
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.error) {
            console.error('❌ Prompt oluşturma hatası:', data.error);
            throw new Error(data.error);
        }

        // Log prompts to console
        if (data.prompt_data && data.prompt_data.length > 0) {
            console.log('\n📝 Seçilen Görsel için Oluşturulan Promptlar:');
            data.prompt_data.forEach((item, index) => {
                console.log(`\nPrompt ${index + 1}:`);
                console.log('Sahne:', item.scene);
                console.log('Prompt:', item.prompt);
                console.log('------------------------');
            });
        }

        // Close the modal
        closeModal();

        // Add selected class to the image container
        document.querySelectorAll('.selected').forEach(el => el.classList.remove('selected'));
        currentImageContainer.classList.add('selected');
    })
    .catch(error => {
        console.error('❌ Prompt oluşturma hatası:', error);
        alert('Prompt oluşturulurken bir hata oluştu: ' + error.message);
    });
}

function showModal(imageUrl) {
    const modal = document.getElementById('imageModal');
    const modalImage = document.getElementById('modalImage');
    
    modalImage.src = imageUrl;
    modal.classList.remove('hidden');
}

function closeModal() {
    const modal = document.getElementById('imageModal');
    modal.classList.add('hidden');
}

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
        })
        .catch(error => {
            loadingPrompts.classList.add('hidden');
            console.error('API hatası:', error);
            alert('Bir hata oluştu: ' + error.message);
        });
    });
    
    function generateVideo(prompt, brandInput) {
        // Seçilen prompt ile video oluştur
        promptResults.classList.add('hidden'); // Prompt sonuçlarını gizle
        videoLoading.classList.remove('hidden');
        
        const formData = new FormData();
        formData.append('prompt', prompt);
        formData.append('brand_input', brandInput);
        
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
    
    // Sayfada "Oluştur" butonuna tıklandığında seçili prompt ile video oluştur
    document.addEventListener('click', function(e) {
        if (e.target.classList.contains('create-video-btn')) {
            if (!selectedPromptCard) {
                alert('Lütfen önce bir prompt seçin');
                return;
            }
            
            // Seçilen prompt ile video oluştur
            const promptContent = selectedPromptCard.querySelector('.prompt-content p');
            const brandInputValue = document.getElementById('brandInput').value;
            
            generateVideo(promptContent.textContent, brandInputValue);
        }
    });

    // Form submit event listener'ı
    const imageForm = document.getElementById('imageForm');
    if (imageForm) {
        imageForm.addEventListener('submit', async function(e) {
            e.preventDefault();
            
            const brandInput = document.getElementById('brandInput').value;
            console.log('🔍 URL girişi:', brandInput);
            
            if (!brandInput) {
                console.warn('⚠️ URL girilmedi!');
                alert('Lütfen geçerli bir URL girin');
                return;
            }
            
            try {
                console.log('🌐 Görsel çekme işlemi başlatılıyor...');
                imageForm.classList.add('opacity-50', 'pointer-events-none');
                
                const images = await fetchImages(brandInput);
                
                if (images && images.length > 0) {
                    console.log(`✅ Başarıyla ${images.length} görsel çekildi:`);
                    images.forEach((imageUrl, index) => {
                        console.log(`${index + 1}. Görsel: ${imageUrl}`);
                    });

                    // Display images in the grid
                    extractedImagesGrid.innerHTML = '';
                    extractedImagesContainer.classList.remove('hidden');
                    
                    images.forEach((imageUrl, index) => {
                        const imageContainer = document.createElement('div');
                        imageContainer.className = 'relative border-2 border-transparent rounded-lg cursor-pointer hover:border-purple-500 transition-all';
                        imageContainer.setAttribute('data-url', imageUrl);
                        
                        const img = document.createElement('img');
                        img.src = imageUrl;
                        img.alt = `Extracted image ${index + 1}`;
                        img.className = 'w-full h-48 object-cover rounded-lg';
                        
                        const loadingOverlay = document.createElement('div');
                        loadingOverlay.className = 'absolute inset-0 bg-gray-900 bg-opacity-75 flex items-center justify-center';
                        loadingOverlay.innerHTML = '<div class="animate-spin rounded-full h-8 w-8 border-t-2 border-b-2 border-purple-500"></div>';
                        imageContainer.appendChild(loadingOverlay);
                        
                        img.onload = function() {
                            loadingOverlay.remove();
                        };
                        
                        img.onerror = function() {
                            loadingOverlay.innerHTML = '<p class="text-red-400 text-sm">Görsel yüklenemedi</p>';
                        };
                        
                        imageContainer.appendChild(img);
                        
                        imageContainer.addEventListener('click', function(e) {
                            if (e.target.tagName === 'IMG') {
                                const imageUrl = this.getAttribute('data-url');
                                currentImageContainer = this;
                                showModal(imageUrl);
                                e.stopPropagation();
                            }
                        });
                        
                        extractedImagesGrid.appendChild(imageContainer);
                    });
                } else {
                    console.warn('⚠️ Hiç görsel bulunamadı');
                    throw new Error('Görsel bulunamadı');
                }

            } catch (error) {
                console.error('❌ İşlem hatası:', {
                    message: error.message,
                    timestamp: new Date().toISOString()
                });
                alert('Hata: ' + error.message);
            } finally {
                imageForm.classList.remove('opacity-50', 'pointer-events-none');
            }
        });
    }
});

async function fetchImages(url) {
    try {
        const imageExtractor = new ImageExtractor();
        const images = await imageExtractor.extractImagesFromUrl(url);
        
        if (!images || images.length === 0) {
            throw new Error('No images found');
        }
        
        return images; // This now returns product_images directly
    } catch (error) {
        console.error('Error fetching images:', error);
        throw error;
    }
} 