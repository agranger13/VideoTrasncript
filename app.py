#!/usr/bin/env python3
import os
import uuid
import subprocess
import json
from pathlib import Path
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import boto3
from botocore.exceptions import ClientError
import ffmpeg
from dotenv import load_dotenv
import structlog

load_dotenv()

app = Flask(__name__)
CORS(app)

# Configuration des logs
logger = structlog.get_logger()

# Configuration AWS S3
s3_client = boto3.client(
    's3',
    aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
    aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
    region_name=os.getenv('AWS_REGION', 'us-west-2')
)

S3_BUCKET = os.getenv('S3_BUCKET_NAME')

# Répertoires
INPUT_DIR = Path('/app/input')
OUTPUT_DIR = Path('/app/output')
TEMP_DIR = Path('/app/temp')

class VideoEncoder:
    """Classe pour l'encodage vidéo optimisé"""
    
    @staticmethod
    def get_video_info(file_path):
        """Récupère les informations d'une vidéo"""
        try:
            probe = ffmpeg.probe(file_path)
            video_stream = next((stream for stream in probe['streams'] 
                               if stream['codec_type'] == 'video'), None)
            return {
                'duration': float(probe['format']['duration']),
                'size': int(probe['format']['size']),
                'bitrate': int(probe['format']['bit_rate']),
                'width': int(video_stream['width']),
                'height': int(video_stream['height']),
                'codec': video_stream['codec_name'],
                'fps': eval(video_stream['r_frame_rate'])
            }
        except Exception as e:
            logger.error(f"Erreur lors de l'analyse vidéo: {e}")
            return None

    @staticmethod
    def encode_with_rav1e(input_path, output_path, quality=None, speed=None):
        """Encode une vidéo avec rav1e (AV1)"""
        try:
            # Paramètres par défaut
            if quality is None:
                quality = 50  # 0-255, plus bas = meilleure qualité
            if speed is None:
                speed = 6  # 0-10, plus haut = plus rapide mais qualité moindre

            cmd = [
                'ffmpeg',
                '-i', str(input_path),
                '-c:v', 'librav1e',
                '-qp', str(quality),
                '-speed', str(speed),
                '-tile-columns', '2',
                '-tile-rows', '1',
                '-c:a', 'libopus',
                '-b:a', '96k',
                '-movflags', '+faststart',
                '-y',
                str(output_path)
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                raise Exception(f"Erreur FFmpeg: {result.stderr}")
                
            return True
            
        except Exception as e:
            logger.error(f"Erreur encodage rav1e: {e}")
            return False

    @staticmethod
    def encode_h264_optimized(input_path, output_path, crf=23, preset='medium'):
        """Encode une vidéo avec H.264 optimisé"""
        try:
            (
                ffmpeg
                .input(str(input_path))
                .output(
                    str(output_path),
                    vcodec='libx264',
                    crf=crf,
                    preset=preset,
                    acodec='aac',
                    audio_bitrate='128k',
                    movflags='+faststart'
                )
                .overwrite_output()
                .run(quiet=True)
            )
            return True
        except Exception as e:
            logger.error(f"Erreur encodage H.264: {e}")
            return False

    @staticmethod
    def encode_h265_optimized(input_path, output_path, crf=28, preset='medium'):
        """Encode une vidéo avec H.265 optimisé"""
        try:
            (
                ffmpeg
                .input(str(input_path))
                .output(
                    str(output_path),
                    vcodec='libx265',
                    crf=crf,
                    preset=preset,
                    acodec='aac',
                    audio_bitrate='128k',
                    movflags='+faststart'
                )
                .overwrite_output()
                .run(quiet=True)
            )
            return True
        except Exception as e:
            logger.error(f"Erreur encodage H.265: {e}")
            return False

def upload_to_s3(file_path, bucket, object_name=None):
    """Upload un fichier vers S3"""
    if object_name is None:
        object_name = os.path.basename(file_path)
    
    try:
        s3_client.upload_file(file_path, bucket, object_name)
        return f"https://{bucket}.s3.amazonaws.com/{object_name}"
    except ClientError as e:
        logger.error(f"Erreur upload S3: {e}")
        return None

@app.route('/health', methods=['GET'])
def health_check():
    """Point de santé de l'API"""
    return jsonify({"status": "healthy", "service": "video-encoder"})

@app.route('/encode', methods=['POST'])
def encode_video():
    """Point d'entrée principal pour l'encodage vidéo"""
    try:
        # Vérification du fichier uploadé
        if 'video' not in request.files:
            return jsonify({"error": "Aucun fichier vidéo fourni"}), 400
        
        file = request.files['video']
        if file.filename == '':
            return jsonify({"error": "Nom de fichier vide"}), 400

        # Paramètres d'encodage
        codec = request.form.get('codec', 'h264')  # h264, h265, av1
        quality = request.form.get('quality', 'medium')  # low, medium, high
        upload_s3 = request.form.get('upload_s3', 'true').lower() == 'true'

        # Génération d'un ID unique pour cette tâche
        task_id = str(uuid.uuid4())
        
        # Sauvegarde du fichier d'entrée
        input_filename = f"{task_id}_{file.filename}"
        input_path = INPUT_DIR / input_filename
        file.save(input_path)

        # Analyse de la vidéo d'entrée
        video_info = VideoEncoder.get_video_info(input_path)
        if not video_info:
            return jsonify({"error": "Impossible d'analyser la vidéo"}), 400

        logger.info(f"Vidéo analysée: {video_info}")

        # Détermination du nom de sortie
        base_name = Path(file.filename).stem
        output_filename = f"{task_id}_{base_name}_optimized"
        
        if codec == 'av1':
            output_filename += '.mp4'
            output_path = OUTPUT_DIR / output_filename
            
            # Paramètres qualité pour AV1
            quality_settings = {
                'low': {'quality': 35, 'speed': 8},
                'medium': {'quality': 50, 'speed': 6},
                'high': {'quality': 25, 'speed': 4}
            }
            settings = quality_settings.get(quality, quality_settings['medium'])
            
            success = VideoEncoder.encode_with_rav1e(
                input_path, output_path, 
                quality=settings['quality'], 
                speed=settings['speed']
            )
            
        elif codec == 'h265':
            output_filename += '.mp4'
            output_path = OUTPUT_DIR / output_filename
            
            # Paramètres CRF pour H.265
            crf_settings = {'low': 32, 'medium': 28, 'high': 23}
            crf = crf_settings.get(quality, 28)
            
            success = VideoEncoder.encode_h265_optimized(
                input_path, output_path, crf=crf
            )
            
        else:  # h264 par défaut
            output_filename += '.mp4'
            output_path = OUTPUT_DIR / output_filename
            
            # Paramètres CRF pour H.264
            crf_settings = {'low': 28, 'medium': 23, 'high': 18}
            crf = crf_settings.get(quality, 23)
            
            success = VideoEncoder.encode_h264_optimized(
                input_path, output_path, crf=crf
            )

        if not success:
            return jsonify({"error": "Échec de l'encodage"}), 500

        # Analyse de la vidéo de sortie
        output_info = VideoEncoder.get_video_info(output_path)
        
        # Calcul du taux de compression
        compression_ratio = (1 - output_info['size'] / video_info['size']) * 100

        response_data = {
            "task_id": task_id,
            "codec": codec,
            "quality": quality,
            "original": {
                "size": video_info['size'],
                "duration": video_info['duration'],
                "bitrate": video_info['bitrate'],
                "resolution": f"{video_info['width']}x{video_info['height']}"
            },
            "encoded": {
                "size": output_info['size'],
                "duration": output_info['duration'],
                "bitrate": output_info['bitrate'],
                "resolution": f"{output_info['width']}x{output_info['height']}"
            },
            "compression_ratio": f"{compression_ratio:.1f}%",
            "filename": output_filename
        }

        # Upload vers S3 si demandé
        if upload_s3 and S3_BUCKET:
            s3_url = upload_to_s3(output_path, S3_BUCKET, output_filename)
            if s3_url:
                response_data["s3_url"] = s3_url
                logger.info(f"Fichier uploadé vers S3: {s3_url}")
            else:
                logger.warning("Échec de l'upload S3")

        # Nettoyage du fichier d'entrée
        os.remove(input_path)

        return jsonify(response_data)

    except Exception as e:
        logger.error(f"Erreur lors de l'encodage: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/download/<filename>', methods=['GET'])
def download_video(filename):
    """Télécharge une vidéo encodée"""
    try:
        file_path = OUTPUT_DIR / filename
        if not file_path.exists():
            return jsonify({"error": "Fichier non trouvé"}), 404
        
        return send_file(file_path, as_attachment=True)
    
    except Exception as e:
        logger.error(f"Erreur téléchargement: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/codecs', methods=['GET'])
def get_available_codecs():
    """Retourne la liste des codecs disponibles"""
    return jsonify({
        "codecs": ["h264", "h265", "av1"],
        "quality_levels": ["low", "medium", "high"],
        "supported_formats": [".mp4", ".mov", ".avi", ".mkv", ".webm"]
    })

@app.route('/batch', methods=['POST'])
def batch_encode():
    """Encodage en lot de plusieurs vidéos"""
    try:
        files = request.files.getlist('videos')
        if not files:
            return jsonify({"error": "Aucun fichier fourni"}), 400

        codec = request.form.get('codec', 'h264')
        quality = request.form.get('quality', 'medium')
        upload_s3 = request.form.get('upload_s3', 'true').lower() == 'true'

        results = []
        
        for file in files:
            if file.filename == '':
                continue
                
            # Traitement similaire à encode_video mais en boucle
            task_id = str(uuid.uuid4())
            input_filename = f"{task_id}_{file.filename}"
            input_path = INPUT_DIR / input_filename
            file.save(input_path)

            # Analyse et encodage (logique simplifiée)
            video_info = VideoEncoder.get_video_info(input_path)
            if video_info:
                base_name = Path(file.filename).stem
                output_filename = f"{task_id}_{base_name}_optimized.mp4"
                output_path = OUTPUT_DIR / output_filename

                if codec == 'av1':
                    success = VideoEncoder.encode_with_rav1e(input_path, output_path)
                elif codec == 'h265':
                    success = VideoEncoder.encode_h265_optimized(input_path, output_path)
                else:
                    success = VideoEncoder.encode_h264_optimized(input_path, output_path)

                if success:
                    output_info = VideoEncoder.get_video_info(output_path)
                    compression_ratio = (1 - output_info['size'] / video_info['size']) * 100
                    
                    result = {
                        "filename": file.filename,
                        "task_id": task_id,
                        "success": True,
                        "compression_ratio": f"{compression_ratio:.1f}%",
                        "output_filename": output_filename
                    }

                    # Upload S3 optionnel
                    if upload_s3 and S3_BUCKET:
                        s3_url = upload_to_s3(output_path, S3_BUCKET, output_filename)
                        if s3_url:
                            result["s3_url"] = s3_url
                    
                    results.append(result)
                else:
                    results.append({
                        "filename": file.filename,
                        "success": False,
                        "error": "Échec de l'encodage"
                    })

            # Nettoyage
            os.remove(input_path)

        return jsonify({"results": results})

    except Exception as e:
        logger.error(f"Erreur encodage en lot: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    # Création des répertoires si nécessaires
    INPUT_DIR.mkdir(exist_ok=True)
    OUTPUT_DIR.mkdir(exist_ok=True)
    TEMP_DIR.mkdir(exist_ok=True)
    
    # Démarrage de l'application
    app.run(host='0.0.0.0', port=5000, debug=False)