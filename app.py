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
import fal_client  # Fal.ai client kütüphanesini içe aktar

# Loglama yapılandırması
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# DNS çözümleme zaman aşımını artır
socket.setdefaulttimeout(30)  # 30 saniye

# Bağlantı havuzu yönetimi
urllib3.PoolManager(retries=urllib3.Retry(total=5, backoff_factor=0.5))

load_dotenv()

app = Flask(__name__)

# API anahtarları
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
FAL_API_KEY = os.getenv("FAL_API_KEY")
ASSISTANT_ID = os.getenv("ASSISTANT_ID")

# Fal.ai API yapılandırması - FAL_KEY çevre değişkenini ayarla
os.environ["FAL_KEY"] = FAL_API_KEY
logger.info(f"FAL_KEY çevre değişkeni ayarlandı: {FAL_API_KEY[:8]}...")

# OpenAI istemcisini yapılandır
try:
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
except Exception as e:
    logger.error(f"OpenAI API bağlantısı kurulamadı: {str(e)}")
    logger.error(f"Hata izleme: {traceback.format_exc()}")

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

def generate_prompt(text: str, feature_type: str) -> dict:
    """
    OpenAI chat completion API kullanarak doğrudan prompt oluşturur.
    Her bir prompt için ayrı stil belirler.
    """
    if feature_type not in ["image", "video"]:
        raise ValueError("Geçersiz feature_type! 'image' veya 'video' olmalıdır.")
    
    logger.info(f"Prompt oluşturuluyor. Metin: {text[:50]}... Özellik tipi: {feature_type}")
    
    try:
        # Feature type değerini uygun formata dönüştür
        prompt_type = "image" if feature_type == "image" else "video"
        
        # Sistem talimatı - Her prompt için ayrı stil belirle
        system_instruction = f"""
        Görevin, kullanıcının verdiği metin için {prompt_type} oluşturmak üzere 4 farklı prompt üretmektir.
        
        Her prompt için farklı bir stil belirle ve her promptun başına stilini ekle.
        
        Kurallar:
        1. Her prompt en az 20, en fazla 75 kelime olmalıdır.
        2. Her prompt farklı bir yaklaşım ve stil sunmalıdır.
        3. Promptlar doğrudan {prompt_type} oluşturmak için kullanılabilir olmalıdır.
        4. Her prompt için belirgin bir stil belirle (örn: cinematic, photorealistic, anime, 3D render, oil painting, vb.)
        
        Yanıtın şu formatta olmalıdır:
        
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
                {"role": "user", "content": f"Metin: {text}\nTür: {feature_type}"}
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
    logger.info("Görsel üretici sayfası görüntüleniyor")
    return render_template('image.html')

@app.route("/generate-prompt", methods=["POST"])
def generate_prompt_api():
    """API endpoint for generating prompts."""
    data = request.json
    text = data.get("text")
    feature_type = data.get("feature_type")
    
    if not text or not feature_type:
        return jsonify({"error": "Missing required parameters: 'text' and 'feature_type'"}), 400
    
    try:
        result = generate_prompt(text, feature_type)
        return jsonify(result)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

@app.route('/generate_video', methods=['POST'])
def generate_video():
    prompt = request.form.get('prompt')
    brand_input = request.form.get('brand_input')
    aspect_ratio = request.form.get('aspect_ratio', '9:16')  # Varsayılan olarak 9:16
    
    if not prompt:
        return jsonify({"error": "Geçersiz prompt seçimi"}), 400
    
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
                        logger.info(f"Fal.ai log: {log.get('message', '')}")
                
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
    """İstek durumunu kontrol etmek için API endpoint'i"""
    try:
        logger.info(f"İstek durumu kontrol ediliyor (ID: {request_id})...")
        status = fal_client.status("fal-ai/veo2", request_id, with_logs=True)
        
        # Durum bilgisini JSON olarak döndür
        return jsonify({
            "status": status,
            "timestamp": time.time()
        })
    except Exception as e:
        logger.error(f"İstek durumu kontrol edilirken hata oluştu: {str(e)}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    logger.info("Uygulama başlatılıyor...")
    app.run(debug=True)