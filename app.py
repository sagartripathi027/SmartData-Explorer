import os
from flask import Flask, request, render_template
import pandas as pd
import traceback
from analysis import analyze_data, generate_heatmap
from werkzeug.utils import secure_filename

app = Flask(__name__, template_folder="templates")

# Limit file size (5MB)
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024

# Upload folder
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# ROUTES

@app.route("/")
def home():
    return render_template("index.html")


@app.route("/upload", methods=["POST"])
def upload():

    if "file" not in request.files:
        return "<h3>No file uploaded.</h3>"

    file = request.files["file"]

    if file.filename == "":
        return "<h3>No file selected.</h3>"

    if not file.filename.endswith(".csv"):
        return "<h3>Please upload a CSV file only.</h3>"

    # Secure filename
    filename = secure_filename(file.filename)
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    file.save(filepath)

    try:
        # Read CSV
        df = pd.read_csv(filepath)

        # Run analysis
        result = analyze_data(df)

        # Generate heatmap ✅ (THIS WAS MISSING)
        heatmap = generate_heatmap(df)

        # Preview
        preview = df.head().to_html(classes="table", index=False)

        # Send to frontend
        return render_template(
            "result.html",
            preview=preview,
            result=result,
            heatmap=heatmap
        )

    except Exception as e:
        return f"<pre>{traceback.format_exc()}</pre>"

    finally:
        if os.path.exists(filepath):
            os.remove(filepath)


# RUN APP
if __name__ == "__main__":
    app.run(debug=True)