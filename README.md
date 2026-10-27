# Chatbot Kebudayaan Indonesia

Landing page Angular (tema gelap) yang memanggil model RAG di `backend/main.py`.

## Frontend

```bash
npm install
npm start
```

Buka `http://localhost:4200`. Permintaan `/api` di-proxy ke `http://127.0.0.1:8000`.

## Backend

Letakkan file model di folder `backend/` (sejajar `main.py`):

- `data_deskripsi_budaya_final.csv`
- `vectorizer_kaya.joblib`
- `semua_deskripsi_tfidf_kaya.joblib`

Salin `backend/.env.example` menjadi `backend/.env` lalu isi `GOOGLE_API_KEY` jika ingin jawaban Gemini. Tanpa kunci, API memakai cadangan lokal dari dokumen TF-IDF.

```bash
cd backend
pip install -r requirements.txt
python main.py
```

## Kontrak chat

`POST /api/chat`

```json
{
  "message": "Apa itu Tari Saman?",
  "history": [
    { "user": "Halo", "bot": "Halo, silakan tanya budaya Nusantara." }
  ]
}
```

Respons: `{ "reply": "..." }`
