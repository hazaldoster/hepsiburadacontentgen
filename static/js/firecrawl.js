// FireCrawl Integration
class ImageExtractor {
    constructor() {
        this.apiKey = "fc-3fe146eea8724b448ba5c838d2d94ac6";
    }

    async extractImagesFromUrl(url) {
        try {
            const response = await fetch('/extract-images', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    url: url
                })
            });

            if (!response.ok) {
                throw new Error('Failed to extract images');
            }

            const data = await response.json();
            return data.images;
        } catch (error) {
            console.error('Error extracting images:', error);
            throw error;
        }
    }
}

// Export the class
window.ImageExtractor = ImageExtractor; 