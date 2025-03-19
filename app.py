from flask import Flask, render_template, request, jsonify, redirect, url_for
import os
import requests
import json
import time
from openai import OpenAI
import openai
from dotenv import load_dotenv
import uuid
import logging
import socket
import urllib3
import traceback
import sys
from bs4 import BeautifulSoup
from pydantic import BaseModel
from typing import List
import random
import base64
from PIL import Image
import io

# Configure logging first
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Log Python version and environment
logger.info(f"Python version: {sys.version}")
logger.info(f"Environment: {os.environ.get('VERCEL_ENV', 'local')}")

# Import fal.ai
try:
    import fal_client
    FAL_CLIENT_AVAILABLE = True
    logger.info("fal.ai client kütüphanesi başarıyla yüklendi.")
except ImportError as e:
    FAL_CLIENT_AVAILABLE = False
    logger.error(f"fal.ai client kütüphanesi yüklenemedi: {str(e)}")

# DNS çözümleme zaman aşımını artır
socket.setdefaulttimeout(30)  # 30 saniye

# Bağlantı havuzu yönetimi
try:
    urllib3.PoolManager(retries=urllib3.Retry(total=5, backoff_factor=0.5))
    logger.info("urllib3 PoolManager başarıyla yapılandırıldı.")
except Exception as e:
    logger.warning(f"urllib3 PoolManager yapılandırılırken hata: {str(e)}")

# Load environment variables
try:
    load_dotenv()
    logger.info("Çevre değişkenleri yüklendi.")
except Exception as e:
    logger.warning(f"Çevre değişkenleri yüklenirken hata: {str(e)}")

# Initialize Flask app
app = Flask(__name__)

# API anahtarları
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
FAL_API_KEY = os.getenv("FAL_API_KEY")
ASSISTANT_ID = os.getenv("ASSISTANT_ID")

# Log API key availability (not the actual keys)
logger.info(f"OPENAI_API_KEY mevcut: {bool(OPENAI_API_KEY)}")
logger.info(f"FAL_API_KEY mevcut: {bool(FAL_API_KEY)}")

# Fal.ai API yapılandırması - FAL_KEY çevre değişkenini ayarla
if FAL_API_KEY:
    os.environ["FAL_KEY"] = FAL_API_KEY
    logger.info(f"FAL_KEY çevre değişkeni ayarlandı: {FAL_API_KEY[:4]}..." if FAL_API_KEY else "FAL_KEY ayarlanamadı")
else:
    logger.warning("FAL_API_KEY bulunamadı, FAL_KEY çevre değişkeni ayarlanamadı.")

# OpenAI istemcisini yapılandır
client = None
try:
    if OPENAI_API_KEY:
        # OpenAI API anahtarını doğrudan ayarla
        openai.api_key = OPENAI_API_KEY
        
        # OpenAI istemcisini oluştur
        client = OpenAI(
            api_key=OPENAI_API_KEY,
        )
        
        # API bağlantısını test et
        logger.info("OpenAI API bağlantısı test ediliyor...")
        models = client.models.list()
        logger.info(f"OpenAI API bağlantısı başarılı. Kullanılabilir model sayısı: {len(models.data)}")
    else:
        logger.warning("OPENAI_API_KEY bulunamadı, OpenAI istemcisi oluşturulamadı.")
except Exception as e:
    logger.error(f"OpenAI API bağlantısı kurulamadı: {str(e)}")
    logger.error(f"Hata izleme: {traceback.format_exc()}")

# Ensure templates directory exists
template_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')
if not os.path.exists(template_dir):
    logger.warning(f"Templates directory not found at {template_dir}. Creating it.")
    try:
        os.makedirs(template_dir, exist_ok=True)
    except Exception as e:
        logger.error(f"Failed to create templates directory: {str(e)}")

# Create basic templates if they don't exist
for template_name in ['welcome.html', 'index.html', 'image.html', 'video.html']:
    template_path = os.path.join(template_dir, template_name)
    if not os.path.exists(template_path):
        logger.warning(f"Template {template_name} not found. Creating a basic version.")
        try:
            with open(template_path, 'w') as f:
                f.write(f"<!DOCTYPE html><html><head><title>{template_name}</title></head><body><h1>{template_name}</h1><p>This is a placeholder template.</p></body></html>")
        except Exception as e:
            logger.error(f"Failed to create template {template_name}: {str(e)}")

