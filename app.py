import os
import fitz  # PyMuPDF for PDF text extraction
import google.generativeai as genai
from flask import Flask, request, render_template

# Flask app
app = Flask(__name__)

# Configure Gemini API
genai.configure(api_key="AIzaSyCxKcOOVO8LkvVLmkF82HJZR0f1AjVXmSc")  # Replace with your Gemini API key
model = genai.GenerativeModel("gemini-2.0-flash")

# Extract text from PDF
def extract_text_from_pdf(file_path):
    text = ""
    with fitz.open(file_path) as pdf:
        for page in pdf:
            text += page.get_text()
    return text

# AI Sentiment + Region Analysis
def analyze_sentiment(text):
    prompt = f"""
    You are analyzing government policy-related documents.

    Strictly return output in JSON ONLY.
    Do not add extra text, markdown, or explanations.

    Format:
    {{
        "sentiment": "Agree | Neutral | Disagree",
        "summary": "One short explanation why.",
        "state": "Name of Indian state/UT if identifiable, else Unknown",
        "country": "Country name if identifiable, else Unknown"
    }}

    Document text:
    {text[:3000]}
    """

    response = model.generate_content(prompt)
    raw_output = response.text.strip()

    # Clean Gemini formatting issues (like code fences)
    cleaned = (
        raw_output.replace("```json", "")
                  .replace("```", "")
                  .replace("\n", " ")
                  .strip()
    )

    try:
        import json
        analysis_data = json.loads(cleaned)
        sentiment = analysis_data.get("sentiment", "Unknown")
        summary = analysis_data.get("summary", "No summary provided.")
        state = analysis_data.get("state", "Unknown")
        country = analysis_data.get("country", "Unknown")
    except Exception:
        # fallback if not valid JSON
        if "Agree" in cleaned:
            sentiment = "Agree"
        elif "Neutral" in cleaned:
            sentiment = "Neutral"
        elif "Disagree" in cleaned:
            sentiment = "Disagree"
        else:
            sentiment = "Unknown"
        summary = cleaned
        state = "Unknown"
        country = "Unknown"

    return sentiment, summary, state, country


# Routes
@app.route("/", methods=["GET", "POST"])
def index():
    results = []
    if request.method == "POST":
        uploaded_files = request.files.getlist("pdfs")
        os.makedirs("uploads", exist_ok=True)

        for file in uploaded_files:
            file_path = os.path.join("uploads", file.filename)
            file.save(file_path)

            text = extract_text_from_pdf(file_path)
            sentiment, summary, state, country = analyze_sentiment(text)

            results.append({
                "filename": file.filename,
                "sentiment": sentiment,
                "summary": summary,
                "state": state,
                "country": country
            })

    return render_template("indexs.html", results=results)


if __name__ == "__main__":
    app.run(debug=True)
