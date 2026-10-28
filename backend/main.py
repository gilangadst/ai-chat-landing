
from io import BytesIO
from pathlib import Path
import logging
import os
import re
from urllib.request import urlopen

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from google import genai
import joblib
import pandas as pd
from sklearn.metrics.pairwise import cosine_similarity

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

BASE_DIR = Path(__file__).resolve().parent
CSV_URL = (
    "https://raw.githubusercontent.com/gilangadst/ai-chat-landing/"
    "main/backend/data_deskripsi_budaya_final.csv"
)
if load_dotenv:
    load_dotenv(BASE_DIR / ".env")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="API Chatbot Kebudayaan Indonesia")

# Izinkan CORS agar Angular (biasanya port 4200) bisa mengakses API ini
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Untuk produksi, batasi ke URL Angular Anda
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Unduh CSV budaya dan bangun ulang matriks pencarian.
df_clean = None
vectorizer = None
matrix = None
try:
    with urlopen(CSV_URL, timeout=30) as response:
        df_clean = pd.read_csv(BytesIO(response.read()))

    required_columns = {
        "Nama Budaya",
        "Kategori",
        "Provinsi",
        "Kabupaten",
        "Deskripsi",
    }
    missing_columns = required_columns.difference(df_clean.columns)
    if missing_columns:
        raise ValueError(
            f"CSV budaya tidak memiliki kolom yang diperlukan: {sorted(missing_columns)}"
        )

    vectorizer = joblib.load(BASE_DIR / "vectorizer_kaya.joblib")
    descriptions = df_clean["Deskripsi"].fillna("").astype(str)
    matrix = vectorizer.transform(descriptions)
    logger.info("Culture CSV downloaded and retrieval matrix built (%d rows).", len(df_clean))
except Exception:
    logger.exception("Failed to download culture CSV or load retrieval vectorizer.")

# 2. Inisialisasi Gemini Client menggunakan Environment Variable
api_key = os.getenv("GOOGLE_API_KEY", "")
client = genai.Client(api_key=api_key) if api_key else None
if client:
    logger.info("Gemini API key is configured.")
else:
    logger.warning("GOOGLE_API_KEY is missing; local fallback is enabled.")

class HistoryItem(BaseModel):
    user: str = ""
    bot: str = ""


class ChatRequest(BaseModel):
    message: str
    history: list[HistoryItem] = Field(default_factory=list)


def find_named_culture_indices(question, cultures):
    normalized_question = re.sub(r"\W+", " ", question.casefold()).strip()
    normalized_question = f" {normalized_question} "
    matched_indices = []

    for index, name in enumerate(cultures["Nama Budaya"].fillna("").astype(str)):
        names = {name, name.split("(", maxsplit=1)[0].strip()}
        for candidate in names:
            normalized_name = re.sub(r"\W+", " ", candidate.casefold()).strip()
            if normalized_name and f" {normalized_name} " in normalized_question:
                matched_indices.append(index)
                break

    return matched_indices