def generate_prompt(text: str, feature_type: str) -> dict:
    """
    OpenAI chat completion API kullanarak doğrudan prompt oluşturur.
    IC-Relight v2 modeli için özel olarak tasarlanmış mise-en-scène veya sahne promptları üretir.
    """
    if feature_type not in ["image", "video"]:
        raise ValueError("Geçersiz feature_type! 'image' veya 'video' olmalıdır.")
    
    logger.info(f"Prompt oluşturuluyor. Metin: {text[:50]}... Özellik tipi: {feature_type}")
    
    try:
        # Eğer görsel URL'si ise, görseli analiz et
        if feature_type == "image":
            try:
                # Görseli indir
                response = requests.get(text, timeout=10)
                if response.status_code != 200:
                    raise ValueError(f"Görsel indirilemedi: HTTP {response.status_code}")
                
                # Pillow ile görseli işle
                image = Image.open(io.BytesIO(response.content))
                
                # Görsel boyutlarını kontrol et ve gerekirse yeniden boyutlandır
                max_size = (1024, 1024)
                if image.size[0] > max_size[0] or image.size[1] > max_size[1]:
                    image.thumbnail(max_size, Image.Resampling.LANCZOS)
                
                # Görsel kalitesini optimize et
                output_buffer = io.BytesIO()
                image.save(output_buffer, format='JPEG', quality=85, optimize=True)
                image_base64 = base64.b64encode(output_buffer.getvalue()).decode('utf-8')
                
                # GPT-4 ile görseli analiz et
                analysis_response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": """Analyze this image in detail, focusing on:
                                    1. Physical characteristics (size, shape, materials)
                                    2. Visual style and design elements
                                    3. Color palette and lighting
                                    4. Composition and layout
                                    5. Notable features or unique aspects
                                    6. Product category and intended use
                                    7. Brand identity elements if visible"""
                                },
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/jpeg;base64,{image_base64}"
                                    }
                                }
                            ]
                        }
                    ]
                )
                
                image_analysis = analysis_response.choices[0].message.content
                logger.info(f"Görsel analizi: {image_analysis[:200]}...")
                
            except Exception as e:
                logger.error(f"Görsel analizi sırasında hata: {str(e)}")
                logger.error(f"Hata izleme: {traceback.format_exc()}")
                image_analysis = "Görsel analizi yapılamadı."
        else:
            image_analysis = ""

        # Sistem talimatı
        system_instruction = """
        Your task is to generate four distinct mise-en-scène or scene prompts specifically tailored for an IC-Relight v2 model based on the provided image analysis.

        Given Image Analysis:
        {image_analysis}

        Responsibilities:
        1. Create prompts grounded in the observed physical context from the image analysis
        2. Ensure each prompt aligns with the product's actual style and identity from the image
        3. Keep prompts short, focused, and scene-oriented
        4. Maintain variation while staying true to the product's actual appearance

        Rules for Each Prompt:
        1. Must be 45-100 words
        2. Must present a unique approach and setting while respecting the product's actual appearance
        3. Must be directly usable for image generation
        4. Must be in English
        5. Must use metaphorical expressions referencing the product's actual features
        6. Must maintain visual consistency with the analyzed product
        7. Must include specific lighting conditions and atmosphere
        8. Must incorporate relevant style elements from the analysis
        9. Must consider the product's context and intended use
        10. Must respect brand identity if visible in the analysis

        Output Format:
        SCENE1: [First scene description]
        [Prompt 1]

        SCENE2: [Second scene description]
        [Prompt 2]

        SCENE3: [Third scene description]
        [Prompt 3]

        SCENE4: [Fourth scene description]
        [Prompt 4]
        """
        
        # Chat completion isteği gönder
        logger.info("Chat completion isteği gönderiliyor...")
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_instruction.format(image_analysis=image_analysis)},
                {"role": "user", "content": f"Tür: {feature_type}"}
            ],
            temperature=0.7,
            max_tokens=1000
        )
        
        # Yanıtı işle
        response_text = response.choices[0].message.content.strip()
        logger.info(f"GPT yanıtı alındı: {response_text[:100]}...")
        
        # Stil ve promptları ayır
        sections = response_text.split('\n\n')
        
        prompt_data = []
        
        for section in sections:
            lines = section.strip().split('\n')
            if not lines:
                continue
                
            # İlk satırdan sahne açıklamasını çıkar
            scene_line = lines[0]
            if "SCENE" in scene_line.upper() and ":" in scene_line:
                scene = scene_line.split(":", 1)[1].strip()
                # Sahne satırını çıkar ve kalan satırları prompt olarak birleştir
                prompt = " ".join(lines[1:]).strip()
                if prompt and len(prompt) > 10:
                    prompt_data.append({"scene": scene, "prompt": prompt})
        
        # Eğer hiç prompt bulunamadıysa, metni doğrudan kullan
        if not prompt_data:
            logger.warning("Hiç prompt bulunamadı, metni doğrudan kullanıyoruz")
            prompt_data.append({
                "scene": "default",
                "prompt": text
            })
        
        # Eğer 4'ten az prompt varsa, eksik olanları doldur
        while len(prompt_data) < 4 and len(prompt_data) > 0:
            prompt_data.append(prompt_data[0])  # İlk promptu tekrarla
        
        # Sadece ilk 4 promptu al
        prompt_data = prompt_data[:4]
        
        logger.info(f"Oluşturulan prompt sayısı: {len(prompt_data)}")
        
        # Sonucu döndür
        return {
            "input_text": text,
            "feature_type": feature_type,
            "prompt_data": prompt_data
        }
        
    except Exception as e:
        logger.error(f"Prompt oluşturulurken hata: {str(e)}")
        logger.error(f"Hata izleme: {traceback.format_exc()}")
        raise ValueError(f"Prompt oluşturulurken hata: {str(e)}")

@app.route('/')
def welcome():
    """Karşılama sayfasını göster"""
    logger.info("Karşılama sayfası görüntüleniyor")
    return render_template('welcome.html')

@app.route('/index')
def index():
    """Ana uygulama sayfasını göster"""
    logger.info("Ana uygulama sayfası görüntüleniyor")
    return render_template('index.html')

@app.route('/image')
def image():
    """Görsel üretici sayfasını göster"""
    image_urls = request.args.getlist('image_url')  # Birden fazla görsel URL'si alabilmek için getlist kullan
    prompt = request.args.get('prompt')
    brand = request.args.get('brand')
    
    if not image_urls:
        logger.info("Görsel üretici sayfası görüntüleniyor")
        return render_template('image.html')
    
    logger.info(f"Görsel sonuç sayfası görüntüleniyor. Görsel URL sayısı: {len(image_urls)}")
    return render_template('image.html', image_urls=image_urls, prompt=prompt, brand=brand)

@app.route("/generate-prompt", methods=["POST"])
def generate_prompt_api():
    """API endpoint for generating prompts."""
    data = request.json
    text = data.get("text")
    feature_type = data.get("feature_type")
    
    if not text or not feature_type:
        logger.error("Missing required parameters in generate_prompt_api")
        return jsonify({"error": "Missing required parameters: 'text' and 'feature_type'"}), 400
    
    logger.info(f"Generating prompt for text: {text[:100]}... Feature type: {feature_type}")
    
    try:
        result = generate_prompt(text, feature_type)
        logger.info(f"Successfully generated prompts: {json.dumps(result)[:200]}...")
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error in generate_prompt_api: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500

@app.route('/generate_video', methods=['POST'])
def generate_video():
    prompt = request.form.get('prompt')
    brand_input = request.form.get('brand_input')
    aspect_ratio = request.form.get('aspect_ratio', '9:16')  # Varsayılan olarak 9:16
    
    if not prompt:
        return jsonify({"error": "Geçersiz prompt seçimi"}), 400
    
    # Fal.ai client'ın kullanılabilir olup olmadığını kontrol et
    if not FAL_CLIENT_AVAILABLE:
        logger.error("fal_client kütüphanesi yüklü değil. Video oluşturulamıyor.")
        return jsonify({"error": "Video oluşturma özelliği şu anda kullanılamıyor. Sunucu yapılandırması eksik."}), 500
    
    try:
        logger.info(f"Fal.ai API'sine video oluşturma isteği gönderiliyor")
        logger.info(f"Kullanılan prompt: {prompt[:50]}...")  # İlk 50 karakteri logla
        logger.info(f"Kullanılan aspect ratio: {aspect_ratio}")
        
        # Fal.ai Veo2 API'si ile video oluştur
        try:
            logger.info("Fal.ai istemcisi ile video oluşturuluyor...")
            
            # Benzersiz bir istek ID'si oluştur (sadece loglama için)
            request_id = str(uuid.uuid4())
            logger.info(f"Oluşturulan istek ID: {request_id}")
            
            # İlerleme güncellemelerini işlemek için callback fonksiyonu
            def on_queue_update(update):
                if hasattr(update, 'logs') and update.logs:
                    for log in update.logs:
                        logger.info(f"🔄 {log.get('message', '')}")
                
                if hasattr(update, 'status'):
                    logger.info(f"Fal.ai durum: {update.status}")
            
            # API isteği için parametreler
            arguments = {
                "prompt": prompt,
                "aspect_ratio": aspect_ratio,  # Kullanıcının seçtiği aspect ratio
                "duration": "8s"  # Maksimum süre (8 saniye)
            }
            
            # Parametreleri logla
            logger.info(f"Fal.ai parametreleri: {json.dumps(arguments)}")
            
            # İstek zamanını ölç
            request_start_time = time.time()
            logger.info("Fal.ai isteği başlıyor...")
            
            # Fal.ai Veo2 modelini çağır
            result = fal_client.subscribe(
                "fal-ai/veo2",
                arguments=arguments,
                with_logs=True,
                on_queue_update=on_queue_update
            )
            
            request_duration = time.time() - request_start_time
            logger.info(f"Fal.ai isteği tamamlandı. Süre: {request_duration:.2f} saniye")
            
            # Sonucu logla
            logger.info(f"Fal.ai sonucu: {json.dumps(result)[:200]}...")  # İlk 200 karakteri logla
            
            # Video URL'sini al
            logger.info("Video URL'si alınıyor...")
            video_url = result.get("video", {}).get("url")
            
            if not video_url:
                logger.error(f"Video URL'si bulunamadı. Sonuç: {result}")
                return jsonify({"error": "Video URL'si alınamadı"}), 500
            
            logger.info(f"Video başarıyla oluşturuldu. URL: {video_url}")
            
            # Video URL'sini test et
            logger.info("Video URL'si test ediliyor...")
            try:
                video_test = requests.head(video_url, timeout=10)
                logger.info(f"Video URL'si test sonucu: {video_test.status_code}")
                if video_test.status_code != 200:
                    logger.warning(f"Video URL'si erişilebilir değil: {video_test.status_code}")
            except Exception as video_test_error:
                logger.warning(f"Video URL'si test edilirken hata oluştu: {str(video_test_error)}")
            
            # Video sayfasına yönlendir
            logger.info("İstemciye yanıt gönderiliyor...")
            return jsonify({
                "video_url": video_url,
                "prompt": prompt,
                "brand_input": brand_input
            })
            
        except Exception as fal_error:
            logger.error(f"Fal.ai istemcisi hatası: {str(fal_error)}")
            logger.error(f"Hata türü: {type(fal_error).__name__}")
            logger.error(f"Hata detayları: {str(fal_error)}")
            logger.error(f"Hata izleme: {traceback.format_exc()}")
            
            # Alternatif olarak REST API'yi dene
            logger.info("Fal.ai istemcisi başarısız oldu, REST API deneniyor...")
            try:
                # API isteği için başlıklar
                headers = {
                    "Authorization": f"Key {FAL_API_KEY}",
                    "Content-Type": "application/json"
                }
                
                # API isteği için veri
                payload = {
                    "input": {
                        "prompt": prompt,
                        "aspect_ratio": aspect_ratio,  # Kullanıcının seçtiği aspect ratio
                        "duration": "10s"  # Maksimum süre (8 saniye)
                    }
                }
                
                # API isteği gönder
                logger.info("REST API isteği gönderiliyor...")
                response = requests.post(
                    "https://api.fal.ai/v1/video/veo2",
                    headers=headers,
                    json=payload,
                    timeout=120
                )
                
                # Yanıtı kontrol et
                if response.status_code != 200:
                    logger.error(f"REST API hatası: {response.text}")
                    return jsonify({"error": f"Video oluşturma başarısız oldu: {response.text}"}), 500
                
                # Yanıtı JSON olarak ayrıştır
                result = response.json()
                
                # Video URL'sini al
                video_url = result.get("video", {}).get("url")
                
                if not video_url:
                    logger.error(f"Video URL'si bulunamadı. Sonuç: {result}")
                    return jsonify({"error": "Video URL'si alınamadı"}), 500
                
                logger.info(f"REST API ile video başarıyla oluşturuldu. URL: {video_url}")
                
                # Video sayfasına yönlendir
                return jsonify({
                    "video_url": video_url,
                    "prompt": prompt,
                    "brand_input": brand_input
                })
                
            except Exception as rest_error:
                logger.error(f"REST API hatası: {str(rest_error)}")
                logger.error(f"Hata izleme: {traceback.format_exc()}")
                return jsonify({"error": f"Video oluşturma başarısız oldu: {str(rest_error)}"}), 500
            
            return jsonify({"error": f"Video oluşturma başarısız oldu: {str(fal_error)}"}), 500
    
    except Exception as e:
        error_msg = f"Hata: {str(e)}"
        logger.error(error_msg)
        logger.error(f"Hata izleme: {traceback.format_exc()}")
        
        return jsonify({"error": f"Bir hata oluştu: {str(e)}"}), 500

@app.route('/video')
def video():
    video_url = request.args.get('video_url')
    prompt = request.args.get('prompt')
    brand = request.args.get('brand')
    
    if not video_url:
        return redirect(url_for('index'))
    
    logger.info(f"Video sayfası görüntüleniyor. Video URL: {video_url}")
    return render_template('video.html', video_url=video_url, prompt=prompt, brand=brand)

@app.route('/check_status/<request_id>')
def check_status(request_id):
    """Check the status of an image generation request."""
    try:
        if not FAL_CLIENT_AVAILABLE:
            raise Exception("fal.ai client kütüphanesi yüklü değil")

        logger.info(f"Checking request status (ID: {request_id})...")
        
        # Initialize fal.ai client
        fal_client.api_key = os.getenv('FAL_KEY')
        
        # Get status from fal.ai
        status = fal_client.get_queue_status(request_id)
        
        # Convert status object to dictionary
        status_dict = {
            "status": "completed" if status.get('completed', False) else "in_progress",
            "logs": status.get('logs', [])
        }
        
        return jsonify(status_dict)
            
    except Exception as e:
        logger.error(f"Error checking request status: {str(e)}")
        return jsonify({
            "status": "error",
            "error": str(e),
            "logs": []
        }), 500

@app.route('/debug')
def debug():
    """Debug endpoint to check environment variables and configuration"""
    debug_info = {
        "python_version": sys.version,
        "environment": os.environ.get('VERCEL_ENV', 'local'),
        "openai_api_key_exists": bool(OPENAI_API_KEY),
        "fal_api_key_exists": bool(FAL_API_KEY),
        "template_dir_exists": os.path.exists(template_dir),
        "templates": [f for f in os.listdir(template_dir) if os.path.isfile(os.path.join(template_dir, f))] if os.path.exists(template_dir) else []
    }
    return jsonify(debug_info)

# Initialize scrape.do configuration
SCRAPE_DO_API_KEY = os.getenv("SCRAPE_DO_API_KEY")
SCRAPE_DO_BASE_URL = "http://api.scrape.do"

@app.route('/extract-images', methods=['POST'])
def extract_images():
    try:
        # Get the URL from the request
        data = request.get_json()
        url = data.get('url')
        
        if not url:
            return jsonify({"error": "URL is required"}), 400

        if not SCRAPE_DO_API_KEY:
            return jsonify({"error": "Scrape.do API key not configured"}), 500

        try:
            # Configuration for image extraction
            config = {
                "carousel_images": {
                    "selectors": [
                        "#pdp-carousel__slide0 img",
                        "#pdp-carousel__slide1 img",
                        "#pdp-carousel__slide2 img",
                        "#pdp-carousel__slide3 img",
                        "#pdp-carousel__slide4 img"
                    ],
                    "attribute": "src",
                    "filters": {
                        "include": "424-600/",
                        "endsWith": ".jpg",
                        "orInclude": "/format:webp"
                    }
                }
            }

            # Make the request to scrape.do
            scrape_url = f"{SCRAPE_DO_BASE_URL}?token={SCRAPE_DO_API_KEY}&url={url}"
            response = requests.get(scrape_url, timeout=30)
            
            if response.status_code != 200:
                return jsonify({"error": f"Failed to fetch URL: {response.status_code}"}), response.status_code
                
            # Parse the HTML content
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Extract images based on configuration
            extracted_images = []
            
            for selector in config["carousel_images"]["selectors"]:
                images = soup.select(selector)
                for img in images:
                    src = img.get(config["carousel_images"]["attribute"])
                    if src:
                        # Handle relative URLs
                        if src.startswith('//'):
                            src = 'https:' + src
                        elif src.startswith('/'):
                            # Get the base URL
                            from urllib.parse import urlparse
                            parsed_uri = urlparse(url)
                            base_url = f'{parsed_uri.scheme}://{parsed_uri.netloc}'
                            src = base_url + src
                        
                        # Apply filters
                        filters = config["carousel_images"]["filters"]
                        if (
                            src.startswith('http') and
                            not src.startswith('data:') and
                            filters["include"] in src and
                            (src.endswith(filters["endsWith"]) or filters["orInclude"] in src)
                        ):
                            extracted_images.append(src)
            
            # Log the results
            logger.info(f"Found {len(extracted_images)} carousel images")
            for idx, img_url in enumerate(extracted_images, 1):
                logger.info(f"Image {idx}: {img_url}")
            
            # Return only the extracted images without generating prompts
            return jsonify({
                "product_images": extracted_images
            })
            
        except Exception as e:
            logger.error(f"Error scraping URL: {str(e)}")
            return jsonify({"error": f"Failed to scrape URL: {str(e)}"}), 500
            
    except Exception as e:
        logger.error(f"Error in extract_images: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/generate_image', methods=['POST'])
def generate_image():
    try:
        data = request.get_json()
        prompt_data = data.get('prompt_data')  # This should be a list of prompts
        image_url = data.get('image_url')

        if not prompt_data or not isinstance(prompt_data, list):
            return jsonify({"error": "Prompt verisi gerekli ve liste formatında olmalı"}), 400

        if not FAL_CLIENT_AVAILABLE:
            return jsonify({"error": "fal.ai client kütüphanesi yüklü değil"}), 500

        logger.info(f"🎨 Çoklu görsel üretme isteği başlatılıyor...")
        logger.info(f"📝 Prompt sayısı: {len(prompt_data)}")
        logger.info(f"🔗 Referans görsel: {image_url}")

        # Fal.ai API anahtarını ayarla
        fal_client.api_key = os.getenv('FAL_KEY')

        generated_images = []

        def on_queue_update(update):
            if hasattr(update, 'logs') and update.logs:
                for log in update.logs:
                    logger.info(f"🔄 {log.get('message', '')}")

        # Her prompt için görsel üret
        for idx, prompt_item in enumerate(prompt_data, 1):
            prompt = prompt_item.get('prompt')
            scene = prompt_item.get('scene')
            
            logger.info(f"🎯 {idx}. görsel üretiliyor...")
            logger.info(f"📝 Sahne: {scene}")
            logger.info(f"📝 Prompt: {prompt}")

            try:
                # Fal.ai'ye istek gönder
                result = fal_client.subscribe(
                    "fal-ai/iclight-v2",
                    arguments={
                        "prompt": prompt,
                        "image_url": image_url,
                        "negative_prompt": "ugly, disfigured, low quality, blurry, nsfw",
                        "num_inference_steps": 30,
                        "guidance_scale": 7.5,
                        "seed": random.randint(1, 1000000)
                    },
                    with_logs=True,
                    on_queue_update=on_queue_update
                )

                if not result or not isinstance(result, dict):
                    logger.error(f"❌ {idx}. görsel üretilemedi: Geçersiz yanıt formatı")
                    continue

                generated_image_url = result.get("images", [{}])[0].get("url")
                
                if not generated_image_url:
                    logger.error(f"❌ {idx}. görsel için URL bulunamadı")
                    continue

                generated_images.append({
                    "scene": scene,
                    "prompt": prompt,
                    "image_url": generated_image_url,
                    "request_id": result.get('request_id')
                })

                logger.info(f"✨ {idx}. görsel başarıyla üretildi")
                logger.info(f"🖼️ Üretilen görsel URL: {generated_image_url}")

            except Exception as e:
                logger.error(f"❌ {idx}. görsel üretilirken hata: {str(e)}")
                continue

        if not generated_images:
            return jsonify({"error": "Hiçbir görsel üretilemedi"}), 500

        return jsonify({
            "status": "success",
            "generated_images": generated_images
        })

    except Exception as e:
        logger.error(f"❌ Görsel üretme hatası: {str(e)}")
        logger.error(f"Hata izleme: {traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500

# Add error handlers
@app.errorhandler(404)
def page_not_found(e):
    logger.error(f"404 error: {str(e)}")
    return render_template('error.html', error="Page not found"), 404

@app.errorhandler(500)
def internal_server_error(e):
    logger.error(f"500 error: {str(e)}")
    return render_template('error.html', error="Internal server error"), 500

if __name__ == '__main__':
    logger.info("Uygulama başlatılıyor...")
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)