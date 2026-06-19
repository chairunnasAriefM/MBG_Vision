# --- DAFTAR IMPORT ---
# --- DAFTAR IMPORT ---
from fastapi import FastAPI, UploadFile, File, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles     
from fastapi.responses import FileResponse      
from ultralytics import YOLO
import cv2
import numpy as np
import base64

# ==========================================
# INISIALISASI APLIKASI & KONFIGURASI
# ==========================================

# Membuat instance/objek utama dari aplikasi FastAPI
app = FastAPI(title="MBG Vision API")

# MENGATUR CORS (Cross-Origin Resource Sharing)
# Ini wajib agar frontend (HTML/JS) yang berjalan di port/domain berbeda 
# diizinkan untuk mengirim request (POST/WebSocket) ke server FastAPI ini.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],     # Mengizinkan semua domain (Bisa diubah ke spesifik domain jika sudah tahap produksi)
    allow_credentials=True,
    allow_methods=["*"],     # Mengizinkan semua metode HTTP (GET, POST, dll)
    allow_headers=["*"],     # Mengizinkan semua header
)

# Muat Model YOLO
# Memuat model deteksi objek yang sudah dilatih sebelumnya. 
# Pastikan file "best.pt" berada di direktori (folder) yang sama dengan file main.py ini.
model = YOLO("best.pt") 

# ==========================================
# ROUTING UNTUK FRONTEND (HTML, CSS, JS)
# ==========================================

# 1. Mount folder "frontend" agar CSS dan JS bisa diakses
# PENTING: Pastikan parameter directory="frontend" sesuai dengan nama folder Anda
app.mount("/static", StaticFiles(directory="frontend"), name="static")

# 2. Endpoint utama ("/") untuk memuat file HTML saat web pertama kali dibuka
@app.get("/")
async def serve_frontend():
    return FileResponse("frontend/index.html")


# ==========================================
# ENDPOINT 1: HTTP POST (Upload Gambar Tunggal)
# ==========================================
# Digunakan ketika pengguna mengunggah file foto secara manual.

@app.post("/detect/")
async def detect_objects(file: UploadFile = File(...)):
    try:
        # 1. Membaca file gambar mentah yang dikirim dari frontend
        contents = await file.read()
        
        # 2. Mengonversi data biner mentah menjadi array Numpy (format yang dipahami OpenCV)
        nparr = np.frombuffer(contents, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        # 3. Menjalankan deteksi menggunakan model YOLO pada gambar tersebut
        results = model(img)

        # Variabel untuk menampung metrik sementara
        detections_count = 0
        total_confidence = 0.0

        # 4. Mengekstrak informasi dari hasil deteksi YOLO
        for r in results:
            detections_count += len(r.boxes) # Hitung total objek yang ditemukan
            for box in r.boxes:
                # Mengambil tingkat kepercayaan (confidence) tiap objek dan menjumlahkannya
                total_confidence += float(box.conf[0])
            
            # Menggambar kotak (bounding box) pada gambar aslinya.
            # Jika tidak ada anomali, gambar akan dikembalikan seperti aslinya.
            img_with_boxes = r.plot()

        # 5. Menghitung rata-rata tingkat kepercayaan (Hindari pembagian dengan nol)
        avg_confidence = (total_confidence / detections_count) if detections_count > 0 else 0.0

        # 6. Mengonversi gambar yang sudah ada bounding box-nya kembali ke teks Base64
        _, buffer = cv2.imencode('.jpg', img_with_boxes)
        img_base64 = base64.b64encode(buffer).decode('utf-8')

        # 7. Mengirim balik hasil (Response) ke frontend dalam bentuk JSON
        return {
            "image_base64": img_base64,
            "detections_count": detections_count,
            "confidence": avg_confidence
        }

    except Exception as e:
        # Tangkap dan kembalikan pesan error jika terjadi kegagalan pemrosesan
        return {"error": str(e)}


# ==========================================
# ENDPOINT 2: WEBSOCKET (Streaming Real-time)
# ==========================================
# Digunakan untuk membuka jalur komunikasi dua arah agar video bisa mengalir tanpa henti.

@app.websocket("/ws/detect/")
async def websocket_endpoint(websocket: WebSocket):
    # Terima dan buka koneksi dari frontend
    await websocket.accept()
    
    try:
        # Memulai loop tanpa henti selama koneksi belum ditutup oleh frontend
        while True:
            # 1. Terima frame dari frontend dalam format teks Base64
            data = await websocket.receive_text()
            
            # 2. Hapus prefix "data:image/jpeg;base64," agar tersisa data murninya saja
            encoded_data = data.split(',')[1]
            
            # 3. Decode teks Base64 tersebut menjadi gambar (array Numpy/OpenCV)
            nparr = np.frombuffer(base64.b64decode(encoded_data), np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

            # 4. Jalankan deteksi YOLO (Sama persis seperti logika pada metode POST)
            results = model(img)
            detections_count = 0
            total_confidence = 0.0

            for r in results:
                detections_count += len(r.boxes)
                for box in r.boxes:
                    total_confidence += float(box.conf[0])
                
                # Plot bounding box (Jika kosong, kembalikan gambar asli)
                img_with_boxes = r.plot() 

            avg_confidence = (total_confidence / detections_count) if detections_count > 0 else 0.0

            # 5. Encode ulang gambar yang sudah diproses menjadi format Base64
            _, buffer = cv2.imencode('.jpg', img_with_boxes)
            img_base64 = base64.b64encode(buffer).decode('utf-8')

            # 6. Kirim hasil balik ke frontend secara instan tanpa memutus jalur koneksi (Streaming)
            await websocket.send_json({
                "image_base64": img_base64,
                "detections_count": detections_count,
                "confidence": avg_confidence
            })

    except WebSocketDisconnect:
        # Logika ketika pengguna mematikan kamera atau menutup tab browser
        print("Client disconnected dari WebSocket.")
    except Exception as e:
        # Menangkap error lain jika frame gagal diproses atau jaringan tidak stabil
        print(f"WebSocket Error: {str(e)}")