@app.post("/api/chat")
async def chat_endpoint(request: ChatRequest):
    if vectorizer is None or matrix is None or df_clean is None:
        raise HTTPException(
            status_code=503,
            detail=(
                "Data budaya dari GitHub atau vectorizer belum berhasil dimuat. "
                "Periksa koneksi internet, URL CSV, dan file vectorizer_kaya.joblib "
                "di folder backend."
            ),
        )

    pertanyaan = request.message
    riwayat = request.history
    named_indices = find_named_culture_indices(pertanyaan, df_clean)

    # A. Hitung kemiripan TF-IDF lokal
    try:
        pertanyaan_tfidf = vectorizer.transform([pertanyaan])
        kemiripan = cosine_similarity(pertanyaan_tfidf, matrix).flatten()
        indeks_terbaik = kemiripan.argsort()[-1]
        skor_kemiripan = kemiripan[indeks_terbaik]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gagal memproses TF-IDF: {e}")

    has_relevant_document = bool(named_indices) or skor_kemiripan >= 0.08
    if named_indices:
        selected_cultures = df_clean.iloc[named_indices]
        context = "\n\n".join(
            f"""
            Nama Budaya: {culture['Nama Budaya']}
            Kategori: {culture['Kategori']}
            Asal Daerah: {culture['Kabupaten']}, {culture['Provinsi']}
            Deskripsi Lengkap: {culture['Deskripsi']}
            """
            for _, culture in selected_cultures.iterrows()
        )
    elif skor_kemiripan < 0.08:
        context = "Tidak ada dokumen kebudayaan spesifik yang sangat relevan dengan pertanyaan ini."
    else:
        budaya_terpilih = df_clean.iloc[indeks_terbaik]
        context = f"""
        Nama Budaya: {budaya_terpilih['Nama Budaya']}
        Kategori: {budaya_terpilih['Kategori']}
        Asal Daerah: {budaya_terpilih['Kabupaten']}, {budaya_terpilih['Provinsi']}
        Deskripsi Lengkap: {budaya_terpilih['Deskripsi']}
        """

    if not client:
        logger.warning("Skipping Gemini: GOOGLE_API_KEY is not configured.")
        if not has_relevant_document:
            return {
                "reply": (
                    "Saya belum menemukan informasi yang cocok di data lokal, dan "
                    "Gemini belum dikonfigurasi untuk menjawab pertanyaan ini."
                )
            }
        selected_indices = named_indices or [indeks_terbaik]
        reply = "\n\n".join(
            f"[Lokal] {culture['Nama Budaya']} berasal dari {culture['Kabupaten']}, "
            f"{culture['Provinsi']}. Kategori: {culture['Kategori']}. "
            f"{culture['Deskripsi'][:300]}..."
            for _, culture in df_clean.iloc[selected_indices].iterrows()
        )
        return {"reply": reply}

    # C. Bangun prompt RAG. Retrieval supplies context when available but does
    # not decide whether a question is allowed to reach Gemini.
    string_riwayat = ""
    for chat in riwayat:
        string_riwayat += f"User: {chat.user}\nChatbot: {chat.bot}\n"

    prompt = f"""
    Anda adalah asisten chatbot khusus Kebudayaan Indonesia yang sangat cerdas, ramah, dan sopan.

    ATURAN PENJAWABAN:
    1. Anda adalah asisten yang fokus pada kebudayaan Indonesia, termasuk tradisi, tarian, kuliner, tokoh, dan Kementerian Kebudayaan.
    2. Balas sapaan atau basa-basi singkat dengan ramah, lalu arahkan percakapan ke kebudayaan Indonesia.
    3. Pertanyaan budaya tetap boleh dijawab dari pengetahuan umum Anda jika konteks lokal tidak tersedia. Jangan berpura-pura informasi itu berasal dari database.
    4. Untuk jabatan atau informasi yang dapat berubah, jelaskan jika informasi Anda mungkin tidak terbaru.
    5. Jika tidak yakin, jangan mengarang; sampaikan ketidakpastian.
    6. Tolak pertanyaan yang tidak berkaitan dengan budaya Indonesia secara sopan.

    Gunakan Informasi Konteks Budaya berikut sebagai referensi utama Anda:
    {context}

    Jika konteks menyatakan tidak ada dokumen yang cocok, gunakan pengetahuan umum Anda untuk pertanyaan budaya dan jangan menolak hanya karena dokumen lokal tidak tersedia.

    Riwayat Percakapan Sebelumnya:
    {string_riwayat}

    Pertanyaan User Terbaru: {pertanyaan}

    Jawaban Anda:
    """

    try:
        logger.info("Sending request to Gemini model gemini-3.5-flash-lite.")
        response = client.models.generate_content(
            model='gemini-3.5-flash-lite',
            contents=prompt,
        )
        output_text = response.text
        if not output_text:
            raise ValueError("Gemini returned an empty response.")
        if skor_kemiripan >= 0.08:
            output_text += f"\n\n*(Keakuratan pencarian data dasar: {skor_kemiripan:.2%})*"
        logger.info("Gemini response received successfully.")
        return {"reply": output_text}
    except Exception as e:
        logger.exception("Gemini request failed.")
        raise HTTPException(
            status_code=502,
            detail="Permintaan ke Gemini gagal. Periksa log di terminal backend.",
        ) from e

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=8000)
