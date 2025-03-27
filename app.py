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
import re
from datetime import datetime
from supabase import create_client

# Data structure to store generated content
generated_content = []

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
ASTRIA_API_KEY = os.getenv("ASTRIA_API_KEY")
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
for template_name in ['welcome.html', 'index.html', 'image.html', 'video.html', 'image2.html']:
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

# Initialize Supabase client
SUPABASE_URL = os.getenv('SUPABASE_URL', 'https://vsczjwvmkqustdbxyvzo.supabase.co')
SUPABASE_KEY = os.getenv('SUPABASE_KEY', 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InZzY3pqd3Zta3F1c3RkYnh5dnpvIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDE4NzU5NjQsImV4cCI6MjA1NzQ1MTk2NH0.7tlRgk0sPXHZnmbnvPyOkEHT-ptJMK8BGvINY-5YPds')

try:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    logger.info("Supabase client initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize Supabase client: {str(e)}")
    supabase = None

def fetch_generations_from_db(limit=100, offset=0):
    """Fetch generations from Supabase database."""
    try:
        if not supabase:
            logger.error("Supabase client not initialized")
            return []
            
        response = supabase.table('generations') \
            .select("*") \
            .order('created_at', desc=True) \
            .limit(limit) \
            .offset(offset) \
            .execute()
            
        # Process the data to ensure all required fields are present
        processed_data = []
        for item in response.data:
            processed_item = {
                'id': item.get('id'),
                'url': item.get('url'),
                'type': item.get('type', ''),  # Media type (image/video)
                'content_type': item.get('content_type', ''),  # Section type (creative-scene/product-visual/video-image)
                'prompt': item.get('prompt', 'No prompt provided'),
                'created_at': item.get('created_at')
            }
            
            # Format the date if present
            if processed_item['created_at']:
                if isinstance(processed_item['created_at'], str):
                    created_at = datetime.fromisoformat(processed_item['created_at'].replace('Z', '+00:00'))
                else:
                    created_at = processed_item['created_at']
                processed_item['date'] = created_at.strftime("%Y-%m-%d %H:%M:%S")
            
            processed_data.append(processed_item)
            
        return processed_data
    except Exception as e:
        logger.error(f"Error fetching generations from database: {str(e)}")
        logger.error(f"Full traceback: {traceback.format_exc()}")
        return []

def store_generated_content(url, content_type, type, prompt=None):
    """Store generated content in the database."""
    try:
        if not url or not content_type or not type:
            raise ValueError("URL, content_type, and type are required")

        # Validate content type
        valid_content_types = ['product-visual', 'creative-scene', 'video-image']
        if content_type not in valid_content_types:
            raise ValueError(f"Invalid content_type. Must be one of: {', '.join(valid_content_types)}")

        # Validate media type
        valid_types = ['image', 'video']
        if type not in valid_types:
            raise ValueError(f"Invalid type. Must be one of: {', '.join(valid_types)}")

        # Log incoming data
        app.logger.info(f"Storing content: url={url}, content_type={content_type}, type={type}, prompt={prompt}")

        # Prepare data for insertion
        data = {
            'url': url,
            'content_type': content_type,
            'type': type,
            'prompt': prompt,
            'created_at': datetime.now().isoformat()
        }

        # Insert into database
        response = supabase.table('generations').insert(data).execute()
        
        if hasattr(response, 'error') and response.error is not None:
            raise Exception(f"Database error: {response.error}")

        return response.data[0] if response.data else None

    except Exception as e:
        app.logger.error(f"Error storing content: {str(e)}")
        app.logger.error(traceback.format_exc())
        raise

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
    duration = request.form.get('duration', '8s')  # Yeni: frontend'den süre değerini al
    content_type = request.form.get('content_type', 'creative-scene')  # Default to creative-scene for index.html/video.html
    
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
        logger.info(f"Kullanılan süre: {duration}")
        logger.info(f"Content type: {content_type}")
        
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
                "duration": duration  # Kullanıcının seçtiği süre
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
            
            # Store the generated video in our library
            store_generated_content(
                url=video_url,
                content_type=content_type,  # Use the content_type from request
                type="video",
                prompt=prompt
            )
            
            # Video sayfasına yönlendir
            logger.info("İstemciye yanıt gönderiliyor...")
            return jsonify({
                "video_url": video_url,
                "prompt": prompt
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
                
                # Store the generated video in our library
                store_generated_content(
                    url=video_url,
                    content_type=content_type,  # Use the content_type from request
                    type="video",
                    prompt=prompt
                )
                
                # Video sayfasına yönlendir
                return jsonify({
                    "video_url": video_url,
                    "prompt": prompt
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
        "astria_api_key_exists": bool(ASTRIA_API_KEY),
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
        prompt_data = data.get('prompt_data')
        image_url = data.get('image_url')
        content_type = data.get('content_type', 'product-visual')  # Default to product-visual if not specified

        if not prompt_data or not isinstance(prompt_data, list):
            return jsonify({"error": "Prompt verisi gerekli ve liste formatında olmalı"}), 400

        if content_type not in ['product-visual', 'video-image']:
            return jsonify({"error": "Invalid content type. Must be 'product-visual' or 'video-image'"}), 400

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

                # Store the generated image in our library
                try:
                    store_generated_content(
                        url=generated_image_url,
                        content_type=content_type,
                        type="image",
                        prompt=prompt
                    )
                    logger.info(f"✅ {idx}. görsel başarıyla veritabanına kaydedildi")
                except Exception as storage_error:
                    logger.error(f"❌ {idx}. görsel veritabanına kaydedilemedi: {str(storage_error)}")
                    # Continue with the process even if storage fails
                    # We'll still show the image to the user
                    pass

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

@app.route('/image2')
def image2():
    """Görsel üretici sayfasını göster"""
    image_urls = request.args.getlist('image_url')  # Birden fazla görsel URL'si alabilmek için getlist kullan
    prompt = request.args.get('prompt')
    brand = request.args.get('brand')
    prompt_id = request.args.get('prompt_id')
    
    # Eğer prompt_id varsa ve görsel URL'leri yoksa, check_image_status fonksiyonunu çağır
    if prompt_id and not image_urls:
        try:
            # API bilgilerini al
            api_key = os.getenv("ASTRIA_API_KEY")
            
            if not api_key:
                logger.error("API yapılandırması eksik")
                return render_template('image2.html')
            
            # Flux model ID - Astria'nın genel Flux modelini kullanıyoruz
            flux_model_id = "1504944"  # Flux1.dev from the gallery
            
            # API URL'sini oluştur - prompt_id ile durumu kontrol et
            api_url = f"https://api.astria.ai/tunes/{flux_model_id}/prompts/{prompt_id}"
            
            headers = {
                "Authorization": f"Bearer {api_key}"
            }
            
            # API'ye istek gönder
            logger.info(f"Astria API durum kontrolü: {api_url}")
            response = requests.get(
                api_url,
                headers=headers
            )
            
            # Yanıtı kontrol et
            if response.status_code == 200:
                # Yanıtı JSON olarak parse et
                result = response.json()
                
                # Görsel URL'lerini farklı formatlarda kontrol et
                if 'images' in result and isinstance(result['images'], list) and len(result['images']) > 0:
                    for image in result['images']:
                        if isinstance(image, dict) and 'url' in image:
                            image_urls.append(image.get('url'))
                        elif isinstance(image, str):
                            image_urls.append(image)
                
                # Diğer olası formatları kontrol et
                if not image_urls and 'image_url' in result:
                    image_urls.append(result.get('image_url'))
                if not image_urls and 'output' in result and isinstance(result['output'], dict) and 'image_url' in result['output']:
                    image_urls.append(result['output']['image_url'])
                
                # Görsel URL'lerini loglama
                if image_urls:
                    logger.info(f"Toplam {len(image_urls)} görsel URL bulundu")
                    logger.info(f"İlk görsel URL: {image_urls[0]}")
        except Exception as e:
            logger.error(f"Görsel durumu kontrol edilirken hata oluştu: {str(e)}")
    
    # Tek bir URL string olarak geldiyse, onu listeye çevir
    if not image_urls and request.args.get('image_url'):
        image_urls = [request.args.get('image_url')]
    
    if not image_urls:
        logger.info("Görsel üretici sayfası görüntüleniyor")
        return render_template('image2.html')
    
    logger.info(f"Görsel sonuç sayfası görüntüleniyor. Görsel URL sayısı: {len(image_urls)}")
    return render_template('image2.html', image_urls=image_urls, prompt=prompt, brand=brand, prompt_id=prompt_id)

@app.route("/generate-prompt-2", methods=["POST"])
def generate_prompt_2_api():
    """API endpoint for generating prompts."""
    data = request.json
    text = data.get("text")
    feature_type = data.get("feature_type")
    aspect_ratio = data.get("aspect_ratio", "1:1")  # Varsayılan olarak 1:1
    
    if not text or not feature_type:
        return jsonify({"error": "Missing required parameters: 'text' and 'feature_type'"}), 400
    
    try:
        result = generate_prompt_2(text, feature_type, aspect_ratio)
        return jsonify(result)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

def detect_style(text: str, feature_type: str) -> str:
    """
    OpenAI'ye ayrı bir istek atarak, girilen metne ve feature_type değerine göre promptun kendi stiline uygun bir stil belirler.
    """
    if feature_type == "image":
        instructions = """Objective:
        Analyze the given text and determine the most appropriate artistic style for an image based on its descriptive elements.
        The detected style should reflect the atmosphere, mood, and composition implied by the text.
        
        Consider factors such as:
        - Lighting (soft, dramatic, neon, natural, etc.)
        - Depth and perspective (wide-angle, close-up, aerial view, etc.)
        - Color palette (vibrant, monochrome, pastel, etc.)
        - Texture and rendering (hyperrealistic, sketch, painterly, etc.)
        
        Output Format:
        Provide a single style descriptor that encapsulates the detected artistic characteristics. Keep it concise and relevant to the provided text."""
    
    elif feature_type == "video":
        instructions = """Objective:
        Analyze the given text and determine the most appropriate cinematic style for a video based on its descriptive elements.
        The detected style should reflect the motion, pacing, and atmosphere implied by the text.
        
        Consider factors such as:
        - Camera movement (steady, shaky cam, sweeping drone shots, etc.)
        - Editing style (fast cuts, slow motion, time-lapse, etc.)
        - Lighting and mood (high contrast, natural, moody, vibrant, etc.)
        - Color grading (warm, cool, desaturated, high-contrast, etc.)
        
        Output Format:
        Provide a single style descriptor that encapsulates the detected cinematic characteristics. Keep it concise and relevant to the provided text."""
    
    else:
        raise ValueError("Geçersiz feature_type! 'image' veya 'video' olmalıdır.")
    
    logger.info(f"Stil belirleme isteği gönderiliyor. Metin: {text[:50]}... Özellik tipi: {feature_type}")
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": instructions},
                {"role": "user", "content": f"Text: {text}\nFeature Type: {feature_type}\nDetermine the best style:"}
            ]
        )
        
        style = response.choices[0].message.content.strip()
        logger.info(f"Belirlenen stil: {style}")
        return style
    except Exception as e:
        logger.error(f"Stil belirlenirken hata: {str(e)}")
        logger.error(f"Hata izleme: {traceback.format_exc()}")
        raise ValueError(f"Stil belirlenirken hata: {str(e)}")

def generate_prompt_2(text: str, feature_type: str, aspect_ratio: str = "1:1") -> dict:
    """
    OpenAI chat completion API kullanarak doğrudan prompt oluşturur.
    Her bir prompt için ayrı stil belirler.
    """
    if feature_type not in ["image", "video"]:
        raise ValueError("Geçersiz feature_type! 'image' veya 'video' olmalıdır.")
    
    logger.info(f"Prompt oluşturuluyor. Metin: {text[:50]}... Özellik tipi: {feature_type}, Aspect Ratio: {aspect_ratio}")
    
    try:
        # Feature type değerini uygun formata dönüştür
        prompt_type = "image" if feature_type == "image" else "video"
        
        # Aspect ratio açıklaması
        aspect_ratio_desc = ""
        if aspect_ratio == "1:1":
            aspect_ratio_desc = "square format (1:1)"
        elif aspect_ratio == "4:5":
            aspect_ratio_desc = "portrait format for Instagram posts (4:5)"
        elif aspect_ratio == "16:9":
            aspect_ratio_desc = "landscape format for web/video (16:9)"
        elif aspect_ratio == "9:16":
            aspect_ratio_desc = "vertical format for stories/reels (9:16)"
        
        # Sistem talimatı - Her prompt için ayrı stil belirle
        system_instruction = f"""
        Görevin, kullanıcının verdiği metin için {prompt_type} oluşturmak üzere 4 farklı prompt üretmektir.  

                Her prompt için farklı bir yaratıcı yaklaşım ve stil belirle ve her promptun başına stilini ekle.  

                ### Kurallar:  
                1. Her prompt en az 50, en fazla 120 kelime olmalıdır. Daha kapsamlı ve detaylı açıklamalar için yeterli uzunluk sağlanmalıdır.  
                2. Her prompt farklı bir görsel ve anlatım yaklaşımı sunmalıdır. Stil, kompozisyon, atmosfer veya teknik bakış açılarıyla çeşitlilik yaratılmalıdır.  
                3. Promptlar doğrudan {prompt_type} oluşturmak için optimize edilmelidir. Her biri, ilgili modelin en iyi sonuçları vermesi için açık, detaylı ve yönlendirici olmalıdır.  
                4. Promptlar mutlaka İngilizce olmalıdır. Teknik ve yaratıcı detayların daha iyi işlenmesi için tüm açıklamalar İngilizce verilmelidir.  
                5. Promptlar {aspect_ratio_desc} için optimize edilmelidir.** Belirtilen en-boy oranına uygun çerçeveleme ve perspektif detayları içermelidir.  
                6. Görseller için ışık, renk paleti, perspektif ve detay seviyesi tanımlanmalıdır. Promptlar, modelin görsel uyumu sağlaması için estetik ve teknik öğeler içermelidir.  
                7. Videolar için hareket, tempo, kamera açısı ve stil detayları belirtilmelidir. Video içeriklerinde sahne akışı, kamera dinamikleri ve atmosfer önemlidir.  
                8. Her prompt, AI modelleri tarafından kolayca anlaşılabilir ve doğru yorumlanabilir olmalıdır. Fazla soyut veya muğlak ifadeler yerine, açık ve yönlendirici dil kullanılmalıdır.  

                ### Yanıt formatı:  

                STYLE1: [Birinci promptun stili]  
                [Prompt 1]  

                STYLE2: [İkinci promptun stili]  
                [Prompt 2]  

                STYLE3: [Üçüncü promptun stili]  
                [Prompt 3]  

                STYLE4: [Dördüncü promptun stili]  
                [Prompt 4]  
        """
        
        # Chat completion isteği gönder
        logger.info("Chat completion isteği gönderiliyor...")
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": f"Metin: {text}\nTür: {feature_type}\nAspect Ratio: {aspect_ratio}"}
            ],
            temperature=0.5,
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
                
            # İlk satırdan stili çıkar
            style_line = lines[0]
            if "STYLE" in style_line.upper() and ":" in style_line:
                style = style_line.split(":", 1)[1].strip()
                # Stil satırını çıkar ve kalan satırları prompt olarak birleştir
                prompt = " ".join(lines[1:]).strip()
                if prompt and len(prompt) > 10:
                    prompt_data.append({"style": style, "prompt": prompt})
        
        # Eğer hiç prompt bulunamadıysa, metni doğrudan kullan
        if not prompt_data:
            logger.warning("Hiç prompt bulunamadı, metni doğrudan kullanıyoruz")
            prompt_data.append({
                "style": "default",
                "prompt": f"{text} {aspect_ratio} aspect ratio"
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
            "aspect_ratio": aspect_ratio,
            "prompt_data": prompt_data
        }
        
    except Exception as e:
        logger.error(f"Prompt oluşturulurken hata: {str(e)}")
        logger.error(f"Hata izleme: {traceback.format_exc()}")
        raise ValueError(f"Prompt oluşturulurken hata: {str(e)}")

@app.route('/check_image_status/<prompt_id>', methods=['GET'])
def check_image_status(prompt_id):
    """Asenkron görsel oluşturma işleminin durumunu kontrol etmek için kullanılan endpoint"""
    try:
        # Yönlendirme seçeneğini kontrol et
        redirect_to_page = request.args.get('redirect', 'false').lower() == 'true'
        prompt = request.args.get('prompt', '')
        brand = request.args.get('brand', '')
        aspect_ratio = request.args.get('aspect_ratio', '1:1')  # Aspect ratio bilgisini al
    #    content_type = request.args.get('content_type', 'video-image')  # Changed default to video-image
        
        # API bilgilerini al
        api_key = os.getenv("ASTRIA_API_KEY")
        
        if not api_key:
            return jsonify({"error": "API yapılandırması eksik"}), 500
        
        # Flux model ID - Astria'nın genel Flux modelini kullanıyoruz
        flux_model_id = "1504944"  # Flux1.dev from the gallery
        
        # API URL'sini oluştur - prompt_id ile durumu kontrol et
        api_url = f"https://api.astria.ai/tunes/{flux_model_id}/prompts/{prompt_id}"
        
        headers = {
            "Authorization": f"Bearer {api_key}"
        }
        
        # API'ye istek gönder
        logger.info(f"Astria API durum kontrolü: {api_url}")
        response = requests.get(
            api_url,
            headers=headers
        )
        
        # Yanıtı kontrol et
        if response.status_code == 200:
            # Yanıtı JSON olarak parse et
            try:
                result = response.json()
                logger.info(f"Astria API durum yanıtı: {json.dumps(result)[:100]}...")
                
                # Görsel URL'sini al
                image_url = None
                image_urls = []
                status = "processing"
                is_ready = False
                
                # Görsel URL'lerini farklı formatlarda kontrol et
                if 'images' in result and isinstance(result['images'], list) and len(result['images']) > 0:
                    for image in result['images']:
                        if isinstance(image, dict) and 'url' in image:
                            image_urls.append(image.get('url'))
                        elif isinstance(image, str):
                            image_urls.append(image)
                
                # Diğer olası formatları kontrol et
                if not image_urls and 'image_url' in result:
                    image_urls.append(result.get('image_url'))
                if not image_urls and 'output' in result and isinstance(result['output'], dict) and 'image_url' in result['output']:
                    image_urls.append(result['output']['image_url'])
                
                # İlk görsel URL'sini ana URL olarak ayarla (geriye dönük uyumluluk için)
                if image_urls:
                    image_url = image_urls[0]
                    # Store each generated image in our library
                    for url in image_urls:
                        store_generated_content(
                            url=url,
                            content_type="video-image",
                            type="image",
                            prompt=prompt
                        )
                
                # Durum bilgisini kontrol et
                if 'status' in result:
                    status = result['status']
                    # Durum "completed" ise görsel hazır demektir
                    if status.lower() in ["completed", "success", "done"]:
                        is_ready = True
                
                # Görsel URL'si varsa hazır kabul et
                if image_urls:
                    is_ready = True
                
                # Görsel URL'lerini loglama
                if image_urls:
                    logger.info(f"Toplam {len(image_urls)} görsel URL bulundu")
                    logger.info(f"İlk görsel URL: {image_urls[0]}")
                else:
                    logger.warning(f"Görsel URL bulunamadı. Yanıt: {json.dumps(result)[:200]}...")
                
                # Her durumda JSON yanıtı döndür
                return jsonify({
                    "is_ready": is_ready,
                    "status": status,
                    "image_url": image_url,  # Geriye dönük uyumluluk için
                    "image_urls": image_urls,  # Tüm görsel URL'leri
                    "prompt_id": prompt_id,
                    "prompt": prompt,
                    "brand": brand,
                    "aspect_ratio": aspect_ratio  # Aspect ratio bilgisini ekle
         #            "content_type": content_type  # Add content_type to response
                })
            except json.JSONDecodeError:
                logger.error(f"Astria API yanıtı JSON formatında değil: {response.text[:100]}...")
                return jsonify({"error": "API yanıtı geçersiz format"}), 500
        else:
            logger.error(f"Astria API durum kontrolü hatası: {response.status_code} - {response.text}")
            return jsonify({"error": f"Durum kontrolü sırasında bir hata oluştu: {response.status_code}"}), response.status_code
    except Exception as e:
        logger.error(f"Durum kontrolü hatası: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/generate_image_2', methods=['POST'])
def generate_image_2():
    prompt = request.form.get('prompt')
    brand_input = request.form.get('brand_input')
    aspect_ratio = request.form.get('aspect_ratio', '1:1')  # Varsayılan olarak 1:1
    redirect_to_page = request.form.get('redirect', 'false').lower() == 'true'  # Yönlendirme seçeneği
    content_type = request.form.get('content_type', 'video-image')  # Changed default to video-image
    
    if not prompt:
        return jsonify({"error": "Geçersiz prompt seçimi"}), 400
    
    try:
        logger.info(f"Astria AI API'sine görsel oluşturma isteği gönderiliyor")
        logger.info(f"Kullanılan prompt: {prompt[:50]}...")  # İlk 50 karakteri logla
        logger.info(f"Kullanılan aspect ratio: {aspect_ratio}")
   #      logger.info(f"Content type: {content_type}")
        
        # API URL'sini kontrol et - Flux API'sini kullanacağız
        api_key = os.getenv("ASTRIA_API_KEY")
        
        # Flux model ID - Astria'nın genel Flux modelini kullanıyoruz
        flux_model_id = "1504944"  # Flux1.dev from the gallery
        
        # API URL'sini oluştur
        api_url = f"https://api.astria.ai/tunes/{flux_model_id}/prompts"
        
        if not api_key:
            logger.error(f"Astria API bilgileri eksik. Key: {api_key[:5] if api_key else None}...")
            return jsonify({"error": "API yapılandırması eksik"}), 500
            
        logger.info(f"Astria API URL: {api_url}")
        
        # Benzersiz bir istek ID'si oluştur
        request_id = str(uuid.uuid4())
        logger.info(f"Oluşturulan istek ID: {request_id}")
        
        # Astria AI dokümantasyonuna göre boyutları ayarla
        # Boyutlar 8'in katları olmalıdır
        if aspect_ratio == "1:1":
            width, height = 1024, 1024  # Kare format
        elif aspect_ratio == "4:5":
            width, height = 1024, 1280  # Instagram post formatı
        elif aspect_ratio == "16:9":
            width, height = 1280, 720  # Yatay video/web formatı
        elif aspect_ratio == "9:16":
            width, height = 720, 1280  # Dikey story formatı
        else:
            # Varsayılan olarak 1:1 kullan
            width, height = 1024, 1024
            logger.warning(f"Bilinmeyen aspect ratio: {aspect_ratio}, varsayılan 1:1 kullanılıyor")
        
        logger.info(f"Kullanılan görsel boyutu: {width}x{height}")
        
        # Prompt'a aspect ratio bilgisini ekle ve optimize et
        # Astria AI dokümantasyonuna göre prompt'u düzenle
        aspect_ratio_prompt = ""
        if aspect_ratio == "1:1":
            aspect_ratio_prompt = "square format, 1:1 aspect ratio"
        elif aspect_ratio == "4:5":
            aspect_ratio_prompt = "portrait format, 4:5 aspect ratio, vertical composition"
        elif aspect_ratio == "16:9":
            aspect_ratio_prompt = "landscape format, 16:9 aspect ratio, horizontal composition"
        elif aspect_ratio == "9:16":
            aspect_ratio_prompt = "vertical format, 9:16 aspect ratio, portrait composition"
        
        enhanced_prompt = f"{prompt}, {aspect_ratio_prompt}, high quality, detailed"
        logger.info(f"Geliştirilmiş prompt: {enhanced_prompt[:100]}...")
        
        # Astria AI API isteği için form data hazırla
        # Dokümantasyona göre parametreleri ayarla
        data = {
            'prompt[text]': enhanced_prompt,
            'prompt[w]': str(width),
            'prompt[h]': str(height),
            'prompt[num_inference_steps]': "50",  # Daha yüksek kalite için 50 adım
            'prompt[guidance_scale]': "7.5",      # Prompt'a uyum için 7.5 değeri
            'prompt[seed]': "-1",                 # Rastgele seed
            'prompt[lora_scale]': "0.8"           # LoRA ağırlığı
        }
        
        headers = {
            "Authorization": f"Bearer {api_key}"
        }
        
        # Payload'ı logla (hassas bilgileri gizleyerek)
        logger.info(f"Astria API data: {json.dumps(data)}")
        
        # İstek zamanını ölç
        request_start_time = time.time()
        logger.info("Astria AI isteği başlıyor...")
        
        # Astria AI API'sine istek gönder
        response = requests.post(
            api_url,
            headers=headers,
            data=data
        )
        
        # İstek süresini hesapla
        request_duration = time.time() - request_start_time
        logger.info(f"Astria AI isteği tamamlandı. Süre: {request_duration:.2f} saniye")
        logger.info(f"Astria API yanıt kodu: {response.status_code}")
        
        # Yanıtı kontrol et
        if response.status_code == 200 or response.status_code == 201:
            try:
                result = response.json()
                logger.info(f"Astria AI yanıtı başarılı: {json.dumps(result)[:100]}...")
            except json.JSONDecodeError:
                # Yanıt JSON değilse, metin olarak al
                result = response.text
                logger.warning(f"Astria API yanıtı JSON formatında değil: {result[:100]}...")
                return jsonify({
                    "error": "API yanıtı geçersiz format",
                    "details": result[:200] + "..." if len(result) > 200 else result
                }), 500
            
            # Görsel URL'sini al - Astria API'sinin yanıt formatına göre
            image_url = None
            image_urls = []
            
            # Yanıt formatını kontrol et
            if isinstance(result, dict):
                # Prompt ID'yi kontrol et
                prompt_id = result.get('id')
                
                # Görsel URL'lerini farklı formatlarda kontrol et
                if 'images' in result and isinstance(result['images'], list) and len(result['images']) > 0:
                    for image in result['images']:
                        if isinstance(image, dict) and 'url' in image:
                            image_urls.append(image.get('url'))
                        elif isinstance(image, str):
                            image_urls.append(image)
                
                # Diğer olası formatları kontrol et
                if not image_urls and 'image_url' in result:
                    image_urls.append(result.get('image_url'))
                if not image_urls and 'output' in result and isinstance(result['output'], dict) and 'image_url' in result['output']:
                    image_urls.append(result['output']['image_url'])
                
                # İlk görsel URL'sini ana URL olarak ayarla (geriye dönük uyumluluk için)
                if image_urls:
                    image_url = image_urls[0]
                    # Store each generated image in our library
                    for url in image_urls:
                        store_generated_content(
                           url=url,
                            content_type= content_type,  # Use the content_type from request
                            type="image",
                            prompt=prompt
                        )
                
                # Görsel URL'lerini loglama
                if image_urls:
                    logger.info(f"Toplam {len(image_urls)} görsel URL bulundu")
                    logger.info(f"İlk görsel URL: {image_urls[0]}")
                else:
                    logger.warning(f"Görsel URL bulunamadı. Yanıt: {json.dumps(result)[:200]}...")
                
                if not image_urls:
                    logger.error("Astria AI yanıtında görsel URL'si bulunamadı")
                    logger.error(f"Tam yanıt: {json.dumps(result)}")
                    
                    # Prompt ID varsa, asenkron işleme için döndür
                    if prompt_id:
                        logger.info(f"Prompt ID bulundu: {prompt_id}. Görsel hazır olduğunda kontrol edilebilir.")
                        return jsonify({
                            "success": True,
                            "prompt_id": prompt_id,
                            "prompt": prompt,
                            "aspect_ratio": aspect_ratio,
                            "request_id": request_id,
                            "message": "Görsel asenkron olarak oluşturuluyor. Lütfen birkaç dakika sonra tekrar kontrol edin."
                        })
                    
                    return jsonify({"error": "Görsel oluşturulamadı", "details": result}), 500
                
                # Eğer yönlendirme isteniyorsa, image.html sayfasına yönlendir
                if redirect_to_page:
                    return redirect(url_for('image', image_url=image_urls, prompt=prompt, brand=brand_input))
                
                # Aksi takdirde JSON yanıtı döndür
                return jsonify({
                    "success": True,
                    "image_url": image_url,  # Geriye dönük uyumluluk için
                    "image_urls": image_urls,  # Tüm görsel URL'leri
                    "prompt": prompt,
                    "aspect_ratio": aspect_ratio,
                    "request_id": request_id,
                    "prompt_id": prompt_id  # Prompt ID'yi de döndür
                })
            else:
                logger.error(f"Beklenmeyen yanıt formatı: {type(result)}")
                return jsonify({"error": "Beklenmeyen yanıt formatı", "details": str(result)[:200]}), 500
        else:
            logger.error(f"Astria AI API hatası: {response.status_code} - {response.text}")
            return jsonify({
                "error": f"Görsel oluşturulurken bir hata oluştu: {response.status_code}",
                "details": response.text
            }), response.status_code
            
    except Exception as e:
        logger.error(f"Görsel oluşturma hatası: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({"error": f"Görsel oluşturulurken bir hata oluştu: {str(e)}"}), 500

@app.route("/image-to-video", methods=["POST"])
def image_to_video():
    """Görüntüyü videoya dönüştürmek için API endpoint'i."""
    try:
        data = request.get_json()
        image_url = data.get("image_url")
        content_type = data.get("content_type", "product-visual")  # Default to product-visual if not specified
        
        if not image_url:
            logger.error("Missing required parameter 'image_url' in image_to_video")
            return jsonify({"error": "Missing required parameter: 'image_url'"}), 400
            
        if content_type not in ['product-visual', 'video-image']:
            return jsonify({"error": "Invalid content type. Must be 'product-visual' or 'video-image'"}), 400

        logger.info(f"Görüntü videoya dönüştürülüyor: {image_url[:100]}...")
        
        # Fal.ai client'ın kullanılabilir olup olmadığını kontrol et
        if not FAL_CLIENT_AVAILABLE:
            logger.error("fal_client kütüphanesi yüklü değil. Video oluşturulamıyor.")
            return jsonify({"error": "Video oluşturma özelliği şu anda kullanılamıyor. Sunucu yapılandırması eksik."}), 500
        
        try:
            # Varsayılan prompt kullan
            prompt = "Transform this image into a video with subtle motion and life-like animation."
            logger.info(f"Varsayılan prompt kullanılıyor: {prompt}")
            
            # Benzersiz bir istek ID'si oluştur
            request_id = str(uuid.uuid4())
            logger.info(f"Oluşturulan istek ID: {request_id}")
            
            # İlerleme güncellemelerini işlemek için callback fonksiyonu
            def on_queue_update(update):
                if hasattr(update, 'logs') and update.logs:
                    for log in update.logs:
                        logger.info(f"🔄 {log.get('message', '')}")
                
                if hasattr(update, 'status'):
                    logger.info(f"Fal.ai durum: {update.status}")
            
            # API isteği için parametreler - Önce normal yoldan deneyelim
            arguments = {
                "prompt": prompt,
                "image_url": image_url
            }
            
            # Parametreleri logla
            logger.info(f"Fal.ai parametreleri: prompt={prompt[:50]}..., image_url={image_url[:50]}...")
            
            # İstek zamanını ölç
            request_start_time = time.time()
            logger.info("Fal.ai isteği başlıyor...")
            
            # Doğrudan API isteği için try bloğu
            try:
                # Fal.ai kling-video modelini doğrudan URL ile çağır
                result = fal_client.subscribe(
                    "fal-ai/kling-video/v1.6/pro/image-to-video",
                    arguments=arguments,
                    with_logs=True,
                    on_queue_update=on_queue_update
                )
                
                request_duration = time.time() - request_start_time
                logger.info(f"Fal.ai isteği tamamlandı. Süre: {request_duration:.2f} saniye")
                
            except Exception as direct_api_error:
                # Doğrudan URL ile istek başarısız olursa, sunucuda görüntüyü işle
                logger.warning(f"Doğrudan API isteği başarısız oldu: {str(direct_api_error)}")
                logger.info("Fallback yöntemi olarak görüntüyü sunucuda işlemeye geçiliyor...")
                
                try:
                    logger.info("Görüntü URL'den indiriliyor...")
                    
                    # Görüntü URL'sinden görüntüyü indir
                    image_response = requests.get(image_url, timeout=30)
                    
                    if image_response.status_code != 200:
                        logger.error(f"Görüntü indirilemedi: HTTP {image_response.status_code}")
                        return jsonify({"error": f"Görüntü indirilemedi: HTTP {image_response.status_code}"}), 500
                    
                    # Geçici dosya oluştur
                    temp_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "temp")
                    
                    # temp dizini yoksa oluştur
                    if not os.path.exists(temp_dir):
                        os.makedirs(temp_dir)
                    
                    temp_image_path = os.path.join(temp_dir, f"temp_image_{request_id}.jpg")
                    
                    # Görüntüyü geçici dosyaya kaydet
                    with open(temp_image_path, "wb") as f:
                        f.write(image_response.content)
                    
                    logger.info(f"Görüntü geçici dosyaya kaydedildi: {temp_image_path}")
                    
                    # Görüntüyü base64'e dönüştür
                    with open(temp_image_path, "rb") as image_file:
                        encoded_string = base64.b64encode(image_file.read()).decode("utf-8")
                    
                    logger.info("Görüntü base64'e dönüştürüldü")
                    
                    # Base64 formatında görüntü URL'si
                    base64_image = f"data:image/jpeg;base64,{encoded_string}"
                    
                    # API isteği için parametreleri güncelle
                    arguments = {
                        "prompt": prompt,
                        "image_url": base64_image  # URL yerine base64 kodlu görüntü kullan
                    }
                    
                    # Parametreleri logla (base64 verisi çok büyük olduğu için onu loglama)
                    logger.info(f"Fal.ai güncellenmiş parametreler: prompt={prompt[:50]}..., base64_image=<veri çok büyük>")
                    
                    # İstek zamanını ölç
                    request_start_time = time.time()
                    logger.info("Fal.ai base64 isteği başlıyor...")
                    
                    # Fal.ai kling-video modelini base64 verisi ile çağır
                    result = fal_client.subscribe(
                        "fal-ai/kling-video/v1.6/pro/image-to-video",
                        arguments=arguments,
                        with_logs=True,
                        on_queue_update=on_queue_update
                    )
                    
                    request_duration = time.time() - request_start_time
                    logger.info(f"Fal.ai base64 isteği tamamlandı. Süre: {request_duration:.2f} saniye")
                    
                    # Geçici dosyayı temizle
                    try:
                        if os.path.exists(temp_image_path):
                            os.remove(temp_image_path)
                            logger.info(f"Geçici dosya silindi: {temp_image_path}")
                    except Exception as cleanup_error:
                        logger.warning(f"Geçici dosya temizlenirken hata: {str(cleanup_error)}")
                
                except Exception as fallback_error:
                    logger.error(f"Fallback yöntemi de başarısız oldu: {str(fallback_error)}")
                    return jsonify({"error": f"Video oluşturma başarısız oldu: {str(fallback_error)}"}), 500
            
            # Sonucu logla
            logger.info(f"Fal.ai sonucu: {json.dumps(result)[:200]}...")
            
            # Video URL'sini al
            video_url = None
            
            # Farklı formatlarda video URL kontrolü
            if "output" in result and "video_url" in result["output"]:
                video_url = result["output"]["video_url"]
            elif "videos" in result and len(result["videos"]) > 0:
                video_url = result["videos"][0]["url"]
            elif "video" in result and "url" in result["video"]:
                video_url = result["video"]["url"]
            elif "video_url" in result:
                video_url = result["video_url"]
            
            if not video_url:
                logger.error(f"Video URL'si bulunamadı. Sonuç: {result}")
                return jsonify({"error": "Video URL'si alınamadı"}), 500
            
            logger.info(f"Video başarıyla oluşturuldu. URL: {video_url}")
            
            # Store the generated video in our library
            store_generated_content(
                url=video_url,
                content_type=content_type,
                type="video",
                prompt=prompt if prompt else None
            )
            
            # Video sayfasına yönlendir
            logger.info("İstemciye yanıt gönderiliyor...")
            return jsonify({
                "success": True,
                "video_url": video_url,
                "request_id": request_id,
                "prompt": prompt
            })
            
        except Exception as fal_error:
            logger.error(f"Fal.ai istemcisi hatası: {str(fal_error)}")
            logger.error(f"Hata izleme: {traceback.format_exc()}")
            
            return jsonify({"error": f"Video oluşturma başarısız oldu: {str(fal_error)}"}), 500
            
    except Exception as e:
        logger.error(f"Genel hata: {str(e)}")
        logger.error(f"Hata izleme: {traceback.format_exc()}")
        return jsonify({"error": f"İşlem başarısız oldu: {str(e)}"}), 500

@app.route('/library')
def library():
    """Display the content library page with data from Supabase."""
    try:
        # Get pagination parameters
        page = request.args.get('page', 1, type=int)
        per_page = 20
        offset = (page - 1) * per_page
        
        # Fetch data from Supabase
        media_items = fetch_generations_from_db(limit=per_page, offset=offset)
        
        # Log the data being sent to template
        logger.info(f"Sending {len(media_items)} items to library template")
        for item in media_items:
            logger.info(f"Item: type={item.get('type')}, content_type={item.get('content_type')}, url={item.get('url')}")
        
        return render_template('library.html', media_items=media_items)
    except Exception as e:
        logger.error(f"Error in library route: {str(e)}")
        logger.error(f"Full traceback: {traceback.format_exc()}")
        return render_template('library.html', media_items=[], error=str(e))

@app.errorhandler(404)
def page_not_found(e):
    logger.error(f"404 error: {str(e)}")
    return render_template('error.html', error="Page not found"), 404

@app.errorhandler(500)
def internal_server_error(e):
    logger.error(f"500 error: {str(e)}")
    return render_template('error.html', error="Internal server error"), 500

@app.route('/delete-generation/<generation_id>', methods=['DELETE'])
def delete_generation(generation_id):
    """Delete a generation from the database."""
    try:
        if not supabase:
            return jsonify({"error": "Database connection not available"}), 500
            
        # Validate UUID format
        try:
            # Convert string to UUID to validate format
            uuid_obj = uuid.UUID(generation_id)
        except ValueError:
            logger.error(f"Invalid UUID format: {generation_id}")
            return jsonify({"error": "Invalid generation ID format"}), 400
            
        # Delete the record
        response = supabase.table('generations') \
            .delete() \
            .eq('id', str(uuid_obj)) \
            .execute()
            
        if response and response.data:
            logger.info(f"Successfully deleted generation {generation_id}")
            return jsonify({"success": True})
        else:
            logger.error(f"No generation found with ID {generation_id}")
            return jsonify({"error": "Generation not found"}), 404
            
    except Exception as e:
        logger.error(f"Error deleting generation {generation_id}: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    logger.info("Uygulama başlatılıyor...")
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)